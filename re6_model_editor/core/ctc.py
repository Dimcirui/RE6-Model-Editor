# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 Dimcirui

"""Chain physics (.ctc, class rCnsTinyChain) of Resident Evil 6, version 22.

The same family as the MHW .ctc (version 28) with smaller records, little endian, centimetres::

    header  60 bytes   'CTC\\0', version, unkn1, unkn2, chain count, node count, attribute flags, step time,
                       gravity scaling, global damping, trans force coef, spring scaling, wind scale, 6 solve counts, 2 pad
    chain   80 bytes   per chain, nodeCount nodes of it follow in the node table
    node    96 bytes   per node, the nodes of chain 0 first

Bones are referenced by function id (the id byte of the bone table of the .mod, named RE6Bone_NNN). Within a chain every node is
the child of the node before it; the first node has isParent = 1. The field names are the ones of the MHW Model Editor.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field

MAGIC = b'CTC\x00'
VERSION = 22
HEADER_SIZE, CHAIN_SIZE, NODE_SIZE = 60, 80, 96
PAD = b'\xcd'

_HEADER = struct.Struct('<4s6I6f6B2x')
_CHAIN = struct.Struct('<I4B3i12s3f4x7f4s')
_NODE = struct.Struct('<H6Bf4s16f3f4s')


class CtcError(ValueError):
    pass


@dataclass
class Header:
    version: int = VERSION
    unkn1: int = 0
    unkn2: int = 1000
    attributeFlags: int = 0
    stepTime: float = 1.0 / 60.0
    gravityScaling: float = 1.0
    globalDamping: float = 0.0
    globalTransForceCoef: float = 1.0
    springScaling: float = 1.0
    windScale: float = 1.0
    solveCounts: tuple = (1, 1, 1, 1, 1, 1)         # Str / Ang / MdlCol / SelCol / ScrCol / ChnCol


@dataclass
class Node:
    boneFunctionId: int = 0          # the low byte is the function id of the bone, the high bits (pl0620 only) are kept
    isParent: int = 0
    unknByte1: int = 0
    angleMode: int = 1               # 0 free, 1 cone, 2 hinge
    unknByte2: int = 0
    collisionShape: int = 1          # 0 sphere, 1 sphere with bone collision (as seen), 2 capsule never
    unknEnum: int = 1
    boneColRadius: float = 5.0
    nodeMatrix: tuple = (1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0)
    angleLimitRadius: float = 0.7853982
    mass: float = 1.0
    elasticCoef: float = 1.0


@dataclass
class Chain:
    collisionAttrFlag: int = 0
    chainAttrFlag: int = 1
    unknAttrFlag1: int = 0
    unknAttrFlag2: int = 0
    colAttribute: int = -1
    colGroup: int = 1
    colType: int = 1
    gravity: tuple = (0.0, -980.0, 0.0)
    damping: float = 0.02
    transForceCoef: float = 0.2
    springCoef: float = 0.015
    unknFloat: float = 1.0           # +0x3c, 1.0 in 1426 of 1441 retail chains
    limitForce: float = 100.0
    frictionCoef: float = 0.0
    reflectCoef: float = 0.1
    nodes: list = field(default_factory=list)


@dataclass
class Ctc:
    header: Header = field(default_factory=Header)
    chains: list = field(default_factory=list)

    @property
    def node_count(self):
        return sum(len(c.nodes) for c in self.chains)


def unpack_chain(data: bytes, pos: int = 0):
    """(Chain without nodes, node count) of the 80 byte chain record at `pos`"""
    (n, ca, cha, u1, u2, cola, colg, colt, _pad, gx, gy, gz, damping, tfcoef, spr, unk, limit, fric, refl,
     _pad2) = _CHAIN.unpack_from(data, pos)
    return Chain(ca, cha, u1, u2, cola, colg, colt, (gx, gy, gz), damping, tfcoef, spr, unk, limit, fric, refl), n


def pack_chain(c: Chain) -> bytes:
    return _CHAIN.pack(len(c.nodes), c.collisionAttrFlag, c.chainAttrFlag, c.unknAttrFlag1, c.unknAttrFlag2,
                       c.colAttribute, c.colGroup, c.colType, PAD * 12, *c.gravity, c.damping, c.transForceCoef,
                       c.springCoef, c.unknFloat, c.limitForce, c.frictionCoef, c.reflectCoef, PAD * 4)


def parse(data: bytes) -> Ctc:
    if len(data) < HEADER_SIZE or data[:4] != MAGIC:
        raise CtcError('not a CTC file')
    (_m, version, unkn1, unkn2, nchain, nnode, attr, step, gscale, damp, tfc, spring, wind, *solve) = _HEADER.unpack_from(data, 0)
    if version != VERSION:
        raise CtcError('CTC version %d is not supported (RE6 uses %d)' % (version, VERSION))
    if len(data) != HEADER_SIZE + CHAIN_SIZE * nchain + NODE_SIZE * nnode:
        raise CtcError('the size of the file does not match its chain / node count')
    out = Ctc(Header(version, unkn1, unkn2, attr, step, gscale, damp, tfc, spring, wind, tuple(solve)))
    pos = HEADER_SIZE
    counts = []
    for _ in range(nchain):
        chain, n = unpack_chain(data, pos)
        pos += CHAIN_SIZE
        out.chains.append(chain)
        counts.append(n)
    if sum(counts) != nnode:
        raise CtcError('the node counts of the chains do not add up')
    for ch, n in zip(out.chains, counts):
        for _ in range(n):
            (bid, par, b1, ang, b2, shape, enum, rad, _pad, *rest) = _NODE.unpack_from(data, pos)
            pos += NODE_SIZE
            ch.nodes.append(Node(bid, par, b1, ang, b2, shape, enum, rad, tuple(rest[:16]), rest[16], rest[17], rest[18]))
    return out


def serialize(ctc: Ctc) -> bytes:
    h = ctc.header
    out = bytearray(_HEADER.pack(MAGIC, h.version, h.unkn1, h.unkn2, len(ctc.chains), ctc.node_count, h.attributeFlags,
                                 h.stepTime, h.gravityScaling, h.globalDamping, h.globalTransForceCoef, h.springScaling,
                                 h.windScale, *h.solveCounts))
    for c in ctc.chains:
        out += pack_chain(c)
    for c in ctc.chains:
        for n in c.nodes:
            out += _NODE.pack(n.boneFunctionId, n.isParent, n.unknByte1, n.angleMode, n.unknByte2, n.collisionShape,
                              n.unknEnum, n.boneColRadius, PAD * 4, *n.nodeMatrix, n.angleLimitRadius, n.mass,
                              n.elasticCoef, PAD * 4)
    return bytes(out)
