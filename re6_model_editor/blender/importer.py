# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 Dimcirui

"""RE6 .mod  ->  Blender scene."""
import colorsys
import json
import os

import bpy
import numpy as np
from mathutils import Matrix, Vector

from ..core import mod211 as M
from ..core import model as MD
from . import common as C
from .i18n import rpt


DEBUG = None        # set to a callable(str) to trace the import step by step


def _dbg(msg):
    if DEBUG:
        DEBUG(msg)


def _to_blender(v):
    """(n,3) RE6 world (Y up, cm) -> Blender (Z up, m); same as IMPORT_MATRIX for vectors"""
    v = np.asarray(v, np.float64)
    return np.stack([v[:, 0], -v[:, 2], v[:, 1]], 1) * 0.01


def _dir_to_blender(v):
    v = np.asarray(v, np.float64)
    return np.stack([v[:, 0], -v[:, 2], v[:, 1]], 1)


def get_material(h, cache):
    name = C.mat_name(h)
    if name in cache:
        return cache[name]
    # one material per import (models share hashes but not textures); Blender numbers clashing names, the exporter
    # only reads the 8 hash digits
    mat = bpy.data.materials.new(C.mat_label(h))
    mat[C.K_MAT_HASH] = '%08x' % h
    rgb = colorsys.hsv_to_rgb(((h >> 8) % 360) / 360.0, 0.35, 0.85)
    mat.diffuse_color = (*rgb, 1.0)
    cache[name] = mat
    return mat


def create_armature(model, name, collection, display_type, bone_size):
    arm = bpy.data.armatures.new(name)
    obj = bpy.data.objects.new(name, arm)
    collection.objects.link(obj)
    arm.display_type = display_type
    obj.show_in_front = True
    view_layer = bpy.context.view_layer
    for o in list(view_layer.objects):
        if o is not None:                    # stale entries appear after objects were deleted
            o.select_set(False)
    view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    world = MD._bone_world(model.bones)
    names = []
    length = bone_size * 0.01                                   # cm -> m
    for b in model.bones:
        eb = arm.edit_bones.new(b.name)
        Wc = C.row_to_matrix(world[b.index])                     # RE6 world matrix, column vectors
        rot = C.ROT_X90 @ Wc.to_3x3()                            # Y up -> Z up
        pos = C.IMPORT_MATRIX @ Wc.translation                   # cm -> m and Y up -> Z up
        m = rot.to_4x4()
        m.translation = pos
        eb.head = pos
        eb.tail = pos + rot @ Vector((0.0, length, 0.0))
        eb.matrix = m
        eb.inherit_scale = 'NONE'
        names.append(eb.name)
    for b in model.bones:
        eb = arm.edit_bones[names[b.index]]
        if b.parent != 255 and b.parent < len(names):
            eb.parent = arm.edit_bones[names[b.parent]]
        eb[C.K_INDEX] = int(b.index)
        eb[C.K_UNK] = int(b.unk)
        if b.mirror < len(names):                       # 255 = no symmetric bone: no key, like the MHW Model Editor
            eb[C.K_MIRROR] = names[b.mirror]
        if b.radius is not None:
            eb[C.K_RADIUS] = float(b.radius)
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.context.view_layer.update()
    obj.select_set(False)
    return obj, names


def create_mesh_object(part, name, bone_names, arm_obj, mat, collection, group_names):
    n = part.vertex_count
    me = bpy.data.meshes.new(name)
    _dbg('mesh %s: new (verts %d faces %d)' % (name, n, len(part.faces)))
    me.from_pydata(_to_blender(part.pos).tolist(), [], part.faces.tolist())
    me.update(calc_edges=True)
    _dbg('mesh %s: from_pydata done' % name)
    if len(me.polygons) != len(part.faces):
        raise RuntimeError('mesh %s lost faces while being created' % name)
    lv = np.empty(len(me.loops), np.int64)
    me.loops.foreach_get('vertex_index', lv)

    _dbg('mesh %s: loops %d' % (name, len(lv)))
    # normals (shadow-only formats carry meaningless normals, leave them to Blender)
    if part.nrm is not None and not part.meta.get('shadow_fmt'):
        nr = _dir_to_blender(part.nrm)
        ln = np.linalg.norm(nr, axis=1, keepdims=True)
        ln[ln < 1e-6] = 1.0
        me.polygons.foreach_set('use_smooth', np.ones(len(me.polygons), bool))
        me.normals_split_custom_set_from_vertices((nr / ln).tolist())

    _dbg('mesh %s: normals done' % name)
    # uv sets (Blender's V axis points up)
    for k, uv in enumerate(part.uvs):
        layer = me.uv_layers.new(name='UVMap%d' % k)
        a = np.asarray(uv, np.float32)[lv].copy()
        a[:, 1] = 1.0 - a[:, 1]
        layer.data.foreach_set('uv', a.ravel())

    _dbg('mesh %s: uv done' % name)
    # original tangents (kept so that an untouched mesh exports exactly what it imported)
    if part.tan is not None:
        at = me.attributes.new('re6_tan', 'FLOAT_VECTOR', 'POINT')
        at.data.foreach_set('vector', _dir_to_blender(part.tan).astype(np.float32).ravel())
        asg = me.attributes.new('re6_tsign', 'FLOAT', 'POINT')
        asg.data.foreach_set('value', np.asarray(part.tsign, np.float32))

    _dbg('mesh %s: tangent attrs done' % name)
    # vertex colours
    if part.col is not None:
        ca = me.color_attributes.new('Color', 'BYTE_COLOR', 'CORNER')
        ca.data.foreach_set('color', (part.col[lv].astype(np.float32) / 255.0).ravel())

    _dbg('mesh %s: colours done' % name)
    obj = bpy.data.objects.new(name, me)
    collection.objects.link(obj)

    # skin weights -> vertex groups
    if arm_obj is not None and part.ids is not None and part.w is not None:
        ids, w = part.ids, part.w
        used = np.unique(ids[w > 0]) if (w > 0).any() else np.unique(ids[:, :1])
        col_of = {int(b): i for i, b in enumerate(used)}
        dense = np.zeros((n, len(used)))
        rows = np.repeat(np.arange(n), ids.shape[1])
        cols = np.array([col_of.get(int(b), 0) for b in ids.ravel()])
        np.add.at(dense, (rows, cols), np.where(w.ravel() > 0, w.ravel(), 0.0))
        for b in used:
            if b >= len(bone_names):
                continue
            vg = obj.vertex_groups.new(name=bone_names[int(b)])
            col = dense[:, col_of[int(b)]]
            idx = np.nonzero(col > 0)[0]
            if len(idx):
                _add_weights(vg, idx, col[idx])
        obj.parent = arm_obj
        mod = obj.modifiers.new('Armature', 'ARMATURE')
        mod.object = arm_obj

    _dbg('mesh %s: weights done' % name)
    me.materials.append(mat)
    C.mesh_set(obj, Mod_Mesh_LOD=int(part.lod), Mod_Mesh_RenderMode=int(part.lod_mask), Mod_Mesh_Flags=int(part.unk3),
               Mod_Mesh_AlphaPriority=int(part.wd_hi), Mod_Mesh_WeightFlags=int(part.wd_flags),
               Mod_Mesh_WeightNum=int(part.wd_infl),
               Mod_Mesh_VertexFormat='%08x' % part.fmt if part.fmt is not None else '',
               Mod_Mesh_ConnectId=int(part.meta.get('ui', 0)), Mod_Mesh_Boundary=int(part.meta.get('tail', 0)),
               Mod_Mesh_Index=int(part.meta.get('index', -1)), Mod_Mesh_Imported=1)
    return obj


def _add_weights(vg, idx, weights):
    # vertex_group.add takes one weight per call; group vertices that share a weight to keep the call count low
    order = np.argsort(weights, kind='stable')
    w_sorted = weights[order]
    i_sorted = idx[order]
    start = 0
    n = len(w_sorted)
    while start < n:
        end = start + 1
        while end < n and w_sorted[end] == w_sorted[start]:
            end += 1
        vg.add(i_sorted[start:end].tolist(), float(w_sorted[start]), 'REPLACE')
        start = end


def load_materials(root, filepath, *, texture_dir='', mrl_path='', previews=True, keep_mrl=True, report=None):
    """build the '<name>.mrl' collection (material entries) for a model collection; looks for the .mrl next to the model only
    (never in the game archives). Returns the MRL collection (None when there is none or keep_mrl is off)"""
    from . import materials as MT
    from . import mrl_objects as MO
    from . import prefs
    p = prefs.get()
    near = MT.find_game_dirs(filepath, ())
    if near:
        prefs.save_game_path(near[0])
    if mrl_path:
        with open(mrl_path, 'rb') as fh:
            data, where = fh.read(), mrl_path
    else:
        data, where = MT.find_mrl(filepath)
    if data is None:
        if report:
            report({'WARNING'}, rpt('RE6: no .mrl found next to %s, materials stay untextured') % os.path.basename(filepath))
        return None
    finder = MT.texture_finder(filepath, texture_dir, p.texture_dir if p else '', p.game_paths() if p else ())
    col, done, missing = MO.import_data(root, data, where, finder, p.pack_textures if p else True, previews=previews)
    if report:
        report({'INFO'}, rpt('RE6: %s: %d of %d materials textured%s') % (
            os.path.basename(where), done, len(MO.model_visuals(root)),
            rpt(', %d materials are not in the .mrl') % len(missing) if missing else ''))
        if missing:
            print('RE6: materials of the meshes that %s does not have: %s' % (os.path.basename(where),
                  ', '.join(MO.model_visuals(root)[h].name for h in missing)))
    if not keep_mrl:
        MO.remove_collection(col)           # the materials keep their textures, only the entries go
        return None
    bpy.context.scene.re6_mrl_toolpanel.mrlCollection = col
    return col


def _hide_lod_collections(lod_cols):
    """hideLODCollections(): only the collection of the highest level is shown"""
    def walk(layer_col):
        for lc in layer_col.children:
            m = C.LOD_NAME.match(lc.name)
            if m and m.group(1) not in ('ALL', '0'):
                lc.hide_viewport = True
            walk(lc)
    walk(bpy.context.view_layer.layer_collection)


def import_mod(filepath, *, clearScene=False, addNestedCollections=True, createCollections=True, importShadow=True,
               importAllLODs=False, ArmatureDisplayType='OCTAHEDRAL', BonesDisplaySize=4.0, loadMaterials=True,
               loadMrlData=False, textureDirectory='', mrlPath='', useBackfaceCulling=False, importArmatureOnly=False,
               loadPhysics=False, report=None):
    """option names are the ones of the MHW Model Editor's mod3 importer (importShadow and textureDirectory are RE6's)"""
    from . import material_names
    material_names.learn_scene()                # names used in this .blend resolve the hashes of the file
    with open(filepath, 'rb') as fh:
        data = fh.read()
    mod = M.Mod211.parse(data)
    model = MD.from_mod(mod, include_shadow=importShadow)
    if clearScene:
        C.clear_scene()
    stem = os.path.splitext(os.path.basename(filepath))[0]
    scene_col = bpy.context.scene.collection
    parent = None
    if createCollections:
        if addNestedCollections:
            parent = bpy.data.collections.new(stem)
            scene_col.children.link(parent)
        root = bpy.data.collections.new(stem + '.mod')
        (parent or scene_col).children.link(root)
        root.color_tag = 'COLOR_01'
        root[C.TYPE] = C.T_MOD
        # model level data needed to write the file back
        root[C.K_SOURCE] = filepath
        root[C.K_ORIGIN] = [float(x) for x in (mod.model_origin if mod.boneCount else np.zeros(3))]
        root[C.K_SCALE] = float(mod.scale if mod.boneCount else 1.0)
        root[C.K_MATERIALS] = json.dumps(['%08x' % h for h in model.materials])
        for gid, sphere in model.groups.items():
            root['%s%03d' % (C.K_GROUP, int(gid))] = [float(x) for x in sphere]
        root[C.K_LOD_DIST] = [int(x) for x in model.lod_dist]
        root[C.K_REMAP] = model.remap.hex()
        root[C.K_TRAILER] = model.trailer.hex()
        root[C.K_TAIL_PAD] = int(model.tail_pad)
        tp = bpy.context.scene.re6_mod_toolpanel
        tp.lastImportCollection = root.name
        bpy.context.scene.re6_mrl_toolpanel.modCollection = root
    else:
        root = scene_col

    arm_obj, bone_names = (None, [])
    if model.has_skeleton:
        arm_obj, bone_names = create_armature(model, stem + ' Armature', root, ArmatureDisplayType, BonesDisplaySize)

    cache = {}
    lod_cols = {}
    cat_cols = {}
    kept = 0
    skipped = 0
    counters = {}
    for part in ([] if importArmatureOnly else sorted(model.parts, key=lambda p: p.group)):
        if not importAllLODs and not (part.lod == 0 or part.lod & 1):
            skipped += 1
            continue
        pcol = root
        level = C.lod_level(part.lod)
        if importAllLODs and createCollections:
            if level not in lod_cols:
                lc = bpy.data.collections.new(C.lod_collection_name(level, root))
                root.children.link(lc)
                lod_cols[level] = lc
            pcol = lod_cols[level]
        if part.is_shadow or part.lod_mask == 0:
            cat = 'Shadow' if part.is_shadow else 'NoRender'
            ck = (id(pcol), cat)
            if ck not in cat_cols:
                cc = bpy.data.collections.new('%s - %s' % (cat, root.name))
                pcol.children.link(cc)
                cc.hide_viewport = True                 # still exported (visibleOnly is off by default)
                cat_cols[ck] = cc
            col = cat_cols[ck]
        else:
            col = pcol
        mh = model.materials[part.material] if part.material < len(model.materials) else 0
        k = counters.get((part.lod, part.group), 0)
        counters[(part.lod, part.group)] = k + 1
        name = 'Group_%d_Sub_%d__%s' % (part.group, k, C.mat_label(mh))
        if importAllLODs:
            name = 'LOD_%s_%s' % (level, name)
        create_mesh_object(part, name, bone_names, arm_obj, get_material(mh, cache), col, None)
        kept += 1
    _hide_lod_collections(lod_cols)
    if cache and (loadMaterials or loadMrlData):
        try:
            load_materials(root, filepath, texture_dir=textureDirectory, mrl_path=mrlPath, previews=loadMaterials,
                           keep_mrl=loadMrlData, report=report)
            if not useBackfaceCulling:
                for m in cache.values():
                    m.use_backface_culling = False
        except Exception as e:      # noqa  (a broken texture must never abort the model import)
            if report:
                report({'WARNING'}, rpt('RE6: materials not loaded: %s') % e)
    if loadPhysics and arm_obj is not None:
        from . import ctc_io
        ctc_path = os.path.splitext(filepath)[0] + '.ctc'
        warnings = []
        if os.path.isfile(ctc_path):
            ctc_io.import_ctc(ctc_path, target=arm_obj, merge=None, load_ccl=True, warnings=warnings, nested=True)
        else:
            print('\033[93mWARNING: An error occurred while reading %s - File is not found.\033[0m' % ctc_path)
    info = dict(meshes=kept, skipped=skipped, bones=len(model.bones), collection=root.name, armature=arm_obj,
                vertices=sum(p.vertex_count for p in model.parts))
    if report:
        report({'INFO'}, rpt('RE6: imported %d meshes, %d bones (%d LOD/shadow meshes skipped)') % (kept, len(model.bones), skipped))
    return info
