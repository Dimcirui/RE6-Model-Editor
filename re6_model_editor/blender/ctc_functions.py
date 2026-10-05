# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 Dimcirui

"""Building the chain objects from a .ctc, and reading them back (ctc_functions.py of the MHW Model Editor).

The objects::

    header (empty)  ->  chain (curve with one hook per bone)  ->  node (sphere empty, constraints to the bone)  ->  node ...
                                                                  node  ->  frame (arrows, the node matrix)  ->  helper (cone)
"""
import json
import re

import bpy
from mathutils import Matrix

from ..core import ctc as K
from . import ccl_nodes as GN
from . import common as C
from . import ctc_nodes as CN
from . import ctc_properties as CP
from . import objects as O
from .export_errors import add_error
from .i18n import iface

K_TRANSLATION = 'Ctc_Node_Translation'       # custom properties that keep what the object model cannot show
K_ID_HIGH = 'Ctc_Node_BoneIdHigh'
K_MATRIX = 'Ctc_Node_Matrix'
K_EMPTY = 'Ctc_Empty_Chains'


# --- finding things ------------------------------------------------------------------------------------------------------

def search_armature(file_name, target=None):
    """the armature a ctc / ccl file belongs to: the one that was chosen, else the one of the .mod collection of the same name,
    else the active object, else the only armature of the scene (None and a message when there is none)"""
    if target is not None:
        return target
    col = bpy.data.collections.get(re.sub(r'\.(ctc|ccl)$', '.mod', file_name, flags=re.I))
    if col is not None:
        arms = [o for o in col.all_objects if o.type == 'ARMATURE']
        if len(arms) == 1:
            return arms[0]
        if len(arms) > 1:
            C.show_error_message_box(iface('More than one armature was found in the scene. Select an armature before '
                                           'importing the ctc file.'))
            return None
    active = bpy.context.view_layer.objects.active
    if active is not None and active.type == 'ARMATURE':
        return active
    arms = [o for o in bpy.context.scene.objects if o.type == 'ARMATURE']
    if len(arms) == 1:
        return arms[0]
    if arms:
        C.show_error_message_box(iface('More than one armature was found in the scene. Select an armature before importing '
                                       'the ctc file.'))
    else:
        C.show_error_message_box(iface('No armature in scene. The armature from the mod file must be present in order to '
                                       'import the ctc file.'))
    return None


def find_header(col):
    return next((o for o in col.all_objects if o.get(C.TYPE) == C.T_CTC_HEADER), None)


def create_header(col, name, header=None):
    """the header object of a ctc collection (locked to the origin)"""
    obj = O.create_empty(name, [(C.TYPE, C.T_CTC_HEADER)], None, col)
    CP.header_to_pg(header or K.Header(), obj)
    O.lock_transforms(obj)
    return obj


def entries_collection(prefix, ctc_col, make_new):
    return O.get_collection('%s - %s' % (prefix, ctc_col.name), ctc_col, make_new=make_new)


def parent_collection_of(col):
    for c in bpy.data.collections:
        if col.name in c.children:
            return c
    return None


def chain_objects(col):
    """the chain objects of a collection in file order (the number in their names)"""
    def key(o):
        m = re.match(r'CTC_CHAIN_(\d+)', o.name)
        return (int(m.group(1)) if m else 10 ** 6, o.name)
    return sorted((o for o in col.all_objects if o.get(C.TYPE) == C.T_CTC_CHAIN), key=key)


def node_children(obj):
    return [c for c in obj.children if c.get(C.TYPE) == C.T_CTC_NODE]


def chain_nodes(chain_obj):
    """the node objects of a chain, first to last"""
    out = []
    cur = chain_obj
    while True:
        kids = node_children(cur)
        if not kids:
            return out
        cur = kids[0]
        out.append(cur)
        if len(out) > 1000:
            return out


# --- building ------------------------------------------------------------------------------------------------------------

def bone_constraint(obj, name, arm_obj, bone_name, owner=None):
    c = obj.constraints.new(type=name)
    c.target = arm_obj
    c.subtarget = bone_name
    return c


def make_node(tp, entry_col, arm_obj, parent, bone_name, node, frame_rows=None, translation=None, id_high=0):
    """a node with its frame and cone; `frame_rows` = the 3x3 of the file (row vectors)"""
    nobj = O.create_empty(bone_name, [(C.TYPE, C.T_CTC_NODE)], parent, entry_col)
    CP.node_to_pg(node, nobj)
    nobj.empty_display_type = 'SPHERE'
    nobj.show_name = tp.showNodeNames
    nobj.show_in_front = tp.drawNodesThroughObjects
    c = nobj.constraints.new(type='COPY_LOCATION')
    c.target, c.subtarget, c.name = arm_obj, bone_name, 'BoneName'
    c = nobj.constraints.new(type='COPY_ROTATION')
    c.target, c.subtarget, c.name = arm_obj, bone_name, 'BoneRotation'
    c = nobj.constraints.new(type='COPY_SCALE')
    c.target, c.name = _chain_of(parent), 'BoneScale'
    if translation is not None and any(translation):
        nobj[K_TRANSLATION] = list(translation)
    if id_high:
        nobj[K_ID_HIGH] = int(id_high)

    frame = O.create_empty(nobj.name + '_ANGLE_LIMIT', [(C.TYPE, C.T_CTC_FRAME)], nobj, entry_col)
    frame.empty_display_type = 'ARROWS'
    frame.empty_display_size = 0.01 * tp.angleLimitDisplaySize
    frame.show_in_front = tp.drawNodesThroughObjects
    for kind in ('COPY_LOCATION', 'COPY_SCALE'):
        fc = frame.constraints.new(type=kind)
        fc.target = nobj
    frame.rotation_mode = 'XYZ'
    if frame_rows is not None:
        frame.matrix_basis = rows_to_basis(frame_rows)
        frame[K_MATRIX] = [float(v) for row in frame_rows for v in row]

    helper = O.create_curve_empty(nobj.name + '_ANGLE_LIMIT_HELPER', [(C.TYPE, C.T_CTC_HELPER)], frame, entry_col)
    helper.show_wire = True
    helper.hide_select = True
    helper.show_in_front = tp.drawConesThroughObjects
    helper.hide_viewport = not tp.showAngleLimitCones
    CN.add_cone_modifier(helper)
    # the properties push their values into the display objects when they are assigned
    nobj.re6_ctc_node.AngleLimitRadius = node.angleLimitRadius
    nobj.re6_ctc_node.BoneColRadius = node.boneColRadius
    CP.cone_scale(helper, tp.coneDisplaySize)
    return nobj


def _chain_of(obj):
    while obj is not None and obj.get(C.TYPE) != C.T_CTC_CHAIN:
        obj = obj.parent
    return obj


def rows_to_basis(rows):
    """the 3x3 of the file (row vectors, in the frame of the bone) as the transformation of a frame object: the transpose"""
    m = Matrix(((rows[0][0], rows[0][1], rows[0][2]), (rows[1][0], rows[1][1], rows[1][2]),
                (rows[2][0], rows[2][1], rows[2][2])))
    return m.transposed().to_4x4()


def basis_to_rows(frame):
    """the 3x3 (rows) to write for a frame object; the values of the file are kept while the frame was not changed"""
    rot = frame.matrix_basis.to_3x3()
    err = (rot @ rot.transposed() - Matrix.Identity(3))
    if max(abs(v) for row in err for v in row) > 1e-4:
        rot = rot.normalized()
    rows = [tuple(rot[c][r] for c in range(3)) for r in range(3)]            # the transpose
    orig = frame.get(K_MATRIX)
    if orig is not None and len(orig) == 9 and max(abs(orig[3 * r + c] - rows[r][c]) for r in range(3) for c in range(3)) < 1e-5:
        return [tuple(orig[3 * r:3 * r + 3]) for r in range(3)]
    return [tuple(round(v, 6) for v in row) for row in rows]


def make_chain(tp, header, entry_col, arm_obj, name, chain, nodes, bone_names, frames=None):
    """a chain object with its nodes; `bone_names` run from the root to the end of the chain, `nodes` are core nodes
    (frames[i] = (rows, translation, id_high))"""
    cobj = O.create_curve_empty(name, [(C.TYPE, C.T_CTC_CHAIN)], header, entry_col, make_new=True)
    CP.chain_to_pg(chain, cobj)
    cobj.re6_ctc_chain.CollisionAttrFlagValue = cobj.re6_ctc_chain.CollisionAttrFlagValue
    c = cobj.constraints.new('COPY_LOCATION')
    c.target, c.subtarget = arm_obj, bone_names[0]
    cobj.show_in_front = tp.drawChainsThroughObjects
    spline = cobj.data.splines.new('NURBS')
    spline.use_endpoint_u = True
    cobj.data.bevel_depth = 0.001 * tp.chainDisplaySize
    cobj.data.dimensions = '3D'
    cobj.data.use_fill_caps = True
    cobj.data.materials.append(CN.chain_material())
    spline.points.add(len(bone_names) - 1)
    for i, bn in enumerate(reversed(bone_names)):                      # end bone first, root bone last
        bone = arm_obj.data.bones[bn]
        pos = list((arm_obj.matrix_world @ bone.matrix_local).to_translation())
        spline.points[i].co = (*pos, 0.5)
        h = cobj.modifiers.new(bn, 'HOOK')
        h.object = arm_obj
        h.subtarget = bn
        h.vertex_indices_set([i])
    parent = cobj
    last_helper = None
    for k, (bn, node) in enumerate(zip(bone_names, nodes)):
        rows, tr, high = frames[k] if frames else (None, None, 0)
        nobj = make_node(tp, entry_col, arm_obj, parent, bn, node, rows, tr, high)
        parent = nobj
        last_helper = CP.helper_of(nobj)
    if last_helper is not None:
        last_helper['isLastNode'] = 1
        last_helper.hide_viewport = tp.hideLastNodeAngleLimit
    return cobj


def set_chain_bone_color(arm_obj, col=None):
    """colour the bones that a node refers to"""
    objs = col.all_objects if col is not None else bpy.data.objects
    for o in objs:
        if o.get(C.TYPE) == C.T_CTC_NODE:
            c = o.constraints.get('BoneName')
            if c is not None and c.target == arm_obj and c.subtarget in arm_obj.data.bones:
                try:
                    arm_obj.data.bones[c.subtarget].color.palette = 'THEME03'
                except (AttributeError, TypeError):
                    pass


def align_chains(col=None):
    """put the nodes back on their bones: the placement is done by the constraints, so the nodes keep an identity transform"""
    for o in (col.all_objects if col is not None else bpy.data.objects):
        if o.get(C.TYPE) == C.T_CTC_NODE:
            o.location = (0.0, 0.0, 0.0)
            o.rotation_euler = (0.0, 0.0, 0.0)
            o.scale = (1.0, 1.0, 1.0)
    bpy.context.view_layer.update()


# --- checking and reading back ----------------------------------------------------------------------------------------------

def constraint_bone(obj, errors, ids):
    """function id of the bone a node / collision is bound to; adds the errors it finds. `ids` collects {id: [objects]}"""
    c = obj.constraints.get('BoneName')
    if c is None:
        add_error(errors, 'NodeHasNoConstraint', objectName=obj.name)
        return None
    if c.target is None or not c.subtarget:
        add_error(errors, 'InvalidNodeConstraint', objectName=obj.name)
        return None
    bone = c.target.data.bones.get(c.subtarget)
    fid = C.bone_fn_id(bone) if bone is not None else None
    if fid is None or fid > C.MAX_BONE_FUNCTION:
        add_error(errors, 'IncorrectBoneNameFormat', boneName=c.subtarget)
        return None
    ids.setdefault(fid, []).append(obj.name)
    return fid


def check_ctc(col, errors):
    """CTCError dict of a ctc collection (empty when it can be exported); returns (header, [(chain, [nodes])])"""
    objs = list(col.all_objects)
    headers = [o for o in objs if o.get(C.TYPE) == C.T_CTC_HEADER]
    if not headers:
        add_error(errors, 'NoCTCHeader')
    elif len(headers) > 1:
        add_error(errors, 'MoreThanOneCTCHeader')
    for h in headers:
        if h.parent is not None:
            add_error(errors, 'HeaderHasParent', objectName=h.name)
    out = []
    ids = {}
    for chain in chain_objects(col):
        if chain.parent is None or chain.parent.get(C.TYPE) != C.T_CTC_HEADER:
            add_error(errors, 'IncorrectChainParent', objectName=chain.name)
        nodes = []
        cur = chain
        while True:
            kids = node_children(cur)
            if len(kids) > 1:
                add_error(errors, 'ChainHasBranch', objectName=cur.name)
            if not kids or len(nodes) > 1000:
                break
            cur = kids[0]
            nodes.append(cur)
        if len(nodes) < 2:
            add_error(errors, 'ChainHasLessThanTwoNodes', objectName=chain.name)
        out.append((chain, nodes))
    for node in (o for o in objs if o.get(C.TYPE) == C.T_CTC_NODE):
        if node.parent is None or node.parent.get(C.TYPE) not in (C.T_CTC_CHAIN, C.T_CTC_NODE):
            add_error(errors, 'IncorrectNodeParent', objectName=node.name)
        frames = [c for c in node.children if c.get(C.TYPE) == C.T_CTC_FRAME]
        if not frames:
            add_error(errors, 'NodeHasNoFrame', objectName=node.name)
        elif len(frames) > 1:
            add_error(errors, 'NodeHasMoreThanOneFrame', objectName=node.name)
        constraint_bone(node, errors, ids)
    if any(len(v) > 1 for v in ids.values()):
        for names in ids.values():
            if len(names) > 1:
                for n in names:
                    add_error(errors, 'MultipleSameBones', objectName=n)
    return headers[0] if len(headers) == 1 else None, out


def read_ctc(col, errors):
    """a core Ctc of a ctc collection; None (and errors) when it cannot be exported"""
    header, chains = check_ctc(col, errors)
    if errors:
        return None
    out = K.Ctc(CP.header_from_pg(header))
    for chain_obj, nodes in chains:
        c = CP.chain_from_pg(chain_obj)
        for k, nobj in enumerate(nodes):
            n = CP.node_from_pg(nobj)
            ids = {}
            fid = constraint_bone(nobj, {}, ids)
            n.boneFunctionId = fid | (int(nobj.get(K_ID_HIGH, 0)) << 8)
            n.isParent = 1 if k == 0 else 0
            frame = next(f for f in nobj.children if f.get(C.TYPE) == C.T_CTC_FRAME)
            rows = basis_to_rows(frame)
            tr = tuple(nobj.get(K_TRANSLATION, (0.0, 0.0, 0.0)))
            n.nodeMatrix = (*rows[0], 0.0, *rows[1], 0.0, *rows[2], 0.0, *tr, 1.0)
            c.nodes.append(n)
        out.chains.append(c)
    for idx, hexdata in sorted(json.loads(header.get(K_EMPTY, '[]'))):
        chain, _n = K.unpack_chain(bytes.fromhex(hexdata))
        out.chains.insert(min(idx, len(out.chains)), chain)
    return out
