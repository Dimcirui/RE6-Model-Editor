# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 Dimcirui

"""Give the bones of one skeleton the names of another one by position (no Blender needed).

Used for a model that was exported under an older bone numbering (the physics bones were renamed in a later version): the same
physical bone has to get the id the newer skeleton gives it, so the .ctc / .ccl of the newer version fits. Positions are in cm.

The two skeletons may sit at a different height (a whole-model shift, or an armature object that was moved); a bone also counts
as a match when it lies where the other one is *without* the shift, so bones that were never shifted match as well.
"""
import re

import numpy as np

BONE_NAME_RE = re.compile(r'^RE6Bone_(\d{3})$')


def detect_shift(names_a, pos_a, names_b, pos_b, near=12.0):
    """median of (a - b) over the bones that exist under the same name in both and are less than `near` cm apart"""
    ib = {n: i for i, n in enumerate(names_b)}
    deltas = []
    for i, n in enumerate(names_a):
        j = ib.get(n)
        if j is not None:
            d = np.asarray(pos_a[i], float) - np.asarray(pos_b[j], float)
            if np.linalg.norm(d) < near:
                deltas.append(d)
    return np.median(np.array(deltas), axis=0) if deltas else np.zeros(3)


def match(names_a, pos_a, names_b, pos_b, shift, tol=0.5):
    """one-to-one matching a -> b, the closest pairs first (a pair with the same name wins a tie).

    Returns ({a name: b name}, [unmatched a names], [unmatched b names])."""
    A = np.asarray(pos_a, float).reshape(-1, 3)
    B = np.asarray(pos_b, float).reshape(-1, 3)
    shift = np.asarray(shift, float)
    if len(A) == 0 or len(B) == 0:
        return {}, list(names_a), list(names_b)
    d = np.minimum(np.linalg.norm(A[:, None, :] - (B[None, :, :] + shift), axis=2), np.linalg.norm(A[:, None, :] - B[None, :, :], axis=2))
    pairs = sorted(((d[i, j] - (1e-3 if names_a[i] == names_b[j] else 0.0), i, j) for i, j in np.argwhere(d < tol)))
    used_a, used_b, mapping = set(), set(), {}
    for _d, i, j in pairs:
        if i in used_a or j in used_b:
            continue
        used_a.add(i)
        used_b.add(j)
        mapping[names_a[i]] = names_b[j]
    return (mapping, [n for k, n in enumerate(names_a) if k not in used_a], [n for k, n in enumerate(names_b) if k not in used_b])


def plan(mapping, unmatched, taken=(), park_start=500):
    """{old name: final name} for every bone: matched ones get the name of their partner, the others are parked under
    RE6Bone_<park_start...> (skipping names that are in use). Raises ValueError when the result would not be one-to-one."""
    final = dict(mapping)
    used = set(mapping.values()) | set(taken)
    k = park_start
    for n in sorted(unmatched, key=lambda s: (int(BONE_NAME_RE.match(s).group(1)) if BONE_NAME_RE.match(s) else 10 ** 9, s)):
        while 'RE6Bone_%03d' % k in used:
            k += 1
        final[n] = 'RE6Bone_%03d' % k
        used.add(final[n])
        k += 1
    if len(set(final.values())) != len(final):
        raise ValueError('the new names are not unique')
    return final
