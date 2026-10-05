# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 Dimcirui

"""Renaming the bones of a mod armature with everything that depends on the name.

Setting `Bone.name` alone leaves several things behind that the importer / exporter read back:
  * (the function id needs nothing: it is the number in the name, for the exporter and for the .ctc / .ccl importers alike)
  * the vertex groups of the meshes the armature deforms (the exporter finds the bones by their names)
  * `Mod_Bone_Symmetry`: the *name* of the mirror bone
  * the names of chain / node / collision objects, which carry the bone names
Constraints of other objects follow a rename by themselves (checked by tools/blender_bone_rename_test.py).
"""
import re

import bpy

from . import common as C

TMP = '__tmp_'
_NAME = re.compile(r'RE6Bone_\d{3}')


def skinned_meshes(arm):
    """the meshes a vertex group of which is a bone weight of `arm`"""
    return [o for o in bpy.data.objects if o.type == 'MESH' and (o.parent == arm or any(m.type == 'ARMATURE' and m.object == arm for m in o.modifiers))]


def check_plan(arm, final):
    """list of problems of a rename plan {old: new} (empty = fine)"""
    names = {b.name for b in arm.data.bones}
    changes = {o: n for o, n in final.items() if o != n}
    out = [('missing', o) for o in changes if o not in names]
    targets = list(changes.values())
    out += [('duplicate', n) for n in set(targets) if targets.count(n) > 1]
    out += [('taken', n) for n in targets if n in names and n not in changes]
    return out


def rename_bones(arm, final):
    """rename the bones of `arm` as {old name: new name} in one go (swaps and cycles are fine) and keep everything that depends on
    the names in step. Returns the number of renamed bones; raises ValueError when the plan is not consistent."""
    problems = check_plan(arm, final)
    if problems:
        raise ValueError('inconsistent rename plan: %s' % problems[:5])
    changes = {o: n for o, n in final.items() if o != n}
    if not changes:
        return 0
    bones = arm.data.bones
    meshes = skinned_meshes(arm)
    for old in changes:                                           # phase 1: out of the way, so no name is ever taken twice
        bones[old].name = TMP + old
        for o in meshes:
            vg = o.vertex_groups.get(old)
            if vg is not None:
                vg.name = TMP + old
    for old, new in changes.items():                              # phase 2: the final names
        b = bones[TMP + old]
        b.name = new
        for o in meshes:
            vg = o.vertex_groups.get(TMP + old)
            if vg is not None:
                vg.name = new
    for b in bones:                                               # the stored mirror bone names
        m = b.get(C.K_MIRROR, '')
        if m and m in changes:
            b[C.K_MIRROR] = changes[m]
    typed = (C.T_CTC_CHAIN, C.T_CTC_NODE, C.T_CTC_FRAME, C.T_CTC_HELPER, C.T_CCL_SPHERE, C.T_CCL_CAPSULE, C.T_CCL_START, C.T_CCL_END)
    for o in bpy.data.objects:                                    # chain / node / collision objects carry bone names
        if o.get(C.TYPE) in typed and _NAME.search(o.name):
            new_name = _NAME.sub(lambda m: changes.get(m.group(0), m.group(0)), o.name)
            if new_name != o.name:
                o.name = new_name
    for o in bpy.data.objects:                                    # a constraint that still points at a temporary name
        for c in o.constraints:
            st = getattr(c, 'subtarget', '')
            if getattr(c, 'target', None) == arm and st.startswith(TMP) and st[len(TMP):] in changes:
                c.subtarget = changes[st[len(TMP):]]
    return len(changes)
