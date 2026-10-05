# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 Dimcirui

"""Copy / paste of one sub panel of an MRL material (Flags, Shader Features, Map / Property / Sampler List).

The clipboard holds named values, so that it can paste between materials of different layouts: a target gets the values
whose name (flag, shader switch, texture slot, constant buffer + property, sampler slot) it has itself; the others are
dropped, and the target's values the clipboard does not have are left alone. It is kept in the scene (a JSON string), so
it survives an add-on reload and is saved with the .blend file."""
import json

import bpy
from bpy.props import EnumProperty
from bpy.types import Operator

from ..core import mrl as R
from ..core import mrl_features as F
from . import common as C
from . import materials as MT
from . import mrl_objects as MO
from . import props as P
from .i18n import iface, rpt

K_CLIP = 're6_mrl_clipboard'

SECTIONS = [('flags', 'Flags', ''), ('features', 'Shader Features', ''), ('maplist', 'Map List', ''),
            ('proplist', 'Property List', ''), ('samplerlist', 'Sampler List', '')]
SECTION_LABEL = {k: n for k, n, _ in SECTIONS}


def clipboard(scene) -> dict:
    try:
        return json.loads(scene.get(K_CLIP, '{}'))
    except ValueError:
        return {}


def has_clip(scene, section) -> bool:
    return section in clipboard(scene)


# --- copy: {name: value} of a section ------------------------------------------------------------------------------------

def _copy_flags(obj):
    p = obj.re6_mrl_material
    d = {k: int(getattr(p, k)) for k in R.FIELDS}
    d.update(blend=p.blend, depth=p.depth, raster=p.raster)
    return d


def _copy_features(obj):
    if not _is_std(obj):
        return None
    mm, _ = MT.core_material(obj)
    return {'%08x' % sw: '%08x' % a for sw, a in F.options(mm).items()}


def _copy_maps(obj):
    return {it.code: it.value for it in obj.re6_mrl_material.mapList_items}


def _copy_props(obj):
    return {blk.code: {it.prop_name: list(MT.get_floats(it)) for it in blk.propertyList_items}
            for blk in obj.re6_mrl_material.propertyBlock_items}


def _copy_samplers(obj):
    return {it.code: it.value for it in obj.re6_mrl_material.samplerList_items}


# --- paste: (pasted, of the clipboard) ------------------------------------------------------------------------------------

def _paste_flags(obj, d):
    p = obj.re6_mrl_material
    n = 0
    for k in R.FIELDS:
        if k in d:
            setattr(p, k, bool(d[k]) if isinstance(getattr(p, k), bool) else d[k])
            n += 1
    if 'blend' in d:
        p.blend_mode = P.mode_of(P.BLEND_MODES, d['blend'])
        p.blend = d['blend']
        n += 1
    if 'depth' in d:
        p.depth_mode = P.mode_of(P.DEPTH_MODES, d['depth'])
        p.depth = d['depth']
        n += 1
    if 'raster' in d:
        p.raster = d['raster']
        p.raster_mode = P.mode_of(P.RASTER_MODES, d['raster'])      # also sets the backface culling of the preview
        n += 1
    return n, len(d)


def _paste_features(obj, d):
    """set the options of the switches the target has; repeated, because an option can bring in the sub switches (UV /
    channel) that the clipboard has values for"""
    if not _is_std(obj):
        return 0, len(d)
    mm, binds = MT.core_material(obj)
    want = {int(k, 16): int(v, 16) for k, v in d.items()}
    done = set()
    for _ in range(4):
        changed = False
        for sw, a in want.items():
            cur = F.options(mm)
            if sw not in cur or a not in dict(F.option_list(sw)):
                continue
            done.add(sw)
            if cur[sw] != a:
                mm = F.set_option(mm, sw, a)
                changed = True
        if not changed:
            break
    p = obj.re6_mrl_material
    bindings = [(c.b, binds.get(c.b)) for c in mm.commands if c.type == R.CMD_TEXTURE]
    MT.store_material(obj, mm, index=p.index, bindings=bindings)
    return len(done), len(d)


def _paste_maps(obj, d):
    n = 0
    for it in obj.re6_mrl_material.mapList_items:
        if it.code in d:
            it.value = d[it.code]
            n += 1
    return n, len(d)


def _paste_props(obj, d):
    n = 0
    for blk in obj.re6_mrl_material.propertyBlock_items:
        vals = d.get(blk.code, {})
        for it in blk.propertyList_items:
            v = vals.get(it.prop_name)
            if v is not None and len(v) == len(MT.get_floats(it)):
                MT.set_floats(it, v)
                n += 1
    return n, sum(len(v) for v in d.values())


def _paste_samplers(obj, d):
    n = 0
    for it in obj.re6_mrl_material.samplerList_items:
        if it.code in d:
            it.value = d[it.code]
            n += 1
    return n, len(d)


COPY = {'flags': _copy_flags, 'features': _copy_features, 'maplist': _copy_maps, 'proplist': _copy_props,
        'samplerlist': _copy_samplers}
PASTE = {'flags': _paste_flags, 'features': _paste_features, 'maplist': _paste_maps, 'proplist': _paste_props,
         'samplerlist': _paste_samplers}


def _is_std(obj):
    try:
        return int(obj.re6_mrl_material.shader, 16) == F.MATERIAL_STD
    except ValueError:
        return False


def _targets(context):
    """the active MRL material and the other selected MRL material empties"""
    act = MO.active_entry(context)
    out = [act] if act is not None else []
    for o in context.selected_objects:
        if o not in out and MO.is_entry(o) and o.get(C.TYPE) == C.T_MAT:
            out.append(o)
    return out


class RE6_OT_mrl_copy_section(Operator):
    bl_idname = 're6_mrl.copy_section'
    bl_label = 'Copy'
    bl_description = 'Copy the values of this panel of the active MRL material to the clipboard'
    bl_options = {'REGISTER'}

    section: EnumProperty(items=SECTIONS, options={'HIDDEN'})

    @classmethod
    def poll(cls, context):
        return MO.active_entry(context) is not None

    def execute(self, context):
        obj = MO.active_entry(context)
        try:
            data = COPY[self.section](obj)
        except (ValueError, KeyError) as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}
        if data is None:
            self.report({'ERROR'}, rpt('Only nDraw::MaterialStd materials have shader features'))
            return {'CANCELLED'}
        clip = clipboard(context.scene)
        clip[self.section] = data
        context.scene[K_CLIP] = json.dumps(clip)
        self.report({'INFO'}, rpt('Copied %s of %s') % (iface(SECTION_LABEL[self.section]), obj.name))
        return {'FINISHED'}


class RE6_OT_mrl_paste_section(Operator):
    bl_idname = 're6_mrl.paste_section'
    bl_label = 'Paste'
    bl_description = ('Paste the clipboard into this panel of the active MRL material (and of the other selected MRL '
                      'materials). Only the values whose name the material also has are pasted')
    bl_options = {'REGISTER', 'UNDO'}

    section: EnumProperty(items=SECTIONS, options={'HIDDEN'})

    @classmethod
    def poll(cls, context):
        return MO.active_entry(context) is not None

    def execute(self, context):
        d = clipboard(context.scene).get(self.section)
        if d is None:
            self.report({'ERROR'}, rpt('The clipboard has no %s') % iface(SECTION_LABEL[self.section]))
            return {'CANCELLED'}
        res = []
        for obj in _targets(context):
            try:
                n, total = PASTE[self.section](obj, d)
            except (ValueError, KeyError) as e:
                self.report({'ERROR'}, '%s: %s' % (obj.name, e))
                return {'CANCELLED'}
            res.append('%s %d/%d' % (obj.name, n, total))
        for area in context.screen.areas:
            area.tag_redraw()
        self.report({'INFO'}, rpt('Pasted %s (same name values / clipboard): %s') % (
            iface(SECTION_LABEL[self.section]), ', '.join(res)))
        return {'FINISHED'}


def draw_header_buttons(lay, context, section):
    row = lay.row(align=True)
    row.operator(RE6_OT_mrl_copy_section.bl_idname, text='', icon='COPYDOWN').section = section
    sub = row.row(align=True)
    sub.enabled = has_clip(context.scene, section)
    sub.operator(RE6_OT_mrl_paste_section.bl_idname, text='', icon='PASTEDOWN').section = section


CLASSES = (RE6_OT_mrl_copy_section, RE6_OT_mrl_paste_section)


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
