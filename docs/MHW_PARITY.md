# Feature comparison with the MHW Model Editor

| MHW Model Editor | RE6 Model Editor | status |
|---|---|---|
| Import / export mod3 (options: clear scene, all LODs, armature only, display type, bone size, selected / visible only, export all LODs, use Blender material names) | Import / export `.mod`: same options (`RE6 Model (.mod)`) | done |
| Drag and drop of the model file into the viewport | `RE6_FH_mod` file handler | done |
| Add-on preferences with defaults for every dialog, remembered export folder | `Preferences > Add-ons > RE6 Model Editor` | done |
| Mesh Tools panel: create collection, rename meshes, set group id, delete loose geometry, remove empty vertex groups, limit total + normalize, bake normal to vertex colour | `RE6 Mesh` sidebar tab, same operators (`mesh_tools.py`) | done |
| Mesh properties (custom properties `Mod3_Mesh_*` on the mesh data, no panel) | custom properties `Mod_Mesh_*` on the mesh data | done (v0.3, see MHWME_ALIGNMENT.md) |
| Export error window | `RE6 Export Error` popup (`re6_mod.show_export_error_window`) | done |
| mrl3: materials with textures, Principled BSDF node trees | `.mrl` -> node trees (albedo / normal / mask), `Load MRL` | done |
| mrl3: material objects in an `.mrl3` collection, edit properties / sampler list / map list, reindex, add / delete | `<name>.mrl` collection with one empty per material, `RE6 MRL` panel (import .mrl alone, replace, add, duplicate, delete, move, reindex, add missing), slots, blend, two sided | done |
| mrl3: property list (named values) | constant buffers as float lists, grouped by buffer hash | done, but the values have no names (the parameter names are hashes we cannot resolve) |
| mrl3: export | `RE6 > Export RE6 MRL` from the MRL collection (texture table rebuilt, missing materials from a template) | done (not tested in game) |
| mrl3: material presets | none; new materials use one built in template | open |
| Tex conversion (texconv): tex <-> dds, directory conversion | `RE6 Tex Tools`: TEX -> DDS, image / DDS -> TEX (own BC1 / BC3 encoder with mip chain), export the textures of a model | done (single files, no directory recursion) |
| Translations (zh_CN) | `i18n.py` (`zh_HANS` / `zh_CN`), follows Blender's language settings | done for the UI, export error messages stay English |
| Bounding box import / export | bounding volumes are regenerated (`core/model.py`) | not needed |
| CTC chains, CCL collisions | RE6 has both (`.ctc` v22, `.ccl`), see docs/CTC_CCL.md | done (Blender layer like MHWME, `RE6 Chain` tab) |
| Batch exporter (commented out upstream), addon updater | - | open |

Differences that come from the format: RE6 has one fixed vertex layout per influence count (40 formats, chosen automatically),
int16 quantised positions, and no per mesh bounding boxes to import.
