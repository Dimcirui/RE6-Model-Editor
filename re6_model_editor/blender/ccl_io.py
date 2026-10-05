# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 Dimcirui

"""Importing and exporting .ccl files (ccl_io.py and blender_ccl.py of the MHW Model Editor)."""
import os
import time

import bpy
from bpy.props import CollectionProperty, StringProperty
from bpy_extras.io_utils import ExportHelper, ImportHelper

from ..core import ccl as K
from . import ccl_functions as F
from . import common as C
from . import ctc_functions as CF
from . import objects as O
from . import prefs
from .export_errors import add_error, print_errors, show_error_window
from .i18n import rpt


def _warn(warnings, text):
    print('\033[93mWARNING: %s\033[0m' % text)
    if warnings is not None:
        warnings.append(text)


def import_ccl(filepath, *, target=None, warnings=None, nested=False, collection=None):
    """build the collision objects of a .ccl file in the active ctc collection; True when it was imported"""
    name = os.path.basename(filepath)
    prefs.load_ctc_visibility(bpy.context.scene)
    if not nested:
        print('\033[96m__________________________________\nRE6 CCL import started.\033[0m')
    start = time.time()
    try:
        with open(filepath, 'rb') as fh:
            ccl = K.parse(fh.read())
    except (OSError, ValueError) as e:
        _warn(warnings, 'An error occurred while reading %s - %s' % (filepath, e))
        return False
    arm = CF.search_armature(name, target)
    if arm is None:
        return False
    ids = C.bones_by_id(arm)
    print('Parsed ccl.\nTarget Armature: %s' % arm.name)
    scene = bpy.context.scene
    tp = scene.re6_ccl_toolpanel
    col = collection or scene.re6_ctc_toolpanel.ctcCollection
    if col is None:
        _warn(warnings, 'No ctc collection to put the collisions into.')
        return False
    tp.lastImportCollection = col.name
    header = CF.find_header(col) or CF.create_header(col, 'CTC_HEADER ' + col.name)
    entry_col = O.get_collection('Collision Entries - %s' % name, col, make_new=nested)
    made, missing, dropped = 0, set(), 0
    for c in ccl.collisions:
        start_bone = ids.get(c.startBoneId)
        end_bone = ids.get(c.endBoneId) if c.shape == 1 else None
        if start_bone is None:
            missing.add(C.BONE_PREFIX + '%03d' % c.startBoneId)
            dropped += 1
            continue
        if c.shape == 1 and end_bone is None:
            missing.add(C.BONE_PREFIX + '%03d' % c.endBoneId)
            dropped += 1
            continue
        if c.shape == 1:
            F.make_capsule(tp, header, entry_col, arm, start_bone, end_bone, c)
        else:
            F.make_sphere(tp, header, entry_col, arm, start_bone, c)
        made += 1
    F.align_collisions(col)
    if dropped:
        _warn(warnings, rpt('%d collision(s) of %s have no bone in the armature and were not imported (they are not in an exported '
                            'ccl either).') % (dropped, name))
    print('Mismatched Bones (%d):' % len(missing))
    for b in sorted(missing):
        print('  ' + b)
    print('CCL imported in %d ms.\n\nCCL Info:\nCollision Count: %d\nMatched Collision Count: %d / %d' % (
        (time.time() - start) * 1000, len(ccl.collisions), made, len(ccl.collisions)))
    if not nested:
        print('\033[92m__________________________________\nRE6 CCL import finished.\033[0m')
    return True


def export_ccl(filepath, col, nested=False):
    """write the collision objects of a ctc collection; True when it was written"""
    if not nested:
        print('\033[96m__________________________________\nRE6 CCL export started.\033[0m')
    start = time.time()
    errors = {}
    if col is None:
        add_error(errors, 'NoTargetCTCCollection')
        print_errors(errors, 'ccl')
        show_error_window(errors, 'ccl', 'None')
        return False
    bpy.context.scene.re6_ccl_toolpanel.lastExportCollection = col.name
    ccl = F.read_ccl(col, errors)
    if errors:
        print_errors(errors, 'ccl')
        show_error_window(errors, 'ccl', col.name)
        return False
    with open(filepath, 'wb') as fh:
        fh.write(K.serialize(ccl))
    print('Converting to ccl file finished.\nCCL exported in %d ms.\n\nCCL Info:\nCollision Count: %d' % (
        (time.time() - start) * 1000, len(ccl.collisions)))
    if not nested:
        print('\033[92m__________________________________\nRE6 CCL export finished.\033[0m')
    return True


class RE6_OT_import_ccl(bpy.types.Operator, ImportHelper):
    """Import RE6 CCL files"""
    bl_idname = 're6_ccl.import_re6_ccl'
    bl_label = 'Import RE6 CCL'
    bl_description = ('Import RE6 CCL Files.\nThe button will only be triggered if active ctc collection exists.\nNOTE: '
                      'Before importing ccl, make sure that at least one mod armature exists in the current scene')
    bl_options = {'PRESET', 'REGISTER', 'UNDO'}

    files: CollectionProperty(name='File Path', type=bpy.types.OperatorFileListElement)
    directory: StringProperty(subtype='DIR_PATH', options={'SKIP_SAVE'})
    filename_ext = '.ccl'
    filter_glob: StringProperty(default='*.ccl', options={'HIDDEN'})

    @classmethod
    def poll(cls, context):
        return context.scene.re6_ctc_toolpanel.ctcCollection is not None

    def invoke(self, context, event):
        if self.directory:
            p = prefs.get()
            if p is None or p.dragDropImportOptions:
                return context.window_manager.invoke_props_dialog(self)
            return self.execute(context)
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def draw(self, context):
        tp = context.scene.re6_ccl_toolpanel
        layout = self.layout
        box = layout.box()
        col = box.column(align=True)
        row = col.row(align=True)
        row.label(text='Target Armature:')
        col.separator()
        row = col.row(align=True)
        row.scale_y = 1.2
        row.prop(tp, 'importCTCArmature', icon='OUTLINER_OB_ARMATURE')
        col.separator()

    def execute(self, context):
        from .operators import print_banner
        tp = context.scene.re6_ccl_toolpanel
        print_banner()
        prefs.toggle_console()
        paths = [os.path.join(self.directory, f.name) for f in self.files] if self.files else [self.filepath]
        multi = len(paths) > 1
        has_errors = False
        warnings = []
        for i, path in enumerate(paths):
            if multi:
                print('Multi CCL Import (%d / %d)' % (i + 1, len(paths)))
            if os.path.isfile(path):
                if not import_ccl(path, target=tp.importCTCArmature, warnings=warnings):
                    has_errors = True
            else:
                has_errors = True
                _warn(warnings, 'Path does not exist, cannot import file.\nIf you are importing multiple files at once, they '
                                'must all be in the same directory.\nInvalid Path: %s' % path)
        for w in warnings:
            self.report({'WARNING'}, w)
        if not has_errors:
            prefs.toggle_console()
            self.report({'INFO'}, rpt('Successfully imported RE6 CCL file.') if not multi
                        else rpt('Successfully imported %d RE6 CCL files.') % len(paths))
            return {'FINISHED'}
        self.report({'INFO'}, rpt('Failed to import RE6 CCL file. Check Window > Toggle System Console for details.')
                    if not multi else rpt('Some RE6 CCL files failed to import. Check Window > Toggle System Console for '
                                          'details.'))
        return {'CANCELLED'}


class RE6_OT_export_ccl(bpy.types.Operator, ExportHelper):
    """Export RE6 CCL file"""
    bl_idname = 're6_ccl.export_re6_ccl'
    bl_label = 'Export RE6 CCL'
    bl_description = 'Export RE6 CCL File'
    bl_options = {'PRESET'}

    filename_ext = '.ccl'
    filter_glob: StringProperty(default='*.ccl', options={'HIDDEN'})

    def invoke(self, context, event):
        tp = context.scene.re6_ccl_toolpanel
        col = None
        last = tp.lastExportCollection
        if last in bpy.data.collections:
            col = bpy.data.collections[last]
        elif context.scene.re6_ctc_toolpanel.ctcCollection:
            col = context.scene.re6_ctc_toolpanel.ctcCollection
        elif tp.lastImportCollection in bpy.data.collections:
            col = bpy.data.collections[tp.lastImportCollection]
        tp.exportCTCCollection = col
        if col and '.ctc' in col.name:
            self.filepath = col.name.split('.ctc')[0] + '.ccl'
        if not os.path.dirname(self.filepath):
            p = prefs.get()
            if p and p.last_export_dir_ccl and os.path.isdir(p.last_export_dir_ccl):
                self.filepath = os.path.join(p.last_export_dir_ccl, self.filepath)
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def draw(self, context):
        tp = context.scene.re6_ccl_toolpanel
        layout = self.layout
        box = layout.box()
        col = box.column(align=True)
        row = col.row(align=True)
        row.label(text='CTC Collection:')
        col.separator()
        row = col.row(align=True)
        row.scale_y = 1.2
        row.prop(tp, 'exportCTCCollection', icon='COLLECTION_COLOR_02')
        if not tp.exportCTCCollection:
            col.separator()
            row = col.row(align=True)
            row.alert = True
            row.label(icon='ERROR', text='Must select a ctc collection first !!!')

    def execute(self, context):
        from .operators import print_banner
        tp = context.scene.re6_ccl_toolpanel
        print_banner()
        prefs.toggle_console()
        success = False
        try:
            success = export_ccl(self.filepath, tp.exportCTCCollection)
        except Exception:       # noqa
            import traceback
            traceback.print_exc()
        if success:
            self.report({'INFO'}, rpt('Successfully exported RE6 CCL file.'))
            if context.scene.re6_mrl_toolpanel.modDirectory == '':
                C.set_mod_directory(self.filepath)
            p = prefs.get()
            if p:
                p.last_export_dir_ccl = os.path.dirname(self.filepath)
        else:
            self.report({'INFO'}, rpt('Failed to export RE6 CCL file. Check Window > Toggle System Console for details.'))
        prefs.toggle_console()
        return {'FINISHED'} if success else {'CANCELLED'}


class RE6_CCL_FH_drag_import(bpy.types.FileHandler):
    bl_idname = 'RE6_CCL_FH_drag_import'
    bl_label = 'File handler for RE6 CCL importing'
    bl_import_operator = RE6_OT_import_ccl.bl_idname
    bl_file_extensions = '.ccl'

    @classmethod
    def poll_drop(cls, context):
        return context.area and context.area.type == 'VIEW_3D'


CLASSES = (RE6_OT_import_ccl, RE6_OT_export_ccl, RE6_CCL_FH_drag_import)


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
