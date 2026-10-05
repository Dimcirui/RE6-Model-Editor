# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 Dimcirui

"""Small numpy block compressor (BC1 / BC3) and mip chain generator used to write .tex files from images.

Endpoints come from the per block colour bounding box (shrunk by 1/16, the classic "range fit"), indices from the
nearest palette entry. Quality is good for game textures and needs no external compressor.
"""
from __future__ import annotations

import numpy as np

from . import tex as T


def _pad4(img: np.ndarray) -> np.ndarray:
    h, w = img.shape[:2]
    ph, pw = (-h) % 4, (-w) % 4
    if ph or pw:
        img = np.pad(img, ((0, ph), (0, pw), (0, 0)), mode='edge')
    return img


def _blocks(img: np.ndarray) -> np.ndarray:
    """(H, W, C) -> (N, 16, C), blocks in row major order, pixels row major inside a block"""
    h, w, c = img.shape
    return img.reshape(h // 4, 4, w // 4, 4, c).transpose(0, 2, 1, 3, 4).reshape(-1, 16, c)


def _expand565(c5: np.ndarray) -> np.ndarray:
    """(N, 3) 5/6/5 bit values -> float 8 bit"""
    r, g, b = c5[:, 0], c5[:, 1], c5[:, 2]
    return np.stack([(r << 3) | (r >> 2), (g << 2) | (g >> 4), (b << 3) | (b >> 2)], 1).astype(np.float32)


def _encode_color(blocks: np.ndarray) -> np.ndarray:
    """(N, 16, >=3) uint8 -> (N, 8) uint8 BC1 blocks (always the 4 colour mode)"""
    rgb = blocks[:, :, :3].astype(np.float32)
    mx = rgb.max(1)
    mn = rgb.min(1)
    inset = (mx - mn) / 16.0
    hi = np.clip(mx - inset, 0, 255)
    lo = np.clip(mn + inset, 0, 255)

    def q(c):
        return np.stack([np.rint(c[:, 0] * 31 / 255), np.rint(c[:, 1] * 63 / 255), np.rint(c[:, 2] * 31 / 255)], 1).astype(np.int32)

    qh, ql = q(hi), q(lo)
    c0 = (qh[:, 0] << 11) | (qh[:, 1] << 5) | qh[:, 2]
    c1 = (ql[:, 0] << 11) | (ql[:, 1] << 5) | ql[:, 2]
    swap = c0 < c1
    c0, c1 = np.where(swap, c1, c0), np.where(swap, c0, c1)
    qh, ql = np.where(swap[:, None], ql, qh), np.where(swap[:, None], qh, ql)
    p0, p1 = _expand565(qh), _expand565(ql)
    pal = np.stack([p0, p1, (2 * p0 + p1) / 3.0, (p0 + 2 * p1) / 3.0], 1)            # (N, 4, 3)
    d = ((rgb[:, :, None, :] - pal[:, None, :, :]) ** 2).sum(-1)                      # (N, 16, 4)
    idx = d.argmin(-1).astype(np.uint32)
    idx[c0 == c1] = 0
    bits = np.zeros(len(blocks), np.uint32)
    for i in range(16):
        bits |= idx[:, i] << np.uint32(2 * i)
    out = np.empty((len(blocks), 8), np.uint8)
    out[:, 0:2] = c0.astype('<u2').view(np.uint8).reshape(-1, 2)
    out[:, 2:4] = c1.astype('<u2').view(np.uint8).reshape(-1, 2)
    out[:, 4:8] = bits.astype('<u4').view(np.uint8).reshape(-1, 4)
    return out


def _encode_alpha(alpha: np.ndarray) -> np.ndarray:
    """(N, 16) uint8 -> (N, 8) uint8 BC4 / DXT5 alpha blocks (8 interpolated values)"""
    a = alpha.astype(np.float32)
    a0 = a.max(1)
    a1 = a.min(1)
    pal = np.empty((len(a), 8), np.float32)
    pal[:, 0], pal[:, 1] = a0, a1
    for k in range(1, 7):
        pal[:, 1 + k] = ((7 - k) * a0 + k * a1) / 7.0
    d = np.abs(a[:, :, None] - pal[:, None, :])
    idx = d.argmin(-1).astype(np.uint64)
    idx[a0 == a1] = 0
    bits = np.zeros(len(a), np.uint64)
    for i in range(16):
        bits |= idx[:, i] << np.uint64(3 * i)
    out = np.empty((len(a), 8), np.uint8)
    out[:, 0] = a0.astype(np.uint8)
    out[:, 1] = a1.astype(np.uint8)
    out[:, 2:8] = bits.astype('<u8').view(np.uint8).reshape(-1, 8)[:, :6]
    return out


def encode_level(img: np.ndarray, layout: str) -> bytes:
    """one mip level (H, W, 4) uint8 RGBA -> block compressed bytes (BC1 / BC3) or BGRA8"""
    if layout == T.BGRA:
        return np.ascontiguousarray(img[:, :, [2, 1, 0, 3]]).tobytes()
    blocks = _blocks(_pad4(img))
    out = []
    step = 65536
    for s in range(0, len(blocks), step):
        b = blocks[s:s + step]
        col = _encode_color(b)
        out.append(np.concatenate([_encode_alpha(b[:, :, 3]), col], 1) if layout == T.BC3 else col)
    return np.concatenate(out).tobytes()


def downsample(img: np.ndarray) -> np.ndarray:
    """box filter to half size (at least 1 x 1)"""
    h, w = img.shape[:2]
    nh, nw = max(1, h // 2), max(1, w // 2)
    f = img[:nh * 2 if h > 1 else 1, :nw * 2 if w > 1 else 1].astype(np.float32)
    if h > 1:
        f = (f[0::2] + f[1::2]) / 2.0
    if w > 1:
        f = (f[:, 0::2] + f[:, 1::2]) / 2.0
    return np.rint(f).astype(np.uint8)


def mip_chain(img: np.ndarray, levels: int = 0) -> list:
    # retail chains stop at 2 x 2: floor(log2(longest side)) levels
    if levels == 0:
        levels = max(1, int(max(img.shape[:2])).bit_length() - 1)
    out = [img]
    while len(out) < levels:
        out.append(downsample(out[-1]))
    return out


def build_tex(img: np.ndarray, layout: str, fmt: int, mips: int = 0) -> bytes:
    """(H, W, 4) uint8 RGBA (first row = top) -> .tex file bytes with a full mip chain"""
    chain = mip_chain(img, mips)
    h, w = img.shape[:2]
    if not (0 < w <= 8191 and 0 < h <= 8191):
        raise T.TexError('texture size %dx%d is not supported' % (w, h))
    payload = b''.join(encode_level(m, layout) for m in chain)
    return T.assemble(w, h, len(chain), layout, fmt, payload)
