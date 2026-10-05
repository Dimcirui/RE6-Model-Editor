# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 Dimcirui

import bpy
from bpy.props import (BoolProperty, CollectionProperty, EnumProperty, FloatProperty, FloatVectorProperty, IntProperty,
                       StringProperty)

from .ccl_nodes import DEFAULT_COLOR as COLLISION_COLOR
from .ctc_nodes import CHAIN_COLOR, CONE_COLOR

ROOT = __package__.rsplit('.', 1)[0]      # the add-on package, also when installed as an extension (bl_ext.<repo>.<name>)

DISPLAY_ITEMS = [('OCTAHEDRAL', 'Octahedral', 'Display bones as octahedral shape (default)'),
                 ('STICK', 'Stick', 'Display bones as simple 2D lines with dots'),
                 ('BBONE', 'B-Bone', 'Display bones as boxes, showing subdivision and B-Splines'),
                 ('ENVELOPE', 'Envelope', 'Display bones as extruded spheres, showing deformation influence volume'),
                 ('WIRE', 'Wire', 'Display bones as thin wires, showing subdivision and B-Splines')]
SHADOW_ITEMS = [('KEEP', 'Keep As Is', 'Write exactly the meshes in the collection (imported shadow meshes included)'),
                ('REGENERATE', 'Regenerate', 'Add a shadow-only copy for every mesh that relies on a separate shadow pass'),
                ('NONE', 'None', 'Every mesh draws and casts shadows itself (render mask 0xFFFF)')]


class Re6GamePathPG(bpy.types.PropertyGroup):
    path: StringProperty(
        name='Path', subtype='DIR_PATH', default='',
        description='Set the path to the folder that contains nativePC: the game folder or an extracted mod folder.'
                    '\nThis determines where textures will be imported from (the exact texture path below each of these folders).'
                    '\nExample: D:\\RE6_EXTRACT or D:\\SteamLibrary\\steamapps\\common\\RE6')


class RE6_UL_GamePathList(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        layout.scale_y = 1.1
        layout.prop(item, 'path')


class RE6_OT_game_path_add(bpy.types.Operator):
    bl_idname = 're6_mod.game_path_list_add_item'
    bl_description = 'Add path to the extracted game folder.\nExample: D:\\RE6_EXTRACT (the folder that contains nativePC)'
    bl_label = 'Add Game Path'

    def execute(self, context):
        p = get()
        if p is not None:
            p.gamePathList_items.add()
            p.gamePathList_index = len(p.gamePathList_items) - 1
        return {'FINISHED'}


class RE6_OT_game_path_remove(bpy.types.Operator):
    bl_idname = 're6_mod.game_path_list_remove_item'
    bl_description = 'Remove game path from the list'
    bl_label = 'Remove Selected Path'

    def execute(self, context):
        p = get()
        if p is not None and 0 <= p.gamePathList_index < len(p.gamePathList_items):
            p.gamePathList_items.remove(p.gamePathList_index)
            p.gamePathList_index = min(max(0, p.gamePathList_index - 1), len(p.gamePathList_items) - 1)
        return {'FINISHED'}


class RE6_OT_game_path_reorder(bpy.types.Operator):
    bl_idname = 're6_mod.game_path_list_reorder_item'
    bl_description = 'Change the order in which files will be searched'
    bl_label = 'Reorder Item'
    direction: EnumProperty(items=[('UP', 'Up', ''), ('DOWN', 'Down', '')], default='UP')

    def execute(self, context):
        p = get()
        if p is None:
            return {'CANCELLED'}
        i = p.gamePathList_index
        j = i - 1 if self.direction == 'UP' else i + 1
        if 0 <= i < len(p.gamePathList_items) and 0 <= j < len(p.gamePathList_items):
            p.gamePathList_items.move(i, j)
            p.gamePathList_index = j
        return {'FINISHED'}


class Re6Preferences(bpy.types.AddonPreferences):
    bl_idname = ROOT

    showAdvancedOptions: BoolProperty(name='Show Advanced Options', default=True)
    showModImportOptions: BoolProperty(name='Show Mod Import Options', default=False)
    showModExportOptions: BoolProperty(name='Show Mod Export Options', default=False)
    showCTCVisibilityOptions: BoolProperty(name='Show CTC Visibility Options', default=False)
    showGamePath: BoolProperty(name='Show Game Path', default=True)

    dragDropImportOptions: BoolProperty(
        name='Show Drag and Drop Import Options (Blender 4.1+)',
        description='Show import options when dragging files into the 3D View.'
                    '\nIf this is disabled, the default import options will be used.'
                    '\nDrag and drop importing is only supported on Blender 4.1+',
        default=False if bpy.app.version < (4, 1, 0) else True)
    showCTCProperties: BoolProperty(
        name='Show CTC & CCL Properties In Sub Panel', default=True,
        description='Synchronously show ctc & ccl properties in "RE6 Chain" panel.\nIf checked, when activating a ctc & ccl '
                    'object, the properties will also be shown in the "Properties" sub-panel')
    showConsole: BoolProperty(
        name='Show Console During Import / Export',
        description='When importing or exporting a file, the console will be opened so that progress can be viewed.'
                    '\nNote that if the console is already opened before import or export, it will be closed instead.'
                    '\n This is a limitation of Blender, there\'s no way to get the active state of the console window',
        default=True)

    # RE6 extras: where textures come from and whether they are stored in the .blend
    texture_dir: StringProperty(
        name='Extra Texture Folder', subtype='DIR_PATH', default='',
        description='Folder with extracted .tex files (either the usual data/chara/... tree or flat)')
    pack_textures: BoolProperty(
        name='Pack Textures', default=True,
        description='Store imported textures inside the .blend so that it does not depend on temporary files')

    saveGamePaths: BoolProperty(
        name='Save Game Paths Automatically',
        description='If a game path is detected when a mod is imported, add it to the game path list automatically',
        default=True)
    gamePathList_items: CollectionProperty(type=Re6GamePathPG)
    gamePathList_index: IntProperty(name='')

    # Default import settings (same names as the options of the import dialog)
    default_clearScene: BoolProperty(
        name='Clear Scene', description='Clear all objects before importing the mod file', default=False)
    default_loadMrlData: BoolProperty(
        name='Load Material Data',
        description='Imports the mrl materials as objects inside a collection in the outliner.'
                    '\nYou can make changes to material data by selecting the mrl material objects in the outliner.'
                    '\nUnder the Object Data Properties tab (green axis), there\'s a panel called "Mrl Material Properties".'
                    '\nMake any changes to mrl materials there',
        default=False)
    default_loadMaterials: BoolProperty(
        name='Load Mesh Materials',
        description='Load materials from the mrl file. This may increase the time the model takes to import',
        default=True)
    default_useBackfaceCulling: BoolProperty(
        name='Use Backface Culling',
        description='Enables backface culling on materials. May improve Blender\'s performance on high poly meshes.'
                    '\nBackface culling will only be enabled on materials without the two sided flag',
        default=False)
    default_addNestedCollections: BoolProperty(
        name='Add Nested Collections',
        description='Add a general parent collection to place other collections of various imported files.'
                    '\nThis will make the collection structure look clearer.'
                    '\nLeaving this option enabled is highly recommended',
        default=True)
    default_createCollections: BoolProperty(
        name='Create Collections',
        description='Create a collection for the mod.\nNote that collections are required for exporting and applying mrl '
                    'changes.\nLeaving this option enabled is recommended',
        default=True)
    default_importArmatureOnly: BoolProperty(
        name='Only Import Armature', description='Only import the armature of the mod file', default=False)
    default_importAllLODs: BoolProperty(
        name='Import All LODs',
        description='Import all LOD (level of detail) meshes in mod file.'
                    '\nIf unchecked, only the highest LOD meshes will be imported',
        default=False)
    default_importShadow: BoolProperty(
        name='Import Shadow Meshes',
        description='Import the meshes that are only drawn in the shadow pass', default=True)
    default_ArmatureDisplayType: EnumProperty(name='Armature Display Type', items=DISPLAY_ITEMS, default='OCTAHEDRAL')
    default_BonesDisplaySize: FloatProperty(
        name='', description='Set the display size of the bones to be imported', default=4.0, step=100, soft_min=0.0)

    # Default export options
    default_selectedOnly: BoolProperty(name='Only Selected Meshes', description='Only export selected meshes', default=False)
    default_visibleOnly: BoolProperty(name='Only Visible Meshes', description='Only export visible meshes', default=False)
    default_allowDuplicateBoneNames: BoolProperty(
        name='Allow Duplicate Bone Names', default=False,
        description='Accept bones named like "RE6Bone_050.001" and write the id before the ".001"')
    default_exportAllLODs: BoolProperty(
        name='Export All LODs',
        description='Export all LODs. If disabled, only LOD0 will be exported. Note that LODs meshes must be grouped inside '
                    'a collection for each level and that collection must be contained in another collection. A target '
                    'collection must also be set',
        default=True)
    default_useBlenderMaterialName: BoolProperty(
        name='Use Blender Material Names',
        description='If left unchecked, the exporter will get the material names to be used from the end of each object name.'
                    '\nFor example, if a mesh is named Group_0_Sub_0__Shirts_Mat, the material name is Shirts_Mat.'
                    '\nIf this option is enabled, the material name will instead be taken from the first material '
                    'assigned to the object',
        default=False)
    default_shadowMode: EnumProperty(name='Shadow Meshes', items=SHADOW_ITEMS, default='KEEP')
    default_loadPhysics: BoolProperty(
        name='Load Chains & Collisions', default=False,
        description='Load physical chain and collision objects from the ctc & ccl file')

    # Default display settings of the ctc & ccl objects (the RE6 Chain > Visibility panel of a new scene)
    default_drawChainsThroughObjects: BoolProperty(
        name='Draw Chains Through Objects', default=True,
        description='Make all ctc chain objects render through any objects in front of them')
    default_showNodeNames: BoolProperty(name='Show Node Names', description='Show Node Names in 3D View', default=True)
    default_drawNodesThroughObjects: BoolProperty(
        name='Draw Nodes Through Objects', default=True,
        description='Make all ctc node and frame objects render through any objects in front of them')
    default_showAngleLimitCones: BoolProperty(name='Show Cones', description='Show Angle Limit Cones in 3D View',
                                              default=True)
    default_drawConesThroughObjects: BoolProperty(
        name='Draw Cones Through Objects', default=True,
        description='Make all angle limit cones render through any objects in front of them')
    default_angleLimitDisplaySize: FloatProperty(name='Angle Limit Size', description='Set the display size of node angle '
                                                 'limits', default=4.0, min=0.0, step=10)
    default_coneDisplaySize: FloatProperty(name='Cone Size', description='Set the display size of node angle limit cones',
                                           default=5.0, min=0.0, step=10)
    default_chainDisplaySize: FloatProperty(name='Chain Size', description='Set the thickness of chain lines', default=6.0,
                                            min=0.0, step=10)
    default_chainColor: FloatVectorProperty(name='Chain Color', subtype='COLOR', size=4, min=0.0, max=1.0,
                                            default=CHAIN_COLOR)
    default_coneColor: FloatVectorProperty(name='Angle Limit Color', subtype='COLOR', size=4, min=0.0, max=1.0,
                                           default=CONE_COLOR)
    default_showRelationLines: BoolProperty(
        name='Show Relation Lines', default=True,
        description='Show dotted lines indicating object parents.\nNote that this affects all objects, not just ctc objects')
    default_hideLastNodeAngleLimit: BoolProperty(
        name='Hide Last Node Cone', default=True,
        description='Hide the last ctc node\'s angle limit cone.\nThis is because the last node is typically unused and has a '
                    'dummy rotation value')
    default_collisionColor: FloatVectorProperty(name='Collision Color', subtype='COLOR', size=4, min=0.0, max=1.0,
                                                default=COLLISION_COLOR)
    default_showCollisionNames: BoolProperty(name='Show Collision Names', description='Show CCL Collision Names in 3D View',
                                             default=True)
    default_drawCollisionsThroughObjects: BoolProperty(
        name='Draw Collisions Through Objects', default=True,
        description='Make all ccl collision objects render through any objects in front of them')
    default_drawCapsuleHandlesThroughObjects: BoolProperty(
        name='Draw Handles Through Objects', default=True,
        description='Make all capsule handle objects render through any objects in front of them')

    last_export_dir_mod: StringProperty(
        name='Last MOD Export Directory', description='Last directory used when exporting a MOD file',
        default='', subtype='DIR_PATH')
    last_export_dir_ctc: StringProperty(
        name='Last CTC Export Directory', description='Last directory used when exporting a CTC file',
        default='', subtype='DIR_PATH')
    last_export_dir_ccl: StringProperty(
        name='Last CCL Export Directory', description='Last directory used when exporting a CCL file',
        default='', subtype='DIR_PATH')
    last_export_dir_mrl: StringProperty(
        name='Last MRL Export Directory', description='Last directory used when exporting a MRL file',
        default='', subtype='DIR_PATH')

    def game_paths(self):
        return [i.path for i in self.gamePathList_items if i.path]

    def draw(self, context):
        layout = self.layout

        def header(prop, text):
            row = layout.row()
            icon = 'DOWNARROW_HLT' if getattr(self, prop) else 'RIGHTARROW'
            row.prop(self, prop, icon=icon, icon_only=True, emboss=False)
            row.label(text=text)

        def rows(col, names):
            for n in names:
                row = col.row(align=True)
                row.scale_y = 1.1
                row.prop(self, n)

        header('showAdvancedOptions', 'Advanced Options')
        if self.showAdvancedOptions:
            box = layout.box()
            rows(box.column(align=True), ('dragDropImportOptions', 'showConsole', 'showCTCProperties'))

        header('showModImportOptions', 'Mod Import Options')
        if self.showModImportOptions:
            box = layout.box()
            col = box.column(align=True)

            row = col.row(align=True)
            row.label(text='Armature Display Type:')
            col.separator()

            row = col.row(align=True)
            row.scale_y = 1.1
            row.prop(self, 'default_ArmatureDisplayType', text='')
            col.separator()

            row = col.row(align=True)
            row.label(text='Bones Display Size:')
            col.separator()

            row = col.row(align=True)
            row.scale_y = 1.1
            row.prop(self, 'default_BonesDisplaySize', text='')
            col.separator()

            rows(col, ('default_addNestedCollections', 'default_importAllLODs', 'default_importShadow',
                       'default_importArmatureOnly'))
            col.separator()
            col.separator()
            rows(col, ('default_loadMrlData', 'default_loadMaterials'))
            col.separator()
            col.separator()
            rows(col, ('default_loadPhysics',))

        header('showModExportOptions', 'Mod Export Options')
        if self.showModExportOptions:
            box = layout.box()
            rows(box.column(align=True), ('default_selectedOnly', 'default_visibleOnly', 'default_useBlenderMaterialName',
                                          'default_shadowMode', 'default_allowDuplicateBoneNames'))

        header('showCTCVisibilityOptions', 'CTC Visibility Options')
        if self.showCTCVisibilityOptions:
            box = layout.box()
            box.use_property_split = True
            box.use_property_decorate = False
            col = box.column(align=True)

            def opt(name, heading=''):
                row = col.row(heading=heading, align=True)
                row.scale_y = 1.1
                row.prop(self, name)

            opt('default_showRelationLines', 'Show Options')
            opt('default_showAngleLimitCones')
            opt('default_hideLastNodeAngleLimit')
            opt('default_showNodeNames')
            opt('default_showCollisionNames')
            col.separator()
            col.separator()
            opt('default_drawChainsThroughObjects', 'Draw Options')
            opt('default_drawNodesThroughObjects')
            opt('default_drawConesThroughObjects')
            opt('default_drawCollisionsThroughObjects')
            opt('default_drawCapsuleHandlesThroughObjects')
            col.separator()
            col.separator()
            for name in ('default_chainDisplaySize', 'default_coneDisplaySize', 'default_angleLimitDisplaySize',
                         'default_chainColor', 'default_coneColor', 'default_collisionColor'):
                col.separator()
                opt(name)

        header('showGamePath', 'Game Path')
        if self.showGamePath:
            box = layout.box()
            row = box.row()
            row.scale_y = 1.1
            row.prop(self, 'saveGamePaths')
            row = box.row()
            row.template_list('RE6_UL_GamePathList', '', self, 'gamePathList_items', self, 'gamePathList_index', rows=3)
            row = box.row()
            row.scale_y = 1.1
            row.operator(RE6_OT_game_path_add.bl_idname)
            row.operator(RE6_OT_game_path_remove.bl_idname)

            row = box.row()
            row.scale_y = 1.1
            row.operator(RE6_OT_game_path_reorder.bl_idname, text='Move Up').direction = 'UP'
            row.operator(RE6_OT_game_path_reorder.bl_idname, text='Move Down').direction = 'DOWN'
            box.separator()
            rows(box.column(align=True), ('texture_dir', 'pack_textures'))


def get():
    a = bpy.context.preferences.addons.get(ROOT)
    return a.preferences if a else None


CTC_VISIBILITY = ('drawChainsThroughObjects', 'showNodeNames', 'drawNodesThroughObjects', 'showAngleLimitCones',
                  'drawConesThroughObjects', 'angleLimitDisplaySize', 'coneDisplaySize', 'chainDisplaySize', 'chainColor',
                  'coneColor', 'showRelationLines', 'hideLastNodeAngleLimit')
CCL_VISIBILITY = ('collisionColor', 'showCollisionNames', 'drawCollisionsThroughObjects', 'drawCapsuleHandlesThroughObjects')


def load_ctc_visibility(scene):
    """give the Visibility panel of a scene the defaults of the preferences, once (at the first ctc / ccl import or the first
    ctc collection), like importSettingsLoaded does for the import dialog"""
    p = get()
    ctc_tp, ccl_tp = scene.re6_ctc_toolpanel, scene.re6_ccl_toolpanel
    if p is None or ctc_tp.visibilitySettingsLoaded:
        return
    for tp, names in ((ctc_tp, CTC_VISIBILITY), (ccl_tp, CCL_VISIBILITY)):
        for n in names:
            setattr(tp, n, getattr(p, 'default_' + n))
    ctc_tp.visibilitySettingsLoaded = True


def toggle_console():
    """what the import / export operators of the MHW Model Editor do before and after their job when 'Show Console' is on"""
    p = get()
    if p is not None and p.showConsole:
        try:
            bpy.ops.wm.console_toggle()
        except Exception:
            pass


def save_game_path(path):
    """add a detected game folder to the list (saveChunkPaths of the MHW Model Editor)"""
    p = get()
    if p is None or not p.saveGamePaths or not path:
        return
    if path not in [i.path for i in p.gamePathList_items]:
        p.gamePathList_items.add().path = path


CLASSES = (Re6GamePathPG, RE6_UL_GamePathList, RE6_OT_game_path_add, RE6_OT_game_path_remove, RE6_OT_game_path_reorder,
           Re6Preferences)


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
