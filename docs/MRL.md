# RE6 material library (.mrl) and textures (.tex)

Verified on all 5813 non empty `.mrl` of the game (44327 materials); parser: `re6_model_editor/core/mrl.py`.

## .mrl (version 0x21)

| offset | |
|---|---|
| 0x00 | `MRL\0`, u32 version 0x21, u32 material count, u32 texture count, u32 unknown, u32 texture table offset (0x1c), u32 material table offset |
| texture table | 0x4c bytes per entry: u32 class hash (rTexture), 2 x u32 0, char[64] path (backslashes, no extension, 0xCD padded) |
| material table | 0x3c bytes per entry (below) |

Material entry: `+00` shader type hash (0x5fb0ebe4 = nDraw::MaterialStd for 99%, 0x854d484 = MaterialNull, 0x7d2b31b3 =
MaterialStdEst), `+04` **name hash = the material hash of the .mod**, `+08` size of the command block, `+0c/+10/+14` blend /
depth / raster state hashes, `+18` and `+1c` two bit-field words (below), `+20` four blend factor floats (always 0),
`+30` animation block size, `+34` command block offset, `+38` animation block offset (0 = none). The block at `+34` is
`count * 12` bytes of commands followed by the constant buffers.

Flag words (layout from albam's mrl.ksy, checked on 44327 retail materials: decode + encode is bit exact;
`core/mrl.py` FIELDS): `+18` bits 0-11 command count, 12-20 unknown (9 bits, copied), 21-28 material id, 29 fog, 30 tangent,
31 half lambert (1 in 99.6%); `+1c` bits 0-7 stencil ref, 8-15 alpha test ref, 16-19 polygon offset, 20 alpha test
(on in 26%), 21-23 alpha test function (always 4), 24-28 draw pass (11 opaque in 74%, 16 / 12 / 14 / 20 others), 29-30
layer (always 0), 31 deferred lighting (on in all but 11). The add-on shows them in the material's *Flags* box.

Command (12 bytes: header, a, b), type = header & 15:

| type | a | b |
|---|---|---|
| 0, 2 | state hash | same hash (shader switches, sampler states) |
| 1 | offset of a constant buffer inside the command block | buffer name hash |
| 3 | **texture number** (1 based into the texture table, 0 = none; read 1 based, 90 % of the retail tNormalMap slots name an `_NM` texture, read 0 based 2 %) | sampler slot hash |

Model to material library: `<name>.mrl` next to the `.mod`; for players etc. `<name>.mrl` is an empty stub and the
real libraries are `<name>_0.mrl`, `_1`, `_2` (the texture variants). Every material hash of a retail `.mod` exists
in its library (10245 of 10371 models; the others only have the stub).

### Which texture is what

The slot hash does not define the role by itself (slot `cd06f347` is the mask of a character but the albedo of most
stage / enemy materials), the file name suffix does: `_BM` base (albedo), `_NM` normal, `_MM` mask (`_DM` detail,
`_LM` light map, `_VTF` / `_MVTF` blood and wetness ramps, `_NUKI` cut-out). The add-on picks by suffix and orders
candidates by slot (`SLOT_PRIORITY` in `mrl.py`): albedo 2266034a, cd06f347, aa6f0351; normal 75a5334b, ff5be348,
0ed1b35a, 039c0367.

State hashes (guessed from their frequency and the models that use them, not verified in game):
blend `62b2d163` opaque (86%), `23baf165` alpha blend (13%), `d3b1d16b` additive; depth `7d2f6198` = no depth write;
raster `108cf19f` back face culling, `923331ad` two sided.

## .tex

Header, mip offset table and payload layout are handled exactly like RE6 ARC Studio (`core/tex.py`): the payload is a
plain DDS payload, so TEX <-> DDS is a header swap. Format byte: 20 = DXT1 (BM), 25 = DXT1 (MM), 31 = DXT5 (NM).
Normal maps are **DXT5nm**: R = 1, B = 1, **x in alpha, y in green**; z is rebuilt (node group `RE6 DXT5nm Normal`,
input `Flip Green` = 1 converts DirectX to OpenGL, unverified which one the game uses).

## Blender side

* `blender/materials.py` builds per material: Image Texture (BM, sRGB) -> Principled Base Color (+ alpha for blended
  materials), NM -> `RE6 DXT5nm Normal` group -> Normal Map -> Normal, MM as an unconnected image node.
* Textures are found in this order: the folder chosen in the import dialog, the add-on preference *Extra Texture Folder*,
  the model's folder (full `data/...` path, then flat file name), the `.arc` archives under every folder above the model
  that contains `nativePC` (a mod folder before the real game) and the preference *Game Folder*.
  The archive index is cached in `%APPDATA%/Blender Foundation/Blender/<ver>/config/re6_model_editor`.
* Images carry `re6_tex` (virtual path); materials carry `re6_textures` (JSON list of slot, path), `re6_shader`,
  `re6_states`, `re6_mrl`. Materials are created per import, so several models with the same hashes do not share textures.
* `RE6 Mrl Tools > Material List > Load MRL` applies another `.mrl` (for example a costume variant) to the materials of the active model.
* Textures that cannot be found leave an empty image node named after the missing file. `Assign Texture` (material panel
  > Textures of the material, buttons Base / Normal / Mask) loads a `.tex` or any image into those nodes by hand. Needed for
  mods whose `.mrl` does not reference their own textures (for example pl0610: the `.mrl` points to `BYtongtong\...` while the
  shipped textures are `pl0610_20_bodytols`, `_21_leg`, `_22_oldbody`).
* An operator dialog cannot open a second file browser ("cannot activate file selector, one is already open"), so the
  texture folder in the import dialog is a plain text field; the add-on preferences have a browse button.
* A texture path that exists nowhere (the `BYtongtong\...` paths of the pl0610 mod; the mod is said to rely on a "path
  redirect" patch of the game) is resolved by **file name**: first in the extracted folders next to the model (the folder
  above its `data/`, and every sub folder of a mod / game folder that has a `data/`, e.g. `uPlTex0600_2/data/...`), then in
  the archives. The same name can exist in several variant archives (`uPlTex0600_0/_1/_2`); the first one found wins,
  folders before archives, alphabetical order. Use `Assign Texture` to pick another variant.

## The .mrl as Blender objects (v0.3.x)

Importing a model with *Load Material Data* (off by default, like the MHW Model Editor's *Load Material Data*) creates the
collection `<name>.mrl` next to the model collection `<name>.mod` (both inside the parent collection `<name>` when *Add Nested
Collections* is on; they are linked by the name). It holds **one empty per material** (`MAT_<hash>`), the source of
truth of the library. Each empty (`object.re6_mrl_material`) holds hash, index (file order), shader, blend / depth / raster mode (drop downs that show the engine's state names `BSSolid`, `DSZTestWrite`, `RSMesh` ...; unknown hashes = Custom, kept as is), the texture
slots (slot hash + path), the constant buffers (named values grouped by buffer in the *Property List*; sizes are constant per hash, e.g. 32 and 84
floats for the two buffers every character material has) and, hidden in `object['re6_mat_data']`, the command block and
animation block. The Blender materials on the meshes are only previews (`re6_mrl_material.linkedMaterial`).

* `RE6 Mesh` sidebar tab > **RE6 Mrl Tools**: Import Mrl, Export Mrl, *Active Mrl Collection*, Create Mrl Collection, Reindex Mrl Materials; sub panel **Material List**: Load MRL, add / duplicate / delete / move and *Add Missing Materials*; Import MRL (standalone, no model needed), Load MRL (replace the library of the active model,
  e.g. a costume variant; the meshes keep their previews), Export MRL, add / duplicate / delete / move / reindex, *Add Missing
  Materials* (an entry from the built-in template for every hash the meshes use that the library lacks).
* Properties > Data (on a material empty, panel *Mrl Material Properties*) or Material (on a mesh): slots, blend, buffers, *Refresh Preview*.
* Export: exactly the entries of the collection, in index order (nothing is added; use *Add Missing Materials* below Load MRL
  first when the meshes use hashes the library lacks); the texture table is rebuilt from the paths in use. Untouched constant buffer values keep their exact bits.
* `Assign Texture` writes the path into the slot of the entry and updates the preview.

## Hashes (compared with the MHW Model Editor's dictionaries, tools/hash_compare.py, tools/hash_names.py)

* **Material names**: the u32 of the .mod material table / .mrl entry is `jamcrc32(name)` = `~crc32(name)`, the same function
  as the keys of MHW's `various_hash_dict.json` (all 266665 entries satisfy it). RE6 hashes that resolve through that table:
  `pl_skin` = 68b3d093, `pl_snow` = 5c491d3e, `Null` = 7a06ac8e, `Shadow` = 8d2578e4, `Material` = 7a37e83c. The rest are
  names nobody has listed for RE6 (8331 distinct hashes in the game). The add-on computes the hash from a name when adding a
  material (`core/hashes.py`).
* **Shader parameters** (`b` of the commands, the state hashes, vertex formats): `h = (jamcrc32(name) & 0xFFFFF) << 12 | code`
  (the command header repeats the low 12 bits). **albam** (Brachi/albam, `albam/engines/mtfw/structs/mrl.ksy`) carries a
  table of 3297 such names; the RE6 materials use 99 of them and every hash in the 44327 retail materials resolves
  (blend 4/4, depth 4/4, raster 5/5, flags 45/45, constant buffers 11/11, sampler states 4/4, textures 26/26). The table is
  lowercase; the letter case was recovered by trying capitals until the hash matches (tools/hash_case.py, unique hits,
  e.g. `tAlbedoMap`, `SSAlbedoMap`, `CBMaterial`, `$Globals`, `FUVTransformPrimary`, `BSSolid`, `DSZTestWrite`, `RSMeshCN`).
  They are in `core/shader_names.py` (generated by tools/make_shader_names.py; data in tools/data/albam_*.json).
  - blend: `BSSolid` 62b2d163 (86%), `BSBlendAlpha` 23baf165, `BSAddAlpha` d3b1d16b, `BSComposite` d4823166
  - depth: `DSZTestWrite` b8139196, `DSZTest` 7d2f6198, `DSZWrite` a967c199, `DSZTestStencilWrite` 3051119c
  - raster: `RSMesh` 108cf19f (one sided), `RSMeshCN` 923331ad (two sided), `RSMeshCF` 2ab011ac, `RSMeshBias3/5`
  - commands type 0 (45 shader flags, in every material): `FVertexDisplacement`, `FUVTransformPrimary` ... `FAlbedo`,
    `FTransparency`, `FBump`, `FLighting`, `FBRDF`, `FShininess` ...; type 2: `SSAlbedoMap`, `SSSpecularMap`, `SSNormalMap`,
    `SSEnvMap`; type 3: `tAlbedoMap` (98%), `tSpecularMap`, `tNormalMap`, `tLightMap`, `tEnvMap`, `tDetailNormalMap`,
    `tAlbedoBlendMap`, `tTransparencyMap` ...
  - vertex formats (40 of the hashes in `core/vertex.py`): `IASkinBridge4wt` (cb68), `IASkinTB2wt` (c31f2), `IASkinTBN4wt`,
    `IANonSkinTBN` ... The add-on's own names for them are descriptive, not the official ones.
* **Constant buffers**: `CBMaterial` (32 floats), `$Globals` (84 floats, the real shader parameters), `CBColorMask` (24),
  `CBVertexDisplacement` (8), `CBVertexDisplacement2` (4) have a known float layout (albam; `core/cb_layouts.py`, generated
  from the ksy). Checked on retail values: albedo colour 1,1,1, specular 0.2, shininess 80, secondary_shift 0.6 on hair,
  parallax samples 4 / 64, colour mask colour of pl0000_0 = 0.45,0.05,0.09. The add-on shows those fields by name. Other
  buffers (`CBBAlphaClip`, `CBVertexDisplacement3`, `CBDistortionRefract` ...) are shown as plain float rows.
* **The slot names still do not tell the role of the texture**: on character materials the `_BM` colour texture sits in
  `tNormalMap`, `_NM` in `tDetailNormalMap` / `tAlbedoBlendMap` and `_MM` in `tAlbedoMap` (retail pl0000_0.mrl), while stage /
  enemy materials use `tAlbedoMap` for the colour. So the texture role keeps coming from the file name suffix.
* **Names found with the help of the MHW Model Editor's vocabulary**: shader type 0x56d89634 = `nDraw::MaterialHud` (376 materials, all HUD screens); the .tex class hashes
  0x241F5DEB = `rTexture`, 0x7808EA10 = `rRenderTargetTexture`; about 40 option values of the shader switches (`tools/data/option_names.txt`: `FUVPrimary` ... `FUVIndirect`,
  `FChannelR` ... `FChannelA`, `FOcclusionMap`, `FAlbedoMap`, `FBumpNormalMap`, `FSpecularMap`, `FFresnelSchlick`, `FReflectCubeMap`, `SSAlbedoMapClamp` ...; the option
  hash is `(name hash 20 bit << 12) | code`, the code counts up from the switch code). Weaker guesses that are not used: `FSpecularDisable` (the commonest `FSpecular` option),
  `FTransparencyDodgeMap`, `FAlbedoMapBlendAlpha`, `FUVTransformOffset`.
* **Still no name**: the `SSEnvMap` alternatives, the vertex displacement option sets, mrl header word +0x10, `hgm` / `sce` ARC classes.
* MHW's `surfaceCoef` high nibble (1 = one sided, 14 = two sided) is the analogue of the RE6 raster state and `alphaCoef[0]` (default 128) of the alpha test reference; MHW has no
  blend / depth / raster hashes and no flag words, its pipeline state comes from the mmtr plus those two fields. None of the MHW property names or cbuffers exist in RE6.

Caveat on the material name list (`core/hashes.py`): the names found by guessing (tools/hash_guess.py: 13 million candidate
names against 8331 hashes) contain about 25 chance hits, because a 32 bit hash is easy to hit. Only the names with many uses
were kept (the pl_skin / pl_base / pl_cloth / pl_hair / pl_nuki families, wp_Totan weapons) plus the five found in the MHW
dictionary (Null, Shadow, Material, pl_skin, pl_snow; 0.5 chance hits expected). A second guess over the model and texture
stems of every file resolved only more stage props whose names equal texture stems, too few uses each to tell them from
chance, so it was not added. New materials can simply be named: a material that is not called MAT_xxxxxxxx gets
`jamcrc32(name)` as its hash on export (warning in the report).

## Shader features (switches) — 2026-10-01

Every `nDraw::MaterialStd` material picks one option for each shader switch (type 0 commands, `b` = switch, `a` = option,
`a == b` = default). `a` = `(jamcrc32(option name) & 0xFFFFF) << 12 | code`; the 12 bit codes are one global enumeration in
declaration order, so options of one family have consecutive codes (FUVPrimary 564, FUVSecondary 565 ...; FBumpNormalMap
544, FBumpDetailNormalMap 545; the RE6 additions are a36..a4a). This is how the names in `tools/data/option_names.txt` are
checked. Command header = `(code of the switch's default << 20) | 0xDCDC0 | type`, constant per command.

The shaders are precompiled: only the options that exist can be chosen, and each option needs its own commands (texture
slots, sampler states, UV / channel switches, constant buffers). `core/mrl_features.py` + the generated
`core/mrl_feature_data.py` (`tools/make_feature_table.py`, learned from all 43793 retail MaterialStd materials):

* presence rule: a material has a command iff it is in ALWAYS (18 commands) or one of its OWNERS (options that imply it) is
  selected, evaluated as a least fixed point — reproduces the command set of **43793 / 43793** retail materials;
* `set_option(mat, switch, option)` changes the option and adds / removes commands; new ones are inserted where they
  contradict the fewest retail orders (pairwise counts), get the retail header, the most common option / sampler state /
  constant buffer data, and empty texture slots; the block is rebuilt (commands, zero pad to 16, buffers in command order;
  `relayout` rebuilds all retail blocks byte for byte);
* 1127 switch combinations exist in the game (`COMBOS`); others are flagged as unverified in game.

`tools/test_mrl_features.py`: switch off and on again restores the same command order in 97.5 % of 185k cases (all keep
their values); A -> option of B for retail pairs differing in one switch gives B's command set always and B's order whenever
A and B order their common commands the same way (the other 253 pairs already disagree in retail).

Blender: material panel sub panel **Shader Features** (`blender/mrl_features.py`): one row per switch with more than one
retail option (main features, then UV / channel / displacement), a search popup lists the options with their retail
count and the commands they would add (+) / remove (-); operator `re6_mrl.set_feature`. Untested in game.

### Names from the game's shader package (2026-10-01)

`nativePC/system/shader/ShaderPackage.mfx` (and `app_shader/AppShaderPackage.mfx`, magic `MFX\0`, version 0x35) contain the
shader object names as plain strings (~5000). Matching their jamcrc32 & 0xFFFFF names **every** switch, option, slot,
buffer and sampler state used by the retail materials (`tools/data/option_names.txt`). It also corrected three earlier
brute-force guesses: 5808b = FUVViewNormal (not FUVMaskCube), d3336 = FVertexDisplacementCurveU, 1cf68 = FColorMaskAlbedoMap.
Sampler alternatives: SSAlbedoMapClamp, SSNormalMapClamp, SSEnvMapLODBias1..5. The .mfx probably also holds which
resources each option uses (not parsed; the owner tables are learned from the materials instead).

### The shader package as the rule book (2026-10-01)

`core/mfx.py` parses `AppShaderPackage.mfx` (the material codes are **its** object index + 1; `ShaderPackage.mfx` only
shares the first 779 objects). Per object: name, type name, kind (0 cbuffer, 1 texture, 2 fragment, 3 sampler, 4/5/6
blend/depth/raster, 7 technique, 8 struct, 9 input layout). Fragments: `+0x30/+0x34` dependency list (u16 index + 1),
`+0x44` interface group (a switch and its options; options = members nobody depends on). Constant buffers: `+0x18` u16
size in floats, `+0x24` default data (sizes match all 11 retail buffers, defaults match 8 exactly).

Checked on all 43793 retail MaterialStd materials: every command and option is a package object, every retail option is in
its switch's package option list, and the dependency closure from the 18 root commands reproduces **every** command set.
`tools/make_feature_table.py` now also writes `MFX_OPTIONS` (48 switches, 154 options, incl. ones no retail material uses:
FBumpParallax(+Occlusion), FVertexDisplacementWave, FFresnelSchlickMap, FUVScreen ...), `MFX_DEPS`, `MFX_CB` (3 buffers
no retail material has), `MFX_SAMPLERS` (SSSpecularMapClamp is new), `MFX_NAMES` (merged into shader_names.py). Command
header = `(b & 0xfff) << 20 | 0xdcdc0 | type` for all 86 retail commands. `set_option` uses the package rule; commands
never seen in retail go right after the switch that needs them. tools/test_mrl_features.py: 113918 option switches
(20848 with unused options) all give the official command set. The Sampler List is a drop down of the package states.
Options no retail material uses are allowed but flagged (unverified in game).
