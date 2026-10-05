# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 Dimcirui

"""Display of the collisions: the material and the Geometry Nodes groups that turn a curve object into a sphere / a capsule."""
import bpy

SPHERE_TREE = 'CCLSphereGeoNodeTreeV1'
CAPSULE_TREE = 'CCLCapsuleGeoNodeTreeV2'
MATERIAL = 'CCLCollisionMat'
DEFAULT_COLOR = (0.003, 0.426, 0.8, 0.3)


def get_material(name, color):
    """a translucent material of that colour (shared)"""
    mat = bpy.data.materials.get(name)
    if mat is not None:
        return mat
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    mat.diffuse_color = color
    bsdf = next((n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None)
    if bsdf is not None:
        bsdf.inputs['Base Color'].default_value = color
        bsdf.inputs['Alpha'].default_value = color[3]
    for attr, value in (('surface_render_method', 'BLENDED'), ('blend_method', 'BLEND')):
        try:
            setattr(mat, attr, value)
        except (AttributeError, TypeError):
            pass
    return mat


def collision_material():
    return get_material(MATERIAL, DEFAULT_COLOR)


def new_tree(name, inputs=(), output='Geometry'):
    """an empty geometry nodes group with the given input sockets [(name, socket type)] and a geometry output"""
    tree = bpy.data.node_groups.new(name, 'GeometryNodeTree')
    for n, t in inputs:
        tree.interface.new_socket(n, in_out='INPUT', socket_type=t)
    tree.interface.new_socket(output, in_out='OUTPUT', socket_type='NodeSocketGeometry')
    return tree


def socket_id(tree, name, in_out='INPUT'):
    """identifier of an interface socket (the key of the modifier input)"""
    for item in tree.interface.items_tree:
        if item.item_type == 'SOCKET' and item.in_out == in_out and item.name == name:
            return item.identifier
    raise KeyError(name)


def node(tree, type_, x, y, **props):
    n = tree.nodes.new(type_)
    n.location = (x, y)
    for k, v in props.items():
        setattr(n, k, v)
    return n


def link(tree, a, out, b, inp):
    tree.links.new(a.outputs[out], b.inputs[inp])


def finish(tree, last, x, out_name='Geometry'):
    """material -> smooth shading -> group output"""
    mat = node(tree, 'GeometryNodeSetMaterial', x, 0)
    mat.inputs['Material'].default_value = collision_material()
    smooth = node(tree, 'GeometryNodeSetShadeSmooth', x + 200, 0)
    out = node(tree, 'NodeGroupOutput', x + 400, 0)
    link(tree, last, out_name, mat, 'Geometry')
    link(tree, mat, 'Geometry', smooth, 'Geometry')
    link(tree, smooth, 'Geometry', out, 'Geometry')


def sphere_tree():
    tree = bpy.data.node_groups.get(SPHERE_TREE)
    if tree is not None:
        return tree
    tree = new_tree(SPHERE_TREE)
    sphere = node(tree, 'GeometryNodeMeshUVSphere', 0, 0)
    sphere.inputs['Radius'].default_value = 1.0
    finish(tree, sphere, 200, 'Mesh')
    return tree


def capsule_tree():
    """a tube between two objects whose radii follow the scale of the objects, with a sphere at each end"""
    tree = bpy.data.node_groups.get(CAPSULE_TREE)
    if tree is not None:
        return tree
    tree = new_tree(CAPSULE_TREE, inputs=(('Start Object', 'NodeSocketObject'), ('End Object', 'NodeSocketObject')))
    gin = node(tree, 'NodeGroupInput', -1400, 0)
    info = []
    for k, name in enumerate(('Start Object', 'End Object')):
        oi = node(tree, 'GeometryNodeObjectInfo', -1200, 200 - 400 * k, transform_space='RELATIVE')
        link(tree, gin, name, oi, 'Object')
        sep = node(tree, 'ShaderNodeSeparateXYZ', -1000, 200 - 400 * k)
        link(tree, oi, 'Scale', sep, 'Vector')
        info.append((oi, sep))
    line = node(tree, 'GeometryNodeCurvePrimitiveLine', -800, 0, mode='POINTS')
    link(tree, info[0][0], 'Location', line, 'Start')
    link(tree, info[1][0], 'Location', line, 'End')
    index = node(tree, 'GeometryNodeInputIndex', -800, -200)
    prev = line
    for k in range(2):
        cmp = node(tree, 'FunctionNodeCompare', -600, -200 - 150 * k, data_type='INT', operation='EQUAL')
        cmp.inputs[3].default_value = k                      # the integer B input
        link(tree, index, 'Index', cmp, 2)                   # the integer A input
        rad = node(tree, 'GeometryNodeSetCurveRadius', -400 + 200 * k, 0)
        link(tree, prev, 'Curve' if k == 0 else 'Curve', rad, 'Curve')
        link(tree, cmp, 'Result', rad, 'Selection')
        link(tree, info[k][1], 'X', rad, 'Radius')
        prev = rad
    circle = node(tree, 'GeometryNodeCurvePrimitiveCircle', 0, -300, mode='RADIUS')
    circle.inputs['Resolution'].default_value = 16
    circle.inputs['Radius'].default_value = 1.0
    tube = node(tree, 'GeometryNodeCurveToMesh', 200, 0)
    link(tree, prev, 'Curve', tube, 'Curve')
    link(tree, circle, 'Curve', tube, 'Profile Curve')
    if 'Scale' in tube.inputs:                                  # newer Blender versions do not scale the profile by the radius
        radius = node(tree, 'GeometryNodeInputRadius', 0, -500)
        link(tree, radius, 'Radius', tube, 'Scale')
    join = node(tree, 'GeometryNodeJoinGeometry', 800, 0)
    link(tree, tube, 'Mesh', join, 'Geometry')
    for k in range(2):
        sph = node(tree, 'GeometryNodeMeshUVSphere', 200, -500 - 300 * k)
        sph.inputs['Radius'].default_value = 1.0
        tr = node(tree, 'GeometryNodeTransform', 500, -500 - 300 * k)
        link(tree, sph, 'Mesh', tr, 'Geometry')
        link(tree, info[k][0], 'Location', tr, 'Translation')
        comb = node(tree, 'ShaderNodeCombineXYZ', 300, -600 - 300 * k)
        for axis in ('X', 'Y', 'Z'):
            link(tree, info[k][1], 'X', comb, axis)
        link(tree, comb, 'Vector', tr, 'Scale')
        link(tree, tr, 'Geometry', join, 'Geometry')
    finish(tree, join, 1000, 'Geometry')
    return tree


def add_modifier(obj, tree, name='CCLGeometryNodes'):
    mod = obj.modifiers.new(name, 'NODES')
    mod.node_group = tree
    return mod
