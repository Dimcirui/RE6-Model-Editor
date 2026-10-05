# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 Dimcirui

"""Property groups of the chain layer (the counterpart of ctc_properties.py of the MHW Model Editor): the tool panel, the header, the
chains, the nodes and the clipboard, with the update callbacks that move the display objects, and the conversion between the groups
and the dataclasses of core/ctc.py."""
import math

import bpy
from bpy.props import (BoolProperty, EnumProperty, FloatProperty, FloatVectorProperty, IntProperty, PointerProperty,
                       StringProperty)

from ..core import chain_ids as CI
from ..core import ctc as K
from . import common as C
from . import ctc_nodes as CN
from .ccl_properties import Re6CclCollisionPG

DAMPING_TIP = ('The greater the damping, the greater the resistance, and the slower and more difficult the movement of the chain.'
               '\nThe smaller the damping, the smaller the resistance, and the faster and more flexible the movement of the chain.'
               '\nNormally the damping is 0 or 0.1, shouldn\'t be set to too high.'
               '\nA negative value will cause the chain to gain additional energy and move automatically')
TRANS_FORCE_TIP = ('When the value is 1, the trans force is equal to the acting force. This is the usual value.'
                   '\nWhen the value is greater than 1, the trans force will be greater than the acting force. And the higher the '
                   'value, the more intense the chain moves.'
                   '\nWhen the value is less than 1, the trans force will be less than the acting force. And the smaller the '
                   'value, the weaker the chain moves.'
                   '\nWhen the value is negative, the trans force and acting force will reverse, causing the chain that was '
                   'originally moving backward to move forward')


def objects_of(*types):
    return [o for o in bpy.data.objects if o.get(C.TYPE) in types]


# --- display callbacks of the tool panel ------------------------------------------------------------------------------

def update_chain_color(self, context):
    CN.set_material_color(CN.chain_material(), tuple(self.chainColor))


def update_cone_color(self, context):
    CN.set_material_color(CN.cone_material(), tuple(self.coneColor))


def update_draw_chains(self, context):
    for o in objects_of(C.T_CTC_CHAIN):
        o.show_in_front = self.drawChainsThroughObjects


def update_show_node_names(self, context):
    for o in objects_of(C.T_CTC_NODE):
        o.show_name = self.showNodeNames


def update_draw_nodes(self, context):
    for o in objects_of(C.T_CTC_NODE, C.T_CTC_FRAME):
        o.show_in_front = self.drawNodesThroughObjects


def update_show_cones(self, context):
    for o in objects_of(C.T_CTC_HELPER):
        if not o.get('isLastNode'):
            o.hide_viewport = not self.showAngleLimitCones


def update_draw_cones(self, context):
    for o in objects_of(C.T_CTC_HELPER):
        o.show_in_front = self.drawConesThroughObjects


def update_angle_limit_size(self, context):
    for o in objects_of(C.T_CTC_FRAME):
        o.empty_display_size = 0.01 * self.angleLimitDisplaySize


def update_cone_size(self, context):
    for o in objects_of(C.T_CTC_HELPER):
        cone_scale(o, self.coneDisplaySize)


def update_chain_size(self, context):
    for o in objects_of(C.T_CTC_CHAIN):
        o.data.bevel_depth = 0.001 * self.chainDisplaySize


def update_relation_lines(self, context):
    space = getattr(context, 'space_data', None)
    if space is not None and getattr(space, 'type', '') == 'VIEW_3D':
        space.overlay.show_relationship_lines = self.showRelationLines


def update_hide_last(self, context):
    for o in objects_of(C.T_CTC_HELPER):
        if o.get('isLastNode'):
            o.hide_viewport = self.hideLastNodeAngleLimit


def update_export_ctc_collection(self, context):
    C.set_export_filename(self.exportCTCCollection, '.ctc')


def filter_ctc_collection(self, col):
    return C.is_ctc(col)


def filter_armature(self, obj):
    return obj.type == 'ARMATURE'


def _preset_items(self, context):
    from . import ctc_presets
    return ctc_presets.preset_items(self, context)


def cone_scale(helper, size):
    """the cone of a node is `size` * 0.001 wide; a hinge only keeps its axis (z factor 0.01)"""
    node = helper.parent.parent if helper.parent is not None and helper.parent.parent is not None else None
    z = 1.0
    if node is not None and node.get(C.TYPE) == C.T_CTC_NODE and node.re6_ctc_node.AngleMode == '2':
        z = 0.01
    helper.scale = (0.001 * size, 0.001 * size, 0.001 * size * z)


class Re6CtcToolPanelPG(bpy.types.PropertyGroup):
    lastImportCollection: StringProperty(default='')
    lastExportCollection: StringProperty(default='')

    importCTCCollection: PointerProperty(
        name='', type=bpy.types.Collection, poll=filter_ctc_collection,
        description='Set the ctc collection to merge ctc objects with.\nUse this when you want to merge ctc objects from '
                    'different files')
    exportCTCCollection: PointerProperty(
        name='', type=bpy.types.Collection, poll=filter_ctc_collection, update=update_export_ctc_collection,
        description='Set the ctc collection to be exported')
    importCTCArmature: PointerProperty(
        name='', type=bpy.types.Object, poll=filter_armature,
        description='Set the armature to attach ctc objects to.\nIf uncheck, addon will try to find matching armature '
                    'automatically.\nNOTE: If some bones that are used by ctc file are missing, corresponding ctc nodes won\'t '
                    'be imported')
    CTCChainPresets: EnumProperty(name='', description='', items=_preset_items)
    ctcCollection: PointerProperty(
        name='', type=bpy.types.Collection, poll=filter_ctc_collection,
        description='Set the collection containing the ctc file to edit.\nYou can create a new ctc collection by pressing the '
                    '"Create CTC Collection" button.\nNote that ccl collision will also be included in the ctc collection')

    drawChainsThroughObjects: BoolProperty(
        name='Draw Chains Through Objects', default=True, update=update_draw_chains,
        description='Make all ctc chain objects render through any objects in front of them')
    showNodeNames: BoolProperty(name='Show Node Names', default=True, update=update_show_node_names,
                                description='Show Node Names in 3D View')
    drawNodesThroughObjects: BoolProperty(
        name='Draw Nodes Through Objects', default=True, update=update_draw_nodes,
        description='Make all ctc node and frame objects render through any objects in front of them')
    showAngleLimitCones: BoolProperty(name='Show Cones', default=True, update=update_show_cones,
                                      description='Show Angle Limit Cones in 3D View')
    drawConesThroughObjects: BoolProperty(
        name='Draw Cones Through Objects', default=True, update=update_draw_cones,
        description='Make all angle limit cones render through any objects in front of them')
    angleLimitDisplaySize: FloatProperty(name='Angle Limit Size', default=4.0, min=0.0, step=10,
                                         update=update_angle_limit_size,
                                         description='Set the display size of node angle limits')
    coneDisplaySize: FloatProperty(name='Cone Size', default=5.0, min=0.0, step=10, update=update_cone_size,
                                   description='Set the display size of node angle limit cones')
    chainDisplaySize: FloatProperty(name='Chain Size', default=6.0, min=0.0, step=10, update=update_chain_size,
                                    description='Set the thickness of chain lines')
    chainColor: FloatVectorProperty(name='Chain Color', subtype='COLOR', size=4, min=0.0, max=1.0,
                                    default=CN.CHAIN_COLOR, update=update_chain_color)
    coneColor: FloatVectorProperty(name='Angle Limit Color', subtype='COLOR', size=4, min=0.0, max=1.0,
                                   default=CN.CONE_COLOR, update=update_cone_color)
    showRelationLines: BoolProperty(
        name='Show Relation Lines', default=True, update=update_relation_lines,
        description='Show dotted lines indicating object parents.\nNote that this affects all objects, not just ctc objects')
    hideLastNodeAngleLimit: BoolProperty(
        name='Hide Last Node Cone', default=True, update=update_hide_last,
        description='Hide the last ctc node\'s angle limit cone.\nThis is because the last node is typically unused and has a '
                    'dummy rotation value')
    alignBoneDirection: BoolProperty(
        name='Align Bone Direction', default=True,
        description='Align bones in a vertical and upward direction.\nNote this operation will apply all transformations of '
                    'the current armature')
    reserveMeshObjects: BoolProperty(name='Reserve Mesh Objects', default=False,
                                     description='Reserve mesh objects when hiding other objects')
    nextChainBoneID: IntProperty(name='Next Start Bone ID', default=0, min=0, max=254,
                                 description='"Rename Chain Bones" suggests the first free ID of the available range from this ID on. '
                                             'Every rename moves it past the renamed chain; IDs already used by the armature are '
                                             'skipped')
    chainIdCharacter: EnumProperty(
        name='Character', items=[(i, l, '') for i, l, _ in CI.CHARACTERS],
        description='Which IDs "Rename Chain Bones" may use.\nGeneric is the most conservative choice: only IDs that are free '
                    'in every character\nA character offers all IDs that nothing of that character uses')
    chainIdPart: EnumProperty(
        name='Part', items=[(i, l, '') for i, l, _ in CI.PARTS],
        description='The part of the model (plXXz0 body, plXXz3 head) the chain is on.\nThe available IDs depend on it')
    visibilitySettingsLoaded: BoolProperty(default=False, options={'HIDDEN'})   # prefs.load_ctc_visibility


# --- header -------------------------------------------------------------------------------------------------------------

class Re6CtcHeaderPG(bpy.types.PropertyGroup):
    AttributeFlags: IntProperty(
        name='Attribute Flags', default=0, min=0,
        description='Determine certain movement properties of the chain.\nIt is actually a binary, and the maximum bit may be '
                    '8 bits from testing.\nThe retail files use 0 (most), 64 (mostly seen on armor) and once 12.\n'
                    'The main difference lies in the fifth and seventh bits of binary, and it is unclear what these bits mean')
    StepTime: FloatProperty(
        name='Step Time', default=1.0 / 60.0,
        description='The time interval between each update of the simulation by the physics engine.\nSetting the step time to '
                    '0.16666 seconds means that the physics engine updates 60 times per second, which matches a frame rate of '
                    '60FPS.\nPlease don\'t change this value')
    GravityScaling: FloatProperty(
        name='Gravity Scaling', default=1.0, soft_min=0.0, soft_max=1.0,
        description='Multiple of the gravity applied to the chain, Usually 1.\nWhen the value is negative, the direction of '
                    'gravity reverses.\nWhen the value is 0, there is no gravity')
    GlobalDamping: FloatProperty(name='Global Damping', default=0.0, soft_min=0.0, soft_max=1.0, description=DAMPING_TIP)
    GlobalTransForceCoef: FloatProperty(name='Global TransForce Coef', default=1.0, soft_min=0.0, soft_max=1.0,
                                        description=TRANS_FORCE_TIP)
    SpringScaling: FloatProperty(
        name='Spring Scaling', default=1.0, soft_min=0.0, soft_max=1.0,
        description='Multiple of chain elasticity, Usually 1.\nSetting it to a negative value is not recommended, which will '
                    'lead to some unstable physical behavior')
    WindScale: FloatProperty(
        name='Wind Scale', default=1.0, soft_min=0.0,
        description='The magnitude of the wind force exposed to the chain.\nUsually 1')


HEADER_KEYS = ('AttributeFlags', 'StepTime', 'GravityScaling', 'GlobalDamping', 'GlobalTransForceCoef', 'SpringScaling',
               'WindScale')


def header_to_pg(h, obj):
    pg = obj.re6_ctc_header
    pg.AttributeFlags, pg.StepTime = h.attributeFlags, h.stepTime
    pg.GravityScaling, pg.GlobalDamping = h.gravityScaling, h.globalDamping
    pg.GlobalTransForceCoef, pg.SpringScaling, pg.WindScale = h.globalTransForceCoef, h.springScaling, h.windScale


def header_from_pg(obj):
    pg = obj.re6_ctc_header
    return K.Header(attributeFlags=pg.AttributeFlags, stepTime=pg.StepTime, gravityScaling=pg.GravityScaling,
                    globalDamping=pg.GlobalDamping, globalTransForceCoef=pg.GlobalTransForceCoef,
                    springScaling=pg.SpringScaling, windScale=pg.WindScale)


# --- chain --------------------------------------------------------------------------------------------------------------

class Re6CtcChainPG(bpy.types.PropertyGroup):
    CollisionAttrFlagValue: IntProperty(name='Collision Attr Flag', default=0, min=0, max=255,
                                        description='Various attribute flags that define how chain collides')
    ChainAttrFlagValue: IntProperty(name='Chain Attr Flag', default=1, min=0, max=255,
                                    description='Various attribute flags that define how chain moves')
    unknAttrFlag1: IntProperty(
        name='Unkn Attr Flag 1', default=0, min=0, max=255,
        description='Actually binary. Common values are 0, 1, 17, 32. More testing is needed.\nTaking 1 for the 1 bits seems '
                    'to make the chain harder (or recovers faster) than taking 0.\nTaking 1 for the 2 bits will force the chain '
                    'to stretch, like a spring')
    unknAttrFlag2: IntProperty(name='Unkn Attr Flag 2', default=0, min=0, max=255,
                               description='Actually binary, Usually the value is 0, rarely the value is 1')
    ColAttribute: IntProperty(name='Col Attribute', default=-1, description='Usually the value is -1')
    ColGroup: IntProperty(name='Col Group', default=1, description='Usually the value is 1')
    ColType: IntProperty(name='Col Type', default=1, description='Usually the value is 1')
    Gravity: FloatVectorProperty(
        name='Gravity', size=3, subtype='XYZ', default=(0.0, -9.8, 0.0),
        description='Usually only need to change the Y axis gravity.\nWhen the value is negative, the direction of gravity '
                    'reverses. When the value is 0, there is no gravity.\n"Gravity Scaling" with the header part can be viewed '
                    'as a multiplier, so when both values are negative, the actual direction of gravity is still downward')
    Damping: FloatProperty(name='Damping', default=0.02, soft_min=0.0, soft_max=1.0, description=DAMPING_TIP)
    TransForceCoef: FloatProperty(
        name='TransForce Coef', default=0.2, soft_min=0.0, soft_max=1.0,
        description='If "Global TransForce" is 1, it usually should be set to a value less than 1 here.\n' + TRANS_FORCE_TIP)
    SpringCoef: FloatProperty(
        name='Spring Coef', default=0.015, soft_min=0.0, soft_max=1.0,
        description='If "Spring Scaling" is 1, it usually should be set to a value less than 1 here, even less than 0.1.\n'
                    'The greater the value, the harder the chain and the less the deformation.\nThe smaller the value, the '
                    'softer the chain and the greater the deformation.\nSetting it to a negative value is not recommended, '
                    'which will lead to some unstable physical behavior')
    unknFloat: FloatProperty(name='Unkn Float', default=1.0,
                             description='Unknown value, 1.0 in almost every retail chain')
    LimitForce: FloatProperty(name='Limit Force', default=1.0, description='Usually the value is 1.0')
    FrictionCoef: FloatProperty(name='Friction Coef', default=0.0, soft_min=0.0, soft_max=1.0,
                                description='Usually the value is 0')
    ReflectCoef: FloatProperty(name='Reflect Coef', default=0.1, soft_min=0.0, soft_max=1.0,
                               description='Usually the value is 0.1')


VGROUND_BIT = 8

CHAIN_KEYS = ('CollisionAttrFlagValue', 'ChainAttrFlagValue', 'unknAttrFlag1', 'unknAttrFlag2', 'ColAttribute', 'ColGroup',
              'ColType', 'Gravity', 'Damping', 'TransForceCoef', 'SpringCoef', 'unknFloat', 'LimitForce', 'FrictionCoef',
              'ReflectCoef')


def chain_to_pg(c, obj):
    """a core chain into the properties of a chain object (gravity and the limit force are shown in metres)"""
    pg = obj.re6_ctc_chain
    pg.CollisionAttrFlagValue, pg.ChainAttrFlagValue = c.collisionAttrFlag, c.chainAttrFlag
    pg.unknAttrFlag1, pg.unknAttrFlag2 = c.unknAttrFlag1, c.unknAttrFlag2
    pg.ColAttribute, pg.ColGroup, pg.ColType = c.colAttribute, c.colGroup, c.colType
    pg.Gravity = [v / 100.0 for v in c.gravity]
    pg.Damping, pg.TransForceCoef, pg.SpringCoef, pg.unknFloat = c.damping, c.transForceCoef, c.springCoef, c.unknFloat
    pg.LimitForce = c.limitForce / 100.0
    pg.FrictionCoef, pg.ReflectCoef = c.frictionCoef, c.reflectCoef


def chain_from_pg(obj):
    pg = obj.re6_ctc_chain
    # bit 8 (VGround) is never written: in game the chains of a player model stay behind when the body is moved by a
    # scripted motion (crawl under an obstacle); no retail player ctc sets it
    return K.Chain(collisionAttrFlag=pg.CollisionAttrFlagValue & ~VGROUND_BIT & 255, chainAttrFlag=pg.ChainAttrFlagValue,
                   unknAttrFlag1=pg.unknAttrFlag1, unknAttrFlag2=pg.unknAttrFlag2, colAttribute=pg.ColAttribute,
                   colGroup=pg.ColGroup, colType=pg.ColType, gravity=tuple(round(v * 100.0, 4) for v in pg.Gravity),
                   damping=pg.Damping, transForceCoef=pg.TransForceCoef, springCoef=pg.SpringCoef, unknFloat=pg.unknFloat,
                   limitForce=round(pg.LimitForce * 100.0, 4), frictionCoef=pg.FrictionCoef, reflectCoef=pg.ReflectCoef)


# --- node ---------------------------------------------------------------------------------------------------------------

def update_node_radius(self, context):
    obj = self.id_data
    if not isinstance(obj, bpy.types.Object):          # the clipboard copy on the scene
        return
    obj.empty_display_size = 0.01 * self.BoneColRadius if self.BoneColRadius else 0.01


def helper_of(node_obj):
    """the cone object of a node (node -> frame -> helper)"""
    for f in node_obj.children:
        if f.get(C.TYPE) == C.T_CTC_FRAME:
            for h in f.children:
                if h.get(C.TYPE) == C.T_CTC_HELPER:
                    return h
    return None


def frame_of(node_obj):
    return next((f for f in node_obj.children if f.get(C.TYPE) == C.T_CTC_FRAME), None)


def update_angle_limit(self, context):
    if not isinstance(self.id_data, bpy.types.Object):
        return
    h = helper_of(self.id_data)
    if h is None:
        return
    for mod in h.modifiers:
        if mod.type == 'NODES' and mod.node_group is not None and mod.node_group.name == CN.CONE_TREE:
            from .ccl_nodes import socket_id
            mod[socket_id(mod.node_group, 'AngleLimitRadius')] = self.AngleLimitRadius
            h.update_tag()
    tp = bpy.context.scene.re6_ctc_toolpanel
    cone_scale(h, tp.coneDisplaySize)


class Re6CtcNodePG(bpy.types.PropertyGroup):
    unknByte1: IntProperty(name='Unkn Byte 1', default=0, min=0, max=255, description='Maybe actually binary, default to 0')
    unknByte2: IntProperty(
        name='Unkn Byte 2', default=0, min=0, max=255,
        description='Maybe actually binary or boolean.\nTaking 1 may make the node more compact than taking 0 (uncertain).\n'
                    'The default is 0')
    AngleMode: EnumProperty(
        name='Angle Mode', default='1', update=update_angle_limit,
        items=[('0', 'Free', 'Node will rotate in any direction'), ('1', 'Cone', 'Rotation of node will be limited to a cone'),
               ('2', 'Hinge', 'Rotation of node will be limited to rotation only along the z-axis')])
    CollisionShape: EnumProperty(
        name='Collision Shape', default='1',
        items=[('0', 'None', 'No Collision'), ('1', 'Sphere', 'The shape of collision is a sphere'),
               ('2', 'Capsule', 'The shape of collision is a capsule')])
    unknEnum: EnumProperty(
        name='Unkn Enum', default='1', items=[('0', '0', ''), ('1', '1', ''), ('2', '2', '')],
        description='Unknown enumeration, usually 1, but rarely used 0 and 2.\nNormally, you can default to 1')
    BoneColRadius: FloatProperty(name='Collision Radius', default=5.0, step=10, soft_min=0.0, update=update_node_radius)
    AngleLimitRadius: FloatProperty(
        name='Angle Limit Radius', default=math.pi / 4, step=100, soft_min=0.0, soft_max=math.pi, subtype='ANGLE',
        update=update_angle_limit,
        description='The amount the node is allowed to rotate from it\'s angle limit direction.\nIt is actually in radian, '
                    'representing the top angle of a cone.\nThe bottom radius of the cone is used here to represent the top '
                    'angle, which is incorrect but sufficient to represent the actual size')
    Mass: FloatProperty(
        name='Mass', default=1.0, soft_min=0.0,
        description='Most ctc files default to 1, a few will have values greater than 1 or even around 10, and some will have '
                    'values less than 1.\nIt is not clear how this parameter works')
    ElasticCoef: FloatProperty(
        name='Elastic Coef', default=1.0, soft_min=0.0, soft_max=1.0,
        description='Note that the elastic coef here is different from the spring coef of chain.\nThe smaller the elastic '
                    'coef, the easier the node is to be stretched.\nThe larger the elastic coef, the more likely the node '
                    'will be to maintain its original length.\nChanging this value is not recommended, usually 1, which means '
                    'that the node always maintains its original length')


NODE_KEYS = ('unknByte1', 'unknByte2', 'AngleMode', 'CollisionShape', 'unknEnum', 'BoneColRadius', 'AngleLimitRadius', 'Mass',
             'ElasticCoef')


def node_to_pg(n, obj):
    pg = obj.re6_ctc_node
    pg.unknByte1, pg.unknByte2 = n.unknByte1, n.unknByte2
    pg.AngleMode, pg.CollisionShape, pg.unknEnum = str(n.angleMode), str(n.collisionShape), str(n.unknEnum)
    pg.BoneColRadius, pg.AngleLimitRadius, pg.Mass, pg.ElasticCoef = n.boneColRadius, n.angleLimitRadius, n.mass, n.elasticCoef


def node_from_pg(obj):
    pg = obj.re6_ctc_node
    return K.Node(unknByte1=pg.unknByte1, unknByte2=pg.unknByte2, angleMode=int(pg.AngleMode),
                  collisionShape=int(pg.CollisionShape), unknEnum=int(pg.unknEnum), boneColRadius=pg.BoneColRadius,
                  angleLimitRadius=pg.AngleLimitRadius, mass=pg.Mass, elasticCoef=pg.ElasticCoef)


# --- clipboard ----------------------------------------------------------------------------------------------------------

class Re6CtcClipboardPG(bpy.types.PropertyGroup):
    ctc_type: StringProperty(default='NONE', options={'HIDDEN'})
    ctc_type_name: StringProperty(default='None', options={'HIDDEN'})
    node_prop_type: StringProperty(default='', options={'HIDDEN'})
    node_prop_name: StringProperty(default='', options={'HIDDEN'})
    prop_keys: StringProperty(default='', options={'HIDDEN'})          # the copied properties, comma separated (ctc_operators.CLIP_FIELDS)
    re6_ctc_header: PointerProperty(type=Re6CtcHeaderPG)
    re6_ctc_chain: PointerProperty(type=Re6CtcChainPG)
    re6_ctc_node: PointerProperty(type=Re6CtcNodePG)
    re6_ccl_collision: PointerProperty(type=Re6CclCollisionPG)
    frameOrientation: FloatVectorProperty(name='Frame Orientation', size=3, subtype='XYZ')


CLASSES = (Re6CtcToolPanelPG, Re6CtcHeaderPG, Re6CtcChainPG, Re6CtcNodePG, Re6CtcClipboardPG)


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)
    bpy.types.Scene.re6_ctc_toolpanel = PointerProperty(type=Re6CtcToolPanelPG)
    bpy.types.Scene.re6_ctc_clipboard = PointerProperty(type=Re6CtcClipboardPG)
    bpy.types.Object.re6_ctc_header = PointerProperty(type=Re6CtcHeaderPG)
    bpy.types.Object.re6_ctc_chain = PointerProperty(type=Re6CtcChainPG)
    bpy.types.Object.re6_ctc_node = PointerProperty(type=Re6CtcNodePG)


def unregister():
    del bpy.types.Object.re6_ctc_node
    del bpy.types.Object.re6_ctc_chain
    del bpy.types.Object.re6_ctc_header
    del bpy.types.Scene.re6_ctc_clipboard
    del bpy.types.Scene.re6_ctc_toolpanel
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
