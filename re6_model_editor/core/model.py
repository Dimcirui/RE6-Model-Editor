# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 Dimcirui

"""Editable, bpy-free representation of an RE6 model and the conversions to / from :class:`mod211.Mod211`.

The Blender layer only talks to :class:`Model` / :class:`Part` / :class:`Bone`, so everything here can be tested
outside Blender (see ``tools/roundtrip_model.py``).

Conventions
    * all positions are **world space** floats in RE6 units (cm), Y up (the Blender layer applies the usual
      "rotate 90 deg X, scale 0.01" import matrix);
    * matrices use the file's row-vector convention (translation in the last row);
    * per vertex data (normal / tangent / uv / colour / weights) - the exporter of the Blender layer has to split
      vertices where a Blender mesh needs different values per corner.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field

import numpy as np

from . import mod211 as M
from . import vertex as V

SHADOW_MASK = 0x1020
DEFAULT_LOD_DIST = (1000, 3000, 1)


# --------------------------------------------------------------------------- data classes
@dataclass
class Bone:
    index: int
    fn_id: int                    # bone "function" id (u8), also the key of the remap table
    parent: int                   # bone index or 255
    mirror: int                   # index of the symmetric bone (own index on the x = 0 plane, 255 when there is none)
    local: np.ndarray             # 4x4 float64, row-vector convention
    unk: int = 0
    radius: float | None = None   # influence radius, computed on export when None
    length: float | None = None   # |local translation| as stored in the file (recomputed when it no longer matches)

    @property
    def name(self):
        return 'RE6Bone_%03d' % self.fn_id


@dataclass
class Part:
    """One entry of the mesh table."""
    name: str
    pos: np.ndarray                       # (n,3) world
    faces: np.ndarray                     # (m,3) local vertex indices
    nrm: np.ndarray | None = None         # (n,3)
    tan: np.ndarray | None = None         # (n,3)
    tsign: np.ndarray | None = None       # (n,) +-1
    uvs: list = field(default_factory=list)   # list of (n,2) float32
    col: np.ndarray | None = None         # (n,4) uint8
    ids: np.ndarray | None = None         # (n,K) bone indices        (skeleton models only)
    w: np.ndarray | None = None           # (n,K) weights
    material: int = 0                     # index into Model.materials  ((unk6 << 4) | (flags >> 12) in the file)
    group: int = 0
    lod: int = 255                        # LOD bit mask (1 = LOD1, 2 = LOD2, 252 = LOD3+, 255 = all)
    lod_mask: int = 0xFFFF                # render pass mask (0x1020 = shadow-only copy)
    unk3: int = 3
    wd_hi: int = 0                        # high byte of weightDynamics (opaque)
    wd_flags: int = 0                     # bits 1-2 of the low byte (opaque)
    wd_infl: int = 0                      # influence count declared by the file (kept when still large enough)
    fmt: int | None = None                # vertex format hash (None = choose automatically)
    meta: dict = field(default_factory=dict)   # opaque per vertex bytes of the original file (nw, tw, residual)

    @property
    def is_shadow(self):
        return self.lod_mask == SHADOW_MASK

    @property
    def vertex_count(self):
        return len(self.pos)


@dataclass
class Model:
    bones: list
    parts: list
    materials: list                        # u32 material name hashes
    groups: dict                           # group id -> (cx, cy, cz, radius) raw sphere entry
    lod_dist: tuple = DEFAULT_LOD_DIST
    remap: bytes = b''
    trailer: bytes = b''
    template: M.Mod211 | None = None       # original file this model was read from (used to keep opaque data)
    tail_pad: int = 0                      # see Mod211.tail_pad

    @property
    def has_skeleton(self):
        return len(self.bones) > 0


# --------------------------------------------------------------------------- read
def _snapshot(p):
    """copies of the attributes a vertex is compared with on export (unchanged vertices keep their file bytes)"""
    return dict(pos=p.pos.copy(), nrm=p.nrm.copy(), tan=None if p.tan is None else p.tan.copy(),
                tsign=None if p.tsign is None else p.tsign.copy(), uvs=[u.copy() for u in p.uvs],
                col=None if p.col is None else p.col.copy(), ids=None if p.ids is None else p.ids.copy(),
                w=None if p.w is None else p.w.copy())


def _unchanged_rows(p):
    """boolean mask of vertices whose attributes still equal the imported ones (None when no comparison possible)"""
    o = p.meta.get('orig')
    if o is None or len(o['pos']) != len(p.pos):
        return None
    same = np.all(o['pos'] == p.pos, axis=1) & np.all(o['nrm'] == p.nrm, axis=1)
    if o['tan'] is not None and p.tan is not None:
        same &= np.all(o['tan'] == p.tan, axis=1)
    if o['tsign'] is not None and p.tsign is not None:
        same &= o['tsign'] == p.tsign
    if len(o['uvs']) != len(p.uvs):
        return None
    for a, b in zip(o['uvs'], p.uvs):
        same &= np.all(a == b, axis=1)
    if o['col'] is not None and p.col is not None:
        same &= np.all(o['col'] == p.col, axis=1)
    if o['ids'] is not None and p.ids is not None:
        same &= np.all(o['ids'] == p.ids, axis=1) & np.all(o['w'] == p.w, axis=1)
    return same


def from_mod(mod: M.Mod211, include_shadow=True, lods=None) -> Model:
    """Decode a whole file.  ``lods`` = set of lod masks to keep (None = everything)."""
    skel = mod.boneCount > 0
    origin = mod.model_origin if skel else np.zeros(3)
    bones = []
    if skel:
        for i, b in enumerate(mod.bone_table()):
            bones.append(Bone(i, b[0], b[1], b[2], mod.lmat[i].astype(np.float64), b[3], float(b[4]), float(b[5])))
    parts = []
    counters = {}
    box_at, acc = [], 0
    for x in mod.meshes:
        box_at.append(acc)
        acc += x.boundingBoxCount
    for i, x in enumerate(mod.meshes):
        if not include_shadow and x.lodMask == SHADOW_MASK:
            continue
        if lods is not None and x.lod not in lods:
            continue
        d = M.decode_vertices(mod, i)
        group = x.flags & 0xFFF
        k = counters.get(group, 0)
        counters[group] = k + 1
        ids = d['ids'] if skel else None
        w = None
        if skel:
            w = np.where(d['w'] < 1e-3, 0.0, d['w'])      # half precision complement noise
        p = Part(name='Group_%d_Sub_%d' % (group, k),
                 pos=d['pos'] - origin if skel else d['pos'],
                 faces=mod.mesh_indices(i).astype(np.int64),
                 nrm=d['nrm'], tan=d.get('tan'), tsign=d.get('tsign'), uvs=list(d['uv']), col=d.get('col'),
                 ids=ids, w=w, material=(x.unk6 << 4) | (x.flags >> 12), group=group, lod=x.lod, lod_mask=x.lodMask,
                 unk3=x.unk3, wd_hi=x.weightDynamics >> 8, wd_flags=x.weightDynamics & 0x06,
                 wd_infl=((x.weightDynamics & 0xFF) - 1) >> 3,
                 fmt=x.blocktype, meta=dict(nw=d['nw'], tw=d.get('tw'), residual=d['residual'], ids_raw=ids, raw=mod.mesh_vertex_bytes(i).copy(),
                                            orig=None, bbox=mod.bboxes[box_at[i]:box_at[i] + x.boundingBoxCount],
                                            wd_orig=x.weightDynamics, shadow_fmt=(V.FORMATS[x.blocktype].tan is None and not V.FORMATS[x.blocktype].uvs), ui=x.unknownIndex,
                                            tail=x.tail, index=i))
        p.meta['orig'] = _snapshot(p)
        parts.append(p)
    groups = {}
    for gi in range(len(mod.groups) // M.GROUP_SIZE):
        g = struct.unpack_from('<i3I4f', mod.groups, gi * M.GROUP_SIZE)
        groups[g[0]] = tuple(g[4:8])
    hd = mod.head
    dist = struct.unpack_from('<III', hd, 0x70) if len(hd) >= 0x7C else DEFAULT_LOD_DIST
    return Model(bones, parts, list(mod.materials), groups, tuple(dist), bytes(mod.remap), bytes(mod.trailer), mod, mod.tail_pad)


# --------------------------------------------------------------------------- helpers for writing
def normalise_influences(ids, w, k_out, tol=2e-3):
    """(n,K) ids / weights -> (n,k_out).

    Duplicate ids are merged (first position wins), weights <= 0 dropped, at most ``k_out`` influences are kept
    (the heaviest ones, original slot order preserved), the weights are renormalised only when they do not sum to 1
    already and unused slots are padded with the first id / zero weight.  Returns (ids, w, max_used)."""
    ids = np.asarray(ids, np.int64)
    w = np.maximum(np.asarray(w, np.float64), 0.0)
    n, K = ids.shape
    oi = np.zeros((n, k_out), np.int64)
    ow = np.zeros((n, k_out))
    used = 1
    for j in range(n):
        acc = {}
        for b, x in zip(ids[j].tolist(), w[j].tolist()):
            if x > 0:
                acc[b] = acc.get(b, 0.0) + x
        if not acc:
            acc = {int(ids[j, 0]): 1.0}
        items = list(acc.items())
        if len(items) > k_out:
            keep = sorted(sorted(range(len(items)), key=lambda i: -items[i][1])[:k_out])
            items = [items[i] for i in keep]
        tot = sum(x for _, x in items)
        if abs(tot - 1.0) > tol:
            items = [(b, x / tot) for b, x in items]
        used = max(used, len(items))
        first = items[0][0]
        for k in range(k_out):
            if k < len(items):
                oi[j, k], ow[j, k] = items[k]
            else:
                oi[j, k], ow[j, k] = first, 0.0
    return oi, ow, used


def influence_count(ids, w, limit=8):
    """maximum number of distinct bones with weight > 0 over all vertices (fast path for rigid data)."""
    if ids is None:
        return 0
    ids = np.asarray(ids)
    w = np.asarray(w)
    if ids.shape[1] == 1:
        return 1
    m = 1
    for j in range(len(ids)):
        s = {b for b, x in zip(ids[j].tolist(), w[j].tolist()) if x > 1e-6}
        m = max(m, len(s))
        if m >= limit:
            break
    return m


def _signature(f: V.Fmt):
    kind = 'static' if f.pos == 'f32' else ('rigid' if f.ids is None else 'skin')
    shadow = f.tan is None and not f.uvs and f.col is None
    return kind, shadow, (f.influences if kind == 'skin' else 1), len(f.uvs), f.col is not None


def _format_candidates():
    """signature -> format hash (first defined wins, so the 'b' / 'c' duplicates are never picked)"""
    table = {}
    for h, f in V.FORMATS.items():
        if f.extra:
            continue
        table.setdefault(_signature(f), h)
    return table


_CANDIDATES = _format_candidates()


def declared_influences(slots: int, n_inf: int) -> int:
    """Influence count written into the weightDynamics of a mesh whose vertex format has `slots` weight slots (1 + 8 * count).

    The weight field has to match the layout (the game picks its skinning from it). Retail pairs every format with a fixed range:
    2 slot formats always 2, 4 slot formats 1..4 (the real count), 8 slot formats 5..8 and never 4 or less (smaller meshes get a
    4 slot format), so a mesh that is forced into an 8 slot format with only 4 influences is declared with 5.
    """
    low = {2: 2, 8: 5}.get(slots, 1)
    return max(low, min(max(1, n_inf), slots))


def choose_format(skeleton: bool, n_inf: int, n_uv: int, has_col: bool, shadow: bool) -> int:
    """smallest known vertex format that can hold the data"""
    kind = 'static' if not skeleton else ('rigid' if n_inf <= 1 else 'skin')
    best = None
    for (k, sh, K, nuv, col), h in _CANDIDATES.items():
        if k != kind or sh != shadow or (kind == 'skin' and K < n_inf):
            continue
        if not shadow and (nuv < max(n_uv, 1) or col != has_col):
            continue
        cand = (V.FORMATS[h].stride, h)
        if best is None or cand < best:
            best = cand
    if best is None and has_col and not shadow:
        return choose_format(skeleton, n_inf, n_uv, False, shadow)
    if best is None:
        raise ValueError('no vertex format for skeleton=%s influences=%d uv=%d colour=%s shadow=%s'
                         % (skeleton, n_inf, n_uv, has_col, shadow))
    return best[1]


def compute_tangents(pos, nrm, uv, faces):
    """Tangents the way the game data has them: the normalised dP/du of every triangle (uv as stored, V pointing
    down) accumulated per vertex, made orthogonal to the normal.  The bitangent sign is -sign(det of the uv
    Jacobian), accumulated per vertex.  Returns (tangent (n,3), sign (n,))."""
    pos = np.asarray(pos, np.float64)
    uv = np.asarray(uv, np.float64)
    f = np.asarray(faces, np.int64)
    e1 = pos[f[:, 1]] - pos[f[:, 0]]
    e2 = pos[f[:, 2]] - pos[f[:, 0]]
    d1 = uv[f[:, 1]] - uv[f[:, 0]]
    d2 = uv[f[:, 2]] - uv[f[:, 0]]
    det = d1[:, 0] * d2[:, 1] - d2[:, 0] * d1[:, 1]
    ok = np.abs(det) > 1e-12
    safe = np.where(ok, det, 1.0)
    dpdu = (e1 * d2[:, 1:2] - e2 * d1[:, 1:2]) / safe[:, None]
    ln = np.linalg.norm(dpdu, axis=1, keepdims=True)
    dpdu = np.where(ok[:, None] & (ln > 1e-12), dpdu / np.maximum(ln, 1e-12), 0.0)
    acc = np.zeros_like(pos)
    sgn = np.zeros(len(pos))
    for k in range(3):
        np.add.at(acc, f[:, k], dpdu)
        np.add.at(sgn, f[:, k], -np.sign(det) * ok)
    n = np.asarray(nrm, np.float64)
    n = n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-9)
    t = acc - n * (acc * n).sum(1, keepdims=True)
    lt = np.linalg.norm(t, axis=1, keepdims=True)
    fallback = np.cross(n, np.array([0.0, 1.0, 0.0]))
    fl = np.linalg.norm(fallback, axis=1, keepdims=True)
    fallback = np.where(fl > 1e-6, fallback / np.maximum(fl, 1e-9), np.cross(n, np.array([1.0, 0.0, 0.0])))
    t = np.where(lt > 1e-6, t / np.maximum(lt, 1e-9), fallback)
    return t, np.where(sgn < 0, -1.0, 1.0)


def _bone_world(bones):
    n = len(bones)
    W = np.zeros((n, 4, 4))
    for b in bones:
        W[b.index] = b.local if b.parent == 255 else b.local @ W[b.parent]
    return W


def bind_positions(bones):
    return _bone_world(bones)[:, 3, :3]


def compute_bone_radius(bones, parts):
    """bone influence radius = farthest vertex that is weighted to the bone (see docs)"""
    bw = bind_positions(bones)
    rad = np.zeros(len(bones))
    for p in parts:
        if p.ids is None:
            continue
        for k in range(p.ids.shape[1]):
            wk = p.w[:, k] > 1e-4
            if not wk.any():
                continue
            for b in np.unique(p.ids[wk, k]):
                sel = wk & (p.ids[:, k] == b)
                rad[b] = max(rad[b], float(np.linalg.norm(p.pos[sel] - bw[b], axis=1).max()))
    return rad


def _sphere_entry(pts, ref=np.zeros(3)):
    lo, hi = pts.min(0), pts.max(0)
    c = (lo + hi) / 2
    return tuple((c - ref).tolist()) + (float(np.linalg.norm(pts - c, axis=1).max()),)


def group_sphere(parts, bone_world=None):
    """Bounding sphere entry of a group: the centre of the box of its vertices relative to the bind position of the bone that
    carries most of the group's weight (the head bone for a head, the wrist for a hand pose ...), then the farthest vertex.

    Retail: with that bone as the reference the sphere covers the group in 98% of 1242 body/hand groups and in 100% of the main
    head groups (median 6 cm off the box centre); with the root bone (id 0) it covers 10% / 24% and a head at the origin of the
    root is then culled as soon as that sphere is off screen.
    """
    pts = np.concatenate([p.pos for p in parts])
    ref = np.zeros(3)
    if bone_world is not None and len(bone_world):
        wt = np.zeros(len(bone_world))
        for p in parts:
            if p.ids is not None and p.w is not None:
                np.add.at(wt, np.clip(np.asarray(p.ids).astype(int), 0, len(wt) - 1).ravel(), np.asarray(p.w, float).ravel())
        ref = bone_world[int(np.argmax(wt))] if wt.any() else bone_world[0]
    return _sphere_entry(pts, ref)


def make_bbox(bone_index, local_pts):
    """0x90 byte bounding volume of one (mesh, bone) pair in bone local space (axis aligned OBB)."""
    lo, hi = local_pts.min(0), local_pts.max(0)
    c = (lo + hi) / 2
    r = float(np.linalg.norm(hi - lo) / 2)
    f = lambda *a: struct.pack('<%df' % len(a), *a)
    return (struct.pack('<I', bone_index) + b'\xcd' * 12
            + f(*c, r) + f(*lo, 0) + f(*hi, 0)
            + f(1, 0, 0, 0) + f(0, 1, 0, 0) + f(0, 0, 1, 0)
            + f(*c, 1) + f(*((hi - lo) / 2), 0))


def _default_head():
    h = bytearray(0x80)
    h[0:4] = b'MOD\0'
    struct.pack_into('<III', h, 0x70, *DEFAULT_LOD_DIST)
    h[0x7E:0x80] = b'\xcd\xcd'
    return bytes(h)


# --------------------------------------------------------------------------- write
def to_mod(model: Model, preserve_quantisation=True, quant=None) -> M.Mod211:
    """quant = (origin(3), scale): quantisation of the original file, kept when all vertices still fit into it"""
    tpl = model.template
    skel = model.has_skeleton
    bones = model.bones
    nb = len(bones)
    parts = model.parts

    # ---- quantisation ---------------------------------------------------------------------
    scale, origin = 1.0, np.zeros(3)
    if skel:
        allp = np.concatenate([p.pos for p in parts]) if parts else np.zeros((1, 3))
        kept = False
        hint = None
        if tpl is not None and tpl.boneCount == nb and tpl.scale > 0:
            hint = (tpl.model_origin, tpl.scale)
        elif quant is not None and quant[1] > 0:
            hint = (np.asarray(quant[0], np.float64), float(quant[1]))
        if preserve_quantisation and hint is not None:
            o, s = hint
            q = (allp + o) / s * 32767.0
            if np.isfinite(q).all() and q.min() >= -32768.49 and q.max() <= 32767.49:
                scale, origin, kept = s, o, True
        kept_q = kept
        if not kept:
            lo = allp.min(0)
            origin = -lo
            ext = float((allp.max(0) - lo).max())
            scale = max(ext, 1e-3) * 1.0001

    kept_q_all = (not skel) or kept_q
    skeleton_same = (not skel) or (tpl is not None and tpl.boneCount == nb and kept_q and np.array_equal(
        tpl.lmat, np.stack([b.local for b in bones]).astype(np.float32)))
    # ---- skeleton ---------------------------------------------------------------------------
    bone_bytes = b''
    lmat = amat = np.zeros((0, 4, 4), np.float32)
    remap = b''
    if skel:
        W = _bone_world(bones)
        S = np.diag([scale, scale, scale, 1.0])
        T = np.eye(4)
        T[3, :3] = -origin
        lmat = np.stack([b.local for b in bones]).astype(np.float32)
        amat = np.stack([S @ T @ np.linalg.inv(W[i]) for i in range(nb)]).astype(np.float32)
        if tpl is not None and tpl.boneCount == nb and kept_q and np.array_equal(tpl.lmat, lmat):
            amat = tpl.amat.copy()                      # skeleton untouched: keep the file's own inverse bind matrices
        rad = None
        out = bytearray()
        for b in bones:
            if b.radius is None:
                if rad is None:
                    rad = compute_bone_radius(bones, parts)
                r = float(rad[b.index])
            else:
                r = b.radius
            t = b.local[3, :3]
            ln = float(np.linalg.norm(t))
            if b.length is not None and abs(b.length - ln) <= 1e-4 * (1 + ln):
                ln = b.length
            out += struct.pack('<BBBBfffff', b.fn_id, b.parent, b.mirror, b.unk, r, ln, *t)
        bone_bytes = bytes(out)
        rm = bytearray(model.remap if len(model.remap) == 256 else b'\xff' * 256)
        for b in bones:
            if b.fn_id == 255:          # same value as the 'unused' marker
                continue
            cur = rm[b.fn_id]
            if cur == 0xFF or cur >= nb or bones[cur].fn_id != b.fn_id:
                rm[b.fn_id] = b.index
        for i in range(256):            # ids whose bone was deleted: retail never leaves a stale entry (a ctc node of that id would drive another bone)
            if rm[i] != 0xFF and (rm[i] >= nb or bones[rm[i]].fn_id != i):
                rm[i] = 0xFF
        remap = bytes(rm)

    # ---- meshes / vertex buckets -------------------------------------------------------------
    vertices = bytearray()
    faces = []
    face_total = 0
    meshes = []
    bboxes = []
    prev_stride = None
    prev_base = prev_sub = 0
    bucket_start = 0
    cur_hash_groups = {}
    order = list(range(len(parts)))
    all_untouched = True
    # draw order (unknownIndex, a permutation of 1..N) and sort key (tail): keep the file's values, new parts go last
    live = [p for p in parts if p.vertex_count and len(p.faces)]
    seen_ui = set()
    for p in live:                                   # duplicated objects share one draw order: later ones count as new
        if 'ui' in p.meta:
            if p.meta['ui'] in seen_ui:
                del p.meta['ui']
            else:
                seen_ui.add(p.meta['ui'])
    old = sorted(p.meta['ui'] for p in live if 'ui' in p.meta)
    rank = {u: i + 1 for i, u in enumerate(old)}
    max_tail = max((p.meta.get('tail', 0) for p in live), default=0x19000000)
    nxt = len(old)
    for pi in order:
        p = parts[pi]
        n = p.vertex_count
        if n == 0 or len(p.faces) == 0:
            continue
        if 'ui' in p.meta:
            ui, tail = rank[p.meta['ui']], p.meta['tail']
        else:
            nxt += 1
            ui = nxt
            max_tail = ((max_tail | 0xFFFF) + 1) & 0xFFFFFFFF
            tail = max_tail | 0xC0
        # ----- skinning -----
        if skel:
            if p.ids is None:
                raise ValueError('part %s has no skin data' % p.name)
            n_inf = influence_count(p.ids, p.w)
        else:
            n_inf = 0
        n_uv = len(p.uvs)
        has_col = p.col is not None
        fmt = p.fmt
        if fmt is not None:
            problems = V.fit_problems(fmt, skel, n_inf, n_uv, has_col, p.is_shadow)
            if problems:                     # a chosen layout is never replaced silently (the exporter reports it first)
                raise ValueError('part %s: %s' % (p.name, '; '.join(problems)))
        if fmt is None:
            fmt = choose_format(skel, n_inf, n_uv, has_col, p.is_shadow)
        f = V.FORMATS[fmt]
        d = dict(pos=p.pos + origin if skel else p.pos,
                 nrm=p.nrm if p.nrm is not None else np.tile([0.0, 1.0, 0.0], (n, 1)))
        if f.tan is not None:
            d['tan'] = p.tan if p.tan is not None else np.tile([1.0, 0.0, 0.0], (n, 1))
            d['tsign'] = p.tsign if p.tsign is not None else np.ones(n)
        d['uv'] = [np.asarray(u, np.float32) for u in p.uvs[:len(f.uvs)]]
        if f.col is not None:
            d['col'] = p.col if has_col else np.full((n, 4), 255, np.uint8)
        if p.meta.get('nw') is not None and len(p.meta['nw']) == n and p.fmt == fmt:
            d['nw'] = p.meta['nw']
            if f.tan is not None and p.meta.get('tw') is not None and p.tsign is None:
                d['tw'] = p.meta['tw']
            if p.meta.get('residual') is not None and len(p.meta['residual']) == n:
                d['residual'] = p.meta['residual']
        if f.pw == 'bone':
            d['bone'] = p.ids[:, 0] if skel else np.zeros(n, int)
        if f.ids is not None:
            K = f.ids[2]
            tol = 0.5 * K / 255.0 + 2e-3 if f.wts[0] in ('u8', 'w8') else 2e-3
            d['ids'], d['w'], _ = normalise_influences(p.ids, p.w, K, tol)
            io = p.meta.get('ids_raw')
            if p.fmt == fmt and io is not None and io.shape == d['ids'].shape:
                # keep the original filler ids of unused slots where the real influences did not change
                same = np.all((d['w'] == 0) | (d['ids'] == io), axis=1)
                d['ids'] = np.where(same[:, None], io, d['ids'])
        raw = V.encode(f, d, scale)
        orig_raw = p.meta.get('raw')
        untouched = False
        if orig_raw is not None and p.fmt == fmt and orig_raw.shape == raw.shape and kept_q_all:
            same = _unchanged_rows(p)
            if same is not None:
                raw[same] = orig_raw[same]
                untouched = bool(same.all()) and skeleton_same
        # ----- bucket bookkeeping (same scheme as MHW) -----
        stride = f.stride
        if stride != prev_stride:
            bucket_start = len(vertices)
            vsub = vbase = 0
            voff = bucket_start
        else:
            if n + prev_sub > 0xFFFF:
                vsub = 0
                vbase = prev_base + prev_sub
            else:
                vsub, vbase = prev_sub, prev_base
            voff = len(vertices) - (vbase + vsub) * stride
        vertices += raw.tobytes()
        prev_stride, prev_base, prev_sub = stride, vbase, vsub + n
        nt = len(p.faces)
        faces.append((np.asarray(p.faces, np.int64) + vsub).astype('<u2').reshape(-1))
        # ----- bounding volumes -----
        if skel and untouched and 'bbox' in p.meta:
            bboxes.extend(p.meta['bbox'])
            nbb = len(p.meta['bbox'])
        elif skel:
            used = sorted({int(b) for b in np.unique(d['ids'][d['w'] > 0])}) if f.ids is not None \
                else sorted({int(b) for b in np.unique(d['bone'])})
            bw = bind_positions(bones)
            for b in used:
                if f.ids is not None:
                    sel = ((d['ids'] == b) & (d['w'] > 0)).any(1)
                else:
                    sel = d['bone'] == b
                bboxes.append(make_bbox(b, p.pos[sel] - bw[b]))
            nbb = len(used)
        else:
            # skeleton-less models still carry one bounding volume per mesh (bone 255, world space)
            bboxes.append(p.meta['bbox'][0] if untouched and p.meta.get('bbox') else make_bbox(255, p.pos))
            nbb = 1
        all_untouched &= untouched
        infl = 0 if not skel else (1 if f.ids is None else declared_influences(f.influences, n_inf))
        if skel and p.fmt == fmt and (untouched or infl <= p.wd_infl <= max(f.influences, 1)):
            infl = p.wd_infl
        wd = (p.wd_hi << 8) | (p.wd_flags & 6) | (1 + 8 * infl)
        shadow_fmt = f.tan is None and not f.uvs
        if p.fmt == fmt and 'index' in p.meta:
            unk3 = p.unk3
        else:
            unk3 = 0xC3 if (p.is_shadow or shadow_fmt) else ((p.unk3 & 0x43) if f.tan is not None else 3)
        meshes.append(M.Mesh(
            lodMask=p.lod_mask, vertexCount=n, flags=((p.material & 0xF) << 12) | (p.group & 0xFFF), unk6=(p.material >> 4) & 0xFF,
            lod=p.lod, weightDynamics=wd, blockSize=stride, unk3=unk3, vertexSub=vsub, vertexOffset=voff,
            blocktype=fmt, faceOffset=face_total, faceCount=nt * 3, vertexBase=vbase, null0=0, boundingBoxCount=nbb,
            unknownIndex=ui, vertexSubMirror=vsub, vertexIndexSub=vsub + n - 1, tail=tail))
        face_total += nt * 3

    # ---- groups / materials ---------------------------------------------------------------------
    gids = sorted({m.flags & 0xFFF for m in meshes})
    groups = bytearray()
    bw_all = bind_positions(bones) if skel else None
    for g in gids:
        if g in model.groups:
            sph = model.groups[g]
        else:
            gp = [p for p in parts if p.group == g and not p.is_shadow and len(p.pos)]
            sph = group_sphere(gp, bw_all) if gp else (0, 0, 0, 1.0)
        groups += struct.pack('<iIIIffff', g, 0xCDCDCDCD, 0xCDCDCDCD, 0xCDCDCDCD, *sph)

    # ---- header ---------------------------------------------------------------------------------
    head = bytearray(tpl.head[:0x80] if tpl is not None and len(tpl.head) >= 0x80 else _default_head())
    allw = np.concatenate([p.pos for p in parts]) if parts else np.zeros((1, 3))
    lo, hi = allw.min(0), allw.max(0)
    c = (lo + hi) / 2
    r = float(np.linalg.norm(allw - c, axis=1).max())
    if not (all_untouched and tpl is not None and len(meshes) == len(tpl.meshes)):
        struct.pack_into('<4f', head, 0x40, *c, r)
        struct.pack_into('<4f', head, 0x50, *lo, 0)
        struct.pack_into('<4f', head, 0x60, *hi, 0)
    struct.pack_into('<III', head, 0x70, *model.lod_dist)
    struct.pack_into('<I', head, 0x14, face_total // 3)
    m = M.Mod211(head=bytes(head) if skel else bytes(head), bones=bone_bytes, lmat=lmat, amat=amat, remap=remap,
                 groups=bytes(groups), materials=list(model.materials), meshes=meshes, bboxes=bboxes,
                 vertices=vertices, faces=np.concatenate(faces) if faces else np.zeros(0, np.uint16),
                 trailer=model.trailer, tail_pad=model.tail_pad)
    return m
