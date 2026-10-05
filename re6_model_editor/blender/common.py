# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 Dimcirui

"""Shared constants and matrix helpers of the Blender layer."""
import re
from math import radians

import bpy
import numpy as np
from mathutils import Matrix

# RE6: Y up, centimetres  ->  Blender: Z up, metres   (same convention as the MHW Model Editor)
IMPORT_MATRIX = Matrix.Rotation(radians(90.0), 4, 'X') @ Matrix.Scale(0.01, 4)
EXPORT_MATRIX = IMPORT_MATRIX.inverted()
ROT_X90 = Matrix.Rotation(radians(90.0), 3, 'X')
ROT_X90_INV = ROT_X90.inverted()

BONE_PREFIX = 'RE6Bone_'
MAT_PREFIX = 'MAT_'

# custom properties, named like the MHW Model Editor's (Mod3_Header_*, Mod3_Group_*, Mod3_Mesh_*, Mod3_Bone_*)
TYPE = '~TYPE'                   # marks collections and objects (value = one of the T_* below)
T_MOD = 'RE6_MOD_COLLECTION'
T_MRL = 'RE6_MRL_COLLECTION'
T_MAT = 'RE6_MRL_MATERIAL'

# the function id of a bone is NOT stored: it is the number in the bone name (bone_name_id), as in the MHW Model Editor
K_MIRROR, K_UNK, K_RADIUS, K_LENGTH, K_INDEX = ('Mod_Bone_Symmetry', 'Mod_Bone_Unkn', 'Mod_Bone_Radius', 'Mod_Bone_Length',
                                               'Mod_Bone_Index')
K_NAME = 'Mrl_Name'              # custom property of an MRL material empty: the resolved name of its hash
K_MAT_HASH = 're6_hash'          # custom property of a Blender material: hash of the .mod material it shows

# model collection (what the importer writes, the exporter reads)
K_SOURCE = 'Mod_Source'
K_ORIGIN, K_SCALE = 'Mod_Header_Origin', 'Mod_Header_Scale'
K_MATERIALS = 'Mod_Header_Materials'          # JSON list of the hashes of the material table
K_LOD_DIST, K_REMAP, K_TRAILER, K_TAIL_PAD = 'Mod_Header_LodDist', 'Mod_Header_Remap', 'Mod_Header_Trailer', 'Mod_Header_TailPad'
K_GROUP = 'Mod_Group_'           # + 3 digit group id = the 4 floats of the group sphere

# mesh data (custom properties of obj.data, name -> default)
MESH_DEFAULTS = {
    'Mod_Mesh_Index': -1,            # position in the mesh table of the original file
    'Mod_Mesh_LOD': 255,             # LOD bit mask: 1 = LOD1, 2 = LOD2, 252 = LOD3 and up, 255 = all
    'Mod_Mesh_RenderMode': 0xFFFF,   # draw_mode: 0xFFFF draw + shadows, 0xFDF7 / 0xFEFB drawn (shadow copy elsewhere), 0x1020 shadow only
    'Mod_Mesh_Flags': 0x43,          # topology (bits 0-5), binormal flip (bit 6), bridge (bit 7)
    'Mod_Mesh_AlphaPriority': 0,     # high byte of the weight field
    'Mod_Mesh_WeightFlags': 0,       # disp / shape / sort bits of the weight field
    'Mod_Mesh_WeightNum': 0,         # declared influences
    'Mod_Mesh_VertexFormat': '',     # hash of the vertex format read from the file ('' = choose on export)
    'Mod_Mesh_ConnectId': 0,         # draw order key
    'Mod_Mesh_Boundary': 0,          # sort key
    'Mod_Mesh_Imported': 0,
}
K_EXCLUDE = 'ModExportExclude'   # custom property of an object: skip it on export


LOD_ALL = 255        # lod mask of a mesh that is drawn at every level
LOD_NAME = re.compile(r'^LOD (ALL|\d+) - ')


def lod_level(mask):
    """the level of a lod bit mask as it is written in the name of a LOD collection: ALL (255) or the lowest level of the
    mask (1 -> 0, 2 -> 1, 252 -> 2)"""
    if mask == LOD_ALL or mask <= 0:
        return 'ALL'
    return str((mask & -mask).bit_length() - 1)


def lod_collection_name(level, root):
    return 'LOD %s - %s' % (level, root.name)


def lod_mask(level, highest):
    """lod bit mask of a mesh in the LOD collection `level`: ALL = 255, a level = its own bit, the highest level also covers
    every level below it (256 - bit)"""
    if level == 'ALL':
        return LOD_ALL
    n = int(level)
    return (256 - (1 << n)) & 0xFF if n == highest else 1 << n


def lod_levels_of(root):
    """{object name: level} of the meshes inside LOD collections of a model collection, and the highest level found"""
    parent = {}
    for c in [root, *root.children_recursive]:
        for ch in c.children:
            parent[ch.name] = c
    out = {}
    highest = 0
    for c in [root, *root.children_recursive]:
        m = LOD_NAME.match(c.name)
        if m and m.group(1) != 'ALL':
            highest = max(highest, int(m.group(1)))
    for o in root.all_objects:
        for c in o.users_collection:
            while c is not None:
                m = LOD_NAME.match(c.name)
                if m:
                    out[o.name] = m.group(1)
                    break
                c = parent.get(c.name)
            if o.name in out:
                break
    return out, highest


def clear_scene():
    """clearScene() of the MHW Model Editor: removes everything that is in the file"""
    for col in list(bpy.data.collections):
        for obj in list(col.objects):
            col.objects.unlink(obj)
        bpy.data.collections.remove(col)
    for data in (bpy.data.objects, bpy.data.meshes, bpy.data.lights, bpy.data.cameras, bpy.data.armatures,
                 bpy.data.materials, bpy.data.node_groups):
        for item in list(data):
            data.remove(item)
    for im in list(bpy.data.images):
        if im.users == 0:
            bpy.data.images.remove(im)


def mesh_get(obj, key):
    v = obj.data.get(key, MESH_DEFAULTS[key])
    if isinstance(v, str) and isinstance(MESH_DEFAULTS[key], int):      # values beyond 32 bit are stored as text
        return int(v)
    return v


def mesh_set(obj, **kw):
    """mesh_set(obj, Mod_Mesh_LOD=1 ...)"""
    for k, v in kw.items():
        obj.data[k] = str(v) if isinstance(v, int) and not -2 ** 31 <= v < 2 ** 31 else v


def group_of(obj):
    """visibility group of a mesh object: the number of Group_<n> in its name (0 when it does not follow the scheme)"""
    import re
    m = re.search(r'Group_(\d+)', obj.name)
    return int(m.group(1)) if m else 0


MAT_OBJ_PREFIX = 'Mrl Material '     # objects of an mrl collection: "Mrl Material 00 (pl_skin)"


def mat_obj_name(index, name):
    return '%s%s (%s)' % (MAT_OBJ_PREFIX, str(index).zfill(2), name)


def mat_obj_number(obj_name):
    """the 00 of "Mrl Material 00 (pl_skin)" (None when the name does not follow the scheme)"""
    import re
    m = re.match(r'^Mrl Material (\d+) \(', obj_name)
    return int(m.group(1)) if m else None


def mat_obj_label(obj_name):
    """the name inside the parentheses of the object name (None when the name does not follow the scheme)"""
    if obj_name.startswith(MAT_OBJ_PREFIX) and '(' in obj_name:
        return obj_name.rsplit('(', 1)[1].split(')')[0]
    return None


# chains and collisions (.ctc / .ccl)
T_CTC = 'RE6_CTC_COLLECTION'
T_CTC_HEADER = 'RE6_CTC_HEADER'
T_CTC_CHAIN = 'RE6_CTC_CHAIN'
T_CTC_NODE = 'RE6_CTC_NODE'
T_CTC_FRAME = 'RE6_CTC_NODE_FRAME'
T_CTC_HELPER = 'RE6_CTC_NODE_FRAME_HELPER'
T_CCL_SPHERE = 'RE6_CCL_SPHERE'
T_CCL_CAPSULE = 'RE6_CCL_CAPSULE'
T_CCL_START = 'RE6_CCL_CAPSULE_START'
T_CCL_END = 'RE6_CCL_CAPSULE_END'
MAX_BONE_FUNCTION = 254          # bone ids are bytes in the .mod, 255 is the "unused" marker
BONE_NAME_RE = r'^%s\d{3}$' % BONE_PREFIX


def is_ctc(col):
    return col is not None and col.get(TYPE) == T_CTC


BONE_ID_RE = r'^%s(\d{3})(\.\d+)?$' % BONE_PREFIX


def bone_name_id(name):
    """function id written in a bone name: "RE6Bone_050" -> 50, and "RE6Bone_050.001" (what Blender makes of a second bone with
    that id) -> 50 too; None for any other name. The name is the only source of the id, like "MhBone_xxx" in the MHW Model Editor."""
    m = re.match(BONE_ID_RE, name)
    return int(m.group(1)) if m else None


def is_dup_bone_name(name):
    m = re.match(BONE_ID_RE, name)
    return bool(m and m.group(2))


def bone_fn_id(bone):
    """function id of an armature bone, from its name only (None when the name does not carry one)"""
    return bone_name_id(bone.name)


def bones_by_id(arm_obj):
    """{function id: bone name} of an armature (the first bone of an id when several have it: the one without ".001")"""
    out = {}
    for b in sorted(arm_obj.data.bones, key=lambda b: (is_dup_bone_name(b.name), b.name)):
        fid = bone_fn_id(b)
        if fid is not None:
            out.setdefault(fid, b.name)
    return out


def is_mod(col):
    return col is not None and col.get(TYPE) == T_MOD


def is_mrl(col):
    return col is not None and col.get(TYPE) == T_MRL


def mod_collections():
    return [c for c in bpy.data.collections if is_mod(c)]


def mrl_collections():
    return [c for c in bpy.data.collections if is_mrl(c)]


def show_message_box(message='', title='Message Box', icon='INFO'):
    def draw(self, context):
        self.layout.label(text=message)
    if bpy.app.background:      # no UI: popup_menu crashes Blender
        print('%s: %s' % (title, message))
        return
    bpy.context.window_manager.popup_menu(draw, title=title, icon=icon)


def show_error_message_box(message):
    print('\033[91mERROR: ' + message + '\033[0m')
    show_message_box(message, title='Error', icon='ERROR')


def find_temp_space(type_name):
    """the file browser that is open at the moment (findTempSpace() of the MHW Model Editor), None when there is none"""
    temp = bpy.data.screens.get('temp')
    if temp is not None:
        for area in temp.areas:
            for space in area.spaces:
                try:
                    if type(space.params).__name__ == type_name:
                        return space
                except AttributeError:
                    pass
    return None


def set_export_filename(collection, ext):
    """update callback of the export collection pickers: show the name of the picked collection in the file browser"""
    space = find_temp_space('FileSelectParams')
    if space is not None and collection is not None and ext in collection.name:
        space.params.filename = collection.name.split(ext)[0] + ext


def split_game_path(filepath):
    """(root folder, rest) for a file below <root>/data/<game folder>/... (what the games call nativePC), else None"""
    from .materials import GAME_DATA_DIRS
    parts = filepath.replace('\\', '/').split('/')
    for i in range(len(parts) - 2, -1, -1):
        if parts[i].lower() == 'data' and i + 1 < len(parts) and parts[i + 1].lower() in GAME_DATA_DIRS:
            return '/'.join(parts[:i]), '/'.join(parts[i:])
    return None


def set_mod_directory(filepath):
    """setModDirectoryFromFilePath(): the mod directory of the tool panel = the folder above data/ of an exported file"""
    split = split_game_path(filepath)
    tp = bpy.context.scene.re6_mrl_toolpanel
    if split:
        tp.modDirectory = split[0]
        print('Set mod directory to %s.' % tp.modDirectory)
    else:
        print('Failed to set mod directory, exported file path probably does not follow the data/ folder scheme.')


def row_to_matrix(m4):
    """file matrix (row vectors, translation in the last row) -> mathutils column-vector Matrix"""
    return Matrix(np.asarray(m4, np.float64).T.tolist())


def bone_world_re6(bone, armature_obj):
    """RE6 world matrix (row-vector 4x4, numpy) of an armature bone in rest pose"""
    m = armature_obj.matrix_world @ bone.matrix_local
    rot = ROT_X90_INV @ m.to_3x3()
    t = EXPORT_MATRIX @ m.translation
    out = np.eye(4)
    out[:3, :3] = np.array(rot).T
    out[3, :3] = np.array(t)
    return out


def mat_name(h):
    return '%s%08x' % (MAT_PREFIX, h)


def mat_label(h):
    """the name of a material hash: the resolved name, else MAT_<hash> (what meshes and materials are called)"""
    from ..core.hashes import material_name
    return material_name(h) or mat_name(h)


def parse_mat_hash(name):
    """hash from a material name like MAT_6390b116(.001); None when it does not follow the scheme"""
    if name.startswith(MAT_PREFIX):
        try:
            return int(name[len(MAT_PREFIX):len(MAT_PREFIX) + 8], 16)
        except ValueError:
            return None
    return None
