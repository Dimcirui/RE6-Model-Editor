# RE6 chain physics (.ctc) and chain collision (.ccl)

Both exist in the retail archives (class `rCnsTinyChain`, hash 535d969f, 289 files, 48 distinct contents; class `rChainCol`, hash 0026e7ff, 131 files, 16 distinct contents).
They sit next to the model (`pl0600.ctc` beside `pl0600.mod`, head variants `pl0603.ctc` / `pl0603.ccl`); the `.mod` does not name them. Loose copies in mod folders are byte
identical to the retail ones. Parsers: `core/ctc.py`, `core/ccl.py` (byte-exact parse -> serialize on 292 `.ctc` and 132 `.ccl`, `tools/roundtrip_ctc_ccl.py`);
extraction: `tools/extract_ctc_ccl.py`. Little endian, centimetres, no Blender dependency.

## CTC (version 22; MHW uses 28)

`size == 60 + 80 * chains + 96 * nodes` in every retail file; the nodes of chain 0 come first.

| part | RE6 | MHW |
|---|---|---|
| header | 60 bytes | 80 (the extra 20 are WindScaleMin / Max / Weight[3]) |
| chain | 80 bytes | 80 |
| node | 96 bytes | 112 |

* **Header**: `'CTC\0'`, version 22, unkn1 (0), unkn2 (1000), chain count, node count, attribute flags (0 in 259 files, 64 in 29, 12 in 1), step time 1/60, gravity scaling 1,
  global damping, trans force coef 1, spring scaling 1, wind scale 1, six solve counts (all 1), 2 pad bytes.
* **Chain**: node count, collision attr flag, chain attr flag (bit 0 angle limit, 1 restitution, 2 end rotation constraint, 3 trans animation, 4 angle free, 5 stretch,
  6 part blend; only 0, 1, 2, 5 seen), two unknown flags, colAttribute (-1), colGroup (1), colType (1), 12 x 0xCD, gravity xyz (cm/s^2, mostly (0, -980, 0)), 4 zero bytes,
  damping, trans force coef, spring coef, **an unknown float at +0x3c (1.0 in 1426 of 1441 chains)**, limit force (100), friction (0), reflect (0.1), 4 x 0xCD.
  No wind rate / wind limit.
* **Node**: bone function id (u16, the low byte is the id, bits 8-9 are set in 45 nodes of pl0620 only), isParent (1 exactly on the first node of a chain), a zero byte,
  angle mode (0 free, 1 cone, 2 hinge; no oval), a zero byte, collision shape (0 / 1), unknown enum, bone collision radius (cm), 4 x 0xCD, 4x4 matrix (row vectors), angle limit
  radius (rad), mass, elastic coef, 4 x 0xCD. No width rate. The first ROW of the 3x3 is the direction to the next node in the bone's local frame (5 of 5 checked); the translation
  row is junk in 899 nodes (kept as is, MHWME writes zero).
* Unknown: the chain float at +0x3c, the two zero bytes in the node, the high id bits, what the attribute flag bits do in RE6 (names come from MHW), mass / elastic assignment is by
  value distribution (not verified in game).

## CCL (version 0x80618, identical to MHW)

`size == 16 + 64 * count`; header `'CCL\0'`, version, count, total size of the records (`64 * count`); record: u32 0, start bone u16, end bone u16 (0xFFFF for most spheres), shape
u8 (0 sphere, 1 capsule), 7 x 0xCD, start position xyz (bone local, cm), u32 0, end position xyz, radius, 12 zero bytes, 4 x 0xCD.

## Bones

Node and collision bones are **function ids** (the id byte of the bone table of the `.mod`, our bones `RE6Bone_NNN`). All 131 `.ccl` and 259 of 262 `.ctc` that have a same-name
`.mod` resolve completely (the misses are head models whose chains run on the body skeleton, and pl0120). Within a chain every node's bone is the child of the previous node's bone
(382 of 382 checks). Ids >= 256 only occur in pl0620.

## Related classes

`rCnsOffsetSet` (14ea8095, 37 files) is a different format (`XFS\0`, a reflected struct dump) and is not read. `rCollision` (.sbc) is stage collision (albam's sbc-211.ksy).
The classes `rChain`, `rCnsIK`, `rCnsTinyIK`, `rCnsNBIK`, `rCnsJointOffset`, `rModelChainSetting` do not occur in the RE6 archives.

## Blender layer (`blender/ctc_*.py`, `ccl_*.py`, `objects.py`)

Built like the MHW Model Editor's layer, from real objects (no gpu drawing): header = empty, chain = NURBS curve with one hook modifier per bone, node = sphere empty with
`BoneName` / `BoneRotation` / `BoneScale` constraints, frame = arrows empty (its rotation is the node matrix), angle limit cone = curve object with a Geometry Nodes group,
collision = curve object with a Geometry Nodes group (sphere; capsule between a head and a tail handle). Names: `re6_ctc.*` / `re6_ccl.*` operators, `scene.re6_ctc_toolpanel`
/ `re6_ccl_toolpanel` / `re6_ctc_clipboard`, `object.re6_ctc_header` / `re6_ctc_chain` / `re6_ctc_node` / `re6_ccl_collision`, `~TYPE` values `RE6_CTC_*` / `RE6_CCL_*`,
sidebar tab `RE6 Chain`, chain presets in the Blender config folder (`re6_model_editor/ChainPresets`).

Differences from MHWME (all deliberate):

* no wind min / max / weights, wind rate / limit, width rate, oval angle mode, no `Create Full Body Collisions`; the chain has the extra `unkn Float`;
* bones are found by function id, and the id is **the number in the bone name** (`RE6Bone_NNN`, or `RE6Bone_NNN.001` for a second bone with the same id) and nothing else, like `MhBone_NNN` in MHWME; ids go up to 254; `Rename Chain Bones` uses the same routine as `Match Bone Names` (bones, vertex groups, mirror names, chain / node / collision object names);
* the node matrix is **transposed on import** (MHWME does not, and its export is the transpose of its import; the retail data stores the direction to the next node in the first
  row). Checked: after import the x axis of every frame points at the next node (dot product 1.0);
* what the object model cannot show is kept in custom properties so that an untouched import -> export is byte identical: `Ctc_Node_Translation` (the junk translation row of 908
  nodes), `Ctc_Node_BoneIdHigh` (the high id byte of pl0620), `Ctc_Node_Matrix` on the frame (the exact 9 floats; used while the frame was not rotated), `Ctc_Empty_Chains` on the
  header (the chains without nodes of the file, with their position), `Ccl_Data` (the exact centimetre values) and `Ccl_EndBone` (the end bone of a sphere);
* the unknown attribute flags 2 are written (MHWME never writes them); the export walks chain -> node instead of relying on the object order; export errors use the same window as
  mod / mrl (`re6_ctc.show_export_error_window` / `re6_ccl.show_export_error_window`);
* the mod import dialog has `loadPhysics` (and the preference `default_loadPhysics`): the `.ctc` / `.ccl` next to the `.mod` are imported with it; `Create Nested Collections` also
  creates the `.ctc` collection with its header.

Tests: `tools/roundtrip_ctc_ccl.py` (core), `tools/blender_ctc_roundtrip.py` (headless Blender, 40 models with their ctc / ccl: 56 of 58 files come back byte identical; the two
exceptions are the head models pl0003 / pl0093, whose chains run on bones that only the body skeleton has, so those nodes are dropped like MHWME drops them).

Presets also read the chain presets of the MHW Model Editor (`presetType` `CTC_CHAIN`, same units): they are listed as
`name (MHW)` from its `modules/ctc/ChainPresets` folder when that add-on is installed, and a copy in our folder works too;
`WindRate`, `WindLimit` and the flag booleans are ignored, `unknFloat` keeps the chain's value.
Rename Chain Bones (dialog): two drop downs, **Character** (Generic / Ada (Original Outfit)) and **Part** (Body plXXz0 / Head plXXz3). The ids come
from the range for that choice (`core/chain_id_data.py`, generated by `tools/pl_free_ids.py`, see docs/BONE_IDS.md): ids that no motion list
(also cutscene / event / QTE ones), jex, link bone or kept bone of the model uses; Generic = the ids that are free in every model of the part,
Ada = pl0600 / pl0603. Bones are numbered along the sorted list of the range's free ids (ids the armature's other bones use are skipped, gaps are
skipped too, so a chain may be 98, 99, 218, 219). A start ID outside the range, or fewer free ids left than the chain has bones, is refused with an
error window and nothing is renamed. The choice is remembered (`re6_ctc_toolpanel.chainIdCharacter` / `chainIdPart`); `nextChainBoneID`
(editable in Rename Bone Settings) is where the next suggestion starts and moves past every renamed chain. Logic without Blender:
`core/chain_ids.py`. Test: `tools/blender_ctc_preset_rename_test.py` (set `RE6_TEST_MODEL_DIR` to a folder with a retail pl0600.mod / .ctc).
