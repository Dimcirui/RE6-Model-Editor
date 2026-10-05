# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 Dimcirui

import os

import bpy
from bpy.props import BoolProperty, CollectionProperty, EnumProperty, FloatProperty, StringProperty
from bpy_extras.io_utils import ExportHelper, ImportHelper

from . import common as C
from . import prefs
from .export_errors import print_errors, show_error_window
from .exporter import ExportError, export_mod
from .importer import import_mod
from .i18n import rpt

VERSION = (0, 3)       # bl_info version of the add-on, printed in the console


def model_of_active_object(context):
    """the model collection that contains the active object, None when it is in none (no guessing)"""
    obj = context.object
    if obj:
        for c in obj.users_collection:
            for cand in C.mod_collections():
                if c == cand or c.name in cand.children_recursive:
                    return cand
    return None


def active_model_collection(context):
    """model collection that contains the active object, else the one of the active MRL collection / the tool panel, else the
    first RE6 model collection"""
    obj = context.object
    if obj:
        for c in obj.users_collection:
            for cand in C.mod_collections():
                if c == cand or c.name in cand.children_recursive:
                    return cand
    tp = context.scene.re6_mrl_toolpanel
    if tp.modCollection is not None and C.is_mod(tp.modCollection):
        return tp.modCollection
    mods = C.mod_collections()
    return mods[0] if mods else None


def print_banner():
    print('\n\033[1mRE6 Model Editor V%d.%d\033[0m' % VERSION)
    print('Blender Version %d.%d.%d' % bpy.app.version)


# Used to circumvent the issue of properties not being able to used as defaults for other properties at startup
def set_mod_import_defaults(self):
    p = prefs.get()
    if p:
        for n in ('clearScene', 'addNestedCollections', 'createCollections', 'importArmatureOnly', 'importAllLODs',
                  'importShadow', 'ArmatureDisplayType', 'BonesDisplaySize', 'loadMrlData', 'loadMaterials',
                  'useBackfaceCulling', 'loadPhysics'):
            setattr(self, n, getattr(p, 'default_' + n))


def set_mod_export_defaults(self):
    p = prefs.get()
    if p:
        for n in ('selectedOnly', 'visibleOnly', 'exportAllLODs', 'useBlenderMaterialName', 'shadowMode', 'allowDuplicateBoneNames'):
            setattr(self, n, getattr(p, 'default_' + n))


class RE6_OT_import_mod(bpy.types.Operator, ImportHelper):
    """Import RE6 MOD files"""
    bl_idname = 're6_mod.import_re6_mod'
    bl_label = 'Import RE6 MOD'
    bl_description = 'Import RE6 MOD Files'
    bl_options = {'PRESET', 'REGISTER', 'UNDO'}

    files: CollectionProperty(name='File Path', type=bpy.types.OperatorFileListElement)
    directory: StringProperty(subtype='DIR_PATH', options={'SKIP_SAVE'})
    filename_ext = '.mod'
    filter_glob: StringProperty(default='*.mod', options={'HIDDEN'})

    clearScene: BoolProperty(name='Clear Scene', default=False,
                             description='Clear all objects before importing the mod file')

    # mod import settings
    addNestedCollections: BoolProperty(
        name='Add Nested Collections', default=True,
        description='Add a general parent collection to place other collections of various imported files.'
                    '\nThis will make the collection structure look clearer.'
                    '\nLeaving this option enabled is highly recommended')
    createCollections: BoolProperty(
        name='Create Collections', default=True,
        description='Create a collection for the mod.\nNote that collections are required for exporting and applying mrl '
                    'changes.\nLeaving this option enabled is recommended')
    importArmatureOnly: BoolProperty(name='Only Import Armature', default=False,
                                     description='Only import the armature of the mod file')
    importAllLODs: BoolProperty(
        name='Import All LODs', default=False,
        description='Import all LOD (level of detail) meshes in mod file.'
                    '\nIf unchecked, only the highest LOD meshes will be imported')
    importShadow: BoolProperty(
        name='Import Shadow Meshes', default=True,
        description='Import the shadow-only copies (render mode 0x1020) into a hidden "Shadow" collection.'
                    '\nThey are exported unchanged')
    ArmatureDisplayType: EnumProperty(name='Armature Display Type', default='OCTAHEDRAL', items=prefs.DISPLAY_ITEMS)
    BonesDisplaySize: FloatProperty(name='', default=4.0, step=100, soft_min=0.0,
                                    description='Set the display size of the bones to be imported')

    # mrl import settings
    loadMrlData: BoolProperty(
        name='Load Material Data', default=False,
        description='Imports the mrl materials as objects inside a collection in the outliner.'
                    '\nYou can make changes to material data by selecting the mrl material objects in the outliner.'
                    '\nUnder the Object Data Properties tab (green axis), there\'s a panel called "Mrl Material Properties".'
                    '\nMake any changes to mrl materials there')
    loadMaterials: BoolProperty(
        name='Load Mesh Materials', default=True,
        description='Load materials from the mrl file. This may increase the time the model takes to import')
    useBackfaceCulling: BoolProperty(
        name='Use Backface Culling', default=False,
        description='Enables backface culling on materials. May improve Blender\'s performance on high poly meshes.'
                    '\nBackface culling will only be enabled on materials without the two sided flag')
    mrlPath: StringProperty(
        name='', default='',
        description='Manually set the path of the mrl file.'
                    '\nThe mrl file is found automatically if this is left blank.'
                    '\nTip: Hold shift and right click the mrl file and click "Copy as path", then paste into this field')
    textureDirectory: StringProperty(
        name='', default='', options={'HIDDEN'},
        description='Extra folder with extracted .tex files (the add-on preferences have a list of folders)')

    loadPhysics: BoolProperty(
        name='Load Chains & Collisions', default=False,
        description='Load physical chain and collision objects from the ctc & ccl file')

    showModOptions: BoolProperty(name='Show Mod Options', default=True)
    showMrlOptions: BoolProperty(name='Show Mrl Options', default=True)
    showCTCCCLOptions: BoolProperty(name='Show CTC & CCL Options', default=True)

    def invoke(self, context, event):
        if not context.scene.re6_mod_toolpanel.importSettingsLoaded:
            set_mod_import_defaults(self)

        if self.directory:                      # dropped into the 3D view
            p = prefs.get()
            if p is None or p.dragDropImportOptions:
                return context.window_manager.invoke_props_dialog(self)
            return self.execute(context)
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def draw(self, context):
        layout = self.layout
        layout.scale_y = 1.1
        layout.prop(self, 'clearScene')

        row = layout.row()
        icon = 'DOWNARROW_HLT' if self.showModOptions else 'RIGHTARROW'
        row.prop(self, 'showModOptions', icon=icon, icon_only=True, emboss=False)
        row.label(text='Mod Options')
        if self.showModOptions:
            box = layout.box()
            col = box.column(align=True)

            row = col.row(align=True)
            row.label(text='Armature Display Type:')
            col.separator()

            row = col.row(align=True)
            row.scale_y = 1.1
            row.prop(self, 'ArmatureDisplayType', text='')
            col.separator()

            row = col.row(align=True)
            row.label(text='Bones Display Size:')
            col.separator()

            row = col.row(align=True)
            row.scale_y = 1.1
            row.prop(self, 'BonesDisplaySize', text='')
            col.separator()

            for n in ('addNestedCollections', 'importAllLODs', 'importShadow', 'importArmatureOnly'):
                row = col.row(align=True)
                row.scale_y = 1.1
                row.prop(self, n)

        row = layout.row()
        icon = 'DOWNARROW_HLT' if self.showMrlOptions else 'RIGHTARROW'
        row.prop(self, 'showMrlOptions', icon=icon, icon_only=True, emboss=False)
        row.label(text='Mrl Options')
        if self.showMrlOptions:
            box = layout.box()
            col = box.column(align=True)

            for n in ('loadMrlData', 'loadMaterials'):
                row = col.row(align=True)
                row.scale_y = 1.1
                row.prop(self, n)

            row = col.row(align=True)
            row.label(text='Manual Mrl Path:')
            col.separator()

            row = col.row(align=True)
            row.scale_y = 1.1
            row.prop(self, 'mrlPath')

        row = layout.row()
        icon = 'DOWNARROW_HLT' if self.showCTCCCLOptions else 'RIGHTARROW'
        row.prop(self, 'showCTCCCLOptions', icon=icon, icon_only=True, emboss=False)
        row.label(text='CTC & CCL Options')
        if self.showCTCCCLOptions:
            box = layout.box()
            col = box.column(align=True)
            row = col.row(align=True)
            row.scale_y = 1.1
            row.prop(self, 'loadPhysics')

    def execute(self, context):
        print_banner()
        context.scene.re6_mod_toolpanel.importSettingsLoaded = True
        prefs.toggle_console()

        paths = [os.path.join(self.directory, f.name) for f in self.files] if self.files else [self.filepath]
        multi = len(paths) > 1
        has_errors = False
        clear = self.clearScene
        for i, path in enumerate(paths):
            if multi:
                print('Multi MOD Import (%d / %d)' % (i + 1, len(paths)))
            if not os.path.isfile(path):
                has_errors = True
                print('\033[93mWARNING: Path does not exist, cannot import file.'
                      '\nIf you are importing multiple files at once, they must all be in the same directory.'
                      '\nInvalid Path: %s\033[0m' % path)
                continue
            try:
                import_mod(path, clearScene=clear, addNestedCollections=self.addNestedCollections,
                           createCollections=self.createCollections, importShadow=self.importShadow,
                           importAllLODs=self.importAllLODs, ArmatureDisplayType=self.ArmatureDisplayType,
                           BonesDisplaySize=self.BonesDisplaySize, loadMaterials=self.loadMaterials,
                           loadMrlData=self.loadMrlData, textureDirectory=self.textureDirectory,
                           mrlPath=self.mrlPath.replace('"', ''), useBackfaceCulling=self.useBackfaceCulling,
                           importArmatureOnly=self.importArmatureOnly, loadPhysics=self.loadPhysics, report=self.report)
                clear = False                   # only before the first file
            except Exception:       # noqa
                has_errors = True
                import traceback
                traceback.print_exc()

        if not has_errors:
            prefs.toggle_console()
            if not multi:
                self.report({'INFO'}, rpt('Successfully imported RE6 MOD file.'))
            else:
                self.report({'INFO'}, rpt('Successfully imported %d RE6 MOD files.') % len(paths))
            return {'FINISHED'}
        if not multi:
            self.report({'INFO'}, rpt('Failed to import RE6 MOD file. Check Window > Toggle System Console for details.'))
        else:
            self.report({'INFO'}, rpt('Some RE6 MOD files failed to import. Check Window > Toggle System Console for details.'))
        return {'CANCELLED'}


class RE6_OT_export_mod(bpy.types.Operator, ExportHelper):
    """Export RE6 MOD file"""
    bl_idname = 're6_mod.export_re6_mod'
    bl_label = 'Export RE6 MOD'
    bl_description = 'Export RE6 MOD File'
    bl_options = {'PRESET'}

    filename_ext = '.mod'
    filter_glob: StringProperty(default='*.mod', options={'HIDDEN'})

    # mod export settings
    selectedOnly: BoolProperty(name='Only Selected Meshes', default=False, description='Only export selected meshes')
    visibleOnly: BoolProperty(name='Only Visible Meshes', default=False, description='Only export visible meshes')
    allowDuplicateBoneNames: BoolProperty(
        name='Allow Duplicate Bone Names', default=False,
        description='Accept bones named like "RE6Bone_050.001" (what Blender makes of a second bone with the same id) and write '
                    'the id before the ".001". Several bones then share one function id; a few retail models (props, some '
                    'enemies) have that')
    exportAllLODs: BoolProperty(
        name='Export All LODs', default=True,
        description='Export all LOD meshes. If unchecked, only the highest LOD meshes will be exported.'
                    '\nNOTE: LOD meshes must be grouped inside a collection for each level, and that collection must be '
                    'contained in mod collection.'
                    '\nImport a mod file with "Import All LODs" option to see how it looks')
    useBlenderMaterialName: BoolProperty(
        name='Use Blender Material Names', default=False,
        description='If left unchecked, the exporter will get the material names to be used from the end of each object name.'
                    '\nFor example, if a mesh is named Group_0_Sub_0__Shirts_Mat, the material name is Shirts_Mat.'
                    '\nIf this option is enabled, the material name will instead be taken from the first material '
                    'assigned to the object')
    shadowMode: EnumProperty(name='Shadow Meshes', default='KEEP', items=prefs.SHADOW_ITEMS)

    def invoke(self, context, event):
        scene = context.scene
        mod_tp = scene.re6_mod_toolpanel

        if not mod_tp.exportSettingsLoaded:
            set_mod_export_defaults(self)

        # the mod collection of the last export, else the active one, else the one of the last import
        col = None
        last = mod_tp.lastExportCollection
        if last in bpy.data.collections:
            col = bpy.data.collections[last]
        elif scene.re6_mrl_toolpanel.modCollection:
            col = scene.re6_mrl_toolpanel.modCollection
        elif mod_tp.lastImportCollection in bpy.data.collections:
            col = bpy.data.collections[mod_tp.lastImportCollection]
        else:
            col = active_model_collection(context)

        mod_tp.exportModCollection = col
        if col and '.mod' in col.name:
            self.filepath = col.name.split('.mod')[0] + '.mod'

        if not os.path.dirname(self.filepath):
            p = prefs.get()
            if p and p.last_export_dir_mod and os.path.isdir(p.last_export_dir_mod):
                self.filepath = os.path.join(p.last_export_dir_mod, self.filepath)

        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def draw(self, context):
        layout = self.layout
        mod_tp = context.scene.re6_mod_toolpanel

        box = layout.box()
        col = box.column(align=True)

        row = col.row(align=True)
        row.label(text='Mod Collection:')
        col.separator()

        row = col.row(align=True)
        row.scale_y = 1.2
        row.prop(mod_tp, 'exportModCollection', icon='COLLECTION_COLOR_01')
        if not mod_tp.exportModCollection:
            col.separator()
            row = col.row(align=True)
            row.alert = True
            row.label(icon='ERROR', text='Must select a mod collection first !!!')
        col.separator()

        for n in ('selectedOnly', 'visibleOnly', 'shadowMode', 'useBlenderMaterialName', 'allowDuplicateBoneNames'):
            row = col.row(align=True)
            row.scale_y = 1.1
            row.prop(self, n)

    def execute(self, context):
        scene = context.scene
        mod_tp = scene.re6_mod_toolpanel
        col = mod_tp.exportModCollection

        print_banner()
        mod_tp.exportSettingsLoaded = True
        prefs.toggle_console()

        success = False
        try:
            export_mod(self.filepath, col, selectedOnly=self.selectedOnly, visibleOnly=self.visibleOnly,
                       shadowMode=self.shadowMode, exportAllLODs=self.exportAllLODs,
                       useBlenderMaterialName=self.useBlenderMaterialName,
                       allowDuplicateBoneNames=self.allowDuplicateBoneNames, report=self.report)
            success = True
        except ExportError as e:
            print_errors(e.errors, 'mod')
            show_error_window(e.errors, 'mod', col.name if col else '')
        except Exception:       # noqa
            import traceback
            traceback.print_exc()

        if success:
            mod_tp.lastExportCollection = col.name
            self.report({'INFO'}, rpt('Successfully exported RE6 MOD file.'))
            if scene.re6_mrl_toolpanel.modDirectory == '':
                C.set_mod_directory(self.filepath)
            p = prefs.get()
            if p:
                p.last_export_dir_mod = os.path.dirname(self.filepath)
        else:
            self.report({'INFO'}, rpt('Failed to export RE6 MOD file. Check Window > Toggle System Console for details.'))

        prefs.toggle_console()
        return {'FINISHED'} if success else {'CANCELLED'}


class RE6_OT_load_mrl(bpy.types.Operator, ImportHelper):
    """Replace the material library of the active RE6 model by another .mrl (for example a costume variant)"""
    bl_idname = 're6_mrl.load_mrl'
    bl_label = 'Load MRL'
    bl_options = {'REGISTER', 'UNDO'}

    filename_ext = '.mrl'
    filter_glob: StringProperty(default='*.mrl', options={'HIDDEN'})
    texture_dir: StringProperty(name='Texture Folder', default='',
                                description='Extra folder with extracted .tex files (paste the path; a file browser cannot '
                                            'be opened from inside this dialog, the add-on preferences have a browse button)')

    @classmethod
    def poll(cls, context):
        return active_model_collection(context) is not None

    def execute(self, context):
        from . import mrl_objects as MO
        from .importer import load_materials
        col = active_model_collection(context)
        try:
            load_materials(col, col.get(C.K_SOURCE, '') or self.filepath, texture_dir=self.texture_dir,
                           mrl_path=self.filepath, report=self.report)
        except Exception as e:      # noqa
            self.report({'ERROR'}, rpt('Load MRL failed: %s') % e)
            return {'CANCELLED'}
        return {'FINISHED'}


class RE6_OT_assign_texture(bpy.types.Operator, ImportHelper):
    """Use a .tex (or any image) as base / normal / mask texture of the active material"""
    bl_idname = 're6_mrl.assign_texture'
    bl_label = 'Assign Texture'
    bl_options = {'REGISTER', 'UNDO'}

    filter_glob: StringProperty(default='*.tex;*.dds;*.png;*.tga;*.jpg;*.jpeg;*.bmp', options={'HIDDEN'})
    role: EnumProperty(name='Use As', default='albedo',
                       items=[('albedo', 'Base (BM)', 'Colour texture'),
                              ('normal', 'Normal (NM)', 'DXT5nm normal map (x in alpha, y in green)'),
                              ('mask', 'Mask (MM)', 'Mask texture, not connected')])

    @classmethod
    def poll(cls, context):
        from . import mrl_objects as MO
        return MO.active_entry(context) is not None

    def execute(self, context):
        from . import mrl_objects as MO
        from .materials import image_tex_path, load_image_file, set_binding, set_role_image, virtual_path
        entry = MO.active_entry(context)
        col = next((c for c in entry.users_collection if C.is_mrl(c)), None)
        src = MO.model_source(col) if col is not None else ''
        vp = virtual_path(src) if src else None
        vdir = vp.rsplit('/', 1)[0] if vp else ''
        try:
            im = load_image_file(self.filepath, self.role, vdir=vdir)
        except Exception as e:      # noqa
            self.report({'ERROR'}, rpt('Cannot load %s: %s') % (os.path.basename(self.filepath), e))
            return {'CANCELLED'}
        if not set_binding(entry, self.role, image_tex_path(im)):
            self.report({'WARNING'}, rpt('%s has no texture slot for this role; the image is shown but not written to the '
                                         '.mrl') % entry.name)
        if entry.re6_mrl_material.linkedMaterial is None:
            MO.MT.build_visual(entry, MO.make_finder(col) if col is not None else MO.MT.TextureFinder([], ()), False)
        set_role_image(entry.re6_mrl_material.linkedMaterial, self.role, im)
        self.report({'INFO'}, '%s: %s = %s' % (entry.name, self.role, im.name))
        return {'FINISHED'}


class RE6_MOD_FH_drag_import(bpy.types.FileHandler):
    bl_idname = 'RE6_MOD_FH_drag_import'
    bl_label = 'File handler for RE6 MOD importing'
    bl_import_operator = RE6_OT_import_mod.bl_idname
    bl_file_extensions = '.mod'

    @classmethod
    def poll_drop(cls, context):
        return context.area and context.area.type == 'VIEW_3D'


CLASSES = (RE6_OT_import_mod, RE6_OT_export_mod, RE6_OT_load_mrl, RE6_OT_assign_texture, RE6_MOD_FH_drag_import)


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
