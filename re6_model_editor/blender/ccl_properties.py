# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 Dimcirui

"""Property groups of the collision layer (ccl_properties.py of the MHW Model Editor): the tool panel and the collision objects."""
import bpy
from bpy.props import BoolProperty, FloatProperty, FloatVectorProperty, PointerProperty, StringProperty

from . import ccl_nodes as CN
from . import common as C
from .ctc_nodes import set_material_color


def _objects(*types):
    return [o for o in bpy.data.objects if o.get(C.TYPE) in types]


def update_collision_color(self, context):
    set_material_color(CN.collision_material(), tuple(self.collisionColor))


def update_show_names(self, context):
    for o in _objects(C.T_CCL_SPHERE, C.T_CCL_START, C.T_CCL_END):
        o.show_name = self.showCollisionNames


def update_draw_collisions(self, context):
    for o in _objects(C.T_CCL_SPHERE, C.T_CCL_CAPSULE):
        o.show_in_front = self.drawCollisionsThroughObjects


def update_draw_handles(self, context):
    for o in _objects(C.T_CCL_START, C.T_CCL_END):
        o.show_in_front = self.drawCapsuleHandlesThroughObjects


def update_export_ccl_collection(self, context):
    C.set_export_filename(self.exportCTCCollection, '.ccl')


def filter_ctc_collection(self, col):
    return C.is_ctc(col)


def filter_armature(self, obj):
    return obj.type == 'ARMATURE'


class Re6CclToolPanelPG(bpy.types.PropertyGroup):
    lastImportCollection: StringProperty(default='')
    lastExportCollection: StringProperty(default='')
    exportCTCCollection: PointerProperty(
        name='', type=bpy.types.Collection, poll=filter_ctc_collection, update=update_export_ccl_collection,
        description='Set the ctc collection to be exported')
    importCTCArmature: PointerProperty(
        name='', type=bpy.types.Object, poll=filter_armature,
        description='Set the armature to attach ccl objects to.\nIf uncheck, addon will try to find matching armature '
                    'automatically.\nNOTE: If some bones that are used by ccl file are missing, corresponding collision objects '
                    'won\'t be imported')
    collisionColor: FloatVectorProperty(name='Collision Color', subtype='COLOR', size=4, min=0.0, max=1.0,
                                        default=CN.DEFAULT_COLOR, update=update_collision_color)
    showCollisionNames: BoolProperty(name='Show Collision Names', default=True, update=update_show_names,
                                     description='Show CCL Collision Names in 3D View')
    drawCollisionsThroughObjects: BoolProperty(
        name='Draw Collisions Through Objects', default=True, update=update_draw_collisions,
        description='Make all ccl collision objects render through any objects in front of them')
    drawCapsuleHandlesThroughObjects: BoolProperty(
        name='Draw Handles Through Objects', default=True, update=update_draw_handles,
        description='Make all capsule handle objects render through any objects in front of them')


def update_collision_offset(self, context):
    obj = self.id_data
    if obj.get(C.TYPE) == C.T_CCL_CAPSULE:
        for ch in obj.children:
            if ch.get(C.TYPE) == C.T_CCL_START:
                ch.location = [0.01 * v for v in self.StartColOffset]
    elif obj.get(C.TYPE) in (C.T_CCL_SPHERE, C.T_CCL_START, C.T_CCL_END):
        obj.location = [0.01 * v for v in self.StartColOffset]


def update_end_collision_offset(self, context):
    obj = self.id_data
    if obj.get(C.TYPE) == C.T_CCL_CAPSULE:
        for ch in obj.children:
            if ch.get(C.TYPE) == C.T_CCL_END:
                ch.location = [0.01 * v for v in self.EndColOffset]


def update_collision_radius(self, context):
    obj = self.id_data
    if obj.get(C.TYPE) == C.T_CCL_CAPSULE:
        for ch in obj.children:
            if ch.get(C.TYPE) in (C.T_CCL_START, C.T_CCL_END):
                ch.scale = [0.01 * self.ColRadius] * 3
    elif obj.get(C.TYPE) == C.T_CCL_SPHERE:
        obj.scale = [0.01 * self.ColRadius] * 3


class Re6CclCollisionPG(bpy.types.PropertyGroup):
    StartColOffset: FloatVectorProperty(name='Head Offset', size=3, step=10, subtype='XYZ', update=update_collision_offset,
                                        description='Set position of the head collision object')
    EndColOffset: FloatVectorProperty(name='Tail Offset', size=3, step=10, subtype='XYZ',
                                      update=update_end_collision_offset,
                                      description='Set position of the tail collision object')
    ColRadius: FloatProperty(name='Collision Radius', default=0.0, step=10, soft_min=0.0, update=update_collision_radius)


def collision_to_pg(c, obj):
    """a core collision (centimetres) into the properties of a collision object"""
    pg = obj.re6_ccl_collision
    pg.ColRadius = c.radius
    pg.StartColOffset = c.startPos
    pg.EndColOffset = c.endPos


CLASSES = (Re6CclToolPanelPG, Re6CclCollisionPG)


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)
    bpy.types.Scene.re6_ccl_toolpanel = PointerProperty(type=Re6CclToolPanelPG)
    bpy.types.Object.re6_ccl_collision = PointerProperty(type=Re6CclCollisionPG)


def unregister():
    del bpy.types.Object.re6_ccl_collision
    del bpy.types.Scene.re6_ccl_toolpanel
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
