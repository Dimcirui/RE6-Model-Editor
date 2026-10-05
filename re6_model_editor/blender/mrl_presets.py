# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 Dimcirui

"""Material presets: a material object of an MRL collection saved as a .json file and added again later
(mrl3_presets.py and the preset operators of the MHW Model Editor).

The presets live in the Blender config folder (not in the add-on folder, an update of the add-on would delete them).
A preset holds everything that is needed to write the material again: the header (shader, states, flag words), the Map List,
the Sampler List, the Property List and the command block with the constant buffers it was read from.
"""
import json
import os
import re

import bpy
from bpy.props import StringProperty
from bpy.types import Operator

from ..core import mrl as R
from . import common as C
from . import materials as MT
from . import mrl_objects as MO
from .i18n import iface, rpt

PRESET_TYPE = 'RE6_MRL_MATERIAL'
PRESET_VERSION = 1
FOLDER = 'MaterialPresets'
_preset_list = []                  # keeps the items of the enum alive (Blender does not copy the strings)


def preset_dir(create=False):
    return bpy.utils.user_resource('CONFIG', path=os.path.join('re6_model_editor', FOLDER), create=create)


def reload_presets():
    """[(file name, name shown, description)] of the .json files in the preset folder"""
    _preset_list.clear()
    path = preset_dir()
    if path and os.path.isdir(path):
        for entry in sorted(os.scandir(path), key=lambda e: e.name.lower()):
            if entry.name.endswith('.json') and entry.is_file():
                _preset_list.append((entry.name, os.path.splitext(entry.name)[0], ''))
    return _preset_list


def preset_items(self, context):
    return reload_presets()


def valid_name(name):
    """the check of saveAsPreset() of the MHW Model Editor, plus: no folders"""
    if not name or re.search(r'^[\w,\s-]+\.[A-Za-z]{3}$', name) or '..' in name:
        return False
    return not any(c in name for c in '/\\:*?"<>|')


def preset_of(obj):
    """the preset dict of an MRL material object"""
    p = obj.re6_mrl_material
    d = json.loads(obj[MT.K_DATA])
    block = bytearray.fromhex(d['block'])
    MT.patch_block(block, p)               # the edited values of the Property List are part of the preset
    d['block'] = bytes(block).hex()
    header = {'materialName': p.materialName, 'hash': p.hash, 'shader': p.shader, 'blend': p.blend, 'depth': p.depth,
              'raster': p.raster, 'flags': {k: getattr(p, k) for k in R.FIELDS}, 'data': d}
    out = {'presetType': PRESET_TYPE, 'presetVersion': PRESET_VERSION, 'Material Header': header}
    if p.mapList_items:
        out['Map List'] = [{'name': i.name, 'value': i.value, 'code': i.code} for i in p.mapList_items]
    if p.samplerList_items:
        out['Sampler List'] = [{'name': i.name, 'value': i.value, 'code': i.code, 'state': i.state}
                               for i in p.samplerList_items]
    if p.propertyBlock_items:
        out['Property List'] = [
            {'blockName': b.blockName, 'code': b.code,
             'props': [{'prop_name': i.prop_name, 'ori_name': i.ori_name, 'data_type': i.data_type, 'offset': i.offset,
                        'value': list(MT.get_floats(i))} for i in b.propertyList_items]}
            for b in p.propertyBlock_items]
    return out


def save_as_preset(obj, name):
    """True when the preset was written"""
    if obj is None or not MO.is_entry(obj):
        C.show_error_message_box(iface('Must select a mrl material object (named with "Mrl Material 00...") to save preset.'))
        return False
    if not valid_name(name):
        C.show_error_message_box(iface('Invalid preset file name.'))
        return False
    path = os.path.join(preset_dir(create=True), name + '.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(preset_of(obj), f, ensure_ascii=False, indent=4)
    print('\033[92m%s%s\033[0m' % (iface('Saved material preset to '), path))
    return True


def _free_number(col):
    used = {C.mat_obj_number(o.name) for o in col.all_objects}
    n = 0
    while n in used:
        n += 1
    return n


def read_preset(filepath):
    """add the material of a preset to the active mrl collection; True when it was added"""
    col = bpy.context.scene.re6_mrl_toolpanel.mrlCollection
    try:
        with open(filepath, encoding='utf-8') as f:
            data = json.load(f)
    except Exception as err:       # noqa
        C.show_error_message_box(iface('Failed to read json file.') + ' \n' + str(err))
        return False
    if not isinstance(data, dict) or data.get('presetType') != PRESET_TYPE:
        C.show_error_message_box(iface('Preset type is not supported.'))
        return False
    h = data.get('Material Header')
    if (not isinstance(h, dict) or not all(h.get(k) for k in ('materialName', 'hash', 'shader', 'blend', 'depth', 'raster'))
            or not isinstance(h.get('data'), dict) or not isinstance(h.get('flags'), dict)):
        C.show_error_message_box(iface('Preset is missing material header info, cannot add preset material.'))
        return False

    print(iface('Adding preset material ') + h['materialName'])
    index = _free_number(col)
    obj = bpy.data.objects.new(C.mat_obj_name(index, h['materialName']), None)
    obj.empty_display_type = 'PLAIN_AXES'
    obj.empty_display_size = 0.10
    obj[C.TYPE] = C.T_MAT
    col.objects.link(obj)
    try:
        p = obj.re6_mrl_material
        p.hash, p.index = h['hash'], index
        p.shader, p.blend, p.depth, p.raster = h['shader'], h['blend'], h['depth'], h['raster']
        p.blend_mode = MT.P.mode_of(MT.P.BLEND_MODES, p.blend)
        p.raster_mode = MT.P.mode_of(MT.P.RASTER_MODES, p.raster)
        p.depth_mode = MT.P.mode_of(MT.P.DEPTH_MODES, p.depth)
        for k, v in h['flags'].items():
            if k in R.FIELDS:
                setattr(p, k, v)
        if not h['materialName'].startswith(C.MAT_PREFIX):
            obj[C.K_NAME] = h['materialName']
        obj.name = C.mat_obj_name(index, p.materialName)
        obj[MT.K_DATA] = json.dumps(h['data'])

        for e in data.get('Map List', []):
            it = p.mapList_items.add()
            it.name, it.value, it.code = e['name'], e['value'], e['code']
        for e in data.get('Sampler List', []):
            it = p.samplerList_items.add()
            it.name, it.value, it.code, it.state = e['name'], e['value'], e['code'], e.get('state', '')
        for b in data.get('Property List', []):
            blk = p.propertyBlock_items.add()
            blk.blockName, blk.code = b['blockName'], b['code']
            for e in b['props']:
                it = blk.propertyList_items.add()
                it.prop_name, it.ori_name, it.data_type, it.offset = e['prop_name'], e['ori_name'], e['data_type'], e.get('offset', 0)
                MT.set_floats(it, tuple(e['value']))
        bpy.context.view_layer.objects.active = obj
    except (KeyError, TypeError, ValueError, IndexError):
        bpy.data.objects.remove(obj, do_unlink=True)
        C.show_error_message_box(iface('Preset is missing material header info, cannot add preset material.'))
        return False
    return True


def tag_redraw(context, space_type='PROPERTIES', region_type='WINDOW'):
    for window in context.window_manager.windows:
        for area in window.screen.areas:
            if area.spaces[0].type == space_type:
                for region in area.regions:
                    if region.type == region_type:
                        region.tag_redraw()


class RE6_OT_add_preset_material(Operator):
    bl_label = 'Add Preset Material'
    bl_idname = 're6_mrl.add_preset_material'
    bl_description = ('Add a new mrl material object with current material preset.'
                      '\nThe button will only be triggered if active mrl collection exists')
    bl_options = {'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.scene.re6_mrl_toolpanel.mrlCollection is not None

    def execute(self, context):
        value = context.scene.re6_mrl_toolpanel.MrlMaterialPresets
        if value != '':
            print(iface('Reading Preset: ') + value)
            finished = read_preset(os.path.join(preset_dir(), value))
        else:
            C.show_error_message_box(iface('There are currently no presets that can be added.'))
            return {'CANCELLED'}
        tag_redraw(bpy.context)
        if finished:
            self.report({'INFO'}, rpt('Added preset material.'))
            return {'FINISHED'}
        return {'CANCELLED'}


class RE6_OT_save_preset(Operator):
    bl_label = 'Save Selected As Preset'
    bl_idname = 're6_mrl.save_selected_as_preset'
    bl_description = ('Save selected mrl material object as a preset for easy reuse and sharing.'
                      '\nThe button will only be triggered if a mrl material object is activated.'
                      '\nPresets can be accessed using the "Open Preset Folder" button')
    presetName: StringProperty(name='Preset Name', default='newPreset')

    @classmethod
    def poll(cls, context):
        return MO.is_entry(context.active_object)

    def execute(self, context):
        if save_as_preset(context.active_object, self.presetName):
            self.report({'INFO'}, rpt('Saved mrl material preset.'))
            return {'FINISHED'}
        return {'CANCELLED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)


class RE6_OT_open_preset_folder(Operator):
    bl_label = 'Open Preset Folder'
    bl_idname = 're6_mrl.open_preset_folder'
    bl_description = 'Open the preset folder in File Explorer'

    def execute(self, context):
        bpy.ops.wm.path_open(filepath=preset_dir(create=True))
        return {'FINISHED'}


CLASSES = (RE6_OT_add_preset_material, RE6_OT_save_preset, RE6_OT_open_preset_folder)


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
