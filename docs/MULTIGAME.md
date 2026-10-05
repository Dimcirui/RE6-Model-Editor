# 多游戏支持：RE Mesh Editor 怎么做，我们该怎么准备

来源：对 RE Mesh Editor（NSA Cloud）和 MHW Model Editor 源码的通读（报告全文在会话的临时目录里，这里只留结论）。

## RE Mesh Editor 的做法

- 它只在**同一个引擎内**多游戏（RE Engine）：所有游戏共用 `.mesh.<版本>`、`.mdf2.<版本>`、`.tex.<版本>`，**游戏由文件扩展名里的版本号决定**。
- 五张表把版本号、内部排序号、游戏名互相映射（`file_re_mesh.py:69-172`）；格式差异是读写代码里的 `if version >= VERSION_X`；顶点布局大多读文件自己的声明。
- 全局的 `Active Game` 下拉在 MDF 工具面板里（`scene.re_mdf_toolpanel.activeGame`），决定预设文件夹、贴图版本和默认扩展名；预设放在 `Presets/<GAME>/*.json`。
- 新增一个游戏要改约 10 个文件、12 张表，同一个“游戏 ↔ 版本”的事实重复了至少 9 处——这是它最大的弱点。
- `~TYPE` 值与游戏无关（`RE_MESH_COLLECTION`、`RE_MDF_COLLECTION`、`RE_MDF_MATERIAL`），命名空间 `re_mesh.*`、`re_mdf.*`、`re_tex.*`。
- 集合上只存了 `~TYPE` 等少数属性，游戏和版本**没有**存在集合上（导出时靠文件扩展名），所以往返时会丢掉游戏信息。

## MHWME 和我们

- MHWME 完全是 MHW 专用（`.mod3` / `.mrl3`，头版本 237），没有多游戏机制；它的 `~TYPE` 带游戏前缀（`MHW_MOD3_COLLECTION` …）。
- MT Framework 的扩展名里**没有版本号**（RE6 `.mod` 是 v211，MHW `.mod3` 是 v237），REME 的“扩展名 = 游戏”不能照搬；要靠文件头（魔数加 u16 版本）识别，并让用户显式选游戏。
- 三种 tex 格式共用魔数 `TEX\0`，贴图转换必须按当前游戏分派。
- 我们的数据模型和 MHWME 已经同构（map / sampler / property 三个列表），`Mod_*` 自定义属性已经是中立名字。主要冲突点是：`.dds;.tex` 文件处理器两边都会注册，
  同时安装时会弹出处理器选择，所以标签必须不同。

## 建议的架构（如果决定为合并做准备）

1. `core/games.py`：一个 `GAMES` 注册表，每个 `GameInfo` 有 `id`、`label`、`engine`、`mod_ext`、`mrl_ext`、`tex_ext`、`mod_versions`、
   游戏根目录名、单位矩阵、预设目录、能力开关；再加 `sniff_mod(data)`。所有表由它派生，同一个事实只写一次。
2. 按游戏拆格式代码：`core/formats/re6/{mod211, mrl, tex, vertex, cb_layouts, model_io}`，`core/model.py` 保持与游戏无关；`importer.py` 通过驱动对象调用，不直接 import `mod211`。
3. 在 mod / mrl 集合上保存 `~GAME` 和 `~VERSION`，导出时优先读它。
4. mod 工具面板加 `activeGame`，游戏路径条目加游戏字段；只有一个游戏时隐藏。导出对话框用 `game` 枚举，不用扩展名枚举。
5. 所有 `~TYPE` 判断走 `C.is_mod` / `C.is_mrl` / `C.is_mat`，它们接受别名集合（`RE6_*`、`MT_*`、`MHW_*`）。
6. 如果决定改中立名字：`MT_MOD_COLLECTION`、`MT_MRL_COLLECTION`、`MT_MRL_MATERIAL`、`mt_mod.*`、`mt_mrl.*`、`mt_tex.*`、`Scene.mt_mod_toolpanel`、
   `Object.mt_mrl_material`、标签页 `MT Mesh`；用 `load_post` 迁移旧名字。`Mod_*` 自定义属性保持不变。
7. 一个 `.tex;.dds` 文件处理器，按游戏分派。预设一开始就按游戏分文件夹（`Presets/RE6/*.json`，带 `presetVersion` 和 `Game` 字段）。
8. 把硬编码的 `nativePC`、`Converted_RE6_*`、`RE6 …` 换成 `GAMES[...]` 字段和格式化字符串；每个游戏的能力集（权重数、标志）放进 `GameInfo`，不要放进 Blender 层。

## 现状

目前只做了与 MHWME 的结构对齐（见 `MHWME_ALIGNMENT.md`），以上 1 到 8 都**没有做**。前缀改名（第 6 条）会让已有的 `.blend` 失效，需要你决定。
