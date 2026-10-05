# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 Dimcirui

"""Texture conversion: .tex <-> .dds / images, and writing the textures of a model (counterpart of the MHW Tex Tools)."""
import os
import shutil
import time

import bpy
import numpy as np
from bpy.props import BoolProperty, CollectionProperty, EnumProperty, IntProperty, StringProperty
from bpy_extras.io_utils import ImportHelper
from bpy.types import Operator

from ..core import bc
from ..core import tex as T
from . import common as C
from . import materials as MT
from . import prefs
from .i18n import iface, rpt


# --- image <-> tex ------------------------------------------------------------------------------------------

def image_rgba(im):
    """(H, W, 4) uint8, first row = top, as stored in a file (byte images: the stored values)"""
    w, h = im.size
    if w == 0 or h == 0:
        raise ValueError('image "%s" has no pixels' % im.name)
    a = np.empty(w * h * 4, np.float32)
    im.pixels.foreach_get(a)
    a = a.reshape(h, w, 4)
    if im.is_float and im.colorspace_settings.name == 'sRGB':
        rgb = np.clip(a[..., :3], 0, 1)
        a[..., :3] = np.where(rgb <= 0.0031308, rgb * 12.92, 1.055 * np.power(rgb, 1 / 2.4) - 0.055)
    return np.rint(np.clip(a, 0, 1) * 255).astype(np.uint8)[::-1]


def to_dxt5nm(rgba, flip_green):
    """regular RGB tangent space normal map -> DXT5nm (R = 1, G = y, B = 1, A = x)"""
    out = np.empty_like(rgba)
    out[..., 0] = 255
    out[..., 1] = 255 - rgba[..., 1] if flip_green else rgba[..., 1]
    out[..., 2] = 255
    out[..., 3] = rgba[..., 0]
    return out


def is_dxt5nm(rgba):
    """True when an (H, W, 4) uint8 image is already packed like the game's normal maps: R and B painted white
    (x lives in alpha, y in green). A regular RGB normal map has R around 0.5, so R alone tells them apart"""
    r, b = rgba[..., 0], rgba[..., 2]
    return bool((r >= 240).mean() > 0.98 and (b >= 240).mean() > 0.98)


def tex_suffix(name):
    base = os.path.splitext(os.path.basename(name))[0]
    return (base.rsplit('_', 1)[-1].upper() if '_' in base else '')[:2]


def image_to_tex_bytes(im, role, flip_green=True, layout=None, fmt=None):
    """encode a Blender image as .tex bytes. Images that came from a .tex keep their layout / format byte;
    normal map images that did not come from a .tex are converted to DXT5nm"""
    rgba = image_rgba(im)
    came_from_tex = bool(im.get(MT.K_TEX))
    if role == 'normal' and not came_from_tex and not is_dxt5nm(rgba):
        rgba = to_dxt5nm(rgba, flip_green)
    layout = layout or im.get('re6_layout')
    if layout not in (T.BC1, T.BC3, T.BGRA):
        layout = T.BC3 if (role == 'normal' or (rgba[..., 3] < 255).any()) else T.BC1
    if role != 'normal' and layout == T.BC1:
        rgba = rgba.copy()
        rgba[..., 3] = 255
    fmt = fmt or im.get('re6_fmt') or T.default_fmt(im.name if not im.get(MT.K_VPATH) else im[MT.K_VPATH], layout)
    return bc.build_tex(rgba, layout, int(fmt))


def needs_export(im):
    """images that are not an untouched copy of a game texture"""
    return not im.get(MT.K_TEX) or im.is_dirty


def tex_target(root, vpath):
    """file the texture with game path `vpath` is written to below `root`"""
    return os.path.join(root, *vpath.replace('\\', '/').split('/')) + '.tex'


def export_model_textures(collection, root, flip_green=True, report=None, only_changed=True):
    """write the textures of the base / normal / mask nodes of every material of a model collection; returns files"""
    from . import mrl_objects as MO
    written = []
    seen = set()
    mats = []
    for o in collection.all_objects:
        if MO.is_entry(o):
            mats.append(o.re6_mrl_material.linkedMaterial)
        elif o.type == 'MESH':
            mats.extend(slot.material for slot in o.material_slots)
    for mat in mats:
        if mat is None or mat in seen or not mat.node_tree:
            continue
        seen.add(mat)
        for role in MT.ROLES:
            node = mat.node_tree.nodes.get(MT.ROLE_NODE[role])
            im = node.image if node is not None else None
            if im is None or (only_changed and not needs_export(im)):
                continue
            dst = tex_target(root, MT.image_tex_path(im))
            if dst in written:
                continue
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with open(dst, 'wb') as fh:
                fh.write(image_to_tex_bytes(im, role, flip_green))
            written.append(dst)
            if report:
                report({'INFO'}, rpt('RE6: wrote %s') % dst)
    return written


# --- operators ---------------------------------------------------------------------------------------------

TARGETS = {'BC1': T.BC1, 'BC3': T.BC3, 'BGRA': T.BGRA}


def source_format(path):
    """(label, layout that can be stored as it is or '') of a file to convert"""
    ext = os.path.splitext(path)[1].lower()
    if ext == '.dds':
        with open(path, 'rb') as fh:
            f = T.dds_format(fh.read())
        return f.name, f.layout
    return ext[1:].upper(), ''


LAYOUT_TARGET = {T.BC1: 'BC1', T.BC3: 'BC3', T.BGRA: 'BGRA'}


def _load_rgba(path):
    """decoded top mip of any image file Blender can read (DDS: also BC4 / BC5 / BC6H / BC7 / DX10 headers)"""
    im = bpy.data.images.load(path, check_existing=False)
    try:
        return image_rgba(im)
    finally:
        bpy.data.images.remove(im)


def image_file_to_tex(path, compression='AUTO', normal_maps='CONVERT', flip_green=True, mipmaps=True):
    """.tex bytes of a .dds / .png / .tga ... file. compression: AUTO (DXT5 for normal maps and images with alpha,
    else DXT1), BC1, BC3 or BGRA. A DDS that is already in the requested (or, for AUTO, any RE6) format is copied
    without re-encoding; other DDS formats (BC7, BC5 ... DX10) are decoded and re-encoded.
    mipmaps=False keeps only the top level (a copied DDS is cut down to its first level)"""
    name = os.path.splitext(os.path.basename(path))[0]
    is_nm = tex_suffix(name) == 'NM'
    convert_nm = is_nm and normal_maps == 'CONVERT'
    rgba = None
    packed = False
    if convert_nm:
        # the pixels decide: R and B painted white = already DXT5nm, whatever the container format is
        rgba = _load_rgba(path)
        packed = is_dxt5nm(rgba)
    if path.lower().endswith('.dds'):
        with open(path, 'rb') as fh:
            data = fh.read()
        f = T.dds_format(data)
        if f.layout and compression in ('AUTO', LAYOUT_TARGET[f.layout]) and (not convert_nm or packed):
            payload, mips = data[f.start:], f.mips
            if not mipmaps and mips > 1:
                payload, mips = payload[:T.level_size(f.width, f.height, f.layout)], 1
            return T.assemble(f.width, f.height, mips, f.layout, T.default_fmt(name, f.layout), payload)
    if rgba is None:
        rgba = _load_rgba(path)
    if convert_nm and not packed:
        rgba = to_dxt5nm(rgba, flip_green)
    layout = TARGETS.get(compression) or (T.BC3 if (is_nm or (rgba[..., 3] < 255).any()) else T.BC1)
    if layout == T.BC1:
        rgba = rgba.copy()
        rgba[..., 3] = 255
    return bc.build_tex(rgba, layout, T.default_fmt(name, layout), 0 if mipmaps else 1)


TEX_DIR, DDS_DIR = 'Converted_RE6_Tex', 'Converted_RE6_DDS'
IMAGE_EXTS = ('.dds', '.png', '.tga', '.jpg', '.jpeg', '.bmp', '.tif', '.tiff')
DXT_NAMES = {T.BC1: 'DXT1', T.BC3: 'DXT5', T.BGRA: 'BGRA8'}


def _open_folder(path):
    try:
        os.startfile(path)
    except (AttributeError, OSError):
        pass


def convert_files(file_paths, out_dir_of, tp, targets=None):
    """convert .tex to .dds and images to .tex; out_dir_of(path, folder) gives the folder a file is written to,
    targets maps a path to its .tex format (AUTO / BC1 / BC3 / BGRA, default tp.compression).
    Returns (success count, failure count, last folder)"""
    ok = fail = 0
    last = ''
    for p in file_paths:
        ext = os.path.splitext(p)[1].lower()
        try:
            if ext == '.tex':
                with open(p, 'rb') as fh:
                    raw = fh.read()
                data, out_ext, folder = T.to_dds(raw), '.dds', DDS_DIR
                prefix = DXT_NAMES.get(T.parse(raw).layout, '') + '_' if tp.addDXGIFormatPrefix else ''
            else:
                data, out_ext, folder = (image_file_to_tex(p, (targets or {}).get(p, tp.compression), tp.normalMaps,
                                                           tp.flipGreen, tp.generateMipmaps), '.tex',
                                         TEX_DIR)
                prefix = ''
            dst_dir = out_dir_of(p, folder)
            os.makedirs(dst_dir, exist_ok=True)
            last = dst_dir
            out = os.path.join(dst_dir, prefix + os.path.splitext(os.path.basename(p))[0] + out_ext)
            with open(out, 'wb') as fh:
                fh.write(data)
            print('Converted %s to %s' % (os.path.basename(p), out))
            ok += 1
        except Exception as e:      # noqa
            fail += 1
            print('\033[93mWARNING: %s: %s\033[0m' % (os.path.basename(p), e))
    return ok, fail, last


def _convert_with_report(op, paths, out_dir_of, tp, targets=None):
    """what the conversion operators of the MHW Model Editor do around the job"""
    from .operators import print_banner
    print_banner()
    prefs.toggle_console()
    print('\033[96m__________________________________\nRE6 Tex convert started.\033[0m')
    start = time.time()
    ok, fail, last = convert_files(paths, out_dir_of, tp, targets)
    print('Tex converted in %d ms.' % ((time.time() - start) * 1000))
    print('\nConversion Info:')
    print('Success Count: %d / %d' % (ok, len(paths)))
    print('Failure Count: %d / %d' % (fail, len(paths)))
    print('\033[92m__________________________________\nRE6 Tex convert finished.\033[0m')
    prefs.toggle_console()
    msg = iface('Converted %d / %d textures.') % (ok, len(paths))
    C.show_message_box(msg, title=iface('RE6 Tex Conversion'))
    op.report({'INFO'}, msg)
    return last


TARGET_ITEMS = [('AUTO', 'Auto', 'DXT5 for normal maps (*_NM) and images with transparency, else DXT1'),
                ('BC1', 'DXT1', 'Block compressed, 1 bit alpha, smallest (1/8 of BGRA8)'),
                ('BC3', 'DXT5', 'Block compressed with a smooth alpha channel (1/4 of BGRA8); normal maps use DXT5nm'),
                ('BGRA', 'BGRA8', 'Uncompressed, lossless, largest. Mind the memory limit of the 32 bit game')]


class Re6TexConvertItem(bpy.types.PropertyGroup):
    path: StringProperty()
    name: StringProperty()
    source: StringProperty()
    is_tex: BoolProperty()
    target: EnumProperty(name='Format', items=TARGET_ITEMS, default='AUTO')


def _set_all_targets(self, context):
    for it in self.items:
        it.target = self.set_all


class RE6_UL_tex_convert(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        split = layout.split(factor=0.42)
        split.label(text=item.name, icon='FILE_IMAGE' if not item.is_tex else 'TEXTURE')
        split = split.split(factor=0.28)
        split.label(text=item.source)
        if item.is_tex:
            split.label(text='-> .dds')
        else:
            split.row(align=True).prop(item, 'target', expand=True)


class RE6_OT_convert_tex_dds(Operator, ImportHelper):
    bl_label = 'RE6 Tex Conversion'
    bl_idname = 're6_tex.convert_re6_tex_dds_files'
    bl_description = ('Opens a window to select textures to convert.'
                      '\nSelected .dds (and .png / .tga ...) files will be converted to .tex, and .tex files will be '
                      'converted to .dds.'
                      '\nIf you are using Blender 4.1 or higher, you can drag .tex or .dds files into the 3D view to '
                      'convert them')
    filter_glob: StringProperty(default='*.dds;*.tex;*.png;*.tga;*.jpg;*.jpeg;*.bmp;*.tif;*.tiff', options={'HIDDEN'})
    files: CollectionProperty(name='File Path', type=bpy.types.OperatorFileListElement)
    directory: StringProperty(subtype='DIR_PATH', options={'SKIP_SAVE'})
    items: CollectionProperty(type=Re6TexConvertItem, options={'SKIP_SAVE'})
    active_index: IntProperty(options={'HIDDEN', 'SKIP_SAVE'})
    set_all: EnumProperty(name='Set All', items=TARGET_ITEMS, default='AUTO', update=_set_all_targets,
                          options={'SKIP_SAVE'}, description='Use this format for every file of the list')

    def _paths(self):
        return [os.path.join(self.directory, f.name) for f in self.files] if self.files else [self.filepath]

    def _fill(self, paths, tp):
        """one list row per file; returns True when a file needs a format choice (anything but .tex)"""
        self.items.clear()
        ask = False
        for p in paths:
            it = self.items.add()
            it.path, it.name = p, os.path.basename(p)
            it.is_tex = p.lower().endswith('.tex')
            if it.is_tex:
                it.source = 'TEX'
                continue
            ask = True
            try:
                it.source, layout = source_format(p)
            except (OSError, T.TexError) as e:
                it.source, layout = str(e), ''
            # formats RE6 reads start as they are (copied, no quality loss), the rest with the panel setting
            it.target = LAYOUT_TARGET.get(layout, tp.compression)
        return ask

    def execute(self, context):
        tp = context.scene.re6_mrl_toolpanel
        if not self.items:
            if self._fill(self._paths(), tp) and tp.askFormat:
                # chosen in the file browser: show the format list as a second step
                bpy.ops.re6_tex.convert_re6_tex_dds_files('INVOKE_DEFAULT', directory=self.directory,
                                                          files=[{'name': it.name} for it in self.items])
                return {'FINISHED'}
        targets = {it.path: it.target for it in self.items if not it.is_tex}
        _convert_with_report(self, [it.path for it in self.items],
                             lambda p, folder: os.path.join(os.path.dirname(p), folder) if tp.addConversionFolder
                             else os.path.dirname(p), tp, targets)
        return {'FINISHED'}

    def invoke(self, context, event):
        if self.directory:                      # dropped into the 3D view (or second step after the file browser)
            tp = context.scene.re6_mrl_toolpanel
            if self._fill(self._paths(), tp) and tp.askFormat:
                return context.window_manager.invoke_props_dialog(self, width=720, title=iface('Tex Format'),
                                                                  confirm_text=iface('Convert'))
            return self.execute(context)
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def draw(self, context):
        layout = self.layout
        if not self.items:          # file browser side panel
            return
        col = layout.column()
        col.label(text=iface('Choose the .tex format of every texture:'))
        rows = min(max(len(self.items), 3), 15)
        col.template_list('RE6_UL_tex_convert', '', self, 'items', self, 'active_index', rows=rows)
        row = col.row(align=True)
        row.label(text=iface('Set All') + ':')
        row.prop(self, 'set_all', expand=True)
        col.prop(context.scene.re6_mrl_toolpanel, 'generateMipmaps')
        col.separator()
        box = col.box().column(align=True)
        for line in (iface('BGRA8: lossless, 4x the size of DXT5 / 8x DXT1 (watch RE6 memory)'),
                     iface('DXT5: same colour quality as DXT1, plus a smooth alpha channel; normal maps (DXT5nm)'),
                     iface('Auto: DXT5 for *_NM and images with transparency, else DXT1'),
                     iface('DDS files already in DXT1 / DXT5 / BGRA8 are copied without re-encoding')):
            box.label(text=line)


class RE6_TEX_FH_drag_import(bpy.types.FileHandler):
    bl_idname = 'RE6_TEX_FH_drag_import'
    bl_label = 'File handler for RE6 Tex Conversion'
    bl_import_operator = RE6_OT_convert_tex_dds.bl_idname
    bl_file_extensions = '.dds;.tex'

    @classmethod
    def poll_drop(cls, context):
        return context.area and context.area.type == 'VIEW_3D'


class RE6_OT_convert_settings(Operator):
    bl_label = 'Convert Settings'
    bl_description = 'Detail settings for converting texture files'
    bl_idname = 're6_tex.convert_settings'
    bl_options = {'UNDO'}

    def execute(self, context):
        return {'FINISHED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def check(self, context):
        # Important for changing options
        return True

    def draw(self, context):
        tp = context.scene.re6_mrl_toolpanel
        layout = self.layout
        box = layout.box()
        col = box.column(align=True)
        for n in ('addConversionFolder', 'addDXGIFormatPrefix', 'openConvertedFolder', 'askFormat', 'compression',
                  'normalMaps', 'flipGreen', 'generateMipmaps'):
            row = col.row(align=True)
            row.scale_y = 1.1
            row.prop(tp, n)


class RE6_OT_convert_tex_directory(Operator):
    bl_label = 'Convert Directory to Tex'
    bl_idname = 're6_tex.convert_tex_directory'
    bl_description = ('Converts all .dds (and .png / .tga ...) files in the chosen directory to .tex.'
                      '\nConverted files will be saved inside a folder called "Converted_RE6_Tex".'
                      '\nSave .dds as DXT1 for color textures without alpha and DXT5 for normal maps and textures with alpha')

    @classmethod
    def poll(cls, context):
        return context.scene.re6_mrl_toolpanel.textureDirectory != ''

    def execute(self, context):
        tp = context.scene.re6_mrl_toolpanel
        src = os.path.realpath(bpy.path.abspath(tp.textureDirectory))
        dst = os.path.join(src, TEX_DIR)
        if os.path.isdir(src):
            files = [os.path.join(src, e.name) for e in os.scandir(src)
                     if e.is_file() and e.name.lower().endswith(IMAGE_EXTS)]
            if files:
                last = _convert_with_report(self, sorted(files), lambda p, folder: dst, tp)
                if last and tp.openConvertedFolder:
                    _open_folder(dst)
            else:
                C.show_error_message_box(iface('There are no .dds files in provided directory.'))
        else:
            C.show_error_message_box(iface('Provided texture directory is not a directory or does not exist.'))
        return {'FINISHED'}


class RE6_OT_open_conversion_folder(Operator):
    bl_label = 'Open Conversion Folder'
    bl_idname = 're6_tex.open_conversion_folder'
    bl_description = 'Open the folder containing the converted texture files in File Explorer'

    @classmethod
    def poll(cls, context):
        return context.scene.re6_mrl_toolpanel.textureDirectory != ''

    def execute(self, context):
        src = os.path.realpath(bpy.path.abspath(context.scene.re6_mrl_toolpanel.textureDirectory))
        dst = os.path.join(src, TEX_DIR)
        if os.path.isdir(src):
            os.makedirs(dst, exist_ok=True)
            _open_folder(dst)
        else:
            C.show_error_message_box(iface('Provided texture directory is not a directory or does not exist.'))
        return {'FINISHED'}


class RE6_OT_copy_converted_tex(Operator):
    bl_label = 'Copy Converted Tex Files'
    bl_idname = 're6_tex.copy_converted_tex'
    bl_options = {'UNDO'}
    bl_description = ('Copies .tex files in conversion folder into the specified mod "nativePC" directory.'
                      '\nCopied files will be placed at the paths set in the active mrl collection')

    def execute(self, context):
        tp = context.scene.re6_mrl_toolpanel
        if tp.textureDirectory == '' or tp.modDirectory == '':
            C.show_error_message_box(iface('Please set texture and mod directory first.'))
            return {'CANCELLED'}
        col = tp.mrlCollection
        if col is None:
            C.show_error_message_box(iface('Please set active mrl collection first.'))
            return {'CANCELLED'}

        from . import mrl_objects as MO
        src = os.path.join(os.path.realpath(bpy.path.abspath(tp.textureDirectory)), TEX_DIR)
        root = os.path.realpath(bpy.path.abspath(tp.modDirectory))
        if not os.path.isdir(root):
            C.show_error_message_box(iface('Provided mod directory is not a directory or does not exist.'))
            return {'CANCELLED'}
        if not os.path.isdir(src):
            C.show_error_message_box(iface('Provided texture directory is not a directory or does not exist.'))
            return {'FINISHED'}

        from .operators import print_banner
        print_banner()
        prefs.toggle_console()
        print('\033[96m__________________________________\nRE6 Tex copy started.\033[0m')
        n = 0
        for o in MO.entries(col):
            for b in o.re6_mrl_material.mapList_items:
                if not b.value:
                    continue
                name = b.value.replace('\\', '/').split('/')[-1]
                f = os.path.join(src, name + '.tex')
                if not os.path.isfile(f):
                    continue
                dst = tex_target(root, b.value.replace('\\', '/'))
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copyfile(f, dst)
                print('Copied %s to %s' % (os.path.basename(f), dst))
                n += 1
        print('\033[92m__________________________________\nRE6 Tex copy finished.\033[0m')
        prefs.toggle_console()
        msg = iface('Copied %d textures to mod directory.') % n
        C.show_message_box(msg, title=iface('RE6 Tex Copy'))
        self.report({'INFO'}, msg)
        return {'FINISHED'}


class RE6_OT_export_textures(Operator):
    """Write the textures of the active model that are new or were edited as .tex files"""
    bl_idname = 're6_tex.export_model_textures'
    bl_label = 'Export Model Textures'
    bl_options = {'REGISTER'}

    directory: StringProperty(subtype='DIR_PATH', options={'HIDDEN'})
    filter_folder: BoolProperty(default=True, options={'HIDDEN'})
    only_changed: BoolProperty(name='Only New / Edited Textures', default=True,
                               description='Skip textures that are unchanged copies of game textures')
    flip_green: BoolProperty(name='Flip Green', default=True,
                             description='Regular (OpenGL) normal maps to the DirectX convention of the game')

    @classmethod
    def poll(cls, context):
        from .operators import active_model_collection
        return active_model_collection(context) is not None

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        from .operators import active_model_collection
        col = active_model_collection(context)
        try:
            files = export_model_textures(col, self.directory, self.flip_green, self.report, self.only_changed)
        except Exception as e:      # noqa
            self.report({'ERROR'}, rpt('Texture export failed: %s') % e)
            return {'CANCELLED'}
        self.report({'INFO'}, rpt('Wrote %d texture(s).') % len(files))
        return {'FINISHED'}


CLASSES = (Re6TexConvertItem, RE6_UL_tex_convert, RE6_OT_convert_tex_dds, RE6_OT_convert_settings, RE6_OT_convert_tex_directory, RE6_OT_open_conversion_folder,
           RE6_OT_copy_converted_tex, RE6_OT_export_textures, RE6_TEX_FH_drag_import)


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
