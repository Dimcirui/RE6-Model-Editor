# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 Dimcirui

"""Shader Features sub panel: change the option of a shader switch of an MRL material; the texture slots, sampler states,
UV / channel switches and constant buffers the option needs are added or removed (core/mrl_features.py)."""
import json
import struct

import bpy
from bpy.props import StringProperty
from bpy.types import Operator

from ..core import mrl as R
from ..core import mrl_features as F
from ..core.shader_names import name_of
from . import materials as MT
from . import mrl_objects as MO
from .i18n import iface, rpt


def entry_commands(obj):
    """[(type, a, b)] of the commands of an MRL empty (from its stored command block)"""
    try:
        d = json.loads(obj[MT.K_DATA])
        block = bytes.fromhex(d['block'])
        cmds = [struct.unpack_from('<III', block, k * R.CMD_SIZE) for k in range(d['ncmd'])]
        return [(h & 0xF, a, b) for h, a, b in cmds]
    except (KeyError, ValueError, struct.error):
        return []


def switch_label(sw):
    return name_of(sw) or '%08x' % sw


def option_label(sw, a):
    if F.is_default(sw, a):
        return iface('Default')
    return name_of(a) or '#%05x' % (a >> 12)


def _cmd_name(k):
    return name_of(k[1]) or '%08x' % k[1]


def _option_tip(context, sw, a):
    """tooltip of a menu option: how many retail materials use it and the commands choosing it adds / removes"""
    n = dict(F.option_list(sw)).get(a, 0)
    tip = '%s: %d' % (iface('retail materials'), n)
    try:
        cur, _ = MT.core_material(MO.active_entry(context))
        add, rem = F.changes(cur, F.set_option(cur, sw, a))
    except Exception:            # noqa: BLE001  (a broken entry only loses the +/- preview)
        return tip
    add = [_cmd_name(k) for k in add if k[0] != R.CMD_SAMPLER]
    rem = [_cmd_name(k) for k in rem if k[0] != R.CMD_SAMPLER]
    if add:
        tip += '\n+ ' + ', '.join(add)
    if rem:
        tip += '\n- ' + ', '.join(rem)
    return tip


class RE6_OT_mrl_set_feature(Operator):
    bl_idname = 're6_mrl.set_feature'
    bl_label = 'Set Shader Feature'
    bl_description = ('Choose the option of this shader switch. The texture slots, sampler states, UV / channel switches '
                      'and constant buffers the option needs are added (empty / retail defaults) or removed')
    bl_options = {'REGISTER', 'UNDO'}

    switch: StringProperty(options={'HIDDEN'})
    option: StringProperty(options={'HIDDEN'})

    @classmethod
    def poll(cls, context):
        return MO.active_entry(context) is not None

    @classmethod
    def description(cls, context, props):
        try:
            return _option_tip(context, int(props.switch, 16), int(props.option, 16))
        except ValueError:
            return cls.bl_description

    def execute(self, context):
        obj = MO.active_entry(context)
        try:
            sw, opt = int(self.switch, 16), int(self.option, 16)
            mm, binds = MT.core_material(obj)
            new = F.set_option(mm, sw, opt)
        except ValueError as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}
        p = obj.re6_mrl_material
        bindings = [(c.b, binds.get(c.b)) for c in new.commands if c.type == R.CMD_TEXTURE]
        MT.store_material(obj, new, index=p.index, bindings=bindings)
        add, rem = F.changes(mm, new)
        msg = rpt('%s = %s') % (switch_label(sw), option_label(sw, opt))
        if add:
            msg += '; ' + rpt('added: %s') % ', '.join(_cmd_name(k) for k in add)
        if rem:
            msg += '; ' + rpt('removed: %s') % ', '.join(_cmd_name(k) for k in rem)
        unused = F.unused_options(new)
        if unused:
            self.report({'WARNING'}, msg + '. ' + rpt('No retail material uses %s (allowed by the shader package, '
                                                      'unverified in game)') % ', '.join(option_label(*x) for x in unused))
        elif not F.is_known_combo(new):
            self.report({'WARNING'}, msg + '. ' + rpt('This switch combination is not used by any retail material '
                                                      '(unverified in game)'))
        else:
            self.report({'INFO'}, msg)
        for area in context.screen.areas:
            area.tag_redraw()
        return {'FINISHED'}


class RE6_MT_mrl_feature_options(bpy.types.Menu):
    """the options of one shader switch (the switch comes from the layout context string re6_mrl_switch)"""
    bl_idname = 'RE6_MT_mrl_feature_options'
    bl_label = 'Shader Feature'

    def draw(self, context):
        lay = self.layout
        try:
            sw = int(getattr(context, 're6_mrl_switch', ''), 16)
        except ValueError:
            lay.label(text='-')
            return
        cur = {b: a for t, a, b in entry_commands(MO.active_entry(context)) if t == R.CMD_STATE}.get(sw)
        for a, n in F.option_list(sw):
            text = option_label(sw, a)
            if not n:
                text += '  (%s)' % iface('not used in retail')
            op = lay.operator(RE6_OT_mrl_set_feature.bl_idname, text=text,
                              icon='CHECKMARK' if a == cur else 'BLANK1')
            op.switch = '%08x' % sw
            op.option = '%08x' % a


def _switch_row(col, sw, a):
    """label | dropdown; a switch with only two options (the default and one other) is a checkbox named after the
    other option"""
    split = col.split(factor=0.45, align=True)
    left = split.row()
    left.alignment = 'RIGHT'
    opts = [o for o, _ in F.option_list(sw)]
    if len(opts) == 2 and any(F.is_default(sw, o) for o in opts):
        other = next(o for o in opts if not F.is_default(sw, o))
        on = a == other
        left.label(text='')
        right = split.row()
        right.alignment = 'LEFT'
        op = right.operator(RE6_OT_mrl_set_feature.bl_idname, text=option_label(sw, other), emboss=False,
                            icon='CHECKBOX_HLT' if on else 'CHECKBOX_DEHLT')
        op.switch = '%08x' % sw
        op.option = '%08x' % (sw if on else other)
        return
    left.label(text=switch_label(sw))
    right = split.row()
    right.context_string_set('re6_mrl_switch', '%08x' % sw)
    right.menu(RE6_MT_mrl_feature_options.bl_idname, text=option_label(sw, a))


def draw_features(lay, obj):
    """one row per shader switch that has more than one option in the game: main features first, then the UV / channel /
    displacement sub switches"""
    from .panels import _indented
    col = _indented(lay)
    try:
        shader = int(obj.re6_mrl_material.shader, 16)
    except ValueError:
        shader = 0
    if shader != F.MATERIAL_STD:
        col.label(text=iface('Only nDraw::MaterialStd materials have shader features'), icon='INFO')
        return
    switches = [(b, a) for t, a, b in entry_commands(obj) if t == R.CMD_STATE and len(F.option_list(b)) > 1]
    opts = {b: a for t, a, b in entry_commands(obj) if t == R.CMD_STATE}
    unused = [(b, a) for b, a in opts.items() if a not in dict(F._data().OPTIONS.get(b, ()))]
    if unused:
        box = col.box()
        box.label(text=iface('Options no retail material uses (unverified in game):'), icon='ERROR')
        for b, a in unused:
            box.label(text='    %s = %s' % (switch_label(b), option_label(b, a)))
    elif F.combo_hash(opts) not in F._data().COMBOS:
        box = col.box()
        box.label(text=iface('Combination not used by any retail material (unverified in game)'), icon='ERROR')
    main = [(b, a) for b, a in switches if F.is_main(b, switch_label(b))]
    sub = [(b, a) for b, a in switches if not F.is_main(b, switch_label(b))]
    for b, a in main:
        _switch_row(col, b, a)
    if sub:
        col.separator()
        col.label(text=iface('UV / Channel / Displacement'))
        for b, a in sub:
            _switch_row(col, b, a)


CLASSES = (RE6_OT_mrl_set_feature, RE6_MT_mrl_feature_options)


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
