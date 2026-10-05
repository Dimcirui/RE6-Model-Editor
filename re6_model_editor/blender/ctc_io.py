# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 Dimcirui

"""Importing and exporting .ctc files (ctc_io.py and blender_ctc.py of the MHW Model Editor)."""
import json
import os
import re
import time

import bpy
from bpy.props import BoolProperty, CollectionProperty, StringProperty
from bpy_extras.io_utils import ExportHelper, ImportHelper

from ..core import ctc as K
from . import common as C
from . import ctc_functions as F
from . import ctc_properties as CP
from . import objects as O
from . import prefs
from .export_errors import add_error, print_errors, show_error_window
from .i18n import rpt


def _warn(warnings, text):
    print('\033[93mWARNING: %s\033[0m' % text)
    if warnings is not None:
        warnings.append(text)


def import_ctc(filepath, *, target=None, merge=None, load_ccl=True, warnings=None, nested=False):
    """build the objects of a .ctc file; True when it was imported"""
    name = os.path.basename(filepath)
    prefs.load_ctc_visibility(bpy.context.scene)
    if not nested:
        print('\033[96m__________________________________\nRE6 CTC import started.\033[0m')
    start = time.time()
    try:
        with open(filepath, 'rb') as fh:
            ctc = K.parse(fh.read())
    except (OSError, ValueError) as e:
        _warn(warnings, 'An error occurred while reading %s - %s' % (filepath, e))
        return False
    arm = F.search_armature(name, target)
    if arm is None:
        return False
    ids = C.bones_by_id(arm)
    print('Parsed ctc.\nTarget Armature: %s' % arm.name)
    tp = bpy.context.scene.re6_ctc_toolpanel

    # the chains that can be built: every node needs a bone of the armature, a chain needs two nodes
    chains, empties, missing, dropped = [], [], set(), 0
    for i, chain in enumerate(ctc.chains):
        if not chain.nodes:
            empties.append((i, K.pack_chain(chain).hex()))
            continue
        kept = []
        for node in chain.nodes:
            bn = ids.get(node.boneFunctionId & 0xFF)
            if bn is None:
                missing.add(C.BONE_PREFIX + '%03d' % (node.boneFunctionId & 0xFF))
            else:
                kept.append((bn, node))
        if len(kept) >= 2:
            chains.append((chain, kept))
        else:
            dropped += 1
    if dropped:
        _warn(warnings, rpt('%d chain(s) of %s have fewer than two bones in the armature and were not imported (they are not in an '
                            'exported ctc either).') % (dropped, name))
    print('Mismatched Bones (%d):' % len(missing))
    for b in sorted(missing):
        print('  ' + b)

    # the collection and its header
    merged = False
    col = merge
    header = None
    if merge is not None:
        tp.lastImportCollection = merge.name
        header = F.find_header(merge)
        merged = header is not None
    if header is None:
        parent = None
        mod_col = arm.users_collection[0] if arm.users_collection else None
        if mod_col is not None and C.is_mod(mod_col):
            parent = F.parent_collection_of(mod_col)
        col = O.create_collection(name, 'COLOR_02', C.T_CTC, parent) if col is None else col
        tp.ctcCollection = col
        tp.lastImportCollection = col.name
        header = F.create_header(col, 'CTC_HEADER ' + name, ctc.header)
        if empties:
            header[F.K_EMPTY] = json.dumps(empties)
    entry_col = F.entries_collection('Chain Entries', col, make_new=not merged)

    index = 0
    for chain, kept in chains:
        cname = 'CTC_CHAIN_%02d' % index
        if merged:
            while O.name_in_use(cname):
                index += 1
                cname = 'CTC_CHAIN_%02d' % index
        else:
            index += 1
        bones = [b for b, _n in kept]
        frames = [([n.nodeMatrix[0:3], n.nodeMatrix[4:7], n.nodeMatrix[8:11]], n.nodeMatrix[12:15], n.boneFunctionId >> 8)
                  for _b, n in kept]
        F.make_chain(tp, header, entry_col, arm, '%s - %s > %s' % (cname, bones[0], bones[-1]), chain,
                     [n for _b, n in kept], bones, frames)
    F.align_chains(col)
    F.set_chain_bone_color(arm, col)
    print('CTC imported in %d ms.\n\nCTC Info:\nChain Count: %d\nMatched Chain Count: %d / %d' % (
        (time.time() - start) * 1000, len(ctc.chains), len(chains), len(ctc.chains)))
    if load_ccl:
        ccl_path = re.sub(r'\.ctc$', '.ccl', filepath, flags=re.I)
        if os.path.isfile(ccl_path):
            from . import ccl_io
            ccl_io.import_ccl(ccl_path, target=arm, warnings=warnings, nested=True, collection=col)
        else:
            _warn(warnings, 'An error occurred while reading %s - File is not found.' % ccl_path)
    if not nested:
        print('\033[92m__________________________________\nRE6 CTC import finished.\033[0m')
    return True


def export_ctc(filepath, col, export_ccl=True):
    """write a ctc collection; True when it was written"""
    print('\033[96m__________________________________\nRE6 CTC export started.\033[0m')
    start = time.time()
    errors = {}
    if col is None:
        add_error(errors, 'NoTargetCTCCollection')
        print_errors(errors, 'ctc')
        show_error_window(errors, 'ctc', 'None')
        return False
    bpy.context.scene.re6_ctc_toolpanel.lastExportCollection = col.name
    ctc = F.read_ctc(col, errors)
    if errors:
        print_errors(errors, 'ctc')
        show_error_window(errors, 'ctc', col.name)
        return False
    with open(filepath, 'wb') as fh:
        fh.write(K.serialize(ctc))
    print('Converting to ctc file finished.\nCTC exported in %d ms.\n\nCTC Info:\nChain Count: %d\nNode Count: %d' % (
        (time.time() - start) * 1000, len(ctc.chains), ctc.node_count))
    if export_ccl:
        from . import ccl_io
        ccl_io.export_ccl(re.sub(r'\.ctc$', '.ccl', filepath, flags=re.I), col, nested=True)
    print('\033[92m__________________________________\nRE6 CTC export finished.\033[0m')
    return True


class RE6_OT_import_ctc(bpy.types.Operator, ImportHelper):
    """Import RE6 CTC files"""
    bl_idname = 're6_ctc.import_re6_ctc'
    bl_label = 'Import RE6 CTC'
    bl_description = ('Import RE6 CTC Files.\nNOTE: Before importing ctc, make sure that at least one mod armature exists in '
                      'the current scene')
    bl_options = {'PRESET', 'REGISTER', 'UNDO'}

    files: CollectionProperty(name='File Path', type=bpy.types.OperatorFileListElement)
    directory: StringProperty(subtype='DIR_PATH', options={'SKIP_SAVE'})
    filename_ext = '.ctc'
    filter_glob: StringProperty(default='*.ctc', options={'HIDDEN'})
    loadCCL: BoolProperty(name='Load CCL Collision', default=True,
                          description='Load physical collision objects from the ccl file')

    def invoke(self, context, event):
        if self.directory:
            p = prefs.get()
            if p is None or p.dragDropImportOptions:
                return context.window_manager.invoke_props_dialog(self)
            return self.execute(context)
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def draw(self, context):
        tp = context.scene.re6_ctc_toolpanel
        layout = self.layout
        box = layout.box()
        col = box.column(align=True)
        row = col.row(align=True)
        row.scale_y = 1.1
        row.prop(self, 'loadCCL')
        row = col.row(align=True)
        row.label(text='Target Armature:')
        col.separator()
        row = col.row(align=True)
        row.scale_y = 1.2
        row.prop(tp, 'importCTCArmature', icon='OUTLINER_OB_ARMATURE')
        col.separator()
        row = col.row(align=True)
        row.label(text='Merge With CTC Collection:')
        col.separator()
        row = col.row(align=True)
        row.scale_y = 1.2
        row.prop(tp, 'importCTCCollection', icon='COLLECTION_COLOR_02')

    def execute(self, context):
        from .operators import print_banner
        tp = context.scene.re6_ctc_toolpanel
        print_banner()
        prefs.toggle_console()
        paths = [os.path.join(self.directory, f.name) for f in self.files] if self.files else [self.filepath]
        multi = len(paths) > 1
        has_errors = False
        warnings = []
        for i, path in enumerate(paths):
            if multi:
                print('Multi CTC Import (%d / %d)' % (i + 1, len(paths)))
            if os.path.isfile(path):
                if not import_ctc(path, target=tp.importCTCArmature, merge=tp.importCTCCollection, load_ccl=self.loadCCL,
                                  warnings=warnings):
                    has_errors = True
            else:
                has_errors = True
                _warn(warnings, 'Path does not exist, cannot import file.\nIf you are importing multiple files at once, they '
                                'must all be in the same directory.\nInvalid Path: %s' % path)
        for w in warnings:
            self.report({'WARNING'}, w)
        if not has_errors:
            prefs.toggle_console()
            self.report({'INFO'}, rpt('Successfully imported RE6 CTC file.') if not multi
                        else rpt('Successfully imported %d RE6 CTC files.') % len(paths))
            return {'FINISHED'}
        self.report({'INFO'}, rpt('Failed to import RE6 CTC file. Check Window > Toggle System Console for details.')
                    if not multi else rpt('Some RE6 CTC files failed to import. Check Window > Toggle System Console for '
                                          'details.'))
        return {'CANCELLED'}


class RE6_OT_export_ctc(bpy.types.Operator, ExportHelper):
    """Export RE6 CTC file"""
    bl_idname = 're6_ctc.export_re6_ctc'
    bl_label = 'Export RE6 CTC'
    bl_description = 'Export RE6 CTC File'
    bl_options = {'PRESET'}

    filename_ext = '.ctc'
    filter_glob: StringProperty(default='*.ctc', options={'HIDDEN'})
    exportCCL: BoolProperty(name='Export CCL Collision', default=True,
                            description='When exporting ctc file, also export collision objects as ccl file')

    def invoke(self, context, event):
        tp = context.scene.re6_ctc_toolpanel
        col = None
        last = tp.lastExportCollection
        if last in bpy.data.collections:
            col = bpy.data.collections[last]
        elif tp.ctcCollection:
            col = tp.ctcCollection
        elif tp.lastImportCollection in bpy.data.collections:
            col = bpy.data.collections[tp.lastImportCollection]
        tp.exportCTCCollection = col
        if col and '.ctc' in col.name:
            self.filepath = col.name.split('.ctc')[0] + '.ctc'
        if not os.path.dirname(self.filepath):
            p = prefs.get()
            if p and p.last_export_dir_ctc and os.path.isdir(p.last_export_dir_ctc):
                self.filepath = os.path.join(p.last_export_dir_ctc, self.filepath)
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def draw(self, context):
        tp = context.scene.re6_ctc_toolpanel
        layout = self.layout
        box = layout.box()
        col = box.column(align=True)
        row = col.row(align=True)
        row.scale_y = 1.1
        row.prop(self, 'exportCCL')
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
        tp = context.scene.re6_ctc_toolpanel
        print_banner()
        prefs.toggle_console()
        success = False
        try:
            success = export_ctc(self.filepath, tp.exportCTCCollection, self.exportCCL)
        except Exception:       # noqa
            import traceback
            traceback.print_exc()
        if success:
            self.report({'INFO'}, rpt('Successfully exported RE6 CTC file.'))
            if context.scene.re6_mrl_toolpanel.modDirectory == '':
                C.set_mod_directory(self.filepath)
            p = prefs.get()
            if p:
                p.last_export_dir_ctc = os.path.dirname(self.filepath)
        else:
            self.report({'INFO'}, rpt('Failed to export RE6 CTC file. Check Window > Toggle System Console for details.'))
        prefs.toggle_console()
        return {'FINISHED'} if success else {'CANCELLED'}


class RE6_CTC_FH_drag_import(bpy.types.FileHandler):
    bl_idname = 'RE6_CTC_FH_drag_import'
    bl_label = 'File handler for RE6 CTC importing'
    bl_import_operator = RE6_OT_import_ctc.bl_idname
    bl_file_extensions = '.ctc'

    @classmethod
    def poll_drop(cls, context):
        return context.area and context.area.type == 'VIEW_3D'


CLASSES = (RE6_OT_import_ctc, RE6_OT_export_ctc, RE6_CTC_FH_drag_import)


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
