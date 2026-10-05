# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 Dimcirui

"""Read only access to RE6 PC .arc archives (version 7) and a path index over a whole game folder.

Layout (little endian): 'ARC\\0', u16 version (7), u16 count, count * 0x50 entries { char[64] name (backslash path,
no extension), u32 class hash, u32 compressed size, u32 size | flags << 29, u32 offset }, data as zlib streams.
See RE6 ARC Studio (re6arc/arc.py) for the full format and for writing archives.
"""
from __future__ import annotations

import glob
import json
import os
import struct
import zlib

ENTRY_SIZE = 0x50
SIZE_MASK = 0x1FFFFFFF


def _class_hash(name: str) -> int:
    return (~zlib.crc32(name.encode('ascii'))) & 0x7FFFFFFF


EXT_OF_HASH = {_class_hash('rTexture'): 'tex', _class_hash('rModel'): 'mod', _class_hash('rMaterial'): 'mrl'}


class ArcError(RuntimeError):
    pass


def read_table(path: str):
    """[(virtual path lower case with extension, offset, compressed size, size)] of the tex / mod / mrl entries"""
    out = []
    with open(path, 'rb') as fh:
        head = fh.read(8)
        if len(head) < 8 or head[:4] != b'ARC\0':
            raise ArcError('not an ARC file')
        version, count = struct.unpack_from('<HH', head, 4)
        if version != 7:
            raise ArcError('unsupported ARC version %d' % version)
        table = fh.read(count * ENTRY_SIZE)
    if len(table) != count * ENTRY_SIZE:
        raise ArcError('truncated entry table')
    for i in range(count):
        raw, th, csize, sz, off = struct.unpack_from('<64sIIII', table, i * ENTRY_SIZE)
        ext = EXT_OF_HASH.get(th)
        if ext is None:
            continue
        name = raw.split(b'\0', 1)[0].decode('latin1').replace('\\', '/').lstrip('/')
        out.append((('%s.%s' % (name, ext)).lower(), off, csize, sz & SIZE_MASK))
    return out


def read_entry(path: str, off: int, csize: int, size: int) -> bytes:
    with open(path, 'rb') as fh:
        fh.seek(off)
        raw = fh.read(csize)
    try:
        data = zlib.decompress(raw)
    except zlib.error:
        if len(raw) != size:
            raise
        data = raw
    if len(data) != size:
        raise ArcError('size mismatch in %s' % path)
    return data


class GameIndex:
    """virtual path -> archive entry over nativePC / nativePC_dlc of a game folder (first archive wins)"""

    def __init__(self, game_dirs, cache_file: str = ''):
        """game_dirs: folders that contain nativePC, earlier ones win (a mod folder before the real game folder)"""
        self.game_dir = '|'.join(game_dirs)
        self.dirs = list(game_dirs)
        self.entries = {}
        self._load(cache_file)

    def archives(self):
        files = []
        for d in self.dirs:
            for sub in ('nativePC', 'nativePC_dlc'):
                files += sorted(glob.glob(os.path.join(d, sub, 'arc', 'DX9', '*.arc')))
        return files

    def _load(self, cache_file):
        files = self.archives()
        stamp = {f: [os.path.getmtime(f), os.path.getsize(f)] for f in files}
        if cache_file and os.path.isfile(cache_file):
            try:
                with open(cache_file, 'r') as fh:
                    c = json.load(fh)
                if c.get('dir') == self.game_dir and c.get('stamp') == stamp:
                    self.entries = {k: tuple(v) for k, v in c['entries'].items()}
                    return
            except (OSError, ValueError, KeyError):
                pass
        for f in files:
            try:
                for key, off, csize, size in read_table(f):
                    self.entries.setdefault(key, (f, off, csize, size))
            except (ArcError, OSError):
                continue
        if cache_file:
            try:
                os.makedirs(os.path.dirname(cache_file), exist_ok=True)
                with open(cache_file, 'w') as fh:
                    json.dump({'dir': self.game_dir, 'stamp': stamp, 'entries': self.entries}, fh)
            except OSError:
                pass

    def by_base(self) -> dict:
        """file name (lower case, with extension) -> first virtual path with that name"""
        if not hasattr(self, '_base'):
            self._base = {}
            for k in self.entries:
                self._base.setdefault(k.rsplit('/', 1)[-1], k)
        return self._base

    def has(self, key: str) -> bool:
        return key.lower() in self.entries

    def find_name(self, name: str):
        """virtual path of the first entry called `name` (any folder), else None"""
        return self.by_base().get(name.lower())

    def read(self, key: str) -> bytes:
        f, off, csize, size = self.entries[key.lower()]
        return read_entry(f, off, csize, size)
