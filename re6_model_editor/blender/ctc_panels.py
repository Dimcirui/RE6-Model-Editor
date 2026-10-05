# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 Dimcirui

"""Panels of the chain and collision layers: the "RE6 Chain" tab of the 3D view and the property panels of the objects
(ctc_panels.py of the MHW Model Editor). The property layouts are written once and used by both."""
import bpy

from . import common as C
from . import prefs
from .i18n import iface

TAB = 'RE6 Chain'


# --- layouts of the properties, used by the data tab panels and by the Properties sub panel ---------------------------------

def _row(col, scale=1.1):
    row = col.row(align=True)
    row.scale_y = scale
    return row


def draw_header(layout, obj):
    pg = obj.re6_ctc_header
    box = layout.box()
    col = box.column()
    col.row().label(text='Note: The header properties here will affect all chains.', icon='ERROR')
    for name in ('AttributeFlags', 'StepTime'):
        _row(col).prop(pg, name)
    _row(col).label(text='')
    _row(col).prop(pg, 'GravityScaling', slider=True)
    _row(col).prop(pg, 'GlobalDamping', slider=True)
    _row(col).prop(pg, 'GlobalTransForceCoef', text='Global TransForce', slider=True)
    _row(col).prop(pg, 'SpringScaling', slider=True)
    _row(col).label(text='')
    _row(col).prop(pg, 'WindScale')


def draw_chain(layout, obj):
    pg = obj.re6_ctc_chain
    box = layout.box()
    col = box.column()
    row = _row(col)
    row.prop(pg, 'CollisionAttrFlagValue')
    row.operator('re6_ctc.set_collision_flags', icon='DOWNARROW_HLT', text='')
    row = _row(col)
    row.prop(pg, 'ChainAttrFlagValue')
    row.operator('re6_ctc.set_chain_flags', icon='DOWNARROW_HLT', text='')
    row = _row(col)
    row.prop(pg, 'unknAttrFlag1', text='Unkn Flags')
    row.prop(pg, 'unknAttrFlag2', text='')
    _row(col).label(text='')
    row = _row(col)
    row.prop(pg, 'Gravity', index=0, text='Gravity')
    row.prop(pg, 'Gravity', index=1, text='')
    row.prop(pg, 'Gravity', index=2, text='')
    _row(col).prop(pg, 'Damping', slider=True)
    _row(col).prop(pg, 'TransForceCoef', slider=True)
    _row(col).prop(pg, 'SpringCoef', slider=True)
    _row(col).label(text='')
    row = _row(col)
    row.prop(pg, 'ColAttribute', text='Collider')
    row.prop(pg, 'ColGroup', text='')
    row.prop(pg, 'ColType', text='')
    row = _row(col)
    row.prop(pg, 'LimitForce', text='Other')
    row.prop(pg, 'FrictionCoef', slider=True, text='')
    row.prop(pg, 'ReflectCoef', slider=True, text='')
    _row(col).prop(pg, 'unknFloat')


def draw_node(layout, obj):
    pg = obj.re6_ctc_node
    box = layout.box()
    col = box.column()

    def line(prop, op=None, **kw):
        row = _row(col)
        row.prop(pg, prop, **kw)
        if op:
            row.operator('re6_ctc.' + op, icon='COPYDOWN', text='')
        return row

    row = _row(col)
    row.prop(pg, 'unknByte1', text='Unkn Flags')
    row.prop(pg, 'unknByte2', text='')
    row.operator('re6_ctc.copy_node_unknflags', icon='COPYDOWN', text='')
    line('AngleMode', 'copy_node_anglemode')
    line('CollisionShape', 'copy_node_collisionshape')
    line('unknEnum', 'copy_node_unknenum')
    line('BoneColRadius', 'copy_node_bonecolradius')
    line('AngleLimitRadius', 'copy_node_angleradius', text='Angle Radius')
    line('Mass', 'copy_node_mass')
    line('ElasticCoef', 'copy_node_elasticcoef', slider=True)


def draw_collision(layout, obj):
    pg = obj.re6_ccl_collision
    box = layout.box()
    col = box.column()
    _row(col).prop(pg, 'ColRadius')
    if obj.get(C.TYPE) == C.T_CCL_SPHERE:
        _row(col).prop(pg, 'StartColOffset', text='Collision Offset')
    else:
        _row(col).prop(pg, 'StartColOffset')
        _row(col).prop(pg, 'EndColOffset')


# --- the 3D view tab -----------------------------------------------------------------------------------------------------------

class RE6_PT_ctc_tools(bpy.types.Panel):
    bl_label = 'RE6 CTC & CCL Tools'
    bl_idname = 'RE6_PT_ctc_tools'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = TAB

    @classmethod
    def poll(cls, context):
        return context is not None

    def draw(self, context):
        tp = context.scene.re6_ctc_toolpanel
        layout = self.layout
        box1 = layout.box()
        box2 = layout.box()
        col1 = box1.column(align=True)
        col2 = box2.column(align=True)

        row = col1.row(align=False)
        row.scale_y = 1.1
        row.operator('re6_ctc.import_re6_ctc', text='Import CTC')
        row.operator('re6_ctc.export_re6_ctc', text='Export CTC')
        col1.separator()
        row = col1.row(align=False)
        row.scale_y = 1.1
        row.operator('re6_ccl.import_re6_ccl', text='Import CCL')
        row.operator('re6_ccl.export_re6_ccl', text='Export CCL')

        row = col2.row(align=True)
        row.label(text='Active CTC Collection')
        col2.separator()
        row = col2.row(align=True)
        row.scale_y = 1.2
        row.prop(tp, 'ctcCollection', icon='COLLECTION_COLOR_02')

        if context.mode != 'POSE':
            col2.separator()
            _row(col2).operator('re6_ctc.create_ctc_collection')
            col2.separator()
            _row(col2).operator('re6_ctc.align_frames', text='Align Angle Direction')
            col2.separator()
            _row(col2).operator('re6_ctc.apply_angle_limit_ramp', text='Apply Angle Ramp')
            col2.separator()
            col2.separator()
            col2.separator()
            col2.row(align=True).label(text='Create new chains in Pose Mode.')
            col2.separator()
            _row(col2).operator('re6_ctc.switch_to_pose_mode')
        else:
            col2.separator()
            row = col2.row(align=False)
            row.scale_y = 1.1
            row.operator('re6_ctc.create_chain_from_bone')
            row.operator('re6_ccl.create_collision_from_bone')
            col2.separator()
            split = col2.row(align=True)
            row = split.row(align=True)
            row.scale_y = 1.1
            row.operator('re6_ctc.rename_chain_bones')
            row = split.row(align=True)
            row.scale_y = 1.1
            row.alignment = 'RIGHT'
            row.operator('re6_ctc.rename_bone_settings', text='', icon='SETTINGS')
            col2.separator()
            col2.separator()
            col2.separator()
            col2.row(align=True).label(text='Configure chains in Object Mode.')
            col2.separator()
            _row(col2).operator('re6_ctc.switch_to_object_mode')


class RE6_PT_ctc_clipboard(bpy.types.Panel):
    bl_label = 'Clipboard'
    bl_idname = 'RE6_PT_ctc_clipboard'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = TAB

    @classmethod
    def poll(cls, context):
        return context is not None

    def draw(self, context):
        cb = context.scene.re6_ctc_clipboard
        box = self.layout.box()
        col = box.column(align=True)
        row = col.row(align=False)
        row.scale_y = 1.1
        row.operator('re6_ctc.copy_ctc_properties', icon='COPYDOWN')
        row.operator('re6_ctc.paste_ctc_properties', icon='PASTEDOWN')
        col.separator()
        text = '%s %s' % (iface('Content:'), iface(cb.ctc_type_name))
        if cb.node_prop_name:
            text += ' - ' + iface(cb.node_prop_name)
        col.row(align=True).label(text=text)


class RE6_PT_ctc_presets(bpy.types.Panel):
    bl_label = 'Presets'
    bl_idname = 'RE6_PT_ctc_presets'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = TAB

    @classmethod
    def poll(cls, context):
        return context is not None

    def draw(self, context):
        tp = context.scene.re6_ctc_toolpanel
        box = self.layout.box()
        col = box.column(align=True)
        row = col.row(align=True)
        row.scale_y = 1.2
        row.prop(tp, 'CTCChainPresets')
        col.separator()
        _row(col).operator('re6_ctc.apply_ctc_chain_preset', text='Apply Chain Preset')
        col.separator()
        row = col.row(align=False)
        row.scale_y = 1.1
        row.operator('re6_ctc.save_selected_as_preset', text='Save Preset')
        row.operator('re6_ctc.open_preset_folder')


class RE6_PT_ctc_visibility(bpy.types.Panel):
    bl_label = 'Visibility'
    bl_idname = 'RE6_PT_ctc_visibility'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = TAB

    @classmethod
    def poll(cls, context):
        return context is not None

    def draw(self, context):
        box = self.layout.box()
        col = box.column(align=True)
        row = col.row(align=False)
        row.scale_y = 1.1
        row.operator('re6_ctc.only_show_chains', text='Only Chains')
        row.operator('re6_ccl.only_show_collisions', text='Only Collisions')
        col.separator()
        row = col.row(align=False)
        row.scale_y = 1.1
        row.operator('re6_ctc.only_show_nodes', text='Only Nodes')
        row.operator('re6_ctc.only_show_angle_limits', text='Only Angles')
        col.separator()
        _row(col).operator('re6_ctc.show_all_objects')


def _sub(label, ident, draw_fn):
    def draw(self, context):
        draw_fn(self.layout, context.scene.re6_ctc_toolpanel, context.scene.re6_ccl_toolpanel)
    return type(ident, (bpy.types.Panel,), dict(
        bl_label=label, bl_idname=ident, bl_parent_id='RE6_PT_ctc_visibility', bl_space_type='VIEW_3D', bl_region_type='UI',
        bl_category=TAB, bl_options={'DEFAULT_CLOSED'}, draw=draw))


def _draw_display(layout, tp, ccl):
    col = layout.box().column(align=True)
    items = ((tp, 'showRelationLines'), (tp, 'showAngleLimitCones'), (tp, 'hideLastNodeAngleLimit'), None, None,
             (tp, 'showNodeNames'), (ccl, 'showCollisionNames'), None, None, (tp, 'drawChainsThroughObjects'),
             (tp, 'drawNodesThroughObjects'), (tp, 'drawConesThroughObjects'), (ccl, 'drawCollisionsThroughObjects'))
    for item in items:
        if item is None:
            col.separator()
        else:
            _row(col).prop(item[0], item[1])


def _draw_size(layout, tp, ccl):
    col = layout.box().column(align=True)
    _row(col).prop(tp, 'chainDisplaySize')
    col.separator()
    _row(col).prop(tp, 'angleLimitDisplaySize')
    col.separator()
    _row(col).prop(tp, 'coneDisplaySize')


def _draw_color(layout, tp, ccl):
    col = layout.box().column(align=True)
    _row(col).prop(tp, 'chainColor')
    col.separator()
    _row(col).prop(tp, 'coneColor')
    col.separator()
    _row(col).prop(ccl, 'collisionColor')


RE6_PT_ctc_display = _sub('Display Settings', 'RE6_PT_ctc_display', _draw_display)
RE6_PT_ctc_size = _sub('Size Settings', 'RE6_PT_ctc_size', _draw_size)
RE6_PT_ctc_color = _sub('Color Settings', 'RE6_PT_ctc_color', _draw_color)

DRAWERS = {C.T_CTC_HEADER: ('Header Properties', draw_header), C.T_CTC_CHAIN: ('Chain Properties', draw_chain),
           C.T_CTC_NODE: ('Node Properties', draw_node), C.T_CCL_SPHERE: ('Collision Properties', draw_collision),
           C.T_CCL_CAPSULE: ('Collision Properties', draw_collision)}


class RE6_PT_ctc_properties(bpy.types.Panel):
    bl_label = 'Properties'
    bl_idname = 'RE6_PT_ctc_properties'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = TAB

    @classmethod
    def poll(cls, context):
        p = prefs.get()
        o = context.active_object
        return p is not None and p.showCTCProperties and o is not None and o.get(C.TYPE) in DRAWERS

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        obj = context.active_object
        layout.label(text=obj.name)
        title, fn = DRAWERS[obj.get(C.TYPE)]
        layout.row().label(text=title)
        fn(layout, obj)


# --- the data tab of the properties editor ---------------------------------------------------------------------------------

def _data_panel(ident, label, types, draw_fn, parent=None, curve=False):
    attrs = dict(bl_label=label, bl_idname=ident, bl_space_type='PROPERTIES', bl_region_type='WINDOW', bl_context='data')
    if parent:
        attrs['bl_parent_id'] = parent

    def poll(cls, context):
        o = context.active_object
        return o is not None and o.get(C.TYPE) in types and (not curve or o.type == 'CURVE')

    def draw(self, context):
        self.layout.use_property_split = True
        self.layout.use_property_decorate = False
        draw_fn(self.layout, context.active_object)
    attrs['poll'] = classmethod(poll)
    attrs['draw'] = draw
    return type(ident, (bpy.types.Panel,), attrs)


RE6_PT_ctc_header_properties = _data_panel('RE6_PT_ctc_header_properties', 'CTC Header Properties', (C.T_CTC_HEADER,), draw_header)
RE6_PT_ctc_chain_properties = _data_panel('RE6_PT_ctc_chain_properties', 'CTC Chain Properties', (C.T_CTC_CHAIN,), draw_chain,
                                          parent='DATA_PT_shape_curve', curve=True)
RE6_PT_ctc_node_properties = _data_panel('RE6_PT_ctc_node_properties', 'CTC Node Properties', (C.T_CTC_NODE,), draw_node)
RE6_PT_ccl_col_properties = _data_panel('RE6_PT_ccl_col_properties', 'CCL Collision Properties',
                                        (C.T_CCL_SPHERE, C.T_CCL_CAPSULE), draw_collision, parent='DATA_PT_shape_curve',
                                        curve=True)

CLASSES = (RE6_PT_ctc_tools, RE6_PT_ctc_clipboard, RE6_PT_ctc_presets, RE6_PT_ctc_visibility, RE6_PT_ctc_display,
           RE6_PT_ctc_size, RE6_PT_ctc_color, RE6_PT_ctc_properties, RE6_PT_ctc_header_properties,
           RE6_PT_ctc_chain_properties, RE6_PT_ctc_node_properties, RE6_PT_ccl_col_properties)


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
