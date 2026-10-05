# RE6 `.mod` (v211) vs MHW `.mod3` (v237)

Verified on `pl0610.mod` and 2226 retail character/weapon mods (all v211; parse -> serialize is byte-identical,
see `tools/roundtrip_all.py`) and on `two029.mod3`.

| Part | MHW mod3 | RE6 mod | Same? |
|---|---|---|---|
| header | 0x140 B, u64 offsets, 8 B date, float segments | 0x80 B, u32 offsets, sphere + AABB | layout differs, same idea |
| bones | 24 B: i16 function, u8 parent, u8 child/mirror, f, len, xyz | 24 B: u8 id, u8 parent, u8 mirror, u8 unk, f, len, xyz | same size, field packing differs |
| LMatrix / AMatrix / boneMap(256) | yes | yes | **identical meaning** |
| group properties | 32 B | 32 B | identical |
| materials | 128 B name strings | 4 B name hash (looked up in .mrl) | differs |
| mesh header | 0x50 | 0x30 | RE6 = MHW without lod u32 and the 32 trailing bytes; the shared fields keep their order |
| vertex buckets | vertexSub / vertexOffset / blockSize, indices relative to bucket | same | **identical scheme** |
| bounding volumes | per mesh, per bone | per mesh, per bone, 0x90 B (bone-local) | same idea |
| faces | u16 triangle lists | u16 triangle lists | identical, same winding/normal convention |
| positions | float32 x3 | **int16 x3**, `s16/32767 * A[0][0]`; the scale lives in the AMatrix diagonal, the translation in A.t | differs |
| normal / tangent | s8 x4 | u8 x4 biased (`b/255*2-1`); tangent.w = 0xFE / 0x00 (bitangent sign) | differs |
| UV | half x2 | half x2 | identical |
| weights | 10-bit x3 (+8-bit x4) + complement, ids u8[4\|8] | `W0` = int16/32767 in `pos.w`, `W1,W2` = half float, `W3 = 1-W0-W1-W2`; ids u8[4] are **direct bone indices** (no remap); filler id = first id | same idea (3 explicit + complement), lower precision |
| vertex formats | 14 hashes | 27 hashes (stride 12..64) | differs |
| textures / materials | .mrl3, BC7/BC5, RMT | .mrl + .tex (DXT1/DXT5/BGRA) | no 1:1 |

Rigid RE6 vertex (hash `0xA8FAB018`, 20 B): `s16 x,y,z | u8 bone | u8 0 | u8 nx ny nz nw | u8 tx ty tz tw | half u v`.

Unknown / copied fields (mesh header): `lodMask`, `unk3`, `unknownIndex` (draw order), `tail` (`unknownIndex`-monotone key, low byte 0xC0).

## Vertex formats (40 hashes, all decoded; `re6vertex.py`, lossless decode -> encode on every mesh of the game)

Skinned / rigid meshes (models with a skeleton): `pos = s16/32767 * A[0][0]`.
Static meshes (no skeleton: stages, effects, events): `pos = float32 x3`, no skinning.
`weightDynamics` low byte = `1 + 8 * influences` (static 1, rigid 9, 2 bones 17, 3 bones 25, 4 bones 33, 5..8 bones 41..65), the high byte is albam's `alpha_priority` (sort priority of alpha meshes); the low byte is `disp` (bit 0), `shape` (bit 1), `sort` (bit 2) and `weight_num` (bits 3-7).

| family | layout |
|---|---|
| rigid | `pos8(pw=bone u8 + 0) n4 [t4] uv.. [col4]`   (IASkinBridge1wt, IASkinTB1wt, TBC1wt, TBN1wt, TBNLA1wt) |
| 2 bones | `pos8(W0) n4 t4 uv4 id_half x2 [col]` or `.. id_half x2 uv..`; shadow copy `pos8(W0) n4 id_u16(0x8000\|id) x2`; W1 = 1-W0 |
| 3-4 bones | `pos8(W0) n4 t4 ids_u8x4 uv4 W1_half W2_half [uv2 / col]`, W3 = 1-W0-W1-W2; shadow copy `pos6 pad2 ids4 w_u8x4 n4` |
| 5-8 bones | `pos8(W0) n4 w_u8x4(@12) ids_u8x8(@16) uv4(@24) w_u8x3+1(@28) t4(@32) [uv2 / col]`; weights = `[W0, b12..b15, b28..b30]`; shadow copy `pos6 pad2 ids8 w_u8x8 n4` |
| static | `pos_f32x3 n4 [t4] uv.. [col]` (19 layouts) |

Normals/tangents are `u8` biased; normal.w is free data, tangent.w = bitangent sign (0 = -1, else +1).

## Mesh header (0x30) and file level fields

| field | meaning |
|---|---|
| `lodMask` (+0) | render pass bit mask: 0xFFFF = draws and casts shadows itself; 0x1020 = shadow-only copy (the 12/16/20/24B "Shadow" formats, `unk3 = 195`); 0xFDF7 / 0xFEFB ... = visible mesh that has a separate shadow copy |
| `flags` (+4) | `material << 12 \| group id` (group = entry of the group table, used by the game to toggle parts) |
| `lod` (+7) | LOD bit mask (1 = LOD1, 2 = LOD2, 252 = LOD3+, 255 = all), same idea as MHW |
| `weightDynamics` | see above |
| `unk3` (+0xB) | albam's `topology` (bits 0-5, 3 = triangle list), `binormal_flip` (bit 6, 0x40) and `bridge` (bit 7, 0x80: the shadow-only "bridge" vertex formats) |
| `unknownIndex` | draw order, a permutation of 1..N |
| `tail` | sort key, monotone with `unknownIndex` (steps of 0x8000); cannot be derived -> generate increasing values |
| bounding volumes | per (mesh, bone): sphere + AABB + OBB in bone local space, first u32 = bone index |
| header `edges` (+0x14) | number of triangles (= indexCount / 3) in retail files |
| header 0x40 / 0x50 / 0x60 | bounding sphere (cx cy cz r) / AABB min / AABB max |
| header 0x70 | LOD distances (u32 x2, e.g. 1000 3000), u32 count |
| group entry (0x20) | `i32 id, 3 x 0xCDCDCDCD, float[4] = bounding sphere` (same as MHW GroupProperty) |
| group sphere frame | the centre is relative to the bind position of the bone that carries most of the group's weight (head bone 3/4 for a head, wrist 8/13 for a hand pose), NOT the root bone 0: with that reference retail spheres cover the group in 98% of 1242 body/hand groups and 100% of the main head groups, with bone 0 only 10% / 24%. A sphere that misses its meshes makes the whole group disappear (frustum culling), whatever its visibleCondition (`core/model.py group_sphere`, `tools/group_sphere_test.py`) |
| bone `f` | bone influence radius: max distance of vertices weighted to the bone |

## Corrections / additions found while building the editor

* **Material index** = `(mesh.unk6 << 4) | (mesh.flags >> 12)` (`unk6` is the high byte; models with more than 16 materials need it).
* **vertexBase** must be added to the vertex start: `start = vertexOffset + (vertexSub + vertexBase) * blockSize`.
* **Tangents**: in well formed meshes `tangent = normalised sum of the per triangle dP/du` (uv as stored, V pointing down), made orthogonal to
  the normal, `bitangent sign = -sign(det(uv Jacobian))`. About 40% of the retail normal-mapped meshes follow another rule, so the editor keeps
  the tangents of an imported mesh and only generates them for new geometry.
* **Quantisation** (skeleton models): `origin = -bbox.min`, positions are `(world + origin) / scale * 32767`, `scale` is written to the diagonal of every AMatrix
  and is free; `A_b = Scale(s) * Translate(-origin) * inverse(W_b)` holds for ~99.7% of the models (W = L matrix chain).
* **Bone record**: `f` = influence radius (farthest vertex weighted to the bone), `length` = |local translation|, `mirror` = index of the symmetric bone.
* **Skeleton-less models** still carry one bounding volume per mesh; its bone field is **255** (retail static mods and MHWME agree; earlier versions of this note said bone 0).
* **Bone record** (checked against MHWME's reader, 5942 retail bones): the byte at +3 (`unk`) is padding (always 0); `f` is 0 exactly when no vertex is weighted to the bone;
  `remap[id] == bone index` holds for every bone, so `id` is the animation function; `mirror` = own index on the x = 0 plane, else the bone at the mirrored x, else 255 (rule of
  `mod3_functions.py`, reproduced for 97% of the bones of 80 models within 5e-4 cm; the exporter uses it only for bones that have no `Mod_Bone_Symmetry` and no id).
* **Mesh header vs MHW** (MHWME / Asterisk names): `vertexSubMirror` / `vertexIndexSub` (+0x28 / +0x2A) = min / max vertex index of the mesh (equal in 10560/10560 retail meshes);
  `boundingBoxCount` (+0x25) = number of distinct bones with weight > 0 on the mesh; `unknownIndex` (+0x26) = MHW `meshIndex`; the group id (+4) is Asterisk's `visibleCondition`
  (weapons: 1 = visible only when drawn, 2 = only when sheathed, 0 = always); `tail` (+0x2C) is the counterpart of MHW `mapData` (0xFFFFFFFF there, never in RE6, so it is still generated).
* **LOD masks** are MHW's scheme truncated to 8 bits: bit n = LOD n, the last LOD owns all higher bits, 255 = all, 0 = never drawn (1 = LOD0, 2 = LOD1, 252 = LOD2 and beyond).
  The header words at +0x70 / +0x74 look like LOD transition distances.
* **Vertex buckets**: the vertexBase / vertexSub bucket rule is the one of MHWME's reader and is keyed by the stride only (not by the format hash).
* `core/validate.py` lists the invariants every retail file satisfies (5345 of 5428 models are completely clean; the rest are cut-scene oddities).

## Names from albam (Brachi/albam, `albam/engines/mtfw/structs/mod-21.ksy`)

Mesh header (0x30): `+00 draw_mode` (our lodMask / render mask), `+02 num_vertices`, `+04` group (12 bits) | material (12 bits,
our flags >> 12 plus unk6 << 4) | `+07 level_of_detail`, `+08` disp / shape / sort / weight_num + `alpha_priority`, `+0a vertex_stride`,
`+0b` topology / binormal_flip / bridge, `+0c vertex_position`, `+10 vertex_offset`, `+14 vertex_format`, `+18 face_position`,
`+1c num_indices`, `+20` vertex block base, `+24 bone_id_start` (u8), `+25 num_weight_bounds` (u8), `+26 connect_id` (our
unknownIndex), `+28 min_index`, `+2a max_index`, `+2c boundary`. The vertex format hashes are `IASkin...` / `IANonSkin...`
(see MRL.md, core/shader_names.py); `core/vertex.official_name` gives them, the descriptive names of `core/vertex.py` are
internal (for example `Rigid1UV` a8fab018 is the official `IASkinTB1wt`). The low 12 bits of a format hash are the entry of the
game's fixed input layout table (0x013 .. 0x03e, 40 used by the retail data; by the order of the name table the unused
0x017 / 0x02b / 0x030 / 0x039 are probably IASkinBridge4wt4m, IANonSkinTBL_LA, IANonSkinTBNL_LA, IANonSkinBL_LA, layouts
unknown), so new layouts can not be made up.
