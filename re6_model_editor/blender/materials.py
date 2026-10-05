# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 Dimcirui

"""Materials and textures: .mrl -> Blender node trees, .tex -> packed images."""
import colorsys
import hashlib
import json
import os
import struct

import bpy

from ..core import mrl as R
from ..core import cb_layouts as CL
from ..core.hashes import slot_name
from ..core.shader_names import name_of
from ..core import tex as T
from . import common as C
from . import props as P

NM_GROUP = 'RE6 DXT5nm Normal'
K_TEX = 're6_tex'                       # image property: virtual path of the .tex it came from
K_VPATH = 're6_tex_path'                # image property: texture path (backslashes, original case)

# render state hashes (see docs/MRL.md): everything else is written to the custom properties unchanged
BLEND_OPAQUE, BLEND_ALPHA, BLEND_ADD = 0x62B2D163, 0x23BAF165, 0xD3B1D16B
RASTER_CULL, RASTER_TWO_SIDED = 0x108CF19F, 0x923331AD
GAME_DATA_DIRS = ('chara', 'stage', 'event', 'effect', 'ui', 'menu', 'textures', 'sound', 'common', 'scr')


# --- where things are -------------------------------------------------------------------------------------

def virtual_path(filepath):
    """'data/chara/pl/pl0600/model/pl0610' for a file below a folder called data; None when there is no such folder"""
    parts = os.path.splitext(os.path.abspath(filepath))[0].replace('\\', '/').split('/')
    for i in range(len(parts) - 2, -1, -1):
        # the game's own data folder is followed by chara / stage / ...; a folder that merely has that name (E:/Data/..) is not
        if parts[i].lower() == 'data' and parts[i + 1].lower() in GAME_DATA_DIRS:
            return '/'.join(parts[i:])
    return None


def find_game_dirs(filepath='', configured=()):
    """folders that contain nativePC: the ancestors of the file (a mod folder, then the game) and the configured ones"""
    out = []
    p = os.path.dirname(os.path.abspath(filepath)) if filepath else ''
    while p and os.path.dirname(p) != p:
        if os.path.isdir(os.path.join(p, 'nativePC')):
            out.append(p)
        p = os.path.dirname(p)
    if isinstance(configured, str):
        configured = [configured]
    for c in configured:
        if c and os.path.isdir(os.path.join(c, 'nativePC')) and c not in out:
            out.append(c)
    return tuple(out)


def find_mrl(filepath):
    """(mrl bytes, where) of the material library of a model: <name>.mrl, else the first non empty <name>_N.mrl, looked up next
    to the file only. An import reads what the user has on disk and never falls back to the game archives (the original
    materials would end up in the collection and in the next export): (None, '') when nothing is there."""
    stem = os.path.splitext(filepath)[0]
    best = None
    for suffix in [''] + ['_%d' % i for i in range(4)]:
        p = stem + suffix + '.mrl'
        if not os.path.isfile(p):
            continue
        with open(p, 'rb') as fh:
            data = fh.read()
        try:
            m = R.parse(data)
        except R.MrlError:
            continue
        if m.materials:
            return data, p
        best = best or (data, p)
    return best if best else (None, '')


def own_root(filepath):
    """the folder above the data/ folder a model lies in (the root of its extracted tree), '' when it lies in none"""
    parts = os.path.dirname(os.path.abspath(filepath)).replace('\\', '/').split('/')
    for i in range(len(parts) - 1, -1, -1):
        if parts[i].lower() == 'data':
            return '/'.join(parts[:i])
    return ''


def texture_finder(filepath='', texture_dir='', pref_texture_dir='', game_paths=()):
    """the finder of an import: the folder the user picked, the model's own root, the model's folder, then the folders of the
    preferences (the order of the MHW Model Editor: what belongs to the model comes before what is configured for everything)"""
    own = own_root(filepath) if filepath else ''
    here = os.path.dirname(filepath) if filepath else ''
    return TextureFinder([texture_dir, own, here, pref_texture_dir, *game_paths], [texture_dir, here, pref_texture_dir])


class TextureFinder:
    """finds the .tex of a texture path of an MRL in the folders the user gave only (never in the game archives: an import reads
    what is on disk), the way the MHW Model Editor does: the exact path below each of `folders` in order, then - for paths that
    exist nowhere, like the custom folders of some mods - the bare file name directly inside each of `name_folders`
    (no sub folders are searched)"""

    def __init__(self, folders, name_folders=()):
        self.folders = [f for f in folders if f and os.path.isdir(f)]
        self.name_folders = [f for f in name_folders if f and os.path.isdir(f)]
        self._listing = {}

    def _names_in(self, folder):
        if folder not in self._listing:
            try:
                self._listing[folder] = {f.lower(): f for f in os.listdir(folder) if f.lower().endswith('.tex')}
            except OSError:
                self._listing[folder] = {}
        return self._listing[folder]

    @staticmethod
    def _load(p):
        with open(p, 'rb') as fh:
            return fh.read()

    def read(self, path):
        """bytes of the .tex for a texture path of the MRL, None when it cannot be found"""
        rel = path.replace('\\', '/').strip('/')
        for f in self.folders:
            cand = os.path.join(f, rel + '.tex')
            if os.path.isfile(cand):
                return self._load(cand)
        base = (rel.rsplit('/', 1)[-1] + '.tex').lower()
        for f in self.name_folders:
            hit = self._names_in(f).get(base)
            if hit:
                return self._load(os.path.join(f, hit))
        return None



# --- images -----------------------------------------------------------------------------------------------

def image_from_tex(key, name, data, colorspace, alpha_packed=False, pack=True, vpath=''):
    """Blender image from the bytes of a .tex (shared by every material that uses the same key), None if unreadable"""
    for im in bpy.data.images:
        if im.get(K_TEX) == key:
            return im
    try:
        dds = T.to_dds(data)
        head = T.parse(data)
    except T.TexError:
        return None
    cache = os.path.join(bpy.app.tempdir, 're6_tex')
    os.makedirs(cache, exist_ok=True)
    f = os.path.join(cache, hashlib.md5(key.encode()).hexdigest()[:12] + '.dds')
    with open(f, 'wb') as fh:
        fh.write(dds)
    im = bpy.data.images.load(f, check_existing=False)
    im.name = name
    im[K_TEX] = key
    im['re6_layout'], im['re6_fmt'] = head.layout, head.fmt
    if vpath:
        im[K_VPATH] = vpath
    im.colorspace_settings.name = colorspace
    if alpha_packed:
        im.alpha_mode = 'CHANNEL_PACKED'
    if pack:
        try:
            im.pack()
        except RuntimeError:
            pass
    return im


def load_image(path, finder, colorspace, alpha_packed=False, pack=True):
    """Blender image for a texture path of a .mrl, None when missing or unreadable"""
    key = R.tex_key(path)
    for im in bpy.data.images:
        if im.get(K_TEX) == key:
            return im
    data = finder.read(path)
    if data is None:
        return None
    return image_from_tex(key, os.path.basename(path.replace('\\', '/')), data, colorspace, alpha_packed, pack,
                          path.replace('/', '\\'))


def load_image_file(filepath, role, pack=True, vdir=''):
    """image from a .tex file or any image file Blender can read (png, dds, tga ...). `vdir` is the game folder new
    textures are written to ('data/chara/pl/pl0600/model'), used when the file is not below a data/ folder"""
    cs = 'sRGB' if role == 'albedo' else 'Non-Color'
    name = os.path.basename(filepath)
    stem = os.path.splitext(name)[0]
    vpath = virtual_path(filepath) or ((vdir.replace('\\', '/').strip('/') + '/' + stem) if vdir else '')
    vpath = vpath.replace('/', '\\')
    if filepath.lower().endswith('.tex'):
        with open(filepath, 'rb') as fh:
            data = fh.read()
        im = image_from_tex(R.tex_key(filepath), name[:-4], data, cs, role == 'normal', pack, vpath)
        if im is None:
            raise ValueError('%s is not a readable .tex (cubemap or unsupported format)' % name)
        return im
    im = bpy.data.images.load(filepath, check_existing=True)
    if vpath:
        im[K_VPATH] = vpath
    im.colorspace_settings.name = cs
    if role == 'normal':
        im.alpha_mode = 'CHANNEL_PACKED'
    if pack:
        try:
            im.pack()
        except RuntimeError:
            pass
    return im


# --- node trees -------------------------------------------------------------------------------------------

def dxt5nm_group():
    """node group: RE6 normal map (x in alpha, y in green, DXT5nm) -> regular RGB tangent space normal colour"""
    g = bpy.data.node_groups.get(NM_GROUP)
    if g is not None:
        return g
    g = bpy.data.node_groups.new(NM_GROUP, 'ShaderNodeTree')
    it = g.interface
    it.new_socket('Color', in_out='INPUT', socket_type='NodeSocketColor')
    it.new_socket('Alpha', in_out='INPUT', socket_type='NodeSocketFloat')
    flip = it.new_socket('Flip Green', in_out='INPUT', socket_type='NodeSocketFloat')
    flip.default_value, flip.min_value, flip.max_value = 1.0, 0.0, 1.0
    it.new_socket('Normal Color', in_out='OUTPUT', socket_type='NodeSocketColor')
    n = g.nodes
    gi = n.new('NodeGroupInput')
    go = n.new('NodeGroupOutput')
    gi.location, go.location = (-900, 0), (700, 0)
    sep = n.new('ShaderNodeSeparateColor')
    sep.location = (-700, 150)
    g.links.new(gi.outputs['Color'], sep.inputs[0])

    def math(op, a=None, b=None, c=None, loc=(0, 0)):
        m = n.new('ShaderNodeMath')
        m.operation = op
        m.location = loc
        for i, v in enumerate((a, b, c)):
            if v is None:
                continue
            if isinstance(v, (int, float)):
                m.inputs[i].default_value = v
            else:
                g.links.new(v, m.inputs[i])
        return m

    x = math('MULTIPLY_ADD', gi.outputs['Alpha'], 2.0, -1.0, (-500, 250))
    y0 = math('MULTIPLY_ADD', sep.outputs[1], 2.0, -1.0, (-500, 50))
    sgn = math('MULTIPLY_ADD', gi.outputs['Flip Green'], -2.0, 1.0, (-500, -150))
    y = math('MULTIPLY', y0.outputs[0], sgn.outputs[0], None, (-300, 50))
    xx = math('MULTIPLY', x.outputs[0], x.outputs[0], None, (-300, 250))
    yy = math('MULTIPLY', y.outputs[0], y.outputs[0], None, (-100, 50))
    s = math('ADD', xx.outputs[0], yy.outputs[0], None, (100, 150))
    d = math('SUBTRACT', 1.0, s.outputs[0], None, (250, 150))
    dm = math('MAXIMUM', d.outputs[0], 0.0, None, (400, 150))
    z = math('SQRT', dm.outputs[0], None, None, (550, 150))
    comb = n.new('ShaderNodeCombineColor')
    comb.location = (550, -100)
    for i, src in enumerate((x, y, z)):
        h = math('MULTIPLY_ADD', src.outputs[0], 0.5, 0.5, (350, -100 - 120 * i))
        g.links.new(h.outputs[0], comb.inputs[i])
    g.links.new(comb.outputs[0], go.inputs[0])
    return g


ROLES = ('albedo', 'normal', 'mask')
ROLE_NODE = {'albedo': 'RE6 Base', 'normal': 'RE6 Normal', 'mask': 'RE6 Mask'}
ROLE_LABEL = {'albedo': 'Base (BM)', 'normal': 'Normal (NM)', 'mask': 'Mask (MM)'}
ROLE_LOC = {'albedo': (-300, 300), 'normal': (-700, -50), 'mask': (-300, -420)}


def _ensure_base(mat):
    """Principled BSDF and output of a material (created when the node tree is empty)"""
    try:
        mat.use_nodes = True
    except AttributeError:
        pass
    nt = mat.node_tree
    bsdf = next((n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED'), None)
    if bsdf is None:
        nt.nodes.clear()
        out = nt.nodes.new('ShaderNodeOutputMaterial')
        out.location = (700, 0)
        bsdf = nt.nodes.new('ShaderNodeBsdfPrincipled')
        bsdf.location = (400, 0)
        bsdf.inputs['Roughness'].default_value = 0.6
        nt.links.new(bsdf.outputs['BSDF'], out.inputs['Surface'])
    return nt, bsdf


def set_role_image(mat, role, image, label=None):
    """put an image (or None = empty slot) into the base / normal / mask image node of a material, wiring it up"""
    nt, bsdf = _ensure_base(mat)
    node = nt.nodes.get(ROLE_NODE[role])
    if node is None:
        node = nt.nodes.new('ShaderNodeTexImage')
        node.name = ROLE_NODE[role]
        node.location = ROLE_LOC[role]
        node.width = 240
        if role == 'albedo':
            nt.links.new(node.outputs['Color'], bsdf.inputs['Base Color'])
            if mat.get('re6_blended'):
                nt.links.new(node.outputs['Alpha'], bsdf.inputs['Alpha'])
        elif role == 'normal':
            grp = nt.nodes.new('ShaderNodeGroup')
            grp.node_tree = dxt5nm_group()
            grp.location = (-420, -60)
            nm = nt.nodes.new('ShaderNodeNormalMap')
            nm.location = (200, -200)
            nt.links.new(node.outputs['Color'], grp.inputs['Color'])
            nt.links.new(node.outputs['Alpha'], grp.inputs['Alpha'])
            nt.links.new(grp.outputs[0], nm.inputs['Color'])
            nt.links.new(nm.outputs['Normal'], bsdf.inputs['Normal'])
    node.image = image
    node.label = label or ROLE_LABEL[role]
    return node


def build_nodes(mat, images, blend, raster, wanted=None):
    """Principled BSDF with albedo / normal / mask image nodes. `wanted` = {role: [paths]} of the .mrl; roles whose
    textures could not be found get an empty image node that names the missing file"""
    blended = blend in (BLEND_ALPHA, BLEND_ADD)
    mat['re6_blended'] = 1 if blended else 0
    for role in ROLES:
        if role in images:
            set_role_image(mat, role, images[role])
        elif wanted and role in wanted:
            missing = os.path.basename(wanted[role][0].replace('\\', '/'))
            set_role_image(mat, role, None, '%s: %s (missing)' % (ROLE_LABEL[role], missing))
    _ensure_base(mat)
    for attr, value in (('surface_render_method', 'BLENDED' if blended else 'DITHERED'),
                        ('use_backface_culling', raster != RASTER_TWO_SIDED)):
        try:
            setattr(mat, attr, value)
        except (AttributeError, TypeError):
            pass


# --- the MRL material data of an empty (object.re6_mrl_material) ---------------------------------------------------------

K_DATA = 're6_mat_data'                 # object property: JSON with the parts of the .mrl material that have no UI


def store_material(obj, mm, mrl=None, index=0, bindings=None):
    """copy one core Material (of `mrl`, or with explicit [(slot, path)] bindings) into the properties of an empty"""
    p = obj.re6_mrl_material
    p.hash = '%08x' % mm.name
    p.index = index
    p.shader = '%08x' % mm.type
    p.blend, p.depth, p.raster = '%08x' % mm.blend, '%08x' % mm.depth, '%08x' % mm.raster
    p.blend_mode = P.mode_of(P.BLEND_MODES, p.blend)
    p.raster_mode = P.mode_of(P.RASTER_MODES, p.raster)
    p.depth_mode = P.mode_of(P.DEPTH_MODES, p.depth)
    for k, v in R.unpack_flags(mm.flags, mm.unk_1c).items():
        setattr(p, k, bool(v) if isinstance(getattr(p, k), bool) else v)
    p.mapList_items.clear()
    for slot, path in (bindings if bindings is not None else R.bindings(mrl, mm)):
        it = p.mapList_items.add()
        it.name, it.code, it.value = slot_name(slot), '%08x' % slot, path or ''
    p.samplerList_items.clear()
    for slot, state in R.samplers(mm):
        it = p.samplerList_items.add()
        it.name, it.code, it.state = slot_name(slot), '%08x' % slot, '%08x' % state
        it.value = max(R.sampler_index(state, slot), 0)
    fill_properties(p, mm)
    obj[K_DATA] = json.dumps(dict(ncmd=mm.flags & 0xFFF, tail=list(mm.tail), cb_size=mm.cb_size,
                                  block=mm.block.hex(), anim=mm.anim.hex()))


# --- the property list (named values of the constant buffers) ------------------------------------------------------

VALUE_ATTR = {'FLOAT': 'float_value', 'FLOAT[2]': 'float2_value', 'FLOAT[3]': 'float3_value', 'FLOAT[4]': 'float4_value',
              'COLOR': 'color_value', 'COLOR4': 'color4_value'}
_COUNT_TYPE = {1: 'FLOAT', 2: 'FLOAT[2]', 3: 'FLOAT[3]', 4: 'FLOAT[4]'}


def _is_color(name):
    return name.endswith(('_color', '_color_2')) or 'rgb' in name


def _prop_type(name, count):
    if _is_color(name) and count in (3, 4):
        return 'COLOR' if count == 3 else 'COLOR4'
    return _COUNT_TYPE[count]


def get_floats(it):
    v = getattr(it, VALUE_ATTR[it.data_type])
    return (float(v),) if it.data_type == 'FLOAT' else tuple(float(x) for x in v)


def set_floats(it, vals):
    setattr(it, VALUE_ATTR[it.data_type], vals[0] if it.data_type == 'FLOAT' else vals)


def property_layout(buffer_hash, count):
    """[(property name, original field name, float offset, float count)] of a constant buffer: the named fields of the known
    layouts (padding is left out, values wider than 4 floats are cut into rows of 4), else rows of 4 named after their
    first float"""
    out = []
    lay = CL.layout_of(buffer_hash, count)
    pos = 0
    for name, n in (lay or [('', count)]):
        if name or not lay:
            for k in range(0, n, 4):
                c = min(4, n - k)
                if lay:
                    out.append((name if n <= 4 else '%s_%d' % (name, k // 4), name, pos + k, c))
                else:
                    out.append(('f%d' % (pos + k), 'f%d' % (pos + k), pos + k, c))
        pos += n
    return out


def fill_properties(p, mm):
    p.propertyBlock_items.clear()
    for h, off, n in R.cbuffers(mm):
        fields = property_layout(h, n)
        if not fields:
            continue
        blk = p.propertyBlock_items.add()
        blk.blockName, blk.code = name_of(h) or '%08x' % h, '%08x' % h
        for name, ori, pos, cnt in fields:
            it = blk.propertyList_items.add()
            it.prop_name, it.ori_name = name, ori
            it.offset = off + 4 * pos
            it.data_type = _prop_type(ori, cnt)
            set_floats(it, struct.unpack_from('<%df' % cnt, mm.block, it.offset))


def patch_block(block, p):
    """write the edited values into the command block (untouched values keep their exact bits)"""
    for blk in p.propertyBlock_items:
        for it in blk.propertyList_items:
            vals = get_floats(it)
            if it.offset + 4 * len(vals) > len(block):
                continue
            for k, new in enumerate(vals):
                old = struct.unpack_from('<f', block, it.offset + 4 * k)[0]
                if not (old == new or (old != old and new != new)):
                    struct.pack_into('<f', block, it.offset + 4 * k, new)


def _bsdf(mat):
    if mat is None or mat.node_tree is None:
        return None
    return next((n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None)


def apply_driven(it):
    """reflect a property that drives the preview material (see props.DRIVEN) on its Blender material"""
    obj = it.id_data
    if not hasattr(obj, 're6_mrl_material') or it.ori_name not in P.DRIVEN:
        return
    bsdf = _bsdf(obj.re6_mrl_material.linkedMaterial)
    if bsdf is None:
        return
    v = get_floats(it)
    try:
        if it.ori_name == 'shininess':
            bsdf.inputs['Roughness'].default_value = min(max((2.0 / (max(v[0], 0.0) + 2.0)) ** 0.5, 0.0), 1.0)
        elif it.ori_name == 'specular_color':
            bsdf.inputs['Specular Tint'].default_value = (v[0], v[1], v[2], 1.0)
    except (KeyError, IndexError, TypeError):
        pass


def sync_visual(obj):
    """apply the driving properties of an MRL empty to its preview material"""
    for blk in obj.re6_mrl_material.propertyBlock_items:
        for it in blk.propertyList_items:
            apply_driven(it)



def core_material(obj):
    """(core Material, {slot hash: path or None}) of an MRL empty; edited constant buffer values are patched into the
    command block (untouched values keep their exact bits)"""
    p = obj.re6_mrl_material
    d = json.loads(obj[K_DATA])
    block = bytearray.fromhex(d['block'])
    patch_block(block, p)
    block = bytes(block)
    flags, unk_1c = R.pack_flags({k: getattr(p, k) for k in R.FIELDS}, d['ncmd'])
    m = R.Material(type=int(p.shader, 16), name=int(p.hash, 16), size=len(block), blend=int(p.blend, 16),
                   depth=int(p.depth, 16), raster=int(p.raster, 16), flags=flags, unk_1c=unk_1c,
                   tail=tuple(d['tail']), cb_size=d['cb_size'], cmd_offset=0, anim_offset=0, block=block,
                   anim=bytes.fromhex(d['anim']))
    for k in range(m.flags & 0xFFF):
        m.commands.append(R.Command(*struct.unpack_from('<III', block, k * R.CMD_SIZE)))
    for it in p.samplerList_items:
        slot = int(it.code, 16)
        cur = int(it.state, 16) if it.state else 0
        state = R.sampler_state(slot, it.value, cur)
        if state is None:
            raise ValueError('%s: the sampler state %d of %s is not known (known: 0%s)' % (
                obj.name, it.value, it.name or it.code, ''.join(', %d' % i for (sl, i) in sorted(R.SAMPLER_STATES) if sl == slot)))
        for c in m.commands:
            if c.type == R.CMD_SAMPLER and c.b == slot:
                c.a = state
    binds = {int(b.code, 16): (b.value or None) for b in p.mapList_items}
    return m, binds


def image_tex_path(image):
    """texture path (backslashes, no extension) an image is written to / referenced by"""
    v = image.get(K_VPATH)
    if v:
        return v
    return 'data\\chara\\textures\\' + os.path.splitext(image.name)[0]


def set_binding(obj, role, path):
    """point the texture slot of an MRL empty that plays `role` at `path`; False when it has no slot for that role"""
    p = obj.re6_mrl_material
    cur = [(int(b.code, 16), b.value) for b in p.mapList_items]
    wanted = R.roles_of([(s, pa) for s, pa in cur if pa])
    target = None
    if role in wanted:
        target = next(s for s, pa in cur if pa == wanted[role][0])
    else:
        for s in R.SLOT_PRIORITY[role]:
            if any(cs == s for cs, _ in cur):
                target = s
                break
    if target is None:
        return False
    for b in p.mapList_items:
        if int(b.code, 16) == target:
            b.value = path
    return True


def owner_of(mat):
    """the MRL empty whose preview material is `mat`, None when there is none"""
    if mat is None:
        return None
    for o in bpy.data.objects:
        if o.type == 'EMPTY' and o.re6_mrl_material.hash and o.re6_mrl_material.linkedMaterial == mat:
            return o
    return None


def build_visual(obj, finder, pack=True):
    """create / refresh the preview material of an MRL empty from its texture slots; returns the number of textures found"""
    p = obj.re6_mrl_material
    mat = p.linkedMaterial
    if mat is None:
        h = int(p.hash, 16)
        mat = bpy.data.materials.new(C.mat_label(h))
        mat.diffuse_color = (*colorsys.hsv_to_rgb(((h >> 8) % 360) / 360.0, 0.35, 0.85), 1.0)
        p.linkedMaterial = mat
    mat[C.K_MAT_HASH] = p.hash
    wanted = R.roles_of([(int(b.code, 16), b.value) for b in p.mapList_items if b.value])
    images = {}
    for role, paths in wanted.items():
        cs = 'sRGB' if role == 'albedo' else 'Non-Color'
        for path in paths:
            im = load_image(path, finder, cs, alpha_packed=(role == 'normal'), pack=pack)
            if im is not None:
                images[role] = im
                break
    try:
        blend, raster = int(p.blend, 16), int(p.raster, 16)
    except ValueError:
        blend, raster = BLEND_OPAQUE, RASTER_CULL
    build_nodes(mat, images, blend, raster, wanted)
    sync_visual(obj)
    return len(images)
