# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 Dimcirui

"""Display of the chains: the materials and the Geometry Nodes group of the angle limit cone."""
import math

from . import ccl_nodes as N

CHAIN_MATERIAL = 'CTCChainMat'
CONE_MATERIAL = 'CTCConeMat'
CHAIN_COLOR = (1.0, 0.0, 0.0, 0.75)
CONE_COLOR = (0.8, 0.6, 0.0, 0.4)
CONE_TREE = 'CTCConeGeoNodeTreeV1'


def chain_material():
    return N.get_material(CHAIN_MATERIAL, CHAIN_COLOR)


def cone_material():
    return N.get_material(CONE_MATERIAL, CONE_COLOR)


def set_material_color(mat, color):
    mat.diffuse_color = color
    bsdf = next((n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None) if mat.node_tree else None
    if bsdf is not None:
        bsdf.inputs['Base Color'].default_value = color
        bsdf.inputs['Alpha'].default_value = color[3]


def cone_tree():
    """a cone of 18 sides whose tip is at the origin and whose axis is +X; the bottom radius is the angle limit (in radians, which
    is not the real shape of the limit but shows its size)"""
    tree = N.bpy.data.node_groups.get(CONE_TREE)
    if tree is not None:
        return tree
    tree = N.new_tree(CONE_TREE, inputs=(('AngleLimitRadius', 'NodeSocketFloat'),))
    for item in tree.interface.items_tree:
        if item.item_type == 'SOCKET' and item.name == 'AngleLimitRadius':
            item.description = 'Do not change this value manually, set it from the chain object'
    gin = N.node(tree, 'NodeGroupInput', -800, 0)
    cone = N.node(tree, 'GeometryNodeMeshCone', -600, 0)
    cone.inputs['Vertices'].default_value = 18
    cone.inputs['Radius Top'].default_value = 0.0
    cone.inputs['Depth'].default_value = 2.0
    N.link(tree, gin, 'AngleLimitRadius', cone, 'Radius Bottom')
    tip = N.node(tree, 'GeometryNodeTransform', -400, 0)                 # the tip (z = +1) to the origin
    tip.inputs['Translation'].default_value = (0.0, 0.0, -1.0)
    N.link(tree, cone, 'Mesh', tip, 'Geometry')
    turn = N.node(tree, 'GeometryNodeTransform', -200, 0)                # the axis (-z) to +x, 10 units long
    turn.inputs['Rotation'].default_value = (0.0, -math.pi / 2, 0.0)
    turn.inputs['Scale'].default_value = (5.0, 5.0, 5.0)
    N.link(tree, tip, 'Geometry', turn, 'Geometry')
    mat = N.node(tree, 'GeometryNodeSetMaterial', 0, 0)
    mat.inputs['Material'].default_value = cone_material()
    N.link(tree, turn, 'Geometry', mat, 'Geometry')
    out = N.node(tree, 'NodeGroupOutput', 200, 0)
    N.link(tree, mat, 'Geometry', out, 'Geometry')
    return tree


def add_cone_modifier(obj, name='CTCGeometryNodes'):
    return N.add_modifier(obj, cone_tree(), name)
