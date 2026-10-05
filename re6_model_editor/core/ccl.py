# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 Dimcirui

"""Chain collision (.ccl, class rChainCol) of Resident Evil 6: the same layout as the MHW .ccl (version 0x80618), little endian,
centimetres::

    header  16 bytes   'CCL\\0', version, record count, total size of the records
    record  64 bytes   start bone, end bone, shape (0 sphere, 1 capsule), start / end position (bone local), radius

Bones are referenced by function id (the id byte of the bone table of the .mod, named RE6Bone_NNN); a sphere has no end bone
(0xFFFF in the retail files).
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field

MAGIC = b'CCL\x00'
VERSION = 0x80618
HEADER_SIZE, RECORD_SIZE = 16, 64
NO_BONE = 0xFFFF
PAD = b'\xcd'

_HEADER = struct.Struct('<4s3I')
_RECORD = struct.Struct('<IHHB7s3fI3ff12s4s')


class CclError(ValueError):
    pass


@dataclass
class Collision:
    startBoneId: int = 0
    endBoneId: int = NO_BONE
    shape: int = 0                   # 0 sphere, 1 capsule
    startPos: tuple = (0.0, 0.0, 0.0)
    endPos: tuple = (0.0, 0.0, 0.0)
    radius: float = 5.0


@dataclass
class Ccl:
    version: int = VERSION
    collisions: list = field(default_factory=list)


def parse(data: bytes) -> Ccl:
    if len(data) < HEADER_SIZE or data[:4] != MAGIC:
        raise CclError('not a CCL file')
    _m, version, count, total = _HEADER.unpack_from(data, 0)
    if len(data) != HEADER_SIZE + RECORD_SIZE * count:
        raise CclError('the size of the file does not match its record count')
    out = Ccl(version)
    for i in range(count):
        (_z, start, end, shape, _p, sx, sy, sz, _z2, ex, ey, ez, rad, _p2, _p3) = _RECORD.unpack_from(
            data, HEADER_SIZE + i * RECORD_SIZE)
        out.collisions.append(Collision(start, end, shape, (sx, sy, sz), (ex, ey, ez), rad))
    return out


def serialize(ccl: Ccl) -> bytes:
    out = bytearray(_HEADER.pack(MAGIC, ccl.version, len(ccl.collisions), RECORD_SIZE * len(ccl.collisions)))
    for c in ccl.collisions:
        out += _RECORD.pack(0, c.startBoneId, c.endBoneId, c.shape, PAD * 7, *c.startPos, 0, *c.endPos, c.radius,
                            b'\x00' * 12, PAD * 4)
    return bytes(out)
