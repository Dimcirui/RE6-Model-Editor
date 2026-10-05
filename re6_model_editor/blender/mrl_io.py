# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 Dimcirui

"""Writing the material library (.mrl) from an MRL collection."""
import os

import bpy
from bpy.props import BoolProperty, StringProperty
from bpy_extras.io_utils import ExportHelper
from bpy.types import Operator

from ..core import mrl as R
from . import common as C
from . import materials as MT
from . import mrl_objects as MO
from . import prefs
from .export_errors import ExportErrors, add_error, print_errors, show_error_window
from .i18n import rpt


def check_mrl_errors(objs):
    """checkMrl3Error(): the error dict of the material objects of an MRL collection (empty when it can be exported)"""
    errors = {}
    if not objs:
        add_error(errors, 'NoMrlMaterials')
    by_hash = {}
    for o in objs:
        try:
            h = int(o.re6_mrl_material.hash, 16)
        except ValueError:
            continue
        by_hash.setdefault(h, []).append(o.name)
    for names in by_hash.values():
        if len(names) > 1:
            for n in names:
                add_error(errors, 'MultipleSameMaterials', objectName=n)
    return errors


def export_mrl(filepath, mrl_col, report=None):
    """write the entries of an MRL collection as they are (missing materials are added beforehand with Material List >
    Add Missing Materials). Raises ExportErrors"""
    objs = MO.entries(mrl_col)
    errors = check_mrl_errors(objs)
    if errors:
        raise ExportErrors(errors)
    entries = []
    for o in objs:
        try:
            core, binds = MT.core_material(o)
        except (ValueError, KeyError) as e:
            print('RE6 export: %s: %s' % (o.name, e))
            add_error(errors, 'UnwritableMaterial', objectName=o.name)
            continue
        entries.append((core, binds))
    if errors:
        raise ExportErrors(errors)
    mrl = R.assemble(entries, unk=int(mrl_col.get(MO.K_UNK, R.DEFAULT_UNK)))
    try:
        blob = R.serialize(mrl)
        with open(filepath, 'wb') as fh:
            fh.write(blob)
        from . import material_names
        material_names.remember(o.get(C.K_NAME, '') for o in objs)
    except (R.MrlError, OSError) as e:
        print('RE6 export: %s' % e)
        add_error(errors, 'MrlWriteFailed')
        raise ExportErrors(errors)
    if report:
        report({'INFO'}, rpt('RE6: wrote %d materials, %d textures -> %s') % (len(mrl.materials), len(mrl.textures), filepath))
    return len(mrl.materials), len(mrl.textures)


class RE6_OT_export_mrl(Operator, ExportHelper):
    """Export RE6 MRL file"""
    bl_idname = 're6_mrl.export_re6_mrl'
    bl_label = 'Export RE6 MRL'
    bl_description = 'Export RE6 MRL File'
    bl_options = {'PRESET'}

    filename_ext = '.mrl'
    filter_glob: StringProperty(default='*.mrl', options={'HIDDEN'})
    export_textures: BoolProperty(name='Also Export New / Edited Textures', default=False,
                                  description='Write the textures that are new or were edited as .tex files below the '
                                              'game folder of the .mrl (or next to it)')
    flip_green: BoolProperty(name='Flip Green', default=False,
                             description='Regular (OpenGL) normal maps to the DirectX convention of the game')

    def invoke(self, context, event):
        tp = context.scene.re6_mrl_toolpanel

        # the mrl collection of the last export, else the active one, else the one of the last import
        col = None
        last = tp.lastExportCollection
        if last in bpy.data.collections:
            col = bpy.data.collections[last]
        elif tp.mrlCollection:
            col = tp.mrlCollection
        elif tp.lastImportCollection in bpy.data.collections:
            col = bpy.data.collections[tp.lastImportCollection]
        else:
            col = MO.find_mrl_collection(context)

        tp.exportMrlCollection = col
        if col and '.mrl' in col.name:
            self.filepath = col.name.split('.mrl')[0] + '.mrl'
            src = col.get(MO.K_SRC, '')
            if src.lower().endswith('.mrl') and os.path.splitext(os.path.basename(src))[0].startswith(col.name.split('.mrl')[0]):
                self.filepath = os.path.basename(src)              # an imported "pl0603_1.mrl" is saved as such

        if not os.path.dirname(self.filepath):
            p = prefs.get()
            if p and p.last_export_dir_mrl and os.path.isdir(p.last_export_dir_mrl):
                self.filepath = os.path.join(p.last_export_dir_mrl, self.filepath)

        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def draw(self, context):
        tp = context.scene.re6_mrl_toolpanel

        layout = self.layout
        box = layout.box()
        col = box.column(align=True)

        row = col.row(align=True)
        row.label(text='Mrl Collection:')
        col.separator()

        row = col.row(align=True)
        row.scale_y = 1.2
        row.prop(tp, 'exportMrlCollection', icon='COLLECTION_COLOR_05')
        if not tp.exportMrlCollection:
            col.separator()
            row = col.row(align=True)
            row.alert = True
            row.label(icon='ERROR', text='Must select a mrl collection first !!!')
        col.separator()
        for n in ('export_textures', 'flip_green'):
            row = col.row(align=True)
            row.scale_y = 1.1
            row.prop(self, n)

    def execute(self, context):
        from .operators import print_banner
        tp = context.scene.re6_mrl_toolpanel
        col = tp.exportMrlCollection

        print_banner()
        prefs.toggle_console()

        success = False
        if col is None:
            errors = {}
            add_error(errors, 'NoTargetMrlCollection')
            print_errors(errors, 'mrl')
            show_error_window(errors, 'mrl')
        else:
            try:
                export_mrl(self.filepath, col, self.report)
                if self.export_textures:
                    from .tex_tools import export_model_textures
                    root = _game_root(self.filepath)
                    files = export_model_textures(col, root, self.flip_green, self.report)
                    self.report({'INFO'}, rpt('RE6: %d texture(s) written below %s') % (len(files), root))
                success = True
            except ExportErrors as e:
                print_errors(e.errors, 'mrl')
                show_error_window(e.errors, 'mrl', col.name)
            except (OSError, ValueError):
                import traceback
                traceback.print_exc()

        if success:
            tp.lastExportCollection = col.name
            self.report({'INFO'}, rpt('Successfully exported RE6 MRL file.'))
            if tp.modDirectory == '':
                C.set_mod_directory(self.filepath)
            p = prefs.get()
            if p:
                p.last_export_dir_mrl = os.path.dirname(self.filepath)
        else:
            self.report({'INFO'}, rpt('Failed to export RE6 MRL file. Check Window > Toggle System Console for details.'))

        prefs.toggle_console()
        return {'FINISHED'} if success else {'CANCELLED'}


def _game_root(mrl_path):
    """folder that holds the data/ folder when the .mrl lies below one, else the folder of the .mrl; textures are written to
    <folder>/<game path>.tex"""
    split = C.split_game_path(os.path.dirname(os.path.abspath(mrl_path)))
    return split[0] if split else os.path.dirname(os.path.abspath(mrl_path))


CLASSES = (RE6_OT_export_mrl,)


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
