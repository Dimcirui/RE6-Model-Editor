# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 Dimcirui

"""The .mrl of a model as Blender objects: a collection '<name>.mrl' with one empty per material (source of truth of
the material library, like the mrl3 collection of the MHW Model Editor), plus the operators that manage it."""
import json
import os
import random
import re

import bpy
from bpy.props import BoolProperty, CollectionProperty, EnumProperty, StringProperty
from bpy.types import Operator
from bpy_extras.io_utils import ImportHelper

from ..core import mrl as R
from ..core.hashes import jamcrc32, material_name
from . import common as C
from . import materials as MT
from . import prefs
from .i18n import rpt

K_SRC = 'Mrl_Source'
K_UNK = 'Mrl_Header_Unk'


# --- finding things ------------------------------------------------------------------------------------------

def is_entry(obj):
    return obj is not None and obj.type == 'EMPTY' and bool(obj.re6_mrl_material.hash)


def _order_key(o):
    n = C.mat_obj_number(o.name)
    return (n if n is not None else 10 ** 9, o.name)


def entries(mrl_col):
    """the material empties of an MRL collection in file order: the order of their names ("Mrl Material 00 (pl_skin)")"""
    return sorted((o for o in mrl_col.objects if is_entry(o)), key=_order_key)


def base_name(col):
    """'pl0000.mod' / 'pl0000.mrl' (Blender may add .001) -> 'pl0000'"""
    return re.sub(r'\.(mod|mrl)(\.\d{3})?$', '', col.name, flags=re.I)


def _parents(col):
    return [p for p in bpy.data.collections if col.name in p.children]


def _siblings_and_children(col):
    out = list(col.children_recursive)
    for p in _parents(col):
        out += [c for c in p.children if c != col]
    return out


def mrl_collection_of(model_col):
    """the '<name>.mrl' collection that belongs to a model collection '<name>.mod' (same name, a sibling inside the same
    parent collection as the MHW Model Editor lays it out; collections below the model collection are found too)"""
    if model_col is None:
        return None
    if C.is_mrl(model_col):
        return model_col
    base = base_name(model_col)
    cands = [c for c in _siblings_and_children(model_col) if C.is_mrl(c)]
    for c in cands:
        if base_name(c) == base:
            return c
    if model_col == bpy.context.scene.collection:
        return next((c for c in C.mrl_collections() if base_name(c) == base), None)
    return cands[0] if len(cands) == 1 else None


def mod_collection_of(mrl_col):
    """the model collection that belongs to an MRL collection (None when standalone)"""
    if mrl_col is None:
        return None
    base = base_name(mrl_col)
    for c in _siblings_and_children(mrl_col) + C.mod_collections():
        if C.is_mod(c) and base_name(c) == base:
            return c
    return None


def find_mrl_collection(context):
    """MRL collection of the active object (an entry, or something of a model), else the active one of the tool panel; None when
    neither tells (nothing is guessed: no "first model", no "any mrl of the file")"""
    from .operators import model_of_active_object
    obj = context.object
    if obj:
        for c in obj.users_collection:
            if C.is_mrl(c):
                return c
    model = model_of_active_object(context)
    col = mrl_collection_of(model) if model is not None else None
    if col is not None:
        return col
    tp = context.scene.re6_mrl_toolpanel.mrlCollection
    if tp is not None and C.is_mrl(tp):
        return tp
    return None


def active_entry(context):
    """the MRL empty the UI should act on: the active empty, or the owner of the active object's material"""
    obj = context.object
    if is_entry(obj):
        return obj
    if obj is not None and obj.type == 'MESH':
        return MT.owner_of(obj.active_material)
    return None


def model_source(mrl_col):
    """path of the .mod the collection belongs to ('' when standalone)"""
    mod = mod_collection_of(mrl_col)
    if mod is not None and mod.get(C.K_SOURCE):
        return mod[C.K_SOURCE]
    return mrl_col.get(K_SRC, '') if mrl_col.get(K_SRC, '').lower().endswith('.mod') else ''


def make_finder(mrl_col, texture_dir=''):
    p = prefs.get()
    src = model_source(mrl_col) or mrl_col.get(K_SRC, '')
    return MT.texture_finder(src, texture_dir, p.texture_dir if p else '', p.game_paths() if p else ())


# --- creating entries -------------------------------------------------------------------------------------------

def create_empty(mrl_col, mm, bindings, index):
    obj = bpy.data.objects.new(C.mat_obj_name(index, 'MAT_%08x' % mm.name), None)
    obj.empty_display_type = 'PLAIN_AXES'
    obj.empty_display_size = 0.10
    obj[C.TYPE] = C.T_MAT
    mrl_col.objects.link(obj)
    MT.store_material(obj, mm, index=index, bindings=bindings)
    nm = material_name(mm.name)
    if nm:
        obj[C.K_NAME] = nm
    obj.name = C.mat_obj_name(index, obj.re6_mrl_material.materialName)
    return obj


def new_collection(parent, name, source, mrl=None):
    col = bpy.data.collections.new(name)
    (parent or bpy.context.scene.collection).children.link(col)
    col.color_tag = 'COLOR_05'
    col[C.TYPE] = C.T_MRL
    col[K_SRC] = source
    col[K_UNK] = int(mrl.unk) if mrl is not None else R.DEFAULT_UNK
    return col


def fill_collection(mrl_col, mrl):
    for i, mm in enumerate(mrl.materials):
        create_empty(mrl_col, mm, R.bindings(mrl, mm), i)


def template_entry(mrl_col, name_hash, index=None):
    mm = R.from_template(name_hash)
    binds = [(c.b, None) for c in mm.commands if c.type == R.CMD_TEXTURE]
    return create_empty(mrl_col, mm, binds, len(entries(mrl_col)) if index is None else index)


def used_hashes(model_col):
    """material hashes of the meshes of a model, in the order of its material table (new ones last)"""
    found = []
    for o in model_col.all_objects:
        if o.type != 'MESH':
            continue
        for slot in o.material_slots:
            h = C.parse_mat_hash(slot.material.name) if slot.material else None
            if slot.material is not None and C.K_MAT_HASH in slot.material:
                try:
                    h = int(str(slot.material[C.K_MAT_HASH]), 16)
                except ValueError:
                    pass
            if h is not None and h not in found:
                found.append(h)
    order = [int(x, 16) for x in json.loads(model_col.get(C.K_MATERIALS, '[]'))]
    return [h for h in order if h in found] + [h for h in found if h not in order]


def model_visuals(model_col):
    """{hash: preview material} of the materials the meshes of a model use"""
    out = {}
    for o in model_col.all_objects:
        if o.type != 'MESH':
            continue
        for slot in o.material_slots:
            m = slot.material
            h = C.parse_mat_hash(m.name) if m else None
            if m is not None and C.K_MAT_HASH in m:
                try:
                    h = int(str(m[C.K_MAT_HASH]), 16)
                except ValueError:
                    pass
            if h is not None:
                out.setdefault(h, m)
    return out


def import_data(model_col, data, source, finder, pack=True, name=None, previews=True):
    """build the '<name>.mrl' collection below a model collection from .mrl bytes; the meshes' materials become the
    preview materials of the entries. A material of the meshes that the .mrl does not have gets no entry (like the MHW Model Editor,
    which only prints it; "Add Missing Materials" adds one on request). Returns (collection, textured entries, missing hashes)"""
    mrl = R.parse(data)
    old = mrl_collection_of(model_col)
    if old is not None and old is not model_col:
        remove_collection(old)
    parents = _parents(model_col) if model_col != bpy.context.scene.collection else []
    mrl_col = new_collection(parents[0] if parents else bpy.context.scene.collection,
                             name or (base_name(model_col) + '.mrl'), source, mrl)
    fill_collection(mrl_col, mrl)
    visuals = model_visuals(model_col)
    have = {int(o.re6_mrl_material.hash, 16): o for o in entries(mrl_col)}
    missing = [h for h in visuals if h not in have]
    done = 0
    for h, mat in visuals.items():
        obj = have.get(h)
        if obj is None:
            continue
        obj.re6_mrl_material.linkedMaterial = mat
        if previews and MT.build_visual(obj, finder, pack):
            done += 1
    return mrl_col, done, missing


def remove_collection(col):
    for o in list(col.all_objects):
        bpy.data.objects.remove(o, do_unlink=True)
    for c in list(col.children_recursive):
        bpy.data.collections.remove(c)
    bpy.data.collections.remove(col)


def apply_order(mrl_col, ordered):
    """number the objects 0, 1, 2 ... in the given order and set their names to the name of their material"""
    for i, o in enumerate(ordered):                 # two passes: a name that is taken would get a .001 suffix
        o.name = 'tmp_mrl_%d' % i
    for i, o in enumerate(ordered):
        o.name = C.mat_obj_name(i, o.re6_mrl_material.materialName)
        o.re6_mrl_material.index = i


def reindex(mrl_col):
    """reindexMaterials() of the MHW Model Editor: the name in the parentheses of an object name sets the material name
    (so a material can be renamed by renaming its object), then the objects are numbered in the order of their names"""
    ordered = entries(mrl_col)
    for o in ordered:
        label = C.mat_obj_label(o.name)
        if label and label != o.re6_mrl_material.materialName:
            o.re6_mrl_material.materialName = label
    apply_order(mrl_col, entries(mrl_col))


def free_hash(mrl_col):
    used = {o.re6_mrl_material.hash for o in entries(mrl_col)}
    while True:
        h = '%08x' % random.getrandbits(31)
        if h not in used:
            return h


# --- operators ----------------------------------------------------------------------------------------------

class _NeedsMrl:
    @classmethod
    def poll(cls, context):
        return find_mrl_collection(context) is not None


class RE6_OT_import_mrl(Operator, ImportHelper):
    """Import a .mrl material library as a collection with one empty per material"""
    bl_idname = 're6_mrl.import_re6_mrl'
    bl_label = 'Import RE6 MRL'
    bl_description = 'Import RE6 MRL Files'
    bl_options = {'PRESET', 'REGISTER', 'UNDO'}

    files: CollectionProperty(name='File Path', type=bpy.types.OperatorFileListElement)
    directory: StringProperty(subtype='DIR_PATH', options={'SKIP_SAVE'})
    filename_ext = '.mrl'
    filter_glob: StringProperty(default='*.mrl', options={'HIDDEN'})
    previews: BoolProperty(name='Build Preview Materials', default=False, options={'HIDDEN'},
                           description='Create a Blender material with textures for every entry (slow for big libraries; '
                                       'the entries of a model get theirs when the model is imported)')
    texture_dir: StringProperty(name='Texture Folder', default='', options={'HIDDEN'},
                                description='Extra folder with extracted .tex files (paste the path)')

    def invoke(self, context, event):
        if self.directory:                      # dropped into the 3D view
            return self.execute(context)
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        from .operators import print_banner
        print_banner()
        prefs.toggle_console()

        paths = [os.path.join(self.directory, f.name) for f in self.files] if self.files else [self.filepath]
        multi = len(paths) > 1
        has_errors = False
        for i, path in enumerate(paths):
            if multi:
                print('Multi MRL Import (%d / %d)' % (i + 1, len(paths)))
            if not os.path.isfile(path):
                has_errors = True
                print('\033[93mWARNING: Path does not exist, cannot import file.'
                      '\nIf you are importing multiple files at once, they must all be in the same directory.'
                      '\nInvalid Path: %s\033[0m' % path)
                continue
            try:
                self.import_file(context, path)
            except (OSError, R.MrlError) as e:
                has_errors = True
                print('\033[91mERROR: %s: %s\033[0m' % (os.path.basename(path), e))

        if not has_errors:
            prefs.toggle_console()
            if not multi:
                self.report({'INFO'}, rpt('Successfully imported RE6 MRL file.'))
            else:
                self.report({'INFO'}, rpt('Successfully imported %d RE6 MRL files.') % len(paths))
            return {'FINISHED'}
        if not multi:
            self.report({'INFO'}, rpt('Failed to import RE6 MRL file. Check Window > Toggle System Console for details.'))
        else:
            self.report({'INFO'}, rpt('Some RE6 MRL files failed to import. Check Window > Toggle System Console for details.'))
        return {'CANCELLED'}

    def import_file(self, context, path):
        from . import material_names
        material_names.learn_scene()
        with open(path, 'rb') as fh:
            mrl = R.parse(fh.read())
        name = os.path.splitext(os.path.basename(path))[0]
        # next to the model collection of the same name (inside its parent collection), else in the scene
        mod = bpy.data.collections.get(name + '.mod')
        parents = _parents(mod) if mod is not None else []
        col = new_collection(parents[0] if parents else context.scene.collection, name + '.mrl', path, mrl)
        fill_collection(col, mrl)
        tp = context.scene.re6_mrl_toolpanel
        tp.lastImportCollection = col.name
        tp.mrlCollection = col
        if mod is not None and C.is_mod(mod):
            tp.modCollection = mod
        if self.previews:
            finder = make_finder(col, self.texture_dir)
            for o in entries(col):
                MT.build_visual(o, finder, True)
        print('RE6: %d materials, %d textures <- %s' % (len(mrl.materials), len(mrl.textures), os.path.basename(path)))
        return col


class RE6_MRL_FH_drag_import(bpy.types.FileHandler):
    bl_idname = 'RE6_MRL_FH_drag_import'
    bl_label = 'File handler for RE6 MRL importing'
    bl_import_operator = RE6_OT_import_mrl.bl_idname
    bl_file_extensions = '.mrl'

    @classmethod
    def poll_drop(cls, context):
        return context.area and context.area.type == 'VIEW_3D'


class RE6_OT_mrl_select(Operator):
    """Make this material the active object"""
    bl_idname = 're6_mrl.select_material'
    bl_label = 'Select Material'
    bl_options = {'INTERNAL'}

    name: StringProperty()

    def execute(self, context):
        obj = bpy.data.objects.get(self.name)
        if obj is None:
            return {'CANCELLED'}
        for o in context.selected_objects:
            o.select_set(False)
        if obj.name in context.view_layer.objects:
            obj.select_set(True)
            context.view_layer.objects.active = obj
        return {'FINISHED'}


class RE6_OT_mrl_add(_NeedsMrl, Operator):
    """Add a material to the .mrl (a plain character material, or a copy of the active entry)"""
    bl_idname = 're6_mrl.add_material'
    bl_label = 'Add Material'
    bl_options = {'REGISTER', 'UNDO'}

    name: StringProperty(name='Material Name', default='',
                         description='The hash is computed from the name (jamcrc32, like the games do); used when the '
                                     'hash below is empty')
    hash: StringProperty(name='Material Hash', default='', description='8 hex digits; empty = computed from the name, or random')
    copy_active: BoolProperty(name='Copy Active Material', default=False)

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        col = find_mrl_collection(context)
        try:
            if self.hash.strip():
                h = int(self.hash, 16)
            elif self.name.strip():
                h = jamcrc32(self.name.strip())
            else:
                h = int(free_hash(col), 16)
        except ValueError:
            self.report({'ERROR'}, 'The hash must be 8 hex digits.')
            return {'CANCELLED'}
        if any(int(o.re6_mrl_material.hash, 16) == h for o in entries(col)):
            self.report({'ERROR'}, 'A material with this hash exists already.')
            return {'CANCELLED'}
        src = active_entry(context)
        if self.copy_active and src is not None:
            mm, binds = MT.core_material(src)
            mm.name = h
            obj = create_empty(col, mm, [(c.b, binds.get(c.b)) for c in mm.commands if c.type == R.CMD_TEXTURE],
                               len(entries(col)))
        else:
            obj = template_entry(col, h)
        if self.name.strip():
            obj[C.K_NAME] = self.name.strip()
            obj.name = C.mat_obj_name(obj.re6_mrl_material.index, obj.re6_mrl_material.materialName)
        self.report({'INFO'}, rpt('Added material %s.') % obj.name)
        return {'FINISHED'}


class RE6_OT_mrl_duplicate(Operator):
    """Duplicate the active material with a new hash"""
    bl_idname = 're6_mrl.duplicate_material'
    bl_label = 'Duplicate Material'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return active_entry(context) is not None

    def execute(self, context):
        src = active_entry(context)
        col = next((c for c in src.users_collection if C.is_mrl(c)), None)
        if col is None:
            return {'CANCELLED'}
        mm, binds = MT.core_material(src)
        mm.name = int(free_hash(col), 16)
        order = entries(col)
        obj = create_empty(col, mm, [(c.b, binds.get(c.b)) for c in mm.commands if c.type == R.CMD_TEXTURE],
                           len(order))
        order.insert(order.index(src) + 1, obj)
        apply_order(col, order)
        self.report({'INFO'}, rpt('Added material %s.') % obj.name)
        return {'FINISHED'}


class RE6_OT_mrl_delete(Operator):
    """Delete the selected materials from the .mrl (meshes that use them keep their Blender material)"""
    bl_idname = 're6_mrl.delete_material'
    bl_label = 'Delete Material'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return any(is_entry(o) for o in context.selected_objects)

    def execute(self, context):
        cols = set()
        n = 0
        for o in [o for o in context.selected_objects if is_entry(o)]:
            cols.update(c for c in o.users_collection if C.is_mrl(c))
            bpy.data.objects.remove(o, do_unlink=True)
            n += 1
        for c in cols:
            reindex(c)
        self.report({'INFO'}, rpt('Deleted %d material(s).') % n)
        return {'FINISHED'}


class RE6_OT_mrl_move(Operator):
    """Move the active material up or down in the .mrl"""
    bl_idname = 're6_mrl.move_material'
    bl_label = 'Move Material'
    bl_options = {'REGISTER', 'UNDO'}

    direction: EnumProperty(name='Direction', items=[('UP', 'Up', ''), ('DOWN', 'Down', '')], default='UP')

    @classmethod
    def poll(cls, context):
        return is_entry(context.object)

    def execute(self, context):
        obj = context.object
        col = next((c for c in obj.users_collection if C.is_mrl(c)), None)
        if col is None:
            return {'CANCELLED'}
        lst = entries(col)
        i = lst.index(obj)
        j = i - 1 if self.direction == 'UP' else i + 1
        if 0 <= j < len(lst):
            lst[i], lst[j] = lst[j], lst[i]
        apply_order(col, lst)
        return {'FINISHED'}


class RE6_OT_mrl_reindex(Operator):
    bl_idname = 're6_mrl.reindex_mrl_materials'
    bl_label = 'Reindex Mrl Materials'
    bl_description = ('Reorders the mrl material objects and sets their names to the name set in the custom properties.'
                      '\nThe button will only be triggered if active mrl collection exists')
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.scene.re6_mrl_toolpanel.mrlCollection is not None

    def execute(self, context):
        reindex(context.scene.re6_mrl_toolpanel.mrlCollection)
        self.report({'INFO'}, rpt('Reindexed mrl material objects.'))
        return {'FINISHED'}


class RE6_OT_mrl_add_missing(_NeedsMrl, Operator):
    """Add a plain character material for every material the meshes of the model use but the .mrl does not have"""
    bl_idname = 're6_mrl.add_missing_materials'
    bl_label = 'Add Missing Materials'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        col = find_mrl_collection(context)
        tp_mod = context.scene.re6_mrl_toolpanel.modCollection
        model = mod_collection_of(col) or (tp_mod if tp_mod is not None and C.is_mod(tp_mod) else None)
        if model is None:
            self.report({'ERROR'}, 'There is no model collection.')
            return {'CANCELLED'}
        have = {int(o.re6_mrl_material.hash, 16): o for o in entries(col)}
        visuals = model_visuals(model)
        n = 0
        for h in used_hashes(model):
            if h not in have:
                obj = template_entry(col, h)
                have[h] = obj
                n += 1
            if h in visuals and have[h].re6_mrl_material.linkedMaterial is None:
                have[h].re6_mrl_material.linkedMaterial = visuals[h]
            if h in visuals and not visuals[h].name.startswith(C.MAT_PREFIX) and not have[h].get(C.K_NAME):
                have[h][C.K_NAME] = visuals[h].name.rsplit('.', 1)[0] if visuals[h].name[-4:-3] == '.' else visuals[h].name
                have[h].name = C.mat_obj_name(have[h].re6_mrl_material.index, have[h].re6_mrl_material.materialName)
        unused = [o.name for o in entries(col) if int(o.re6_mrl_material.hash, 16) not in set(used_hashes(model))]
        self.report({'INFO'}, rpt('Added %d missing material(s); %d material(s) of the .mrl are not used by the model.')
                    % (n, len(unused)))
        return {'FINISHED'}


class RE6_OT_mrl_refresh(Operator):
    """Rebuild the preview material (textures) of the selected materials from their texture slots"""
    bl_idname = 're6_mrl.refresh_preview'
    bl_label = 'Refresh Preview'
    bl_options = {'REGISTER', 'UNDO'}

    texture_dir: StringProperty(name='Texture Folder', default='',
                                description='Extra folder with extracted .tex files (paste the path)')

    @classmethod
    def poll(cls, context):
        return active_entry(context) is not None

    def execute(self, context):
        objs = [o for o in context.selected_objects if is_entry(o)] or [active_entry(context)]
        n = 0
        for o in objs:
            col = next((c for c in o.users_collection if C.is_mrl(c)), None)
            finder = make_finder(col, self.texture_dir) if col is not None else MT.TextureFinder([], ())
            p = prefs.get()
            n += MT.build_visual(o, finder, p.pack_textures if p else True) > 0
        self.report({'INFO'}, rpt('Refreshed %d material preview(s).') % len(objs))
        return {'FINISHED'}


class RE6_OT_create_mrl_collection(Operator):
    """Create a mrl collection for putting mrl material objects into"""
    bl_idname = 're6_mrl.create_mrl_collection'
    bl_label = 'Create Mrl Collection'
    bl_description = 'Create a mrl collection for putting mrl material objects into'
    bl_options = {'UNDO'}

    collectionName: StringProperty(name='Mrl Name', default='pl0000',
                                   description='The name of the newly created mrl collection.\nUse the same name as the '
                                               'mrl file')

    def invoke(self, context, event):
        # the name of the last imported mod collection is the name that is preset
        name = context.scene.re6_mod_toolpanel.get('lastImportCollection')
        if name is not None and '.mod' in name:
            self.collectionName = name.split('.mod')[0]
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        name = self.collectionName.strip()
        if name != '':
            # the nested collection group of the mod, else a new one
            parent = bpy.data.collections.get(name)
            if parent is None:
                parent = bpy.data.collections.new(name)
                context.scene.collection.children.link(parent)
            col = new_collection(parent, name + '.mrl', '')
            context.scene.re6_mrl_toolpanel.mrlCollection = col
            self.report({'INFO'}, rpt('Created new mrl collection.'))
            return {'FINISHED'}
        self.report({'ERROR'}, rpt('Invalid mrl collection name.'))
        return {'CANCELLED'}


class RE6_OT_replace_string(Operator):
    """Replace certain specific string in the texture path"""
    bl_idname = 're6_mrl.replace_string'
    bl_label = 'Replace String'
    bl_description = 'Replace certain specific string in the texture path'
    bl_options = {'UNDO'}

    originalString: StringProperty(name='Original String', default='',
                                   description='The original string that needs to be replaced')
    replacedString: StringProperty(name='Replaced String', default='', description='The string after being replaced')

    @classmethod
    def poll(cls, context):
        return is_entry(context.active_object)

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        obj = context.active_object
        match = False
        if self.originalString != '':
            for item in obj.re6_mrl_material.mapList_items:
                if self.originalString not in item.value:
                    continue
                match = True
                item.value = item.value.replace(self.originalString, self.replacedString)
        if match:
            self.report({'INFO'}, rpt('Replaced string "%s" to "%s".') % (self.originalString, self.replacedString))
        else:
            self.report({'ERROR'}, rpt('Unable to match the string "%s".') % self.originalString)
        return {'FINISHED'}


CLASSES = (RE6_OT_import_mrl, RE6_OT_mrl_select, RE6_OT_mrl_add, RE6_OT_mrl_duplicate, RE6_OT_mrl_delete,
           RE6_OT_mrl_move, RE6_OT_mrl_reindex, RE6_OT_mrl_add_missing, RE6_OT_mrl_refresh,
           RE6_OT_create_mrl_collection, RE6_OT_replace_string, RE6_MRL_FH_drag_import)


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
