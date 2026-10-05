# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 Dimcirui

"""Operators of the collision layer (ccl_operators.py of the MHW Model Editor)."""
import bpy
from bpy.types import Operator

from ..core import ccl as K
from . import ccl_functions as F
from . import common as C
from . import ctc_functions as CF
from . import ctc_operators as CO
from .i18n import iface, rpt


class RE6_OT_create_collision_from_bone(Operator):
    bl_label = 'Create Collision'
    bl_idname = 're6_ccl.create_collision_from_bone'
    bl_description = ('Create new ccl collision objects from selected bone(s).'
                      '\nThe button will only be triggered if active ctc collection exists.'
                      '\nSelect one bone to create a sphere or two bones to create a capsule')
    bl_options = {'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.scene.re6_ctc_toolpanel.ctcCollection is not None

    def execute(self, context):
        scene = context.scene
        arm = context.active_object
        sel = [pb.bone for pb in (context.selected_pose_bones or [])]
        if arm is None or arm.type != 'ARMATURE' or len(sel) not in (1, 2):
            C.show_error_message_box(iface('Select one bone to create a sphere or two bones to create a capsule.'))
            return {'CANCELLED'}
        if any(C.bone_fn_id(b) is None for b in sel):
            C.show_error_message_box(iface('Selected bone(s) must be named with format "RE6Bone_xxx".'))
            return {'CANCELLED'}
        tp = scene.re6_ccl_toolpanel
        col = scene.re6_ctc_toolpanel.ctcCollection
        header = CF.find_header(col) or CF.create_header(col, 'CTC_HEADER ' + col.name)
        entry_col = CF.entries_collection('Collision Entries', col, make_new=False)
        c = K.Collision(radius=8.0)
        if len(sel) == 1:
            F.make_sphere(tp, header, entry_col, arm, sel[0].name, c)
        else:
            c.shape = 1
            F.make_capsule(tp, header, entry_col, arm, sel[0].name, sel[1].name, c)
        F.align_collisions(col)
        self.report({'INFO'}, rpt('Created ccl collision from bone.'))
        return {'FINISHED'}


class RE6_OT_only_show_collisions(Operator):
    bl_label = 'Only Show Collisions'
    bl_idname = 're6_ccl.only_show_collisions'
    bl_description = 'Hide other objects and only show ccl collision objects.\nPress the "Show All Objects" button to recover'
    bl_options = {'UNDO'}

    def execute(self, context):
        keep = (C.T_CCL_SPHERE, C.T_CCL_CAPSULE, C.T_CCL_START, C.T_CCL_END)
        reserve = context.scene.re6_ctc_toolpanel.reserveMeshObjects
        for o in context.scene.objects:
            if o.get(C.TYPE) in keep:
                o.hide_viewport = False
            elif not (o.type == 'MESH' and reserve):
                o.hide_viewport = True
        self.report({'INFO'}, rpt('Hid all non ccl collision objects.'))
        return {'FINISHED'}


CLASSES = (RE6_OT_create_collision_from_bone, RE6_OT_only_show_collisions)


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
