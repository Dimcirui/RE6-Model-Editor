# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 Dimcirui

"""Shader features (switches) of nDraw::MaterialStd: change the option of a switch and add / remove the commands that the
option needs (texture slots, sampler states, UV / channel switches, constant buffers).

A MaterialStd material picks one option for each of ~45 shader switches (type 0 commands: b = switch, a = option;
a == b is the default option). The shaders are precompiled, so only the options that exist can be used, and every option
needs its own commands: FSpecular = FSpecularMap needs tSpecularMap + SSSpecularMap + FUVSpecularMap + FChannelSpecularMap,
FBump = FBumpDetailNormalMap needs tDetailNormalMap + FUVDetailNormalMap, FAlbedo = 9f2aaa39 needs CBColorMask ...

The tables (core/mrl_feature_data.py) are learned from all retail materials by tools/make_feature_table.py:
* ALWAYS: commands every material has; OWNERS[command]: the options that imply it. A material has a command exactly when
  it is in ALWAYS or one of its owners is selected (least fixed point, so UV switches do not keep their own slot alive);
  this reproduces the command set of every retail material.
* RANK: the usual command order, used to insert new commands. HEADERS / DEFAULT_A / CB_DEFAULT: values of new commands.
* COMBOS: the switch combinations that exist in the game; any other combination is unverified in game.
* MFX_*: the official rules of the game's shader package (core/mfx.py): every option of every switch (also unused
  ones), the commands each option needs, buffer defaults, sampler states. When present, set_option uses them (the
  dependency closure reproduces all retail materials too); the retail tables still give the order and the defaults.

Command keys are (type, b). The command block is commands, zero padding to 16 bytes, then the constant buffers in command
order (each buffer has a fixed size per name).
"""
from __future__ import annotations

import copy
import struct
import zlib

from . import mrl as R

MATERIAL_STD = 0x5FB0EBE4

_UV_PREFIX = ('FUV', 'FChannel', 'FVD')


def _data():
    from . import mrl_feature_data as D
    return D


def key(c) -> tuple:
    return (c.type, c.b)


def keys(mat) -> set:
    return {key(c) for c in mat.commands}


def options(mat) -> dict:
    """{switch hash: option hash} of a material"""
    return {c.b: c.a for c in mat.commands if c.type == R.CMD_STATE}


def combo_hash(opts: dict) -> int:
    return zlib.crc32(b''.join(struct.pack('<II', sw, a) for sw, a in sorted(opts.items())))


def cbuffer_data(mat) -> dict:
    """{buffer hash: bytes} of the constant buffers of a material"""
    return {h: bytes(mat.block[off:off + 4 * n]) for h, off, n in R.cbuffers(mat)}


def required(opts: dict, always, owners) -> set:
    """command keys a material with these switch options has (least fixed point of the owner rule)"""
    present = set(always)
    todo = {k: own for k, own in owners.items()}
    changed = True
    while changed:
        changed = False
        for k in list(todo):
            if any((R.CMD_STATE, sw) in present and opts.get(sw) == a for sw, a in todo[k]):
                present.add(k)
                del todo[k]
                changed = True
    return present


def mfx_required(opts: dict, always, deps: dict, parents: dict = None) -> set:
    """command keys a material with these switch options has, by the shader package: the root commands, and for every
    present switch the dependencies of its selected option (a missing entry in `opts` = the default option);
    `parents` receives the switch that brought each command"""
    present = {tuple(k) for k in always}
    todo = [k for k in present if k[0] == R.CMD_STATE]
    while todo:
        k = todo.pop()
        for d in deps.get(opts.get(k[1], k[1]), ()):
            d = tuple(d)
            if d not in present:
                present.add(d)
                if parents is not None:
                    parents[d] = k
                if d[0] == R.CMD_STATE:
                    todo.append(d)
    return present


def header_of(k) -> int:
    """command header: the retail value, else (code of b << 20) | 0xdcdc0 | type (true for every retail command)"""
    h = _data().HEADERS.get(k)
    return h if h is not None else ((k[1] & 0xFFF) << 20) | 0xDCDC0 | k[0]


def relayout(mat, commands, cbdata: dict):
    """a copy of `mat` with these commands; the constant buffers (data from `cbdata`, else the most common retail data,
    else the shader package default) are placed after the commands and the command block is rebuilt"""
    D = _data()
    m = copy.copy(mat)
    m.commands = [R.Command(c.header, c.a, c.b) for c in commands]
    pos = (len(m.commands) * R.CMD_SIZE + 15) // 16 * 16
    bufs = []
    for c in m.commands:
        if c.type == R.CMD_CBUFFER:
            data = cbdata.get(c.b)
            if data is None:
                data = D.CB_DEFAULT.get(c.b)
            if data is None:
                data = getattr(D, 'MFX_CB', {}).get(c.b)
            if data is None:
                raise ValueError('no data for the constant buffer %08x' % c.b)
            c.a = pos
            bufs.append(data)
            pos += len(data)
    blk = bytearray(pos)
    for k, c in enumerate(m.commands):
        struct.pack_into('<III', blk, k * R.CMD_SIZE, c.header, c.a, c.b)
    for c, data in zip([c for c in m.commands if c.type == R.CMD_CBUFFER], bufs):
        blk[c.a:c.a + len(data)] = data
    m.block = bytes(blk)
    m.size = len(m.block)
    m.flags = (m.flags & ~0xFFF) | len(m.commands)
    return m


def default_option(switch: int) -> int:
    """option a switch gets when it is added: its most common retail option, else the most common option of its group
    (FUVPrimary for the UV selectors), else its default"""
    D = _data()
    a = D.DEFAULT_A.get((R.CMD_STATE, switch))
    if a is not None:
        return a
    g = getattr(D, 'MFX_GROUP', {}).get(switch)
    a = getattr(D, 'GROUP_DEFAULT', {}).get(g)
    if a is not None and a in getattr(D, 'MFX_OPTIONS', {}).get(switch, ()):
        return a
    return switch


def _new_command(k, opts):
    t, b = k
    if t == R.CMD_STATE:
        a = opts.get(b, default_option(b))
    elif t == R.CMD_SAMPLER:
        a = b
    else:
        a = 0                       # texture index (assigned when the file is assembled) / buffer offset (relayout)
    return R.Command(header_of(k), a, b)


_UNIVERSE = None


def _universe() -> set:
    """every command key the tables know"""
    global _UNIVERSE
    if _UNIVERSE is None:
        D = _data()
        u = {tuple(k) for k in D.ALWAYS} | set(D.RANK)
        for ks in getattr(D, 'MFX_DEPS', {}).values():
            u |= {tuple(k) for k in ks}
        _UNIVERSE = u
    return _UNIVERSE


def set_option(mat, switch: int, option: int):
    """a copy of `mat` with `switch` set to `option` and the commands added / removed that the options now need (by the
    shader package when its tables are there, else by the retail owner rule). Existing commands keep their values and
    order; new ones are inserted at their usual retail place (or right after the switch that needs them), with retail /
    shader package defaults and empty texture slots."""
    D = _data()
    if (R.CMD_STATE, switch) not in keys(mat):
        raise ValueError('the material has no switch %08x' % switch)
    if option not in [a for a, _ in option_list(switch)]:
        raise ValueError('option %08x does not exist for the switch %08x' % (option, switch))
    opts = options(mat)
    opts[switch] = option
    parents = {}
    if hasattr(D, 'MFX_DEPS'):
        full = dict(opts)
        for k in _universe():
            if k[0] == R.CMD_STATE and k[1] not in full:
                full[k[1]] = default_option(k[1])
        need = mfx_required(full, D.ALWAYS, D.MFX_DEPS, parents)
    else:
        full = {k[1]: a for k, a in D.DEFAULT_A.items() if k[0] == R.CMD_STATE}
        full.update(opts)
        need = required(full, D.ALWAYS, D.OWNERS)
    have = keys(mat)
    unknown = have - _universe()                 # commands the tables do not know: keep them
    cmds = []
    for c in mat.commands:
        k = key(c)
        if k in need or k in unknown:
            cmds.append(R.Command(c.header, option if k == (R.CMD_STATE, switch) else c.a, c.b))
    new = need - have
    for k in sorted((k for k in new if k in D.RANK), key=lambda k: D.RANK[k]):
        cmds.insert(_insert_at(k, cmds), _new_command(k, full))
    rest = sorted(k for k in new if k not in D.RANK)
    while rest:                                  # never seen in retail: right after the switch that needs them
        k = next((k for k in rest if parents.get(k) not in rest), rest[0])
        rest.remove(k)
        pk = parents.get(k)
        at = next((i for i, c in enumerate(cmds) if key(c) == pk), len(cmds) - 1)
        while at + 1 < len(cmds) and key(cmds[at + 1]) in new and key(cmds[at + 1]) not in D.RANK:
            at += 1
        cmds.insert(at + 1, _new_command(k, full))
    return relayout(mat, cmds, cbuffer_data(mat))


def _insert_at(k, cmds) -> int:
    """position for a new command: the one that contradicts the fewest retail orders (pairwise counts in BEFORE)"""
    D = _data()
    r = D.RANK[k]
    ranks = [D.RANK.get(key(c)) for c in cmds]
    # cost of position p = sum over the commands before p of 'k before x' + over the commands from p on of 'x before k'
    after = [0 if x is None else D.BEFORE.get(x * 256 + r, 0) for x in ranks]
    before = [0 if x is None else D.BEFORE.get(r * 256 + x, 0) for x in ranks]
    cost = sum(after)
    best, best_cost = 0, cost
    for p in range(len(cmds)):
        cost += before[p] - after[p]
        if cost < best_cost:
            best, best_cost = p + 1, cost
    return best


def is_std(mat) -> bool:
    return mat.type == MATERIAL_STD


def is_known_combo(mat) -> bool:
    """True when this switch combination exists in a retail material"""
    return combo_hash(options(mat)) in _data().COMBOS


def option_list(switch: int) -> list:
    """[(option hash, retail count)] of a switch, in code order: every option of the shader package (count 0 = no retail
    material uses it), or the retail ones when the package tables are missing"""
    D = _data()
    mfx = getattr(D, 'MFX_OPTIONS', {}).get(switch)
    if not mfx:
        return list(D.OPTIONS.get(switch, ()))
    retail = dict(D.OPTIONS.get(switch, ()))
    return sorted(((a, retail.get(a, 0)) for a in mfx), key=lambda an: (an[0] & 0xFFF, an[0]))


def unused_options(mat) -> list:
    """[(switch, option)] of the options of a material that no retail material uses"""
    D = _data()
    return [(sw, a) for sw, a in options(mat).items() if a not in dict(D.OPTIONS.get(sw, ()))]


def sampler_states(slot: int) -> list:
    """the sampler state objects a sampler slot can use (the slot's own default first)"""
    return list(getattr(_data(), 'MFX_SAMPLERS', {}).get(slot, [slot]))


def is_default(switch: int, option: int) -> bool:
    return switch == option


def is_main(switch: int, name: str = '') -> bool:
    """main feature switch as opposed to the UV / channel / displacement sub switches (FUV*, FChannel*, FVD*)"""
    return (R.CMD_STATE, switch) in _data().HEADERS and not name.startswith(_UV_PREFIX)


def changes(old, new) -> tuple:
    """(added keys, removed keys) between two versions of a material"""
    a, b = keys(old), keys(new)
    return sorted(b - a), sorted(a - b)
