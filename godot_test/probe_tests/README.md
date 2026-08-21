
# Godot 4.7.1 Verifier 噪声与 3.x 自动迁移实验

> 本文档将实验重构为两个彼此隔离的阶段：
>
> 1. **第一阶段：Verifier 噪声排查**  
>    使用 Godot 4.7.1 原生 clean 项目和专项 probe 项目，确认命令语义、缓存、autoload、warning、UID、shader、退出码和非确定性等问题。
> 2. **第二阶段：官方 3.5/3.6 Demo 自动迁移评测**  
>    先验证 converter 能力边界，再对官方 Demo 执行自动迁移，统计迁移后残余问题的类型、数量和分布。

---

# 第 0 层 · 测量定义

## 0.1 一次测量 = 四元组，不是“跑一条命令”

缓存状态必须进入实验设计：

```text
Measurement = (project, command, cache_state, repeat_idx)

cache_state ∈ {COLD, WARM}
  COLD = rm -rf .godot/
  WARM = 先跑一次 V3 import 成功后的状态

repeat_idx ∈ {1..R}
  R = 3（全部实验的默认值）
  R = 5（仅 N09 自身，校准低频抖动需要更多样本，见 N09 卡片）
```

任何实验结论都必须记录：

- 项目或数据集版本；
- Godot 二进制版本和 hash；
- 完整 argv；
- 缓存状态；
- 重复编号；
- stdout；
- stderr；
- exit code；
- signal；
- timeout；
- wall time；
- 实验前后文件差异；
- 实验工作区是否成功清理。

**任何一条结论，如果没有标注 cache state，就不进入“已确认”结论区。**

## 0.2 指令编号

| ID | 命令 | 语义定位 |
|---|---|---|
| **V1** | `$GODOT --headless --path $P --check-only --quit` | 项目级 check？**语义待裁决（B3）** |
| **V2** | `$GODOT --headless --path $P --script res://X.gd --check-only --quit` | 单文件 check（官方文档唯一支持的用法） |
| **V3** | `$GODOT --headless --path $P --editor --import --quit` | 全项目导入 + class cache 重建 |
| **V4** | `$GODOT --headless --path $P --import --quit` | 不带 `--editor` 能否 import |
| **V5** | `$GODOT --headless --path $P --quit` | 真实运行时（autoload 会注册）→ **交叉验证信号源** |
| **V6** | `$GODOT --headless --path $P --quit-after 2` | 更硬的防挂死 |
| **V7** | V1/V2/V3 + `--verbose` | 是否给出结构化/依赖顺序信息 |
| **V8** | V1/V2 + `--debug` | **预期挂死或 signal 11 崩溃** |
| **V9** | `$GODOT --headless --path $P --check-only --script res://__probe_sentinel.gd --quit`，哨兵内 preload 全部脚本 | godot-proposals #1758 里社区给出的 workaround；如果 V1 是 no-op，这是 verifier 的候选实现。哨兵**不常驻 fixture**，由 `generate_sentinel` hook 在步骤开始时生成、步骤结束时删除（契约见 ARCHITECTURE.md） |
| **V10** | 对每个 `.gd` 循环跑 V2，N 次进程 | 保底方案，用来测单进程启动开销 × 文件数 |

## 0.3 `PROJECT_CHECK` 逻辑指令

B3 裁决完成后，由实验系统生成一个只读的命令能力配置：

```text
PROJECT_CHECK =
  V1，若 V1 被证实可以覆盖项目目标文件；
  V9，若 V1 无效但 preload 哨兵有效；
  V10，若 V1、V9 都无法提供完整覆盖。
```

注意：

- **不能全局删除或替换 V1。**
- 当 V1 本身是实验对象时，仍必须运行原始 V1。
- 只有后续实验中表达“需要项目级扫描”的逻辑步骤，才使用 `PROJECT_CHECK`。
- 这样既保留 V1/V9/V10 的对照实验，又避免后续实验错误地把 no-op 的 V1 当作 verifier。

## 0.4 噪声判定

### 0.4.1 两级 signature

归一化对每一条输出行产出**两条** signature，用途不同，不可互相替代：

```text
local_signature = sha1(kind | res_path | symbol | normalized_msg)
  保留 res:// 相对路径与符号名；抹掉行号、绝对路径、内存地址、耗时数值
  用途：项目内身份 —— 重复比较、级联去重、Agent 震荡检测

noise_signature = sha1(kind | msg_template)
  路径、符号名、数值全部占位符化，只留消息模板
  用途：唯一用途是 BG 减法
```

两级各自抹掉哪些字段，由 N09 的**纵向 + 横向**两个维度共同裁定（见 N09 卡片）。

因为 `noise_signature` 已经抹掉全部项目专属字段，**BG 不需要与探针同构**——CleanControl 可以一直保持极简。

### 0.4.2 BG 减法只作用于 noise_signature

对 CleanControl 建立背景集：

```text
BG(cmd, state) = {
  noise_signature(line)
  | line ∈ CleanControl 在 (cmd,state) 下的 stderr/stdout
  且 severity ∈ {ERROR, SCRIPT ERROR, WARNING}
}
```

对任意探针 P：

```text
Δ(P, cmd, state) = { line ∈ Out(P, cmd, state) | noise_signature(line) ∉ BG(cmd, state) }
```

**陷阱（必须写在实现里）**：模板化会把 `Identifier not found: Config`（N01）和 `Identifier not found: ProbeFoo`（N03）折叠成同一个 `noise_signature`。所以 **BG 减法只做粗筛，TP/FP 归类必须回到 `local_signature`**。这两步不可合并——一旦合并，只要背景里出现过任意一条同模板消息，N01 的真假阳性就会被整体减掉。

### 0.4.3 real / clean 是归类桶，不是事先标注

埋点表 `annotations/<phase>/<NAME>.yaml` 只记录"我在哪个文件埋了什么 + 怎么匹配"，**不预言引擎会报什么文案**（那是实测结果，进 artifacts）。real/clean 是 Δ 算完之后的归类结果：

```text
埋点表（事先）：我在哪个文件埋了什么 + 匹配线索
归类（事后）：Δ 中每条命中埋点 → REAL 桶；未命中 → CLEAN 桶
```

| 判定 | 定义 | 含义 |
|---|---|---|
| **TP** | 埋点被 Δ 中某条命中 | verifier 正常工作；该 Δ 条目进 REAL 桶 |
| **FN** | 埋点未被任何 Δ 条目命中 | verifier 盲区 |
| **FP** | Δ 中未命中任何埋点的条目 = CLEAN 桶的全部内容 | 噪声，必须过滤或规避 |
| **SEV-MISMATCH** | 输出存在但严重度与预期不同 | 可能误触发终止条件 |
| **BG-DRIFT** | CleanControl 自身在重复实验间不稳定 | 输出需要归一化 |

**两个桶累积起来就是第一阶段的最终交付物**：

- CLEAN 桶 = 生产 verifier 的**噪声过滤白名单**；
- REAL 桶 = **禁止过滤的保护名单**。

桶内每条必须同时存 `local_signature` 与 `noise_signature`：存前者才能回溯到具体埋点与具体文件，存后者才能把第一阶段的结论**泛化到第二阶段的官方 Demo**——那些项目的路径和符号名与探针完全不同，只有模板级 signature 能迁移。

### 0.4.4 对照优先级

同一个判定能用多种对照物时，按此优先级取：

```text
同项目内的 clean 埋点  >  最近邻探针  >  CleanControl (BG-base)
```

越靠前的对照物与被测项越同构，能排除的变量越多。这个设计原本已散落在各 N 卡片里当特例（NP-SYNTAX 的 `ok.gd`、NP-ALIEN 的 `ok.gd`、NP-AUTOLOAD 的 main.gd 走场景 vs `uses_autoload.gd` 孤立、N02 用 NP-AUTOLOAD 而不是 CleanControl 作对照），此处提为通则。

推论：**CleanControl 不需要为了"特征覆盖"变复杂**。它只承担 BG-base 与 N08 无错 rc 基线这两个职责，保持极简即可。

---

# 第 1 层 · 项目总体规划

## 1.1 原始探针项目总览

### A 组：Verifier 噪声探针

| 探针 | 目标噪声/issue | 必跑指令 | 必需缓存态 | 必需对照物 |
|---|---|---|---|---|
| **CleanControl** | 建立 BG 背景集；N08(无错时 rc)；N09 | V1,V2,V3,V4,V5,V6,V7 ×3 次 | COLD+WARM | — |
| **NP-SYNTAX** | **B3(V1语义裁决)**、N08(有错时 rc)、B9(启动不能证明正确)、错误文本格式 | V1,V2,V3,V4,V5,**V9**,V10 | COLD+WARM | CleanControl |
| **NP-AUTOLOAD** | **N01/B1** | V2,V5(+V1,V9 若存在) | **COLD+WARM 都必须** | CleanControl |
| **NP-ADDON** | **N02/B2、N10/C2** | V2,V5,**V8** | WARM | NP-AUTOLOAD |
| **NP-GLOBALCLASS** | **N03、N12-a** | V2,V3,V9 按 COLD→import→WARM 三态 | COLD→WARM 序列 | 自身三态序列 |
| **NP-CASCADE** | **N04/B6、N09/B8** | V2,V3,V9 ×3 次 | WARM | NP-SYNTAX `scene_bad.gd` |
| **NP-WARN** | **N05/B5、C1** | V1,V2,V3（× 项目设置开/关）+ V8 对照 | WARM | CleanControl |
| **NP-RESOURCE** | **N06/D2/D5、N12-b** | V3,V2,V9 按“改前/改后不import/补import”三态 | WARM | CleanControl |
| **NP-SHADER** | **N07/B7** | V2,V3,V5 | COLD+WARM | 同项目 `good.gdshader` |
| **NP-ALIEN** | **N13/G2** | V2,V3,V5 | COLD | 同项目 `ok.gd` |
| **NP-CONCURRENT**（选做） | **D4** | 同目录并发两个 V3 | WARM | 自身串行结果 |

### B 组：Converter 探针

| 探针 | 目标 | 指令 |
|---|---|---|
| **CP-BIGFILE** | **N11/A1/A4/C3** | `--validate-conversion-3to4`、`--convert-3to4`、带参数版 |
| **CP-TODO** | **A7**（TODOConverter3To4 语义标记） | `--convert-3to4` + diff |
| **CP-SHADER** | **A5/#63673** | `--convert-3to4` + diff |
| **CP-MUTATION** | **F2**（哪些变异算子转换器搞不定 → 决定基准集有效性） | `--convert-3to4` + 逐算子 diff |
| **CP-MINIMAL** | **N15/N16** 能力门与职责矩阵 | `--help`、`--validate-conversion-3to4`、`--convert-3to4` |

## 1.2 重要架构调整：项目是 Fixture，N 才是实验

原方案中的 NP/CP 项目继续保留，但其角色改为：

```text
NP/CP Project = 不可变实验材料 Fixture
N01...N21    = 独立、有序、可重复、可恢复的实验定义
```

因此：

- 不在每个 NP 项目中放 `_probe.yaml`；
- 不以“进入某个项目后，把 V1—V10 全部跑一遍”的方式执行；
- 每个 N 独立拥有一份实验配置；
- 一个 N 只执行与自己有关的命令；
- YAML 中的 `steps` 是严格有序列表；
- 每次实验从不可变 Fixture 创建独立工作区；
- 实验结束后删除工作区，而不是依赖在原目录中反向修改；
- 任何 GUI 操作、UID 生成、插件启用、文件改名或配置注入，都只能发生在该 N 的临时工作区。

---

# 第 2 层 · N01—N21 的阶段分类

## 2.1 第一阶段：Godot 4.7.1 Verifier 噪声排查

| 编号 | 主题 | Fixture | 合并的 3.1 issue |
|---|---|---|---|
| N01 | autoload 假阳性 | NP-AUTOLOAD | #120225 |
| N02 | addon 单例假阳性 | NP-ADDON | — |
| N03 | `class_name` 全局类缓存 | NP-GLOBALCLASS | — |
| N04 | 级联错误 | NP-CASCADE | — |
| N05 | warning/error 严重度 | NP-WARN | — |
| N06 | invalid UID 严重度 | NP-RESOURCE | — |
| N07 | shader verifier 盲区 | NP-SHADER | B7 |
| N08 | exit code、V1 语义、启动成功语义 | CleanControl、NP-SYNTAX | B3、B9 |
| N09 | 非确定性与归一化 | CleanControl、NP-CASCADE | — |
| N10 | `--debug` 挂死/崩溃 | NP-ADDON | — |
| N12 | patch 后缓存陈旧 | NP-GLOBALCLASS、NP-RESOURCE | — |
| N13 | C#/GDExtension 环境污染 | NP-ALIEN | — |
| N14 | 并发 import 污染 | CleanControl 的临时副本 | D4 |

## 2.2 第二阶段：Converter 和官方 Demo 自动迁移评测

| 编号 | 主题 | Fixture/数据集 | 合并的 3.1 issue |
|---|---|---|---|
| N11 | converter 跳过大文件或挂起 | CP-BIGFILE | A1、A4 |
| N15 | converter CLI 能力门 | 最小 3.x 项目 | E1 |
| N16 | ProjectUpgradeTool 职责和 CLI 边界 | 最小 3.x 项目、CP 项目 | A8、E2 |
| N17 | TODOConverter3To4 和 `instance()` 覆盖率 | CP-TODO | A7、A2 |
| N18 | shader 转换正确性和报告可信度 | CP-SHADER | A5 |
| N19 | 自动迁移后 import 成本 | 官方迁移快照 | C4 |
| N20 | converter 对 mutation 基准的评测泄漏 | CP-MUTATION | F2 |
| N21 | 官方 3.5/3.6 Demo 自动迁移残余问题分布 | 官方 Demo 数据集 | 第二阶段总体统计任务 |

## 2.3 3.1 issue 合并结果

| 原 3.1 条目 | 并入 |
|---|---|
| E1：`--convert-3to4` 是否存在 | N15 |
| A8/E2：ProjectUpgradeTool CLI 和职责边界 | N16 |
| A7：`TODOConverter3To4` | N17 |
| A2：`instance()→instantiate()` | N17 |
| A1+A4：大文件阈值和 hang | N11 |
| A5：shader 转换/谎报 | N18 |
| B3：V1 的真实语义 | N08 |
| B9：启动成功能否证明脚本全部正确 | N08 |
| B7：shader 在 import/scene-load 阶段是否可见 | N07 |
| C4：RealTarget 的 `--import` 耗时 | N19 |
| D4：并发 import 是否污染 `.godot/` | N14 |
| F2：mutation 是否会被 converter 自动修复 | N20 |
| #120225：ResourceFormatLoader/Saver 与 autoload | N01 |

---

# 第 3 层 · 实验配置与执行架构

目录结构、YAML schema、Runner / Hook / Analyzer 契约、artifact 布局、derived patch 与 fake Godot 桩，全部写在 [ARCHITECTURE.md](ARCHITECTURE.md)。

本层只保留与实验规划直接相关的约束：

- 每个 N 一份 YAML，`steps` 是严格有序列表；
- V1 保留字面形式；需要项目级扫描时写 `PROJECT_CHECK`，由 N08 能力配置解析；
- V9 哨兵 `__probe_sentinel.gd` 由 hook 步骤级注入，不常驻 fixture；
- 埋点表在 `annotations/`，与 `fixtures/` 路径一一对应；
- GUI 产物优先冻结为 `derived/<fixture>@<state>/patch.diff`；
- 默认 `repeat: 3`；N09 自身为 5。

---

# 第 4 层 · 第一阶段实验

## N01 · autoload 假阳性（#78587）

| | |
|---|---|
| **项目** | NP-AUTOLOAD（`Config` 注册为 autoload，`uses_autoload.gd` 调 `Config.ping()`，是孤立脚本） |
| **对照** | CleanControl（取 BG） |
| **指令** | `V2 on uses_autoload.gd` @COLD、@WARM；`V5`；若 V1/V9 可用也各跑一次 |
| **判据** | **FP 成立** ⟺ V2 输出含 `Identifier not found: Config` 或 `Class "Config" hides an autoload singleton`，**且** V5 正常打印 `Config.ping() called`（证明符号真实存在） |
| **必须同时记录** | 精确文案。因为原材料里两处文案不一致——我查到 **#78587 里两种文案都有**：`Compile Error: Identifier not found: singleton` 是**假阳性本体**，`Parse Error: Class "singleton" hides an autoload singleton` 是报告者为了对比故意加 `class_name singleton` 造出的**真错误**。所以 NP-AUTOLOAD 必须埋两个点（见源码 `shadow_config.gd.disabled`），**分别确认哪条是噪声、哪条不能过滤**——否则你的过滤器会把真错误一起吃掉 |
| **COLD/WARM 差异** | 报告者暗示与 `.godot` 缓存有关。若 WARM 下 FP 消失 → 你的 verifier 只需保证“每次 verify 前 WARM”，N01 自动消失，**这是最便宜的解法** |
| **决策影响** | ① FP 存在且 WARM 也在 → 必须实现 autoload 符号白名单过滤（解析 `project.godot` 的 `[autoload]` 段）+ V5 交叉验证；② FP 只在 COLD → verifier 强制 warm-up，省掉整个过滤器；③ **FP 不复现**（4.7.1 可能已合入修复 PR #110295）→ 直接删掉 N01，把省下的时间给 N02。**三种结果对应三套不同代码量，所以必须今天定。** |
| **并入的 3.1 issue** | **#120225**：自定义 `ResourceFormatLoader` / `ResourceFormatSaver` 子类在 autoload 注册为全局常量之前被编译，导致其引用的 autoload 报 `Identifier not found`。使用 `res_loader.gd.disabled` 作为独立子实验，不与主 FP 实验同时启用。**该 issue 的本质是注册顺序**，因此子实验必须由 hook 把 `res_loader.gd` 注入 `project.godot` 的 `[autoload]` 段、且**排在 `Config` 之前**；fixture 本身不预置这一条目。若只是把它当孤立脚本启用后跑 V2，测到的只是“孤立脚本引用 autoload”，与 `uses_autoload.gd` 完全重复，测不到注册顺序。 |
| **实验脚本/YAML 规划** | `N01.yaml` 使用 NP-AUTOLOAD 的独立副本，顺序为：COLD V2 → 建立 WARM → V5 运行时交叉验证 → WARM V2 → V1/V9 对照 → 启用 `shadow_config.gd.disabled` 子实验 → 恢复工作区 → `res_loader.gd.disabled` 子实验（`rename_file` 去掉 `.disabled`，再由 `append_project_settings` 把它注册为**排在 `Config` 之前**的 autoload，然后跑 V2/V5）。两个 disabled 文件不得同时启用。所有改名与配置注入只发生在临时工作区，结束后删除工作区。 |

---

## N02 · addon 单例假阳性（#111515）

| | |
|---|---|
| **项目** | NP-ADDON（`addons/dummy/plugin.gd` 在 `_enable_plugin()` 里 `add_autoload_singleton("DummySingleton", ...)`） |
| **对照** | **NP-AUTOLOAD**（不是 CleanControl！） |
| **指令** | `V2 on uses_addon.gd`、`V5`、`V8`（`V2 + --debug`） |
| **关键前置操作** | 必须用 GUI 打开项目并**启用一次插件**，然后 `git diff project.godot` 看它写了什么 |
| **判据（决策分叉点）** | **这是我认为原方案漏掉的最重要一步**：<br>• 若启用后 `DummySingleton` **出现在 project.godot 的 `[autoload]` 里** → N02 与 N01 **同根同源**，可以合并成一条过滤规则，你少写一个模块；<br>• 若**没出现**（纯运行时注册） → 过滤器必须去**扫描 addon 源码里的 `add_autoload_singleton` 调用**才能建白名单，这是显著更贵、更不可靠的实现 → 建议直接判定为**不过滤，走 escalate**，并在报告里写明理由 |
| **决策影响** | 决定“符号白名单”这个模块是 20 行还是 200 行，或者干脆不做 |
| **并入的 3.1 issue** | 无新增；#111515 的 `--debug` 崩溃部分由 N10 单独执行，避免 N02 的假阳性判定被崩溃污染。 |
| **实验脚本/YAML 规划** | `N02.yaml` 先复制 NP-ADDON 到临时工作区。优先消费 `derived/NP-ADDON@plugin-enabled/`（`patch.diff` + `provenance.yaml`）：build hash 与当前二进制一致则直接应用 patch，否则退回 manual gate（GUI 启用插件并退出，把新 diff 冻结回 derived）。Runner 在继续前记录 `project.godot` diff、插件启用状态和 autoload 段。随后按 V5 → V2 的顺序运行。N02 不运行 V8；V8 留给 N10。实验结束后删除整个工作区，原始 NP-ADDON 必须保持未启用插件的干净状态。若 GUI 写入了二进制或不可移植内容，derived patch 方案作废，永久退回 manual gate。 |

---

## N03 · `class_name` 全局类缓存冷假阳性

| | |
|---|---|
| **项目** | NP-GLOBALCLASS |
| **对照** | 自身的三态序列（这是**唯一不需要 CleanControl 的探针**，因为它比的是自己） |
| **指令序列（严格按序）** | `rm -rf .godot` → **T1**: V2 on `uses_class.gd` → **T2**: V3 import → **T3**: V2 again → 新建 `late_class.gd`（带新 `class_name`）+ `uses_late.gd` → **T4**: V2 on `uses_late.gd`（不 import） → **T5**: V3 → **T6**: V2 again |
| **判据** | • T1 报 `Identifier not found: ProbeFoo` 而 T3 干净 → **N03 确认**（冷缓存假阳性）<br>• T4 报错而 T6 干净 → **N12-a 确认**（新增 class_name 后必须重跑 import） |
| **决策影响（这条最贵）** | 直接回答架构问题②“每轮 patch 后必须重跑 import 吗”：<br>• T4 报错 → 只要 patch 触及 `class_name`/新增文件，**必须 import**，代价是每轮 +N 秒 → Day4/5 必须做**条件性 import 触发器**（diff 里 grep `class_name`/文件新增/资源变更）<br>• T4 干净 → import 只需一次，迭代成本被 check 主导 → 迭代速度提升一个量级，Agent 可以放心多轮试错 |
| **并入的 3.1 issue** | 无。 |
| **实验脚本/YAML 规划** | `N03.yaml` 将 T1—T6 写成不可并行、不可重排的有序步骤。`late_class.gd` 和 `uses_late.gd` 由通用 `create_late_global_class` Hook 在 T3 后创建。每一步都快照 `.godot/global_script_class_cache.cfg`。T6 完成后删除工作区，不在 Fixture 中永久保留 `late/` 文件。 |

---

## N04 · 级联错误淹没根因

| | |
|---|---|
| **项目** | NP-CASCADE（1 个坏根 + 5 个直接依赖 + 1 个二级依赖） |
| **对照** | **NP-SYNTAX 的 `scene_bad.gd`**（不是笼统的“NP-SYNTAX 单个孤立坏文件”）：它与 NP-CASCADE 的 `root_bad.gd` 内容完全一致，都是 `func f() -> void` 缺冒号，属于**同构错误**；`orphan_bad_parse.gd` 是另一种形态（`func broken(:`），不能拿来做分母。→ **放大倍数 = NP-CASCADE 行数 / `scene_bad.gd` 单文件行数** |
| **指令** | V2 on 每个 dep、V3、V9，各 ×3 |
| **判据** | 1 个根因产生 ≥ 2 条 error → 级联存在。同时提取级联专属文案：`Failed to load script "..." with error "Compilation failed"`、`Failed to compile depended scripts`、`ERROR: modules/gdscript/gdscript.cpp:3041` |
| **必须额外产出** | 一张“根因 error ↔ 症状 error”的**文案配对表**。判定规则草案：`at:` 位置指向**引擎内部路径**（`modules/gdscript/*.cpp`）的行 = 症状；指向 `res://` 的行 = 根因候选 |
| **决策影响** | ① 放大倍数决定 error triage 的必要性和收益（若 1:7，说明不做 triage 你的 Agent 有 86% 的注意力浪费在症状上）；② **症状 error 不得计入 error-signature 重试计数器**，否则一个根因就会把熔断阈值打满，把好仓库误标 needs-human；③ 决定 `VerifyReport` 需要一个 `root_cause_errors` 字段而不是扁平列表 |
| **并入的 3.1 issue** | 无。 |
| **实验脚本/YAML 规划** | `N04.yaml` 对 dep_1—dep_5、leaf、V3 和 V9 分别定义步骤，每一步重复三次。YAML 显式声明 NP-SYNTAX 的 `scene_bad.gd` 单根错误结果为外部对照（同构错误分母，不得用 `orphan_bad_parse.gd` 替代）。Runner 输出原始错误行数、去重 signature 数、根因候选数、症状数和放大倍数。N09 的非确定性规则必须先于本实验生成。 |

---

## N05 · warning 与 error 严重度混淆

| | |
|---|---|
| **项目** | NP-WARN |
| **对照** | CleanControl（BG 里本来就有多少 WARNING？） |
| **指令** | V1/V2/V3 × {默认设置 / 注入 `[debug] gdscript/warnings/enable=true` + `exclude_addons=true`}，另跑一次 V8 做对照 |
| **判据** | ① 默认设置下 warning 是否根本不出现（那 N05 在 CLI 下不成立，只是文档里的坑）；② 注入设置后是否以 `WARNING:` 前缀出现在 **stderr** 里；③ `exclude_addons` 是否真的屏蔽了 addon 内的 warning |
| **决策影响** | ① 若项目设置注入成功 → 你在**不触发挂死**的前提下拿到第二档信号，可以喂给 Agent-as-Judge 做“改坏了吗”的辅助证据（例如 patch 后新增 `UNUSED_PARAMETER` 说明可能删错了逻辑）——这是一个**免费的语义保真信号**，含金量很高；② 无论如何，**`severity != ERROR` 的行绝不进 reward 和终止条件**，否则 Agent 永远修不完（N06 同理） |
| **并入的 3.1 issue** | 无；V8 的稳定性结论引用 N10，不在 N05 内重新解释。 |
| **实验脚本/YAML 规划** | `N05.yaml` 先运行默认配置组，再通过 `append_project_settings` Hook 注入 `experiments/common/fragments/np-warn-debug.ini`，然后运行启用 warning 的配置组。V1 若被 N08 判定为不能执行项目扫描，仍保留字面 V1 对照，同时增加 `PROJECT_CHECK` 步骤。V8 只在 N10 尚未确认时作为一次性对照；已确认会挂死后可由依赖结果标记为安全跳过。 |

---

## N06 · `invalid UID` 是 warning 不是 error

| | |
|---|---|
| **项目** | NP-RESOURCE（手动把 `.uid` / `.tscn` 里的 `uid://` 改成伪造值） |
| **对照** | CleanControl（同结构但 UID 正确） |
| **指令** | V3、V2、V9 @WARM |
| **判据** | 出现 `invalid UID` 且 severity 为 WARNING → SEV-MISMATCH 风险确认；若它以 `ERROR:` 前缀出现 → **更糟**，说明你无法靠前缀区分，必须靠消息文案白名单 |
| **决策影响** | ① 若是 WARNING → 前缀过滤即可，成本 0；② 若是 ERROR → 必须维护“非阻塞性 error 文案白名单”，且这是 Day 4 熔断误触发的头号来源；③ 无论如何，**入队前对 workspace 跑一次 UID 规范化（`--import` 重建）**，把这类噪声在源头消掉 |
| **并入的 3.1 issue** | 无；ProjectUpgradeTool 的 CLI 和 UID 重建职责单独归入第二阶段 N16。 |
| **实验脚本/YAML 规划** | `N06.yaml` 优先应用 `derived/NP-RESOURCE@uid-baseline/patch.diff`（校验 build hash）。不存在或不一致则进入 manual gate：在临时工作区用 Godot GUI 打开并保存，建立正确 UID，把 diff 冻结回 derived。Runner 确认正确 UID 基线后，才允许通过 `corrupt_uid` Hook 将 UID 改为伪造值。顺序为正确基线 → 伪造 UID → WARM V2/V9 → V3 → 再次 V2/V9。禁止在 Fixture 中保存错误 UID，实验结束后直接删除工作区。 |

---

## N07 · shader 盲区（漏报，不是假阳性）

| | |
|---|---|
| **项目** | NP-SHADER（坏 `.gdshader` → `mat.tres` → 挂在 `main.tscn` 的 Sprite2D 上；另有 `shader_user.gd` 用 `preload` 引用它。同场景还有 `good.gdshader` → `good_mat.tres` 作为正确 shader 对照，用来区分“这个 shader 坏”与“任何 shader 都不报”） |
| **对照** | 同项目 `good.gdshader`（第一优先）> CleanControl |
| **指令** | V2 on `shader_user.gd`、V3、V5 @COLD+WARM |
| **判据（三种结果，价值递减）** | ① **全部静默** → 盲区确认，`.gdshader` 走 escalate 通道；② **V3 import 阶段报错** → 你多了一条免费信号，shader 可以进 reward，项目范围可以扩大；③ **V2 报 `Failed to load resource`** → `preload` 会把 shader 错误“抬”到 GDScript 解析期 → **这是个可利用的技巧**：由 `generate_sentinel` hook 注入一个 preload 全部 `.gdshader` 的 `__probe_sentinel.gd`，就把 shader 纳入了 check-only 的覆盖范围 |
| **决策影响** | 直接决定你的**验证边界声明**。面试里“我知道我的客观信号覆盖不到哪类错误，所以那类直接升级人工”比“我全都能修”可信一百倍。若命中 ③，则是一个可写进 README 的巧思 |
| **并入的 3.1 issue** | **B7**：shader 错误在 import/scene-load 阶段是否可捕获。A5 不并入本项，A5 是 converter 行为，归入第二阶段 N18。 |
| **实验脚本/YAML 规划** | `N07.yaml` 按 COLD V2 → COLD V3 → WARM V2 → WARM V5 → `PROJECT_CHECK` 的顺序执行。每一步分别标记是脚本解析、资源 import 还是场景启动信号。若 V2 的 preload 方案成立，实验只输出 capability，不直接改写其他 Fixture；后续由 command profile 决定是否生成 shader sentinel。 |

---

## N08 · exit code 可信度

| | |
|---|---|
| **项目** | **CleanControl（无错）+ NP-SYNTAX（有真错）+ NP-ADDON V8（被 kill）** 三者交叉 |
| **指令** | 全部指令都记 rc |
| **判据** | 填这张交叉表，只要出现“有错但 rc=0”→ rc 不可信 |
| **并入的 3.1 issue** | **B3**：`--check-only` 不带 `--script` 的真实语义；**B9**：启动成功能否证明脚本全部正确。N08 除 exit code 外，还负责产出 `PROJECT_CHECK` 的 V1/V9/V10 能力选择。 |
| **实验脚本/YAML 规划** | `N08.yaml` 先跑 CleanControl 无错基线，再跑 NP-SYNTAX 的 V1、V2、V3、V4、V5、V9、V10，最后引用 N10 的 timeout/crash 结果或执行受控的 V8。步骤不能按项目矩阵批量运行。YAML 导出 `exit_code_policy.json` 和 `command-capabilities.json`，后者供所有后续实验解析 `PROJECT_CHECK`。 |

| 场景 | 项目 | 有真错误 | 期望 rc | 实测 rc |
|---|---|---|---|---|
| 干净 | CleanControl | 否 | 0 | ? |
| 单文件真错 | NP-SYNTAX V2 | 是 | ≠0 | ? |
| 项目级真错 | NP-SYNTAX V1/V9 | 是 | ≠0 | ? |
| 纯假阳性 | NP-AUTOLOAD V2 | 否 | 0 | ? |
| 被 timeout kill | NP-ADDON V8 | — | 124/137 | ? |

若 rc 与错误无关联，则：

```text
VerifyReport.success 不能直接等于 exit_code == 0
```

必须区分：

- `CLEAN`
- `HAS_ERRORS`
- `INFRA_FAILURE`

---

## N09 · 非确定性

| | |
|---|---|
| **项目** | CleanControl（BG 稳定性）+ NP-CASCADE（多错误时的顺序稳定性） |
| **两个对比维度（缺一不可）** | • **纵向 = 同一项目重复运行**：只能发现内存地址、随机 ID、耗时数字这类**运行时随机**字段。<br>• **横向 = CleanControl 与 NP-CASCADE 在同一条指令下互相 diff**：绝对路径、`res://` 路径、符号名、行号在纵向重复中**完全稳定**，纵向永远发现不了它们；只有横向能暴露"这个字段随项目而变"。横向**不需要新增任何运行**——两个项目的日志本来都要采，横向 diff 是纯离线分析 |
| **指令** | 每条指令重复运行并逐次 diff（纵向）；再取同一条指令下两个项目的结果互相 diff（横向） |
| **重复次数** | **N09 自身 5 次**——它要"发现"低频抖动，3 次容易漏掉只在第 4、5 次才出现的字段；**其余全部实验 3 次**——它们只需"确认"已知字段稳定。N09 把这个 3 写进全局默认值 |
| **判据** | ① 行集合不同 → 内容非确定；② 集合相同顺序不同 → 顺序非确定；③ 出现随机 id/内存地址/耗时数字 → 需归一化；④ 横向 diff 中随项目而变的字段 → 必须在 `noise_signature` 里占位符化 |
| **决策影响** | 直接定死 §0.4.1 两级 signature 的**字段规格**：**纵向发现的字段两级都抹**（行号、绝对路径、内存地址、耗时数值）；**横向发现的字段 `local_signature` 保留、`noise_signature` 抹掉**（`res://` 路径、符号名）。其中**行号必须排除**（patch 会移动行号，含行号的 signature 会让“同一个错误”看起来像新错误，Day4 的震荡检测直接失效）。并且 `VerifyReport` 的 error 集合必须是**排序后的 set**，不是 list |
| **并入的 3.1 issue** | 无。 |
| **实验脚本/YAML 规划** | `N09.yaml` 是第一阶段最先执行的 N。先对 CleanControl 重复运行 5 次，判断背景输出是否漂移；再对 NP-CASCADE 的 V2/V3/V9 各重复运行 5 次，判断多错误顺序是否漂移；最后离线做两个项目的横向 diff。N09 输出初始 normalization profile（两级 signature 各自的字段抹除规则）与后续实验的 `repeat: 3` 默认值。N04 完成后可用同一批原始日志补充根因/症状归一化规则，不需要重新运行项目。 |

---

## N10 · `--debug` 挂死/崩溃（C1/C2）

| | |
|---|---|
| **项目** | NP-ADDON（**唯一需要跑 V8 的项目**） |
| **指令** | `V8 = V2 + --debug`，外层必须 `timeout 30` |
| **预期两种现象**（都要试着复现） | ① 论坛（4.6，2026-01）：掉进交互式 debugger 永久挂住 → 只能 `timeout` 强杀；② #111515（4.5，macOS ARM）：在 debugger 里按 `q` 后 **signal 11 崩溃**（backtrace 里出现 `Node3DEditor`/`FileDialog` vtable，说明 headless 下 debugger 引用了未初始化的编辑器对象） |
| **判据** | wall time ≥ timeout（挂死）或 rc = 134/139（崩溃）或 stderr 含 `handle_crash: Program crashed with signal 11` |
| **决策影响** | ① 证实 → `--debug` **永久禁入正式 verifier**，只作一次性探针；进程管理必须 `subprocess` + `start_new_session=True` + `os.killpg(SIGKILL)`（因为 Godot 会 fork/spawn 子进程，单杀 pid 无效）；② 顺带意味着 **warning 通道不能靠 `--debug`** → NP-WARN 的项目设置方案变成唯一出路 |
| **并入的 3.1 issue** | 无新增；保留 #111515 和 C1/C2 的原测试范围。 |
| **实验脚本/YAML 规划** | `N10.yaml` 只运行 V8，不与 N02 共享同一次工作区。Runner 必须创建独立进程组并设置 30 秒 timeout，记录是否 timeout、终止 signal、退出码和 crash 文案。无论进程状态如何，finally 阶段都要杀死进程组、确认无残留 Godot 子进程并删除工作区。 |

---

## N12 · patch 后缓存陈旧

| 子项 | 项目 | 触发物 | 见上文 |
|---|---|---|---|
| **N12-a** | NP-GLOBALCLASS | 新增/修改 `class_name` | 见 N03 的 T4–T6 |
| **N12-b** | NP-RESOURCE | 修改 `.tscn` 的 `ext_resource` 指向 | 三态：改前 V2 → 改后不 import 直接 V2 → 补 V3 再 V2 |
| **并入的 3.1 issue** | 无 | ProjectUpgradeTool 不并入本项，归入第二阶段 N16 | — |
| **实验脚本/YAML 规划** | `N12.yaml` 复用两个 Fixture，但为 N12-a 和 N12-b 分别创建工作区，不复用 N03/N06 的已修改目录。N12-a 可引用 N03 的 T4—T6 原始结果；若需要独立复验，则重复相同顺序。N12-b 顺序固定为正确基线 → 修改资源引用但不 import → V2/PROJECT_CHECK → V3 → 再次 V2/PROJECT_CHECK。最终导出“patch 类型 → 是否必须 import”的触发表。 | — | — |

两个子实验共同产出：

```text
import_trigger_policy:
  class_name_added: true/false
  gd_file_added: true/false
  scene_ext_resource_changed: true/false
  uid_changed: true/false
  ordinary_gd_body_changed: true/false
```

---

## N13 · C#/GDExtension 环境不匹配

| | |
|---|---|
| **项目** | NP-ALIEN |
| **对照** | CleanControl |
| **指令** | V2、V3、V5 @COLD |
| **判据** | 是否出现 `Unable to load .NET runtime` / `Can't open dynamic library` / GDExtension 加载失败，以及**这些错误是否会连带污染纯 GDScript 文件的解析结果** |
| **决策影响** | ① 若污染 → gateway **入队前硬拒收**（扫描 `*.csproj` / `*.gdextension` / `*.gdnlib`），并在报告里给明确理由，这是“识别我搞不定的”的产品交付物之一；② 若不污染 → 可以只跳过相关文件，扩大可服务仓库范围 |
| **并入的 3.1 issue** | 无新增；G2 已完整包含在本项。 |
| **实验脚本/YAML 规划** | `N13.yaml` 创建纯 GDScript 对照工作区和带 C#/GDExtension 的实验工作区，二者都从 COLD 开始。顺序为 V2 检查 `ok.gd` → V3 import → V5。重点不是只记录异类组件报错，而是比较 `ok.gd` 的 signature 是否被污染。实验结束后检查是否有编译产物、`.mono/`、`.godot/mono/` 或动态库缓存残留，并删除工作区。 |

---

## N14 · 并发 import 是否污染 `.godot/`（D4）

| | |
|---|---|
| **项目** | CleanControl 的同一临时工作区 |
| **对照** | 同一项目串行执行两次 V3 后的 `.godot/` 内容、hash 和后续 verifier 结果 |
| **指令** | 同目录并发启动两个 V3；另设串行控制组 |
| **判据** | 并发组出现错误、hang、崩溃、cache 文件缺失、cache hash 异常、后续 PROJECT_CHECK 输出异常，或与串行组产生不可解释差异 |
| **决策影响** | 污染成立 → workspace 分布式锁是刚性需求；不污染 → 锁仍可用于避免重复工作和控制 Godot 进程资源，但不能宣称其用于修复已证实的数据损坏 |
| **并入的 3.1 issue** | **D4**：并发 import 是否污染 `.godot/`，以及删除 `.godot/` 是否足以建立可靠冷态。 |
| **实验脚本/YAML 规划** | `N14.yaml` 先运行串行控制组并保存 cache manifest，再从同一个干净 Fixture 创建新的并发工作区，同时启动两个 V3。Runner 使用并发 Hook，同步启动时间并分别记录两个进程。完成后运行 PROJECT_CHECK，比较串行和并发 cache manifest。实验最后删除工作区。N14 必须排在 N09、N08、N03 和 N12 之后，因为它依赖稳定的 signature、命令能力和 cache 判定方法。 |

---

# 第 5 层 · 第二阶段实验

## N15 · converter CLI 能力门（E1）

| | |
|---|---|
| **目标** | 验证 Godot 4.7.1 官方二进制是否包含 `--validate-conversion-3to4` 和 `--convert-3to4`，以及参数语法 |
| **原 3.1 方法** | `$GODOT --help \| grep -iE "convert\|3to4\|upgrade"` |
| **判据** | help 中存在并可对最小 `config_version=4` 项目调用；不能只根据源码中存在对应代码就判定 CLI 可用 |
| **决策影响** | 存在 → 使用单二进制；不存在 → 使用明确固定版本的第二个 Godot 二进制；仍不可用 → 从 `renames_map_3_to_4.cpp` 自建 L0 |
| **并入的 3.1 issue** | **E1**。 |
| **实验脚本/YAML 规划** | `N15.yaml` 不修改项目，只采集完整 `--help`、版本、build hash 和最小项目调用结果。它导出 `converter-capabilities.json`，N11、N16、N17、N18、N20、N21 都依赖该文件。若能力门失败，后续实验必须明确标记为 BLOCKED，而不是静默跳过。 |

---

## N16 · ProjectUpgradeTool 的 CLI 与职责边界（A8/E2）

| | |
|---|---|
| **目标** | 判断 ProjectUpgradeTool 是否具有可自动化的 CLI 入口，以及它与 converter、`--import` 的职责边界 |
| **原 3.1 方法** | `--help` 搜 `upgrade`；若有则在 CP 项目上跑并 `git diff` |
| **判据** | 分别检查它是否修改 GDScript、UID、`.tscn`、`.tres`、资源路径或 import cache |
| **决策影响** | 有 CLI → 第二阶段流水线可使用 converter → upgrade tool → verifier；无 CLI → 以 `--import` 近似替代，并声明 UID/资源重保存边界 |
| **并入的 3.1 issue** | **A8、E2**。 |
| **实验脚本/YAML 规划** | `N16.yaml` 先读取 N15 的 capability，再在彼此隔离的 CP 项目副本上运行 converter、upgrade tool（若存在）和 `--import`。三组不能在同一工作区连续执行，否则无法归因。每组保存完整文件 diff，用于建立“工具 → 文件类型/变更类型”的职责矩阵。 |

---

## N11 · 转换器跳过大文件

| | |
|---|---|
| **项目** | **CP-BIGFILE（3.x 项目，不是 NoiseProbe）** |
| **说明** | 原方案把 `n11_huge.gd` 埋在 NoiseProbe 里是**分类错误**：这不是 verifier 噪声，是 converter 覆盖率问题，而且它需要 `config_version=4` 的 3.x 项目才能跑转换器 |
| **指令** | `--validate-conversion-3to4` → `--convert-3to4` → 带参数版 `--convert-3to4 20000 1000`（拉高 max_file_kb / max_line_size） |
| **判据** | `git diff --stat` 看 `big.gd` 是否被改；stderr 是否**明确报告跳过**还是**静默跳过**；转换器是否 hang（#63672 报 >500kb 失败，与文档的 4MB 阈值矛盾——**这个矛盾今天可以裁决**） |
| **决策影响** | ① 静默跳过 → 入队前必须做**文件大小预扫描**并显式报告“这些文件 L0 未覆盖”，否则 Agent 会面对一堆本该被机械改名的错误，白烧 token；② 参数可调且有效 → 直接拉高阈值，问题消失；③ 转换器 hang → **converter 调用也必须包 timeout + killpg**，不只是 verifier |
| **并入的 3.1 issue** | **A1+A4**：大文件阈值、文档与 issue 的阈值矛盾，以及转换器在大文件上 hang。 |
| **实验脚本/YAML 规划** | `N11.yaml` 属于第二阶段。它依赖 N15 已确认 converter 指令存在。Runner 从 CP-BIGFILE 创建两个独立工作区：默认参数组和提高阈值组，避免第一次转换结果污染第二次。大文件由 `generate_big_file` Hook 按配置生成，YAML 只保存目标字节数、行数和最大单行长度；生成的 `big.gd` / `longline.gd` **必须按固定间隔插入可转换模式**（如 `OS.get_ticks_msec()`、`.instance()`），否则“文件未被改”与“converter 跳过”无法区分，静默跳过判据失效。每次 converter 调用都必须有 timeout 和进程组清理。 |

---

## N17 · TODOConverter3To4 与 `instance()` 覆盖率（A7/A2）

| | |
|---|---|
| **目标** | 验证 converter 对无法安全迁移的调用是否插入 `TODOConverter3To4`，并测量不同 `instance()` 形态的转换覆盖率 |
| **原 3.1 方法** | CP-TODO 中放置 `move_and_slide_with_snap`、`yield`、Tween API，以及变量、preload、表达式三种 `instance()`；转换后 diff 并搜索 `TODOConverter3To4` |
| **判据** | 每个埋点分类为：正确转换、TODO 后保留旧值、完全未动、错误转换 |
| **决策影响** | TODO 可作为机器可读待办队列；无 TODO 的语义残余必须交给 Judge；`instance()` 覆盖率低则考虑补充安全的 L0 规则 |
| **并入的 3.1 issue** | **A7、A2**。 |
| **实验脚本/YAML 规划** | `N17.yaml` 在转换前从 `annotations/phase2/CP-TODO.yaml` 读取全部埋点及匹配线索。converter 运行后，由 diff 分析器逐埋点归类，不仅执行全局 grep。YAML 中保存埋点 ID、源调用形态、预期类别和是否允许自动转换。实验结束删除工作区，结果导出为 `converter-coverage.json`。 |

---

## N18 · shader 转换正确性和报告可信度（A5）

| | |
|---|---|
| **目标** | 检查 `.shader` 是否正确迁移为 `.gdshader`、shader 语法是否更新、引用路径是否同步，以及 converter 是否谎报已转换 |
| **原 3.1 方法** | CP-SHADER：3.x 语法 `.shader` + `.tres` 引用 → 转换 → diff |
| **判据** | 检查文件扩展名、`hint_albedo` 等语法、`.tres` 引用和 converter stdout；报告成功但文件未正确修改即为报告不可信 |
| **决策影响** | converter 输出不可作为 checkpoint 时，必须以文件 diff 和后续 import/verifier 结果为准；shader 残余按 N07 的可检测边界处理 |
| **并入的 3.1 issue** | **A5/#63673**。 |
| **实验脚本/YAML 规划** | `N18.yaml` 在转换前保存 old.shader 和 mat.tres 的 hash、扩展名和引用关系，转换后同时进行内容、文件名和引用图比较。随后在独立副本中执行 V3 和 N07 已确定的 shader 检测路径，避免将 converter 正确性和 verifier 可见性混为同一判据。 |

---

## N19 · 自动迁移后 `--import` 真实耗时（C4）

| | |
|---|---|
| **目标** | 在官方 Demo 的已转换快照上测量 COLD/WARM import 成本 |
| **原 3.1 方法** | 在 RealTarget（转换后）上跑 V3，记录 wall time；COLD 与 WARM 各一次 |
| **判据** | 按项目、文件数、资源数、总大小记录 cold import、warm import、重复方差和失败率 |
| **决策影响** | 若 import 成为迭代主导成本，则需要条件性 import、预热 cache 快照或 workspace 级缓存复用 |
| **并入的 3.1 issue** | **C4**。 |
| **实验脚本/YAML 规划** | `N19.yaml` 不直接修改官方源仓库，而是消费 N21 生成的只读 converted snapshot。每个 Demo 分别建立 COLD 和 WARM 工作区，至少重复三次。COLD 每次从无 `.godot/` 的快照开始；WARM 必须从一次成功 V3 的 cache snapshot 开始。结果按 Demo 和资源规模归一化。 |

---

## N20 · mutation 是否被 converter 自动修复（F2）

| | |
|---|---|
| **目标** | 确定哪些反向变异算子会被 converter 自动复原，避免把 L0 能力错误计入 Agent 修复率 |
| **原 3.1 方法** | 对同一份健康 4.x 文件逐算子生成变体，各跑一次 converter，比较是否复原 |
| **判据** | 每个算子标记为 `RESTORED_BY_CONVERTER`、`PARTIALLY_RESTORED`、`SURVIVES` 或 `CORRUPTED` |
| **启动前置条件（否则 N20 跑不起来）** | CP-MUTATION 的基线是健康 4.x 项目，`project.godot` 为 `config_version=5`，而 converter 可能**只接受 `config_version=4`**。因此 mutation hook 必须包含一个 **`config_version` 降级步骤**（5 → 4，连带 `.tscn`/`.tres` 的 `format` 字段），并且**这个降级本身要记为实验的一部分**：降级是否被 converter 接受、降级有没有引入额外 diff，都必须留证。若降级后 converter 仍拒绝该项目，N20 标记为 BLOCKED，不得静默跳过 |
| **决策影响** | 被 converter 修复的算子从 Agent 主基准中剔除或单列为 L0 组；只有 surviving mutation 才作为 Agent 的主要考题 |
| **并入的 3.1 issue** | **F2**。 |
| **实验脚本/YAML 规划** | `N20.yaml` 为每个 mutation operator 创建独立工作区，绝不在同一工作区叠加多个变异。每个工作区的步骤顺序固定为：`config_version` 降级 → 记录降级后基线 hash → 施加单个变异算子 → converter → 比较。YAML 只声明 operator ID、输入基线、预期变更和比较策略；具体变异与降级由通用 mutation Hook 完成。转换后同时比较源码、解析结果和语义标记，防止“文本未完全复原但已经被 converter 部分修复”被误分类。 |

---

## N21 · 官方 3.5/3.6 Demo 自动迁移残余问题分布

| | |
|---|---|
| **目标** | 对选定的官方 Godot 3.5/3.6 游戏 Demo 执行自动迁移，统计 converter 之后仍然存在的问题 |
| **输入** | 固定 tag/commit/hash 的官方 Demo；每个 Demo 保留来源 URL、版本、文件树 hash、文件数和资源规模 |
| **转换流程** | 原始快照 → converter → 可用时执行 N16 确认的 upgrade tool，否则执行标准化 import → 第一阶段已确认的 verifier 流程 |
| **对照** | 官方对应 4.x Demo 只能作为弱参考；不能默认认为它与 3.5/3.6 版本逐文件一致 |
| **统计单位** | 项目、文件、原始错误行、归一化 signature、根因簇、converter TODO、未处理文件、人工确认的语义问题 |
| **判据** | 所有残余问题必须归类；无法自动判断的问题进入 `UNCLASSIFIED_NEEDS_REVIEW`，不能静默丢弃 |
| **决策影响** | 得到真实的残余错误分布、RAG 语料权重、Agent 修复优先级、预估成本和支持边界 |
| **实验脚本/YAML 规划** | `N21.yaml` 以 Demo manifest 为输入，每个 Demo 创建独立转换工作区。转换完成后先冻结 converted snapshot，再由 N19 和 residual verifier 各自消费副本。不能在同一个已转换目录上连续运行多个会修改文件的实验。YAML 记录转换前后文件树、converter 输出、TODO、跳过文件、verifier 结果和最终人工分类。 |

### N21 分类体系

#### A. Converter 行为

- 正确转换；
- 部分转换；
- 插入 `TODOConverter3To4`；
- 明确跳过；
- 静默跳过；
- 错误转换；
- 报告成功但文件未变化；
- timeout；
- crash；
- 产生破坏性文件修改。

#### B. Verifier 阶段

- parse error；
- compile error；
- import/resource error；
- invalid UID warning；
- shader error；
- startup/runtime error；
- warning；
- verifier false positive；
- verifier false negative；
- infrastructure failure。

#### C. 根因类别

- API rename；
- 方法签名变化；
- 参数顺序变化；
- `instance()` / scene 实例化；
- `yield` / `await` 时序；
- Tween 重构；
- 生命周期变化；
- 节点或属性改名；
- signal/connect API；
- scene/resource 序列化；
- UID；
- shader；
- autoload/addon；
- C#/GDExtension；
- 二进制资源；
- converter 缺陷；
- 4.0→4.7 版本漂移；
- 其他待人工确认。

#### D. 每条残余记录字段

```text
demo_id
source_version
source_commit
godot_build_hash
path
file_type
raw_message
normalized_signature
severity
phase
root_cause_category
version_drift_bucket
converter_touched_file
converter_todo_present
verifier_command
cache_state
repeat_count
is_root_cause
is_cascade
auto_fixable
needs_judge
needs_human
```

---

# 第 6 层 · 正确的实验执行顺序

P1-0 / P2-0 是环境与 fixture 校验，不是 N。依赖未完成或 `inputs_digest` 过期时，下游标记为 BLOCKED，不得静默跳过。

| 序号 | N | 依赖 | 该实验产出的决策 | 影响哪些下游 |
|---|---|---|---|---|
| P1-1 | N09 | — | 两级 signature 字段规格；后续默认 repeat=3；BG 是否漂移 | 第一阶段全部、N04 根因归一化 |
| P1-2 | N08 | N09 | `PROJECT_CHECK`=V1/V9/V10；exit code 可否当 success；V5 仅交叉验证 | 所有需要项目扫描的 N |
| P1-3 | N03 | N08, N09 | COLD/WARM 是否有效；新增 class_name 是否必须 import | N01, N12, 条件性 import |
| P1-4 | N01 | N08, N03, N09 | autoload FP 是否存在；WARM 能否规避；是否要 `[autoload]` 白名单 | N02 过滤策略 |
| P1-5 | N02 | N01 | addon 单例是否写入 `[autoload]`；是否与 N01 同根 | 符号白名单实现成本 |
| P1-6 | N10 | N02 fixture，独立工作区 | `--debug` 是否禁入；是否必须 killpg | N05 是否跑 V8；N08 回填 INFRA rc |
| P1-7 | N04 | N09, N08, NP-SYNTAX/`scene_bad.gd` | 级联放大倍数；症状是否计入重试 | VerifyReport.root_cause_errors |
| P1-8 | N05 | N08, N10, N09 | warning 如何采集；是否进 reward/终止条件 | 正式 verifier 严重度策略 |
| P1-9 | N06 | N08, N09 | invalid UID 严重度；是否要文案白名单 | 入队前 UID 规范化 |
| P1-10 | N12 | N03, N06 | import 触发表 | 每轮 patch 后是否 V3 |
| P1-11 | N07 | command profile, cache, severity | shader 盲区还是可抬升 | 验证边界 / sentinel |
| P1-12 | N13 | N08, N09 | C#/GDExtension 是否污染 GDScript | 入队硬拒收规则 |
| P1-13 | N14 | N09, N08, N03, N12 | 并发 import 是否损坏 cache | workspace 锁的理由 |
| P2-1 | N15 | — | converter CLI 是否存在 | N11, N16–N21；失败则 BLOCKED |
| P2-2 | N16 | N15 | 流水线是 converter→upgrade→verifier 还是 converter→import→verifier | N21 标准步骤 |
| P2-3 | N11 | N15 | 大文件阈值、静默跳过、hang | 入队预扫描；converter timeout |
| P2-4 | N17 | N15 | TODO 是否可解析；instance() 覆盖率 | Agent 待办队列 / L0 规则 |
| P2-5 | N18 | N15, N07 | shader 转换与报告是否可信 | 必须以 diff 为准 |
| P2-6 | N20 | N15 | 哪些 mutation 被 converter 复原 | Agent 主基准算子 |
| P2-7 | N21-A | N15, N16 | 冻结 converted snapshot | N19, N21-B |
| P2-8 | N19 | N21-A | import 是否为迭代主导成本 | 条件性 import / cache snapshot |
| P2-9 | N21-B | N21-A + 第一阶段策略 | 残余问题分布与支持边界 | RAG / Agent / 人工升级 |

---

# 第 7 层 · Fixture 与埋点表

Fixture 实物是唯一真相源，位于 `fixtures/phase1/` 与 `fixtures/phase2/`。本文不再抄录源码。

埋点表与 fixture 路径一一对应，位于 `annotations/phase1/` 与 `annotations/phase2/`：只描述“埋了什么 + 怎么匹配”，不预言引擎文案。

实验参数片段（如 N05 的 warning 配置）在 `experiments/common/fragments/`，不进 fixture。

GUI 产物在 `derived/`，见 [ARCHITECTURE.md](ARCHITECTURE.md) §7。

---

# 第 8 层 · 清理、恢复与隔离规则

## 8.1 不在原 Fixture 上直接实验

所有实验都使用：

```text
immutable fixture
    ↓ copy/worktree
temporary workspace
    ↓ ordered experiment
artifacts
    ↓
delete temporary workspace
```

这比在同一项目中反复 `git checkout` 更可靠，因为：

- `.godot/` 可能不受 git 管理；
- GUI 可能写入隐藏文件；
- C# 可能产生 `.mono/`；
- import 可能产生 `.godot/imported/`；
- 插件可能修改 `project.godot`；
- converter 可能重命名文件；
- crash 后可能留下锁文件或临时文件。

## 8.2 每个实验必须执行的清理检查

实验完成后，Runner 必须确认：

- Godot 进程组已退出；
- 无残留子进程；
- 临时工作区已删除；
- 原 Fixture git 状态干净；
- 原 Fixture 文件树 hash 未变化；
- artifacts 不位于 Fixture 内；
- 下一个 N 不会继承上一个 N 的 `.godot/`；
- manual gate 产生的文件只存在于临时工作区。

## 8.3 失败时也必须清理

即使出现：

- timeout；
- signal 11；
- converter hang；
- Python 异常；
- 人工取消；
- assertion failure；

也必须进入统一 finally 清理流程。

---

# 第 9 层 · 最终报告结构

```text
report/
├── environment.md
├── command-capabilities.md
├── phase1/
│   ├── confirmed-noise.md
│   ├── not-reproduced.md
│   ├── verifier-blind-spots.md
│   ├── exit-code-policy.md
│   ├── import-trigger-policy.md
│   └── signature-policy.md
├── phase2/
│   ├── converter-capabilities.md
│   ├── converter-coverage.md
│   ├── demo-migration-summary.md
│   ├── residual-distribution.csv
│   ├── residual-distribution.md
│   ├── import-performance.md
│   └── unsupported-boundaries.md
└── evidence/
    └── artifact-index.md
```

每个结论只能处于以下状态之一：

- `CONFIRMED`
- `NOT_REPRODUCED`
- `INCONCLUSIVE`
- `BLOCKED`
- `NEEDS_MANUAL_REVIEW`

“已确认”区必须引用：

- run ID；
- N 编号；
- step ID；
- log 文件；
- Godot build hash；
- cache state；
- repeat 数；
- 判定依据。

---

# 最终设计结论

1. **NP/CP 项目不再是实验执行单元，而是不可变 Fixture。**
2. **N01—N21 才是独立实验单元，每个 N 有自己的有序 YAML。**
3. **N09 最先执行，用于建立输出稳定性和归一化规则。**
4. **N08 紧随其后，用于裁决 V1/V9/V10 和 exit code。**
5. **不能简单地把全部 V1 文本替换为 V9；应由 `PROJECT_CHECK` 逻辑别名解析。**
6. **N11 从第一阶段移入第二阶段，因为它测试的是 converter，而不是 verifier。**
7. **A5 也不再混入 N07：N07 测 verifier shader 盲区，N18 测 converter shader 行为。**
8. **所有 GUI、UID、插件和文件修改只发生在临时工作区；可重复的 GUI 产物冻结为 derived patch。**
9. **官方 3.5/3.6 Demo 的转换结果先冻结为只读快照，再分别用于性能实验和残余问题统计。**
10. **最终指标必须同时覆盖解析/编译正确性、converter 残余和语义级待办；“解析清零”不能等同于“迁移完成”。**
11. **判定走 `analysis.type` 分派的 8 类 analyzer；执行 kernel 统一，判定不塞进同一个 expect 字段。**
12. **V9 哨兵由 hook 步骤级注入 `__probe_sentinel.gd`，不常驻 fixture。**
13. **Signature 分两级：`local_signature` 做项目内身份，`noise_signature` 只用于 BG 减法；real/clean 是归类桶不是事先标注。**