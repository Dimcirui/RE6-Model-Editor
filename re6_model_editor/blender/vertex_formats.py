# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 Dimcirui

"""Vertex formats in Blender: a dropdown on the mesh (the official layout names of the game, stored in the custom property
Mod_Mesh_VertexFormat as before) and the Set Vertex Format operator, which picks a layout from its components the way the MHW
Model Editor builds its block names (PosNorTanUV1Weight4Bone4 ...). Only layouts of the game can be chosen (core/vertex.py)."""
import bpy
from bpy.props import BoolProperty, EnumProperty, IntProperty
from bpy.types import Operator

from ..core import vertex as V
from . import common as C
from .i18n import iface, rpt

KEY = 'Mod_Mesh_VertexFormat'
AUTO = 'AUTO'


def stored_format(mesh):
    """the layout hash stored on a mesh, or None (Auto / not a valid hash)"""
    value = mesh.get(KEY, '')
    try:
        return int(value, 16) if value else None
    except (TypeError, ValueError):
        return None


def has_skeleton(obj):
    """whether the model of an object has an armature: the mod collection it is in decides, else its armature modifier"""
    for col in C.mod_collections():
        if obj.name in col.all_objects:
            return any(o.type == 'ARMATURE' for o in col.all_objects)
    return obj.find_armature() is not None


def item_label(h):
    return '%s (%d B)' % (V.official_name(h), V.FORMATS[h].stride)


# --- dropdown on the mesh ----------------------------------------------------------------------------------------------
# Blender keeps only references to the strings of a dynamic enum, so the items live in a module list.
_mesh_items = []


def _mesh_format_items(self, context):
    obj = getattr(context, 'active_object', None) if context else None
    skeleton = has_skeleton(obj) if obj is not None and obj.data == self else True
    current = stored_format(self)
    _mesh_items.clear()
    _mesh_items.append((AUTO, iface('Auto'), iface('Choose the smallest layout that holds the data when exporting'), 0))
    for h in sorted(V.FORMATS, key=lambda h: h & 0xFFF):
        if (V.FORMATS[h].pos == 's16') == skeleton or h == current:
            _mesh_items.append(('%08x' % h, item_label(h), V.describe(h), h & 0xFFF))
    return _mesh_items


def _get_mesh_format(self):
    h = stored_format(self)
    return 0 if h is None or h not in V.FORMATS else h & 0xFFF


def _set_mesh_format(self, value):
    h = next((h for h in V.FORMATS if h & 0xFFF == value), None)
    self[KEY] = '%08x' % h if h is not None and value else ''


# --- composer ----------------------------------------------------------------------------------------------------------
_compose_items = []


def _components(op):
    tangent = op.uvCount > 0 if op.skinned else op.useTangent         # skinned layouts have a tangent exactly when they have UVs
    return op.skinned, int(op.weights), op.uvCount, op.useColor, tangent, op.extraData


def _compose_format_items(self, context):
    _compose_items.clear()
    for h in V.compose(*_components(self)):
        _compose_items.append(('%08x' % h, item_label(h), V.describe(h)))
    if not _compose_items:
        _compose_items.append(('NONE', iface('None'), ''))
    return _compose_items


WEIGHT_ITEMS = [('1', '1', 'One bone per vertex (rigid)'), ('2', '2', 'Up to 2 bones per vertex'),
                ('4', '4', 'Up to 4 bones per vertex'), ('8', '8', 'Up to 8 bones per vertex')]


class RE6_OT_set_vertex_format(Operator):
    bl_idname = 're6_mod.set_vertex_format'
    bl_label = 'Set Vertex Format'
    bl_description = ('Set the vertex format of the selected meshes by choosing what the vertices hold.'
                      '\nOnly the layouts that exist in the game can be used; if there is none for the chosen components, '
                      'the closest ones are listed.\nData the format can not hold (vertex colors, extra UV maps, bone '
                      'influences beyond its count) is dropped on export')
    bl_options = {'UNDO'}

    useAuto: BoolProperty(name='Auto', default=False,
                          description='Let the exporter choose the smallest layout that holds the data of each mesh')
    skinned: BoolProperty(name='Skinned', default=True,
                          description='Layouts of models with a skeleton (IASkin...). Off = static models without a skeleton '
                                      '(IANonSkin...)')
    weights: EnumProperty(name='Weights', items=WEIGHT_ITEMS, default='4',
                          description='Bone influences per vertex the layout holds')
    uvCount: IntProperty(name='UV Maps', default=1, min=0, max=4,
                         description='UV maps the layout holds. 0 = the bridge / shadow layouts (no UV, no tangent)')
    useColor: BoolProperty(name='Vertex Color', default=False, description='The layout holds a vertex color')
    useTangent: BoolProperty(name='Tangent', default=True,
                             description='The layout holds a tangent (skinned layouts have one whenever they have UVs)')
    extraData: BoolProperty(name='Extra Data (4M)', default=False,
                            description='The 64 byte layouts with extra data (IASkinOTB_4WT_4M, IANonSkinTBN_4M); the extra '
                                        'bytes are kept from the file or written as zero')
    vertexFormat: EnumProperty(name='Format', items=_compose_format_items,
                               description='The layouts of the game that hold these components')

    @classmethod
    def poll(cls, context):
        return any(o.type == 'MESH' for o in context.selected_objects)

    def invoke(self, context, event):
        obj = context.active_object if context.active_object and context.active_object.type == 'MESH' else \
            next(o for o in context.selected_objects if o.type == 'MESH')
        h = stored_format(obj.data)
        if h in V.FORMATS:
            skinned, weights, nuv, col, tan, extra = V.components(V.FORMATS[h])
            self.useAuto = False
        else:                                   # start from the data of the mesh
            skinned, nuv = has_skeleton(obj), min(len(obj.data.uv_layers), 4)
            weights, col, tan, extra = 4, len(obj.data.color_attributes) > 0, True, False
            self.useAuto = True
        self.skinned, self.uvCount, self.useColor, self.useTangent, self.extraData = skinned, nuv, col, tan, extra
        self.weights = str(weights) if skinned and str(weights) in ('1', '2', '4', '8') else '4'
        if h in V.FORMATS and '%08x' % h in [i[0] for i in _compose_format_items(self, context)]:
            self.vertexFormat = '%08x' % h
        return context.window_manager.invoke_props_dialog(self, width=420)

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        col = layout.column(align=True)
        col.prop(self, 'useAuto')
        body = layout.column(align=True)
        body.enabled = not self.useAuto
        body.prop(self, 'skinned')
        if self.skinned:
            body.row(align=True).prop(self, 'weights', expand=True)
        body.prop(self, 'uvCount')
        body.prop(self, 'useColor')
        if not self.skinned:
            body.prop(self, 'useTangent')
        body.prop(self, 'extraData')
        body.separator()
        found = V.compose(*_components(self))
        if found:
            body.prop(self, 'vertexFormat')
            h = int(self.vertexFormat, 16) if self.vertexFormat != 'NONE' else found[0]
            body.label(text=V.describe(h))
        else:
            box = body.box()
            box.alert = True
            box.label(text=iface('The game has no vertex format with these components.'), icon='ERROR')
            box.label(text=iface('Closest formats:'))
            for h in V.nearest(*_components(self)):
                box.label(text='%s: %s' % (V.official_name(h), V.describe(h)))

    def execute(self, context):
        meshes = [o for o in context.selected_objects if o.type == 'MESH']
        if self.useAuto:
            for o in meshes:
                o.data[KEY] = ''
            self.report({'INFO'}, rpt('Set vertex format Auto on %d mesh object(s).') % len(meshes))
            return {'FINISHED'}
        found = V.compose(*_components(self))
        if not found:
            C.show_error_message_box(iface('The game has no vertex format with these components.'))
            return {'CANCELLED'}
        h = int(self.vertexFormat, 16) if self.vertexFormat not in ('', 'NONE') and \
            int(self.vertexFormat, 16) in found else found[0]
        skipped = [o.name for o in meshes if has_skeleton(o) != self.skinned]
        done = [o for o in meshes if o.name not in skipped]
        for o in done:
            o.data[KEY] = '%08x' % h
        for name in skipped:
            self.report({'WARNING'}, rpt('Skipped %s: the model %s a skeleton.')
                        % (name, iface('has') if not self.skinned else iface('has no')))
        self.report({'INFO'}, rpt('Set vertex format %s on %d mesh object(s).') % (V.official_name(h), len(done)))
        return {'FINISHED'}


def draw_panel(layout, context):
    """the Vertex Format box of the Mesh Tools panel"""
    box = layout.box()
    col = box.column(align=True)
    obj = context.active_object
    if obj is not None and obj.type == 'MESH':
        row = col.row(align=True)
        row.scale_y = 1.1
        row.prop(obj.data, 're6_vertex_format', text='')
        h = stored_format(obj.data)
        col.label(text=V.describe(h) if h in V.FORMATS else iface('Chosen when exporting'))
        col.separator()
    row = col.row(align=True)
    row.scale_y = 1.1
    row.operator(RE6_OT_set_vertex_format.bl_idname)


CLASSES = (RE6_OT_set_vertex_format,)


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)
    bpy.types.Mesh.re6_vertex_format = EnumProperty(
        name='Vertex Format', items=_mesh_format_items, get=_get_mesh_format, set=_set_mesh_format,
        description='Vertex format (input layout) of the mesh in the game. Auto = the exporter chooses the smallest layout that '
                    'holds the data.\nStored in the custom property Mod_Mesh_VertexFormat')


def unregister():
    del bpy.types.Mesh.re6_vertex_format
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
