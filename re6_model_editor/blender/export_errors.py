# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 Dimcirui

"""The export error window (the counterpart of mod3_export_errors.py / mrl3_export_errors.py of the MHW Model Editor).

An exporter collects its problems in an error dict {error type: {count, objectSet / boneSet}} (add_error), raises
ExportErrors when there are any, and the operator that called it shows them with show_error_window.
"""
import textwrap

import bpy
from bpy.props import CollectionProperty, IntProperty, StringProperty
from bpy.types import Operator

from .i18n import iface

ERROR_WINDOW_SIZE = 750
SPLIT_FACTOR = .35


class textColors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


def add_error(error_dict, error_type, objectName=None, boneName=None):
    """addErrorToDict()"""
    if error_type in error_dict:
        error_dict[error_type]['count'] += 1
        if objectName is not None:
            error_dict[error_type].setdefault('objectSet', set()).add(objectName)
        if boneName is not None:
            error_dict[error_type].setdefault('boneSet', set()).add(boneName)
    else:
        if objectName is not None:
            error_dict[error_type] = {'count': 1, 'objectSet': {objectName}}
        elif boneName is not None:
            error_dict[error_type] = {'count': 1, 'boneSet': {boneName}}
        else:
            error_dict[error_type] = {'count': 1}


class ExportErrors(Exception):
    """raised by an exporter that found problems; .errors is the error dict"""

    def __init__(self, errors):
        super().__init__(', '.join('%s (%d)' % (k, v['count']) for k, v in sorted(errors.items())))
        self.errors = errors


# type -> "Title\nERROR INFO:\n...\n——————————————\nHOW TO FIX:\n..." (the first line is the title shown in the list)
ERROR_INFO = {
    # ---- mrl
    'NoTargetMrlCollection': """No Target Mrl Collection
ERROR INFO:
Target mrl collection was not selected when exporting.
——————————————
HOW TO FIX:
Select a target mrl collection in the export options.""",

    'MultipleSameMaterials': """Multiple Same Materials
ERROR INFO:
Multiple mrl objects have the same material name.
——————————————
HOW TO FIX:
Delete extra conflict objects, or set the material name to a different name.
Make sure each mrl object has its unique material name.
""",

    'NoMrlMaterials': """No Materials
ERROR INFO:
The mrl collection has no material objects.
——————————————
HOW TO FIX:
Import an mrl file, or add material objects with the Material List.
""",

    'UnwritableMaterial': """Unwritable Material
ERROR INFO:
The data of the material object can not be written, for example because it uses a sampler state that is not known.
——————————————
HOW TO FIX:
Check the Sampler List and the Flags of the material object, or import the material again.
""",

    'MrlWriteFailed': """Writing The File Failed
ERROR INFO:
The mrl file could not be written (a texture path is longer than 63 characters, or the file can not be created).
——————————————
HOW TO FIX:
Shorten the texture paths of the Map List, and make sure the export folder can be written to.
""",

    # ---- mod
    'NoTargetModCollection': """No Target Mod Collection
ERROR INFO:
Target mod collection was not selected when exporting.
——————————————
HOW TO FIX:
Select a target mod collection in the export options.""",

    'NoMeshesInCollection': """No Meshes In Collection
ERROR INFO:
No meshes were found in the target mod collection.
Also maybe there are no selected or visible meshes.
——————————————
HOW TO FIX:
Select a target mod collection in the export options that contains meshes.
If you checked "Only Selected Meshes" or "Only Visible Meshes" in the export options,
please make sure there are selected or visible meshes.""",

    'MultipleSameLodCollections': """Multiple Same Lod Collections
ERROR INFO:
There are multiple child lod collections with the same lod level.
——————————————
HOW TO FIX:
Change the name of child lod collections to ensure that each lod level is unique.""",

    'MoreThanOneArmature': """More Than One Armature
ERROR INFO:
More than one armature was found in the target mod collection.
——————————————
HOW TO FIX:
Move the extra armature into another collection or delete it.""",

    'MaxBonesExceeded': """Max Bones Exceeded
ERROR INFO:
The amount of bones on the armature exceeds the maximum limit of 255.
——————————————
HOW TO FIX:
Reduce the amount of bones on the armature.""",

    'BoneLoop': """Bone Hierarchy Loop
ERROR INFO:
The bone hierarchy contains a loop.
——————————————
HOW TO FIX:
Check the parents of the bones.""",

    'IncorrectBoneNameFormat': """Incorrect Bone Name Format
ERROR INFO:
The id of a bone is the number in its name. Some bones are not named "RE6Bone_xxx" (xxx = three digits),
or the number exceeds the maximum limit of 254.
Bones named like "RE6Bone_050.001" are only accepted with the "Allow Duplicate Bone Names" option.
——————————————
HOW TO FIX:
Change the bone name to "RE6Bone_xxx", where xxx is the bone id, such as "RE6Bone_150".
And also make sure that the id is less than 255.""",

    'NoMaterialOnSubMesh': """No Material On Sub Mesh
ERROR INFO:
A mesh has no material assigned to it.
All meshes must have one material assigned to them.
——————————————
HOW TO FIX:
Specify an mrl material name on the end of the object name separated by two underscores.
Example Object Name: Group_0_Sub_0__pl_cloth
If "Use Blender Material Names" is enabled, assign a material to the mesh instead.""",

    'NoVerticesOnSubMesh': """No Vertices On Sub Mesh
ERROR INFO:
A mesh has no vertices. All meshes must have at least 3 vertices and 1 face.
——————————————
HOW TO FIX:
Delete the listed mesh objects.""",

    'NoFacesOnSubMesh': """No Faces On Sub Mesh
ERROR INFO:
A mesh has no faces. All meshes must have at least 3 vertices and 1 face.
——————————————
HOW TO FIX:
Delete the listed mesh objects.""",

    'NoUVMapOnSubMesh': """No UV Map On Sub Mesh
ERROR INFO:
A mesh has no UV map. All meshes require at least one uv map.
Only shadow meshes can be exported without a UV map.
——————————————
HOW TO FIX:
Create a UV map.""",

    'NoWeightsOnMesh': """No Weights On Mesh
ERROR INFO:
A mesh has an armature, but no weights assigned to bones.
——————————————
HOW TO FIX:
Add a new vertex group and weight it to a bone on the armature in weight paint mode.""",

    'UnweightedVertices': """Vertices Without Weights
ERROR INFO:
Some vertices are not weighted to any bone.
——————————————
HOW TO FIX:
Assign the vertices to a vertex group of a bone in weight paint mode.""",

    'MaxWeightsPerVertexExceeded': """Max Weights Per Vertex Exceeded On Sub Mesh
ERROR INFO:
A vertex has more than the maximum of 8 weights assigned to it.
——————————————
HOW TO FIX:
Limit total weights to 8 in weight paint mode and normalize all weights.
Or click "Limit Total and Normalize All" button in "RE6 Mesh Tools" to solve this.""",

    'MaxVerticesExceeded': """Max Vertices Exceeded On Sub Mesh
ERROR INFO:
A mesh exceeded the limit of 65535 vertices (after splitting the vertices that have more than one UV, normal or color).
——————————————
HOW TO FIX:
Separate parts of the mesh into more sub meshes.
Or use the decimate modifier to reduce mesh quality.""",

    'TotalMeshesExceeded': """Total Meshes Exceeded Max Limit
ERROR INFO:
Total meshes count exceeds the maximum limit of 65535.
——————————————
HOW TO FIX:
Join meshes that use the same material.""",

    'TotalMaterialsExceeded': """Total Materials Exceeded Max Limit
ERROR INFO:
Total materials count exceeds the maximum limit of 4096.
——————————————
HOW TO FIX:
Merge materials.""",

    'VertexFormatMismatch': """Vertex Format Mismatch
ERROR INFO:
The vertex format set on a mesh can not be used: a skinned format on a model without a skeleton
(or a static one on a model with a skeleton), or a value that is not a vertex format.
Bone influences, UV maps and vertex colors that a format can not hold are not errors: they are dropped on export.
——————————————
HOW TO FIX:
Select the mesh and choose another format with "Set Vertex Format" in "RE6 Mesh Tools",
or set it to Auto so that the exporter chooses one.""",

    'ExportFailed': """Export Failed
ERROR INFO:
The model could not be written.
——————————————
HOW TO FIX:
Check Window > Toggle System Console for details.""",
}


SEP = '——————————————'


def _info(title, info, fix):
    return '%s\nERROR INFO:\n%s\n%s\nHOW TO FIX:\n%s' % (title, info, SEP, fix)


# the texts of the ctc and ccl export (a key that is not here is looked up in ERROR_INFO)
ERROR_INFO_KIND = {
    'ctc': {
        'NoTargetCTCCollection': _info('No Target CTC Collection', 'Target ctc collection was not selected when exporting.',
                                       'Select a target ctc collection in the export options.'),
        'HeaderHasParent': _info('Header Has Parent', 'CTC header cannot be a child of other objects.',
                                 'Make sure ctc header doesn\'t have parent objects.'),
        'NodeHasMoreThanOneFrame': _info('Node Has More Than One Frame', 'Some nodes have more than one frame as child.',
                                         'Make sure each node has only one child frame.'),
        'NodeHasNoFrame': _info('Node Has No Frame', 'Some nodes have no frame as child.',
                                'Make sure each node has only one child frame.'),
        'IncorrectNodeParent': _info('Incorrect Node Parent', 'Some nodes have incorrect parent object types.\nOr maybe node '
                                     'has no parent chain or node object.',
                                     'Make sure each node has a parent chain or node object.'),
        'InvalidNodeConstraint': _info('Invalid Node Constraint', 'The "BoneName" constraint of node has no target or '
                                       'subtarget.', 'Make sure "BoneName" constraint of node has target armature and '
                                       'subtarget bone.'),
        'NodeHasNoConstraint': _info('Node Has No Constraint', 'Some nodes have no "BoneName" constraint.',
                                     'Make sure each node has a "BoneName" constraint.'),
        'IncorrectChainParent': _info('Incorrect Chain Parent', 'Some chains have incorrect parent object types.\nOr maybe '
                                      'chain has no parent header object.', 'Make sure all chains are parented to header '
                                      'object.'),
        'ChainHasLessThanTwoNodes': _info('Chain Has Less Than Two Nodes', 'Some chains have less than two nodes as child.',
                                          'Make sure each chain has at least two nodes as its child.'),
        'NoCTCHeader': _info('No CTC Header', 'Target ctc collection has no ctc header object.',
                             'Make sure target ctc collection has only one ctc header object.'),
        'MoreThanOneCTCHeader': _info('More Than One CTC Header', 'Target ctc collection has more than one ctc header object.',
                                      'Make sure target ctc collection has only one ctc header object.'),
        'IncorrectBoneNameFormat': _info('Incorrect Bone Name Format', 'Some constraint bones are not named with format '
                                         '"RE6Bone_xxx".\nOr the number is larger than the maximum of 254.',
                                         'Change the bone name to "RE6Bone_xxx", where xxx is the bone id, such as '
                                         '"RE6Bone_150".\nAnd also make sure that the id is less than 255.'),
        'ChainHasBranch': _info('Chain Has Branch', 'Some chains have branching node structure.',
                                'Delete extra branch nodes.\nMake sure each chain has no branch nodes.'),
        'MultipleSameBones': _info('Multiple Same Bones', 'Multiple nodes have the same constraint bone.',
                                   'Delete extra conflict nodes.\nMake sure each node corresponds to a specific bone.'),
    },
    'ccl': {
        'NoTargetCTCCollection': _info('No Target CTC Collection', 'Target ctc collection was not selected when exporting.',
                                       'Select a target ctc collection in the export options.'),
        'CapsuleHasMultipleHeads': _info('Capsule Has Multiple Heads', 'Some capsule collisions have more than one head.',
                                         'Delete extra head.\nMake sure each capsule collision only has one head.'),
        'CapsuleHasMultipleTails': _info('Capsule Has Multiple Tails', 'Some capsule collisions have more than one tail.',
                                         'Delete extra tail.\nMake sure each capsule collision only has one tail.'),
        'CapsuleHasNoHead': _info('Capsule Has No Head', 'Some capsule collisions have no head.',
                                  'Make sure each capsule collision only has one head.'),
        'CapsuleHasNoTail': _info('Capsule Has No Tail', 'Some capsule collisions have no tail.',
                                  'Make sure each capsule collision only has one tail.'),
        'InvalidNodeConstraint': _info('Invalid Node Constraint', 'The "BoneName" constraint of sphere or capsule has no '
                                       'target or subtarget.', 'Make sure "BoneName" constraint of sphere or capsule has '
                                       'target armature and bone.'),
        'NodeHasNoConstraint': _info('Node Has No Constraint', 'Some spheres or capsules have no "BoneName" constraint.',
                                     'Make sure each sphere or capsule has a "BoneName" constraint.'),
        'IncorrectBoneNameFormat': _info('Incorrect Bone Name Format', 'Some constraint bones are not named with format '
                                         '"RE6Bone_xxx".\nOr the number is larger than the maximum of 254.',
                                         'Change the bone name to "RE6Bone_xxx", where xxx is the bone id, such as '
                                         '"RE6Bone_150".\nAnd also make sure that the id is less than 255.'),
    },
}


def info_of(kind, error_type):
    return ERROR_INFO_KIND.get(kind, {}).get(error_type) or ERROR_INFO.get(error_type) or '%s\nERROR INFO:\n%s' % (
        error_type, error_type)


def print_errors(error_dict, kind):
    """printMrl3ErrorDict(): the summary in the console"""
    print('\n%sUnable to export %s. %d error(s) were found that need to be fixed.%s\n' % (
        textColors.FAIL, kind, len(error_dict), textColors.ENDC))
    for error_type in sorted(error_dict):
        d = error_dict[error_type]
        info = info_of(kind, error_type)
        title, _, text = info.partition('\n')
        print('%s%s (%d)%s' % (textColors.WARNING, title, d['count'], textColors.ENDC))
        print(text)
        names = sorted(d.get('objectSet', ())) or sorted(d.get('boneSet', ()))
        if names:
            print('%s:' % ('ERROR OBJECTS' if d.get('objectSet') else 'ERROR BONES'))
            for n in names:
                print('  ' + n)
        print()
    print('\033[92m__________________________________\nRE6 %s export failed.\033[0m' % kind)


class Re6ErrorEntry(bpy.types.PropertyGroup):
    errorType: StringProperty(name='')
    errorName: StringProperty(name='')
    errorDescription: StringProperty(name='')
    objectSetString: StringProperty(name='')
    boneSetString: StringProperty(name='')
    errorCount: IntProperty(name='')


class MESH_UL_Re6ErrorList(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        layout.label(text='%s (%d)' % (iface(item.errorType), item.errorCount))

    # Disable double-click to rename
    def invoke(self, context, event):
        return {'PASS_THROUGH'}


class _ShowErrorWindow:
    bl_options = {'REGISTER'}
    scene_list = ''
    what = ''                    # 'mod' / 'mrl'

    collectionName: StringProperty()
    armatureName: StringProperty()
    errorList_items: CollectionProperty(type=Re6ErrorEntry)
    errorList_index: IntProperty(name='')

    def execute(self, context):
        return {'FINISHED'}

    def invoke(self, context, event):
        window = context.window
        window.cursor_warp(window.width // 2, window.height // 2)
        for entry in getattr(context.scene, self.scene_list):
            item = self.errorList_items.add()
            for key, value in entry.items():
                item[key] = value
        return context.window_manager.invoke_props_dialog(self, width=ERROR_WINDOW_SIZE)

    def draw(self, context):
        layout = self.layout
        row_count = 2
        font_scale = 9 * context.preferences.view.ui_scale
        max_label_width = int((ERROR_WINDOW_SIZE * (1 - SPLIT_FACTOR) * (2 - SPLIT_FACTOR)) // font_scale)
        n = len(self.errorList_items)
        layout.label(text=iface('The %s objects have %d %s that must be fixed before it can be exported.')
                     % (self.what, n, iface('issues') if n > 1 else iface('issue')), icon='ERROR')
        layout.label(text='%s %s' % (iface('Target Collection:'), self.collectionName))

        layout.row().separator()
        split = layout.split(factor=SPLIT_FACTOR)
        col1 = split.column()
        col2 = split.column()

        if n != 0:
            item = self.errorList_items[min(self.errorList_index, n - 1)]
            box = col2.box()
            for line in item.errorDescription.splitlines():
                for chunk in textwrap.wrap(iface(line.strip()), width=max_label_width):
                    box.label(text=chunk)
                    row_count += 1
            string = item.objectSetString if item.objectSetString != '' else item.boneSetString
            if string != '':
                box2 = col2.box()
                for line in string.splitlines():
                    for chunk in textwrap.wrap(iface(line.strip()), width=max_label_width):
                        box2.label(text=chunk)
                        row_count += 1
        col1.template_list(
            listtype_name='MESH_UL_Re6ErrorList', list_id='', dataptr=self, propname='errorList_items',
            active_dataptr=self, active_propname='errorList_index', rows=row_count, type='DEFAULT')


class RE6_OT_show_mod_errors(_ShowErrorWindow, Operator):
    """Show the errors found when exporting"""
    bl_idname = 're6_mod.show_export_error_window'
    bl_label = 'RE6 Mod Export Error'
    scene_list = 're6_mod_error_list'
    what = 'mod'


class RE6_OT_show_ctc_errors(_ShowErrorWindow, Operator):
    """Show the errors found when exporting"""
    bl_idname = 're6_ctc.show_export_error_window'
    bl_label = 'RE6 CTC Export Error'
    scene_list = 're6_ctc_error_list'
    what = 'ctc'


class RE6_OT_show_ccl_errors(_ShowErrorWindow, Operator):
    """Show the errors found when exporting"""
    bl_idname = 're6_ccl.show_export_error_window'
    bl_label = 'RE6 CCL Export Error'
    scene_list = 're6_ccl_error_list'
    what = 'ccl'


class RE6_OT_show_mrl_errors(_ShowErrorWindow, Operator):
    """Show the errors found when exporting"""
    bl_idname = 're6_mrl.show_export_error_window'
    bl_label = 'RE6 Mrl Export Error'
    scene_list = 're6_mrl_error_list'
    what = 'mrl'


def show_error_window(error_dict, kind, col_name='', arm_name=''):
    """fill the scene list and open the window; kind is 'mod' or 'mrl'"""
    lst = getattr(bpy.context.scene, 're6_%s_error_list' % kind)
    lst.clear()
    for error_type in sorted(error_dict):
        d = error_dict[error_type]
        item = lst.add()
        item.errorCount = d['count']
        info = info_of(kind, error_type)
        title, _, text = info.partition('\n')
        item.errorType, item.errorDescription = title, text
        if d.get('objectSet'):
            item.objectSetString = '\nERROR OBJECTS:\n' + '\n'.join(sorted(d['objectSet']))
        elif d.get('boneSet'):
            item.boneSetString = '\nERROR BONES:\n' + '\n'.join(sorted(d['boneSet']))
    getattr(bpy.ops, 're6_%s' % kind).show_export_error_window('INVOKE_DEFAULT', collectionName=col_name,
                                                              armatureName=arm_name)


CLASSES = (Re6ErrorEntry, MESH_UL_Re6ErrorList, RE6_OT_show_mod_errors, RE6_OT_show_mrl_errors, RE6_OT_show_ctc_errors,
           RE6_OT_show_ccl_errors)


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)
    bpy.types.Scene.re6_mod_error_list = CollectionProperty(type=Re6ErrorEntry)
    bpy.types.Scene.re6_mrl_error_list = CollectionProperty(type=Re6ErrorEntry)
    bpy.types.Scene.re6_ctc_error_list = CollectionProperty(type=Re6ErrorEntry)
    bpy.types.Scene.re6_ccl_error_list = CollectionProperty(type=Re6ErrorEntry)


def unregister():
    del bpy.types.Scene.re6_ccl_error_list
    del bpy.types.Scene.re6_ctc_error_list
    del bpy.types.Scene.re6_mrl_error_list
    del bpy.types.Scene.re6_mod_error_list
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
