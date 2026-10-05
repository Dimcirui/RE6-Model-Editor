# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 Dimcirui

bl_info = {
    "name": "RE6 Model Editor",
    "author": "Dimcirui",
    "version": (0, 3, 0),
    "blender": (4, 2, 0),
    "location": "File > Import / Export > RE6 Model Editor",
    "description": "Import, edit and export Resident Evil 6 (MT Framework) .mod model files.",
    "category": "Import-Export",
}

try:
    import bpy  # noqa: F401
    _HAS_BPY = True
except ImportError:          # the pure python core is usable without Blender
    _HAS_BPY = False


def register():
    if _HAS_BPY:
        from .blender import register_all
        register_all()


def unregister():
    if _HAS_BPY:
        from .blender import unregister_all
        unregister_all()
