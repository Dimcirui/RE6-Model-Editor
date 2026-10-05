# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 Dimcirui

"""RE6 PC .tex (MT Framework texture) <-> DDS, dependency free.

A TEX file is 'TEX\\0' + 12 byte bit-packed header + [108 byte cubemap block when images == 6] + u32 mip offsets
(absolute, mips * images of them) + raw block compressed / BGRA payload, i.e. exactly the DDS payload.
The pixel layout is identified from the payload size (8 byte blocks = BC1/DXT1, 16 byte blocks = BC3/DXT5,
4 bytes per pixel = BGRA8). Format of this module follows RE6 ARC Studio (re6arc/tex.py).
"""
from __future__ import annotations

import struct
from dataclasses import dataclass

TEX_MAGIC = b'TEX\x00'
CUBE_BLOCK = 108

BC1, BC3, BGRA = 'BC1', 'BC3', 'BGRA'
_BLOCK = {BC1: 8, BC3: 16}
_DDS_FOURCC = {BC1: b'DXT1', BC3: b'DXT5'}


class TexError(ValueError):
    pass


@dataclass
class Tex:
    version: int
    unk: int
    attr: int
    prebias: int
    type: int
    mips: int
    width: int
    height: int
    images: int
    fmt: int
    depth: int
    flags: int
    cube: bytes
    offsets: list
    payload_start: int
    layout: str


_FIELDS = (('version', 8), ('unk', 8), ('attr', 8), ('prebias', 4), ('type', 4),
           ('mips', 6), ('width', 13), ('height', 13), ('images', 8), ('fmt', 8),
           ('depth', 13), ('flags', 3))


def level_size(w: int, h: int, layout: str) -> int:
    if layout == BGRA:
        return w * h * 4
    return ((w + 3) // 4) * ((h + 3) // 4) * _BLOCK[layout]


def mip_chain_size(w: int, h: int, mips: int, layout: str) -> int:
    total = 0
    for _ in range(mips):
        total += level_size(w, h, layout)
        w, h = max(1, w // 2), max(1, h // 2)
    return total


def _offset_step(w: int, h: int, layout: str) -> int:
    # below 4x4 the game's own tools advance by w*h*bytes-per-pixel in the offset table (payload is block aligned)
    if layout != BGRA and w < 4 and h < 4:
        return max(1, w * h * _BLOCK[layout] // 16)
    return level_size(w, h, layout)


def _infer_layout(w: int, h: int, mips: int, images: int, payload: int):
    for layout in (BC1, BC3, BGRA):
        if mip_chain_size(w, h, mips, layout) * images == payload:
            return layout
    return None


def parse(data: bytes) -> Tex:
    if len(data) < 16 or data[:4] != TEX_MAGIC:
        raise TexError('not a TEX file')
    bits = int.from_bytes(data[4:16], 'little')
    vals, cur = {}, 0
    for name, n in _FIELDS:
        vals[name] = (bits >> cur) & ((1 << n) - 1)
        cur += n
    mips, images = vals['mips'], vals['images']
    if not (1 <= mips <= 16 and images >= 1 and vals['width'] and vals['height']):
        raise TexError('unsupported TEX header (render target or unknown variant)')
    cube = data[16:16 + CUBE_BLOCK] if images == 6 else b''
    off_pos = 16 + len(cube)
    count = mips * images
    start = off_pos + count * 4
    if len(data) < start:
        raise TexError('mip offset table exceeds file')
    offsets = list(struct.unpack_from('<%dI' % count, data, off_pos))
    layout = _infer_layout(vals['width'], vals['height'], mips, images, len(data) - start)
    if layout is None:
        raise TexError('payload size does not match any supported pixel layout')
    return Tex(cube=cube, offsets=offsets, payload_start=start, layout=layout, **vals)


def _pack_header(t: Tex) -> bytes:
    bits, cur = 0, 0
    for name, n in _FIELDS:
        bits |= (getattr(t, name) & ((1 << n) - 1)) << cur
        cur += n
    return TEX_MAGIC + bits.to_bytes(12, 'little')


def _dds_header(w: int, h: int, mips: int, layout: str, cubemap: bool = False) -> bytes:
    flags = 0x1 | 0x2 | 0x4 | 0x1000
    caps = 0x1000
    if mips > 1:
        flags |= 0x20000
        caps |= 0x8 | 0x400000
    if layout == BGRA:
        pf = struct.pack('<II4sIIIII', 32, 0x41, b'\0\0\0\0', 32, 0xFF0000, 0xFF00, 0xFF, 0xFF000000)
        pitch = w * 4
        flags |= 0x8
    else:
        pf = struct.pack('<II4sIIIII', 32, 0x4, _DDS_FOURCC[layout], 0, 0, 0, 0, 0)
        pitch = level_size(w, h, layout)
        flags |= 0x80000
    caps2 = (0x200 | 0xFC00) if cubemap else 0
    head = struct.pack('<4s18I', b'DDS ', 124, flags, h, w, pitch, 0, mips, *([0] * 11))
    if cubemap:
        caps |= 0x8
    return head + pf + struct.pack('<5I', caps, caps2, 0, 0, 0)


def to_dds(data: bytes) -> bytes:
    """TEX -> DDS (cubemaps keep all six faces)"""
    t = parse(data)
    body = data[t.payload_start:]
    if t.images == 1:
        return _dds_header(t.width, t.height, t.mips, t.layout) + body
    if t.images == 6:
        return _dds_header(t.width, t.height, t.mips, t.layout, cubemap=True) + body
    raise TexError('cannot convert a TEX with %d images to DDS' % t.images)


@dataclass
class DdsInfo:
    width: int
    height: int
    mips: int
    layout: str
    payload: bytes


# DXGI formats of DX10 headers: the ones RE6 can store as they are, and names of the ones that must be re-encoded
_DXGI_NATIVE = {71: BC1, 72: BC1, 77: BC3, 78: BC3, 87: BGRA, 91: BGRA}
_DXGI_NAMES = {2: 'RGBA32F', 10: 'RGBA16F', 24: 'RGB10A2', 28: 'RGBA8', 29: 'RGBA8 sRGB', 61: 'R8', 49: 'RG8',
               70: 'BC1', 71: 'BC1', 72: 'BC1 sRGB', 74: 'BC2', 75: 'BC2 sRGB', 77: 'BC3', 78: 'BC3 sRGB',
               80: 'BC4', 81: 'BC4S', 83: 'BC5', 84: 'BC5S', 87: 'BGRA8', 88: 'BGRX8', 91: 'BGRA8 sRGB',
               93: 'BGRX8 sRGB', 95: 'BC6H', 96: 'BC6H S', 98: 'BC7', 99: 'BC7 sRGB'}
_FOURCC_NAMES = {b'DXT1': 'DXT1', b'DXT2': 'DXT2', b'DXT3': 'DXT3', b'DXT4': 'DXT4', b'DXT5': 'DXT5',
                 b'ATI1': 'BC4', b'BC4U': 'BC4', b'BC4S': 'BC4S', b'ATI2': 'BC5', b'BC5U': 'BC5', b'BC5S': 'BC5S'}


@dataclass
class DdsFormat:
    width: int
    height: int
    mips: int
    name: str           # e.g. 'DXT1', 'BC7 sRGB (DX10)'
    layout: str         # BC1 / BC3 / BGRA when the payload can be stored in a .tex as it is, else ''
    start: int          # payload offset


def dds_format(dds: bytes) -> DdsFormat:
    """pixel format of a DDS (legacy or DX10 header); cubemaps, volumes and arrays are rejected"""
    if len(dds) < 128 or dds[:4] != b'DDS ':
        raise TexError('not a DDS file')
    (hsize, flags, h, w, _pitch, _depth, mips) = struct.unpack_from('<7I', dds, 4)
    pf_flags, fourcc, bits, rmask, gmask, bmask, amask = struct.unpack_from('<I4sIIIII', dds, 80)
    caps2 = struct.unpack_from('<I', dds, 112)[0]
    if hsize != 124:
        raise TexError('malformed DDS header')
    if caps2 & 0x200 or caps2 & 0x200000:
        raise TexError('cubemap / volume DDS files are not supported')
    mips = max(1, mips) if flags & 0x20000 else 1
    start, layout = 128, ''
    if pf_flags & 0x4 and fourcc == b'DX10':
        if len(dds) < 148:
            raise TexError('malformed DX10 header')
        dxgi, dim, misc, array = struct.unpack_from('<4I', dds, 128)
        if misc & 0x4 or array > 1 or dim == 4:
            raise TexError('cubemap / array / volume DDS files are not supported')
        start, layout = 148, _DXGI_NATIVE.get(dxgi, '')
        name = _DXGI_NAMES.get(dxgi, 'DXGI %d' % dxgi) + ' (DX10)'
    elif pf_flags & 0x4:
        layout = {b'DXT1': BC1, b'DXT5': BC3}.get(fourcc, '')
        name = _FOURCC_NAMES.get(fourcc, fourcc.decode('latin1', 'replace'))
    elif pf_flags & 0x40 and bits == 32 and (rmask, gmask, bmask) == (0xFF0000, 0xFF00, 0xFF):
        layout, name = BGRA, 'BGRA8' if amask else 'BGRX8'
        if not amask:
            layout = ''
    elif pf_flags & 0x40:
        name = 'RGB%d' % bits
    else:
        name = 'unknown'
    if layout and len(dds) - start != mip_chain_size(w, h, mips, layout):
        layout = ''         # odd mip chain / padding: decode and re-encode instead
    return DdsFormat(w, h, mips, name, layout, start)


def parse_dds(dds: bytes) -> DdsInfo:
    """a DDS whose payload can be stored in a .tex as it is (DXT1 / DXT5 / BGRA8, legacy or DX10 header)"""
    f = dds_format(dds)
    if not f.layout:
        raise TexError('DDS format %s has to be re-encoded (DXT1, DXT5 or BGRA8 are stored as they are)' % f.name)
    return DdsInfo(f.width, f.height, f.mips, f.layout, dds[f.start:])


def assemble(width: int, height: int, mips: int, layout: str, fmt: int, payload: bytes) -> bytes:
    """a new single image .tex (header fields as in the retail textures: version 154, type 2, depth 1)"""
    t = Tex(version=154, unk=0, attr=0, prebias=0, type=2, mips=mips, width=width, height=height, images=1, fmt=fmt,
            depth=1, flags=0, cube=b'', offsets=[], payload_start=0, layout=layout)
    start = 16 + mips * 4
    offsets, pos, w, h = [], start, width, height
    for _ in range(mips):
        offsets.append(pos)
        pos += _offset_step(w, h, layout)
        w, h = max(1, w // 2), max(1, h // 2)
    return _pack_header(t) + struct.pack('<%dI' % mips, *offsets) + payload


# `fmt` byte per role and layout in the retail files (see tools/tex_headers.py): BM 20 (BC1) / 24 (BC3),
# NM 31 (BC3), MM 25 (BC1). Retail BGRA8 textures are only env maps (40), *_lin (39) and vertex data (14), so BGRA8
# colour maps take 40 and normal / mask maps the linear 39 (not tested in game yet)
DEFAULT_FMT = {('BM', BC1): 20, ('BM', BC3): 24, ('NM', BC3): 31, ('NM', BC1): 25, ('MM', BC1): 25, ('MM', BC3): 31,
               ('BM', BGRA): 40, ('NM', BGRA): 39, ('MM', BGRA): 39}


def default_fmt(name: str, layout: str) -> int:
    base = name.replace('\\', '/').rsplit('/', 1)[-1]
    suf = (base.rsplit('_', 1)[-1].upper() if '_' in base else '')[:2]
    return DEFAULT_FMT.get((suf, layout), {BC1: 20, BC3: 24, BGRA: 40}[layout])


def from_dds(original_tex: bytes, dds: bytes) -> bytes:
    """write a DDS back into an existing TEX, keeping every header field except size / mips / offsets"""
    t = parse(original_tex)
    if t.images != 1:
        raise TexError('write-back into cubemap TEX files is not supported')
    info = parse_dds(dds)
    t.width, t.height, t.mips = info.width, info.height, info.mips
    if t.width > 8191 or t.height > 8191:
        raise TexError('texture larger than 8191 px')
    start = 16 + info.mips * 4
    offsets, pos, w, h = [], start, info.width, info.height
    for _ in range(info.mips):
        offsets.append(pos)
        pos += _offset_step(w, h, info.layout)
        w, h = max(1, w // 2), max(1, h // 2)
    return _pack_header(t) + struct.pack('<%dI' % info.mips, *offsets) + info.payload
