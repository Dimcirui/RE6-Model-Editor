# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 Dimcirui

"""Blender scene  ->  RE6 .mod"""
import json
import re

import bpy
import numpy as np

from ..core import model as MD
from ..core import vertex as V
from ..core.hashes import jamcrc32
from . import common as C
from .export_errors import ExportErrors as ExportError, add_error
from .i18n import rpt

MAX_BONES = 255
MAX_VERTS_PER_MESH = 65535
MAX_WEIGHTS_PER_VERT = 8
MAX_MESHES_TOTAL = 65535
MAX_MATERIALS_TOTAL = 4096


# --------------------------------------------------------------------------- skeleton
def _snap(x, tol=2e-5):
    r = np.round(x, 4)
    return np.where(np.abs(x - r) < tol, r, x)


def derive_mirrors(pos, tol=5e-4):
    """the symmetric bone of every bone, by position (the rule of mod3_functions.py of the MHW Model Editor, which also holds for
    the retail RE6 models): on the x = 0 plane = the bone itself, else the bone at the mirrored x, else 255 (none)"""
    out = []
    for i, p in enumerate(pos):
        if abs(p[0]) <= tol:
            out.append(i)
            continue
        out.append(next((j for j, q in enumerate(pos) if j != i and abs(q[0] + p[0]) <= tol and abs(q[1] - p[1]) <= tol
                         and abs(q[2] - p[2]) <= tol), 255))
    return out


def collect_bones(arm_obj, errors, allowDuplicateBoneNames=False):
    arm = arm_obj.data
    bones = list(arm.bones)
    if len(bones) > MAX_BONES:
        add_error(errors, 'MaxBonesExceeded')
        return [], {}
    # original order first (re6_index), new bones after; then make sure parents come before their children
    def key(b):
        return (b.get(C.K_INDEX, 10 ** 6), b.name)
    pending = sorted(bones, key=key)
    ordered, placed = [], set()
    while pending:
        progressed = False
        for b in list(pending):
            if b.parent is None or b.parent.name in placed:
                ordered.append(b)
                placed.add(b.name)
                pending.remove(b)
                progressed = True
        if not progressed:
            add_error(errors, 'BoneLoop')
            return [], {}
    index_of = {b.name: i for i, b in enumerate(ordered)}
    world = {b.name: C.bone_world_re6(b, arm_obj) for b in ordered}
    derived = derive_mirrors([world[b.name][3, :3] for b in ordered])
    out = []
    for i, b in enumerate(ordered):
        # the id is the number in the bone name and nothing else (like "MhBone_xxx" in the MHW Model Editor): a name that
        # does not carry one, or the ".001" of a second bone with the same id when duplicates are not allowed, is an error
        fn = C.bone_name_id(b.name)
        if fn is None or (C.is_dup_bone_name(b.name) and not allowDuplicateBoneNames):
            add_error(errors, 'IncorrectBoneNameFormat', boneName=b.name)
            fn = 0
        if fn > 254:
            add_error(errors, 'IncorrectBoneNameFormat', boneName=b.name)
        Wb = world[b.name]
        if b.parent is None:
            local, parent = Wb.copy(), 255
        else:
            local = Wb @ np.linalg.inv(world[b.parent.name])
            parent = index_of[b.parent.name]
        rot = local[:3, :3]
        if np.abs(rot - np.eye(3)).max() < 1e-5:
            local[:3, :3] = np.eye(3)
        local[3, :3] = _snap(local[3, :3])
        local[:3, 3] = 0.0
        local[3, 3] = 1.0
        mirror = b.get(C.K_MIRROR, '')
        if mirror:
            mirror_index = index_of.get(mirror, i)
        elif C.K_INDEX in b:                            # an imported bone without the key had no partner
            mirror_index = 255
        else:                                           # a new bone
            mirror_index = derived[i]
        out.append(MD.Bone(i, fn, parent, mirror_index, local, int(b.get(C.K_UNK, 0)),
                           float(b[C.K_RADIUS]) if C.K_RADIUS in b else None))
    return out, index_of


# --------------------------------------------------------------------------- meshes
def _vertex_weights(obj, me, bone_index_of, max_inf, errors, fmt_limit=None):
    """(nv, K) bone indices / weights from the vertex groups (only groups named like a bone) and the number of vertices
    whose influences were cut to fmt_limit (the capacity of a chosen vertex format; without one, more than max_inf is an
    error)"""
    gmap = {}
    for vg in obj.vertex_groups:
        if vg.name in bone_index_of:
            gmap[vg.index] = bone_index_of[vg.name]
    nv = len(me.vertices)
    K = 1
    lists = []
    over = reduced = 0
    limit = fmt_limit or max_inf
    for v in me.vertices:
        gs = [(gmap[g.group], g.weight) for g in v.groups if g.group in gmap and g.weight > 0.0]
        if len(gs) > limit:
            if fmt_limit:
                reduced += 1
            else:
                over += 1
            gs = sorted(gs, key=lambda t: -t[1])[:limit]           # the strongest ones, normalised below
        K = max(K, len(gs))
        lists.append(gs)
    ids = np.zeros((nv, K), np.int64)
    w = np.zeros((nv, K))
    unweighted = 0
    for i, gs in enumerate(lists):
        if not gs:
            unweighted += 1
            continue
        tot = sum(x for _, x in gs)
        gs = sorted(gs, key=lambda t: -t[1])
        for k, (b, x) in enumerate(gs):
            ids[i, k], w[i, k] = b, x / tot
        ids[i, len(gs):] = gs[0][0]
    if over:
        add_error(errors, 'MaxWeightsPerVertexExceeded', objectName='%s (%d vertices)' % (obj.name, over))
    if unweighted == nv:
        add_error(errors, 'NoWeightsOnMesh', objectName=obj.name)
    elif unweighted:
        add_error(errors, 'UnweightedVertices', objectName='%s (%d vertices)' % (obj.name, unweighted))
    return ids, w, reduced


def _strip_dup(name):
    """'pl_cloth.001' -> 'pl_cloth' (Blender's duplicate suffix)"""
    return re.sub(r'\.\d{3}$', '', name)


def _named_hash(name):
    """hash of a material that is not called MAT_xxxxxxxx: the games hash the material name (jamcrc32, see core/hashes.py)"""
    return jamcrc32(_strip_dup(name))


def _material_hash(obj, errors, from_material=True):
    if not from_material:
        base = _strip_dup(obj.name)
        m = re.search(r'(?:^|_)MAT_([0-9a-fA-F]{8})$', base)
        if m:
            return int(m.group(1), 16)
        if '__' in base:
            return _named_hash(base.rsplit('__', 1)[1])
        add_error(errors, 'NoMaterialOnSubMesh', objectName=obj.name)
        return None
    mat = obj.material_slots[0].material if obj.material_slots and obj.material_slots[0].material else None
    if mat is None:
        add_error(errors, 'NoMaterialOnSubMesh', objectName=obj.name)
        return None
    if C.K_MAT_HASH in mat:
        try:
            return int(str(mat[C.K_MAT_HASH]), 16)
        except ValueError:
            pass
    h = C.parse_mat_hash(mat.name)
    if h is None:
        return _named_hash(mat.name)
    return h


def _merge_close_groups(new_of_loop, rep, lv, nrm_loop, uvs_loop, col_loop, ignore_normal):
    """np.unique splits on rounded values; glue back groups of one Blender vertex that only differ by rounding noise"""
    vids = lv[rep]
    order = np.argsort(vids, kind='stable')
    sv = vids[order]
    if len(rep) < 2:
        return new_of_loop, rep
    same_v = sv[1:] == sv[:-1]
    if not same_v.any():
        return new_of_loop, rep
    parent = np.arange(len(rep))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    i = 0
    n = len(order)
    while i < n:
        j = i + 1
        while j < n and sv[j] == sv[i]:
            j += 1
        if j - i > 1:
            grp = order[i:j]
            for a in range(len(grp)):
                for b in range(a + 1, len(grp)):
                    ga, gb = grp[a], grp[b]
                    la, lb = rep[ga], rep[gb]
                    if not ignore_normal and np.abs(nrm_loop[la] - nrm_loop[lb]).max() > 0.02:
                        continue
                    if any(np.abs(u[la] - u[lb]).max() > 3e-4 for u in uvs_loop):
                        continue
                    if col_loop is not None and (col_loop[la] != col_loop[lb]).any():
                        continue
                    ra, rb = find(ga), find(gb)
                    if ra != rb:
                        parent[max(ra, rb)] = min(ra, rb)
        i = j
    roots = np.array([find(a) for a in range(len(rep))])
    if (roots == np.arange(len(rep))).all():
        return new_of_loop, rep
    uniq = np.unique(roots)                          # sorted -> keeps first-appearance order of the survivors
    remap = np.zeros(len(rep), np.int64)
    remap[uniq] = np.arange(len(uniq))
    final = remap[roots]
    return final[new_of_loop], rep[uniq]


def extract_part(obj, arm_obj, bone_index_of, dg, errors, warnings, max_inf=MAX_WEIGHTS_PER_VERT):
    me = bpy.data.meshes.new_from_object(obj, preserve_all_data_layers=True, depsgraph=dg)
    try:
        nv = len(me.vertices)
        if nv == 0:
            add_error(errors, 'NoVerticesOnSubMesh', objectName=obj.name)
            return None
        if len(me.polygons) == 0:
            add_error(errors, 'NoFacesOnSubMesh', objectName=obj.name)
            return None
        me.calc_loop_triangles()
        nl = len(me.loops)
        nt = len(me.loop_triangles)
        tri_loops = np.empty(nt * 3, np.int64)
        me.loop_triangles.foreach_get('loops', tri_loops)
        tri_loops = tri_loops.reshape(-1, 3)
        lv = np.empty(nl, np.int64)
        me.loops.foreach_get('vertex_index', lv)
        loose = nv - len(np.unique(lv))
        if loose:                                     # only the vertices of faces are written (retail files have some, too)
            warnings.append('Mesh "%s": %d loose vertices are not exported.' % (obj.name, loose))

        co = np.empty(nv * 3, np.float64)
        me.vertices.foreach_get('co', co)
        co = co.reshape(-1, 3)
        mw = np.array(obj.matrix_world)
        cow = co @ mw[:3, :3].T + mw[:3, 3]
        pos_re6_all = np.stack([cow[:, 0], cow[:, 2], -cow[:, 1]], 1) * 100.0

        cn = np.empty(nl * 3, np.float32)
        me.corner_normals.foreach_get('vector', cn)
        cn = cn.reshape(-1, 3).astype(np.float64) @ mw[:3, :3].T
        cn /= np.maximum(np.linalg.norm(cn, axis=1, keepdims=True), 1e-9)
        nrm_loop = np.stack([cn[:, 0], cn[:, 2], -cn[:, 1]], 1)

        fmt = _chosen_format(obj)
        f = V.FORMATS.get(fmt)                        # a chosen vertex format: the data it can not hold is dropped
        dropped = []
        no_uv_fmt = f is not None and not f.uvs
        uvs_loop = []
        for layer in me.uv_layers:
            a = np.empty(nl * 2, np.float32)
            layer.data.foreach_get('uv', a)
            a = a.reshape(-1, 2).copy()
            a[:, 1] = 1.0 - a[:, 1]
            uvs_loop.append(a)
        if not uvs_loop and not no_uv_fmt and C.mesh_get(obj, 'Mod_Mesh_RenderMode') != MD.SHADOW_MASK:
            add_error(errors, 'NoUVMapOnSubMesh', objectName=obj.name)
            return None
        if f is not None and len(uvs_loop) > len(f.uvs):
            dropped.append('%d UV map(s) dropped' % (len(uvs_loop) - len(f.uvs)))
            uvs_loop = uvs_loop[:len(f.uvs)]

        col_loop = None
        if len(me.color_attributes) and f is not None and f.col is None:
            dropped.append('vertex colors dropped')
        elif len(me.color_attributes):
            ca = me.color_attributes.active_color or me.color_attributes[0]
            a = np.empty(len(ca.data) * 4, np.float32)
            ca.data.foreach_get('color', a)
            a = np.clip(a.reshape(-1, 4) * 255.0 + 0.5, 0, 255).astype(np.uint8)
            col_loop = a if ca.domain == 'CORNER' else a[lv]

        # ---- split vertices where normal / uv / colour differ (tangents are averaged afterwards) ----
        shadow_like = no_uv_fmt or C.mesh_get(obj, 'Mod_Mesh_RenderMode') == MD.SHADOW_MASK
        cols = [lv[:, None].astype(np.float64)]
        if not shadow_like:
            cols.append(np.rint(nrm_loop * 1e3))
        for u in uvs_loop:
            cols.append(np.rint(u.astype(np.float64) * 1e4))
        if col_loop is not None:
            cols.append(col_loop.astype(np.float64))
        key = np.concatenate(cols, axis=1)
        _, first, inv = np.unique(key, axis=0, return_index=True, return_inverse=True)
        inv = inv.reshape(-1)
        order = np.argsort(first)
        rank = np.empty_like(order)
        rank[order] = np.arange(len(order))
        new_of_loop = rank[inv]
        rep = first[order]                           # representative loop of every new vertex
        new_of_loop, rep = _merge_close_groups(new_of_loop, rep, lv, nrm_loop, uvs_loop, col_loop, shadow_like)
        nnew = len(rep)
        if nnew > MAX_VERTS_PER_MESH:
            add_error(errors, 'MaxVerticesExceeded', objectName='%s (%d vertices, max %d)' % (obj.name, nnew, MAX_VERTS_PER_MESH))
            return None
        nrm_v = nrm_loop[rep]
        if shadow_like:                               # one averaged normal per vertex
            acc = np.zeros((nnew, 3))
            np.add.at(acc, new_of_loop, nrm_loop)
            ln = np.linalg.norm(acc, axis=1, keepdims=True)
            nrm_v = np.where(ln > 1e-9, acc / np.maximum(ln, 1e-9), nrm_loop[rep])
        tan_v = sign_v = None
        faces = new_of_loop[tri_loops]
        src_v = lv[rep]

        part = MD.Part(name=obj.name, pos=pos_re6_all[src_v], faces=faces, nrm=nrm_v,
                       uvs=[u[rep] for u in uvs_loop], col=None if col_loop is None else col_loop[rep])
        # tangents: stored ones when the vertex count did not change, else generated like the game data
        at, asg = me.attributes.get('re6_tan'), me.attributes.get('re6_tsign')
        if at is not None and asg is not None and len(at.data) == nv:
            t = np.empty(nv * 3, np.float32)
            at.data.foreach_get('vector', t)
            t = t.reshape(-1, 3).astype(np.float64)[src_v] @ mw[:3, :3].T
            sg = np.empty(nv, np.float32)
            asg.data.foreach_get('value', sg)
            part.tan = np.stack([t[:, 0], t[:, 2], -t[:, 1]], 1)
            part.tsign = np.where(sg[src_v] < 0, -1.0, 1.0)
        elif part.uvs:
            part.tan, part.tsign = MD.compute_tangents(part.pos, part.nrm, part.uvs[0], part.faces)
        if arm_obj is not None:
            fmt_limit = f.influences if f is not None and f.pos == 's16' else None
            ids, w, reduced = _vertex_weights(obj, me, bone_index_of, max_inf, errors, fmt_limit)
            if reduced:
                dropped.append('bone influences cut to %d on %d vertices' % (fmt_limit, reduced))
            part.ids, part.w = ids[src_v], w[src_v]
        if dropped:
            warnings.append('Mesh "%s" exported as %s: %s.' % (obj.name, V.official_name(fmt), ', '.join(dropped)))
        return part
    finally:
        bpy.data.meshes.remove(me)


def _chosen_format(obj):
    """the vertex format set on a mesh (Mod_Mesh_VertexFormat, hex), None = Auto; an unreadable value is returned as -1"""
    value = C.mesh_get(obj, 'Mod_Mesh_VertexFormat')
    if not value:
        return None
    try:
        return int(value, 16)
    except (TypeError, ValueError):
        return -1


def check_format(part, obj, skeleton, errors):
    """VertexFormatMismatch when the chosen layout can not be used at all: an unreadable value, or a skinned layout on a
    model without a skeleton (and the other way round); data a usable layout can not hold was already dropped"""
    if part.fmt is None:
        return
    if part.fmt not in V.FORMATS:
        add_error(errors, 'VertexFormatMismatch', objectName='%s (unknown vertex format "%s")'
                  % (obj.name, C.mesh_get(obj, 'Mod_Mesh_VertexFormat')))
        return
    n_inf = MD.influence_count(part.ids, part.w) if skeleton and part.ids is not None else 0
    problems = V.fit_problems(part.fmt, skeleton, n_inf, len(part.uvs), part.col is not None, part.is_shadow)
    if problems:
        add_error(errors, 'VertexFormatMismatch', objectName='%s (%s)' % (obj.name, '; '.join(problems)))


def _lod_mask(o_name, level, highest, collection):
    """the lod mask of a mesh from the LOD collection it is in; a mesh keeps the mask it was imported with as long as that
    mask belongs to the same level (a mask like 3 covers several levels)"""
    obj = bpy.data.objects.get(o_name)
    stored = C.mesh_get(obj, 'Mod_Mesh_LOD') if obj is not None and obj.type == 'MESH' else None
    if stored is not None and obj.data.get('Mod_Mesh_Imported') and C.lod_level(stored) == level:
        return stored
    return C.lod_mask(level, highest)


def _mask_of(obj, lod_masks):
    return lod_masks.get(obj.name, C.mesh_get(obj, 'Mod_Mesh_LOD'))


def _apply_props(part, obj, materials, mat_hash):
    g = lambda k: C.mesh_get(obj, k)           # noqa
    if mat_hash is not None:
        if mat_hash not in materials:
            materials.append(mat_hash)
        part.material = materials.index(mat_hash)
    if g('Mod_Mesh_Imported'):
        part.group, part.lod, part.lod_mask = C.group_of(obj), g('Mod_Mesh_LOD'), g('Mod_Mesh_RenderMode')
        part.unk3, part.wd_hi = g('Mod_Mesh_Flags'), g('Mod_Mesh_AlphaPriority')
        part.wd_flags, part.wd_infl = g('Mod_Mesh_WeightFlags'), g('Mod_Mesh_WeightNum')
        if g('Mod_Mesh_Index') >= 0:
            part.meta['table'] = g('Mod_Mesh_Index')
        if g('Mod_Mesh_ConnectId') and g('Mod_Mesh_Boundary'):
            part.meta['ui'], part.meta['tail'] = g('Mod_Mesh_ConnectId'), g('Mod_Mesh_Boundary')
            part.meta['index'] = -1                 # marks "declared by the file"; keeps unk3 / wd as stored
    else:
        part.group = C.group_of(obj)
        part.lod, part.lod_mask = g('Mod_Mesh_LOD'), g('Mod_Mesh_RenderMode')
        part.unk3 = g('Mod_Mesh_Flags')
    fmt = _chosen_format(obj)                   # imported or set with Set Vertex Format; None = Auto
    part.fmt = fmt


def make_shadow_part(part):
    sp = MD.Part(name=part.name + '_shadow', pos=part.pos, faces=part.faces, nrm=part.nrm, ids=part.ids, w=part.w,
                 material=part.material, group=part.group, lod=part.lod, lod_mask=MD.SHADOW_MASK, unk3=0xC3)
    return sp


# --------------------------------------------------------------------------- main
def export_mod(filepath, collection, *, selectedOnly=False, visibleOnly=False, shadowMode='KEEP', exportAllLODs=True,
               useBlenderMaterialName=False, allowDuplicateBoneNames=False, report=None):
    """option names are the ones of the MHW Model Editor's mod3 exporter (shadowMode is RE6's)"""
    errors, warnings = {}, []
    if collection is None:
        add_error(errors, 'NoTargetModCollection')
        raise ExportError(errors)
    if not C.is_mod(collection):
        warnings.append('Collection "%s" was not created by the importer; defaults are used for missing model data.' % collection.name)
    if bpy.context.object and bpy.context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')

    objs = list(collection.all_objects)
    arms = [o for o in objs if o.type == 'ARMATURE']
    if len(arms) > 1:
        add_error(errors, 'MoreThanOneArmature')
    arm_obj = arms[0] if arms else None
    levels = [m.group(1) for c in collection.children_recursive if (m := C.LOD_NAME.match(c.name))]
    if len(levels) != len(set(levels)):
        add_error(errors, 'MultipleSameLodCollections')
    lod_of, highest = C.lod_levels_of(collection)
    lod_masks = {n: _lod_mask(o_name=n, level=lv, highest=highest, collection=collection) for n, lv in lod_of.items()}
    meshes = [o for o in objs if o.type == 'MESH' and not o.get(C.K_EXCLUDE) and (not selectedOnly or o.select_get())
              and (exportAllLODs or not C.mesh_get(o, 'Mod_Mesh_Imported') or _mask_of(o, lod_masks) == 0
                   or _mask_of(o, lod_masks) & 1)
              and (not visibleOnly or o.visible_get())]
    if not meshes:
        add_error(errors, 'NoMeshesInCollection')
    if errors:
        raise ExportError(errors)

    prev_pose = None
    if arm_obj is not None:
        prev_pose = arm_obj.data.pose_position
        arm_obj.data.pose_position = 'REST'
        bpy.context.view_layer.update()
    try:
        bones, index_of = ([], {})
        if arm_obj is not None:
            bones, index_of = collect_bones(arm_obj, errors, allowDuplicateBoneNames)
        materials = [int(h, 16) for h in json.loads(collection.get(C.K_MATERIALS, '[]'))]
        dg = bpy.context.evaluated_depsgraph_get()
        parts = []
        meshes.sort(key=lambda o: (C.mesh_get(o, 'Mod_Mesh_Index') if C.mesh_get(o, 'Mod_Mesh_Index') >= 0 else 10 ** 9, o.name))
        for obj in meshes:
            part = extract_part(obj, arm_obj, index_of, dg, errors, warnings)
            if part is None:
                continue
            _apply_props(part, obj, materials, _material_hash(obj, errors, useBlenderMaterialName))
            if obj.name in lod_masks:
                part.lod = lod_masks[obj.name]
            check_format(part, obj, arm_obj is not None, errors)
            parts.append(part)
    finally:
        if arm_obj is not None:
            arm_obj.data.pose_position = prev_pose
            bpy.context.view_layer.update()
    if errors:
        raise ExportError(errors)

    if shadowMode == 'NONE':
        for p in parts:
            if p.lod_mask not in (0, MD.SHADOW_MASK):
                p.lod_mask = 0xFFFF
    elif shadowMode == 'REGENERATE':
        withs = []
        for p in parts:
            if p.lod_mask not in (0, 0xFFFF, MD.SHADOW_MASK):
                withs.append(make_shadow_part(p))
            withs.append(p)
        parts = withs
    if len(parts) > MAX_MESHES_TOTAL:
        add_error(errors, 'TotalMeshesExceeded')
        raise ExportError(errors)

    groups = {int(k[len(C.K_GROUP):]): tuple(collection[k]) for k in collection.keys()
              if k.startswith(C.K_GROUP) and k[len(C.K_GROUP):].isdigit()}
    remap = bytes.fromhex(collection.get(C.K_REMAP, '')) if collection.get(C.K_REMAP) else b''
    trailer = bytes.fromhex(collection.get(C.K_TRAILER, '')) if collection.get(C.K_TRAILER) else b''
    lod_dist = tuple(collection.get(C.K_LOD_DIST, MD.DEFAULT_LOD_DIST))
    # the material table lists what the meshes use and nothing else (the stored table of an imported model only gives the order)
    if all(0 <= p.material < len(materials) for p in parts):
        used = sorted({p.material for p in parts})
        new_index = {o: n for n, o in enumerate(used)}
        materials = [materials[o] for o in used]
        for p in parts:
            p.material = new_index[p.material]
    if len(materials) > MAX_MATERIALS_TOTAL:
        add_error(errors, 'TotalMaterialsExceeded')
        raise ExportError(errors)
    model = MD.Model(bones, parts, materials, groups, lod_dist, remap, trailer, None, int(collection.get(C.K_TAIL_PAD, 0)))
    quant = None
    if C.K_ORIGIN in collection and C.K_SCALE in collection:
        quant = (list(collection[C.K_ORIGIN]), float(collection[C.K_SCALE]))
    try:
        mod = MD.to_mod(model, quant=quant)
        blob = mod.serialize()
    except (ValueError, KeyError) as e:
        print('RE6 export: %s' % e)
        add_error(errors, 'ExportFailed')
        raise ExportError(errors)
    with open(filepath, 'wb') as fh:
        fh.write(blob)
    from . import material_names
    material_names.remember({material_names.mesh_suffix(o) for o in meshes} |
                            {s.material.name for o in meshes for s in o.material_slots if s.material is not None})
    info = dict(meshes=len(mod.meshes), bones=len(bones), vertices=sum(m.vertexCount for m in mod.meshes),
                triangles=len(mod.faces) // 3, size=len(blob), warnings=warnings)
    if report:
        for w in warnings:
            report({'WARNING'}, w)
        report({'INFO'}, rpt('RE6: exported %d meshes, %d bones -> %s') % (info['meshes'], info['bones'], filepath))
    return info
