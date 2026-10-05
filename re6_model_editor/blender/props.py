# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 Dimcirui

import os

import bpy
from ..core.hashes import jamcrc32, material_name
from . import common as C
from bpy.props import (BoolProperty, CollectionProperty, EnumProperty, FloatProperty, FloatVectorProperty, IntProperty,
                       PointerProperty, StringProperty)


# (identifier, the engine's name of the state, tooltip, state hash); the names are the ones of the game's shader package
BLEND_MODES = (('OPAQUE', 'BSSolid', 'Opaque: no blending (alpha test can still cut pixels out)', '62b2d163'),
               ('ALPHA', 'BSBlendAlpha', 'Alpha blending with the background (smooth transparency)', '23baf165'),
               ('ADD', 'BSAddAlpha', 'Additive blending (glow, fire)', 'd3b1d16b'),
               ('COMPOSITE', 'BSComposite', 'Composite blend (1 retail material, meaning unverified)', 'd4823166'))
TWO_SIDED, ONE_SIDED = '923331ad', '108cf19f'
DEPTH_MODES = (('TEST_WRITE', 'DSZTestWrite', 'Depth test and depth write', 'b8139196'),
               ('TEST', 'DSZTest', 'Depth test without writing', '7d2f6198'),
               ('WRITE', 'DSZWrite', 'Depth write without testing', 'a967c199'),
               ('TEST_STENCIL_WRITE', 'DSZTestStencilWrite', 'Depth test, depth write and stencil write (1 retail '
                'material)', '3051119c'))
RASTER_MODES = (('MESH', 'RSMesh', 'Default raster state (back faces culled)', '108cf19f'),
                ('MESH_CN', 'RSMeshCN', 'No culling: both sides are drawn (two sided)', '923331ad'),
                ('MESH_CF', 'RSMeshCF', 'Culling variant (10 retail materials, meaning unverified)', '2ab011ac'),
                ('MESH_BIAS3', 'RSMeshBias3', 'Depth bias variant 3 (1 retail material)', '243271a2'),
                ('MESH_BIAS5', 'RSMeshBias5', 'Depth bias variant 5 (1 retail material)', '1e6121a4'))


def mode_of(table, h) -> str:
    """identifier of the mode whose state hash is `h` ('CUSTOM' when it is not in the table)"""
    return {m[3]: m[0] for m in table}.get(h, 'CUSTOM')


def _blend_items(self, context):
    return [(m[0], m[1], m[2]) for m in BLEND_MODES] + [('CUSTOM', 'Custom', 'Other blend state hash (kept as is)')]


def _blend_update(self, context):
    for m in BLEND_MODES:
        if m[0] == self.blend_mode:
            self.blend = m[3]


def _depth_items(self, context):
    return [(m[0], m[1], m[2]) for m in DEPTH_MODES] + [('CUSTOM', 'Custom', 'Other depth state hash (kept as is)')]


def _depth_update(self, context):
    for m in DEPTH_MODES:
        if m[0] == self.depth_mode:
            self.depth = m[3]


def _raster_items(self, context):
    return [(m[0], m[1], m[2]) for m in RASTER_MODES] + [('CUSTOM', 'Custom', 'Other raster state hash (kept as is)')]


def _raster_update(self, context):
    for m in RASTER_MODES:
        if m[0] == self.raster_mode:
            self.raster = m[3]
    if self.linkedMaterial is not None:
        try:
            self.linkedMaterial.use_backface_culling = self.raster != TWO_SIDED
        except AttributeError:
            pass


class Re6MapPG(bpy.types.PropertyGroup):
    """one texture slot of a material (Mrl3MapPG): name = sampler slot name, value = texture path, code = slot hash"""
    name: StringProperty(name="")
    value: StringProperty(name="", maxlen=256, description="Texture path without extension (data\\chara\\pl\\...). Empty = "
                          "no texture")
    code: StringProperty(name="")


_SAMPLER_ITEMS = {}         # Blender needs the strings of dynamic enum items to stay referenced


def _sampler_items(self, context):
    """the sampler states of the shader package for this slot; the enum number is the state index (= `value`)"""
    from ..core import mrl as R
    from ..core import mrl_features as F
    from ..core.shader_names import name_of
    try:
        slot = int(self.code, 16)
    except ValueError:
        slot = 0
    items = []
    for h in F.sampler_states(slot):
        i = R.sampler_index(h, slot)
        if i >= 0:
            items.append((str(i), name_of(h) or '%08x' % h, '%08x' % h, i))
    if not any(it[3] == self.value for it in items):
        items.append((str(self.value), '%d (%s)' % (self.value, self.state or '?'), '', self.value))
    _SAMPLER_ITEMS[slot] = items
    return items


def _sampler_get(self):
    return self.value


def _sampler_set(self, v):
    self.value = v


class Re6SamplerPG(bpy.types.PropertyGroup):
    """one sampler state of a material (Mrl3SamplerPG): name = sampler slot name, value = state index, code = slot hash"""
    name: StringProperty(name="")
    value: IntProperty(name="", min=0, description="Index of the sampler state selected for this slot (0 = the default state "
                       "of the slot; the alternatives that exist in the game data are known for some slots)")
    code: StringProperty(name="")
    state: StringProperty(name="", description="State object hash read from the file")
    state_enum: EnumProperty(name="", items=_sampler_items, get=_sampler_get, set=_sampler_set,
                             description="Sampler state of this slot (the states of the game's shader package)")


def update_listFilter(self, context):
    if context.area:
        context.area.tag_redraw()


class _FilteredList:
    filterString: StringProperty(name="Filter", description="Search the list for items that contain this string.\nPress "
                                 "enter to search", default='', update=update_listFilter)

    def invoke(self, context, event):           # no rename on double click
        return {'PASS_THROUGH'}

    def draw_filter(self, context, layout):
        layout.column(align=True).row(align=True).prop(self, 'filterString', text='', icon='VIEWZOOM')

    def filter_items(self, context, data, propname):
        filtered, ordered = [], []
        items = getattr(data, propname)
        if self.filterString:
            filtered = [self.bitflag_filter_item] * len(items)
            for i, item in enumerate(items):
                if self.filterString.lower() not in item.name.lower():
                    filtered[i] &= ~self.bitflag_filter_item
        return filtered, ordered

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        layout.ui_units_y = 1.4
        split = layout.split(factor=0.35)
        col1 = split.column()
        col2 = split.column()
        row = col2.row()
        col2.alignment = 'RIGHT'
        col1.label(text=item.name or item.code)
        row.prop(item, "value")


class MESH_UL_MrlMapList(_FilteredList, bpy.types.UIList):
    pass


class MESH_UL_MrlSamplerList(_FilteredList, bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        layout.ui_units_y = 1.4
        split = layout.split(factor=0.35)
        split.label(text=item.name or item.code)
        split.prop(item, 'state_enum', text='')


DRIVEN = ('shininess', 'specular_color')        # properties that drive the preview material (the wrench icon of the list)


def _prop_update(self, context):
    from . import materials
    materials.apply_driven(self)


class Re6PropPG(bpy.types.PropertyGroup):
    """one named value of a constant buffer (Mrl3PropPG): a run of 1 to 4 floats at `offset` of the command block"""
    prop_name: StringProperty(name="")
    ori_name: StringProperty(name="")
    offset: IntProperty(default=0, description="Byte offset of the value in the command block of the material")
    data_type: EnumProperty(name="Data Type", items=[
        ('FLOAT', 'Float', 'Float'), ('FLOAT[2]', 'Float[2]', 'Float[2]'), ('FLOAT[3]', 'Float[3]', 'Float[3]'),
        ('FLOAT[4]', 'Float[4]', 'Float[4]'), ('COLOR', 'Color', 'Color (3 floats)'),
        ('COLOR4', 'Color (RGBA)', 'Color with alpha (4 floats)')])
    float_value: FloatProperty(name="", update=_prop_update)
    float2_value: FloatVectorProperty(name="", size=2, update=_prop_update)
    float3_value: FloatVectorProperty(name="", size=3, update=_prop_update)
    float4_value: FloatVectorProperty(name="", size=4, update=_prop_update)
    color_value: FloatVectorProperty(name="", size=3, subtype='COLOR', min=0.0, max=1000.0, soft_max=1.0,
                                     default=(1.0, 1.0, 1.0), update=_prop_update)
    color4_value: FloatVectorProperty(name="", size=4, subtype='COLOR', min=0.0, max=1000.0, soft_max=1.0,
                                      default=(1.0, 1.0, 1.0, 1.0), update=_prop_update)


class Re6PropBlockPG(bpy.types.PropertyGroup):
    """one constant buffer of a material (Mrl3PropBlockPG)"""
    propertyList_items: CollectionProperty(type=Re6PropPG)
    propertyList_index: IntProperty(name="")
    blockName: StringProperty(name="")
    code: StringProperty(name="", description="Name hash of the constant buffer")


class MESH_UL_MrlPropertyList(bpy.types.UIList):
    filterString: StringProperty(name="Filter", description="Search the list for items that contain this string.\nPress "
                                 "enter to search", default='', update=update_listFilter)

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        layout.ui_units_y = 1.4
        split = layout.split(factor=0.48)
        col1 = split.column()
        col2 = split.column()
        row = col2.row()
        col2.alignment = 'RIGHT'
        col1.label(text=item.prop_name, icon="MODIFIER" if item.ori_name in DRIVEN else "NONE")
        row.prop(item, {'FLOAT': 'float_value', 'FLOAT[2]': 'float2_value', 'FLOAT[3]': 'float3_value',
                        'FLOAT[4]': 'float4_value', 'COLOR': 'color_value', 'COLOR4': 'color4_value'}[item.data_type])

    def invoke(self, context, event):
        return {'PASS_THROUGH'}

    def draw_filter(self, context, layout):
        layout.column(align=True).row(align=True).prop(self, 'filterString', text='', icon='VIEWZOOM')

    def filter_items(self, context, data, propname):
        filtered, ordered = [], []
        items = getattr(data, propname)
        if self.filterString:
            filtered = [self.bitflag_filter_item] * len(items)
            for i, item in enumerate(items):
                if self.filterString.lower() not in item.prop_name.lower():
                    filtered[i] &= ~self.bitflag_filter_item
        return filtered, ordered


def _get_material_name(self):
    """the resolved name of the material, else MAT_<hash> (the name the exporter takes as a plain hash)"""
    obj = self.id_data
    nm = obj.get(C.K_NAME, '') if obj is not None else ''
    if not nm:
        try:
            h = int(self.hash, 16)
        except ValueError:
            return ''
        nm = material_name(h) or C.mat_name(h)
    return nm


def _set_material_name(self, value):
    """a name sets the hash (jamcrc32 of the name, like the games do); MAT_xxxxxxxx is a hash written out. The meshes and
    preview materials of the model that used the old hash follow (material_names.relink), and the name is remembered"""
    obj = self.id_data
    value = value.strip()
    if not value:
        return
    try:
        old_hash = int(self.hash, 16)
    except ValueError:
        old_hash = None
    h = C.parse_mat_hash(value)
    if h is not None and len(value) == len(C.MAT_PREFIX) + 8:
        if obj is not None and C.K_NAME in obj:
            del obj[C.K_NAME]
        self.hash = '%08x' % h
    else:
        if obj is not None:
            obj[C.K_NAME] = value
        self.hash = '%08x' % jamcrc32(value)
    if obj is not None:
        num = C.mat_obj_number(obj.name)
        obj.name = C.mat_obj_name(num if num is not None else self.index, _get_material_name(self))
        from . import material_names, mrl_objects
        material_names.remember([value])
        mrl_col = next((c for c in obj.users_collection if C.is_mrl(c)), None)
        model = mrl_objects.mod_collection_of(mrl_col)
        if old_hash is not None and model is not None:
            material_names.relink(old_hash, value, [model])


class Re6MaterialProps(bpy.types.PropertyGroup):
    """one material of a .mrl (object.re6_mrl_material of the empties in a '<name>.mrl' collection); the parts without a UI
    (command block with the constant buffers, animation block) are kept in object['re6_mat_data']"""
    materialName: StringProperty(name="Material Name", get=_get_material_name, set=_set_material_name,
                                 description="The name of the current material. Its hash is computed from the name "
                                             "(jamcrc32), so the name must match the one the meshes refer to.\n"
                                             "Materials whose name is not known are shown as MAT_<hash>")
    hash: StringProperty(name="Material hash", description="Name hash of the material: the hash the .mod meshes refer "
                         "to (8 hex digits). Empty = not an MRL material", default="")
    index: IntProperty(name="Index", description="Position of the material in the .mrl", default=0, min=0)
    shader: StringProperty(name="Shader", description="Shader type hash", default="")
    blend: StringProperty(name="Blend state hash", default="")
    depth: StringProperty(name="Depth state hash", default="")
    raster: StringProperty(name="Raster state hash", default="")
    blend_mode: EnumProperty(name="Blend", items=_blend_items, update=_blend_update)
    depth_mode: EnumProperty(name="Depth", items=_depth_items, update=_depth_update)
    raster_mode: EnumProperty(name="Raster", items=_raster_items, update=_raster_update)
    # the two flag words of the material (core/mrl.py FIELDS)
    alphatest: BoolProperty(name="Alpha Test", description="Discard pixels whose alpha fails the test against the "
                            "reference", default=False)
    alphatest_ref: IntProperty(name="Alpha Ref", description="Alpha test reference (0-255)", default=0, min=0, max=255)
    alphatest_func: IntProperty(name="Alpha Func", description="Alpha test comparison (4 in every retail material)",
                                default=4, min=0, max=7)
    draw_pass: IntProperty(name="Draw Pass", description="Render pass of the material (11 = opaque in most retail "
                           "materials, 12 / 14 / 16 / 20 = alpha and special passes)", default=11, min=0, max=31)
    layer: IntProperty(name="Layer", default=0, min=0, max=3)
    deferred: BoolProperty(name="Deferred Lighting", default=True)
    half_lambert: BoolProperty(name="Half Lambert", description="Half-Lambert diffuse lighting", default=True)
    fog: BoolProperty(name="Fog", default=False)
    tangent: BoolProperty(name="Tangent", default=False)
    stencil_ref: IntProperty(name="Stencil Ref", default=0, min=0, max=255)
    polygon_offset: IntProperty(name="Polygon Offset", default=0, min=0, max=15)
    mat_id: IntProperty(name="Material Id", default=0, min=0, max=255)
    unk_bits: IntProperty(name="Unknown bits", description="Bits 12-20 of the flags, meaning unknown (copied)",
                          default=4, min=0, max=511)
    mapList_items: CollectionProperty(type=Re6MapPG)
    mapList_index: IntProperty(name="")
    samplerList_items: CollectionProperty(type=Re6SamplerPG)
    samplerList_index: IntProperty(name="")
    propertyBlock_items: CollectionProperty(type=Re6PropBlockPG)
    propertyBlock_index: IntProperty(name="")
    linkedMaterial: PointerProperty(
        name="Linked Material", type=bpy.types.Material,
        description="The blender material that corresponds to this mrl material object."
                    "\nAny changes made to supported mrl properties (with spanner icon) will reflect on the blender material")


def _filter_mod(self, col):
    return C.is_mod(col)


def _filter_mrl(self, col):
    return C.is_mrl(col)


def _mrl_changed(self, context):
    """like MHWME: choosing the active MRL collection selects the model collection of the same name"""
    if self.mrlCollection is not None:
        base = self.mrlCollection.name[:-4] if self.mrlCollection.name.lower().endswith('.mrl') else self.mrlCollection.name
        mod = bpy.data.collections.get(base + '.mod')
        if mod is not None:
            self.modCollection = mod


def _update_export_mod(self, context):
    C.set_export_filename(self.exportModCollection, '.mod')


def _update_export_mrl(self, context):
    C.set_export_filename(self.exportMrlCollection, '.mrl')


def _update_mod_directory(self, context):
    try:
        if "//" in self.modDirectory:
            self.modDirectory = os.path.realpath(bpy.path.abspath(self.modDirectory))
    except Exception:       # noqa
        pass


def _update_texture_directory(self, context):
    try:
        if "//" in self.textureDirectory:
            self.textureDirectory = os.path.realpath(bpy.path.abspath(self.textureDirectory))
    except Exception:       # noqa
        pass


def _preset_items(self, context):
    from . import mrl_presets
    return mrl_presets.preset_items(self, context)


class Re6ModToolPanelPG(bpy.types.PropertyGroup):
    """scene.re6_mod_toolpanel (the counterpart of mhw_mod3_toolpanel)"""
    importSettingsLoaded: BoolProperty(default=False)
    exportSettingsLoaded: BoolProperty(default=False)

    lastImportCollection: StringProperty(default="")
    lastExportCollection: StringProperty(default="")

    exportModCollection: PointerProperty(name="", description="Set the mod collection to be exported",
                                         type=bpy.types.Collection, poll=_filter_mod, update=_update_export_mod)


class Re6MrlToolPanelPG(bpy.types.PropertyGroup):
    """scene.re6_mrl_toolpanel (the counterpart of mhw_mrl3_toolpanel)"""
    lastImportCollection: StringProperty(default="")
    lastExportCollection: StringProperty(default="")
    exportMrlCollection: PointerProperty(name="", description="Set the mrl collection to be exported",
                                         type=bpy.types.Collection, poll=_filter_mrl, update=_update_export_mrl)
    MrlMaterialPresets: EnumProperty(name="", description="", items=_preset_items)

    mrlCollection: PointerProperty(name="", description="Set the blue collection containing the mrl file to edit.\n"
                                   "You can create a new mrl collection by pressing the \"Create Mrl Collection\" button",
                                   type=bpy.types.Collection, poll=_filter_mrl, update=_mrl_changed)
    modCollection: PointerProperty(name="", description="Set the red mod collection to apply the active mrl collection to",
                                   type=bpy.types.Collection, poll=_filter_mod)
    modDirectory: StringProperty(name="", subtype='DIR_PATH', default="", update=_update_mod_directory,
                                 description='Set the nativePC directory of your mod (the folder that contains data/).'
                                             '\nThis is used by the "Copy Converted Tex" button.'
                                             '\nThis will be set automatically when a file is exported.'
                                             '\nExample:\n' + r'D:\SteamLibrary\steamapps\common\RE6\nativePC')
    textureDirectory: StringProperty(name="", subtype='DIR_PATH', default="", update=_update_texture_directory,
                                     description="Set the directory containing textures to be converted to .tex files")
    addConversionFolder: BoolProperty(name="Add Conversion Folder", default=False,
                                      description='When converting texture files, add a folder called "Converted_RE6_DDS" '
                                                  'or "Converted_RE6_Tex" next to them')
    addDXGIFormatPrefix: BoolProperty(
        name="Add DXGI Format Prefix", default=False,
        description='When converting .tex to .dds, add the format prefix to the file name.'
                    '\nFor example, if the name of .tex is "body_BM.tex", the name of the converted .dds will be '
                    '"DXT1_body_BM.dds"')
    openConvertedFolder: BoolProperty(name="Open Folder After Conversion", default=False,
                                      description="Open the directory containing the converted texture files after conversion")
    askFormat: BoolProperty(name='Choose Format Per File', default=True,
                            description='When converting images / .dds to .tex, show a list to pick DXT1, DXT5 or BGRA8 '
                                        'for every file')
    compression: EnumProperty(name='Compression', default='AUTO',
                              items=[('AUTO', 'Automatic', 'DXT5 for normal maps and images with transparency, else DXT1'),
                                     ('BC1', 'DXT1', 'No alpha'), ('BC3', 'DXT5', 'With alpha'),
                                     ('BGRA', 'BGRA8', 'Uncompressed, lossless, largest')])
    normalMaps: EnumProperty(name='Files Named *_NM', default='CONVERT',
                             items=[('CONVERT', 'Convert To DXT5nm', 'Regular RGB normal maps are converted; images already packed like the game (R and B white) are kept'),
                                    ('KEEP', 'Keep As Is', "The images already use the game's packing")])
    flipGreen: BoolProperty(name='Flip Green', default=True,
                            description='Regular (OpenGL) normal maps to the DirectX convention of the game')
    generateMipmaps: BoolProperty(name='Generate Mipmaps', default=True,
                                  description='Write a full mip chain when converting images / .dds to .tex (adds 1/3 '
                                              'to the size). Off: only the top level, the game then always samples '
                                              'full resolution (sharper, but shimmering on dense patterns)')


CLASSES = (Re6MapPG, Re6SamplerPG, MESH_UL_MrlMapList, MESH_UL_MrlSamplerList, Re6PropPG, Re6PropBlockPG,
           MESH_UL_MrlPropertyList, Re6MaterialProps, Re6ModToolPanelPG, Re6MrlToolPanelPG)


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)
    bpy.types.Scene.re6_mod_toolpanel = bpy.props.PointerProperty(type=Re6ModToolPanelPG)
    bpy.types.Scene.re6_mrl_toolpanel = bpy.props.PointerProperty(type=Re6MrlToolPanelPG)
    bpy.types.Object.re6_mrl_material = bpy.props.PointerProperty(type=Re6MaterialProps)


def unregister():
    del bpy.types.Object.re6_mrl_material
    del bpy.types.Scene.re6_mrl_toolpanel
    del bpy.types.Scene.re6_mod_toolpanel
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
