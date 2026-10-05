# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 Dimcirui

"""Data driven RE6 vertex formats (MOD v211).

Every vertex starts with ``pos8`` = int16 x,y,z + 2 bytes (``pw``), positions are ``s16 / 32767 * scale``.

pw roles
    'bone'  u8 bone index in byte 6 (rigid, weightDynamics 9), byte 7 preserved
    'w0'    int16 / 32767 = weight of slot 0 (the largest one)
    'pad'   unused (shadow copies of skinned meshes carry all weights elsewhere)

id kinds     u8 (K bytes) | half (K halves holding the index as a number, e.g. 41.0) | u16f (u16 = 0x8000 | index)
weight kinds
    'w2'   W0 in pos.w, W1 = 1 - W0                                   (2 bones)
    'w4h'  W0 in pos.w, W1/W2 half floats, W3 = 1 - W0 - W1 - W2       (4 bones)
    'w8'   W0 in pos.w, then u8 weights at 12..15 and 28..30 (/255)   (8 bones)
    'u8'   K u8 weights (/255) at an offset (shadow copies)

Normals / tangents are u8 x3 biased (b/255*2-1); the 4th byte of the normal is kept as ``nw``, the 4th byte of the tangent
is the bitangent sign (0 -> -1, otherwise +1) and kept as ``tw``.  Bytes not covered by any component are kept in
``residual`` so that decode -> encode is lossless.

Every hash is ``(jamcrc32(official name) & 0xFFFFF) << 12 | code``: an entry of the fixed input layout table of the game (codes
0x013 .. 0x03e, 40 used by the retail data). A layout that is not in that table cannot be drawn, so new layouts can not be made
up; ``compose`` picks among the existing ones. The names of ``Fmt`` are descriptive, ``official_name`` gives the game's.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass(frozen=True)
class Fmt:
    name: str
    stride: int
    pw: str                      # 'bone' | 'w0' | 'pad'
    nrm: int = 8
    tan: int | None = None
    uvs: tuple = ()
    ids: tuple | None = None     # (kind, offset, K)
    wts: tuple | None = None     # (kind, offset_or_None, K)
    col: int | None = None
    pos: str = 's16'             # 's16' (scaled by the model scale) | 'f32' (static, skeleton-less models)
    extra: bool = False          # carries more data than the decoded fields (the _4M layouts); never chosen automatically

    @property
    def influences(self):
        return 1 if self.ids is None else self.ids[2]


def _w8_base(name, stride, uvs=(24,), col=None):
    return Fmt(name, stride, 'w0', 8, 32, uvs, ('u8', 16, 8), ('w8', None, 8), col)


FORMATS = {
    0xb0983013: Fmt('Rigid', 12, 'bone'),
    0xa8fab018: Fmt('Rigid1UV', 20, 'bone', 8, 12, (16,)),
    0xcbf6c01a: Fmt('Rigid1UVColor', 24, 'bone', 8, 12, (16,), col=20),
    0x667b1019: Fmt('Rigid2UV', 24, 'bone', 8, 12, (16, 20)),
    0xd877801b: Fmt('Rigid4UV', 32, 'bone', 8, 12, (16, 20, 24, 28)),
    0x0cb68015: Fmt('Skin4wtShadow', 20, 'pad', 16, None, (), ('u8', 8, 4), ('u8', 12, 4)),
    0xa320c016: Fmt('Skin8wtShadow', 28, 'pad', 24, None, (), ('u8', 8, 8), ('u8', 16, 8)),
    0xdb7da014: Fmt('Skin2wtShadow', 16, 'w0', 8, None, (), ('u16f', 12, 2), ('w2', None, 2)),
    0xc31f201c: Fmt('Skin2wt1UV', 24, 'w0', 8, 12, (16,), ('half', 20, 2), ('w2', None, 2)),
    0xa013501e: Fmt('Skin2wt1UVColor', 28, 'w0', 8, 12, (16,), ('half', 20, 2), ('w2', None, 2), col=24),
    0x0d9e801d: Fmt('Skin2wt2UV', 28, 'w0', 8, 12, (16, 24), ('half', 20, 2), ('w2', None, 2)),
    0xb392101f: Fmt('Skin2wt4UV', 36, 'w0', 8, 12, (20, 24, 28, 32), ('half', 16, 2), ('w2', None, 2)),
    0x14d40020: Fmt('Skin4wt1UV', 28, 'w0', 8, 12, (20,), ('u8', 16, 4), ('w4h', 24, 4)),
    0x64593023: Fmt('Skin4wt2UV', 40, 'w0', 8, 12, (20, 32), ('u8', 16, 4), ('w4h', 24, 4)),
    0xda55a021: Fmt('Skin4wt2UVb', 32, 'w0', 8, 12, (20, 28), ('u8', 16, 4), ('w4h', 24, 4)),
    0x77d87022: Fmt('Skin4wt1UVColor', 32, 'w0', 8, 12, (20,), ('u8', 16, 4), ('w4h', 24, 4), col=28),
    0x2f55c03d: Fmt('Skin4wt1UVBlend', 64, 'w0', 8, 12, (20,), ('u8', 16, 4), ('w4h', 24, 4), extra=True),  # 28..63 raw
    0xbb424024: _w8_base('Skin8wt1UV', 36),
    0x75c3e025: _w8_base('Skin8wt2UV', 40, (24, 36)),
    0xd84e3026: _w8_base('Skin8wt1UVColor', 40, col=36),
    0xcbcf7027: _w8_base('Skin8wt2UVb', 48, (24, 40)),
}


def _static(name, stride, tan, uvs, col=None, extra=False):
    return Fmt(name, stride, 'pad', 12, tan, uvs, col=col, pos='f32', extra=extra)


# skeleton-less (stage / effect / event) models: float32 positions, no skinning
FORMATS.update({
    0xa7d7d036: _static('Static1UV', 20, None, (16,)),
    0x207d6037: _static('Static1UVColor', 24, None, (16,), 20),
    0xd1a47038: _static('Static2UV', 24, None, (16, 20)),
    0xc66fa03a: _static('Static2UVb', 24, None, (16, 20)),
    0xd8297028: _static('Static1UVTan', 24, 16, (20,)),
    0x49b4f029: _static('Static1UVTanColor', 28, 16, (20,), 24),
    0x5e7f202c: _static('Static2UVTan', 28, 16, (20, 24)),
    0xafa6302d: _static('Static2UVTanb', 28, 16, (20, 24)),
    0xa14e003c: _static('Static2UVColor', 28, None, (16, 20), 24),
    0x2082f03b: _static('Static3UV', 28, None, (16, 20, 24)),
    0x926fd02e: _static('Static2UVTanColor', 32, 16, (20, 24), 28),
    0x9399c033: _static('Static2UVTanColorb', 32, 16, (20, 24), 28),
    0xb86de02a: _static('Static3UVTan', 32, 16, (20, 24, 28)),
    0x747d1031: _static('Static3UVTanb', 32, 16, (20, 24, 28)),
    0x12553032: _static('Static3UVTanc', 32, 16, (20, 24, 28)),
    0x63b6c02f: _static('Static4UVTan', 36, 16, (20, 24, 28, 32)),
    0x37a4e035: _static('Static4UVTanb', 36, 16, (20, 24, 28, 32)),
    0xb6681034: _static('Static3UVTanColor', 36, 16, (20, 24, 32), 28),
    0x4325a03e: _static('Static1UVTanExt', 64, 16, (20,), extra=True),  # 24..63 raw (extra data, copy of the normal at 52)
})


# ------------------------------------------------------------------ names and components

def official_name(h: int) -> str:
    """the game's name of a layout (IASkinTB4wt ...), from the shader object name table"""
    from .shader_names import NAMES
    return NAMES.get(h >> 12, '%08x' % h)


def kind_of(f: Fmt) -> str:
    """'static' (no skeleton, float positions), 'rigid' (one bone per vertex) or 'skin'"""
    return 'static' if f.pos == 'f32' else ('rigid' if f.ids is None else 'skin')


def components(f: Fmt) -> tuple:
    """(skinned, weights, uv count, colour, tangent, extra): what a layout holds; weights is 0 for static layouts"""
    kind = kind_of(f)
    return (kind != 'static', 0 if kind == 'static' else f.influences, len(f.uvs), f.col is not None, f.tan is not None,
            f.extra)


def describe(h: int) -> str:
    """'4 weights, 1 UV, tangent, 28 bytes'"""
    f = FORMATS[h]
    skinned, weights, nuv, col, tan, extra = components(f)
    parts = ['%d weight%s' % (weights, 's' if weights > 1 else '') if skinned else 'static']
    parts.append('%d UV%s' % (nuv, 's' if nuv != 1 else '') if nuv else 'no UV (shadow / bridge)')
    if col:
        parts.append('color')
    if tan:
        parts.append('tangent')
    if extra:
        parts.append('extra data')
    parts.append('%d bytes' % f.stride)
    return ', '.join(parts)


def compose(skinned: bool, weights: int, nuv: int, col: bool, tan: bool, extra: bool = False) -> list:
    """the layouts of the game that hold exactly these components, smallest first (several layouts can share them;
    their extra letters N / L / A are not decoded and stay zero for new data)"""
    want = (skinned, weights if skinned else 0, nuv, col, tan, extra)
    return sorted((h for h, f in FORMATS.items() if components(f) == want), key=lambda h: (FORMATS[h].stride, h & 0xFFF))


def nearest(skinned: bool, weights: int, nuv: int, col: bool, tan: bool, extra: bool = False, count: int = 3) -> list:
    """the closest existing layouts of the same kind (skinned or static) when compose() finds none"""
    def cost(h):
        s, w, u, c, t, x = components(FORMATS[h])
        return ((w < weights) * 100 + abs(w - weights) * 2 + (u < nuv) * 50 + abs(u - nuv) * 3 + (c != col) * 5
                + (t != tan) * 4 + (x != extra) * 8, FORMATS[h].stride)
    same = [h for h, f in FORMATS.items() if components(f)[0] == skinned]
    return sorted(same, key=cost)[:count]


def fit_problems(h: int, skeleton: bool, influences: int, nuv: int, has_col: bool, shadow: bool = False) -> list:
    """why a mesh does not fit layout h (empty = it fits); a layout with more fields than the data is fine, the encoder
    fills them (UV 0, colour white, unused weights 0)"""
    f = FORMATS.get(h)
    if f is None:
        return ['unknown vertex format %08x' % h]
    out = []
    if skeleton != (f.pos == 's16'):
        out.append('%s is a %s layout, the model %s a skeleton' % (official_name(h), 'skinned' if f.pos == 's16' else
                                                                   'static', 'has' if skeleton else 'has no'))
    if skeleton and influences > f.influences:
        out.append('%d bone influences, %s holds %d' % (influences, official_name(h), f.influences))
    if nuv > len(f.uvs) and not shadow:
        out.append('%d UV maps, %s holds %d' % (nuv, official_name(h), len(f.uvs)))
    if has_col and f.col is None:
        out.append('vertex colors, %s has none' % official_name(h))
    return out

# ------------------------------------------------------------------ helpers


def _u8_from(x):
    return np.clip(np.rint((np.asarray(x, np.float64) + 1.0) * 0.5 * 255.0), 0, 255).astype(np.uint8)


def _view(raw, o, dt, cols):
    return np.ascontiguousarray(raw[:, o:o + np.dtype(dt).itemsize * cols]).view(dt).reshape(len(raw), cols)


def _put(out, o, arr):
    a = np.ascontiguousarray(arr)
    out[:, o:o + a.dtype.itemsize * (a.shape[1] if a.ndim > 1 else 1)] = a.view(np.uint8).reshape(len(out), -1)


def _covered(f: Fmt):
    """byte mask of everything a decode / encode touches"""
    m = np.zeros(f.stride, bool)
    m[0:12 if f.pos == 'f32' else 6] = True
    if f.pos == 's16':
        m[6:8] = f.pw != 'pad'
    m[f.nrm:f.nrm + 3] = True
    m[f.nrm + 3] = True
    if f.tan is not None:
        m[f.tan:f.tan + 4] = True
    for o in f.uvs:
        m[o:o + 4] = True
    if f.ids:
        k, o, K = f.ids
        m[o:o + {'u8': K, 'half': 2 * K, 'u16f': 2 * K}[k]] = True
    if f.wts:
        k, o, K = f.wts
        if k == 'w4h':
            m[o:o + 4] = True
        elif k == 'u8':
            m[o:o + K] = True
        elif k == 'w8':
            m[12:16] = True
            m[28:31] = True
    if f.col is not None:
        m[f.col:f.col + 4] = True
    return m


def decode(f: Fmt, raw: np.ndarray, scale: float) -> dict:
    """raw (n, stride) uint8 -> canonical dict (see module docstring)."""
    n = len(raw)
    if f.pos == 'f32':
        d = dict(pos=_view(raw, 0, '<f4', 3).astype(np.float64))
    else:
        d = dict(pos=_view(raw, 0, '<i2', 3).astype(np.float64) / 32767.0 * scale)
    if f.pw == 'bone':
        d['bone'] = raw[:, 6].astype(int)
        d['pw_hi'] = raw[:, 7].copy()
    d['nrm'] = raw[:, f.nrm:f.nrm + 3].astype(np.float64) / 255.0 * 2 - 1
    d['nw'] = raw[:, f.nrm + 3].copy()
    if f.tan is not None:
        d['tan'] = raw[:, f.tan:f.tan + 3].astype(np.float64) / 255.0 * 2 - 1
        d['tw'] = raw[:, f.tan + 3].copy()
        d['tsign'] = np.where(d['tw'] == 0, -1.0, 1.0)
    d['uv'] = [_view(raw, o, '<f2', 2).astype(np.float32) for o in f.uvs]
    if f.col is not None:
        d['col'] = raw[:, f.col:f.col + 4].copy()
    # skinning
    if f.ids is None:
        d['ids'] = d['bone'][:, None] if 'bone' in d else np.zeros((n, 1), int)
        d['w'] = np.ones((n, 1))
    else:
        kind, o, K = f.ids
        if kind == 'u8':
            ids = raw[:, o:o + K].astype(int)
        elif kind == 'half':
            ids = np.rint(_view(raw, o, '<f2', K).astype(np.float64)).astype(int)
        else:  # u16f
            ids = (_view(raw, o, '<u2', K).astype(int) & 0x7FFF)
        d['ids'] = ids
        wk, wo, WK = f.wts
        w0 = _view(raw, 6, '<i2', 1)[:, 0].astype(np.float64) / 32767.0 if f.pw == 'w0' else None
        if wk == 'w2':
            w = np.stack([w0, 1 - w0], 1)
        elif wk == 'w4h':
            h = _view(raw, wo, '<f2', 2).astype(np.float64)
            w = np.stack([w0, h[:, 0], h[:, 1], 1 - w0 - h[:, 0] - h[:, 1]], 1)
        elif wk == 'w8':
            w = np.concatenate([w0[:, None], raw[:, 12:16] / 255.0, raw[:, 28:31] / 255.0], 1)
        else:
            w = raw[:, wo:wo + WK].astype(np.float64) / 255.0
        d['w'] = w
    keep = ~_covered(f)
    res = np.zeros_like(raw)
    res[:, keep] = raw[:, keep]
    d['residual'] = res
    return d


def encode(f: Fmt, d: dict, scale: float) -> np.ndarray:
    """canonical dict -> (n, stride) uint8.  Missing optional keys default to zero / neutral values."""
    pos = np.asarray(d['pos'], np.float64)
    n = len(pos)
    res = d.get('residual')
    out = np.array(res, np.uint8, copy=True) if res is not None and np.shape(res) == (n, f.stride) \
        else np.zeros((n, f.stride), np.uint8)
    if f.pos == 'f32':
        _put(out, 0, pos.astype('<f4'))
    else:
        q = np.rint(pos / scale * 32767.0)
        if n and (q.max() > 32768 or q.min() < -32769):
            raise ValueError('vertex outside the quantisation range (+-%.1f model units)' % scale)
        _put(out, 0, np.clip(q, -32768, 32767).astype('<i2'))
    if f.pw == 'bone':
        out[:, 6] = np.asarray(d['bone'], np.uint8)
        out[:, 7] = d.get('pw_hi', np.zeros(n, np.uint8))
    nrm = np.asarray(d['nrm'], np.float64)
    out[:, f.nrm:f.nrm + 3] = _u8_from(nrm)
    out[:, f.nrm + 3] = d.get('nw', np.full(n, 254, np.uint8))
    if f.tan is not None:
        out[:, f.tan:f.tan + 3] = _u8_from(d['tan'])
        if 'tw' in d:
            out[:, f.tan + 3] = d['tw']
        else:
            out[:, f.tan + 3] = np.where(np.asarray(d.get('tsign', np.ones(n))) < 0, 0, 254)
    uvs = d.get('uv', [])
    for k, o in enumerate(f.uvs):
        uv = uvs[k] if k < len(uvs) else np.zeros((n, 2), np.float32)
        _put(out, o, np.asarray(uv, '<f2'))
    if f.col is not None:
        out[:, f.col:f.col + 4] = d.get('col', np.full((n, 4), 255, np.uint8))
    if f.ids is not None:
        kind, o, K = f.ids
        ids = np.asarray(d['ids'], int)
        w = np.asarray(d['w'], np.float64)
        if ids.shape[1] < K:            # pad with the first id / zero weight
            ids = np.concatenate([ids, np.repeat(ids[:, :1], K - ids.shape[1], 1)], 1)
            w = np.concatenate([w, np.zeros((n, K - w.shape[1]))], 1)
        if kind == 'u8':
            out[:, o:o + K] = ids[:, :K].astype(np.uint8)
        elif kind == 'half':
            _put(out, o, ids[:, :K].astype('<f2'))
        else:
            _put(out, o, (ids[:, :K] | 0x8000).astype('<u2'))
        wk, wo, WK = f.wts
        if f.pw == 'w0':
            _put(out, 6, np.rint(w[:, 0] * 32767).astype('<i2'))
        if wk == 'w4h':
            _put(out, wo, w[:, 1:3].astype('<f2'))
        elif wk == 'w8':
            out[:, 12:16] = np.clip(np.rint(w[:, 1:5] * 255), 0, 255).astype(np.uint8)
            out[:, 28:31] = np.clip(np.rint(w[:, 5:8] * 255), 0, 255).astype(np.uint8)
        elif wk == 'u8':
            b = np.clip(np.rint(w[:, :WK] * 255), 0, 255).astype(np.int64)
            b[:, 0] += 255 - b.sum(1)         # keep the sum at exactly 255
            out[:, wo:wo + WK] = np.clip(b, 0, 255).astype(np.uint8)
    return out
