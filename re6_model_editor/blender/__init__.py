# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 Dimcirui

import bpy

from . import (ccl_io, ccl_operators, ccl_properties, ctc_io, ctc_operators, ctc_panels, ctc_presets, ctc_properties,
               export_errors, i18n, mesh_tools, mrl_clipboard, mrl_features, mrl_io, mrl_objects, mrl_presets, operators,
               material_names, panels, prefs, props, tex_tools, vertex_formats)


class IMPORT_MT_re6_model_editor(bpy.types.Menu):
    bl_label = 'RE6 Model Editor'
    bl_idname = 'IMPORT_MT_re6_model_editor'

    def draw(self, context):
        layout = self.layout
        layout.operator(operators.RE6_OT_import_mod.bl_idname, text='RE6 MOD (.mod) (Model)', icon='MESH_DATA')
        layout.operator(mrl_objects.RE6_OT_import_mrl.bl_idname, text='RE6 MRL (.mrl) (Material)', icon='MATERIAL')
        layout.operator(ctc_io.RE6_OT_import_ctc.bl_idname, text='RE6 CTC (.ctc) (Physic)', icon='LINK_BLEND')
        layout.operator(ccl_io.RE6_OT_import_ccl.bl_idname, text='RE6 CCL (.ccl) (Collision)', icon='SPHERE')


def re6_model_editor_import(self, context):
    self.layout.menu('IMPORT_MT_re6_model_editor', icon='MOD_LINEART')


class EXPORT_MT_re6_model_editor(bpy.types.Menu):
    bl_label = 'RE6 Model Editor'
    bl_idname = 'EXPORT_MT_re6_model_editor'

    def draw(self, context):
        layout = self.layout
        layout.operator(operators.RE6_OT_export_mod.bl_idname, text='RE6 MOD (.mod) (Model)', icon='MESH_DATA')
        layout.operator(mrl_io.RE6_OT_export_mrl.bl_idname, text='RE6 MRL (.mrl) (Material)', icon='MATERIAL')
        layout.operator(ctc_io.RE6_OT_export_ctc.bl_idname, text='RE6 CTC (.ctc) (Physic)', icon='LINK_BLEND')
        layout.operator(ccl_io.RE6_OT_export_ccl.bl_idname, text='RE6 CCL (.ccl) (Collision)', icon='SPHERE')


def re6_model_editor_export(self, context):
    self.layout.menu('EXPORT_MT_re6_model_editor', icon='MOD_LINEART')


def register_all():
    i18n.register()
    prefs.register()
    export_errors.register()
    props.register()
    ccl_properties.register()           # first: the ctc clipboard holds a ccl collision group
    ctc_properties.register()
    operators.register()
    mesh_tools.register()
    material_names.register()
    vertex_formats.register()
    mrl_objects.register()
    mrl_features.register()
    mrl_clipboard.register()
    mrl_presets.register()
    mrl_io.register()
    ctc_io.register()
    ccl_io.register()
    ctc_operators.register()
    ccl_operators.register()
    ctc_presets.register()
    tex_tools.register()
    panels.register()
    ctc_panels.register()
    bpy.utils.register_class(IMPORT_MT_re6_model_editor)
    bpy.utils.register_class(EXPORT_MT_re6_model_editor)
    bpy.types.TOPBAR_MT_file_import.append(re6_model_editor_import)
    bpy.types.TOPBAR_MT_file_export.append(re6_model_editor_export)
    print('RE6 Model Editor addon is installed.')


def unregister_all():
    bpy.types.TOPBAR_MT_file_export.remove(re6_model_editor_export)
    bpy.types.TOPBAR_MT_file_import.remove(re6_model_editor_import)
    bpy.utils.unregister_class(EXPORT_MT_re6_model_editor)
    bpy.utils.unregister_class(IMPORT_MT_re6_model_editor)
    ctc_panels.unregister()
    panels.unregister()
    tex_tools.unregister()
    ctc_presets.unregister()
    ccl_operators.unregister()
    ctc_operators.unregister()
    ccl_io.unregister()
    ctc_io.unregister()
    mrl_io.unregister()
    mrl_presets.unregister()
    mrl_clipboard.unregister()
    mrl_features.unregister()
    mrl_objects.unregister()
    vertex_formats.unregister()
    material_names.unregister()
    mesh_tools.unregister()
    operators.unregister()
    ctc_properties.unregister()
    ccl_properties.unregister()
    props.unregister()
    export_errors.unregister()
    prefs.unregister()
    i18n.unregister()
    print('RE6 Model Editor addon is uninstalled.')
