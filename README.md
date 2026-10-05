# RE6 Model Editor

Blender add-on (and a dependency-free Python core) to import, edit and export **Resident Evil 6** `.mod` model files
(MT Framework, MOD version 211). The design follows the MHW Model Editor: a model is a collection, LODs are
sub collections, bones are named `RE6Bone_<id>`, everything the game needs but Blender cannot show is kept in custom
properties.

## Install

```
python tools/install_addon.py --zip        # dist/re6_model_editor.zip  -> Blender: Preferences > Add-ons > Install from Disk
python tools/install_addon.py --install    # or copy straight into the newest %APPDATA% Blender version
```

File > Import / Export > **RE6 Model Editor** > **RE6 MOD (.mod) (Model)** and **RE6 MRL (.mrl) (Material)**, **RE6 CTC (.ctc) (Physic)** and **RE6 CCL (.ccl) (Collision)** (or drop a `.mod`, `.mrl`, `.ctc`, `.ccl`, `.tex` or `.dds` into the 3D viewport; several files can be dropped at once: a `.mod` shows its import options unless the add-on preference *Show Drag and Drop Import Options* is off, a `.mrl` is imported, `.tex` / `.dds` files are converted into each other at once). Side panel: **RE6 Mesh** tab
(*RE6 Mrl Tools*, *Presets*, *RE6 Mesh Tools*, *RE6 Tex Tools*), laid out like the MHW Model Editor's *MHW Mesh* tab, and the **RE6 Chain** tab
(*RE6 CTC & CCL Tools*, *Clipboard*, *Presets*, *Visibility*) for the chain physics (`.ctc`) and chain collisions (`.ccl`), see `docs/CTC_CCL.md`.
The add-on follows the MHW Model Editor's structure (see `docs/MHWME_ALIGNMENT.md`): collections `<name>.mod` and `<name>.mrl`
inside a parent collection `<name>`, marked by the custom property `~TYPE` (`RE6_MOD_COLLECTION`, `RE6_MRL_COLLECTION`,
`RE6_MRL_MATERIAL`); the per mesh settings are custom properties of the mesh data (`Mod_Mesh_*`), the model settings
custom properties of the `.mod` collection (`Mod_Header_*`, `Mod_Group_NNN`), the bone settings `Mod_Bone_*`; operators are
`re6_mod.*`, `re6_mrl.*`, `re6_tex.*`. Objects with the custom property `ModExportExclude` are not exported.

## Workflow

1. Extract the `.mod` (for example with RE6 ARC Studio) and import it. Import options: all LODs, shadow meshes.
2. Edit meshes / weights / UVs / vertex colours, add meshes (one material slot named `MAT_xxxxxxxx`, the material hash).
   New meshes need vertex groups named after the bones they are bound to (`RE6Bone_xxx`) when the model has a skeleton.
3. Export the model collection. The exporter chooses the smallest matching vertex format, rebuilds vertex buckets,
   bounding volumes, group table and quantisation, and keeps everything it did not touch.

## Layout

| path | |
|---|---|
| `re6_model_editor/core/mod211.py` | file structure reader / writer (byte exact) |
| `re6_model_editor/core/vertex.py` | all 40 vertex formats of the game (decode / encode) |
| `re6_model_editor/core/model.py` | editable model (`Mod211 <-> Model`), skin weights, format choice, bounding volumes |
| `re6_model_editor/core/validate.py` | structural invariants of retail files |
| `re6_model_editor/blender/` | import, export, operators, panels |
| `docs/MOD211_vs_MOD3.md` | format notes and the comparison with MHW mod3 |
| `tools/` | analysis and regression scripts (`roundtrip_*`, `validate_all`, `compare_*`), `mhw_probe/` = early MHW -> RE6 experiment |

## Verification done (no in-game test yet!)

* parse -> write is byte identical for all 5500+ `.mod` of the game,
* `Mod211 -> Model -> Mod211` byte identical for 5428 models,
* Blender import -> export keeps positions, UVs, normals, tangents, weights for 48 mixed models,
* every exported file satisfies `core/validate.py` (rules true for 98.5% of the retail models).

Materials and textures: the importer reads the `.mrl` of the model (next to it, or from the game `.arc` archives, see `docs/MRL.md`)
and builds node trees with albedo / normal / mask textures (`.tex` -> DDS, packed into the .blend). Set the game folder in
the add-on preferences if the model is not inside it. `RE6 > Export RE6 MRL` writes the material library (texture slots can be edited in Properties > Material > RE6 Material or with
`Assign Texture`), `RE6 Tex Tools` converts `.tex` <-> `.dds` / images. The feature list next to the MHW Model Editor is in
`docs/MHW_PARITY.md`. The UI has a Simplified Chinese translation.

Known gaps: constant buffer (material parameter) editing, in-game tests of exported `.mrl` / `.tex`, `tail` (draw sort key) is generated, shadow meshes are
kept as imported, bone-weight limits and more than 65535 vertices per mesh are reported as errors.

## Credits

The names of the shader objects (material states, texture slots, constant buffers, vertex formats), the float layout of
the constant buffers and the bit layout of the material flags come from [albam](https://github.com/Brachi/albam)
(MIT, `mrl.ksy` / `mod-21.ksy`); they are kept as data in `tools/data/` and compiled into `core/shader_names.py` and
`core/cb_layouts.py` by `tools/make_shader_names.py`.

## License

Based on the [MHW Model Editor](https://github.com/chikichikibangbang/MHW_Model_Editor) (GPL-3.0-or-later, by
诸葛不太亮 and NSACloud): the add-on structure and parts of the Blender layer were ported and adapted from it for RE6.
See `NOTICE.md`.

Copyright (c) 2026 Dimcirui. Licensed under the GNU General Public License, version 3 or (at your option) any later
version (`GPL-3.0-or-later`), see `LICENSE`. Third-party MIT notices are in `LICENSES/`. The `sideloader/` folder keeps its
own MIT license (`sideloader/LICENSE`).
