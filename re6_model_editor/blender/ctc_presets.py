# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 Dimcirui

"""Chain presets: the properties of a chain object saved as a .json file and applied to other chains
(ctc_presets.py of the MHW Model Editor). The presets live in the Blender config folder.

The chain presets of the MHW Model Editor (presetType CTC_CHAIN, same units: gravity in centimetres, limit force x 100) can be
applied as well: they are listed from its ChainPresets folder when that add-on is installed, and a copy of such a file in our
folder works too. Keys RE6 does not have (WindRate, WindLimit, the flag booleans) are ignored, keys the file does not have
(unknFloat) keep the value of the chain."""
import json
import os
import re

import bpy
from bpy.props import StringProperty
from bpy.types import Operator

from . import common as C
from . import ctc_properties as CP
from .i18n import iface, rpt

PRESET_TYPE = 'RE6_CTC_CHAIN'
MHW_PRESET_TYPE = 'CTC_CHAIN'                 # chain presets of the MHW Model Editor
MHW_PREFIX = 'MHW/'                           # enum id prefix of the presets listed from the MHW Model Editor's folder
PRESET_VERSION = 1
FOLDER = 'ChainPresets'
_preset_list = []


def preset_dir(create=False):
    return bpy.utils.user_resource('CONFIG', path=os.path.join('re6_model_editor', FOLDER), create=create)


def mhw_preset_dir():
    """the ChainPresets folder of an installed MHW Model Editor, or None"""
    import addon_utils
    for mod in addon_utils.modules():
        if 'mhw_model_editor' not in mod.__name__.lower():
            continue
        root = os.path.dirname(mod.__file__)
        for base, dirs, _files in os.walk(root):
            if os.path.basename(base) == 'ChainPresets' and os.path.basename(os.path.dirname(base)) == 'ctc':
                return base
    return None


def _json_files(path):
    if not path or not os.path.isdir(path):
        return []
    return [e.name for e in sorted(os.scandir(path), key=lambda e: e.name.lower()) if e.name.endswith('.json') and e.is_file()]


def preset_items(self, context):
    _preset_list.clear()
    for name in _json_files(preset_dir()):
        _preset_list.append((name, os.path.splitext(name)[0], ''))
    mhw = mhw_preset_dir()
    for name in _json_files(mhw):
        _preset_list.append((MHW_PREFIX + name, '%s (MHW)' % os.path.splitext(name)[0],
                             iface('Chain preset of the MHW Model Editor') + ': ' + os.path.join(mhw, name)))
    return _preset_list


def preset_path(value):
    """the file of an enum id of preset_items()"""
    if value.startswith(MHW_PREFIX):
        return os.path.join(mhw_preset_dir() or '', value[len(MHW_PREFIX):])
    return os.path.join(preset_dir(), value)


def valid_name(name):
    if not name or re.search(r'^[\w,\s-]+\.[A-Za-z]{3}$', name) or '..' in name:
        return False
    return not any(c in name for c in '/\\:*?"<>|')


def chain_preset(obj):
    pg = obj.re6_ctc_chain
    out = {'presetType': PRESET_TYPE, 'presetVersion': PRESET_VERSION}
    for k in CP.CHAIN_KEYS:
        v = getattr(pg, k)
        if k == 'Gravity':
            v = [round(x * 100.0, 4) for x in v]          # centimetres, like the file
        elif k == 'LimitForce':
            v = round(v * 100.0, 4)
        out[k] = v
    return out


def save_as_preset(obj, name):
    if obj is None or obj.get(C.TYPE) != C.T_CTC_CHAIN:
        C.show_error_message_box(iface('Must select a ctc chain object (named with "CTC_CHAIN_XX...") to save preset.'))
        return False
    if not valid_name(name):
        C.show_error_message_box(iface('Invalid preset file name.'))
        return False
    path = os.path.join(preset_dir(create=True), name + '.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(chain_preset(obj), f, ensure_ascii=False, indent=4)
    print('\033[92m%s%s\033[0m' % (iface('Saved chain preset to '), path))
    return True


def read_preset(filepath, obj):
    """apply a preset to a chain object; True when it was applied"""
    try:
        with open(filepath, encoding='utf-8') as f:
            data = json.load(f)
    except Exception as err:       # noqa
        C.show_error_message_box(iface('Failed to read json file.') + ' \n' + str(err))
        return False
    kind = data.get('presetType') if isinstance(data, dict) else None
    if kind not in (PRESET_TYPE, MHW_PRESET_TYPE):
        C.show_error_message_box(iface('Preset type is not supported.'))
        return False
    print(iface('Applying preset to ') + obj.name)
    pg = obj.re6_ctc_chain
    for k in CP.CHAIN_KEYS:
        if k not in data:
            if kind == PRESET_TYPE:            # an MHW preset never has the RE6 only keys, that is not worth a warning
                print('\033[93mWARNING: Preset is missing key %s, cannot set value on active object.\033[0m' % k)
            continue
        v = data[k]
        if k == 'Gravity':
            v = [x / 100.0 for x in v]
        elif k == 'LimitForce':
            v = v / 100.0
        setattr(pg, k, v)
    return True


class RE6_OT_save_chain_preset(Operator):
    bl_label = 'Save Selected As Preset'
    bl_idname = 're6_ctc.save_selected_as_preset'
    bl_description = ('Save selected ctc chain object as a preset for easy reuse and sharing.'
                      '\nThe button will only be triggered if a ctc object is activated.'
                      '\nPresets can be accessed using the "Open Preset Folder" button')
    presetName: StringProperty(name='Preset Name', default='newPreset')

    @classmethod
    def poll(cls, context):
        return context.active_object is not None and context.active_object.get(C.TYPE) == C.T_CTC_CHAIN

    def execute(self, context):
        if save_as_preset(context.active_object, self.presetName):
            self.report({'INFO'}, rpt('Saved ctc chain preset.'))
            return {'FINISHED'}
        return {'CANCELLED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)


class RE6_OT_open_chain_preset_folder(Operator):
    bl_label = 'Open Preset Folder'
    bl_idname = 're6_ctc.open_preset_folder'
    bl_description = 'Open the preset folder in File Explorer'

    def execute(self, context):
        bpy.ops.wm.path_open(filepath=preset_dir(create=True))
        return {'FINISHED'}


class RE6_OT_apply_chain_preset(Operator):
    bl_label = 'Apply CTC Chain Preset'
    bl_idname = 're6_ctc.apply_ctc_chain_preset'
    bl_description = 'Apply preset to selected ctc chain objects'
    bl_options = {'UNDO', 'INTERNAL'}

    def execute(self, context):
        value = context.scene.re6_ctc_toolpanel.CTCChainPresets
        if value == '':
            C.show_error_message_box(iface('There are currently no presets that can be applied.'))
            return {'CANCELLED'}
        chains = [o for o in context.selected_objects if o.get(C.TYPE) == C.T_CTC_CHAIN]
        if not chains:
            C.show_error_message_box(iface('Must select a ctc chain object (named with "CTC_CHAIN_XX...") to apply preset.'))
            return {'CANCELLED'}
        done = all([read_preset(preset_path(value), o) for o in chains])
        if done:
            self.report({'INFO'}, rpt('Applied ctc chain preset.'))
            return {'FINISHED'}
        return {'CANCELLED'}


CLASSES = (RE6_OT_save_chain_preset, RE6_OT_open_chain_preset_folder, RE6_OT_apply_chain_preset)


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
