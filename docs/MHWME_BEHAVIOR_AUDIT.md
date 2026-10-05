# 和 MHWME 的行为审计（2026-10-03）

> 范围：只看**行为**——同一个用户操作，两个插件会不会给出不同结果。不改代码。
> 对应计划：`docs/PLAN_MHWME_BEHAVIOR_AUDIT.md` 第 1 步。确认后再进第 2 步。
> 缩写：`MH` = MHWME `modules/…`；`RE` = 我们 `re6_model_editor/blender/…`。

## 0. 怎么做的，哪些验证了

- 三份并行审计（mod/骨骼、mrl/贴图/路径、ctc/ccl），每份逐行读两边源码，按 5 个维度（真相来源、查找规则、传播规则、导出范围、默认值与失败行为）列差异。
- **我自己抽查核对过的行号**（读了源码，和审计报告一致）：
  `exporter.py:64-82`（`Mod_Bone_Id` 优先、无重复检查、重名时静默取最小空闲 id）、`common.py:181-186`（`bone_fn_id` 同样属性优先）、
  `exporter.py:509`（`int(k[len(K_GROUP):])` 不在 try 内）、`exporter.py:415-425, 450-456`（导入网格固定顶点格式、`selectedOnly/visibleOnly` 过滤）、
  `mrl_objects.py:85-103`（`find_mrl_collection` 最后退到"文件里任意一个 mrl"）、`mrl_objects.py:526-540` + `operators.py:18-34`（Add Missing 最后退到 `mods[0]`）、
  `materials.py:100-140`（贴图精确路径和按文件名两遍的搜索顺序）、`importer.py:195-215`（`save_game_path` 每次导入都写）、
  `ctc_operators.py:312-352`（重命名链骨骼逐个 `old in o.name` 替换、不含 ccl 对象）、`ctc_io.py:50-66`（少于 2 个节点的链被丢弃）、
  `ctc_properties.py:305-311`（bit 8 被清掉）、`ctc_operators.py:378` + `ctc_properties.py:178`（`alignBoneDirection` 没有任何读取）、`core/ctc.py:66-82` 和 MH `file_ctc.py:161-163`（新链默认值不同）。
- **其余条目是审计员读代码得出的，我没逐条复核**，表里标"（未复核）"。
- **全部没有在 Blender 里运行过**；凡涉及游戏内效果的都标"游戏内未验证"。
- 新增了一个只读数据核对：`tools/dup_bone_ids.py` 扫描全部原版 .mod 的骨骼 function id 是否重复（结果见 A1）。

## 1. 为什么之前的"对齐审计"漏了

`docs/MHWME_ALIGNMENT.md` 把下面这些写成"有意保留的差异"，只写了**为什么不同**，没问**这个不同会让哪些操作的结果不一致**：

| 文档里的"有意差异" | 没写的行为后果 | 本审计里的条目 |
|---|---|---|
| `Mod_Bone_Id/Index/Radius` 为无损往返而保留 | 属性压过骨骼名，名字不再是真相来源 | A1 A2 B3 |
| 导入网格固定顶点格式 `Mod_Mesh_VertexFormat` | 多出来的 UV/顶点色/影响数被静默丢弃 | B1 |
| 保留 `re6_tan` | UV 或形状改动后切线过期 | B5 |
| 导出失败返回 `CANCELLED` | 偏好默认值在下次对话框丢失（未复核） | C6 |
| 不做 `allowDuplicateBoneNames` | 重复 id 被静默接受，比 MH 的报错更糟 | A2 |
| 不做 texture cache | 同路径贴图永远复用旧图 | C5 |
| `useBackfaceCulling` "跟随 MH" | MH 里该选项根本没被读，前提不成立 | C8 |

"78%"这个数字在项目文档里找不到来源，不再引用。

## 2. 审计表（按风险排序）

风险：**高** = 会产生错误文件或静默改坏数据；**中** = 特定操作下结果和预期不一致；**低** = 小差异或更好的差异。

### A. 真相来源（名字 vs 隐藏属性）

| # | 主题 | MH（文件:行） | RE（文件:行） | 有理由吗 | 风险 | 建议 |
|---|---|---|---|---|---|---|
| **A1** | 骨骼 function id 来源 | **只看名字** `MhBone_NNN`：`mod3_functions.py:490-509`、`ctc/file_ctc.py:285,359`、`ctc_properties.py:927`、`ccl_properties.py:179,199,208` | **属性 `Mod_Bone_Id` 优先**，名字只是兜底：`exporter.py:73-82`、`common.py:181-196`、`ctc_io.py:46,58`、`ccl_io.py:44,57`、`ctc_functions.py:261-263` | 为"名字不规范的骨骼"设计，原则上说得通；但没有一致性检查，且我们自己的报错文案说"改骨骼名"（`export_errors.py:147-153`），属性存在时这句话是错的 | **高**。F2 把 `RE6Bone_100` 改成 `RE6Bone_120`：ctc/mod 导出仍写 100，导入 id 120 的 ctc 会挂到别的骨骼上。这就是你这次遇到的"名字一样、导入却错"的根因 | **P0-1：名字是唯一来源**（见第 3 节的重复 id 事实和做法） |
| **A2** | 重复 id / 自动分配 id 静默 | `.001` 后缀的骨骼默认报错，开 `allowDuplicateBoneNames` 才放行并在控制台警告：`mod3_functions.py:493-509,552-565` | 无重复检查；`exporter.py:76` 的正则没有 `$`，`RE6Bone_050.001` 被当成 50；id 被占用或名字不规范时**静默取从 0 开始的最小空闲 id**（`:76-82`）；`model.py:449-455` 重映射表第一个骨骼赢 | 不合理 | **高**。Ctrl+J 合并骨架或 Shift+D 复制骨骼后两根骨骼同 id，第二根对 ctc/动画不可达，没有任何提示；新骨骼可能取到某个 LMT 在用的低 id，被动画误驱动（游戏内未验证） | 加错误 `DuplicateBoneId`、`UnnamedBone`，取消静默分配（或只在名字合格时才允许，并警告） |
| **A3** | 混合场景：属性 id 和名字 id 冲突 | 无此问题（只有名字） | 导入骨骼 `Mod_Bone_Id=150`，用户再加一根名为 `RE6Bone_150`、无属性的新骨骼：mod 导出里新骨骼被静默改号（`exporter.py:76-82`），ctc 导出却写名字里的 150（`bone_fn_id`），**mod 和 ctc 对不上** | 不合理 | **高**（A1 的推论） | 随 A1 一起消失 |
| A4 | 镜像骨骼 | x≈0 平面自指；否则必须互指且位置镜像，否则保持默认：`mod3_functions.py:511-529` | `Mod_Bone_Symmetry`（名字字符串）不校验，悬空名字回落成"自己的镜像"（`exporter.py:97-99`）；位置不重新核对 | 为往返无损，部分合理 | 中。删除/手动改名镜像骨骼后，伙伴骨骼声称自己是自己的镜像，而不是"无"(255) | 悬空 → 255 并警告 |
| A5 | 骨骼半径 `Mod_Bone_Radius` | 每次导出重算 | 属性存在就原样写，不重算（`exporter.py:104-105`、`model.py:437-441`）；`Mod_Bone_Length` 声明了但没读写 | 往返无损；游戏内是否影响未验证 | 中 | 取 max(存储值, 重算值)，或网格变了就重算 |
| A6 | 材质哈希来源（mod 侧） | 默认取物体名 `__` 后第一段并去掉第一个 `.` 之后（`split("__",1)[1].split(".")[0]`）；开 `useBlenderMaterialName` 取材质名；两种模式互相兜底：`mod3_functions.py:642-676` | 默认模式 `rsplit('__',1)`（最后一个 `__`），只去 `.NNN`（`exporter.py:164-173`）；材质名模式 `re6_hash` 属性**压过**材质名（`:178-186`）；无互相兜底，缺 `__` 报 `NoMaterialOnSubMesh` | 严格部分合理；`re6_hash` 优先不合理 | 中。开"用 Blender 材质名"时改材质名不起作用；名字里含 `__` 时两边哈希不同 | 统一一条规则，exporter 和 mrl 工具共用；`re6_hash` 与名字不符时警告 |
| A7 | 材质表 `Mod_Header_Materials` | 每次导出按网格重建（`blender_mod3.py:489-496`） | 以存储列表为种子，只追加（`exporter.py:471`、`:403-406`），用不到的哈希永远留着；`relink`（`material_names.py:144-165`）不更新它 | 往返无损 | **高**（未复核后果）：mrl 改名后 mod 表里留着旧哈希，mrl 里已无此条目；游戏是否容忍"表里有哈希但 mrl 没有"**未验证** | 导出时剔除没网格用的哈希，或至少警告；`relink` 同步更新 |
| A8 | 链/碰撞的顺序 | 按 `all_objects` 顺序，不解析名字（`blender_ctc.py:172-213`） | 按物体名里的数字排序（`ctc_functions.py:86-91`、`ccl_functions.py:120-124`），新链取最小空闲编号可能插到中间 | 确定性比 MH 好，但名字不该是键；链顺序是否影响游戏**未验证** | 中 | 创建时在物体上存序号，名字只做兜底 |
| A9 | 节点上的陈旧数据 `Ctc_Node_BoneIdHigh/Translation`、`Ccl_EndBone` | 无 | 存在节点/球体物体上；改 `BoneName` 约束指向别的骨骼后，旧值会写给新骨骼（`ctc_functions.py:328-332`、`ccl_functions.py:129`） | 往返无损（高字节只出现在 pl0620） | 低 | 骨骼名对不上时忽略这些值 |

### B. mod 的导出范围与数据保留

| # | 主题 | MH | RE | 有理由吗 | 风险 | 建议 |
|---|---|---|---|---|---|---|
| **B1** | 导入网格的顶点格式被固定 | 每次导出按网格实际 UV/顶点色/权重重选格式：`mod3_functions.py:678-748` | `part.fmt = Mod_Mesh_VertexFormat`（`exporter.py:420-421`）；多余 UV、顶点色、影响数被丢，只发 WARNING（`:288-294,349,354-355`） | 为字节级往返，部分合理；但没有逃生口 | **高**。导入 1 影响数的刚性网格再刷第二块骨骼权重，导出成功但只保留最强一块；加第二套 UV 直接消失 | 数据装不下固定格式时自动换格式（并警告）或报错，不要默默截断 |
| B2 | 组包围球 | 写所有 `Mod3_Group_NNN`，不生成：`mod3_parser.py:449-454` | 存储值优先，无属性的组才生成（`model.py:601-611`）；球与顶点是否相容不检查；`int(k[len(K_GROUP):])` 遇到非数字键会抛 ValueError（`exporter.py:509`，已复核） | 自动生成比 MH 好 | **高**（我们刚被这个坑过）：把头部变形或改物体名 `Group_5` 对上旧球，存储球不覆盖顶点，整组被剔除 | 导出前校验存储球是否覆盖该组顶点（用 `group_sphere` 同一参考系），不覆盖就重算并警告；包住 `int()` |
| B3 | 选择/可见过滤丢掉影子副本 | 无影子网格 | 影子副本在隐藏集合（`importer.py:299-307`），`selectedOnly/visibleOnly` 过滤把它们丢掉（`exporter.py:450-456`，已复核），渲染遮罩仍保持"有独立影子副本" | 不合理 | 中。"只导出选中/可见"得到不投影的模型（游戏内未验证） | 影子副本跟随其可见伙伴，或警告 |
| B4 | 影子模式 | — | `NONE` 只改遮罩，导入的 shadow-only 部件仍写出；`REGENERATE` 又加一份，导入的旧影子不删，重复（`exporter.py:494-504`） | 不合理 | 中 | NONE 删除 shadow-only；REGENERATE 先删旧 |
| B5 | 切线 | 每次导出重算 `calc_tangents()`：`blender_mod3.py:466` | 顶点数不变就沿用存储的 `re6_tan/tsign`（`exporter.py:337-347`） | 往返无损 | 中。翻转/展开 UV 或同顶点数变形后法线贴图在游戏里着色错 | 对 `_unchanged_rows` 之外的顶点重算 |
| B6 | 权重阈值 | `MIN_WEIGHT=0.001`：`blender_mod3.py:553-561` | `> 0.0`（`exporter.py:124`、`model.py:223`） | 否 | 中。第 9 个 0.0004 影响数导致 `MaxWeightsPerVertexExceeded`，MH 里不会；第 5 个极小权重把网格推到 8 槽格式 | 先剔除 <1e-3 并归一 |
| B7 | `Limit Total` 默认值 | 8：`mod3_operators.py:371` | 4（`mesh_tools.py:250`），但报错文案叫用户点这个按钮解决"8 影响数"错误（`export_errors.py:201-207`） | 否 | 中 | 默认改 8 |
| B8 | 导出范围 | 有 LOD 子集合时只导 LOD 集合里的网格（`blender_mod3.py:402`） | 集合内所有网格；LOD 集合外的网格用过期的 `Mod_Mesh_LOD`（`exporter.py:480-481`） | 宽松且合理 | 低（拖出 LOD 集合会悄悄换 LOD） | 文档化 |
| B9 | 错误分两阶段 | 一次收集所有错误弹一个窗：`blender_mod3.py:657-660` | 三次 raise（`exporter.py:459-460, 488-489, 490-507`） | 不影响正确性 | 低 | 以后再说 |
| B10 | 其他合理差异 | 导出当前姿势、未权重顶点静默写 0、先清场景再解析 | 强制 REST 姿势导出、未权重顶点报错、先解析再清场景 | 合理，更严 | 低 | 保持 |
| B11 | `ModExportExclude` | MH 设置 `Mod3ExportExclude` 但从不读 | 我们读 `ModExportExclude`，导入器从不设置 | — | 低 | 文档说明 |

### C. mrl / 贴图 / 路径

| # | 主题 | MH | RE | 有理由吗 | 风险 | 建议 |
|---|---|---|---|---|---|---|
| **C0** | 导入路径有没有 arc 回退 | — | **没有**。`materials.py` 只读磁盘；`core/arc.py` 的 `GameIndex`/`find_name` 在插件里**零调用**（审计员 grep `GameIndex|game_index|\barc\b|find_name|find_game_dirs|loose_roots|game_paths|save_game_path`，我复核了 `importer.py`、`materials.py` 的相关段）。残留：`importer.py:193` 文档字符串"then in the game archives"、`i18n.py` 的 `.arc` 条目、`prefs.py:26-28` 说"也用于材质库"（实际 `find_mrl` 不用）已过时 | 规则成立 | 低（风险是将来被误接回去） | 从发布包删 `GameIndex`（留在 tools/），清理过时文案 |
| **C1** | 贴图搜索顺序 | 先 mrl 自己所在根目录的精确路径 → mrl 目录按文件名 → 偏好里的 chunk 列表精确路径，**从不递归**：`blender_mod3_mrl3.py:90-127` | 精确路径：对话框目录 → **偏好 `texture_dir`** → 模型目录 → `loose_roots`（模型自己的根在这里，排在偏好之后）；**按文件名那遍**（`_walk`）顺序反过来：`walk_folders` 先、用户目录最后，`setdefault` 先到先得（`materials.py:100-140`，已复核）；递归遍历 | 递归按名字匹配对"自定义目录的 mod"有用；顺序没理由 | **高**。偏好 `texture_dir` 指向解包的原版目录时，原版同路径贴图盖过 mod 自己的；平铺的用户目录输给某游戏路径子树里的同名文件 | 顺序：对话框目录 → 模型自己的根 → 模型目录 → 偏好目录；按名字那遍只搜用户给的目录；记录每张图取自哪个目录 |
| **C2** | mrl 的查找 | 只认 `<mod 名>.mrl3`，或用户指定路径，找不到警告：`blender_mod3.py:31-103` | `<名字>.mrl` → 第一个非空的 `<名字>_0..3.mrl`（`materials.py:59-78`）；主文件损坏会无提示落到变体；集合永远叫 `<base>.mrl`（`mrl_objects.py:215`），导出默认文件名丢掉 `_N`（`mrl_io.py:106`） | RE6 确有 `_N` 变体（`pl0603_0/1/2.mrl`），猜测有用，但是猜测 | 中。导入 `pl0603_1.mrl`、编辑后导出成 `pl0603.mrl`，覆盖/加载错文件 | **[问用户]** 保留猜测则必须：报告里写出读了哪个文件，保存真实文件名作为导出默认名 |
| **C3** | 活动 mrl 的解析 | 一个指针 `mrl3Collection` 管所有操作：`mrl3_operators.py:61,133`；缺失材质只打印，从不添加：`blender_mod3_mrl3.py:199-205` | `find_mrl_collection` 链：活动物体所在 → 活动模型的 mrl → `tp.mrlCollection` → **文件里任意一个 mrl**（已复核）；其他操作用 `tp.mrlCollection`，两处可能指向不同集合；`Add Missing` 的模型回落到 `active_model_collection` → `tp.modCollection` → `mods[0]`（已复核），会把别的角色的材质抄进这个 mrl；`import_data` 对 mod 用到而 mrl 没有的材质**即使读了真 mrl 也加模板条目**（`mrl_objects.py:206-230`）；`createCollections=False` 时 `root=scene.collection`，扫描全场景网格（`importer.py:275`） | 模板条目是便利；其余是猜测 | **高**（对应你看到的"导出 mrl 多出一堆无关材质"）。两个模型的场景里什么都不选，就会混材质，导出时没有任何察觉 | 统一"活动 mrl"解析（`tp.mrlCollection` 优先），去掉 `mods[0]`/任意 mrl 的猜测；Add Missing 找不到就报错；模板条目改为选项或按名字列出；拒绝 scene-root 情形 |
| C4 | 偏好里的游戏路径自动累积 | 只在路径不含 `nativepc` 时保存（即只存真正的 chunk 解包目录）：`blender_mod3_mrl3.py:179-182` | 每次导入都 `save_game_path(near[0])`，near[0] = 最近含 `nativePC` 的祖先，**mod 目录也会存**，之后永远是搜索根（`importer.py:198-200`） | 否 | 中。旧 mod 的贴图能满足之后别的导入（叠加 C1） | 不自动保存 mod 目录，只在用户显式操作时保存 |
| C5 | 贴图图像复用 | 每次导入的字典 + 磁盘缓存，有"重新加载缓存贴图"选项：`blender_mod3_mrl3.py:243` | 同 `re6_tex` 键的图像一律复用（`materials.py:147-150,180-182`），改过的贴图不会重载；DDS 写到 `bpy.app.tempdir`，不打包时 .blend 指向会消失的临时文件，下次导入复用坏图 | 对齐文档 D3 | 中 | 复用前检查文件存在/`has_data`；提供重载选项；不打包时警告 |
| C6 | 导出失败返回值/等级 | `FINISHED` | `CANCELLED`，且 `exportSettingsLoaded=True` 在成功前就设了（`operators.py:344,372`）；失败消息用 INFO 级（`mrl_io.py:180`、`operators.py:369`） | `CANCELLED` 不进撤销栈，合理 | 低-中 | 失败改 ERROR 级；`exportSettingsLoaded` 成功后才设（影响未验证） |
| C7 | mrl 导出范围 | `all_objects` 里所有 `MHW_MRL3_MATERIAL`，未知 mmtr 静默跳过：`blender_mrl3.py:137-157` | `entries()` 用 `mrl_col.objects`，**子集合里的条目被丢**（`mrl_objects.py:38-40`）；而 `export_textures`、预设、mod 导出用 `all_objects`，范围不一致 | 排序合理，丢子集合不合理 | 中。放进子集合的材质从 .mrl 里消失且无提示 | 用 `all_objects`，对没编号/不是条目的 `T_MAT` 警告 |
| C8 | `useBackfaceCulling` | 该选项**从未被读**，行 351 总是按 `surfaceCoef` 设置 | 选项关时强制所有缓存材质 `use_backface_culling=False`（`importer.py:323-325`） | 对齐文档 D5 的前提不成立 | 低（只影响预览） | 忽略选项保留数据驱动，或文档说明 |
| C9 | 传播缺口 | 改名不传播；F2 名字保留到 Reindex | `apply_order` 重写所有物体名，丢掉未 Reindex 的 F2 改名；`Delete` 调 `reindex()` 把待定改名变成哈希变化+relink；`Replace String` 只改映射列表，写出的 .tex 仍在旧路径（`mrl_objects.py:241-247,480,641-645`、`materials.py:513-518`、`tex_tools.py:101`） | 否 | 中 | `apply_order`/Delete 前先同步；贴图写出路径取自 mrl 绑定 |
| C10 | `Load MRL` 破坏性 | 无此操作 | 无确认地删除现有 mrl 集合（含用户编辑）：`operators.py:375-401`、`mrl_objects.py:210-212` | 否 | 中低（有撤销） | 确认对话框或把旧集合改名保留 |
| C11 | `relink` 后 mod 没同步 | — | mrl 条目改名时只改同名 mod 的网格/预览材质；mrl 没有同名 mod（如 `pl0603_1.mrl` 对 `pl0603.mod`）则完全不 relink（`material_names.py:144-165`） | 否 | 高→合并入 A7 | 见 A7 |
| C12 | 贴图搜索代价与诊断 | 不递归；每个缺失文件警告一次 | `_walk` 递归遍历模型目录和所有根，6 万文件上限只 break 内层循环；`Refresh` 每个物体新建 finder；缺失贴图只报数量（`importer.py:215`） | 否 | 低 | 缓存 finder；控制台列出搜索根和每个缺失路径 |

### D. ctc / ccl

| # | 主题 | MH | RE | 有理由吗 | 风险 | 建议 |
|---|---|---|---|---|---|---|
| **D1** | 导入时丢链 | `file_ctc.py:359-370`、`file_ccl.py:123-128` 同样丢（共有问题） | 缺骨骼的节点被跳过，剩下不足 2 个节点的链整条丢弃，只有 0 节点链用 `Ctc_Empty_Chains` 保留（`ctc_io.py:50-66`，已复核）；导出 `.ctc` 时同时覆盖旁边的 `.ccl`（默认 `exportCCL=True`，`ctc_io.py:140-142,233`）；不匹配骨骼只打印控制台 | 否 | **高（数据丢失）**。把 `pl0603.ctc` 导到缺骨骼的骨架上，编辑后导出，丢掉的链永远消失 | 被丢的链/碰撞保留为原始数据重新写出，或弹窗列出并在覆盖前警告 |
| **D2** | 重命名链骨骼有两套实现 | MH 拒绝任何已被占用的新名：`ctc_operators.py:1128-1135` | `ctc_operators.py:316-342` 逐个 `old in o.name` 替换；新 id 池排除自己链的骨骼，新旧范围重叠时（旧 100-103 → 新 101-104）物体名被改坏成 `…101.001` 再变 `…102.001`（已复核代码路径，**未用测试复现**）；`objs` 不含 `T_CCL_*`，ccl 对象名过期；永远写 `Mod_Bone_Id`，而 `bone_rename` 只在原来就有时写 | 否 | 中 | 让该操作改调 `bone_rename.rename_bones`（两套合一） |
| D3 | 新链默认值 | `CollisionAttrFlag=4, ChainAttrFlag=39`，damping 0.0，spring 0.01：`file_ctc.py:161-175` | `0 / 1 / 0.02 / 0.015`（`core/ctc.py:66-82`，已复核）；而设置碰撞标志对话框默认 `CollisionModelEnable=True`（`ctc_operators.py:695`） | 可能是按原版分布取的，但文档没写 | 中 | 文档写明，或和对话框对齐 |
| D4 | bit 8（VGround）导出被清 | 原样写 | `ctc_properties.py:309` 清掉；UI 复选框禁用（`ctc_operators.py:719`，已复核）。非玩家 ctc 是否有 bit 8 未验证 | 对玩家模型有依据 | 中-低 | 存储值带 bit 8 时警告 |
| D5 | 死选项 `alignBoneDirection` | 真的执行（`ctc_operators.py:1038-1068,1161-1162`） | 复选框画了、默认 True，**没有任何代码读它**（已复核） | 不执行合理（会改骨骼矩阵），默认开着的假选项不合理 | 低 | 删掉属性和复选框 |
| D6 | 更严的解析 | ccl 读取忽略头里的计数，按文件大小读：`file_ccl.py:117` | `core/ccl.py:52`、`core/ctc.py:115` 头计数和文件大小不符就拒绝 | 严格一些 | 低-中 | ccl 容忍读取并警告 |
| D7 | 缺骨骼时的报错文案与未捕获异常 | 只做正则检查 | 绑定骨骼已不存在 → 报 `IncorrectBoneNameFormat`（文案不对）；`check_ctc` 只验集合内的节点，`read_ctc` 走 `children` 会碰到集合外的坏节点 → TypeError/StopIteration，操作 CANCELLED 但没有错误窗（`ctc_functions.py:261-263,299-339`、`ctc_io.py:282-286`） | 更严合理 | 低 | 单独错误类型；检查覆盖走到的所有节点 |
| D8 | 预设列表 | 插件目录内 | 每次枚举重绘都 `addon_utils.modules()` + `os.walk` MHWME 目录（`ctc_presets.py:35-62`）；也是一处"读别的插件目录"的查找 | 可用 | 低（UI 卡顿，未测） | 缓存 |
| D9 | 其他（我们更好） | `glob.escape` 在含 `[ ] * ?` 路径上出错；合并目标无头时新建集合；嵌套 ccl 目标依赖面板指针 | 正则去后缀、复用目标、显式传集合 | — | — | 保持 |

## 3. 关键事实：原版里有没有重复的 function id？

`tools/dup_bone_ids.py`（新增，只读）扫描全部原版 arc 里的 .mod：**1708 个带骨骼的模型，其中 10 个有重复 id**。

| 模型 | 重复 id | 说明 |
|---|---|---|
| `data/event/face/pl0000/cs_pl0004`、`event/face/em5810/cs_em5811`、`event/face/sm6320/cs_sm6321`、`chara/em/em6511`、`chara/sm/sm1651` | 255 ×2 | 255 = "无 function id"，本来就不唯一 |
| `chara/sm/sm5008`、`sm5018`、`sm5061` | 22 ×2、23 ×2 | 道具/小物件 |
| `chara/em/em6552` | 254 ×2 | 敌人 |
| `chara/sm/sm1605/model/sm1605_09` | 0 ×2 | 道具 |

结论：
- **玩家角色（plXXXy）没有真正的重复 id**；重复只出现在 255（"无"）和少数 sm/em 对象上。
- 所以"名字是唯一来源"在玩家模型上直接成立。对要保留往返无损的非玩家模型，需要像 MH 那样用 `.NNN` 后缀表示重复 id（`RE6Bone_022.001` = 又一个 22）。
- 有 5 个模型含 id 255 的骨骼。现在导出器对 `fn > 254` 报 `IncorrectBoneNameFormat`（`exporter.py:83-84`），这些模型是否能无损往返要在第 2 步里一并确认（`roundtrip_model.py` 是直接走 `Model`，不经过 Blender 导出器，所以这条路径没被它覆盖）。

## 4. 建议修改清单（按顺序，等你确认）

**第 2 步 P0（会产生错误文件 / 数据丢失 / 违反你的规则）**

| 序号 | 内容 | 对应条目 | 要问你吗 |
|---|---|---|---|
| P0-1 | 骨骼 id 以名字为准：`bone_fn_id`、`collect_bones`、`ctc_io`、`ccl_io`、`bone_rename`、`ctc_operators`、`mesh_tools`、导入器都改；`.NNN` 后缀表示重复 id；加 `DuplicateBoneId` / `UnnamedBone` 错误，取消静默分配；修正 `IncorrectBoneNameFormat` 文案；`Mod_Bone_Id` 不再被读 | A1 A2 A3 D2 | 不用（你已明确要对齐） |
| P0-2 | 贴图搜索顺序和"按名字"那遍只搜用户目录；不自动保存 mod 目录 | C1 C4 | 不用 |
| P0-3 | 活动 mrl 解析统一，去掉 `mods[0]`/任意 mrl 的猜测；模板条目改选项；Add Missing 无目标就报错 | C3 | **要问**：模板条目导入时默认关还是列出名字 |
| P0-4 | mod 导出材质表剔除未用哈希（或警告），`relink` 同步；`re6_hash` 与名字不符警告 | A6 A7 C11 | **要问**：游戏是否容忍表里多余哈希未验证，剔除是否会破坏你的往返习惯 |
| P0-5 | ctc/ccl 导入丢链：保留原始数据或弹窗列出 + 覆盖前警告 | D1 | **要问**：选"保留重写"还是"弹窗警告" |
| P0-6 | 导入网格数据装不下固定顶点格式时自动换格式/报错；存储组球不覆盖顶点时重算并警告 | B1 B2 | 不用 |
| P0-7 | mrl `_0.._3` 猜测 | C2 | **要问**：保留（必须写出读了哪个文件，并保存真实文件名）还是完全对齐 |
| P0-8 | `loose_roots` / `game_paths`（只列磁盘子文件夹，不碰 arc）算不算"回退" | C0 | **要问** |

**第 3 步 P1**：B3 B4 B5 B6 B7、A4 A5 A8、C5 C6 C7 C9 C10、D3 D4 D5 D6 D7、C0 清理（删 `GameIndex`、过时文案）。

**第 4 步**：文档（`MHWME_ALIGNMENT.md` 把行为项拆出来重写，`CTC_CCL.md`）、i18n 检查、安装 + 重载、重打包（问版本号）。

## 5. 没验证的东西

- 全部没在 Blender 里运行；A2 的"Shift+D 复制骨骼会不会连自定义属性一起复制"没验证；D2 的重叠改名没用测试复现；
- 游戏是否容忍材质表里有多余哈希、新骨骼取低 id 是否被 LMT 误驱动、链顺序是否影响游戏、`影子副本丢失` 的游戏内效果，都未验证；
- 5 个含 id 255 骨骼的模型能否经 Blender 导出器往返，未验证。

## 6. 第 2 步进度（2026-10-03）

你的回答：①保留 `_0.._3` 猜测；②C3 没听懂（我按"读到真 mrl 时不再自动加模板条目"做，下面写了怎么回事）；③丢掉的链/碰撞"保留原样"（我理解为：保留成原始数据，导出时原样写回）；④`loose_roots`/`game_paths` 和 MHWME 对齐。

| 项 | 状态 | 做了什么 | 验证 |
|---|---|---|---|
| P0-1 骨骼 id 只看名字（A1 A2 A3 D2） | **已做** | `common.bone_name_id` / `bone_fn_id` 只读名字（`RE6Bone_NNN`，`.NNN` 后缀也认）；`Mod_Bone_Id` 删除（导入器不再写，没有任何代码再读）；导出器不再静默分配 id，名字不合格或带 `.001` 且没开选项 → `IncorrectBoneNameFormat`；新增导出选项 `allowDuplicateBoneNames`（和 MHWME 同名，偏好里有默认值）；报错文案已改；`Rename Chain Bones` 改调 `bone_rename.rename_bones`（修了新旧范围重叠的改名问题，ccl 对象名也会跟着改）；镜像"有无伙伴"的判断从 `Mod_Bone_Id` 改成 `Mod_Bone_Index` | 新增 `tools/blender_bone_id_test.py` 12 项全过（含：导入再导出，骨骼表的 id/父/镜像和原文件一致；F2 改名后导出 id 随之变；无 id 名字报错；`.001` 无选项报错、有选项两根都是 id 11；>254 报错；ctc 按名字导入）；`blender_bone_rename_test` 通过；`blender_ctc_preset_rename_test` 21/21（用原版 pl0600）；`roundtrip_model` 188/188 逐字节一致 |
| P0-2 贴图查找（C1 C4 C0） | **已做** | 去掉 `loose_roots`（不再枚举子文件夹）和递归按文件名搜索；顺序改成：对话框目录 → 模型自己的根 → 模型所在目录 → 偏好 `texture_dir` → 偏好里的游戏路径，按完整路径找；按文件名只在对话框目录、模型目录、偏好 `texture_dir` 里**不递归**地找；过时文案已改。`save_game_path` 保留（受偏好 `saveGamePaths` 控制，和 MHWME 一致） | `blender_panel_draw_test`、`blender_clipboard_errors_test` 29/29 通过；**没有用真实贴图做导入对比**（没验证） |
| P0-3 活动 mrl 解析（C3） | **部分** | `find_mrl_collection` 去掉了"第一个模型的 mrl"和"文件里任意一个 mrl"的兜底；`Add Missing Materials` 去掉了 `mods[0]` 兜底，没有明确的模型就报错；**导入 mod 时不再往 mrl 里自动加模板条目**，缺的材质只在报告和控制台里按名字列出，要加用 `Add Missing Materials`（这就是 C3 的意思：以前导入时，mod 用到而 mrl 没有的材质会被偷偷加成"普通角色"模板条目，之后被导出）；导出 mrl 的默认文件名用导入时的真实名字（`pl0603_1.mrl` 不再变成 `pl0603.mrl`） | 面板绘制测试通过；**导入后"未包含材质"报告没有单独测试**（没验证） |
| D1 丢链 | **已做** | ctc：少于两根骨骼匹配的链保留为"单链 ctc 数据"存在头部，导出时按原位置原样写回（旧的 0 节点链格式仍能读）；ccl：找不到骨骼的碰撞体存进 `Ccl_Dropped`，导出时写回；导入时用警告告诉你有几条 | 新增 `tools/blender_ctc_dropped_test.py` 7 项全过（pl0620：删掉第一条链的骨骼 + 一个碰撞体的骨骼 → 导入少 1 条 → 导出后链数 4/4、被丢的链逐字段相同、碰撞 4/4） |
| B2 的一半 | 已做 | `Mod_Group_*` 非数字键不再抛异常 | — |
| P0-4 材质表清理 / `relink` 同步 | **没做，要问你** | — | — |
| B1 固定顶点格式 / B2 存储球校验 | **没做** | — | — |

测试说明：
- 我把原版 `pl0600.mod/.ctc` 和 `pl0620.mod/.ctc/.ccl` 提取到会话临时目录用于测试。`blender_ctc_preset_rename_test` 在你的 `nativePC_mod` 版 pl0600 上会失败（你的 mod 用了 98 以后的大量 id，可用 id 池空了），不是代码问题。
- `blender_material_names_test`（2 项）、`blender_vertex_format_test`（3 项）在你现在的 pl0600 上有失败：前者要的 `FACE` 材质在你现在的 mod 里已经不存在，后者要 8 槽网格；两者**没有做改动前的对照**，我判断与本次改动无关，但没有证明。

### 6.1 你的第二轮回答（2026-10-03）

- 找不到骨骼的链 / 碰撞体：**直接丢弃，有警告就行**。已撤回上面"保留原样"的做法：不足两根骨骼的链、找不到骨骼的碰撞体不导入，导出的 ctc/ccl 里也没有；导入后用 WARNING 报条数（导入 ctc/ccl 的操作现在会把警告报给界面，不只是控制台）。`blender_ctc_dropped_test` 改成验证这个行为，通过。
- C3：不自动加模板条目，只留手动的 `Add Missing Materials`（已是这样）。
- mod 导出：材质表只写网格用到的材质哈希，没有网格用的剔除（保留原有顺序，网格的材质序号同步重排）。`tools/blender_material_table_test.py` 4 项通过（注入两个无用哈希，导出后消失，表和网格序号一致）。游戏是否容忍多余哈希仍未验证，但现在不会再写出去。
- 因此 P0-4 里"剔除"部分完成；`relink` 同步 `Mod_Header_Materials` 不再需要（导出时按网格重建）。
- **2026-10-05 撤回剔除**：游戏内验证了两件事。① 多余哈希没问题：能显示的 cs_pl0600 材质表里有 8 个 loose mrl 里不存在的原版哈希。② 剔除有害：重导出后脸部材质序号从 8 变成 0，过场里脸就消失了，恢复 9 项表后脸又出现（过场头部按**序号**找材质）。现在导出器原样写出存储的表，新哈希只追加在末尾；`blender_material_table_test.py` 改成验证这一点（5 项通过）。
