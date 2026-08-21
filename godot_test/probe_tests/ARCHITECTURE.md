# probe_tests 执行架构

实验规划（N01–N21 的目的、判据、决策影响）在 [README.md](README.md)。V1–V10 指令编号表也留在 README §0.2，因为每张 N 卡片都就近引用它。本文只规定**怎么跑、怎么判定、产物放哪**。

---

## 1. 三层架构

执行是同构的，判定是异构的。统一放在 kernel，异构放在 analyzer。

```text
Layer 1  Kernel     完全统一、薄
Layer 2  Analyzer   按 analysis.type 分派，8 类
Layer 3  Report     A 节由 artifact 生成；B 节人手写判断
```

```mermaid
flowchart TD
  Fixture[fixtures/NP-X] --> WS[临时 workspace]
  Derived[derived/NP-X@state patch] --> WS
  WS --> Kernel["Kernel: argv + cache_state + repeat"]
  Kernel --> Raw["RawResult: stdout/stderr/rc/signal/walltime/fsdiff"]
  Raw --> Norm["两级 signature 归一化"]
  Norm --> Local["local_signature 项目内身份"]
  Norm --> Noise["noise_signature 跨项目模板"]
  Noise --> Delta["Δ = Sig(P) − BG"]
  Local --> Delta
  Anno[annotations/NP-X.yaml 埋点表] --> Cls[归类]
  Delta --> Cls
  Cls --> Real["REAL 桶: 真信号保护名单"]
  Cls --> Clean["CLEAN 桶: 噪声过滤白名单"]
  Real --> Rep[reports 自动生成 A 节]
  Clean --> Rep
```

### Kernel 职责

1. 读取 N 的 YAML，校验 `depends_on` 与 `inputs_digest`。陈旧（STALE）默认拒绝重跑，须 `--force-stale`；上游 latest 缺失（MISSING）不可 force。Fake 跑不读写 `artifacts/latest/`。
2. 从不可变 Fixture 创建独立工作区；需要时应用 `derived/` patch。
3. COLD 步骤前删除工作区 `.godot/`；WARM 步骤前确认 V3 已成功。
4. 用 argv 列表启动进程，不经过 shell；独立进程组；timeout 时 `killpg`。
5. 记录 stdout / stderr / rc / signal / wall time / 前后文件快照。
6. 步骤级 hook 注入与撤销（哨兵、大文件、late class、UID、配置片段）。
7. finally：杀进程组、删工作区、校验原始 Fixture 仍 clean。

Kernel 不知道“实验赢了没有”。

### Analyzer 职责

按 YAML 的 `analysis.type` 消费 RawResult + 埋点表，写出 `evaluation.json`。

### Report 职责

从 artifact 生成 A 节表格与证据索引。B 节（判断、对后续实验的影响）仍人手写，见 [reports/README.md](reports/README.md)。

---

## 2. 目录

```text
probe_tests/
├── README.md
├── ARCHITECTURE.md          本文件
├── fixtures/{phase1,phase2}/  纯净项目，零实验元信息
├── annotations/{phase1,phase2}/  与 fixtures 一一对应的埋点表
├── derived/                 manual gate 产物（patch + provenance）
├── datasets/official-demos/
├── experiments/
│   ├── common/              defaults / command-profiles / signature-rules / taxonomy / fragments
│   ├── phase1/              N01–N10, N12–N14
│   └── phase2/              N11, N15–N21
├── runner/
│   ├── kernel/
│   ├── hooks/
│   ├── analyzers/
│   ├── report/
│   └── testing/             fake Godot 桩，先测判定逻辑再跑真二进制
├── reports/README.md
├── workspaces/
└── artifacts/
```

`fixtures/` 中不得放：实验说明、实验 YAML、临时日志、GUI 记录、错误 UID 的永久版本、`.godot/`、运行结果。埋点表在 `annotations/`，实验参数片段在 `experiments/common/fragments/`。

---

## 3. YAML schema

每个 N 的 YAML 只描述实验，不实现执行逻辑。`steps` 必须是有序列表。

| 字段 | 作用 |
|---|---|
| `id` | N 编号 |
| `phase` | phase1 或 phase2 |
| `fixture` / `dataset` | 输入材料 |
| `depends_on` | 前置实验及其输出文件 |
| `engine_profile` | Godot 路径、版本、build hash |
| `analysis.type` | 见 §4，决定用哪个判定器 |
| `analysis.*` | 该 type 的专属字段 |
| `manual_gates` | 人工 GUI；优先被 derived patch 替代 |
| `steps` | 严格有序步骤 |
| `cache_state` | COLD / WARM / PRESERVE |
| `command` | V1–V10 或 converter 指令；需要项目级扫描时写 `PROJECT_CHECK`，由 N08 导出的能力配置解析。字面 V1 永不被全局替换 |
| `repeat` | 重复次数。默认 3；N09 自身为 5。聚合策略由 analyzer 声明，不由 kernel 解释 |
| `hooks` | 步骤级 hook 列表 |
| `capture` | stdout/stderr/rc/time/diff/cache checksum |
| `cleanup` | 工作区删除和基准完整性检查 |
| `exports` | 输出给后续实验的 JSON |

`expect: real/clean/timeout/crash` **不再作为统一判定字段**。判定语义属于 `analysis.type`。

---

## 4. 八类 analyzer

| type | 判定逻辑 | 覆盖 |
|---|---|---|
| `capability_probe` | 只跑、只记录、导出 capability，无对错 | N15、N16 |
| `stability` | 纵向重复 + 横向跨项目 diff，导出两级 signature 规则 | N09 |
| `baseline_delta` | Δ = noise_signature 减法；TP/FP/FN 用 local_signature 对埋点表归类 | N01、N02、N05、N06、N07、N13 |
| `state_sequence` | 有序状态机，断言写在状态转移上 | N03、N12 |
| `liveness` | timeout / signal / crash 本身是观测量 | N10 |
| `transform_diff` | 转换前后按埋点逐条分类 | N11、N17、N18、N20 |
| `interference` | 并发组 vs 串行组的 cache manifest | N14 |
| `corpus_survey` | 数据集迭代 + 聚合统计 | N19、N21 |

新实验落在已有 type 里则只写 YAML；落不进去才新增 analyzer。

`repeat` 的聚合策略由 type 声明，例如：

- `stability`: `report_variance`（重复本身是测量对象）
- `baseline_delta` / `state_sequence`: `all_equal_required`
- `liveness`: `any_of_expected_outcomes`
- `capability_probe`: 通常 `repeat: 1`

---

## 5. Hook 契约

不为每个 N 写主程序。特殊行为进 hook。步骤结束必须撤销自己写入的文件，除非该步骤的目的就是留下变更（converter、降级）。

### `generate_sentinel`

V9 的哨兵**不常驻 fixture**。

```text
扫描 workspace 内 *.gd（N07 按需扩展到 .tscn / .tres / .gdshader）
排除自身与 __probe_ 前缀
写入 res://__probe_sentinel.gd
运行 V9
步骤结束删除
```

`__probe_` 前缀同时用于：V10 逐文件循环排除、signature 统计排除、fixture 洁净性校验。N04 分析根因时必须先扣掉哨兵 preload 坏文件产生的人造级联边。

### `generate_big_file`

YAML 只保存目标字节数、行数、最大单行长度。生成的 `big.gd` / `longline.gd` **必须按固定间隔插入可转换模式**（与 `small.gd` 同类的 `OS.get_ticks_msec()`、`.instance()`）。否则“文件未被改”与“converter 跳过”无法区分。

### 其他通用 hook

| hook | 用途 |
|---|---|
| `rename_file` | 去掉 `.disabled` 等 |
| `append_project_settings` | 注入 `experiments/common/fragments/` 片段；N01 的 res_loader 必须插到 `[autoload]` 且排在 `Config` 之前 |
| `corrupt_uid` | 在已有正确 UID 的基线上伪造 |
| `create_late_global_class` | 连目录一起创建 `late_class.gd` / `uses_late.gd` |
| `launch_concurrently` | N14：同步启动两个 V3 |
| `wait_for_manual_gui_step` | derived patch 不可用时的退路 |
| `snapshot_cache` / `restore_git_state` | cache 与工作区快照 |
| `apply_derived_patch` | 见 §7 |
| `downgrade_config_version` | N20：`config_version` 5→4，并记录降级 diff |

---

## 6. Artifact 布局

与 README §0.1 的四元组对齐，路径必须包含 cache 与 repeat，否则三次重复会互相覆盖：

```text
artifacts/<run-id>/<N>/<group_id>/<step-id>/<cache_state>/<repeat_idx>/
├── metadata.json          含 inputs_digest
├── argv.json
├── stdout.log
├── stderr.log
├── process-status.json
├── fs-before.json
├── fs-after.json
├── workspace.diff
├── cache-manifest.json
├── signatures.json        local_signature + noise_signature
└── evaluation.json

artifacts/<run-id>/<N>/<group_id>/cleanup.json
artifacts/<run-id>/index.md
```

路径必须含 `group_id`：同一 N 下多个 group 可以有同名 `step_id`（N09 两组都有 `v3-cold`），否则后写的会覆盖先写的日志。

`inputs_digest` 是该步骤消费的 fixture hash、annotation hash、derived patch hash、上游 export JSON hash、Godot build hash 的摘要。N09 重跑且 normalization profile 变化时，下游实验必须被标记为陈旧，不得继续使用旧结论。

---

## 7. Derived patch（manual gate 的可重放形式）

N02、N06 的 GUI 产物是纯文本，优先冻结为：

```text
derived/NP-ADDON@plugin-enabled/
├── patch.diff
└── provenance.yaml     Godot 版本 + build hash + 生成时间 + 人工确认记录

derived/NP-RESOURCE@uid-baseline/
├── patch.diff
└── provenance.yaml
```

Runner 应用前校验 `provenance.yaml` 的 build hash。不一致则退回 manual gate，要求重做并覆盖 derived。若 GUI 写入了二进制或不可移植内容，永久退回 manual gate。

N02 的核心判据本来就是“GUI 启用后 `git diff project.godot` 写了什么”——那份 diff 既是实验产物，也是可重放输入。

`provenance.yaml` 的 build hash 对的是当前 Godot 可执行文件，不是 git commit；空或不一致则重做 GUI 并覆盖 derived。derived 只收可 `git apply`、换工作区仍成立的文本 diff。GUI 之后若出现下列情况，derived 方案作废，永久 manual gate：

1. 二进制资源：`.res` / `.scn`、import 产物（如 `.ctex`），diff 不可读且跨构建不稳。
2. `.godot/` 私货：`imported/`、`filesystem_cache*`、`editor_layout.cfg`、class cache——含时间戳、窗口坐标、本机路径。
3. 绝对路径或平台痕迹：`/Users/...`、`C:\...`、CRLF、`.DS_Store`。
4. 关键状态未写入可提交文本：例如启用插件后 `project.godot` 无变更，单例只活在运行时或 `.godot/`。

本地判定（不必推远程）：对 fixture 副本建 git 基线，GUI 后看 `git status` / `git diff`；只把实验目标文件的文本变更冻进 `patch.diff`（N02：`project.godot`；N06：`.tscn` / `.uid`）。`git diff --numstat` 出现 `-	-	`（二进制）或有效变更全在 `.godot/` 则不可移植。用 `git apply --check` 在另一份干净副本上验证可重放。

---

## 8. Fake Godot（`runner/testing/`）

在跑真 4.7.1 之前，用可按脚本吐出预设 stdout/stderr/rc/signal/timeout 的假二进制，测试：

- kernel 的进程组终止与 finally 清理；
- 两级 signature 归一化；
- 八类 analyzer 的 `evaluation.json` 形状；
- `inputs_digest` 陈旧检测。

假二进制不得被任何“已确认”结论引用。

---

## 9. 两级 signature 与归类（实现备忘）

规格以 README §0.4 为准。实现时不可合并这两步：

1. 用 `noise_signature` 做 BG 减法（粗筛引擎噪声）；
2. 用 `local_signature` + `annotations/` 埋点表把 Δ 归入 REAL / CLEAN 桶。

CLEAN 桶 = 生产 verifier 的噪声过滤白名单；REAL 桶 = 禁止过滤的保护名单。桶内两条 signature 都要存。
