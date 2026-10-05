# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 Dimcirui

"""Operators of the chain layer (ctc_operators.py of the MHW Model Editor)."""
import math

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty, StringProperty
from bpy.types import Operator
from mathutils import Matrix, Vector

from ..core import chain_ids as CI
from ..core import ctc as K
from . import bone_rename as BR
from . import common as C
from . import ctc_functions as F
from . import ctc_properties as CP
from . import objects as O
from . import prefs
from .i18n import iface, rpt

TYPE_NAMES = {C.T_CTC_HEADER: 'CTC Header', C.T_CTC_CHAIN: 'CTC Chain', C.T_CTC_NODE: 'CTC Node',
              C.T_CTC_FRAME: 'Angle Limit Orientation', C.T_CCL_SPHERE: 'CCL Sphere', C.T_CCL_CAPSULE: 'CCL Capsule'}


def tag_redraw(context):
    for window in context.window_manager.windows:
        for area in window.screen.areas:
            area.tag_redraw()


def selected_chains(context):
    """the selected chain objects, else every chain of the active ctc collection"""
    chains = [o for o in context.selected_objects if o.get(C.TYPE) == C.T_CTC_CHAIN]
    if not chains:
        col = context.scene.re6_ctc_toolpanel.ctcCollection
        chains = F.chain_objects(col) if col is not None else []
    return chains


# --- collection and modes --------------------------------------------------------------------------------------------------

class RE6_OT_create_ctc_collection(Operator):
    bl_label = 'Create CTC Collection'
    bl_idname = 're6_ctc.create_ctc_collection'
    bl_description = ('Create a ctc collection for putting ctc & ccl objects into.\nNote that a ctc header object will also be '
                      'created, and all ctc & ccl objects must be parented to it')
    bl_options = {'UNDO'}

    collectionName: StringProperty(name='CTC Name', default='pl0000',
                                   description='The name of the newly created ctc collection.\nUse the same name as the ctc file')

    def invoke(self, context, event):
        name = context.scene.re6_mod_toolpanel.get('lastImportCollection')
        if name is not None and '.mod' in name:
            self.collectionName = name.split('.mod')[0]
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        name = self.collectionName.strip()
        if name == '':
            self.report({'ERROR'}, rpt('Invalid ctc collection name.'))
            return {'CANCELLED'}
        parent = bpy.data.collections.get(name)
        if parent is None:
            parent = O.get_collection(name, make_new=True)
        prefs.load_ctc_visibility(context.scene)
        col = O.create_collection(name + '.ctc', 'COLOR_02', C.T_CTC, parent)
        context.scene.re6_ctc_toolpanel.ctcCollection = col
        header = F.create_header(col, 'CTC_HEADER %s.ctc' % name)
        context.view_layer.objects.active = header
        self.report({'INFO'}, rpt('Created new ctc collection.'))
        return {'FINISHED'}


def _armature(context):
    arm = context.active_object if context.active_object is not None and context.active_object.type == 'ARMATURE' else None
    if arm is None:
        arm = next((o for o in context.scene.objects if o.type == 'ARMATURE'), None)
    return arm


class RE6_OT_switch_to_pose_mode(Operator):
    bl_label = 'Switch To Pose Mode'
    bl_idname = 're6_ctc.switch_to_pose_mode'
    bl_description = 'Switch to pose mode to add new ctc chains or ccl collisions'
    bl_options = {'UNDO'}

    def execute(self, context):
        try:
            arm = _armature(context)
            if arm is not None:
                if context.mode == 'OBJECT':
                    for o in context.selected_objects:
                        o.select_set(False)
                    context.view_layer.objects.active = arm
                    arm.select_set(True)
                bpy.ops.object.mode_set(mode='POSE')
        except RuntimeError:
            pass
        return {'FINISHED'}


class RE6_OT_switch_to_object_mode(Operator):
    bl_label = 'Switch To Object Mode'
    bl_idname = 're6_ctc.switch_to_object_mode'
    bl_description = 'Switch to object mode to configure ctc chains or ccl collisions'
    bl_options = {'UNDO'}

    def execute(self, context):
        try:
            bpy.ops.object.mode_set(mode='OBJECT')
        except RuntimeError:
            pass
        return {'FINISHED'}


# --- chains from bones -----------------------------------------------------------------------------------------------------

def _bone_chain(bone):
    """bone and its descendants; None when a bone has more than one child"""
    out = [bone]
    while True:
        kids = out[-1].children
        if len(kids) > 1:
            return None
        if not kids:
            return out
        out.append(kids[0])


def frame_rows_between(arm_obj, bone, nxt):
    """the node matrix (rows of the file) that points the angle limit at the next bone, in the frame of the bone"""
    if nxt is None:
        return [(1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)]
    d = arm_obj.matrix_world.to_3x3() @ (nxt.head_local - bone.head_local)
    rot = (arm_obj.matrix_world @ bone.matrix_local).to_3x3()
    local = rot.inverted() @ d
    if local.length < 1e-9:
        return [(1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)]
    m = O.orient_vector_pair((1.0, 0.0, 0.0), local.normalized()).to_3x3()
    return [tuple(m[c][r] for c in range(3)) for r in range(3)]            # the transpose: the rows of the file


class RE6_OT_create_chain_from_bone(Operator):
    bl_label = 'Create Chain'
    bl_idname = 're6_ctc.create_chain_from_bone'
    bl_description = ('Create new ctc chain objects starting from the selected bone and ending at the last child bone.'
                      '\nThe button will only be triggered if active ctc collection exists.'
                      '\nBones in a chain must be named with format "RE6Bone_xxx"')
    bl_options = {'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.scene.re6_ctc_toolpanel.ctcCollection is not None

    def execute(self, context):
        tp = context.scene.re6_ctc_toolpanel
        arm = context.active_object
        sel = list(context.selected_pose_bones or [])
        if arm is None or arm.type != 'ARMATURE' or len(sel) != 1:
            C.show_error_message_box(iface('Select only the chain start bone.'))
            return {'CANCELLED'}
        bones = _bone_chain(sel[0].bone)
        if bones is None:
            C.show_error_message_box(iface('Cannot have branching bones in a chain.'))
            return {'CANCELLED'}
        if len(bones) < 2:
            C.show_error_message_box(iface('A chain must have at least 2 bones.'))
            return {'CANCELLED'}
        if any(C.bone_fn_id(b) is None for b in bones):
            C.show_error_message_box(iface('Current chain has some bones that are not named with format "RE6Bone_xxx".'))
            return {'CANCELLED'}
        col = tp.ctcCollection
        header = F.find_header(col) or F.create_header(col, 'CTC_HEADER ' + col.name)
        entry_col = F.entries_collection('Chain Entries', col, make_new=False)
        index = 0
        while O.name_in_use('CTC_CHAIN_%02d' % index):
            index += 1
        names = [b.name for b in bones]
        frames = [(frame_rows_between(arm, b, bones[k + 1] if k + 1 < len(bones) else None), None, 0)
                  for k, b in enumerate(bones)]
        F.make_chain(tp, header, entry_col, arm, 'CTC_CHAIN_%02d - %s > %s' % (index, names[0], names[-1]), K.Chain(),
                     [K.Node() for _ in names], names, frames)
        F.align_chains(col)
        F.set_chain_bone_color(arm, col)
        self.report({'INFO'}, rpt('Created ctc chain from bone.'))
        return {'FINISHED'}


def _wrap_ids(ids, width=46):
    """the ids as lines of ranges ("56-59, 98-99, ...") that fit a dialog"""
    lines, cur = [], ''
    for part in CI.format_runs(ids).split(', '):
        if cur and len(cur) + len(part) + 2 > width:
            lines.append(cur)
            cur = ''
        cur = part if not cur else cur + ', ' + part
    return lines + ([cur] if cur else [])


class RE6_OT_rename_chain_bones(Operator):
    bl_label = 'Rename Chain Bones'
    bl_idname = 're6_ctc.rename_chain_bones'
    bl_description = ('Rename all bones in a chain with format "RE6Bone_xxx".\nIf a ctc chain has been created, all node names '
                      'in the chain will also be renamed.\nThe IDs are taken from the range that is available for the chosen '
                      'character and part; an ID outside of it is refused.\nCheck button on the right for detailed settings')
    bl_options = {'UNDO'}

    character: EnumProperty(name='Character', items=[(i, l, '') for i, l, _ in CI.CHARACTERS],
                            description='Which IDs may be used.\nGeneric is the most conservative choice: only IDs that are free '
                                        'in every character\nA character offers all IDs that nothing of that character uses')
    part: EnumProperty(name='Part', items=[(i, l, '') for i, l, _ in CI.PARTS],
                       description='The part of the model (plXXz0 body, plXXz3 head) the chain is on.\nThe available IDs '
                                   'depend on it')
    newStartBoneID: IntProperty(name='Start Bone ID', default=0, min=0, max=C.MAX_BONE_FUNCTION,
                                description='Current chain will be renamed with the ID entered, then the next available IDs of the '
                                            'range, counting up from the first bone.\nIt must be inside the available range.'
                                            '\nIt is filled in with the next free ID after the last renamed chain')

    lastSel: StringProperty(options={'HIDDEN', 'SKIP_SAVE'})        # character / part the start ID was suggested for

    @classmethod
    def poll(cls, context):
        return context.active_object is not None

    @staticmethod
    def chain(context):
        sel = list(context.selected_pose_bones or [])
        return _bone_chain(sel[0].bone) if len(sel) == 1 else None

    def suggest(self, context):
        chain = self.chain(context)
        self.newStartBoneID = CI.suggest_start(self.pool(context, chain), context.scene.re6_ctc_toolpanel.nextChainBoneID,
                                               len(chain) if chain else 1)
        self.lastSel = self.character + self.part

    def check(self, context):
        """the dialog redraws on every change: another character / part moves the start ID into its range"""
        if self.lastSel != self.character + self.part:
            self.suggest(context)
        return True

    def used_ids(self, context, chain=None):
        """ids of the bones of the armature, without the bones that are renamed"""
        arm = context.active_object
        if arm is None or arm.type != 'ARMATURE':
            return set()
        skip = {b.name for b in chain or ()}
        return {C.bone_fn_id(b) for b in arm.data.bones if b.name not in skip}

    def pool(self, context, chain=None):
        """the ids of the chosen range that no other bone of the armature uses"""
        return CI.free_pool(self.character, self.part, self.used_ids(context, chain))

    def invoke(self, context, event):
        tp = context.scene.re6_ctc_toolpanel
        self.character, self.part = tp.chainIdCharacter, tp.chainIdPart
        self.suggest(context)
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        layout = self.layout
        chain = self.chain(context)
        count = len(chain) if chain else 1
        pool = self.pool(context, chain)
        layout.prop(self, 'character')
        layout.prop(self, 'part')
        layout.prop(self, 'newStartBoneID')
        layout.label(text='%s %d' % (iface('Count Of Available IDs:'), len(pool)))
        if self.newStartBoneID not in pool:
            layout.label(text=iface('The start ID is outside of the available range.'), icon='ERROR')
        elif len([i for i in pool if i >= self.newStartBoneID]) < count:
            layout.label(text=iface('Not enough available IDs left from the start ID.'), icon='ERROR')
        layout.label(text=iface('Available IDs:'))
        for line in _wrap_ids(pool):
            layout.label(text=line)

    def error(self, e):
        ch = iface(CI.label_of(CI.CHARACTERS, self.character))
        pt = iface(CI.label_of(CI.PARTS, self.part))
        if e.kind == 'empty':
            C.show_error_message_box(iface('No available ID is left in the range of %s / %s.') % (ch, pt))
        elif e.kind == 'outside':
            C.show_error_message_box(iface('Bone ID %d is outside of the available range of %s / %s. Please select another '
                                           'start ID.') % (e.args_[0], ch, pt))
        else:
            C.show_error_message_box(iface('The chain has %d bones, but only %d available IDs are left from ID %d in the range '
                                           'of %s / %s. Please select another start ID.') % (e.args_[0], e.args_[1], e.args_[2], ch,
                                                                                            pt))

    def execute(self, context):
        arm = context.active_object
        sel = list(context.selected_pose_bones or [])
        if arm is None or arm.type != 'ARMATURE' or len(sel) != 1:
            C.show_error_message_box(iface('Select only the chain start bone.'))
            return {'CANCELLED'}
        bones = _bone_chain(sel[0].bone)
        if bones is None:
            C.show_error_message_box(iface('Cannot have branching bones in a chain.'))
            return {'CANCELLED'}
        try:
            ids = CI.pick_ids(self.pool(context, bones), self.newStartBoneID, len(bones))
        except CI.ChainIdError as e:
            self.error(e)
            return {'CANCELLED'}
        olds = [b.name for b in bones]
        news = ['%s%03d' % (C.BONE_PREFIX, i) for i in ids]
        existing = {b.name for b in arm.data.bones} - set(olds)
        if any(n in existing for n in news):
            C.show_error_message_box(iface('Current start ID will result in duplicate bone names. Please select another start '
                                           'ID.'))
            return {'CANCELLED'}
        tp = context.scene.re6_ctc_toolpanel
        tp.chainIdCharacter, tp.chainIdPart = self.character, self.part
        # the same routine as Match Bone Names: bones, vertex groups, mirror names, chain / node / collision object names
        BR.rename_bones(arm, dict(zip(olds, news)))
        tp.nextChainBoneID = min(ids[-1] + 1, C.MAX_BONE_FUNCTION)
        self.report({'INFO'}, rpt('Renamed chain bones.'))
        return {'FINISHED'}


class RE6_OT_rename_bone_settings(Operator):
    bl_label = 'Rename Bone Settings'
    bl_idname = 're6_ctc.rename_bone_settings'
    bl_description = 'Detail settings for renaming chain bones'
    bl_options = {'UNDO'}

    def execute(self, context):
        return {'FINISHED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def check(self, context):
        return True

    def draw(self, context):
        tp = context.scene.re6_ctc_toolpanel
        box = self.layout.box()
        col = box.column(align=True)
        row = col.row(align=True)
        row.scale_y = 1.1
        row.prop(tp, 'alignBoneDirection')
        row = col.row(align=True)
        row.scale_y = 1.1
        row.prop(tp, 'nextChainBoneID')


# --- editing ---------------------------------------------------------------------------------------------------------------

class RE6_OT_align_frames(Operator):
    bl_label = 'Align Angle Limit Direction'
    bl_idname = 're6_ctc.align_frames'
    bl_description = ('Aligns angle limit direction with the next node in the chain.\nYou can select one or more ctc chain '
                      'objects to align.\nNote that additional adjustments may be required for the angle limit to work properly')
    bl_options = {'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.scene.re6_ctc_toolpanel.ctcCollection is not None

    def execute(self, context):
        chains = selected_chains(context)
        if not chains:
            C.show_error_message_box(iface('No chains found in selected objects or active ctc collection.'))
            return {'CANCELLED'}
        for chain in chains:
            nodes = F.chain_nodes(chain)
            for k, node in enumerate(nodes):
                con = node.constraints.get('BoneName')
                frame = CP.frame_of(node)
                if con is None or con.target is None or frame is None:
                    continue
                arm = con.target
                nxt = None
                if k + 1 < len(nodes):
                    c2 = nodes[k + 1].constraints.get('BoneName')
                    nxt = arm.data.bones.get(c2.subtarget) if c2 is not None else None
                rows = frame_rows_between(arm, arm.data.bones[con.subtarget], nxt)
                frame.matrix_basis = F.rows_to_basis(rows)
                if F.K_MATRIX in frame:
                    del frame[F.K_MATRIX]
        self.report({'INFO'}, rpt('Aligned angle limit directions.'))
        return {'FINISHED'}


class RE6_OT_apply_angle_limit_ramp(Operator):
    bl_label = 'Apply Angle Limit Ramp'
    bl_idname = 're6_ctc.apply_angle_limit_ramp'
    bl_description = ('Apply an increasing angle limit radius on each ctc node as it gets further away.\nYou can select one or '
                      'more ctc chain objects to apply ramp')
    bl_options = {'UNDO'}

    maxAngleLimit: FloatProperty(
        name='Max Angle Limit', default=math.pi / 3, step=100, soft_min=0.0, soft_max=math.pi, subtype='ANGLE',
        description='The maximum angle limit radius after the max iteration number is reached.\nFor example, if the max angle '
                    'limit is 60 and the max iteration is 4, the first node angle limit will be 15, the second will be 30 and '
                    'so on.\nOnce the max iteration is reached, all nodes after that will be the max angle limit value')
    maxIteration: IntProperty(name='Max Iteration', default=4, min=1,
                              description='The amount of ctc nodes until the angle limit radius is at it\'s maximum value')

    reverse: BoolProperty(name='Reverse', default=False,
                          description='Reverse the order of the ramp: the angle limit radius decreases as the node gets further '
                                      'away instead of increasing')

    @classmethod
    def poll(cls, context):
        return any(o.get(C.TYPE) == C.T_CTC_CHAIN for o in context.selected_objects)

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        chains = [o for o in context.selected_objects if o.get(C.TYPE) == C.T_CTC_CHAIN]
        if not chains:
            C.show_error_message_box(iface('Must select one or more ctc chain objects to apply ramp.'))
            return {'CANCELLED'}
        step = self.maxAngleLimit / self.maxIteration
        for chain in chains:
            nodes = F.chain_nodes(chain)
            for i, node in enumerate(reversed(nodes) if self.reverse else nodes):
                node.re6_ctc_node.AngleLimitRadius = step * (i + 1) if i + 1 < self.maxIteration else self.maxAngleLimit
        self.report({'INFO'}, rpt('Applied angle limit ramp to selected ctc chains.'))
        return {'FINISHED'}


# --- clipboard -------------------------------------------------------------------------------------------------------------
# The clipboard holds named properties, so that it can paste between ctc and ccl objects: a target gets the properties it has
# under the same name (the collision radius of a node and of a collision, the head offset of a sphere and of a capsule ...);
# properties the target does not have are dropped, properties the clipboard does not have are left alone.

def _same(keys):
    return {k: k for k in keys}


# object type -> (property group on the object and on the clipboard, {clipboard name: property of the group})
CLIP_FIELDS = {
    C.T_CTC_HEADER: ('re6_ctc_header', _same(CP.HEADER_KEYS)),
    C.T_CTC_CHAIN: ('re6_ctc_chain', _same(CP.CHAIN_KEYS)),
    C.T_CTC_NODE: ('re6_ctc_node', {**_same(k for k in CP.NODE_KEYS if k != 'BoneColRadius'), 'ColRadius': 'BoneColRadius'}),
    C.T_CCL_SPHERE: ('re6_ccl_collision', _same(('StartColOffset', 'ColRadius'))),
    C.T_CCL_CAPSULE: ('re6_ccl_collision', _same(('StartColOffset', 'EndColOffset', 'ColRadius'))),
}


def clip_object(obj):
    """the object whose properties are copied / pasted: the head and tail of a capsule stand for the capsule"""
    if obj is not None and obj.get(C.TYPE) in (C.T_CCL_START, C.T_CCL_END) and obj.parent is not None \
            and obj.parent.get(C.TYPE) == C.T_CCL_CAPSULE:
        return obj.parent
    return obj


def copy_to_clipboard(cb, obj, keys=None):
    """keys: clipboard names to copy (all properties of the type when None)"""
    t = obj.get(C.TYPE)
    group, fields = CLIP_FIELDS[t]
    keys = list(fields) if keys is None else [k for k in keys if k in fields]
    src, dst = getattr(obj, group), getattr(cb, group)
    for k in keys:
        setattr(dst, fields[k], getattr(src, fields[k]))
    cb.ctc_type, cb.ctc_type_name = t, TYPE_NAMES[t]
    cb.prop_keys = ','.join(keys)


def paste_from_clipboard(cb, obj):
    """paste the properties the target has; False when it shares none with the clipboard"""
    if cb.ctc_type not in CLIP_FIELDS or obj.get(C.TYPE) not in CLIP_FIELDS:
        return False
    src_group, src_fields = CLIP_FIELDS[cb.ctc_type]
    dst_group, dst_fields = CLIP_FIELDS[obj.get(C.TYPE)]
    keys = [k for k in cb.prop_keys.split(',') if k in src_fields and k in dst_fields]
    src, dst = getattr(cb, src_group), getattr(obj, dst_group)
    for k in keys:
        setattr(dst, dst_fields[k], getattr(src, src_fields[k]))
    return bool(keys)


class RE6_OT_copy_ctc_properties(Operator):
    bl_label = 'Copy'
    bl_idname = 're6_ctc.copy_ctc_properties'
    bl_description = ('Copy properties from a ctc or ccl object.\nThe button will only be triggered if a ctc or ccl object is '
                      'activated')
    bl_options = {'UNDO'}

    @classmethod
    def poll(cls, context):
        o = clip_object(context.active_object)
        return o is not None and o.get(C.TYPE) in TYPE_NAMES

    def execute(self, context):
        obj = clip_object(context.active_object)
        cb = context.scene.re6_ctc_clipboard
        t = obj.get(C.TYPE)
        cb.node_prop_type = cb.node_prop_name = ''
        if t == C.T_CTC_FRAME:
            cb.ctc_type, cb.ctc_type_name, cb.prop_keys = t, TYPE_NAMES[t], ''
            cb.frameOrientation = obj.matrix_basis.to_euler('XYZ')
        else:
            copy_to_clipboard(cb, obj)
        self.report({'INFO'}, rpt('Copied properties of %s object to clipboard.') % TYPE_NAMES[t].lower())
        return {'FINISHED'}


class _CopyNodeProp(Operator):
    bl_label = 'Copy'
    bl_description = 'Copy a specific property from a ctc node object to clipboard'
    bl_options = {'UNDO'}
    prop_type = ''
    prop_name = ''
    keys = ()

    def execute(self, context):
        obj = context.active_object
        if obj is None or obj.get(C.TYPE) != C.T_CTC_NODE:
            return {'CANCELLED'}
        cb = context.scene.re6_ctc_clipboard
        copy_to_clipboard(cb, obj, self.keys)
        cb.node_prop_type, cb.node_prop_name = self.prop_type, self.prop_name
        self.report({'INFO'}, rpt('Copied %s property to clipboard.') % self.prop_name.lower())
        return {'FINISHED'}


def _copy_op(idname, prop_type, prop_name, keys):
    return type('RE6_OT_' + idname, (_CopyNodeProp,), {
        'bl_idname': 're6_ctc.' + idname, 'prop_type': prop_type, 'prop_name': prop_name, 'keys': keys,
        '__annotations__': {}})


COPY_OPS = (
    _copy_op('copy_node_unknflags', 'UnknFlags', 'Unkn Flags', ('unknByte1', 'unknByte2')),
    _copy_op('copy_node_anglemode', 'AngleMode', 'Angle Mode', ('AngleMode',)),
    _copy_op('copy_node_collisionshape', 'CollisionShape', 'Collision Shape', ('CollisionShape',)),
    _copy_op('copy_node_unknenum', 'unknEnum', 'Unkn Enum', ('unknEnum',)),
    _copy_op('copy_node_bonecolradius', 'BoneColRadius', 'Collision Radius', ('ColRadius',)),
    _copy_op('copy_node_angleradius', 'AngleLimitRadius', 'Angle Radius', ('AngleLimitRadius',)),
    _copy_op('copy_node_mass', 'Mass', 'Mass', ('Mass',)),
    _copy_op('copy_node_elasticcoef', 'ElasticCoef', 'Elastic Coef', ('ElasticCoef',)),
)


class RE6_OT_paste_ctc_properties(Operator):
    bl_label = 'Paste'
    bl_idname = 're6_ctc.paste_ctc_properties'
    bl_description = ('Paste properties from a ctc or ccl object to selected objects.\nOnly the properties that the selected '
                      'objects also have are pasted, for example the collision radius of a ctc node to a ccl collision')
    bl_options = {'UNDO'}

    @classmethod
    def poll(cls, context):
        return bool(context.selected_objects)

    def execute(self, context):
        cb = context.scene.re6_ctc_clipboard
        if cb.ctc_type == 'NONE':
            C.show_error_message_box(iface('Select at least one ctc object to paste.'))
            return {'FINISHED'}
        targets = list(dict.fromkeys(clip_object(o) for o in context.selected_objects))
        pasted = 0
        for o in targets:
            if cb.ctc_type == C.T_CTC_FRAME:
                if o.get(C.TYPE) != C.T_CTC_FRAME:
                    continue
                o.rotation_euler = cb.frameOrientation
                if F.K_MATRIX in o:
                    del o[F.K_MATRIX]
                pasted += 1
            elif paste_from_clipboard(cb, o):
                pasted += 1
        if not pasted:
            C.show_error_message_box(iface('Select at least one ctc or ccl object that has the properties of the clipboard '
                                           'content to paste.'))
            return {'FINISHED'}
        tag_redraw(context)
        if cb.node_prop_type:
            self.report({'INFO'}, rpt('Pasted %s property from clipboard.') % cb.node_prop_name.lower())
        else:
            self.report({'INFO'}, rpt('Pasted properties of %s object from clipboard.') % cb.ctc_type_name.lower())
        return {'FINISHED'}


# --- visibility ------------------------------------------------------------------------------------------------------------

def _only_show(context, keep, message):
    tp = context.scene.re6_ctc_toolpanel
    for o in context.scene.objects:
        if o.get(C.TYPE) in keep:
            continue
        if o.type == 'MESH' and tp.reserveMeshObjects:
            continue
        o.hide_viewport = True
    for o in context.scene.objects:
        if o.get(C.TYPE) in keep:
            o.hide_viewport = False
    return message


class _Visibility(Operator):
    bl_options = {'UNDO'}
    keep = ()
    message = ''

    def execute(self, context):
        self.report({'INFO'}, rpt(_only_show(context, self.keep, self.message)))
        return {'FINISHED'}


class RE6_OT_only_show_chains(_Visibility):
    bl_label = 'Only Show Chains'
    bl_idname = 're6_ctc.only_show_chains'
    bl_description = 'Hide other objects and only show ctc chain objects.\nPress the "Show All Objects" button to recover'
    keep = (C.T_CTC_CHAIN, C.T_CTC_HELPER)
    message = 'Hid all non ctc chain objects.'


class RE6_OT_only_show_nodes(_Visibility):
    bl_label = 'Only Show Nodes'
    bl_idname = 're6_ctc.only_show_nodes'
    bl_description = 'Hide other objects and only show ctc node objects.\nPress the "Show All Objects" button to recover'
    keep = (C.T_CTC_NODE, C.T_CTC_HELPER)
    message = 'Hid all non ctc node objects.'


class RE6_OT_only_show_angle_limits(_Visibility):
    bl_label = 'Only Show Angle Limits'
    bl_idname = 're6_ctc.only_show_angle_limits'
    bl_description = 'Hide other objects and only show angle limit objects.\nPress the "Show All Objects" button to recover'
    keep = (C.T_CTC_FRAME, C.T_CTC_HELPER)
    message = 'Hid all non angle limit objects.'


class RE6_OT_show_all_objects(Operator):
    bl_label = 'Show All Objects'
    bl_idname = 're6_ctc.show_all_objects'
    bl_description = 'Unhide all objects hidden with above buttons'
    bl_options = {'UNDO'}

    def execute(self, context):
        tp = context.scene.re6_ctc_toolpanel
        for o in context.scene.objects:
            if o.get(C.TYPE) == C.T_CTC_HELPER:
                last = bool(o.get('isLastNode'))
                o.hide_viewport = not tp.showAngleLimitCones or (last and tp.hideLastNodeAngleLimit)
            else:
                o.hide_viewport = False
        self.report({'INFO'}, rpt('Unhid all objects.'))
        return {'FINISHED'}


# --- flags -----------------------------------------------------------------------------------------------------------------

class RE6_OT_set_collision_flags(Operator):
    bl_label = 'Set Collision Flags'
    bl_idname = 're6_ctc.set_collision_flags'
    bl_description = 'Set flags from a list of detail values'
    bl_options = {'UNDO', 'INTERNAL'}

    CollisionSelfEnable: BoolProperty(name='Collision Self Enable', default=False,
                                      description='Whether the chain is allowed to collide with other chains')
    CollisionModelEnable: BoolProperty(name='Collision Model Enable', default=True,
                                       description='Whether the chain is allowed to collide with ccl file')
    CollisionVGroundEnable: BoolProperty(name='Collision VGround Enable', default=False,
                                         description='Whether the chain is allowed to collide with the ground. Disabled: never written,'
                                                     ' the chains stay behind in scripted motions (e.g. crawling under an obstacle)')

    BITS = (('CollisionSelfEnable', 2), ('CollisionModelEnable', 4), ('CollisionVGroundEnable', 8))

    @classmethod
    def poll(cls, context):
        return context.active_object is not None and context.active_object.get(C.TYPE) == C.T_CTC_CHAIN

    def invoke(self, context, event):
        v = context.active_object.re6_ctc_chain.CollisionAttrFlagValue
        for name, bit in self.BITS:
            setattr(self, name, bool(v & bit))
        self.CollisionVGroundEnable = False
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        col = self.layout.column()
        col.prop(self, 'CollisionSelfEnable')
        col.prop(self, 'CollisionModelEnable')
        row = col.row()
        row.enabled = False        # greyed out: with VGround the chains stay behind in scripted motions (crawl under obstacles)
        row.prop(self, 'CollisionVGroundEnable')

    def execute(self, context):
        targets = {context.active_object} | {o for o in context.selected_objects if o.get(C.TYPE) == C.T_CTC_CHAIN}
        for o in targets:
            pg = o.re6_ctc_chain
            known = sum(b for _n, b in self.BITS)
            pg.CollisionAttrFlagValue = (pg.CollisionAttrFlagValue & ~known & 255) | sum(
                b for n, b in self.BITS if n != 'CollisionVGroundEnable' and getattr(self, n))
        self.report({'INFO'}, rpt('Set collision flags.'))
        return {'FINISHED'}


class RE6_OT_set_chain_flags(Operator):
    bl_label = 'Set Chain Flags'
    bl_idname = 're6_ctc.set_chain_flags'
    bl_description = 'Set flags from a list of detail values'
    bl_options = {'UNDO', 'INTERNAL'}

    AngleLimitEnable: BoolProperty(
        name='Angle Limit Enable', default=True,
        description='Whether to enable angle limit.\nUsually recommended to enable it, otherwise angle limit will be invalid')
    AngleLimitRestitutionEnable: BoolProperty(name='Angle Limit Restitution Enable', default=True,
                                              description='Whether to enable angle limit restitution')
    EndRotConstraintEnable: BoolProperty(name='End Rot Constraint Enable', default=True,
                                         description='Whether to enable the rotation of end node (uncertain)')
    TransAnimationEnable: BoolProperty(
        name='Trans Animation Enable', default=False,
        description='Whether to enable trans animation.\nAfter activating, the chain will stagnate in a motion stop posture, '
                    'but the specific meaning is unclear')
    AngleFreeEnable: BoolProperty(name='Angle Free Enable', default=False, description='Whether to enable angle free')
    StretchBothEnable: BoolProperty(
        name='Stretch Both Enable', default=True,
        description='Whether to enable stretch (uncertain).\nDepends on the mass and elasticity of the nodes')
    PartBlendEnable: BoolProperty(
        name='Part Blend Enable', default=False,
        description='Whether to enable part blend.\nAfter activating, the chain seems to squeeze towards the center, but the '
                    'specific meaning is unclear')

    BITS = (('AngleLimitEnable', 1), ('AngleLimitRestitutionEnable', 2), ('EndRotConstraintEnable', 4),
            ('TransAnimationEnable', 8), ('AngleFreeEnable', 16), ('StretchBothEnable', 32), ('PartBlendEnable', 64))

    @classmethod
    def poll(cls, context):
        return context.active_object is not None and context.active_object.get(C.TYPE) == C.T_CTC_CHAIN

    def invoke(self, context, event):
        v = context.active_object.re6_ctc_chain.ChainAttrFlagValue
        for name, bit in self.BITS:
            setattr(self, name, bool(v & bit))
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        targets = {context.active_object} | {o for o in context.selected_objects if o.get(C.TYPE) == C.T_CTC_CHAIN}
        for o in targets:
            pg = o.re6_ctc_chain
            known = sum(b for _n, b in self.BITS)
            pg.ChainAttrFlagValue = (pg.ChainAttrFlagValue & ~known & 255) | sum(b for n, b in self.BITS if getattr(self, n))
        self.report({'INFO'}, rpt('Set chain flags.'))
        return {'FINISHED'}


CLASSES = (RE6_OT_create_ctc_collection, RE6_OT_switch_to_pose_mode, RE6_OT_switch_to_object_mode,
           RE6_OT_create_chain_from_bone, RE6_OT_rename_chain_bones, RE6_OT_rename_bone_settings, RE6_OT_align_frames,
           RE6_OT_apply_angle_limit_ramp, RE6_OT_copy_ctc_properties, *COPY_OPS, RE6_OT_paste_ctc_properties,
           RE6_OT_only_show_chains, RE6_OT_only_show_nodes, RE6_OT_only_show_angle_limits, RE6_OT_show_all_objects,
           RE6_OT_set_collision_flags, RE6_OT_set_chain_flags)


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
