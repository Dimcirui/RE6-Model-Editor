# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 Dimcirui

"""MT Framework material library (.mrl, version 0x21) of Resident Evil 6.

Layout (all little endian)::

    0x00  'MRL\\0'
    0x04  u32 version (0x21)
    0x08  u32 material count
    0x0c  u32 texture count
    0x10  u32 unknown (constant per file)
    0x14  u32 texture table offset (0x1c)
    0x18  u32 material table offset
    tex   0x4c bytes per entry: u32 class hash (rTexture), 2 x u32 0, char path[64] (no extension, cdcdcdcd padded)
    mat   0x3c bytes per entry:
            +0x00 shader type hash        +0x04 name hash (equals the .mod material hash)
            +0x08 size of the command block (commands + constant buffer)
            +0x0c blend / +0x10 depth / +0x14 rasteriser state hash
            +0x18 flags: bits 0-11 command count, 21-28 material id, 29 fog, 30 tangent, 31 half lambert (see FIELDS)
            +0x1c flags 2: stencil ref, alpha test ref / func, polygon offset, draw pass, layer, deferred lighting
            +0x20 4 floats blend factor   +0x30 animation block size
            +0x34 command block offset    +0x38 animation block offset (0 when none)
    cmd   12 bytes per command: u32 header (low nibble = type), u32 a, u32 b
            type 0 / 2 : render and sampler state, a == b == state hash
            type 1     : a = offset of the constant buffer in the command block, b = buffer name hash
            type 3     : a = texture number (1 based into the texture table, 0 = no texture), b = sampler slot hash
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field

MAGIC = b'MRL\0'
TEX_SIZE = 0x4C
MAT_SIZE = 0x3C
CMD_SIZE = 12

CMD_STATE, CMD_CBUFFER, CMD_SAMPLER, CMD_TEXTURE = 0, 1, 2, 3

# the two flag words of a material (names of albam's mrl.ksy): name -> (word, first bit, bit count); word 0 = flags, 1 = unk_1c
FIELDS = {
    'unk_bits': (0, 12, 9), 'mat_id': (0, 21, 8), 'fog': (0, 29, 1), 'tangent': (0, 30, 1), 'half_lambert': (0, 31, 1),
    'stencil_ref': (1, 0, 8), 'alphatest_ref': (1, 8, 8), 'polygon_offset': (1, 16, 4), 'alphatest': (1, 20, 1),
    'alphatest_func': (1, 21, 3), 'draw_pass': (1, 24, 5), 'layer': (1, 29, 2), 'deferred': (1, 31, 1),
}

# shader type hash of a material (class names from albam)
MATERIAL_TYPES = {0x5FB0EBE4: 'nDraw::MaterialStd', 0x7D2B31B3: 'nDraw::MaterialStdEst', 0x0854D484: 'nDraw::MaterialNull',
                  0x56D89634: 'nDraw::MaterialHud'}


def unpack_flags(flags: int, unk_1c: int) -> dict:
    words = (flags, unk_1c)
    return {k: (words[w] >> lo) & ((1 << n) - 1) for k, (w, lo, n) in FIELDS.items()}


def pack_flags(fields: dict, count: int) -> tuple:
    """(flags, unk_1c) from the decoded fields and the command count"""
    words = [count & 0xFFF, 0]
    for k, (w, lo, n) in FIELDS.items():
        words[w] |= (int(fields[k]) & ((1 << n) - 1)) << lo
    return words[0], words[1]

class MrlError(ValueError):
    pass


@dataclass
class Command:
    header: int
    a: int
    b: int

    @property
    def type(self) -> int:
        return self.header & 0xF


@dataclass
class Material:
    type: int
    name: int                # hash, the material hash used in the .mod
    size: int
    blend: int
    depth: int
    raster: int
    flags: int
    unk_1c: int
    tail: tuple              # the 4 blend factor floats (+0x20 .. +0x2f), kept as words
    cb_size: int             # size of the animation block (+0x30)
    cmd_offset: int
    anim_offset: int
    commands: list = field(default_factory=list)
    block: bytes = b''       # `size` bytes at cmd_offset: the commands followed by the constant buffers
    anim: bytes = b''        # animation block (empty when anim_offset == 0)

    @property
    def textures(self) -> dict:
        """sampler slot hash -> texture number (1 based, 0 = none)"""
        return {c.b: c.a for c in self.commands if c.type == CMD_TEXTURE}


@dataclass
class Mrl:
    version: int
    unk: int
    textures: list           # path strings exactly as stored (backslashes, no extension)
    materials: list
    tex_meta: list = field(default_factory=list)    # (class hash, u32, u32) of every texture entry

    def find(self, name_hash: int):
        for m in self.materials:
            if m.name == name_hash:
                return m
        return None


def parse(data: bytes) -> Mrl:
    if len(data) < 0x1C or data[:4] != MAGIC:
        raise MrlError('not an MRL file')
    version, nmat, ntex, unk, toff, moff = struct.unpack_from('<6I', data, 4)
    if toff + ntex * TEX_SIZE > len(data) or moff + nmat * MAT_SIZE > len(data):
        raise MrlError('tables exceed the file')
    tex, meta = [], []
    for i in range(ntex):
        o = toff + i * TEX_SIZE
        meta.append(struct.unpack_from('<III', data, o))
        raw = data[o + 12:o + TEX_SIZE]
        tex.append(raw.split(b'\0')[0].decode('latin1'))
    mats = []
    for i in range(nmat):
        o = moff + i * MAT_SIZE
        w = struct.unpack_from('<15I', data, o)
        m = Material(type=w[0], name=w[1], size=w[2], blend=w[3], depth=w[4], raster=w[5], flags=w[6], unk_1c=w[7],
                     tail=tuple(w[8:12]), cb_size=w[12], cmd_offset=w[13], anim_offset=w[14])
        n = m.flags & 0xFFF
        if m.cmd_offset + max(m.size, n * CMD_SIZE) > len(data):
            raise MrlError('material %d: command block exceeds the file' % i)
        m.block = data[m.cmd_offset:m.cmd_offset + m.size]
        for k in range(n):
            h, a, b = struct.unpack_from('<III', data, m.cmd_offset + k * CMD_SIZE)
            m.commands.append(Command(h, a, b))
        mats.append(m)
    starts = sorted({m.anim_offset for m in mats if m.anim_offset})
    for m in mats:
        if m.anim_offset:
            nxt = [x for x in starts if x > m.anim_offset]
            m.anim = data[m.anim_offset:(nxt[0] if nxt else len(data))]
    return Mrl(version, unk, tex, mats, meta)


def _align(v, a):
    return (v + a - 1) // a * a


def serialize(mrl: Mrl) -> bytes:
    """file bytes of an Mrl; identical to the original when nothing was edited (commands are written back into the
    command blocks, texture paths into the texture table)"""
    nt, nm = len(mrl.textures), len(mrl.materials)
    toff = 0x1C
    moff = toff + nt * TEX_SIZE
    pos = _align(moff + nm * MAT_SIZE, 16)
    blocks, offs = [], []
    for m in mrl.materials:
        blk = bytearray(m.block.ljust(max(m.size, len(m.commands) * CMD_SIZE), b'\0'))
        for k, c in enumerate(m.commands):
            struct.pack_into('<III', blk, k * CMD_SIZE, c.header, c.a, c.b)
        blocks.append(bytes(blk))
        offs.append(pos)
        pos += len(blk)
    aoffs = []
    for m in mrl.materials:
        if m.anim:
            aoffs.append(pos)
            pos += len(m.anim)
        else:
            aoffs.append(0)
    out = bytearray(struct.pack('<4s6I', MAGIC, mrl.version, nm, nt, mrl.unk, toff, moff))
    for i, path in enumerate(mrl.textures):
        meta = mrl.tex_meta[i] if i < len(mrl.tex_meta) else (0x241F5DEB, 0, 0)
        raw = path.encode('latin1')
        if len(raw) > 63:
            raise MrlError('texture path too long (%d > 63): %s' % (len(raw), path))
        out += struct.pack('<III', *meta) + (raw + b'\0').ljust(64, b'\xcd')
    for m, off, aoff, blk in zip(mrl.materials, offs, aoffs, blocks):
        n = len(m.commands)
        out += struct.pack('<15I', m.type, m.name, len(blk), m.blend, m.depth, m.raster, (m.flags & ~0xFFF) | n, m.unk_1c,
                           *m.tail, m.cb_size, off, aoff)
    if nm:
        out = out.ljust(_align(len(out), 16), b'\0')
    for blk in blocks:
        out += blk
    for m in mrl.materials:
        out += m.anim
    return bytes(out)


# The sampler slot hash alone does not say what a texture is (the same slot is the albedo of a stage material and the
# mask of a character), but the file name suffix does: _BM base (albedo), _NM normal (DXT5nm: x in alpha, y in green),
# _MM mask. Slots only order the candidates when a material binds several textures with the same suffix.
SLOT_PRIORITY = {
    'albedo': (0x2266034A, 0xCD06F347, 0xAA6F0351),
    'normal': (0x75A5334B, 0xFF5BE348, 0x0ED1B35A, 0x039C0367),
    'mask': (0xCD06F347, 0x64C43356, 0x57C1C3D5),
}
ROLE_SUFFIX = {'albedo': 'BM', 'normal': 'NM', 'mask': 'MM'}


def tex_suffix(path: str) -> str:
    base = path.replace('\\', '/').rsplit('/', 1)[-1]
    return base.rsplit('_', 1)[-1].upper() if '_' in base else ''


def bindings(mrl: Mrl, mat: Material) -> list:
    """[(sampler slot hash, texture path or None)] for every texture command of a material"""
    return [(c.b, texture_of(mrl, c.a)) for c in mat.commands if c.type == CMD_TEXTURE]


def texture_of(mrl: Mrl, a: int):
    """the path of texture number a of a type 3 command: 1 based, 0 = no texture (in the retail files 90 % of the
    tNormalMap slots name an _NM texture when read 1 based, 2 % when read 0 based)"""
    return mrl.textures[a - 1] if 1 <= a <= len(mrl.textures) else None


# Sampler states (type 2 commands): `b` is the name of the sampler slot (SSAlbedoMap ...), `a` the sampler state object that is
# selected for it. The default is the state that has the slot's own hash (a == b); the alternatives seen in the game data have
# other names but a code (low 12 bits) of slot code + index, so the index is what is shown: (a & 0xFFF) - (b & 0xFFF).
# Only these alternatives exist in the 5813 retail .mrl files.
SAMPLER_STATES = {
    (0xCAA79208, 1): 0x92388209,
    (0xBBF63214, 1): 0xF7792215, (0xBBF63214, 2): 0x62628216, (0xBBF63214, 3): 0x116BE217,
    (0xBBF63214, 4): 0x5831D218, (0xBBF63214, 5): 0x2B38B219,
    (0x25C7620B, 1): 0x8008820C,
}


def sampler_index(a: int, b: int) -> int:
    """index of the state `a` of the sampler slot `b` (0 = default); -1 when it is not of the form slot code + n"""
    n = (a & 0xFFF) - (b & 0xFFF)
    return n if a == b or (0 < n < 64) else -1


def sampler_state(b: int, index: int, current: int = 0):
    """state object hash for a sampler slot and index: the default for 0, a known alternative, or `current` when it already
    has that index; None when nothing is known for that index"""
    if index == 0:
        return b
    if (b, index) in SAMPLER_STATES:
        return SAMPLER_STATES[(b, index)]
    if current and sampler_index(current, b) == index:
        return current
    from . import mrl_features             # the states of the shader package (also ones no retail material uses)
    return next((h for h in mrl_features.sampler_states(b) if sampler_index(h, b) == index), None)


def samplers(mat: Material) -> list:
    """[(sampler slot hash, state hash)] of the sampler state commands of a material"""
    return [(c.b, c.a) for c in mat.commands if c.type == CMD_SAMPLER]


def roles(mrl: Mrl, mat: Material) -> dict:
    """{'albedo'|'normal'|'mask': [texture paths, best first]} of the textures bound by a material"""
    return roles_of([(s, p) for s, p in bindings(mrl, mat) if p is not None])


def roles_of(bound) -> dict:
    """same as roles() for a list of (slot, path)"""
    out = {}
    for role, suffix in ROLE_SUFFIX.items():
        cand = [(slot, p) for slot, p in bound if tex_suffix(p).startswith(suffix)]
        if not cand:
            continue
        pri = SLOT_PRIORITY[role]
        cand.sort(key=lambda sp: pri.index(sp[0]) if sp[0] in pri else len(pri))
        out[role] = [p for _, p in cand]
    return out


def tex_key(path: str) -> str:
    """normalised lookup key of a texture path ('data/chara/...', lower case, forward slashes)"""
    return path.replace('\\', '/').lower()


def cbuffers(mat: Material) -> list:
    """[(buffer name hash, byte offset in the command block, number of floats)] of the constant buffers of a material;
    a buffer extends to the start of the next one (the last one to the end of the block)"""
    cmds = sorted({c.a: c.b for c in mat.commands if c.type == CMD_CBUFFER}.items())
    out = []
    for i, (off, h) in enumerate(cmds):
        end = cmds[i + 1][0] if i + 1 < len(cmds) else len(mat.block)
        if off % 4 == 0 and off >= len(mat.commands) * CMD_SIZE and end > off and end <= len(mat.block):
            out.append((h, off, (end - off) // 4))
    return out


# --- building files ------------------------------------------------------------------------------------------

DEFAULT_UNK = 0x6A5489B8            # header word 0x10 of 89% of the files (the rest: 0x54226a19)
DEFAULT_TEX_CLASS = 0x241F5DEB      # rTexture


def from_template(name_hash: int) -> Material:
    """a new plain character material (base / normal / mask / extra slot) with the given name hash"""
    from . import mrl_template as T
    m = Material(type=T.TYPE, name=name_hash, size=len(T.BLOCK), blend=T.BLEND, depth=T.DEPTH, raster=T.RASTER,
                 flags=T.FLAGS, unk_1c=T.UNK_1C, tail=tuple(T.TAIL), cb_size=T.CB_SIZE, cmd_offset=0, anim_offset=0,
                 block=T.BLOCK)
    for k in range(m.flags & 0xFFF):
        m.commands.append(Command(*struct.unpack_from('<III', T.BLOCK, k * CMD_SIZE)))
    return m


def assemble(entries, unk: int = DEFAULT_UNK, version: int = 0x21) -> Mrl:
    """Mrl from [(Material, {slot hash: texture path or None})]; the texture table is rebuilt from the paths that are
    used (first use order); a texture command gets the 1 based number of its path, 0 when the slot has none"""
    paths, index = [], {}
    mats = []
    for mat, binds in entries:
        for c in mat.commands:
            if c.type != CMD_TEXTURE:
                continue
            p = binds.get(c.b)
            if p:
                k = tex_key(p)
                if k not in index:
                    paths.append(p)
                    index[k] = len(paths)
                c.a = index[k]
            else:
                c.a = 0
        mats.append(mat)
    return Mrl(version, unk, paths, mats, [(DEFAULT_TEX_CLASS, 0, 0)] * len(paths))
