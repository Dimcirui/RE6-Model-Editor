# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 Dimcirui

"""RE6 (MT Framework) .mod  -- version 211 reader / writer.

Layout (all little endian, sections are contiguous in every retail file checked):

    0x00  header (0x70 bytes) + 0x10 bytes of misc data           -> Mod211.head
    bones      boneCount * 0x18   (id, parent, mirror, unk, f, length, x, y, z)
    lmatrix    boneCount * 0x40   local matrices     (same meaning as MHW mod3)
    amatrix    boneCount * 0x40   inverse absolute matrices (carry the vertex dequant scale!)
    remap      0x100              bone function id -> bone index (0xFF = unused)
    groups     groupCount * 0x20
    materials  materialCount * 4  (name hashes, the .mrl is looked up by hash)
    meshes     meshCount * 0x30
    bboxes     u32 count + count * 0x90   (per mesh, per bone bounding volumes)
    vertices   vertexBufferSize
    faces      indexCount * u16   (triangle lists)
    trailer    free-form (tool signature strings in modded files)

Vertex positions are int16 x3, dequantised with  pos_model = s16 / 32767 * A[0][0]
and moved into world space by the translation stored in the AMatrices
(see :meth:`Mod211.model_to_world`).
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field

import numpy as np

MESH_SIZE = 0x30
BONE_SIZE = 0x18
BBOX_SIZE = 0x90
GROUP_SIZE = 0x20

# blocktype hash -> stride ("blockSize").  Extracted from all retail chara mods.
VERTEX_STRIDE = {
    0xb0983013: 12, 0x0cb68015: 20, 0xa8fab018: 20, 0x14d40020: 28, 0x64593023: 40,
    0xc31f201c: 24, 0xdb7da014: 16, 0xcbf6c01a: 24, 0xd877801b: 32, 0xb392101f: 36,
    0xbb424024: 36, 0x207d6037: 24, 0xa320c016: 28, 0xda55a021: 32, 0xcbcf7027: 48,
    0xd8297028: 24, 0xa013501e: 28, 0x2f55c03d: 64, 0x667b1019: 24, 0x0d9e801d: 28,
    0x49b4f029: 28, 0xa7d7d036: 20, 0x926fd02e: 32, 0x77d87022: 32, 0x75c3e025: 40,
    0x5e7f202c: 28, 0xd84e3026: 40,
}

# rigid (single bone) 20 byte format:  s16[3] pos, u8 boneIndex, u8 0xFE, n[4], t[4], half uv[2]
RIGID_1UV = 0xa8fab018


class ModError(RuntimeError):
    pass


@dataclass
class Mesh:
    lodMask: int          # +0x00  0xFDF7 normal, 0x1020 low lod / shadow ...
    vertexCount: int      # +0x02
    flags: int            # +0x04  (materialIdx << 12) | visibleCondition
    unk6: int             # +0x06
    lod: int              # +0x07
    weightDynamics: int   # +0x08  9 = one bone, 17/25/33... = multi bone
    blockSize: int        # +0x0a  vertex stride
    unk3: int             # +0x0b
    vertexSub: int        # +0x0c  first vertex of this mesh inside its bucket
    vertexOffset: int     # +0x10  byte offset of the bucket in the vertex buffer
    blocktype: int        # +0x14  vertex format hash
    faceOffset: int       # +0x18  in indices (u16 units)
    faceCount: int        # +0x1c  number of indices
    vertexBase: int       # +0x20
    null0: int            # +0x24
    boundingBoxCount: int  # +0x25
    unknownIndex: int     # +0x26
    vertexSubMirror: int  # +0x28
    vertexIndexSub: int   # +0x2a  vertexSub + vertexCount - 1
    tail: int             # +0x2c

    FMT = '<HHHBBHBBIIIIIIBBHHHI'

    @classmethod
    def unpack(cls, buf, off):
        return cls(*struct.unpack_from(cls.FMT, buf, off))

    def pack(self):
        return struct.pack(self.FMT, *(getattr(self, f) for f in self.__dataclass_fields__))

    @property
    def material(self):
        return self.flags >> 12


@dataclass
class Mod211:
    head: bytes                     # bytes [0, boneOffset) -- patched on write
    bones: bytes
    lmat: np.ndarray                # (n,4,4)
    amat: np.ndarray                # (n,4,4)
    remap: bytes
    groups: bytes
    materials: list
    meshes: list
    bboxes: list                    # list of 0x90 byte blobs
    vertices: bytearray
    faces: np.ndarray               # uint16
    trailer: bytes
    version: int = 211
    tail_pad: int = 0               # extra zero bytes between the faces and the trailer (some tools write 4)

    # header field offsets
    _H = struct.Struct('<4sHHHHIIIIII')  # magic ver bones meshes mats vtx idx edges vbs 2nd groups

    @property
    def boneCount(self):
        return len(self.bones) // BONE_SIZE

    # ------------------------------------------------------------------ parse
    @classmethod
    def parse(cls, d: bytes) -> 'Mod211':
        if d[:4] != b'MOD\0':
            raise ModError('not a MOD file')
        ver, nb, nm, nmat = struct.unpack_from('<HHHH', d, 4)
        if ver != 211:
            raise ModError('unsupported MOD version %d' % ver)
        nv, ni, ne, vbs, _, ng = struct.unpack_from('<IIIIII', d, 0x0c)
        boff, goff, moff, meoff, voff, foff, toff = struct.unpack_from('<7I', d, 0x24)
        if nb == 0:
            boff = 0x80            # skeleton-less models store boneOffset = 0 but data starts at 0x80
        head = d[:boff]
        o = boff
        bones = d[o:o + nb * BONE_SIZE]; o += nb * BONE_SIZE
        lmat = np.frombuffer(d, '<f4', nb * 16, o).reshape(nb, 4, 4).copy(); o += nb * 64
        amat = np.frombuffer(d, '<f4', nb * 16, o).reshape(nb, 4, 4).copy(); o += nb * 64
        if nb:
            remap = d[o:o + 256]; o += 256
        else:
            remap = b''            # skeleton-less models have no bone map either
        if o != goff or goff + ng * GROUP_SIZE != moff or moff + nmat * 4 != meoff:
            raise ModError('non contiguous bone/group/material sections')
        groups = d[goff:moff]
        materials = list(struct.unpack_from('<%dI' % nmat, d, moff))
        meshes = [Mesh.unpack(d, meoff + i * MESH_SIZE) for i in range(nm)]
        o = meoff + nm * MESH_SIZE
        nbox = struct.unpack_from('<I', d, o)[0]
        bboxes = [d[o + 4 + i * BBOX_SIZE:o + 4 + (i + 1) * BBOX_SIZE] for i in range(nbox)]
        o += 4 + nbox * BBOX_SIZE
        std_toff = foff + ni * 2 + (-(foff + ni * 2)) % 4
        pad = toff - std_toff
        if o != voff or voff + vbs != foff or not 0 <= pad <= 64 or any(d[std_toff:toff]):
            raise ModError('non contiguous mesh/vertex/face sections')
        return cls(head, bones, lmat, amat, remap, groups, materials, meshes, bboxes,
                   bytearray(d[voff:foff]), np.frombuffer(d, '<u2', ni, foff).copy(), d[toff:], ver, pad)

    # -------------------------------------------------------------- serialize
    def serialize(self) -> bytes:
        nb = self.boneCount
        head = bytearray(self.head)
        boff = len(head)
        goff = boff + nb * BONE_SIZE + nb * 128 + (256 if nb else 0)
        moff = goff + len(self.groups)
        meoff = moff + 4 * len(self.materials)
        voff = meoff + MESH_SIZE * len(self.meshes) + 4 + BBOX_SIZE * len(self.bboxes)
        foff = voff + len(self.vertices)
        toff = foff + self.faces.size * 2
        toff += (-toff) % 4
        toff += self.tail_pad
        struct.pack_into('<HHHH', head, 4, self.version, nb, len(self.meshes), len(self.materials))
        struct.pack_into('<I', head, 0x0c, sum(m.vertexCount for m in self.meshes))
        struct.pack_into('<I', head, 0x10, int(self.faces.size))
        struct.pack_into('<I', head, 0x18, len(self.vertices))
        struct.pack_into('<I', head, 0x20, len(self.groups) // GROUP_SIZE)
        struct.pack_into('<7I', head, 0x24, boff if nb else 0, goff, moff, meoff, voff, foff, toff)
        out = bytearray(head)
        out += self.bones
        out += self.lmat.astype('<f4').tobytes()
        out += self.amat.astype('<f4').tobytes()
        out += self.remap
        out += self.groups
        out += struct.pack('<%dI' % len(self.materials), *self.materials)
        for m in self.meshes:
            out += m.pack()
        out += struct.pack('<I', len(self.bboxes))
        for b in self.bboxes:
            out += b
        out += self.vertices
        out += self.faces.astype('<u2').tobytes()
        out += bytes((-len(out)) % 4 + self.tail_pad)
        out += self.trailer
        return bytes(out)

    # ------------------------------------------------------------- skeleton
    def bone_table(self):
        """[(id, parent, mirror, unk, f, length, x, y, z)]"""
        return [struct.unpack_from('<BBBBfffff', self.bones, i * BONE_SIZE) for i in range(self.boneCount)]

    @property
    def scale(self):
        """dequantisation scale = diagonal of the AMatrices (231.9 for pl0610)"""
        return float(self.amat[0][0][0])

    def bind_world(self):
        """bone positions in *model space* (= -translation of inverse bind matrices)"""
        return -self.amat[:, 3, :3] / 1.0

    @property
    def model_origin(self):
        """translation that moves model space into the world space of the L-matrix chain.

        For every bone  A.t = -(worldL + origin)  =>  origin = -A.t - worldL
        """
        world = self.local_world()
        return (-self.amat[0, 3, :3]) - world[0]

    def local_world(self):
        n = self.boneCount
        bt = self.bone_table()
        w = np.zeros((n, 3))
        for i in range(n):
            p = bt[i][1]
            t = self.lmat[i][3][:3].astype(float)
            w[i] = t if p == 255 else w[p] + t
        return w

    # -------------------------------------------------------------- vertices
    def mesh_vertex_bytes(self, i):
        m = self.meshes[i]
        base = m.vertexOffset + (m.vertexSub + m.vertexBase) * m.blockSize
        return np.frombuffer(self.vertices, np.uint8, m.vertexCount * m.blockSize, base).reshape(m.vertexCount, m.blockSize)

    def mesh_positions_model(self, i):
        v = self.mesh_vertex_bytes(i)
        return v[:, :6].copy().view('<i2').reshape(-1, 3).astype(np.float64) / 32767.0 * self.scale

    def mesh_indices(self, i):
        m = self.meshes[i]
        idx = self.faces[m.faceOffset:m.faceOffset + m.faceCount].astype(np.int64)
        return idx.reshape(-1, 3) - m.vertexSub

    def mesh_uv(self, i):
        """first UV set for formats that have uv at +16 (rigid 20B / 28B / 40B ...)."""
        m = self.meshes[i]
        v = self.mesh_vertex_bytes(i)
        if m.blocktype == RIGID_1UV:
            return v[:, 16:20].copy().view('<f2').reshape(-1, 2).astype(np.float32)
        if m.blocktype in (0x14d40020, 0x64593023):
            return v[:, 20:24].copy().view('<f2').reshape(-1, 2).astype(np.float32)
        return None

    def mesh_normals(self, i):
        v = self.mesh_vertex_bytes(i)
        m = self.meshes[i]
        off = 16 if m.blocktype == 0x0cb68015 else 8
        n = v[:, off:off + 3].astype(np.float32) / 255.0 * 2 - 1
        return n


# ---------------------------------------------------------------------------
# skin decoding.   weightDynamics == 1 + 8 * (number of influencing bones)
#   9 -> 1 bone (bone id lives in pos.w low byte), 17 -> 2, 25 -> 3, 33 -> 4
# ---------------------------------------------------------------------------
def decode_vertices(mod: 'Mod211', i: int) -> dict:
    """Decode mesh ``i`` with the format table of :mod:`re6vertex` (all 40 formats found in the game).

    Keys: pos (model space for skinned/rigid meshes, world floats for static ones), nrm, tan, tsign, uv (list),
    ids (n,K) bone indices, w (n,K) weights, col, plus raw ``nw``/``tw``/``residual`` bytes for lossless re-encoding.
    """
    from . import vertex as re6vertex
    m = mod.meshes[i]
    f = re6vertex.FORMATS.get(m.blocktype)
    if f is None:
        raise ModError('vertex format 0x%08x is not known' % m.blocktype)
    d = re6vertex.decode(f, mod.mesh_vertex_bytes(i), mod.scale if mod.boneCount else 1.0)
    d['format'] = m.blocktype
    return d
