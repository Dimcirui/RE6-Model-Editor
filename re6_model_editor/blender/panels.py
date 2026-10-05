# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 Dimcirui

import bpy

from . import common as C
from . import mrl_clipboard as MC
from . import mrl_features as MF
from . import mrl_objects as MO
from .operators import RE6_OT_assign_texture
from ..core import cb_layouts as CL
from ..core import hashes as H
from ..core import mrl as R
from ..core import shader_names as SN
from .i18n import iface


def draw_entry(lay, obj):
    """the header of one .mrl material (an empty of an MRL collection): the black box of the material panel"""
    p = obj.re6_mrl_material
    lay.use_property_split = True
    lay.use_property_decorate = False
    box = lay.box()
    col = box.column()
    try:
        kind = R.MATERIAL_TYPES.get(int(p.shader, 16), '') or p.shader
    except ValueError:
        kind = p.shader
    row = col.row(align=True)
    row.label(text='%s %s' % (iface('Shader Type:'), kind))
    row = col.row(align=True)
    row.scale_y = 1.1
    row.prop(p, 'materialName')


def draw_flags(lay, obj):
    """blend / depth / culling states and the flag words of the material"""
    p = obj.re6_mrl_material
    col = _indented(lay)
    col.use_property_split = True
    col.use_property_decorate = False
    col.prop(p, 'blend_mode')
    col.prop(p, 'depth_mode')
    col.prop(p, 'raster_mode')
    col.separator()
    col.prop(p, 'alphatest')
    sub = col.column()
    sub.active = p.alphatest
    sub.prop(p, 'alphatest_ref')
    sub.prop(p, 'alphatest_func')
    col.prop(p, 'draw_pass')
    col.separator()
    for n in ('deferred', 'half_lambert', 'fog', 'tangent'):
        col.prop(p, n)
    col.separator()
    for n in ('layer', 'stencil_ref', 'polygon_offset', 'mat_id', 'unk_bits'):
        col.prop(p, n)


def _indented(lay):
    split = lay.split(factor=0.025)          # indent the lists so that they read as part of a sub panel
    split.column()
    return split.column()


def draw_map_list(lay, obj):
    p = obj.re6_mrl_material
    col = _indented(lay)
    row = col.row(align=True)
    row.scale_y = 1.1
    row.operator('re6_mrl.replace_string')
    row = col.row(align=True)
    for role, text in (('albedo', 'Base'), ('normal', 'Normal'), ('mask', 'Mask')):
        row.operator(RE6_OT_assign_texture.bl_idname, text=text).role = role
    col.operator('re6_mrl.refresh_preview', icon='FILE_REFRESH')
    col.template_list('MESH_UL_MrlMapList', '', p, 'mapList_items', p, 'mapList_index',
                      rows=min(6, len(p.mapList_items)), type='DEFAULT')


def draw_sampler_list(lay, obj):
    p = obj.re6_mrl_material
    col = _indented(lay)
    col.label(text='%s %d' % (iface('Sampler Count:'), len(p.samplerList_items)))
    col.template_list('MESH_UL_MrlSamplerList', '', p, 'samplerList_items', p, 'samplerList_index',
                      rows=min(6, len(p.samplerList_items)), type='DEFAULT')


def draw_property_list(lay, obj):
    p = obj.re6_mrl_material
    for index, blk in enumerate(p.propertyBlock_items):
        n = len(blk.propertyList_items)
        if not n:
            continue
        col2 = _indented(lay)
        col2.label(text='%s    %s %d' % (blk.blockName, iface('Property Count:'), n))
        col2.template_list('MESH_UL_MrlPropertyList', 'propertyBlock_%d' % index, blk, 'propertyList_items', blk,
                           'propertyList_index', rows=min(6, n), type='DEFAULT')


# (key, label, draw function, closed by default, has something to show)
SUBPANELS = (
    ('flags', 'Flags', draw_flags, True, lambda e: True),
    ('features', 'Shader Features', MF.draw_features, False, lambda e: True),
    ('maplist', 'Map List', draw_map_list, False, lambda e: len(e.re6_mrl_material.mapList_items)),
    ('proplist', 'Property List', draw_property_list, False, lambda e: len(e.re6_mrl_material.propertyBlock_items)),
    ('samplerlist', 'Sampler List', draw_sampler_list, True, lambda e: len(e.re6_mrl_material.samplerList_items)),
)


def _sub_funcs(key, fn, has):
    def poll(cls, context):
        e = MO.active_entry(context)
        return e is not None and bool(has(e))

    def draw(self, context):
        fn(self.layout, MO.active_entry(context))

    def draw_header_preset(self, context):          # copy / paste buttons on the right of the header
        MC.draw_header_buttons(self.layout, context, key)
    return classmethod(poll), draw, draw_header_preset


def make_subpanels(parent_id, tag):
    """the Shader Features / Map / Property / Sampler List sub panels of a material panel (one set per parent panel)"""
    out = []
    for key, label, fn, closed, has in SUBPANELS:
        name = 'RE6_PT_%s_%s' % (tag, key)
        poll, draw, header = _sub_funcs(key, fn, has)
        attrs = dict(bl_label=label, bl_idname=name, bl_parent_id=parent_id, bl_space_type='PROPERTIES',
                     bl_region_type='WINDOW', bl_options={'DEFAULT_CLOSED'} if closed else set(), poll=poll, draw=draw,
                     draw_header_preset=header)
        out.append(type(name, (bpy.types.Panel,), attrs))
    return out


class RE6_PT_material(bpy.types.Panel):
    bl_label = 'RE6 Material'
    bl_idname = 'RE6_PT_material'
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = 'material'

    @classmethod
    def poll(cls, context):
        o = context.object
        return (o is not None and o.type == 'MESH' and o.active_material is not None
                and 'HIDE_RE6_MRL_EDITOR_PANEL' not in context.scene)

    def draw(self, context):
        mat = context.object.active_material
        lay = self.layout
        lay.label(text=iface('Material hash: %s') % (mat.get(C.K_MAT_HASH, '?')), icon='MATERIAL')
        owner = MO.active_entry(context)
        if owner is None:
            lay.label(text='No MRL entry for this material', icon='INFO')
            lay.operator('re6_mrl.add_missing_materials', icon='ADD')
            return
        lay.operator('re6_mrl.select_material', text=owner.name, icon='EMPTY_AXIS').name = owner.name
        draw_entry(lay, owner)


class RE6_PT_mrl_entry(bpy.types.Panel):
    bl_label = 'Mrl Material Properties'
    bl_idname = 'RE6_PT_mrl_entry'
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = 'data'

    @classmethod
    def poll(cls, context):
        o = context.object
        return (MO.is_entry(o) and o.get(C.TYPE) == C.T_MAT and o.mode == 'OBJECT'
                and 'HIDE_RE6_MRL_EDITOR_PANEL' not in context.scene)

    def draw(self, context):
        draw_entry(self.layout, context.object)


TAB = 'RE6 Mesh'


class RE6_PT_mrl_tools(bpy.types.Panel):
    bl_label = 'RE6 Mrl Tools'
    bl_idname = 'RE6_PT_mrl_tools'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = TAB

    def draw(self, context):
        tp = context.scene.re6_mrl_toolpanel
        lay = self.layout
        box1 = lay.box()
        box2 = lay.box()
        col1 = box1.column(align=True)
        col2 = box2.column(align=True)
        row = col1.row(align=False)
        row.scale_y = 1.1
        row.operator('re6_mod.import_re6_mod', text='Import Mod')
        row.operator('re6_mod.export_re6_mod', text='Export Mod')
        col1.separator()
        row = col1.row(align=False)
        row.scale_y = 1.1
        row.operator('re6_mrl.import_re6_mrl', text='Import Mrl')
        row.operator('re6_mrl.export_re6_mrl', text='Export Mrl')

        col2.label(text='Active Mrl Collection')
        col2.separator()
        row = col2.row(align=True)
        row.scale_y = 1.2
        row.prop(tp, 'mrlCollection', icon='COLLECTION_COLOR_05')
        col2.separator()
        row = col2.row(align=True)
        row.scale_y = 1.1
        row.operator('re6_mrl.create_mrl_collection')
        col2.separator()
        row = col2.row(align=True)
        row.scale_y = 1.1
        row.operator('re6_mrl.reindex_mrl_materials')
        col2.separator()
        row = col2.row(align=True)
        row.scale_y = 1.1
        row.operator('re6_mrl.resolve_material_names')
        col2.separator()
        col2.separator()
        col2.separator()
        col2.label(text='Mod Directory')
        col2.separator()
        row = col2.row(align=True)
        row.scale_y = 1.2
        row.prop(tp, 'modDirectory')


class RE6_PT_mrl_list(bpy.types.Panel):
    """the material list of the active mrl collection (RE6 extra, the MHW Model Editor manages them with Blender's own
    object operators)"""
    bl_label = 'Material List'
    bl_idname = 'RE6_PT_mrl_list'
    bl_parent_id = 'RE6_PT_mrl_tools'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = TAB

    def draw(self, context):
        lay = self.layout
        lay.operator('re6_mrl.load_mrl', icon='FILE_REFRESH')
        lay.operator('re6_mrl.add_missing_materials', icon='ADD')
        mrl = MO.find_mrl_collection(context)
        if mrl is None:
            return
        lay.label(text=mrl.name, icon='OUTLINER_COLLECTION')
        row = lay.row(align=True)
        row.operator('re6_mrl.add_material', icon='ADD', text='')
        row.operator('re6_mrl.duplicate_material', icon='DUPLICATE', text='')
        row.operator('re6_mrl.delete_material', icon='REMOVE', text='')
        row.operator('re6_mrl.move_material', icon='TRIA_UP', text='').direction = 'UP'
        row.operator('re6_mrl.move_material', icon='TRIA_DOWN', text='').direction = 'DOWN'
        objs = MO.entries(mrl)
        box = lay.box().column(align=True)
        for o in objs[:60]:
            r = box.row(align=True)
            r.operator('re6_mrl.select_material', text='%02d  %s  %s' % (o.re6_mrl_material.index, o.re6_mrl_material.hash, o.get(C.K_NAME, '')),
                       depress=(o == context.object)).name = o.name
            r.label(text='', icon='MATERIAL' if o.re6_mrl_material.linkedMaterial else 'BLANK1')
        if len(objs) > 60:
            box.label(text='... %d more (see the outliner)' % (len(objs) - 60))


class RE6_PT_mrl_presets(bpy.types.Panel):
    bl_label = 'Presets'
    bl_idname = 'RE6_PT_mrl_presets'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = TAB

    @classmethod
    def poll(cls, context):
        return context is not None

    def draw(self, context):
        tp = context.scene.re6_mrl_toolpanel
        layout = self.layout
        box = layout.box()
        col = box.column(align=True)

        row = col.row(align=True)
        row.scale_y = 1.2
        row.prop(tp, 'MrlMaterialPresets')

        col.separator()
        row = col.row(align=True)
        row.scale_y = 1.1
        row.operator('re6_mrl.add_preset_material')

        col.separator()
        row = col.row(align=False)
        row.scale_y = 1.1
        row.operator('re6_mrl.save_selected_as_preset', text='Save Preset')
        row.operator('re6_mrl.open_preset_folder')


class RE6_PT_mesh_tools(bpy.types.Panel):
    bl_label = 'RE6 Mesh Tools'
    bl_idname = 'RE6_PT_mesh_tools'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = TAB

    @classmethod
    def poll(cls, context):
        return context is not None and 'HIDE_RE6_MRL_EDITOR_TAB' not in context.scene

    def draw(self, context):
        lay = self.layout
        box1 = lay.box()
        box2 = lay.box()
        col1 = box1.column(align=True)
        col2 = box2.column(align=True)
        first = True
        for col, ops in ((col1, ('create_mod_collection', 'create_nested_collections', 'rename_meshes', 'set_mesh_group_id',
                                 'match_bone_names')),
                         (col2, ('bake_normal_to_vertex_color', 'delete_loose_geometry', 'remove_empty_vertex_groups',
                                 'limit_total_normalize'))):
            first = True
            for op in ops:
                if not first:
                    col.separator()
                first = False
                row = col.row(align=True)
                row.scale_y = 1.1
                row.operator('re6_mod.' + op)
        from .vertex_formats import draw_panel
        draw_panel(lay, context)


class RE6_PT_tex_tools(bpy.types.Panel):
    bl_label = 'RE6 Tex Tools'
    bl_idname = 'RE6_PT_tex_tools'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = TAB

    @classmethod
    def poll(cls, context):
        return context is not None and 'HIDE_RE6_MRL_EDITOR_TAB' not in context.scene

    def draw(self, context):
        tp = context.scene.re6_mrl_toolpanel
        col = self.layout.box().column(align=True)
        split = col.row(align=True)
        row = split.row(align=True)
        row.scale_y = 1.1
        row.operator('re6_tex.convert_re6_tex_dds_files')
        row = split.row(align=True)
        row.scale_y = 1.1
        row.alignment = 'RIGHT'
        row.operator('re6_tex.convert_settings', text='', icon='SETTINGS')
        col.separator()
        col.separator()
        col.separator()
        col.label(text='Texture Directory')
        col.separator()
        row = col.row(align=True)
        row.scale_y = 1.2
        row.prop(tp, 'textureDirectory')
        col.separator()
        row = col.row(align=False)
        row.scale_y = 1.1
        row.operator('re6_tex.convert_tex_directory')
        row.operator('re6_tex.open_conversion_folder')
        col.separator()
        col.separator()
        col.separator()
        col.label(text='Mod Directory')
        col.separator()
        row = col.row(align=True)
        row.scale_y = 1.2
        row.prop(tp, 'modDirectory')
        col.separator()
        row = col.row(align=True)
        row.scale_y = 1.1
        row.operator('re6_tex.copy_converted_tex')
        col.separator()
        row = col.row(align=True)
        row.scale_y = 1.1
        row.operator('re6_tex.export_model_textures')


CLASSES = (RE6_PT_mrl_tools, RE6_PT_mrl_list, RE6_PT_mrl_presets, RE6_PT_mrl_entry, *make_subpanels('RE6_PT_mrl_entry', 'entry'),
           RE6_PT_material, *make_subpanels('RE6_PT_material', 'mat'), RE6_PT_mesh_tools, RE6_PT_tex_tools)


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
