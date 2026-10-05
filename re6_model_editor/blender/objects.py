# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 Dimcirui

"""Helpers that build the objects of the chain (ctc) and collision (ccl) layers: collections, empties, curve objects, locked
transforms, the sphere made of three circles."""
import math

import bpy
from mathutils import Matrix, Vector


def create_collection(name, color, type_, parent=None):
    col = bpy.data.collections.new(name)
    col.color_tag = color
    col['~TYPE'] = type_
    (parent or bpy.context.scene.collection).children.link(col)
    return col


def get_collection(name, parent=None, make_new=False):
    """the collection of that name, or a new one linked to `parent` (or the scene)"""
    if make_new or not bpy.data.collections.get(name):
        col = bpy.data.collections.new(name)
        (parent or bpy.context.scene.collection).children.link(col)
        return col
    return bpy.data.collections[name]


def create_empty(name, props, parent=None, collection=None):
    obj = bpy.data.objects.new(name, None)
    obj.empty_display_size = .10
    obj.empty_display_type = 'PLAIN_AXES'
    obj.parent = parent
    for k, v in props:
        obj[k] = v
    (collection or bpy.context.scene.collection).objects.link(obj)
    return obj


def create_curve_empty(name, props, parent=None, collection=None, make_new=False):
    """a curve object without splines (it carries a modifier, or gets splines later); the data is shared unless make_new"""
    if make_new:
        data = bpy.data.curves.new(name, 'CURVE')
        data.use_path = False
    else:
        data = bpy.data.curves.get('emptyCurve')
        if data is None:
            data = bpy.data.curves.new('emptyCurve', 'CURVE')
            data.use_path = False
    obj = bpy.data.objects.new(name, data)
    obj.parent = parent
    for k, v in props:
        obj[k] = v
    (collection or bpy.context.scene.collection).objects.link(obj)
    return obj


def _circle(plane):
    """closed bezier circle of radius 1 in the xy / xz / yz plane: [(co, handle left, handle right)]"""
    k = 0.5523
    pts = []
    for i in range(4):
        a = i * math.pi / 2
        c, s = math.cos(a), math.sin(a)
        co = (c, s)
        hl = (c + k * s, s - k * c)           # tangent direction (-s, c) backwards
        hr = (c - k * s, s + k * c)
        pts.append((co, hl, hr))

    def put(p):
        return {'xy': (p[0], p[1], 0.0), 'xz': (p[0], 0.0, p[1]), 'yz': (0.0, p[0], p[1])}[plane]
    return [(put(co), put(hl), put(hr)) for co, hl, hr in pts]


def create_fake_empty_sphere(name, props, parent=None, collection=None):
    """a sphere that looks like an empty sphere: three circles in one shared curve datablock"""
    data = bpy.data.curves.get('fakeEmptySphere')
    if data is None:
        data = bpy.data.curves.new('fakeEmptySphere', 'CURVE')
        data.use_path = False
        for plane in ('xy', 'xz', 'yz'):
            spline = data.splines.new(type='BEZIER')
            spline.use_cyclic_u = True
            spline.bezier_points.add(3)
            for point, (co, hl, hr) in zip(spline.bezier_points, _circle(plane)):
                point.handle_left_type = point.handle_right_type = 'FREE'
                point.co, point.handle_left, point.handle_right = co, hl, hr
    obj = bpy.data.objects.new(name, data)
    obj.parent = parent
    for k, v in props:
        obj[k] = v
    (collection or bpy.context.scene.collection).objects.link(obj)
    return obj


def lock_transforms(obj, location=True, rotation=True, scale=True):
    """limit constraints that pin an object to its parent's space"""
    if location:
        c = obj.constraints.new(type='LIMIT_LOCATION')
        c.use_min_x = c.use_min_y = c.use_min_z = c.use_max_x = c.use_max_y = c.use_max_z = True
    if rotation:
        c = obj.constraints.new(type='LIMIT_ROTATION')
        c.use_limit_x = c.use_limit_y = c.use_limit_z = True
    if scale:
        c = obj.constraints.new(type='LIMIT_SCALE')
        c.use_min_x = c.use_min_y = c.use_min_z = c.use_max_x = c.use_max_y = c.use_max_z = True
        c.min_x = c.min_y = c.min_z = c.max_x = c.max_y = c.max_z = 1.0


def name_in_use(base, objs=None):
    """True when `base` is part of the name of an object (checkNameUsage())"""
    for o in (bpy.data.objects if objs is None else objs):
        if base in o.name:
            return True
    return False


def orient_vector_pair(a, b):
    """rotation matrix (4x4) that turns the direction `a` into the direction `b`"""
    a, b = Vector(a), Vector(b)
    if a.length < 1e-9 or b.length < 1e-9:
        return Matrix.Identity(4)
    return a.rotation_difference(b).to_matrix().to_4x4()
