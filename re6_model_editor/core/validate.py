# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 Dimcirui

"""Structural sanity checks for a parsed .mod.

Every rule here holds for all ~5500 retail models of the game (see tools/validate_all.py), so a file that violates
one of them was most likely written wrongly.
"""
from __future__ import annotations

import struct

import numpy as np

from . import mod211 as M
from . import vertex as V


def validate(mod: M.Mod211) -> list:
    """returns a list of problem strings (empty = fine)"""
    errs = []
    nb = mod.boneCount
    nm = len(mod.meshes)
    n_idx = mod.faces.size
    mats = len(mod.materials)
    gids = {struct.unpack_from('<i', mod.groups, i * M.GROUP_SIZE)[0] for i in range(len(mod.groups) // M.GROUP_SIZE)}
    seen_ui = sorted(m.unknownIndex for m in mod.meshes)
    if seen_ui != list(range(1, nm + 1)):
        errs.append('unknownIndex is not a permutation of 1..%d' % nm)
    if sum(m.boundingBoxCount for m in mod.meshes) != len(mod.bboxes):
        errs.append('sum of boundingBoxCount (%d) != number of bounding volumes (%d)'
                    % (sum(m.boundingBoxCount for m in mod.meshes), len(mod.bboxes)))
    if nb:
        parents = [struct.unpack_from('<B', mod.bones, i * M.BONE_SIZE + 1)[0] for i in range(nb)]
        for i, p in enumerate(parents):
            if p != 255 and p >= nb:
                errs.append('bone %d has parent %d out of range' % (i, p))
        if len(mod.remap) != 256:
            errs.append('bone remap table has %d entries' % len(mod.remap))
    box = 0
    for i, m in enumerate(mod.meshes):
        tag = 'mesh %d' % i
        f = V.FORMATS.get(m.blocktype)
        if f is None:
            errs.append('%s: unknown vertex format 0x%08x' % (tag, m.blocktype))
            continue
        if f.stride != m.blockSize:
            errs.append('%s: blockSize %d != format stride %d' % (tag, m.blockSize, f.stride))
        if m.faceCount % 3 or m.faceOffset + m.faceCount > n_idx:
            errs.append('%s: bad face range' % tag)
            continue
        if m.vertexSubMirror != m.vertexSub or m.vertexIndexSub != m.vertexSub + m.vertexCount - 1:
            errs.append('%s: vertexSubMirror / vertexIndexSub inconsistent' % tag)
        start = m.vertexOffset + (m.vertexSub + m.vertexBase) * m.blockSize
        if start < 0 or start + m.vertexCount * m.blockSize > len(mod.vertices):
            errs.append('%s: vertex data outside the vertex buffer' % tag)
            continue
        idx = mod.faces[m.faceOffset:m.faceOffset + m.faceCount].astype(np.int64)
        if len(idx) and (idx.min() < m.vertexSub or idx.max() >= m.vertexSub + m.vertexCount):
            errs.append('%s: face indices outside [vertexSub, vertexSub+count)' % tag)
        if (m.vertexSub + m.vertexCount) > 0xFFFF + 1:
            errs.append('%s: vertexSub + vertexCount exceeds 16 bit' % tag)
        if ((m.flags >> 12) | (m.unk6 << 4)) >= max(mats, 1):
            errs.append('%s: material index %d >= %d materials' % (tag, (m.unk6 << 4) | (m.flags >> 12), mats))
        if (m.flags & 0xFFF) not in gids:
            errs.append('%s: group %d missing from the group table' % (tag, m.flags & 0xFFF))
        wd_n = ((m.weightDynamics & 0xFF) - 1) >> 3
        exp_n = 0 if f.pos == 'f32' else f.influences
        if nb and f.ids is None and wd_n != 1 and f.pos == 's16':
            errs.append('%s: rigid format but weightDynamics says %d influences' % (tag, wd_n))
        if nb and f.ids is not None and not (1 <= wd_n <= f.influences):
            errs.append('%s: weightDynamics influences %d not in 1..%d' % (tag, wd_n, f.influences))
        if nb and f.pos == 's16':
            d = M.decode_vertices(mod, i)
            ids = d['ids']
            if ids.max() >= nb:
                errs.append('%s: bone index %d >= boneCount %d' % (tag, ids.max(), nb))
            w = d['w']
            if f.ids is not None and (w.min() < -2e-3 or np.abs(w.sum(1) - 1).max() > 0.05 + 0.5 * f.influences / 255):
                errs.append('%s: weights do not sum to 1 (max deviation %.3f)' % (tag, np.abs(w.sum(1) - 1).max()))
            lst = [struct.unpack_from('<I', mod.bboxes[box + k], 0)[0] for k in range(m.boundingBoxCount)]
            used = set(np.unique(ids[w > 1e-3]).tolist()) if f.ids is not None else set(np.unique(ids).tolist())
            missing = used - set(lst)
            if missing and m.boundingBoxCount:
                errs.append('%s: bones %s are used but have no bounding volume' % (tag, sorted(missing)[:4]))
        box += m.boundingBoxCount
    tris = mod.faces.size // 3
    head_edges = struct.unpack_from('<I', mod.head, 0x14)[0]
    if head_edges != tris:
        errs.append('header triangle count %d != %d' % (head_edges, tris))
    return errs
