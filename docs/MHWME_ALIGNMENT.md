# 与 MHW Model Editor 完全对齐：逐项对照表

目的：RE6 插件的布局（集合、对象、属性、面板、算子、选项）与 MHWME 一一同构，只换游戏前缀；同构之后再把公共部分抽成共享层，
统一 MT Framework 的 modding 流程。本表是重写前的**审批稿**，没有改任何代码。

数据来源：MHWME 源码（`MHW_Model_Editor-main`，用 AST 提取的类、属性、算子、面板清单，以及 `file_mrl3.py`、
`mrl3_panels.py`、`mrl3_properties.py` 的实际内容）和本仓库当前代码。**没有读到的部分标了「待查」。**

图例：`=` 已一致　`改名` 只需换标识符或标签　`重做` 结构不同，要重写　`新增` RE6 现在没有　`无对应` 需要你决定　`不适用` RE6 没有这个概念

---

## 进度（v0.3.0，结构层已完成并在 Blender 里实测）

D1 到 D5 都按建议执行。已完成：

- **第 1 节**：`~TYPE` 标记（`RE6_MOD_COLLECTION` / `RE6_MRL_COLLECTION` / `RE6_MRL_MATERIAL`）；网格属性改为网格数据上的自定义属性
  `Mod_Mesh_*`（`Index`、`LOD`、`RenderMode`、`Flags`、`AlphaPriority`、`WeightFlags`、`WeightNum`、`VertexFormat`、`ConnectId`、
  `Boundary`、`Imported`），`RE6 Mesh` 面板和 `re6_mesh` 属性组已删除；组号只从物体名 `Group_<n>` 取；集合头数据 `Mod_Header_*`、
  `Mod_Group_NNN`（每组一个球体）、`Mod_Source`；骨骼 `Mod_Bone_*`；mrl 集合 `Mrl_Source`、`Mrl_Header_Unk`，材质物体 `Mrl_Name`、`Mrl_Data`；
  `ModExportExclude` 物体不导出。集合命名 `<name>.mod` / `<name>.mrl`，嵌套在 `<name>` 里，按名字关联；场景级
  `re6_mod_toolpanel` / `re6_mrl_toolpanel` 保存活动集合、导出集合、mod 目录、贴图目录和转换设置。
- **第 2 节**：单一标签页 `RE6 Mesh`：RE6 Mrl Tools（带 Material List 子面板，放 RE6 独有的条目管理）→ RE6 Mesh Tools → RE6 Tex Tools；
  材质属性面板在数据页，只对 `~TYPE == RE6_MRL_MATERIAL` 的物体显示。
- **第 3 节**：算子改为 `re6_mod.*` / `re6_mrl.*` / `re6_tex.*`；新增 Create Nested Collections、Create Mrl Collection、Replace String、
  Convert Settings、Convert Directory to Tex、Open Conversion Folder、Copy Converted Tex Files；tex 转换合并为一个按扩展名判断方向的算子；
  mod / mrl 各有自己的导出错误窗口；chunk 路径列表对应为游戏路径列表（`re6_mod.game_path_list_*`）。
- **第 4 节**：选项改用 MHWME 的标识符（`clearScene`、`addNestedCollections`、`createCollections`、`importArmatureOnly`、`importAllLODs`、
  `ArmatureDisplayType`、`BonesDisplaySize`、`loadMrlData`、`loadMaterials`、`useBackfaceCulling`、`mrlPath`、`selectedOnly`、`visibleOnly`、
  `exportAllLODs`、`useBlenderMaterialName`；RE6 独有：`importShadow`、`shadowMode`、`textureDirectory`），偏好设置 `default_*` 同名；
  D5：`useBackfaceCulling`、`useBlenderMaterialName`、`loadMrlData` 的默认值与 MHWME 一致（都为关）；导出集合改用指针
  `exportModCollection` / `exportMrlCollection`；`last_export_dir_mod` / `_mrl` 分开记。
- 待查项的结论：`autoSolveRepeatedUVs` 和 `preserveSharpEdges` 我们的导出器始终开启（按 UV、法线、颜色拆顶点），不提供开关；
  `allowDuplicateBoneNames` 不提供（顶点组按骨骼名匹配，带 `.001` 后缀的骨骼名会失配）；`importBoundingBoxes`、`exportBoundingBoxes`
  不做（包围体每次导出重新生成）。

**第 5 节进度（Map List 和 Sampler List 已完成）**：`re6_mrl_material.mapList_items`（`name` 槽名、`value` 贴图路径、`code` 槽哈希）和
`samplerList_items`（`name`、`value` 状态序号、`code`、隐藏的 `state`）取代了旧的 `bindings`；UIList 照搬 MHWME（过滤框、35% 名字列、
禁用双击重命名）；材质面板的子面板顺序为 Map List、Property List、Sampler List（默认折叠），材质页和数据页各一套。
采样器的 `value` = 状态对象相对槽位默认状态的序号：`(a & 0xFFF) - (b & 0xFFF)`，默认状态 `a == b` 为 0。官方数据里只有
`SSAlbedoMap` 有 1 个备选，`SSNormalMap` 有 1 个，`SSEnvMap` 有 5 个（`core/mrl.py` 的 `SAMPLER_STATES`），90491 条采样器命令全部能还原；
改到未知序号时导出会报错并列出已知序号。
**Property List 已完成**：`re6_mrl_material.propertyBlock_items`（块名、缓冲区哈希）里是 `Re6PropPG`（`prop_name`、`ori_name`、`offset`、`data_type`、
`float_value` / `float2_value` / `float3_value` / `float4_value` / `color_value` / `color4_value`），取代了旧的 `cbuffers`。
`$Globals`（35 项）、`CBMaterial`（10 项）、`CBColorMask`（6 项）、`CBVertexDisplacement(2)` 按 albam 的字段名显示，填充字段不显示；
宽于 4 个浮点的值拆成 `name_0`、`name_1` 行；名字以 `_color` / `_color_2` 结尾或含 `rgb` 的 3 或 4 浮点值用取色器（`COLOR`、`COLOR4`，
MHWME 只有 `COLOR`）；没有布局的缓冲区按 4 个浮点一行显示为 `f0`、`f4` ……。导出时只把改过的值写回命令块，没动的值保持原位（官方
数据上未改动导出的常量缓冲区与原文件逐字节一致）。带扳手图标的属性会同步到预览材质：`shininess` → Roughness（`sqrt(2/(shininess+2))`），
`specular_color` → Specular Tint（`props.DRIVEN`，`materials.apply_driven`）。MHWME 里更多属性驱动节点，这里只做这两个，因为预览只是近似。

**拖放**：`RE6_FH_mod`、`RE6_FH_mrl`、`RE6_FH_tex`（`.dds;.tex`）三个文件处理器（Blender 4.1+），行为照 MHWME：拖入 `.mod` 时按偏好设置 `dragDropImportOptions`（默认开）弹出导入选项，关闭则直接用默认选项导入；`.mrl` 直接导入，放进同名 `<name>.mod` 所在的父集合；`.tex` 和 `.dds` 直接互相转换（输出位置和设置同 Convert Settings）。不是拖放时仍然打开文件浏览器。文件菜单里有 `.mrl` 的导入导出项。

**材质面板头部**（v0.3.x）：材质属性面板顶部是一个黑色头部块（MHWME 的 Master Material Type / Material Name 那块）：
第一行 `Shader Type: nDraw::MaterialStd`，第二行 `Material Name`，名字解得出就显示名字，解不出显示 `MAT_<哈希>`。
输入名字会用 jamcrc32 算出哈希，输入 `MAT_xxxxxxxx` 则直接当作哈希。哈希、序号、预览材质指针不再显示（Linked Material 不单独实现）。
Blend、Depth、Raster（下拉框，显示引擎的状态名 `BSSolid` / `DSZTestWrite` / `RSMesh` 等，未知哈希为 Custom）和所有标志位合并成子面板 **Flags**，与 Map List、Property List、Sampler List 平级，默认折叠；
子面板顺序为 Flags、Shader Features、Map List、Property List、Sampler List（Flags 在最上面）。

**材质物体的名字**：照 MHWME 的 `Mrl3 Material 00 (name)` 命名为 `Mrl Material 00 (pl_skin)`，名字解不出时括号里是 `MAT_<哈希>`；
文件里的顺序就是物体名的顺序（`entries()` 按名字里的序号排序，序号按数字比较，超过 99 也正确），不再依赖 `index` 属性；
改 `Material Name` 会改物体名，改物体名括号里的名字再按 Reindex Mrl Materials 会改材质名（`reindexMaterials()` 的逻辑）；
移动、复制、删除都通过重新编号物体名实现。

**网格物体的名字**：按 MHWME 的 `Group_0_Sub_0__<材质名>`，材质名是解出的名字（`Group_0_Sub_0__pl_cloth`），解不出才是 `MAT_<哈希>`；
预览用的 Blender 材质同样以材质名命名。重命名网格（Rename Meshes）会取 Blender 材质的名字，材质还是默认的 `MAT_<哈希>` 时取解出的名字；
导出时“按物体名取材质”的模式（`useBlenderMaterialName` 关，默认）把 `__` 后面的名字按 jamcrc32 算成哈希，不报警告。
组号只从物体名里的 `Group_<n>` 取（和 MHWME 一样，改名后没有 `Group_` 的物体组号为 0）。

未做（按计划在后面）：
第 6 节的预设、`loadUnusedTextures` / `loadUnusedProps`、贴图缓存、自动更新器。

---

## 1. 三个结构性差异（影响其余所有条目）

| # | MHWME | RE6 现在 | 目标 | 状态 |
|---|---|---|---|---|
| 1 | 集合和对象用自定义属性 `~TYPE` 标记：`MHW_MOD3_COLLECTION`、`MHW_MRL3_COLLECTION`、`MHW_MOD3_BBOX_COLLECTION`、对象 `MHW_MRL3_MATERIAL`、`MHW_MOD3_AABB` 等；面板的 poll 和下拉过滤都看它 | 集合键 `re6_model` / `re6_mrl`，对象用 `re6_mrl_material` 指针判断 | `~TYPE` = `RE6_MOD_COLLECTION` / `RE6_MRL_COLLECTION` / `RE6_MRL_MATERIAL` | 重做（小） |
| 2 | 网格、分组、骨骼、文件头的未知字段是**自定义属性**（对象上的 Custom Properties 面板）：`Mod3_Mesh_Index`、`Mod3_Mesh_RenderMode`、`Mod3_Mesh_ShadowFlag`、`Mod3_Mesh_Unkn`、`Mod3_Group_000…`、`Mod3_Header_Unkn1…5`、`Mod3_Bone_Symmetry`、`Mod3_Bone_Unkn`、`Mod3ExportExclude`；没有专门的“网格属性”面板 | `re6_mesh` PropertyGroup + 数据页 `RE6 Mesh` 面板（group、lod、render_mask、unk3、wd_*、fmt、ui、tail） | 改成 `Mod_Mesh_*` / `Mod_Group_*` / `Mod_Header_*` / `Mod_Bone_*` 自定义属性，删掉 `RE6 Mesh` 面板 | 重做（中，见决策 D1） |
| 3 | 材质 = `Mrl3MaterialPG`（名字、名字哈希、MMTR、shader 哈希、surfaceCoef、alphaCoef、linkedMaterial）+ 三个带过滤框的 UIList（Map / Property（按块分组）/ Sampler） | `Re6MaterialProps`（哈希、状态枚举、标志位字段、绑定列表、cbuffer 展开行） | 见第 5 节 | 重做（大） |

## 2. 侧栏标签页与面板

MHWME 所有工具面板都在同一个标签页 `MHW Mesh` 下，顺序：MHW Mesh Tools → MHW Mrl3 Tools → Presets → MHW Tex Tools。
材质属性面板在属性编辑器的**数据**页，且只在 `~TYPE == MHW_MRL3_MATERIAL` 的对象上显示。

| MHWME 面板 | 内容 | RE6 现在 | 目标 | 状态 |
|---|---|---|---|---|
| `MHW Mesh Tools`（`OBJECT_PT_mod3_mesh_tools_panel`） | Create Mod3 Collection、Create Nested Collections、Rename Meshes、Set Mesh Group ID、Bake Normal To Vertex Color、Delete Loose Geometry、Remove Empty Vertex Groups、Limit Total and Normalize All | `RE6 Mesh Tools`（标签页 `RE6 Mesh`），缺 Create Nested Collections | 标签页 `RE6 Mesh`；补 Nested Collections | 改名 + 新增 |
| `MHW Mrl3 Tools` | Import/Export Mod3、Import/Export Mrl3、Active Mrl3 Collection（集合指针）、Create Mrl3 Collection、Reindex Mrl3 Materials、Mod Directory | `RE6 Model Editor`（标签页 `RE6`）只有导入导出；`RE6 MRL` 面板是列表式管理 | 合并进 `RE6 Mesh` 标签页，布局照抄 | 重做 |
| `Presets` | 预设下拉、Add Preset Material、Save Preset、Open Preset Folder | 无 | 同构 | 新增 |
| `MHW Tex Tools` | Tex Conversion + 设置齿轮、Texture Directory、Convert Directory to Tex、Open Conversion Folder、Mod Directory、Copy Converted Tex Files | `RE6 Tex Tools`：TEX→DDS、图→TEX、导出模型贴图 | 见第 7 节 | 重做（中） |
| `Mrl3 Material Properties`（数据页） | Master Material 类型、Material Name、Linked Material、Surface Coef、Alpha Coef；子面板 Map List / Property List / Sampler List（默认折叠） | `RE6 Material`（材质页）、`RE6 MRL Material`（物体页） | 数据页，`~TYPE` 过滤；子面板同名 | 重做 |
| 侧栏 `RE6 MRL`（我们自己的列表） | 材质条目列表、增删移 | 无对应（MHW 靠 Blender 自带的物体操作） | 见决策 D2 | 无对应 |

## 3. 算子

前缀建议：`mhw_mod3` → `re6_mod`，`mhw_mrl3` → `re6_mrl`，`mhw_tex` → `re6_tex`。

| MHWME `bl_idname` | 标签 | RE6 现在 | 状态 |
|---|---|---|---|
| `mhw_mod3.import_mhw_mod3` / `export_mhw_mod3` | Import/Export MHW MOD3 | `import_mod` / `export_mod`（旧名） | 改名，已完成 |
| `mhw_mod3.show_export_error_window` | MHW Mod3 Export Error | `show_errors`（三个模块共用一个） | 改名，拆成 mod / mrl 各一个 |
| `mhw_mod3.create_mod3_collection` | Create Mod3 Collection | `create_collection`（同时建 .mrl 集合） | 改名；.mrl 集合改为单独的 `create_mrl_collection` |
| `mhw_mod3.create_nested_collections` | Create Nested Collections | 无 | 新增 |
| `mhw_mod3.rename_meshes` / `set_mesh_group_id` / `delete_loose_geometry` / `remove_empty_vertex_groups` / `limit_total_normalize` / `bake_normal_to_vertex_color` | 同名 | `rename_meshes` / `set_group_id` / `delete_loose` / `remove_empty_groups` / `limit_normalize` / `bake_normal_color` | 改名 |
| `mhw_mrl3.import_mhw_mrl3` / `export_mhw_mrl3` | Import/Export MHW MRL3 | `import_mrl` / `export_mrl` | 改名 |
| `mhw_mrl3.create_mrl3_collection` | Create Mrl3 Collection | 并在 create_collection 里 | 新增（拆出） |
| `mhw_mrl3.reindex_mrl3_materials` | Reindex Mrl3 Materials | `mrl_reindex` | 改名 |
| `mhw_mrl3.replace_string` | Replace String（贴图路径批量替换） | 无 | 新增（容易） |
| `mhw_mrl3.save_selected_as_preset` / `add_preset_material` / `open_preset_folder` | 预设三件套 | 无 | 新增 |
| `mhw_tex.convert_mhw_tex_dds_files` | 选文件，.dds→.tex、.tex→.dds | `tex_to_dds`、`image_to_tex` 两个 | 合并 |
| `mhw_tex.convert_tex_directory` / `convert_settings` / `open_conversion_folder` / `copy_converted_tex` | 目录转换、设置、打开目录、复制到 mod 目录 | 无（`export_textures` 只导出模型用到的） | 新增 |
| `mhw_mod3.clear_texture_cache_folder` / `check_texture_cache_size` / `open_texture_cache_folder` | 贴图缓存管理 | 无（我们直接打包进 .blend） | 见决策 D3 |
| `mhw_mod3.chunk_path_list_add_item` / `remove_item` / `reorder_item` | 多个 chunk 路径列表 | 单个 `game_dir` + `texture_dir` | 重做（RE6 可用游戏目录 + mod 目录的列表） |
| `mhw_ctc.*`、`mhw_ccl.*` | 链和碰撞 | 无 | 不适用 |
| （RE6 独有）`mrl_add` / `duplicate` / `delete` / `move` / `select` / `refresh` / `add_missing`、`assign_texture`、`load_mrl` | | | 无对应，见 D2 |

## 4. 导入导出选项

| MHWME 选项（标签） | RE6 现在 | 状态 |
|---|---|---|
| `clearScene`（Clear Scene） | `clear_scene` | = |
| `addNestedCollections`（Add Nested Collections，默认开） | 无 | 新增 |
| `createCollections`（Create Collections，默认开，同时给每个 LOD 建集合） | 无（LOD 集合由 `all_lods` 决定） | 新增 |
| `importArmatureOnly` | `armature_only` | = |
| `importAllLODs` | `all_lods` | = |
| `importBoundingBoxes` | 无 | 不适用？RE6 有包围球/AABB，可以导入做调试，待查 |
| `ArmatureDisplayType` / `BonesDisplaySize`（默认 5） | `display_type` / `bone_size`（默认 4，单位厘米） | = |
| `loadMrl3Data`（把材质导入为集合里的物体，默认关） | 总是导入 | 新增（开关，默认值要对齐） |
| `loadMaterials`（Load Mesh Materials） | `textures`（Load Textures） | 改名 |
| `loadUnusedTextures` / `loadUnusedProps` | 无 | 新增，`loadUnusedProps` 取决于 D4 |
| `useBackfaceCulling`（默认关） | `backface_culling`（默认开，语义是“用 .mrl 的剔除状态，关 = 全部双面”） | 语义不同，要统一 |
| `reloadCachedTextures` | 无（没有缓存） | 见 D3 |
| `mrl3Path` | `mrl_path` | 改名 |
| `loadPhysics`（ctc、ccl） | 无 | 不适用 |
| `selectedOnly` / `visibleOnly` / `exportAllLODs` | `selected_only` / `visible_only` / `export_all_lods` | = |
| `autoSolveRepeatedUVs`、`preserveSharpEdges`、`allowDuplicateBoneNames` | 待查：我们的导出器有没有这些处理，有没有开关 | 待查 |
| `useBlenderMaterialName`（默认关，关 = 材质名从物体名取） | `material_from_name`（默认开，开 = 从网格材质取） | 语义相同、默认值相反，要统一 |
| `exportBoundingBoxes`、`invisibleMantlesModFix` | 无 | 不适用 |
| （RE6 独有）`import_shadow`、`shadow_mode` | | 保留，放进 RE6 专用选项组 |
| `showMod3Options` / `showMrl3Options` / `showCTCCCLOptions`（折叠） | 无 | 新增（纯界面） |

偏好设置：MHWME 每个选项都有 `default_*`，另有 `last_export_dir_mod3/mrl3/ctc/ccl`、贴图缓存、chunk 路径列表、自动更新、外部链接、
拖放导入选项（Blender 4.1+）、`showConsole`、`useDDS`。RE6 现在有各项 `default_*` 和单个 `last_export_dir`，其余都没有。

## 5. 材质数据模型

### 5.1 `Mrl3MaterialPG` ↔ RE6

| MHWME 字段 | 含义 | RE6 对应 | 状态 |
|---|---|---|---|
| `materialName` | 材质名，必须与 mod3 里的一致 | `re6_name`（只有解出的名字）。RE6 的 .mod 只存哈希，名字大多未知 | 改名；未解出时用 `MAT_xxxxxxxx`，与现在导出规则一致 |
| `materialNameHash` | 名字哈希 | `re6_mrl_material.hash` | 改名（RE6 用 jamcrc32(name) 和 MHW 相同，已验证） |
| `mmtrHash` / `mmtrName` | 主材质类型（来自 ShaderPackage.sdf，字典里 112 个） | 材质类型哈希 `shader`（0x5fb0ebe4 占 99%，共 4 种） | 改名；只显示类型名（`nDraw::MaterialStd` 等） |
| `shaderHash` | 与 MMTR 一一对应的着色器哈希 | 无独立字段 | 无对应，见 D4 |
| `surfaceCoef`（2 字节）/ `alphaCoef`（4 字节） | 作者注释“这个字段不清楚”，默认 `[0,225]`、`[150,112,4,0]` | blend / depth / raster 状态哈希 + 两个标志字，已解码 | 见第 9 节 |
| `linkedMaterial` | 对应的 Blender 材质 | `visual` | 改名 |
| `mapList_items`（name、value=路径、code=哈希） | 贴图列表 | `bindings`（slot 哈希、路径） | 改名，补 name（槽名）字段 |
| `samplerList_items`（name、value=整数、code=哈希） | 采样器列表 | type 2 命令：槽名 `SSAlbedoMap` 等；值 = 命令的 `a`（状态对象哈希） | 重做，见 5.3 |
| `propertyBlock_items`（块名、code、属性列表） | 按常量缓冲区分组的属性 | `cbuffers`（哈希、偏移、浮点列表） | 重做，见 5.2 |

### 5.2 Property List

MHWME 每个属性（`Mrl3PropPG`）有 `prop_name`、`ori_name`、`data_type`（FLOAT / INT / UINT / BOOL / FLOAT[2] / FLOAT[3] / FLOAT[4] / COLOR）和对应类型的值。
列表带过滤框，可驱动 Blender 材质里同名节点的属性带扳手图标。

RE6：块 = 常量缓冲区。`$Globals`（84）、`CBMaterial`（32）、`CBColorMask`（24）、`CBVertexDisplacement`（8）、
`CBVertexDisplacement2`（4）有字段名和布局，可以直接生成 `Mrl3PropPG` 同构的属性，类型按字段推：
3 个浮点且名字带 color → COLOR，其余按长度 FLOAT / FLOAT[2..4]。其他缓冲区（`CBBAlphaClip`、`CBVertexDisplacement3`、
`CBDistortionRefract` 等）没有布局，显示为 FLOAT 行。**状态：重做（中）。**

驱动节点：MHWME 靠 `mrl3_nodes.py` 里硬编码的 `addPropertyNode("属性名")`；RE6 要自己决定哪些属性驱动预览节点（albedo 色、高光色、
shininess、自发光色、alpha 裁剪阈值）。预览只是近似，不等于游戏内效果。

### 5.3 Sampler List 与 Flags

RE6 命令里 type 0（45 个着色器开关，每个材质都有）和 type 2（采样器状态）：`b` 是名字哈希（低 12 位对每个名字是常量），
**`a` 才是取值**，它是所选选项的哈希（例如 `FUVAlbedoMap` 的 `a` 绝大多数是 `91272564`，`FUVAlbedoBlendMap` 多为 `c4ef1565` / `5808b568`；
这些选项哈希的低 12 位依次是 0x564、0x565、0x566、0x567、0x568 … 0x56c，像枚举序号，可能是 UV 通道 0..8，**未验证**）。选项哈希本身没有名字（不在 albam 表里）。

所以 Sampler List 的 `value` 可以对应命令的 `a`，显示选项序号；type 0 开关没有 MHW 对应列表，可以做成额外的 Flags 子面板（我们现在的 Flags 框只是
材质头的位字段，这 45 个开关还没有界面）。**状态：重做（小），语义未定。**

## 6. 预设

MHWME：`MaterialPresets` 文件夹 + `Mrl3MaterialPresets` 下拉，保存选中材质、按预设新增材质、打开预设文件夹。RE6：全部新增。
预设文件格式自己定（JSON：类型、状态、标志位、绑定槽名、cbuffer 浮点）。**容易。**

## 7. 贴图工具

MHWME 依赖 texconv（BC7 sRGB / BC5 Linear 等）。RE6 是 BC1 / BC3，我们有自己的编码器。
要对齐的是面板和算子的形态：一个“选文件转换”（.dds→.tex、.tex→.dds）、一个“转换目录”、转换设置（加 Converted 文件夹、加 DXGI 前缀、转换后打开目录）、
复制到 mod 目录（按 mrl 里的贴图路径放）。**中等，主要是界面。**

## 对照审计（逐文件对照 MHWME 的 mod3 / mrl3 / tex / preference / 顶层，已按结果修改）

**对本文旧内容的更正**：面板顺序由 `@reg_order` 决定，是 Mrl3 Tools（0）→ Presets（2）→ Mesh Tools（18）→ Tex Tools（20），我们已经一致，
只缺 Presets；MHWME 没有 Flags 面板，那是 RE6 自己的；MHWME 的 `BonesDisplaySize` 默认值是 5（不是 4）；MHWME 直接导入 `.mrl3`
时集合放在场景根，我们放在同名 `.mod` 旁边。

**已改成与 MHWME 一致**
- 文件菜单：Import / Export 各一个 `RE6 Model Editor` 子菜单（图标 `MOD_LINEART`），条目 `RE6 MOD (.mod) (Model)`、`RE6 MRL (.mrl) (Material)`。
  FileHandler 改名 `RE6_MOD_FH_drag_import`、`RE6_MRL_FH_drag_import`、`RE6_TEX_FH_drag_import`，标签 `File handler for … importing`。
- 导入 / 导出对话框：选项顺序、`clearScene` 在盒子外、`DOWNARROW_HLT` / `RIGHTARROW` 图标折叠、`Armature Display Type:` / `Bones Display Size:`
  标签、`Manual Mrl Path:`、`useBackfaceCulling` 和 `createCollections` 不画、`mrlPath` 去引号、`BonesDisplaySize` 用 `step=100` / `soft_min=0`、
  导出对话框一个盒子（`Mod Collection:` 标签、`COLLECTION_COLOR_01` 图标、红色 `Must select a mod collection first !!!`）；导出集合按
  上次导出 → 活动集合 → 上次导入的顺序选；文件名只给名字（再接上次导出目录）；`importSettingsLoaded` / `exportSettingsLoaded` 只在第一次载入偏好默认值；
  多文件导入失败不中断；成功 / 失败的提示语和 MHWME 一致；导出成功后自动设置 `modDirectory`；导出集合选择器改变时同步文件浏览器的文件名。
- 导出错误窗口：新的 `blender/export_errors.py`——错误字典 `{类型: {count, objectSet / boneSet}}`、`Re6ErrorEntry` 属性组、`MESH_UL_Re6ErrorList`、
  `re6_mod.show_export_error_window` / `re6_mrl.show_export_error_window`（宽 750、0.35 分栏、说明框和 `ERROR OBJECTS` 框）、
  控制台红色汇总、`scene.re6_mod_error_list` / `re6_mrl_error_list`。重复材质会列出出错的对象名；没有目标集合时按钮不再置灰，而是弹错误窗口。
- 偏好设置：外观和顺序（Advanced Options → Import → Export → Game Path），所有 `default_*` 补全了说明，加了 `showConsole`（导入 / 导出前后切换控制台）、
  `saveGamePaths`（导入时把检测到的游戏文件夹加进列表）、游戏路径列表改成 MHWME 的样式（Add / Remove、Move Up / Move Down，添加空项后直接编辑）；
  `exportAllLODs`、`useBackfaceCulling` 的默认值不再画出来；`bl_idname` 改成包名，作为扩展安装时也能用；翻译同时注册 `zh_HANT` / `zh_TW`。
- 材质面板：`use_property_split` 设在面板的 layout 上；加了 `HIDE_RE6_MRL_EDITOR_PANEL`（材质面板）和 `HIDE_RE6_MRL_EDITOR_TAB`（Mesh Tools、Tex Tools）；
  Property List 每个块各建一个缩进分栏；空物体大小 0.10，去掉隐藏渲染和变换锁定；`re6_mat` 改名 `re6_mrl_material`，预览材质指针改名 `linkedMaterial`
  （标签 `Linked Material`，不画出来）。
- Mrl 操作：Create Mrl Collection 总是建 / 复用 `<name>` 父集合，名字取自 `lastImportCollection`；Reindex 用 `mrlCollection` 做 poll、带说明和提示；
  Replace String 只作用于活动对象，提示语 `Replaced string "a" to "b".` / `Unable to match the string "a".`；导入的 `previews`、`texture_dir` 隐藏。
- Mesh Tools：Create Mod Collection 同样建 `<name>` 父集合，且不再设置 `lastImportCollection`；Set Mesh Group ID 的属性名改成 `groupID`，用 `re.search`，
  只统计真正改了名的对象；Limit Total 不再弹窗；Bake Normal 的轴名称、枚举顺序和说明与 MHWME 相同；所有说明文字和提示语改成 MHWME 的原文（换了 mod / mrl）。
- 导入行为：LOD 集合命名 `LOD <level> - <mod 集合名>`（level 为 `ALL` 或 0, 1, 2 …），网格前缀 `LOD_<level>_`，除 `ALL` 和 `0` 外的 LOD 集合默认隐藏；
  **导出时按网格所在的 LOD 集合决定 LOD 掩码**（`ALL` = 255，第 n 级 = `1 << n`，最高一级 = `256 - (1 << n)`；导入时保存的掩码属于同一级就保持不变，所以无修改的往返不变）；
  子网格编号按组排序；阴影集合命名 `Shadow - <name>`；骨骼 `inherit_scale = NONE`，没有镜像骨骼时不写 `Mod_Bone_Symmetry`；
  `clearScene` 清掉集合、网格、材质、骨架、节点组和无用户的图像。
- Tex 工具：转换完成后弹窗并返回 `FINISHED`；错误用弹窗（`There are no .dds files in provided directory.` 等）；按钮 poll 只看贴图目录非空，Open Conversion Folder
  会创建文件夹再打开；Convert Settings 用盒子、`scale_y 1.1`、`check()`；加了 `addDXGIFormatPrefix`（.tex 转 .dds 时加 `DXT1_` / `DXT5_` 前缀）；
  Copy Converted Tex 不再用 poll，缺什么就弹窗说明。

**有意保留的差异**
- 命名：`re6_*` / `RE6_*` / `Mod_*` 前缀（游戏前缀）；材质物体 `Mrl Material NN (name)`，未知名字显示 `MAT_<hex8>`（MHWME 是 `Unknown Hash <十进制>`）；面板类名 `RE6_PT_*`。
- 材质头：`Shader Type:` 代替 `Master Material Type:`（RE6 没有 MMTR，未知着色器显示原始哈希），没有 `Surface Coef` / `Alpha Coef`，多了 Flags 子面板；
  Map List 里多了 Assign Texture 和 Refresh Preview；Property List 多了 `COLOR4`，隐藏 `offset`；Material List 子面板、条目增删移动、Load MRL、Add Missing 是 RE6 独有的。
- 导入对话框：多了 `importShadow`；导出对话框多了 `shadowMode`；导出 mrl 对话框多了 `export_textures`、`flip_green`（默认都关）；贴图转换多了压缩、法线、翻转绿通道三个设置，
  贴图文件名后缀和格式不同（DXT1 / DXT5，自带 BC 编码器）。`BonesDisplaySize` 默认 4。
- 导出失败时返回 `CANCELLED`（MHWME 返回 `FINISHED`）；导入 `.mrl` 时集合放在同名 `.mod` 旁；`entries()` 按名字里的数字排序（超过 99 个也对）。
- `Mod_Mesh_*`（11 个）、`Mod_Header_*`、`Mod_Bone_Index` / `Radius`、网格上的 `re6_tan` / `re6_tsign` 属性：为了无损往返，MHWME 没有对应物。
  （`Mod_Bone_Id` 已删除，2026-10-03：骨骼 function id 只看骨骼名，和 MHWME 一致；见 `docs/MHWME_BEHAVIOR_AUDIT.md` A1。）
- Limit Total 的上限是 4（RE6 的顶点格式）；Set Mesh Group ID 的上限 4095；没有 `autoSolveRepeatedUVs` / `preserveSharpEdges` / `invisibleMantlesModFix` /
  包围盒选项（理由见上）；`allowDuplicateBoneNames` 已加（2026-10-03，`RE6Bone_050.001` 写成 id 50）；没有贴图缓存、自动更新器、External Links（还没有公开仓库地址）。
- 类名和 `bl_idname` 不是 `OBJECT_PT_*`；`core/` 不依赖 bpy。

**预设（已完成）**：`blender/mrl_presets.py`，Presets 面板（枚举 `MrlMaterialPresets`、Add Preset Material、Save Preset、Open Preset Folder）位于 RE6 Mrl Tools 和 Mesh Tools 之间。
和 MHWME 的差别：预设放在 Blender 配置文件夹（`config/re6_model_editor/MaterialPresets`，插件更新不会删掉）；JSON 的头里存的是 RE6 的字段
（`shader`、`blend`、`depth`、`raster`、`flags` 各字段）和写回文件所需的 `data`（命令块、动画块、blend factor；命令块已经带上 Property List 里改过的值），
另有 `presetType = RE6_MRL_MATERIAL`、`presetVersion`；Sampler List 多存 `state`，Property List 多存 `offset`；预设名不允许含路径字符；读到损坏的预设不会留下半成品对象。
测试：保存、再添加后，新条目的命令块、动画块、标志、状态哈希、贴图绑定与原条目逐字节相同。

**CTC / CCL（已完成）**：RE6 有 `.ctc`（v22）和 `.ccl`（和 MHW 相同），见 `docs/CTC_CCL.md`。Blender 层对应 MHWME 的 ctc / ccl 模块：`ctc_properties`、`ccl_properties`、
`ctc_nodes`、`ccl_nodes`、`ctc_functions`、`ccl_functions`、`ctc_io`、`ccl_io`、`ctc_operators`、`ccl_operators`、`ctc_presets`、`ctc_panels`、`objects`；侧边栏标签页 `RE6 Chain`
（RE6 CTC & CCL Tools → Clipboard → Presets → Visibility → Properties）、属性编辑器数据页的 Header / Chain / Node / Collision 面板、导入导出对话框、文件菜单条目和拖放处理器、
`loadPhysics`、`showCTCProperties`、`last_export_dir_ctc` / `ccl`、导出错误窗口的 ctc / ccl 类型都已对齐。与 MHWME 的差异（去掉风力、WidthRate、Oval 和 Full Body Collisions，按功能 id 找骨骼，
节点矩阵导入时转置，用自定义属性保存无法显示的数据以保证无修改往返逐字节一致）见 `docs/CTC_CCL.md`。

**mod 导出错误类型（已对齐）**：改用 MHWME 的名字和标题：`NoMeshesInCollection`、`MoreThanOneArmature`、`MaxBonesExceeded`、
`IncorrectBoneNameFormat`（骨骼 id > 254）、`NoMaterialOnSubMesh`（两种取材质方式共用）、`NoVerticesOnSubMesh` / `NoFacesOnSubMesh`、
`MaxVerticesExceeded`、`TotalMaterialsExceeded`（上限 4096）；新增 `NoUVMapOnSubMesh`（阴影网格除外，原来只警告并写零 UV）、
`NoWeightsOnMesh`（整个网格没有权重；部分顶点没有权重仍是 RE6 的 `UnweightedVertices`）、`MaxWeightsPerVertexExceeded`（超过 8 个，
原来是丢弃最弱的并警告）、`MultipleSameLodCollections`、`TotalMeshesExceeded`。有意不做：`LooseVerticesOnSubMesh` 只警告不报错
（5433 个官方模型里 226 个有松散顶点，导出器本来就只写面用到的顶点，报错会让原样导出失败）；`NonTriangulatedFace`（MHWME 自己注释掉了，
我们导出时自动三角化）；`MaxFacesExceeded` / `TotalVertices/FacesExceeded`（RE6 的计数是 32 位，到不了）；`NoBonesOnArmature`、
`NoArmatureInCollection`（MHWME 有文字但从不触发）。测试：`tools/blender_clipboard_errors_test.py`；171 个官方样本导出无错误，输出与改动前逐字节相同。

**CTC 可见性默认值（已对齐，且比 MHWME 多走一步）**：偏好设置里补了 `showCTCVisibilityOptions` 和 17 个 `default_*`（链、节点、锥体、碰撞体的
显示和颜色）。MHWME 这一段整体被注释掉，默认值从未生效；这里每个场景在第一次导入 ctc / ccl 或第一次 Create CTC Collection 时套用一次
（`prefs.load_ctc_visibility`，标记 `re6_ctc_toolpanel.visibilitySettingsLoaded`），之后用户的修改不会被覆盖。
`applyPresetToChildNodes` 不加：MHWME 里只定义了属性，没有任何代码用它（也没有节点预设）。

**顶点格式（RE6 扩展，对应 MHWME 按 UV / 颜色 / 权重拼 block 名再查表）**：格式哈希是游戏固定输入布局表的条目（`(jamcrc32(官方名) & 0xFFFFF) << 12 | 编号`，
编号 0x013..0x03e），不能自造新布局，只能在 40 个已有布局里选。
- 显示官方名（`core/vertex.official_name`，如 `IASkinTB4wt`），`core/vertex.describe` 给出“4 weights, 1 UV, tangent, 28 bytes”；内部描述名里错误的
  `NonSkin*` 改成 `Rigid*`（它们是单骨骼蒙皮，官方 `IASkinBridge1wt` / `IASkinTB*1wt`）。
- 网格数据上的下拉框 `Mesh.re6_vertex_format`（读写原来的自定义属性 `Mod_Mesh_VertexFormat`，Auto = 空），有骨架的模型只列 IASkin，没有的只列 IANonSkin；
  画在 RE6 Mesh Tools 面板底部。
- 算子 `re6_mod.set_vertex_format`（Set Vertex Format）：选蒙皮 / 权重数 1 2 4 8 / UV 数 / 顶点色 / 切线（只对静态）/ 4M 额外数据，`core/vertex.compose`
  找出完全匹配的布局（可能有几个，如 IASkinTBN4wt 和 IASkinTBNLA4wt），没有就列出 `nearest` 的 3 个；骨架有无与所选不符的网格会跳过。
- 导出：选定的格式（导入的或手动设的，新建网格以前会被忽略，现在也生效）总是照用，数据按格式处理：格式没有的顶点色丢弃、多出的 UV 通道丢弃、
  超出格式权重数的骨骼影响只保留最强的几个并重新归一化，每个网格一条警告（`Mesh "..." exported as IASkinTB4wt: vertex colors dropped.`）；
  格式比数据多的 UV / 颜色 / 权重由编码器填 0 / 白 / 0。只有用不了的格式才报 `VertexFormatMismatch`：骨架有无与格式不符，或值不是格式哈希。
  Auto（空值）时不丢数据，按数据选最小格式。
- 测试：`tools/blender_vertex_format_test.py`（22 项）；4500 个官方模型 core 往返逐字节一致；171 个样本经 Blender 导出与改动前逐字节一致。

**材质名的解析（对应 MHWME 的 mod3 ↔ mrl3 联动）**：MHWME 用 mod3 里的材质名字符串算 jamcrc32 反查 mrl3 的名字哈希，再查 26.6 万条的全局字典，
最后显示 `Unknown Hash`（还留了“在场景材质里找”的 TODO）。RE6 的 .mod 只存哈希（MHW 那本字典也只解出 5 个 RE6 名字），所以名字由插件自己保存
（`blender/material_names.py`，`core/hashes.LEARNED`）：
- 每次导入 .mod / .mrl 前，先学习当前 .blend 里用过的名字（网格名 `__<名字>`、模型网格用的 Blender 材质、mrl 材质的 `Mrl_Name`），即 MHWME 的 TODO；
- 学到的、导出时用到的、在 Material Name 里输入的名字都写进 `config/re6_model_editor/material_names.json`，之后的会话导入同样的哈希时直接显示名字
  （代替 mod3 的名字表）；
- 在 mrl 面板改 Material Name 时，同一模型里用旧哈希的网格（名字后缀）和预览材质跟着改名，名字换了哈希也一样，导出的 .mod 和 .mrl 始终对得上；
- Mrl Tools 里的 **Resolve Material Names**：学习当前文件的名字，并把所有仍显示 `MAT_<hash>`、但哈希已知的网格、预览材质、mrl 材质换成名字。
测试：`tools/blender_material_names_test.py`（10 项，用 nativePC_mod 的 pl0600：四个材质正是 Shinano_body / costume / face / hair）。

**剪贴板（RE6 扩展）**：Copy / Paste 也支持 ccl 球体和胶囊体（选胶囊的头尾等同于选胶囊），并能跨类型粘贴：按属性名匹配，目标有的才粘贴，
剪贴板没有的不覆盖。共有的属性：ctc 节点 `BoneColRadius` ↔ ccl `ColRadius`（单位都是厘米），球体 ↔ 胶囊的头部偏移和半径。节点的单项复制
（如 Mass）粘贴到没有该属性的对象时提示错误，不改任何东西。MHWME 的剪贴板只有 ctc。

**还没做**
- `loadUnusedTextures` / `loadUnusedProps`；包围盒；导出对话框的 `showMod3Options` / `showMrl3Options` / `showCTCCCLOptions` 折叠；游戏内实测。
- 是否把前缀改成与游戏无关的 `mt_*` / `MT_*`（以及 `core/games.py` 游戏注册表、集合上保存 `~GAME` / `~VERSION`）：见多游戏研究的建议，等你决定。

## 8. 需要你决定的事

| # | 问题 | 我的建议 |
|---|---|---|
| D1 | 网格/分组/骨骼/文件头属性改成自定义属性（与 MHWME 一致，删除 `RE6 Mesh` 面板），代价是失去带标签、有范围校验的界面 | 对齐。自定义属性是统一流程的一部分，且我们的字段本来就大多是“从文件复制”的未知项 |
| D2 | RE6 独有的材质条目管理算子（add / duplicate / delete / move / add_missing / refresh / assign_texture / load_mrl）：MHWME 没有 | 保留，但放进单独的子面板，不碰同构的部分 |
| D3 | 贴图缓存、chunk 路径列表、自动更新器 | chunk 路径列表对齐（游戏目录 + mod 目录的列表）；缓存暂不做（我们打包进 .blend）；更新器不做 |
| D4 | `mmtr` / `shaderHash` / `surfaceCoef` / `alphaCoef` 在 RE6 没有对应字段：占位、隐藏，还是把 MHWME 一侧改进（见第 9 节） | 见第 9 节 |
| D5 | 语义相反的默认值（`useBackfaceCulling`、`useBlenderMaterialName`）是否以 MHWME 为准 | 以 MHWME 为准，并在文档里写明 |

## 9. surfaceCoef / alphaCoef 与 RE6 的状态分解

**事实（已核对）**
- MHW 的材质条目（56 字节）：`typeID`、名字哈希、`mmtrHash`、`shaderHash`、`blockSize`，然后 `surfaceCoef`（2 字节）、`resourceCount`（u16）、`alphaCoef`（4 字节）、20 字节（被 MHWME 直接跳过，本地 29 个样本全为 0）、块偏移（u64）。
- RE6 的条目（60 字节）：类型、名字哈希、`size`，然后 **blend / depth / raster 三个状态哈希**、两个位字段字（命令数、alpha 测试、draw pass、延迟光照……）、4 个 blend factor 浮点（全 0）、动画块大小、偏移。
- 所以 RE6 能拆出 blend / depth / two sided，是因为 RE6 把它们直接放在材质头里，每个都是 32 位状态对象哈希，而且 albam 的名字表能把全部 44327 个官方材质里的哈希解出来（`BSSolid` / `BSBlendAlpha` / `BSAddAlpha`，`DSZTestWrite` / `DSZTest` / `DSZWrite`，`RSMesh` / `RSMeshCN`）。我最初是靠统计（三个字段分别只有 4、4、5 个取值，且和透明、双面贴图相关联）猜出含义的，名字表出来后才确认。
- MHW 头里没有这三个字段。

**假设（未验证）**
- MHW 把状态折进了主材质类型（MMTR 和 shader 哈希一一对应，MMTR 里按材质变体区分），剩下的位放在 `surfaceCoef` / `alphaCoef` 里，作用类似 RE6 的两个标志字。
- 证据很弱：本地只有 29 个 MHW 材质（来自 20 个 mrl3）。`alphaCoef[0]` 在 28/29 个里是 128，有一个是 180（bow 的 `ya029`）——像 alpha 测试参考值（RE6 的参考值 50–128 常见）；`alphaCoef[2]` 取 4、5、1、0；`surfaceCoef` 取 (0,17)、(2,17)、(84,17)、(12,17)、(0,225)。样本太少，不能下结论。

**验证方法**：需要完整的 MHW chunk（几千个 mrl3）。把 `surfaceCoef` / `alphaCoef` 的每个字节与 MMTR 名字、贴图组合（有没有透明贴图、是否双面）做相关统计，用 RE6 的字段作为先验。如果成立，可以把 MHWME 的两个字段拆成命名字段（alpha 测试、draw pass 等），回馈上游，这也正好是统一方案的第一个共享成果。

## 10. 建议顺序

1. 结构层（第 1、2、3 节）：`~TYPE`、算子和属性改名、标签页合并、自定义属性。纯机械，风险最低。
2. 材质数据模型（第 5 节）：Map / Sampler / Property 三个列表。
3. 预设（第 6 节）和贴图工具（第 7 节）。
4. 并行：游戏内实测，以及第 9 节的 MHW 数据验证。
