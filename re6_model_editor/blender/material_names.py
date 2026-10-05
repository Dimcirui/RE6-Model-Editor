# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 Dimcirui

"""Material names for the hashes of .mod / .mrl files.

The MHW Model Editor resolves the name hashes of an .mrl3 with the material names stored in the .mod3 (jamcrc32 of every name),
then with a big dictionary, else shows "Unknown Hash". A RE6 .mod stores only the hashes, so the editor keeps the names itself:

* the names used in Blender (mesh objects Group_0_Sub_0__<name>, Blender materials, the Material Name of .mrl materials) are
  learned before every import, so a file with those hashes comes in with names (the "search the scene" TODO of MHWME);
* every name that is learned, exported or typed in is kept in config/re6_model_editor/material_names.json, so it resolves in
  later sessions too (the role of the .mod3 name table);
* renaming a material in the Mrl panel renames the meshes and preview materials of the same model that use it, so the .mod and
  the .mrl keep pointing at the same hash; Resolve Material Names replaces MAT_<hash> everywhere a name is known now.
"""
import json
import os
import re

import bpy
from bpy.types import Operator

from ..core import hashes as H
from . import common as C
from .i18n import rpt

FILE = 'material_names.json'
_SUFFIX = re.compile(r'^(.*__)(.+?)(\.\d{3})?$')        # Group_0_Sub_0__<name>(.001)


def _file(create=False):
    folder = bpy.utils.user_resource('CONFIG', path='re6_model_editor', create=create)
    return os.path.join(folder, FILE) if folder else None


def _plain(name):
    """a name without Blender's .001 suffix; '' for MAT_<hash> and empty names"""
    name = re.sub(r'\.\d{3}$', '', (name or '').strip())
    return '' if not name or C.parse_mat_hash(name) is not None else name


def load():
    """read the dictionary of the user into core.hashes.LEARNED"""
    path = _file()
    if not path or not os.path.isfile(path):
        return 0
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        print('\033[93mWARNING: cannot read %s: %s\033[0m' % (path, e))
        return 0
    n = 0
    for name in data.values() if isinstance(data, dict) else ():
        if isinstance(name, str) and H.learn(name) is not None:
            n += 1
    return n


def save():
    path = _file(create=True)
    if not path:
        return
    data = {'%08x' % h: n for h, n in sorted(H.LEARNED.items())}
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def remember(names):
    """learn names (the hash of each is jamcrc32(name)) and keep the new ones in the dictionary file; returns how many are new"""
    new = 0
    for name in names:
        name = _plain(name)
        if not name:
            continue
        try:
            h = H.jamcrc32(name)
        except UnicodeError as e:
            print('\033[93mWARNING: cannot hash the material name %r, skipped: %s\033[0m' % (name, e))
            continue
        if H.material_name(h) != name:
            H.learn(name)
            new += 1
    if new:
        try:
            save()
        except OSError as e:
            print('\033[93mWARNING: cannot write the material name dictionary: %s\033[0m' % e)
    return new


def mesh_suffix(obj):
    """the <name> of an object called Group_0_Sub_0__<name>, '' when it has none"""
    m = _SUFFIX.match(obj.name)
    return m.group(2) if m else ''


def scene_names():
    """the material names used in the open .blend"""
    out = set()
    for col in C.mod_collections():
        for o in col.all_objects:
            if o.type == 'MESH':
                out.add(mesh_suffix(o))
                out.update(s.material.name for s in o.material_slots if s.material is not None)
    for o in bpy.data.objects:
        if o.get(C.TYPE) == C.T_MAT and o.get(C.K_NAME):
            out.add(o[C.K_NAME])
    return {n for n in (_plain(x) for x in out) if n}


def learn_scene():
    """before an import: the names of the scene resolve the hashes of the new file"""
    return remember(scene_names())


def _material_hash(mat):
    if C.K_MAT_HASH in mat:
        try:
            return int(str(mat[C.K_MAT_HASH]), 16)
        except ValueError:
            pass
    h = C.parse_mat_hash(mat.name)
    return h if h is not None else (H.jamcrc32(_plain(mat.name)) if _plain(mat.name) else None)


def _mesh_hash(obj):
    s = mesh_suffix(obj)
    if not s:
        return None
    h = C.parse_mat_hash(s)
    return h if h is not None else H.jamcrc32(s)


def _rename_mesh(obj, name):
    m = _SUFFIX.match(obj.name)
    if m:
        obj.name = m.group(1) + name


def _rename_material(mat, name, h):
    mat.name = name
    mat[C.K_MAT_HASH] = '%08x' % h


def relink(old_hash, name, model_cols=None):
    """a material of hash old_hash is now called `name` (hash jamcrc32(name), or the hash of a MAT_<hash> name): rename the
    meshes that use it (their name suffix decides the material on export) and the preview materials, in the given model
    collections (all when None)"""
    new_hash = C.parse_mat_hash(name) if C.parse_mat_hash(name) is not None else H.jamcrc32(name)
    cols = model_cols if model_cols is not None else C.mod_collections()
    meshes = mats = 0
    seen = set()
    for col in cols:
        for o in col.all_objects:
            if o.type != 'MESH':
                continue
            if _mesh_hash(o) == old_hash:
                _rename_mesh(o, name)
                meshes += 1
            for slot in o.material_slots:
                m = slot.material
                if m is not None and m.name not in seen and _material_hash(m) == old_hash:
                    seen.add(m.name)
                    _rename_material(m, name, new_hash)
                    mats += 1
    return meshes, mats


def resolve_scene():
    """replace MAT_<hash> by the name wherever the hash resolves now: mesh names, preview materials, .mrl materials"""
    meshes = mats = entries = 0
    for col in C.mod_collections():
        for o in col.all_objects:
            if o.type == 'MESH':
                s = mesh_suffix(o)
                h = C.parse_mat_hash(s) if s else None
                if h is not None and H.material_name(h):
                    _rename_mesh(o, H.material_name(h))
                    meshes += 1
    for m in bpy.data.materials:
        h = C.parse_mat_hash(m.name)
        if h is not None and C.K_MAT_HASH in m and H.material_name(h):
            m.name = H.material_name(h)
            mats += 1
    for o in bpy.data.objects:
        if o.get(C.TYPE) == C.T_MAT and not o.get(C.K_NAME):
            try:
                h = int(o.re6_mrl_material.hash, 16)
            except ValueError:
                continue
            if H.material_name(h):
                o[C.K_NAME] = H.material_name(h)
                num = C.mat_obj_number(o.name)
                o.name = C.mat_obj_name(num if num is not None else o.re6_mrl_material.index, H.material_name(h))
                entries += 1
    return meshes, mats, entries


class RE6_OT_resolve_material_names(Operator):
    bl_idname = 're6_mrl.resolve_material_names'
    bl_label = 'Resolve Material Names'
    bl_description = ('Learn the material names used in this file and replace MAT_<hash> by the name wherever the hash is '
                      'known now: mesh names, preview materials and mrl materials.\nKnown names are kept in '
                      'material_names.json in the Blender config folder, so they resolve in later imports too')
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        new = learn_scene()
        meshes, mats, entries = resolve_scene()
        self.report({'INFO'}, rpt('Learned %d new name(s); renamed %d mesh(es), %d material(s), %d mrl material(s).')
                    % (new, meshes, mats, entries))
        return {'FINISHED'}


CLASSES = (RE6_OT_resolve_material_names,)


def register():
    n = load()
    if n:
        print('RE6: %d material name(s) loaded from %s' % (n, _file()))
    for c in CLASSES:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
