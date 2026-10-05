# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 Dimcirui

"""Building the collision objects from a .ccl, and reading them back (ccl_functions.py of the MHW Model Editor).

A sphere is one curve object (parent: the ctc header, a "BoneName" child-of constraint puts it on its bone); a capsule is a root
curve object that holds the properties, with a head and a tail handle as children.
"""
import json

import bpy
from mathutils import Matrix

from ..core import ccl as K
from . import ccl_nodes as GN
from . import common as C
from . import ctc_functions as F
from . import objects as O
from .export_errors import add_error

K_DATA = 'Ccl_Data'              # the values of the file (cm), kept while the object is not moved
K_END_BONE = 'Ccl_EndBone'       # the end bone of a sphere when the file has one


def free_index():
    n = 0
    while O.name_in_use('CCL_%02d' % n):
        n += 1
    return n


def _child_of(obj, arm_obj, bone_name):
    c = obj.constraints.new(type='CHILD_OF')
    c.name = 'BoneName'
    c.target = arm_obj
    c.subtarget = bone_name
    c.use_scale_x = c.use_scale_y = c.use_scale_z = False
    c.inverse_matrix = Matrix.Identity(4)       # a new constraint computes the inverse of its target, which would cancel the bone
    return c


def make_sphere(tp, header, entry_col, arm_obj, bone_name, collision):
    name = 'CCL_%02d_SPHERE %s' % (free_index(), bone_name)
    obj = O.create_curve_empty(name, [(C.TYPE, C.T_CCL_SPHERE)], header, entry_col, make_new=True)
    _child_of(obj, arm_obj, bone_name)
    GN.add_modifier(obj, GN.sphere_tree())
    obj.show_name = tp.showCollisionNames
    obj.show_in_front = tp.drawCollisionsThroughObjects
    from .ccl_properties import collision_to_pg
    collision_to_pg(collision, obj)
    obj[K_DATA] = json.dumps([*collision.startPos, 0.0, 0.0, 0.0, collision.radius])
    if collision.endBoneId != K.NO_BONE:
        obj[K_END_BONE] = int(collision.endBoneId)
    return obj


def make_capsule(tp, header, entry_col, arm_obj, start_bone, end_bone, collision):
    idx = free_index()
    root = O.create_curve_empty('CCL_%02d_CAPSULE - %s > %s' % (idx, start_bone, end_bone),
                                [(C.TYPE, C.T_CCL_CAPSULE)], header, entry_col, make_new=True)
    O.lock_transforms(root)
    root.show_in_front = tp.drawCollisionsThroughObjects
    head = O.create_fake_empty_sphere('CCL_%02d_CAPSULE_HEAD %s' % (idx, start_bone), [(C.TYPE, C.T_CCL_START)], root, entry_col)
    _child_of(head, arm_obj, start_bone)
    tail = O.create_fake_empty_sphere('CCL_%02d_CAPSULE_TAIL %s' % (idx, end_bone), [(C.TYPE, C.T_CCL_END)], root, entry_col)
    _child_of(tail, arm_obj, end_bone)
    c = tail.constraints.new(type='COPY_SCALE')
    c.target = head
    for h in (head, tail):
        h.show_name = tp.showCollisionNames
        h.show_in_front = tp.drawCapsuleHandlesThroughObjects
    tree = GN.capsule_tree()
    mod = GN.add_modifier(root, tree)
    mod[GN.socket_id(tree, 'Start Object')] = head
    mod[GN.socket_id(tree, 'End Object')] = tail
    from .ccl_properties import collision_to_pg
    collision_to_pg(collision, root)
    root[K_DATA] = json.dumps([*collision.startPos, *collision.endPos, collision.radius])
    return root


def align_collisions(col=None):
    bpy.context.view_layer.update()


def check_constraint(obj, errors, ids=None):
    """function id of the bone of a collision object (None and an error when there is none)"""
    return F.constraint_bone(obj, errors, ids if ids is not None else {})


def read_ccl(col, errors):
    """a core Ccl of a ctc collection; None (and errors) when it cannot be exported"""
    spheres, capsules = [], []
    for o in col.all_objects:
        t = o.get(C.TYPE)
        if t == C.T_CCL_SPHERE:
            spheres.append(o)
        elif t == C.T_CCL_CAPSULE:
            capsules.append(o)
    items = []
    for o in spheres:
        fid = check_constraint(o, errors)
        items.append((o, None, None, fid))
    for o in capsules:
        heads = [c for c in o.children if c.get(C.TYPE) == C.T_CCL_START]
        tails = [c for c in o.children if c.get(C.TYPE) == C.T_CCL_END]
        if len(heads) > 1:
            add_error(errors, 'CapsuleHasMultipleHeads', objectName=o.name)
        elif not heads:
            add_error(errors, 'CapsuleHasNoHead', objectName=o.name)
        if len(tails) > 1:
            add_error(errors, 'CapsuleHasMultipleTails', objectName=o.name)
        elif not tails:
            add_error(errors, 'CapsuleHasNoTail', objectName=o.name)
        if len(heads) == 1 and len(tails) == 1:
            items.append((o, heads[0], tails[0], (check_constraint(heads[0], errors), check_constraint(tails[0], errors))))
    if errors:
        return None

    def key(item):
        n = item[0].name.split('_')
        return (int(n[1]) if len(n) > 1 and n[1].isdigit() else 10 ** 6, item[0].name)
    out = K.Ccl()
    for o, head, tail, fid in sorted(items, key=key):
        pg = o.re6_ccl_collision
        data = json.loads(o[K_DATA]) if K_DATA in o else None
        if head is None:                                        # sphere
            vals = [100.0 * v for v in o.location] + [0.0] * 3 + [100.0 * o.scale[0]]
            c = K.Collision(fid, int(o.get(K_END_BONE, K.NO_BONE)), 0)
        else:                                                   # capsule
            vals = [100.0 * v for v in head.location] + [100.0 * v for v in tail.location] + [100.0 * head.scale[0]]
            c = K.Collision(fid[0], fid[1], 1)
        vals = [_keep(v, data[i] if data else None) for i, v in enumerate(vals)]
        c.startPos, c.endPos, c.radius = tuple(vals[0:3]), tuple(vals[3:6]), vals[6]
        out.collisions.append(c)
    return out


def _keep(value, original):
    """values are shown in metres (floats), so a value that was not changed is written exactly as it was read"""
    if original is not None and abs(value - original) < 5e-4:
        return original
    return round(value, 4)
