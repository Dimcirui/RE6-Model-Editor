# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 Dimcirui

"""MT Framework shader package (.mfx, version 0x35) of Resident Evil 6: nativePC/system/app_shader/AppShaderPackage.mfx
(the material codes refer to this one; system/shader/ShaderPackage.mfx shares its first 779 objects).

Layout (32 bit; the x64 variant of UMVC3 is described by tge-was-taken/umvc3-tools templates/mt_mfx.bt)::

    0x00  'MFX\\0', u16 version 0x35, u16 0x16, u32 hash
    0x0c  u32 object count, u32 string table offset (strings are referenced by offset into it), u32 0
    0x18  u32 offset of every object
    object  +0x00 name string, +0x04 type name string, +0x08 bits 0-5 kind (KIND), +0x0c high 16 bits = index + 1
            fragments (kind 2): +0x28/+0x2c [start, end) of the reference list (u16 object index + 1, with repeats),
            +0x30/+0x34 [start, end) of the dependency list (the distinct objects it uses: texture slots, sampler
            states, constant buffers, the switches it calls), +0x44 interface (group) name: a switch and its options
            share it ("Bump" for FBump, FBumpNormalMap ...); the UV / channel switches share "UVSelector" /
            "ChannelSelector" with their options. Options are the members nobody depends on.
            constant buffers (kind 0): +0x18 u16 size in floats, u16 field count; +0x20 field records (0x1c bytes:
            name, type words, annotations); +0x24 offset of the default data. Type name 'Local' = material buffers.

Material commands are these objects: b (and a for options) = (jamcrc32(name) & 0xFFFFF) << 12 | (index + 1); the command
type follows from the kind (cbuffer 1, texture 3, sampler state 2, fragment 0).
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field

from .hashes import jamcrc32

MAGIC = b'MFX\0'
KIND = {0: 'cbuffer', 1: 'texture', 2: 'fragment', 3: 'sampler', 4: 'blend', 5: 'depth', 6: 'raster', 7: 'technique',
        8: 'struct', 9: 'input layout', 10: 'comparison sampler'}
CMD_OF_KIND = {0: 1, 1: 3, 2: 0, 3: 2}         # material command type of an object kind


class MfxError(ValueError):
    pass


@dataclass
class MfxObject:
    index: int
    name: str
    type_name: str
    kind: int
    group: str = ''
    deps: list = field(default_factory=list)      # object indices
    cb_default: bytes = b''                       # constant buffers: default data (size = +0x18 low 16 bits floats)

    @property
    def code(self) -> int:
        return self.index + 1

    @property
    def hash(self) -> int:
        """the 32 bit material hash of this object (command b / option a)"""
        return (jamcrc32(self.name) & 0xFFFFF) << 12 | (self.code & 0xFFF)


@dataclass
class Mfx:
    version: int
    objects: list

    def __post_init__(self):
        self.by_name = {o.name: o for o in self.objects}
        self.by_hash = {o.hash: o for o in self.objects}
        users = {}
        for o in self.objects:
            for x in o.deps:
                users.setdefault(x, []).append(o.index)
        self.users = users

    def options(self, switch: MfxObject) -> list:
        """the options of a switch: the members of its interface group that no object depends on, the switch itself
        (= the default option) first"""
        if not switch.group:
            return [switch]
        out = [switch]
        for o in self.objects:
            if o.kind == 2 and o.group == switch.group and o is not switch and o.index not in self.users:
                out.append(o)
        return out


def parse(data: bytes) -> Mfx:
    if data[:4] != MAGIC:
        raise MfxError('not an MFX file')
    version = struct.unpack_from('<H', data, 4)[0]
    n, st = struct.unpack_from('<II', data, 0x0C)
    if 0x18 + 4 * n > len(data) or st > len(data):
        raise MfxError('tables exceed the file')

    def s(o):
        if not o or st + o >= len(data):
            return ''
        return data[st + o:data.find(b'\0', st + o)].decode('latin1')

    objs = []
    for i, p in enumerate(struct.unpack_from('<%dI' % n, data, 0x18)):
        nm, tn, fl = struct.unpack_from('<III', data, p)
        o = MfxObject(i, s(nm), s(tn), fl & 0x3F)
        if o.kind == 2:
            b0, b1 = struct.unpack_from('<2I', data, p + 0x30)
            if b1 > b0:
                o.deps = [x - 1 for x in struct.unpack_from('<%dH' % ((b1 - b0) // 2), data, b0) if 0 < x <= n]
            o.group = s(struct.unpack_from('<I', data, p + 0x44)[0])
        elif o.kind == 0:
            size = struct.unpack_from('<H', data, p + 0x18)[0]
            dp = struct.unpack_from('<I', data, p + 0x24)[0]
            if dp and dp + 4 * size <= len(data):
                o.cb_default = data[dp:dp + 4 * size]
        objs.append(o)
    return Mfx(version, objs)


def is_material_object(o) -> bool:
    """an object that can be a command of a material: material constant buffers ('Local' and $Globals), texture slots
    and sampler states with a type name, and switch / option fragments (with an interface group)"""
    if o.kind == 0:
        return o.type_name == 'Local' or o.name == '$Globals'
    if o.kind in (1, 3):
        return bool(o.type_name)
    if o.kind == 2:
        return bool(o.group)
    return False


def key_of(o) -> tuple:
    """(material command type, b) of an object"""
    return (CMD_OF_KIND[o.kind], o.hash)


def material_tables(m: Mfx, root) -> dict:
    """everything a MaterialStd material can use, starting from the command keys `root` (the commands every material
    has): {'options': {switch: [option hashes, default first]}, 'deps': {option: [command keys]},
    'cb': {buffer: default bytes}, 'samplers': {slot: [state hashes, default first]}, 'names': {hash: name}}"""
    options, deps, seen = {}, {}, set(root)
    todo = [k for k in root if k[0] == CMD_OF_KIND[2]]
    while todo:
        _, sw = todo.pop()
        o = m.by_hash.get(sw)
        if o is None or sw in options:
            continue
        options[sw] = [x.hash for x in m.options(o)]
        for opt in m.options(o):
            ks = [key_of(m.objects[x]) for x in opt.deps if is_material_object(m.objects[x])]
            deps[opt.hash] = ks
            for k in ks:
                if k not in seen:
                    seen.add(k)
                    if k[0] == CMD_OF_KIND[2]:
                        todo.append(k)
    objs = [m.by_hash[k[1]] for k in seen if k[1] in m.by_hash]
    objs += [m.by_hash[a] for v in options.values() for a in v]
    cb = {o.hash: o.cb_default for o in objs if o.kind == 0 and o.cb_default}
    samplers = {}
    for o in objs:
        if o.kind == 3:
            alts = [x for x in m.objects if x.kind == 3 and x.type_name == o.type_name and x is not o
                    and x.index not in m.users]
            samplers[o.hash] = [o.hash] + [x.hash for x in alts]
    names = {o.hash >> 12: o.name for o in objs}
    for v in samplers.values():
        for h in v:
            names[h >> 12] = m.by_hash[h].name
    return dict(options=options, deps=deps, cb=cb, samplers=samplers, names=names)
