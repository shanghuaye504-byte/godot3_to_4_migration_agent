# Godot 4.7.1 Verifier 噪声与 Godot 3.x 自动迁移实验报告

> **文档性质**：结论记录。实验设计见 [../README.md](../README.md)，执行架构见 [../ARCHITECTURE.md](../ARCHITECTURE.md)。
>
> **三条填写规则**：
>
> 1. **这里只写结论和判据实测值。** 原始数据在 `artifacts/`，规程化中间结果在 `reports/<run-id>/<N>/<analyzer>/`，两者都**不往这里抄**。可复现性靠落盘，不靠在报告里重述。
> 2. **每条结论必须带状态标签与证据路径。** 没有日志支撑的推测不写进本文。
> 3. **每个实验只有一个「决策」栏**，写清它把 §5 的哪一项配置定成了什么。定不了就写清缺什么证据。

---

# 0. 标签

| 状态 | 含义 |
| --- | --- |
| `NOT_STARTED` / `RUNNING` | 尚未开始 / 正在执行 |
| `CONFIRMED` | 现象稳定复现，证据充分 |
| `PARTIAL` | 只确认了实验中的一部分现象 |
| `NOT_REPRODUCED` | 按计划执行后未复现 |
| `INCONCLUSIVE` | 结果不稳定或证据不足 |
| `BLOCKED` | 因环境、工具或上游依赖无法执行 |

可信度：`HIGH`（多次重复一致 + 对照正常 + 缓存态明确）、`MEDIUM`（日志完整但重复不足或依赖人工判断）、`LOW`（单次观察或无可靠对照）、`NONE`（尚无结论）。

---

# 1. 环境

## 1.1 元数据

| 字段 | 实测值 |
| --- | --- |
| 报告版本 | `0.2.0` |
| 最后更新 | `2026-08-22 00:05 +0800` |
| 执行人员 | `yy_catmax`（git: `shanghuaye504-byte <shanghuaye504@gmail.com>`） |
| 操作系统 / 架构 | `macOS 26.3.1`（Darwin 25.3.0）/ `arm64`，`sysctl.proc_translated=0` |
| Python | `3.13.9`（`/Users/yy_catmax/miniconda3/bin/python`） |
| Godot 可执行文件 | `/usr/local/bin/godot4` → `Godot.app/Contents/MacOS/Godot` |
| Godot 版本 / build hash | `4.7.1.stable.official.a13da4feb` / `a13da4feb`（二进制 sha1 `9fab64a7acbe2af2690e3ac7c3249b40363b76bb`） |
| 构建来源 | 官方构建（Developer ID `Prehensile Tales B.V.`，Gatekeeper `Notarized Developer ID`） |
| 环境预检 Run ID | `env-preflight-20260821-180807`（旧预检 `env-preflight-20260821-105347` 保留为历史） |

## 1.2 环境校验

证据目录：`artifacts/env-preflight-20260821-180807/`。

| 检查项 | 结果 | 状态 |
| --- | --- | --- |
| Godot 版本与 headless 冒烟 | `4.7.1.stable.official.a13da4feb`；CleanControl 副本 `--headless --quit` 退出码 0，stdout 含 `CLEAN_OK` | `CONFIRMED` |
| 二进制架构 | universal（`x86_64`+`arm64`），未走 Rosetta | `CONFIRMED` |
| macOS quarantine 不阻止执行 | 带 `com.apple.quarantine` 但 `spctl` 为 `accepted`；`--version` 与冒烟均 exit 0 | `CONFIRMED` |
| Fixture git 状态 clean | 99 个文件已入库，`git status` / `git diff` 空 | `CONFIRMED` |
| Fixture 中无 `.godot/` | 计数 1：`CleanControl/.godot/` 已被跟踪入库，不是冒烟写回的 | `PARTIAL` |
| artifacts 位于 fixture 外 | `artifacts/` 与 `fixtures/` 为兄弟目录 | `CONFIRMED` |
| 采集侧支持进程组终止 | 旧 `runner/kernel/process.py` 已验证 `start_new_session=True` + `killpg`，Fake hang 测得 `timed_out=True`、signal 9、无残留 pid | `CONFIRMED`（**架构改为 `experiments/util` 后必须重跑同一检查**） |

---

# 2. 看板

顺序即执行顺序。实验设计与步骤表见 [../README.md](../README.md) 第 4、5 层；本轮裁剪掉的实验及其先验结论见该文 §2.3，不在本报告出现。

## 2.1 第一阶段（9 条）

| 执行序 | 实验 | 主题 | 状态 | 核心结论 | 可信度 |
| --- | --- | --- | --- | --- | --- |
| P1-1 | N09 | 非确定性与归一化 | `NOT_STARTED` | `待填写` | `NONE` |
| P1-2 | N08 | exit code、启动语义、`--debug` 存活性 | `NOT_STARTED` | `待填写` | `NONE` |
| P1-3 | N03 | `class_name` 冷缓存与 import 触发 | `NOT_STARTED` | `待填写` | `NONE` |
| P1-4 | N01 | autoload 假阳性 | `NOT_STARTED` | `待填写` | `NONE` |
| P1-5 | N02 | addon 单例假阳性 | `NOT_STARTED` | `待填写` | `NONE` |
| P1-6 | N04 | 级联错误与根因放大 | `NOT_STARTED` | `待填写` | `NONE` |
| P1-7 | N05 | warning 与 error 严重度 | `NOT_STARTED` | `待填写` | `NONE` |
| P1-8 | N06 | invalid UID 严重度与资源引用变更 | `NOT_STARTED` | `待填写` | `NONE` |
| P1-9 | N07 | shader verifier 盲区 | `NOT_STARTED` | `待填写` | `NONE` |

## 2.2 第二阶段（2 条）

| 执行序 | 实验 | 主题 | 状态 | 核心结论 | 可信度 |
| --- | --- | --- | --- | --- | --- |
| P2-1 | N15 | converter 与 upgrade tool 能力门 | `NOT_STARTED` | `待填写` | `NONE` |
| P2-2 | N21 | 官方 Demo 自动迁移残余分布 | `NOT_STARTED` | `待填写` | `NONE` |

---

# 3. 第一阶段结论

每节只有四块：状态行、判据实测、结论、决策。表格里填的是**判据需要的那几个值**，不是全部测量数据。

---

## P1-1 · N09 非确定性与归一化

`NOT_STARTED` · 可信度 `NONE` · 证据 `artifacts/n09-20260821/N09/` → `reports/n09-20260821/N09/stability/`

| 判据 | 实测 |
| --- | --- |
| 重复间行集合是否一致（内容确定性） | `待填写` |
| 重复间输出顺序是否一致 | `待填写` |
| 出现哪些动态字段（绝对路径 / 行号 / 内存地址 / 随机 ID / 耗时数字） | `待填写` |
| 横向（CleanControl vs NP-CASCADE）暴露哪些随项目而变的字段 | `待填写` |
| CleanControl 背景是否漂移（BG-DRIFT） | `待填写` |

**结论**：`待填写`

**决策**：两级 signature 的字段规格 → 写进 §5 `signature`。纵向发现的字段两级都抹；横向发现的字段 `local` 留、`noise` 抹；行号必须排除；error 集合按排序后的 set 比较。后续实验重复次数：`待填写`（默认 3）。

---

## P1-2 · N08 exit code、启动语义与 `--debug` 存活性

`NOT_STARTED` · 可信度 `NONE` · 证据 `artifacts/<run-id>/N08/` → `reports/<run-id>/N08/exitcode/`

| 判据 | 实测 |
| --- | --- |
| 干净项目 rc（期望 0） | `待填写` |
| 单文件真错 rc（期望 ≠0） | `待填写` |
| 项目级真错 rc（期望 ≠0） | `待填写` |
| 纯假阳性 rc（期望 0，标签待 N01 确认） | `待填写` |
| V8 结局：挂死 / signal 11 / 正常退出，以及是否有残留子进程 | `待填写` |
| 有坏脚本时 V5 能否启动成功（B9） | `待填写` |
| V4 不带 `--editor` 能否 import；V6/V7 是否改变 rc | `待填写` |

**结论**：`待填写`（关键判断是“是否存在有错但 rc=0”）

**决策**：`VerifyReport.success` 用 `exit_code == 0` 还是三态 `CLEAN` / `HAS_ERRORS` / `INFRA_FAILURE` → §5 `verifier.success_source`；`--debug` 是否永久禁入、进程管理是否必须 killpg → §5 `verifier.allow_debug`、`process`。

---

## P1-3 · N03 `class_name` 冷缓存与 import 触发

`NOT_STARTED` · 可信度 `NONE` · 证据 `artifacts/<run-id>/N03/` → `reports/<run-id>/N03/sequence/`

| 判据 | 实测 |
| --- | --- |
| T1（COLD）是否报 `Identifier not found: ProbeFoo` | `待填写` |
| T3（import 后）是否干净 → 冷缓存假阳性 | `待填写` |
| T4（新增 `class_name`，不 import）是否报错 | `待填写` |
| T6（补 import 后）是否干净 → 缓存陈旧 | `待填写` |
| `global_script_class_cache.cfg` 在各步是否真的被重建 | `待填写` |

**结论**：`待填写`

**决策**：是否强制 warm-up（§5 `verifier.require_warm_cache`）；`import_trigger_policy` 的 `class_name_added` / `gd_file_added` / `ordinary_gd_body_changed` 三项 → §5 `import_policy`。T4 报错则必须做条件性 import 触发器，代价是每轮 patch 多花一次 import。

---

## P1-4 · N01 autoload 假阳性

`NOT_STARTED` · 可信度 `NONE` · 证据 `artifacts/<run-id>/N01/` → `reports/<run-id>/N01/delta/`

| 判据 | 实测 |
| --- | --- |
| COLD 下 V2 是否报 `Identifier not found: Config`（埋点 `AL-USES`） | `待填写` |
| WARM 下是否仍报 | `待填写` |
| V5 是否打印 `Config.ping() called`（证明符号真实存在） | `待填写` |
| V1 项目级扫描是否放大该 FP | `待填写` |
| 真错误埋点 `AL-SHADOW` 的精确文案（不得被过滤） | `待填写` |

**结论**：`待填写`（三选一：FP 在 COLD+WARM 都存在 / 只在 COLD / 不复现）

**决策**：§5 `noise_filters.autoload` 取值——`[autoload]` 段白名单 + V5 交叉验证 / 强制 warm-up 即可 / 无需处理。同时决定 §5 `verifier.require_warm_cache`。

---

## P1-5 · N02 addon 单例假阳性

`NOT_STARTED` · 可信度 `NONE` · 证据 `artifacts/<run-id>/N02/` → `reports/<run-id>/N02/delta/`

| 判据 | 实测 |
| --- | --- |
| 启用插件后 `DummySingleton` 是否出现在 `project.godot` 的 `[autoload]` 段 | `待填写` |
| V2 是否报单例找不到 | `待填写` |
| V5 是否证明单例在运行时注册成功 | `待填写` |
| 与 N01 是否同根同源（同一条过滤规则能否通吃） | `待填写` |
| 插件启用状态来自 derived patch 还是 manual gate | `待填写` |

**结论**：`待填写`

**决策**：§5 `noise_filters.addon_singleton` 取值——复用 autoload 白名单（约 20 行）/ 扫 addon 源码里的 `add_autoload_singleton`（约 200 行，不可靠）/ 不过滤直接 escalate。

---

## P1-6 · N04 级联错误与根因放大

`NOT_STARTED` · 可信度 `NONE` · 证据 `artifacts/<run-id>/N04/` + 复用 `artifacts/n09-20260821/N09/` → `reports/<run-id>/N04/cascade/`

| 判据 | 实测 |
| --- | --- |
| NP-CASCADE 项目级原始 error 行数（已扣除哨兵人造级联边） | `待填写` |
| 同构单根分母：`scene_bad.gd` 单文件 error 行数 | `待填写` |
| 放大倍数 | `待填写` |
| 去重后 signature 数 / 根因候选数 / 症状数 | `待填写` |
| 「`at:` 指向引擎内部路径 = 症状」这条规则是否成立 | `待填写` |
| 直接依赖（`dep_1`）与二级依赖（`leaf`）被单独 check 时报根因还是症状 | `待填写` |

**结论**：`待填写`

**决策**：`VerifyReport` 是否需要 `root_cause_errors` 字段（§5 `verifier.report_shape`）；症状 error 是否排除在重试计数器与熔断阈值之外（§5 `retry.count_symptoms`）。

---

## P1-7 · N05 warning 与 error 严重度

`NOT_STARTED` · 可信度 `NONE` · 证据 `artifacts/<run-id>/N05/` → `reports/<run-id>/N05/delta/`

| 判据 | 实测 |
| --- | --- |
| 默认设置下 warning 是否根本不出现 | `待填写` |
| 注入 `gdscript/warnings/enable=true` 后是否以 `WARNING:` 前缀出现在 stderr | `待填写` |
| `exclude_addons=true` 是否真的屏蔽了 addon 内 warning | `待填写` |
| CleanControl 背景里本来有多少 WARNING | `待填写` |

**结论**：`待填写`

**决策**：§5 `verifier.enable_warnings`——是否采集 warning 作为 Judge 的辅助证据。无论结果如何，`severity != ERROR` 的行不进 reward 与终止条件（这条已定，不需实验支撑）。

---

## P1-8 · N06 invalid UID 严重度与资源引用变更

`NOT_STARTED` · 可信度 `NONE` · 证据 `artifacts/<run-id>/N06/` → `reports/<run-id>/N06/sequence/`、`.../delta/`

| 判据 | 实测 |
| --- | --- |
| `invalid UID` 的严重度前缀（`WARNING:` 还是 `ERROR:`） | `待填写` |
| V3 重新 import 能否自愈伪造的 UID | `待填写` |
| `ext_resource` 指向变更后不 import 是否报错 | `待填写` |
| 补 import 之后是否干净 | `待填写` |
| 正确 UID 基线来自 derived patch 还是 manual gate | `待填写` |

**结论**：`待填写`

**决策**：§5 `noise_filters.invalid_uid`——前缀过滤（成本 0）还是必须维护非阻塞 error 文案白名单；`import_policy` 的 `scene_ext_resource_changed` / `uid_changed` 两项；入队前是否强制跑一次 UID 规范化。

---

## P1-9 · N07 shader verifier 盲区

`NOT_STARTED` · 可信度 `NONE` · 证据 `artifacts/<run-id>/N07/` → `reports/<run-id>/N07/delta/`

| 判据 | 实测 |
| --- | --- |
| V2（`preload` shader 的脚本）是否报错 | `待填写` |
| V3 import 阶段是否报错 | `待填写` |
| V5 场景启动阶段是否报错 | `待填写` |
| 默认 V1 哨兵（只 preload `*.gd`）能否覆盖 | `待填写` |
| `good.gdshader` 侧是否静默（排除“所有 shader 都不报”） | `待填写` |

**结论**：`待填写`（三选一，价值递减：全部静默 → 盲区 / import 阶段可见 → 免费信号 / V2 可抬升 → 哨兵可扩展）

**决策**：§5 `verifier.shader_coverage`——`.gdshader` 走 escalate、进 reward、或扩展哨兵到 `.gdshader`。这一条直接决定对外的验证边界声明。

---

# 4. 第二阶段结论

---

## P2-1 · N15 converter 与 upgrade tool 能力门

`NOT_STARTED` · 可信度 `NONE` · 证据 `artifacts/<run-id>/N15/` → `reports/<run-id>/N15/capability/`

| 判据 | 实测 |
| --- | --- |
| `--validate-conversion-3to4` 是否存在且可对最小项目调用 | `待填写` |
| `--convert-3to4` 是否存在且**真的改了文件**（以 diff 为准） | `待填写` |
| 是否接受 `max_file_kb` / `max_line_size` 参数 | `待填写` |
| ProjectUpgradeTool 是否有 headless CLI 入口 | `待填写` |
| 职责矩阵：converter / upgrade tool / `--import` 各改哪类文件（GDScript、`.tscn`、`.tres`、UID、资源路径、import cache） | `待填写` |

**结论**：`待填写`

**决策**：第二阶段流水线形状 → §5 `pipeline`：`converter → upgrade tool → verifier` 还是 `converter → --import → verifier`；是否需要第二个固定版本的 Godot 二进制；是否需要从 `renames_map_3_to_4.cpp` 自建 L0。能力门失败则 N21 记 `BLOCKED`。

---

## P2-2 · N21 官方 Demo 自动迁移残余分布

`NOT_STARTED` · 可信度 `NONE` · 证据 `artifacts/<run-id>/N21/` → `reports/<run-id>/N21/corpus/`

完整分布表（converter 行为分布、根因类别分布、严重度分布、可处理性分布、代表案例）由 `analyzer/corpus.py` 写在上面的 `reports/` 目录里，**不抄进本文**。这里只留摘要与判断。

| 判据 | 实测 |
| --- | --- |
| Demo 总数 / converter 成功完成数 / 转换后直接通过 verifier 的数 | `待填写` |
| 每个 Demo 的根因簇数：均值 / 中位 / P95 | `待填写` |
| Top 3 残余根因类别 | `待填写` |
| `TODOConverter3To4` 总数，以及是否机器可解析 | `待填写` |
| shader 残余：`.shader` 是否正确转为 `.gdshader`、引用是否同步 | `待填写` |
| converter 报告成功但文件未变化的案例数 | `待填写` |
| 最大 `.gd` 字节数与最长单行（判断大文件跳过问题是否成立） | `待填写` |
| COLD / WARM import 耗时（按 Demo 规模归一化） | `待填写` |
| `UNCLASSIFIED_NEEDS_REVIEW` 条数 | `待填写` |
| 3.x→4.0 残余与 4.0→4.7 漂移的比例 | `待填写` |

**结论**：`待填写`

**决策**：支持边界（自动 / 有条件 / 必须人工 / 明确不支持）→ §6.3；RAG 语料优先级与 Agent 优先处理的错误类型；import 是否为迭代主导成本（决定是否需要 cache 快照复用）。

---

# 5. 生产 verifier 配置

跨实验汇总，是本报告对项目的**唯一输出接口**。`null` 待实验回填；已标注「先验」的项不依赖实验，已经定死（依据见 [../README.md](../README.md) §2.3）。

```yaml
godot:
  version: "4.7.1.stable.official.a13da4feb"
  build_hash: "a13da4feb"

verifier:
  project_check: "V1 哨兵 preload"          # 先验：裸 --check-only 已确认是 no-op
  success_source: null                      # N08：exit_code 还是 CLEAN/HAS_ERRORS/INFRA_FAILURE
  require_warm_cache: null                  # N03 + N01
  use_runtime_cross_check: true             # 先验：V5 只作交叉验证，不作主通道
  enable_warnings: null                     # N05
  allow_debug: false                        # 先验 + N08 一次性观测确认
  shader_coverage: null                     # N07
  report_shape: null                        # N04：是否需要 root_cause_errors

process:
  timeout_seconds: null                     # 按 N08/N21 的实测 wall time 定
  use_process_group: true                   # 先验：Godot 会 fork 子进程，必须 killpg
  workspace_lock: true                      # 先验：串行锁无条件实现（原 N14 已裁剪）

signature:                                  # N09 回填
  local:
    include: [kind, res_path, symbol, normalized_message]
    exclude: [line_number, absolute_path, memory_address, timing_value]
  noise:
    include: [kind, msg_template]
    exclude: [res_path, symbol, line_number, absolute_path, memory_address, timing_value, numeric_value]
  compare_as_sorted_set: true

import_policy:                              # N03（脚本侧）+ N06（资源侧）
  class_name_added: null
  gd_file_added: null
  ordinary_gd_body_changed: null
  scene_ext_resource_changed: null
  uid_changed: null

noise_filters:
  autoload: null                            # N01
  addon_singleton: null                     # N02
  invalid_uid: null                         # N06
  cascade_symptoms: null                    # N04

retry:
  count_symptoms: null                      # N04：症状是否计入熔断阈值

gateway:
  reject_csproj: true                       # 先验：C#/GDExtension 硬拒收（原 N13 已裁剪）
  reject_gdextension: true                  # 同上
  prescan_file_size: true                   # 先验：converter 大文件问题改为入队预扫描（原 N11 已裁剪）
  normalize_uid_on_intake: null             # N06

pipeline:                                   # N15
  converter: null
  upgrade_tool: null
  verifier_entry: "V1"
```

---

# 6. 最终结论

> 所有相关实验结束后填写。每条必须引用实验编号与证据路径。

## 6.1 已确认的噪声与盲区

| 实验 | 现象 | 是否确认 | 规避 / 过滤策略 | 证据 |
| --- | --- | --- | --- | --- |
| N09 | 输出非确定性 | `待填写` | `待填写` | `待填写` |
| N08 | exit code 不可信 | `待填写` | `待填写` | `待填写` |
| N03 | 冷缓存 / patch 后缓存陈旧 | `待填写` | `待填写` | `待填写` |
| N01 | autoload 假阳性 | `待填写` | `待填写` | `待填写` |
| N02 | addon 单例假阳性 | `待填写` | `待填写` | `待填写` |
| N04 | 级联放大 | `待填写` | `待填写` | `待填写` |
| N05 | warning 严重度 | `待填写` | `待填写` | `待填写` |
| N06 | invalid UID 严重度 | `待填写` | `待填写` | `待填写` |
| N07 | shader 盲区（假阴性） | `待填写` | `待填写` | `待填写` |

## 6.2 未复现 / 尚无定论 / 被阻塞

- 未复现：`待填写`（注明环境、重复次数、缓存态）
- 尚无定论：`待填写`（说明缺哪份证据）
- 被阻塞：`待填写`（注明阻塞源与解除条件）

## 6.3 支持边界

- 自动支持：`待填写`
- 有条件支持：`待填写`
- 必须人工审核：`待填写`
- 明确不支持：C#/GDExtension 仓库（先验，入队拒收）；其余 `待填写`

## 6.4 摘要

需要回答的问题就这七条，多余的不写：

1. Godot 4.7.1 下可靠的 verifier 组合是什么？
2. 哪些输出是已确认的假阳性，怎么过滤？
3. 哪些错误类别是 verifier 的盲区，因此必须升级人工？
4. 哪些 patch 必须触发 re-import？
5. 官方 converter 对 3.5/3.6 Demo 的实际覆盖率如何？
6. 自动迁移后的主要残余问题是什么，各归哪一层处理（L0 / Agent / RAG / Judge / 人工）？
7. “解析清零”与“迁移完成”之间还差多少？

```text
待填写。
```
