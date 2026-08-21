# Godot 4.7.1 Verifier 噪声与 Godot 3.x 自动迁移实验报告

> **文档性质：**实验结果记录模板  
> **实验范围：**
>
> - **第一阶段：**使用 Godot 4.7.1 原生 Clean 项目和 Probe 项目，排查 verifier 自身的噪声、盲区和基础设施问题。
> - **第二阶段：**使用官方 Godot 3.5/3.6 游戏 Demo，验证官方 converter 的能力边界，并统计自动迁移后的残余问题。
>
> 本报告只记录实测结果。未经日志支持的推测不得写入“已确认结论”。  
> A 节由 runner 从 artifacts 生成，勿手填。B 节是人写的判断，以及该实验对后续规划的决策影响。

---

# 0. 报告填写规范

## 0.1 实验状态


| 状态                    | 含义              |
| --------------------- | --------------- |
| `NOT_STARTED`         | 尚未开始            |
| `RUNNING`             | 正在执行            |
| `CONFIRMED`           | 现象已稳定复现，证据充分    |
| `NOT_REPRODUCED`      | 按计划执行后未复现       |
| `INCONCLUSIVE`        | 结果不稳定或证据不足      |
| `BLOCKED`             | 因环境、工具或依赖条件无法执行 |
| `NEEDS_MANUAL_REVIEW` | 必须人工判断          |
| `PARTIALLY_CONFIRMED` | 只确认了实验中的一部分现象   |




## 0.2 结论可信度


| 等级         | 要求                          |
| ---------- | --------------------------- |
| **HIGH**   | 多次重复结果一致；有完整日志；对照组正常；缓存状态明确 |
| **MEDIUM** | 有完整日志，但重复次数不足或部分依赖人工判断      |
| **LOW**    | 单次观察、存在环境干扰，或没有可靠对照         |
| **NONE**   | 尚未形成结论                      |




## 0.3 单次实验必须记录的字段

```text
Measurement = (project, command, cache_state, repeat_idx)
```


| 字段                   | 必填               |
| -------------------- | ---------------- |
| Run ID               | 是                |
| 实验编号                 | 是                |
| Step ID              | 是                |
| Fixture/Dataset 版本   | 是                |
| Godot 版本和 build hash | 是                |
| 完整 argv              | 是                |
| COLD/WARM 状态         | 是                |
| Repeat 编号            | 是                |
| Exit code            | 是                |
| Signal               | 是                |
| Timeout              | 是                |
| Wall time            | 是                |
| stdout 日志            | 是                |
| stderr 日志            | 是                |
| 文件 diff              | 涉及修改时必填          |
| Cache manifest       | 涉及 `.godot/` 时必填 |
| Cleanup 结果           | 是                |




## 0.4 证据索引

A 节表格由 runner 生成，勿手填。证据索引写在 `artifacts/<run-id>/index.md`。

单次测量路径必须含 cache 与 repeat：

```text
artifacts/<run-id>/<N>/<step-id>/<cache_state>/<repeat_idx>/
```



## 0.5 结果分类

埋点表在 `annotations/`（事先）。real/clean 是运行后的归类桶。


| 分类                | 定义                                         |
| ----------------- | ------------------------------------------ |
| **TP**            | 埋点被 Δ 中某条 `local_signature` 命中；该条目进 REAL 桶 |
| **FN**            | 埋点未被任何 Δ 条目命中（盲区）                          |
| **FP**            | Δ 中未命中任何埋点的条目 = CLEAN 桶全部内容                |
| **SEV-MISMATCH**  | 输出存在但严重度与预期不同                              |
| **BG-DRIFT**      | CleanControl 背景输出在重复实验间漂移                  |
| **INFRA_FAILURE** | timeout、crash、环境错误或执行器故障                   |
| **UNCLASSIFIED**  | 暂时无法归类                                     |


两级 signature：

- `local_signature = sha1(kind \| res_path \| symbol \| normalized_msg)`：项目内身份
- `noise_signature = sha1(kind \| msg_template)`：只用于 BG 减法

BG 减法只做粗筛。TP/FP 归类必须回到 `local_signature`。CLEAN 桶 = 噪声过滤白名单，REAL 桶 = 禁止过滤的保护名单。

---



# 1. 实验运行信息



## 1.1 报告元数据


| 字段               | 实测值                                                                                                                                     |
| ---------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| 报告版本             | `0.1.0`                                                                                                                                 |
| 报告创建时间           | `2026-08-21 10:55:20 +0800`                                                                                                             |
| 最后更新时间           | `2026-08-21 10:55:20 +0800`                                                                                                             |
| 执行人员             | `yy_catmax`（git: `shanghuaye504-byte <shanghuaye504@gmail.com>`）                                                                        |
| Git commit       | `4bb577cb615b9d90519a15aa2631059151819a94`（HEAD；`godot_test/probe_tests/` 尚未入库）                                                        |
| 主 Run ID         | `env-preflight-20260821-105347`（仅环境预检，N01–N21 未跑）                                                                                      |
| 操作系统             | `macOS 26.3.1`（Build `25D771280a`；Darwin 25.3.0 `arm64`）                                                                               |
| CPU 架构           | `arm64`（Apple Silicon，`sysctl.proc_translated=0`）                                                                                       |
| Python 版本        | `3.13.9`（conda base：`/Users/yy_catmax/miniconda3/bin/python`）；PATH 另有 Homebrew `3.14.6`                                                |
| Godot 可执行文件      | `/usr/local/bin/godot4` → `/Users/yy_catmax/workspace/Godot Workspace/Godot.app/Contents/MacOS/Godot`                                    |
| Godot 版本         | `4.7.1.stable.official.a13da4feb`                                                                                                       |
| Godot build hash | `a13da4feb`                                                                                                                             |
| 官方构建/自编译构建       | 官方构建（version 含 `official`；Developer ID `Prehensile Tales B.V. (6K46PWY5DM)`，Gatekeeper `Notarized Developer ID`）                      |




## 1.2 环境校验

证据索引：`artifacts/env-preflight-20260821-105347/index.md`。


| 检查项                    | 期望            | 实测                                                                                                                                                          | 状态                    | 证据                                                                                  |
| ---------------------- | ------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------- | ----------------------------------------------------------------------------------- |
| Godot 版本               | 4.7.1         | `4.7.1.stable.official.a13da4feb`；CleanControl 副本 `--headless --path --quit` 退出码 0，stdout 含 `CLEAN_OK`                                                     | `CONFIRMED`           | `artifacts/env-preflight-20260821-105347/godot-identity.txt`、`godot-smoke.txt`       |
| 二进制架构                  | 与宿主一致，如 arm64 | 宿主 `arm64`；二进制为 universal `x86_64`+`arm64`，`LSArchitecturePriority` 优先 arm64；未走 Rosetta                                                                      | `CONFIRMED`           | `artifacts/env-preflight-20260821-105347/godot-identity.txt`                        |
| macOS quarantine       | 不阻止执行         | App/二进制带 `com.apple.quarantine`（Safari 下载）；`spctl` 为 `accepted` / `Notarized Developer ID`；`--version` 与 headless 冒烟均 exit 0                             | `CONFIRMED`           | `artifacts/env-preflight-20260821-105347/godot-quarantine.txt`、`godot-smoke.txt`     |
| Fixture git 状态         | 全部 clean      | 无已跟踪修改（`git diff` 空，`git ls-files` 空）；86 个 fixture 文件均为 `??` untracked，`probe_tests` 尚未建立提交基线                                                                | `PARTIALLY_CONFIRMED` | `artifacts/env-preflight-20260821-105347/fixture-git-status.txt`                    |
| Fixture 中无 `.godot/`   | 是             | `find fixtures -type d -name .godot` 计数 0；冒烟在 `workspaces/` 副本上进行，原 fixture 未被写入                                                                             | `CONFIRMED`           | `artifacts/env-preflight-20260821-105347/fixture-godot-scan.txt`                     |
| artifacts 位于 Fixture 外 | 是             | `probe_tests/artifacts/` 与 `probe_tests/fixtures/` 为兄弟目录，`artifacts_inside_fixtures=False`                                                                  | `CONFIRMED`           | `artifacts/env-preflight-20260821-105347/artifacts-location.txt`                    |
| Runner 支持进程组终止         | 是             | `runner/kernel/process.py` 仍为骨架，无 `subprocess`/`killpg`；宿主 Python 3.13.9 实测 `start_new_session` + `os.killpg(SIGKILL)` 可杀掉子进程组（含 fork 出的孙进程，rc=-9） | `BLOCKED`             | `artifacts/env-preflight-20260821-105347/runner-process-source.txt`、`process-group-kill.txt` |


---



# 2. 总体结果看板



## 2.1 第一阶段看板

> 以下顺序为实际执行顺序，不按 N 编号排序。


| 执行序号  | 实验  | 主题                      | 状态            | 核心结论  | 可信度    |
| ----- | --- | ----------------------- | ------------- | ----- | ------ |
| P1-01 | N09 | 非确定性与输出归一化              | `NOT_STARTED` | `待填写` | `NONE` |
| P1-02 | N08 | 命令语义、退出码和 PROJECT_CHECK | `NOT_STARTED` | `待填写` | `NONE` |
| P1-03 | N03 | `class_name` 冷缓存行为      | `NOT_STARTED` | `待填写` | `NONE` |
| P1-04 | N01 | autoload 假阳性            | `NOT_STARTED` | `待填写` | `NONE` |
| P1-05 | N02 | addon 单例假阳性             | `NOT_STARTED` | `待填写` | `NONE` |
| P1-06 | N10 | `--debug` 挂死/崩溃         | `NOT_STARTED` | `待填写` | `NONE` |
| P1-07 | N04 | 级联错误和根因放大               | `NOT_STARTED` | `待填写` | `NONE` |
| P1-08 | N05 | warning/error 严重度       | `NOT_STARTED` | `待填写` | `NONE` |
| P1-09 | N06 | invalid UID 严重度         | `NOT_STARTED` | `待填写` | `NONE` |
| P1-10 | N12 | patch 后缓存陈旧             | `NOT_STARTED` | `待填写` | `NONE` |
| P1-11 | N07 | shader verifier 盲区      | `NOT_STARTED` | `待填写` | `NONE` |
| P1-12 | N13 | C#/GDExtension 环境污染     | `NOT_STARTED` | `待填写` | `NONE` |
| P1-13 | N14 | 并发 import 污染            | `NOT_STARTED` | `待填写` | `NONE` |




## 2.2 第二阶段看板


| 执行序号  | 实验    | 主题                        | 状态            | 核心结论  | 可信度    |
| ----- | ----- | ------------------------- | ------------- | ----- | ------ |
| P2-01 | N15   | converter CLI 能力门         | `NOT_STARTED` | `待填写` | `NONE` |
| P2-02 | N16   | ProjectUpgradeTool 职责边界   | `NOT_STARTED` | `待填写` | `NONE` |
| P2-03 | N11   | 大文件跳过、阈值和 hang            | `NOT_STARTED` | `待填写` | `NONE` |
| P2-04 | N17   | TODO 与 `instance()` 转换覆盖率 | `NOT_STARTED` | `待填写` | `NONE` |
| P2-05 | N18   | shader 转换正确性              | `NOT_STARTED` | `待填写` | `NONE` |
| P2-06 | N20   | mutation 评测泄漏             | `NOT_STARTED` | `待填写` | `NONE` |
| P2-07 | N21-A | 官方 Demo 转换与快照冻结           | `NOT_STARTED` | `待填写` | `NONE` |
| P2-08 | N19   | 自动迁移后 import 成本           | `NOT_STARTED` | `待填写` | `NONE` |
| P2-09 | N21-B | 官方 Demo 残余问题统计            | `NOT_STARTED` | `待填写` | `NONE` |


---



# 第一阶段 · Godot 4.7.1 Verifier 噪声排查

---



# P1-01 · N09 非确定性与输出归一化



## A. 数据记录

> 由 runner 生成，勿手填。证据见 `artifacts/<run-id>/index.md`。N09 纵向 repeat=5。



### A.1 实验信息


| 字段      | 记录                                                                   |
| ------- | -------------------------------------------------------------------- |
| 状态      | `NOT_STARTED`                                                        |
| Fixture | CleanControl、NP-CASCADE                                              |
| 目标      | 纵向发现运行时随机字段；横向（CleanControl vs NP-CASCADE）发现项目相关字段；产出两级 signature 规格 |
| 重复次数    | N09 自身 5 次校准；其余实验默认 3 次                                              |
| 缓存状态    | COLD、WARM                                                            |
| 前置依赖    | 无                                                                    |
| 输出给后续实验 | normalization profile、重复次数策略、BG 稳定性结论                                |




### A.2 CleanControl 纵向重复


| Step      | 指令  | Cache     | Repeat | Exit code | Wall time | Error/Warning 数 | 输出 hash |
| --------- | --- | --------- | ------ | --------- | --------- | --------------- | ------- |
| N09-CC-V1 | V1  | COLD/WARM | 5      |           |           |                 |         |
| N09-CC-V3 | V3  | COLD/WARM | 5      |           |           |                 |         |
| N09-CC-V9 | V9  | WARM      | 5      |           |           |                 |         |




### A.3 NP-CASCADE 纵向重复


| Step       | 指令             | Repeat | 错误行集合一致 | 输出顺序一致 | 动态字段 |
| ---------- | -------------- | ------ | ------- | ------ | ---- |
| N09-CAS-V2 | V2 on dep_1.gd | 5      |         |        |      |
| N09-CAS-V3 | V3             | 5      |         |        |      |
| N09-CAS-V9 | V9             | 5      |         |        |      |




### A.3b 横向对比（CleanControl vs NP-CASCADE，同命令离线 diff）


| 指令  | 随项目而变的字段 | 归入 local / noise |
| --- | -------- | ---------------- |
| V1  |          |                  |
| V3  |          |                  |
| V9  |          |                  |




### A.4 漂移字段记录


| 字段类型  | 是否出现 | 示例  | 是否归一化      | 归一化规则          |
| ----- | ---- | --- | ---------- | -------------- |
| 绝对路径  |      |     |            |                |
| 行号    |      |     | 是          | 从 signature 排除 |
| 内存地址  |      |     |            |                |
| 随机 ID |      |     |            |                |
| UID   |      |     |            |                |
| 时间数字  |      |     |            |                |
| 输出顺序  |      |     | 使用排序后的 set |                |




## B. 实验结果分析


| 分析项                    | 判断            |
| ---------------------- | ------------- |
| BG 是否稳定                | `待填写`         |
| 错误集合是否稳定               | `待填写`         |
| 错误顺序是否稳定               | `待填写`         |
| 是否存在动态字段               | `待填写`         |
| 后续实验建议重复次数             | `待填写`         |
| signature 是否必须集合化      | `待填写`         |
| 是否确认 BG-DRIFT          | `待填写`         |
| 横向暴露了哪些项目相关字段          | `待填写`         |
| local_signature 保留哪些字段 | `待填写`         |
| noise_signature 抹掉哪些字段 | `待填写`         |
| 最终状态                   | `NOT_STARTED` |
| 可信度                    | `NONE`        |




### B.1 最终 signature 规格

```text
待填写。必须分成两级：

local_signature  = sha1(kind | res_path | symbol | normalized_msg)
noise_signature  = sha1(kind | msg_template)

纵向发现的字段两级都抹；横向发现的字段 local 留、noise 抹。
```



### B.2 对后续实验的影响

- [ ] 后续结果可按原始输出顺序比较
- [ ] 后续结果必须先归一化再比较
- [ ] 后续结果必须作为排序后的 set
- [ ] 已产出两级 signature 字段规格
- [ ] 后续实验默认重复 3 次（N09 自身已用 5 次校准）
- [ ] 仅高风险实验提高重复次数
- [ ] 需要补充其他规则：`待填写`

---



# P1-02 · N08 命令语义、退出码和 `PROJECT_CHECK`



## A. 数据记录

> 由 runner 生成，勿手填。证据见 `artifacts/<run-id>/index.md`。



### A.1 实验信息


| 字段      | 记录                                       |
| ------- | ---------------------------------------- |
| 状态      | `NOT_STARTED`                            |
| Fixture | CleanControl、NP-SYNTAX                   |
| 合并验证项   | B3、B9、N08                                |
| 目标      | 裁决 V1/V9/V10 覆盖能力、V5 启动语义和 exit code 可信度 |
| 前置依赖    | N09 normalization profile                |
| 延迟回填依赖  | N10 的 timeout/crash exit code            |




### A.2 命令能力测试


| 指令         | 目标                  | 是否发现 orphan parse error | 是否发现 orphan compile error | 是否发现非主场景错误 | 是否只报第一个错误 | Exit code | 日志  |
| ---------- | ------------------- | ----------------------- | ------------------------- | ---------- | --------- | --------- | --- |
| V1         | 无 `--script` 的项目检查  |                         |                           |            |           |           |     |
| V2 parse   | 单文件 parse error     | `适用`                    | —                         | —          |           |           |     |
| V2 compile | 单文件 compile error   | —                       | `适用`                      | —          |           |           |     |
| V3         | import 扫描           |                         |                           |            |           |           |     |
| V4         | 无 `--editor` import |                         |                           |            |           |           |     |
| V5         | 启动主场景               |                         |                           |            |           |           |     |
| V9         | preload 哨兵检查        |                         |                           |            |           |           |     |
| V10        | 逐文件 V2              |                         |                           |            | 不适用       |           |     |




### A.3 V10 成本


| `.gd` 文件数 | 进程数 | 总 wall time | 平均启动时间 | 最大时间 | 最小时间 | 日志  |
| --------- | --- | ----------- | ------ | ---- | ---- | --- |
|           |     |             |        |      |      |     |




### A.4 Exit code 交叉表


| 场景                | 项目/指令        | 真实状态              | Exit code  | stderr 有错误 | 判定  |
| ----------------- | ------------ | ----------------- | ---------- | ---------- | --- |
| 干净                | CleanControl | CLEAN             |            |            |     |
| 单文件 parse error   | NP-SYNTAX V2 | HAS_ERRORS        |            |            |     |
| 单文件 compile error | NP-SYNTAX V2 | HAS_ERRORS        |            |            |     |
| 项目检查              | NP-SYNTAX V1 | HAS_ERRORS 或命令无覆盖 |            |            |     |
| 哨兵检查              | NP-SYNTAX V9 | HAS_ERRORS        |            |            |     |
| 启动主场景             | NP-SYNTAX V5 | 主场景正常、孤立文件错误      |            |            |     |
| Timeout/crash     | N10 V8       | INFRA_FAILURE     | `待 N10 回填` |            |     |




### A.5 `PROJECT_CHECK` 裁决


| 候选  | 覆盖完整 | 输出可解析 | 性能可接受 | 选用  |
| --- | ---- | ----- | ----- | --- |
| V1  |      |       |       |     |
| V9  |      |       |       |     |
| V10 |      |       |       |     |


```text
PROJECT_CHECK = 待填写
```



## B. 实验结果分析


| 分析项                 | 判断            |
| ------------------- | ------------- |
| V1 是否真正执行项目级检查      | `待填写`         |
| V9 是否覆盖全部目标文件       | `待填写`         |
| V9 是否因首个错误提前中断      | `待填写`         |
| V10 是否为必要保底方案       | `待填写`         |
| V5 启动成功能否证明项目脚本全部正确 | `待填写`         |
| Exit code 是否可信      | `待填写`         |
| 最终 `PROJECT_CHECK`  | `待填写`         |
| 最终状态                | `NOT_STARTED` |
| 可信度                 | `NONE`        |




### B.1 Verifier 状态定义


| 状态              | 最终判定规则 |
| --------------- | ------ |
| `CLEAN`         | `待填写`  |
| `HAS_ERRORS`    | `待填写`  |
| `INFRA_FAILURE` | `待填写`  |




### B.2 对后续实验的影响

- [ ] 后续项目级检查使用 V1
- [ ] 后续项目级检查使用 V9
- [ ] 后续项目级检查使用 V10
- [ ] V5 仅用于运行时交叉验证
- [ ] 不能使用 exit code 单独决定成功
- [ ] V1 保留为命令语义对照，但不再作为正确性判据

---



# P1-03 · N03 `class_name` 全局类缓存



## A. 数据记录

> 由 runner 生成，勿手填。证据见 `artifacts/<run-id>/index.md`。



### A.1 实验序列


| Step | 操作                  | Cache         | 预期观察             | 实测输出 | Exit code | Wall time | Cache 快照 | 日志  |
| ---- | ------------------- | ------------- | ---------------- | ---- | --------- | --------- | -------- | --- |
| T1   | V2 `uses_class.gd`  | COLD          | 是否找不到 `ProbeFoo` |      |           |           |          |     |
| T2   | V3 import           | COLD→WARM     | 建立 class cache   |      |           |           |          |     |
| T3   | V2 `uses_class.gd`  | WARM          | 是否恢复干净           |      |           |           |          |     |
| T4   | 新建 `ProbeLate` 后 V2 | WARM、未 import | 是否找不到新类          |      |           |           |          |     |
| T5   | V3 import           | WARM          | 更新 class cache   |      |           |           |          |     |
| T6   | V2 `uses_late.gd`   | WARM          | 是否恢复干净           |      |           |           |          |     |




### A.2 Class cache 内容变化


| 比较      | 是否变化 | 新增/删除类 | 证据  |
| ------- | ---- | ------ | --- |
| T1 → T2 |      |        |     |
| T2 → T3 |      |        |     |
| T3 → T4 |      |        |     |
| T4 → T5 |      |        |     |
| T5 → T6 |      |        |     |




## B. 实验结果分析


| 分析项                            | 判断            |
| ------------------------------ | ------------- |
| T1 错、T3 干净                     | `待填写`         |
| 是否确认冷缓存假阳性                     | `待填写`         |
| T4 错、T6 干净                     | `待填写`         |
| 新增 `class_name` 是否要求 re-import | `待填写`         |
| 删除 `.godot/` 是否形成可靠 COLD       | `待填写`         |
| 单次 import 成本                   | `待填写`         |
| 最终状态                           | `NOT_STARTED` |
| 可信度                            | `NONE`        |




### B.1 初步 import 触发策略


| Patch 类型                 | 是否触发 import |
| ------------------------ | ----------- |
| 新增带 `class_name` 的 `.gd` | `待填写`       |
| 修改现有 `class_name`        | `待填写`       |
| 新增普通 `.gd`               | `待填写`       |
| 仅修改函数体                   | `待填写`       |


---



# P1-04 · N01 autoload 假阳性



## A. 数据记录

> 由 runner 生成，勿手填。证据见 `artifacts/<run-id>/index.md`。



### A.1 主实验


| Step   | 操作                    | Cache     | 关键输出                | `Config` 是否被报告不存在 | Exit code | 日志  |
| ------ | --------------------- | --------- | ------------------- | ----------------- | --------- | --- |
| N01-01 | V2 `uses_autoload.gd` | COLD      |                     |                   |           |     |
| N01-02 | V3 建立 WARM            | COLD→WARM |                     | —                 |           |     |
| N01-03 | V5 运行主场景              | WARM      | 是否打印 `CONFIG_ALIVE` | —                 |           |     |
| N01-04 | V2 `uses_autoload.gd` | WARM      |                     |                   |           |     |
| N01-05 | V1 对照                 | WARM      |                     |                   |           |     |
| N01-06 | V9/PROJECT_CHECK      | WARM      |                     |                   |           |     |




### A.2 精确错误文案


| 子实验                | 预期性质       | 精确消息  | Severity | `res://` 位置 | 判定  |
| ------------------ | ---------- | ----- | -------- | ----------- | --- |
| `uses_autoload.gd` | 假阳性候选      | `待填写` |          |             |     |
| `shadow_config.gd` | 真实冲突       | `待填写` |          |             |     |
| `res_loader.gd`    | #120225 变种 | `待填写` |          |             |     |




### A.3 COLD/WARM 对比


| 观察项                                          | COLD | WARM | 差异  |
| -------------------------------------------- | ---- | ---- | --- |
| `Identifier not found: Config`               |      |      |     |
| `Class "Config" hides an autoload singleton` |      |      |     |
| V5 运行时 Config 可用                             |      |      |     |
| Exit code                                    |      |      |     |




## B. 实验结果分析


| 分析项                 | 判断            |
| ------------------- | ------------- |
| autoload FP 是否复现    | `待填写`         |
| 是否只在 COLD 出现        | `待填写`         |
| WARM 是否能完全规避        | `待填写`         |
| 真错误和假阳性文案能否可靠区分     | `待填写`         |
| #120225 是否复现        | `待填写`         |
| 是否需要 autoload 白名单过滤 | `待填写`         |
| 是否需要 V5 交叉验证        | `待填写`         |
| 最终状态                | `NOT_STARTED` |
| 可信度                 | `NONE`        |




### B.1 处理策略裁决

- [ ] 不复现，无需过滤
- [ ] 只需强制 warm-up
- [ ] 解析 `[autoload]` 建立白名单
- [ ] 需要 V5 交叉验证
- [ ] #120225 不得使用普通 autoload 白名单直接过滤
- [ ] 直接 escalate
- [ ] 其他：`待填写`

---



# P1-05 · N02 addon 单例假阳性



## A. 数据记录

> 由 runner 生成，勿手填。证据见 `artifacts/<run-id>/index.md`。



### A.1 GUI 前置操作


| 检查项                                | 实测    |
| ---------------------------------- | ----- |
| GUI 启用插件成功                         | `待填写` |
| `[editor_plugins]` 是否变化            | `待填写` |
| `[autoload]` 是否新增 `DummySingleton` | `待填写` |
| 插件是否修改其他文件                         | `待填写` |
| `project.godot` diff               |       |
| GUI 操作证据                           |       |




### A.2 指令结果


| Step   | 指令                 | 观察                       | Exit code | Wall time | 日志  |
| ------ | ------------------ | ------------------------ | --------- | --------- | --- |
| N02-01 | V5                 | 是否打印 `DUMMY_ALIVE`       |           |           |     |
| N02-02 | V2 `uses_addon.gd` | 是否报 `DummySingleton` 不存在 |           |           |     |
| N02-03 | PROJECT_CHECK      | 是否出现相同问题                 |           |           |     |




### A.3 与 N01 对照


| 比较项               | N01 autoload | N02 addon | 是否同根 |
| ----------------- | ------------ | --------- | ---- |
| 是否写入 `[autoload]` |              |           |      |
| 错误文案              |              |           |      |
| WARM 后是否消失        |              |           |      |
| V5 是否正常           |              |           |      |




## B. 实验结果分析


| 分析项                                | 判断            |
| ---------------------------------- | ------------- |
| addon 单例 FP 是否复现                   | `待填写`         |
| 是否与 N01 同根                         | `待填写`         |
| 单例是否永久写入 `[autoload]`              | `待填写`         |
| 是否需要扫描 addon 源码                    | `待填写`         |
| 扫描 `add_autoload_singleton` 是否值得实现 | `待填写`         |
| 最终状态                               | `NOT_STARTED` |
| 可信度                                | `NONE`        |




### B.1 实现决策

- [ ] 复用 N01 的 `[autoload]` 白名单
- [ ] 新增 addon 源码扫描
- [ ] 不过滤，直接 escalate
- [ ] 不复现，无需处理
- [ ] 其他：`待填写`

---



# P1-06 · N10 `--debug` 挂死或崩溃



## A. 数据记录

> 由 runner 生成，勿手填。证据见 `artifacts/<run-id>/index.md`。



### A.1 进程结果


| Step   | 指令  | Timeout 设置 | 实际 wall time | Exit code | Signal | 是否残留子进程 | 日志  |
| ------ | --- | ---------- | ------------ | --------- | ------ | ------- | --- |
| N10-01 | V8  | 30s        |              |           |        |         |     |




### A.2 现象判定


| 现象                       | 是否出现  | 证据  |
| ------------------------ | ----- | --- |
| 进入交互式 debugger           | `待填写` |     |
| 达到 timeout               | `待填写` |     |
| signal 11                | `待填写` |     |
| rc 134                   | `待填写` |     |
| rc 139                   | `待填写` |     |
| `handle_crash` 文案        | `待填写` |     |
| headless 编辑器对象 backtrace | `待填写` |     |
| 单杀主进程后仍有子进程              | `待填写` |     |
| killpg 后全部退出             | `待填写` |     |




### A.3 Cleanup


| 检查项              | 结果    |
| ---------------- | ----- |
| Godot 进程组已终止     | `待填写` |
| 无残留进程            | `待填写` |
| 工作区删除成功          | `待填写` |
| Fixture 保持 clean | `待填写` |
| Cleanup 日志       |       |




## B. 实验结果分析


| 分析项                        | 判断            |
| -------------------------- | ------------- |
| V8 是否挂死                    | `待填写`         |
| V8 是否崩溃                    | `待填写`         |
| 是否确认 INFRA_FAILURE         | `待填写`         |
| `--debug` 是否应禁入正式 verifier | `待填写`         |
| Runner 是否必须 kill 整个进程组     | `待填写`         |
| 回填到 N08 的 exit code 规则     | `待填写`         |
| 对 N05 warning 获取方式的影响      | `待填写`         |
| 最终状态                       | `NOT_STARTED` |
| 可信度                        | `NONE`        |


---



# P1-07 · N04 级联错误与根因放大



## A. 数据记录

> 由 runner 生成，勿手填。证据见 `artifacts/<run-id>/index.md`。



### A.1 各入口错误数量


| 入口        | 指令               | 原始错误行数 | 归一化 signature 数 | 根因候选数 | 症状数 | 重复稳定 | 日志  |
| --------- | ---------------- | ------ | --------------- | ----- | --- | ---- | --- |
| dep_1.gd  | V2               |        |                 |       |     |      |     |
| dep_2.gd  | V2               |        |                 |       |     |      |     |
| dep_3.gd  | V2               |        |                 |       |     |      |     |
| dep_4.gd  | V2               |        |                 |       |     |      |     |
| dep_5.gd  | V2               |        |                 |       |     |      |     |
| leaf.gd   | V2               |        |                 |       |     |      |     |
| 项目 import | V3               |        |                 |       |     |      |     |
| 项目检查      | V9/PROJECT_CHECK |        |                 |       |     |      |     |




### A.2 根因与症状文案配对


| 类型  | 精确/归一化文案                                   | `at:` 位置               | 是否计入修复重试 | 证据  |
| --- | ------------------------------------------ | ---------------------- | -------- | --- |
| 根因  | `待填写`                                      | `res://...`            | 是        |     |
| 症状  | `Failed to load script...` 或实测文案           | `待填写`                  | 否        |     |
| 症状  | `Failed to compile depended scripts` 或实测文案 | `待填写`                  | 否        |     |
| 症状  | 引擎内部 `.cpp` 错误                             | `modules/gdscript/...` | 否        |     |




### A.3 放大倍数


| 指标                | 数值    |
| ----------------- | ----- |
| NP-SYNTAX 单根因错误行数 | `待填写` |
| NP-CASCADE 错误行数   | `待填写` |
| 行数放大倍数            | `待填写` |
| Signature 放大倍数    | `待填写` |
| 症状占全部错误比例         | `待填写` |




## B. 实验结果分析


| 分析项                                     | 判断            |
| --------------------------------------- | ------------- |
| 是否存在级联错误                                | `待填写`         |
| 根因和症状能否按路径区分                            | `待填写`         |
| 是否需要 root-cause clustering              | `待填写`         |
| 症状是否应排除出重试计数                            | `待填写`         |
| `VerifyReport` 是否需要 `root_cause_errors` | `待填写`         |
| 最终状态                                    | `NOT_STARTED` |
| 可信度                                     | `NONE`        |


---



# P1-08 · N05 warning 与 error 严重度



## A. 数据记录

> 由 runner 生成，勿手填。证据见 `artifacts/<run-id>/index.md`。



### A.1 默认设置与注入设置对照


| 配置           | 指令            | Warning 数 | Error 数 | Warning 输出流 | Addon warning 数 | Exit code | 日志  |
| ------------ | ------------- | --------- | ------- | ----------- | --------------- | --------- | --- |
| 默认           | V1            |           |         |             |                 |           |     |
| 默认           | V2            |           |         |             |                 |           |     |
| 默认           | V3            |           |         |             |                 |           |     |
| 注入 `[debug]` | V1            |           |         |             |                 |           |     |
| 注入 `[debug]` | V2            |           |         |             |                 |           |     |
| 注入 `[debug]` | V3            |           |         |             |                 |           |     |
| 注入 `[debug]` | PROJECT_CHECK |           |         |             |                 |           |     |




### A.2 Warning 类型


| Warning 类型           | 默认可见 | 注入后可见 | Severity 文本 | stdout/stderr | 证据  |
| -------------------- | ---- | ----- | ----------- | ------------- | --- |
| unused variable      |      |       |             |               |     |
| integer division     |      |       |             |               |     |
| narrowing conversion |      |       |             |               |     |
| shadowed variable    |      |       |             |               |     |
| unused signal        |      |       |             |               |     |
| untyped declaration  |      |       |             |               |     |




### A.3 `exclude_addons`


| 检查项                          | 结果    |
| ---------------------------- | ----- |
| Addon 中确实存在 warning 埋点       | `待填写` |
| `exclude_addons=false` 时是否可见 | `待填写` |
| `exclude_addons=true` 时是否屏蔽  | `待填写` |
| 屏蔽是否完全                       | `待填写` |




## B. 实验结果分析


| 分析项                      | 判断            |
| ------------------------ | ------------- |
| 默认 CLI 是否输出 warning      | `待填写`         |
| 项目设置注入是否有效               | `待填写`         |
| warning 是否具有稳定前缀         | `待填写`         |
| warning 是否可能误判为 error    | `待填写`         |
| `exclude_addons` 是否可靠    | `待填写`         |
| warning 是否可作为 Judge 辅助信号 | `待填写`         |
| warning 是否进入 reward      | 否             |
| warning 是否进入终止条件         | 否             |
| 最终状态                     | `NOT_STARTED` |
| 可信度                      | `NONE`        |


---



# P1-09 · N06 invalid UID 严重度



## A. 数据记录

> 由 runner 生成，勿手填。证据见 `artifacts/<run-id>/index.md`。



### A.1 GUI 正确 UID 基线


| 检查项                 | 实测    |
| ------------------- | ----- |
| 已在临时工作区中用 GUI 打开并保存 | `待填写` |
| 正确 UID 已生成          | `待填写` |
| 正确 UID 值            | `待填写` |
| 基线项目运行正常            | `待填写` |
| 基线 diff/hash        |       |




### A.2 UID 实验序列


| Step | 状态              | 指令               | 输出中的 UID 文案 | Severity | Exit code | UID 是否被修复 | 日志  |
| ---- | --------------- | ---------------- | ----------- | -------- | --------- | --------- | --- |
| S1   | 正确 UID          | V3               |             |          |           | 不适用       |     |
| S1   | 正确 UID          | V2/PROJECT_CHECK |             |          |           | 不适用       |     |
| S2   | 伪造 UID、未 import | V2/PROJECT_CHECK |             |          |           |           |     |
| S2   | 伪造 UID          | V3               |             |          |           |           |     |
| S2   | import 后        | V2/PROJECT_CHECK |             |          |           |           |     |




### A.3 严重度判断


| 消息                 | 前缀    | 解析后 severity | 是否阻塞  | 证据  |
| ------------------ | ----- | ------------ | ----- | --- |
| invalid UID        | `待填写` | `待填写`        | `待填写` |     |
| fallback path/资源警告 | `待填写` | `待填写`        | `待填写` |     |




## B. 实验结果分析


| 分析项               | 判断            |
| ----------------- | ------------- |
| invalid UID 是否复现  | `待填写`         |
| 实际严重度是否为 WARNING  | `待填写`         |
| 是否以 ERROR 前缀输出    | `待填写`         |
| 是否存在 SEV-MISMATCH | `待填写`         |
| V3 是否自动修复 UID     | `待填写`         |
| 是否需要文案白名单         | `待填写`         |
| 入队前是否应强制 UID 规范化  | `待填写`         |
| 最终状态              | `NOT_STARTED` |
| 可信度               | `NONE`        |


---



# P1-10 · N12 patch 后缓存陈旧



## A. 数据记录

> 由 runner 生成，勿手填。证据见 `artifacts/<run-id>/index.md`。



### A.1 N12-a：`class_name` 缓存

> 可直接引用 N03 的 T4—T6；若独立复验，则填写新的日志。


| 状态                | 操作             | 未 import 结果 | 补 V3 后结果 | 是否确认缓存陈旧 | 证据  |
| ----------------- | -------------- | ----------- | -------- | -------- | --- |
| 新增 `class_name`   | 新增 `ProbeLate` |             |          |          |     |
| 修改现有 `class_name` |                |             |          |          |     |
| 新增普通 `.gd`        |                |             |          |          |     |




### A.2 N12-b：资源引用缓存


| Step | 操作                         | 指令               | 结果  | Exit code | Cache 变化 | 日志  |
| ---- | -------------------------- | ---------------- | --- | --------- | -------- | --- |
| R1   | 正确资源引用                     | V2/PROJECT_CHECK |     |           |          |     |
| R2   | 修改 `ext_resource`，不 import | V2/PROJECT_CHECK |     |           |          |     |
| R3   | 补 V3                       | V3               |     |           |          |     |
| R4   | import 后复查                 | V2/PROJECT_CHECK |     |           |          |     |




### A.3 Import 触发表


| Patch 类型                | 未 import 是否产生陈旧结果 | V3 是否修复 | 是否必须触发 import | 证据  |
| ----------------------- | ----------------- | ------- | ------------- | --- |
| 新增 `class_name`         |                   |         |               |     |
| 修改 `class_name`         |                   |         |               |     |
| 新增普通 `.gd`              |                   |         |               |     |
| 修改普通函数体                 |                   |         |               |     |
| 修改 `.tscn ext_resource` |                   |         |               |     |
| 修改 UID                  |                   |         |               |     |
| 新增资源文件                  |                   |         |               |     |




## B. 实验结果分析


| 分析项                 | 判断            |
| ------------------- | ------------- |
| N12-a 是否确认          | `待填写`         |
| N12-b 是否确认          | `待填写`         |
| 是否需要每轮无条件 import    | `待填写`         |
| 是否可使用条件性 import     | `待填写`         |
| 条件性 import 可节省的估计成本 | `待填写`         |
| 最终状态                | `NOT_STARTED` |
| 可信度                 | `NONE`        |




### B.1 最终 import policy

```yaml
# 待填写
import_trigger_policy:
  class_name_added:
  class_name_modified:
  gd_file_added:
  ordinary_gd_body_changed:
  scene_ext_resource_changed:
  uid_changed:
  resource_added:
```

---



# P1-11 · N07 shader verifier 盲区



## A. 数据记录

> 由 runner 生成，勿手填。证据见 `artifacts/<run-id>/index.md`。



### A.1 各信号通道


| Step   | 指令                  | Cache | 是否发现 shader 语法错误 | 错误阶段          | 文案  | Exit code | 日志  |
| ------ | ------------------- | ----- | ---------------- | ------------- | --- | --------- | --- |
| N07-01 | V2 `shader_user.gd` | COLD  |                  |               |     |           |     |
| N07-02 | V3                  | COLD  |                  | import/其他     |     |           |     |
| N07-03 | V2 `shader_user.gd` | WARM  |                  |               |     |           |     |
| N07-04 | V5                  | WARM  |                  | scene/runtime |     |           |     |
| N07-05 | PROJECT_CHECK       | WARM  |                  |               |     |           |     |




### A.2 信号归类


| 信号                        | 是否出现 | 能否定位 `.gdshader` | 是否可进入 reward | 证据  |
| ------------------------- | ---- | ---------------- | ------------ | --- |
| Shader 语法错误               |      |                  |              |     |
| `Failed to load resource` |      |                  |              |     |
| Import error              |      |                  |              |     |
| Scene startup error       |      |                  |              |     |
| 完全静默                      |      | 不适用              | 否            |     |




## B. 实验结果分析


| 分析项                       | 判断            |
| ------------------------- | ------------- |
| V2 preload 是否抬升 shader 错误 | `待填写`         |
| V3 是否捕获 shader 错误         | `待填写`         |
| V5 是否捕获 shader 错误         | `待填写`         |
| 是否确认 verifier 盲区          | `待填写`         |
| 是否值得生成 shader sentinel    | `待填写`         |
| `.gdshader` 是否必须 escalate | `待填写`         |
| 最终状态                      | `NOT_STARTED` |
| 可信度                       | `NONE`        |




### B.1 Shader 验证策略

- [ ] PROJECT_CHECK 已覆盖 shader
- [ ] 注入 preload shader sentinel
- [ ] 依赖 V3 import
- [ ] 依赖 V5 scene load
- [ ] 全部静默，直接 escalate
- [ ] 其他：`待填写`

---



# P1-12 · N13 C#/GDExtension 环境污染



## A. 数据记录

> 由 runner 生成，勿手填。证据见 `artifacts/<run-id>/index.md`。



### A.1 纯 GDScript 与异类项目对照


| 组别           | 指令         | `.NET` 错误数 | GDExtension 错误数 | `ok.gd` 是否被污染 | Exit code | 日志  |
| ------------ | ---------- | ---------- | --------------- | ------------- | --------- | --- |
| CleanControl | V2         |            |                 | 否             |           |     |
| NP-ALIEN     | V2 `ok.gd` |            |                 |               |           |     |
| NP-ALIEN     | V3         |            |                 |               |           |     |
| NP-ALIEN     | V5         |            |                 |               |           |     |




### A.2 环境错误文案


| 类别                      | 精确文案  | Severity | 是否影响纯 GDScript | 证据  |
| ----------------------- | ----- | -------- | -------------- | --- |
| .NET runtime            | `待填写` |          |                |     |
| C# project              | `待填写` |          |                |     |
| Dynamic library         | `待填写` |          |                |     |
| GDExtension entry point | `待填写` |          |                |     |




### A.3 运行痕迹


| 路径/产物          | 是否产生 | 是否清理 |
| -------------- | ---- | ---- |
| `.godot/mono/` |      |      |
| `.mono/`       |      |      |
| C# build 输出    |      |      |
| 动态库缓存          |      |      |
| 残留进程           |      |      |




## B. 实验结果分析


| 分析项                            | 判断            |
| ------------------------------ | ------------- |
| C# 环境错误是否污染 GDScript 验证        | `待填写`         |
| GDExtension 错误是否污染 GDScript 验证 | `待填写`         |
| 是否需要硬拒收整个仓库                    | `待填写`         |
| 是否可以仅跳过异类文件                    | `待填写`         |
| Gateway 扫描规则                   | `待填写`         |
| 最终状态                           | `NOT_STARTED` |
| 可信度                            | `NONE`        |




### B.1 入队规则

- [ ] 命中 `*.csproj` 时拒收
- [ ] 命中 `*.gdextension` 时拒收
- [ ] 命中 `*.gdnlib` 时拒收
- [ ] 仅跳过异类文件
- [ ] 允许进入，但在报告中标记环境不完整
- [ ] 其他：`待填写`

---



# P1-13 · N14 并发 import 污染



## A. 数据记录

> 由 runner 生成，勿手填。证据见 `artifacts/<run-id>/index.md`。



### A.1 串行控制组


| 运行       | 指令  | Exit code | Wall time | Cache hash | 后续 PROJECT_CHECK | 日志  |
| -------- | --- | --------- | --------- | ---------- | ---------------- | --- |
| Serial-1 | V3  |           |           |            |                  |     |
| Serial-2 | V3  |           |           |            |                  |     |




### A.2 并发组


| 进程           | 启动时间 | 结束时间 | Exit code | Signal | 错误  | 日志  |
| ------------ | ---- | ---- | --------- | ------ | --- | --- |
| Concurrent-A |      |      |           |        |     |     |
| Concurrent-B |      |      |           |        |     |     |




### A.3 Cache 完整性


| 检查项                                  | 串行组 | 并发组 | 是否异常 |
| ------------------------------------ | --- | --- | ---- |
| `.godot/` 文件数                        |     |     |      |
| `global_script_class_cache.cfg` hash |     |     |      |
| Import cache 文件缺失                    |     |     |      |
| 临时文件残留                               |     |     |      |
| 后续 PROJECT_CHECK                     |     |     |      |
| 后续 V3                                |     |     |      |




## B. 实验结果分析


| 分析项                  | 判断            |
| -------------------- | ------------- |
| 并发 import 是否产生错误     | `待填写`         |
| 是否产生 cache 损坏        | `待填写`         |
| 是否产生非确定性差异           | `待填写`         |
| 是否确认必须使用 workspace 锁 | `待填写`         |
| 锁的理由是数据安全还是资源控制      | `待填写`         |
| 最终状态                 | `NOT_STARTED` |
| 可信度                  | `NONE`        |


---



# 第一阶段综合结论



## 3.1 Verifier 能力配置


| 项目                  | 最终结论  |
| ------------------- | ----- |
| `PROJECT_CHECK`     | `待填写` |
| Exit code 可否直接使用    | `待填写` |
| 是否强制 WARM           | `待填写` |
| 何时触发 V3             | `待填写` |
| 是否使用 V5 交叉验证        | `待填写` |
| 是否允许 `--debug`      | `待填写` |
| Warning 是否采集        | `待填写` |
| Shader 是否覆盖         | `待填写` |
| C#/GDExtension 是否拒收 | `待填写` |
| 是否要求 workspace 锁    | `待填写` |




## 3.2 第一阶段确认的噪声


| N   | 噪声                          | 是否确认 | 规避/过滤策略 | 证据  |
| --- | --------------------------- | ---- | ------- | --- |
| N01 | autoload FP                 |      |         |     |
| N02 | addon singleton FP          |      |         |     |
| N03 | global class cache          |      |         |     |
| N04 | cascade amplification       |      |         |     |
| N05 | warning severity            |      |         |     |
| N06 | invalid UID severity        |      |         |     |
| N07 | shader blind spot           |      |         |     |
| N08 | exit code/command semantics |      |         |     |
| N09 | nondeterminism              |      |         |     |
| N10 | debug hang/crash            |      |         |     |
| N12 | stale cache                 |      |         |     |
| N13 | alien environment pollution |      |         |     |
| N14 | concurrent import pollution |      |         |     |


---



# 第二阶段 · Godot 3.5/3.6 官方 Demo 自动迁移

---



# P2-01 · N15 Converter CLI 能力门



## A. 数据记录

> 由 runner 生成，勿手填。证据见 `artifacts/<run-id>/index.md`。



### A.1 Help 输出能力


| 能力                           | Help 中存在 | 精确参数说明 | 证据  |
| ---------------------------- | -------- | ------ | --- |
| `--validate-conversion-3to4` |          | `待填写`  |     |
| `--convert-3to4`             |          | `待填写`  |     |
| `max_file_kb` 参数             |          | `待填写`  |     |
| `max_line_size` 参数           |          | `待填写`  |     |
| `upgrade` 相关命令               |          | `待填写`  |     |




### A.2 最小项目调用


| 指令          | 是否成功启动 | Exit code | 是否修改项目 | 输出  | 日志  |
| ----------- | ------ | --------- | ------ | --- | --- |
| validate    |        |           | 否/待填   |     |     |
| convert     |        |           |        |     |     |
| convert 带参数 |        |           |        |     |     |




## B. 实验结果分析


| 分析项                     | 判断            |
| ----------------------- | ------------- |
| 官方 4.7.1 是否包含 converter | `待填写`         |
| 参数是否可用                  | `待填写`         |
| 是否需要第二个 Godot 二进制       | `待填写`         |
| 是否需要自建 rename L0        | `待填写`         |
| 后续实验是否解除 BLOCKED        | `待填写`         |
| 最终状态                    | `NOT_STARTED` |
| 可信度                     | `NONE`        |




### B.1 Converter profile

```yaml
# 待填写
converter:
  executable:
  version:
  build_hash:
  validate_command:
  convert_command:
  supports_limits:
```

---



# P2-02 · N16 ProjectUpgradeTool 职责边界



## A. 数据记录

> 由 runner 生成，勿手填。证据见 `artifacts/<run-id>/index.md`。



### A.1 工具可用性


| 检查项                 | 结果    | 证据  |
| ------------------- | ----- | --- |
| Help 中存在 upgrade 命令 | `待填写` |     |
| 可在 headless CLI 使用  | `待填写` |     |
| 仅编辑器 GUI 可用         | `待填写` |     |
| 命令参数                | `待填写` |     |




### A.2 隔离工作区职责矩阵


| 文件/变化类型             | Converter 组 | Upgrade Tool 组 | `--import` 组 |
| ------------------- | ----------- | -------------- | ------------ |
| GDScript API rename |             |                |              |
| `.tscn` 重保存         |             |                |              |
| `.tres` 重保存         |             |                |              |
| UID 生成/重建           |             |                |              |
| 资源路径更新              |             |                |              |
| Import cache        |             |                |              |
| Shader 修改           |             |                |              |




### A.3 文件 diff


| 组别           | 修改文件数 | 新增  | 删除  | 重命名 | Diff |
| ------------ | ----- | --- | --- | --- | ---- |
| Converter    |       |     |     |     |      |
| Upgrade Tool |       |     |     |     |      |
| Import       |       |     |     |     |      |




## B. 实验结果分析


| 分析项                        | 判断            |
| -------------------------- | ------------- |
| ProjectUpgradeTool 是否有 CLI | `待填写`         |
| 是否修改 GDScript              | `待填写`         |
| 是否负责 UID/资源重保存             | `待填写`         |
| `--import` 是否可近似替代         | `待填写`         |
| 标准迁移流水线                    | `待填写`         |
| 已知无法覆盖的职责                  | `待填写`         |
| 最终状态                       | `NOT_STARTED` |
| 可信度                        | `NONE`        |




### B.1 第二阶段标准流水线

```text
待填写，例如：

converter
  → ProjectUpgradeTool
  → V3 import
  → PROJECT_CHECK
```

---



# P2-03 · N11 大文件跳过、阈值和 hang



## A. 数据记录

> 由 runner 生成，勿手填。证据见 `artifacts/<run-id>/index.md`。



### A.1 输入文件


| 文件            | 大小  | 行数  | 最大单行长度 | 是否超过默认阈值 |
| ------------- | --- | --- | ------ | -------- |
| `small.gd`    |     |     |        | 否        |
| `big.gd`      |     |     |        |          |
| `longline.gd` |     |     |        |          |




### A.2 默认参数组


| 文件            | Validate 是否报告 | Convert 是否修改 | 是否明确跳过 | 是否静默跳过 | 是否 timeout | Diff/Log |
| ------------- | ------------- | ------------ | ------ | ------ | ---------- | -------- |
| `small.gd`    |               |              |        |        |            |          |
| `big.gd`      |               |              |        |        |            |          |
| `longline.gd` |               |              |        |        |            |          |




### A.3 提高阈值组


| 参数              | 实测值   |
| --------------- | ----- |
| `max_file_kb`   | `待填写` |
| `max_line_size` | `待填写` |



| 文件            | Convert 是否修改 | 与默认组差异 | 是否 timeout | Diff/Log |
| ------------- | ------------ | ------ | ---------- | -------- |
| `small.gd`    |              |        |            |          |
| `big.gd`      |              |        |            |          |
| `longline.gd` |              |        |            |          |




### A.4 进程行为


| 组别           | Wall time | Exit code | Signal | Timeout | 残留进程 |
| ------------ | --------- | --------- | ------ | ------- | ---- |
| Validate     |           |           |        |         |      |
| 默认 Convert   |           |           |        |         |      |
| 提高阈值 Convert |           |           |        |         |      |




## B. 实验结果分析


| 分析项                            | 判断            |
| ------------------------------ | ------------- |
| 默认最大文件阈值                       | `待填写`         |
| 默认最大行长度阈值                      | `待填写`         |
| 参数是否生效                         | `待填写`         |
| 是否存在静默跳过                       | `待填写`         |
| 是否复现 hang                      | `待填写`         |
| Converter 是否必须包 timeout/killpg | `待填写`         |
| 入队前是否必须预扫描大文件                  | `待填写`         |
| 最终状态                           | `NOT_STARTED` |
| 可信度                            | `NONE`        |


---



# P2-04 · N17 TODO 与 `instance()` 转换覆盖率



## A. 数据记录

> 由 runner 生成，勿手填。证据见 `artifacts/<run-id>/index.md`。



### A.1 埋点逐项分类


| 埋点 ID | 原始调用                             | 转换结果 | TODO | 是否保留旧值 | 分类  | Diff |
| ----- | -------------------------------- | ---- | ---- | ------ | --- | ---- |
| A7-01 | `move_and_slide_with_snap(...)`  |      |      |        |     |      |
| A2-01 | `preload(...).instance()`        |      |      |        |     |      |
| A2-02 | `pk.instance()`                  |      |      |        |     |      |
| A2-03 | `get_node(...).scene.instance()` |      |      |        |     |      |
| A7-02 | `yield(...)`                     |      |      |        |     |      |
| A7-03 | Tween API                        |      |      |        |     |      |
| A7-04 | `OS.get_ticks_msec()`            |      |      |        |     |      |


分类取值：

- `CORRECTLY_CONVERTED`
- `TODO_AND_PRESERVED`
- `UNTOUCHED`
- `INCORRECTLY_CONVERTED`
- `NEEDS_MANUAL_REVIEW`



### A.2 汇总


| 分类         | 数量  | 占比  |
| ---------- | --- | --- |
| 正确转换       |     |     |
| TODO 后保留旧值 |     |     |
| 完全未动       |     |     |
| 错误转换       |     |     |
| 需人工判断      |     |     |




### A.3 `instance()` 覆盖率


| 指标                | 数值  |
| ----------------- | --- |
| `instance()` 总埋点数 |     |
| 正确转换数             |     |
| 部分转换数             |     |
| 未转换数              |     |
| 错误转换数             |     |
| 覆盖率               |     |




## B. 实验结果分析


| 分析项                        | 判断            |
| -------------------------- | ------------- |
| `TODOConverter3To4` 是否存在   | `待填写`         |
| TODO 是否稳定、可机器解析            | `待填写`         |
| 是否存在“可编译但语义未迁移”            | `待填写`         |
| `instance()` 覆盖率是否足够       | `待填写`         |
| 是否需要自建 `.instance()` L0 规则 | `待填写`         |
| TODO 是否进入 Agent 待办队列       | `待填写`         |
| Agent-as-Judge 是否为刚性需求     | `待填写`         |
| 最终状态                       | `NOT_STARTED` |
| 可信度                        | `NONE`        |


---



# P2-05 · N18 Shader 转换正确性



## A. 数据记录

> 由 runner 生成，勿手填。证据见 `artifacts/<run-id>/index.md`。



### A.1 文件级结果


| 检查项                 | 转换前          | 转换后 | 是否正确 | 证据  |
| ------------------- | ------------ | --- | ---- | --- |
| 文件扩展名               | `.shader`    |     |      |     |
| Shader 文件内容         | 3.x 语法       |     |      |     |
| `hint_albedo`       | 存在           |     |      |     |
| `.tres` 引用路径        | `old.shader` |     |      |     |
| Converter stdout 报告 | —            |     |      |     |




### A.2 报告与实际变更一致性


| Converter 声称 | 文件实际变化 | 引用实际变化 | 判定    |
| ------------ | ------ | ------ | ----- |
| `待填写`        | `待填写`  | `待填写`  | `待填写` |




### A.3 转换后验证


| 指令                  | 是否报 shader 错误 | 是否报资源引用错误 | Exit code | 日志  |
| ------------------- | ------------- | --------- | --------- | --- |
| V3                  |               |           |           |     |
| N07 确定的 shader 检测路径 |               |           |           |     |




## B. 实验结果分析


| 分析项                  | 判断            |
| -------------------- | ------------- |
| `.shader` 是否正确改名     | `待填写`         |
| Shader 语法是否正确升级      | `待填写`         |
| 资源引用是否同步更新           | `待填写`         |
| Converter 报告是否可信     | `待填写`         |
| 是否复现“谎报已转换”          | `待填写`         |
| 是否必须自行 diff 校验       | `待填写`         |
| Shader 是否归入 escalate | `待填写`         |
| 最终状态                 | `NOT_STARTED` |
| 可信度                  | `NONE`        |


---



# P2-06 · N20 Mutation 评测泄漏



## A. 数据记录

> 由 runner 生成，勿手填。证据见 `artifacts/<run-id>/index.md`。

每个算子独立工作区。步骤固定为：`config_version` 5→4 降级（本身记为实验的一部分）→ 施加单个变异 → converter。基线 fixture 是健康 4.x（`config_version=5`）；降级失败则 N20 标记 BLOCKED。

### A.1 算子结果


| Operator               | 变异内容                 | Converter 结果 | Verifier 结果 | 分类  | Diff/Log |
| ---------------------- | -------------------- | ------------ | ----------- | --- | -------- |
| `instantiate2instance` | `instantiate()` 反向变异 |              |             |     |          |
| `ticks_msec`           | 时间 API 反向变异          |              |             |     |          |
| `await2yield`          | `await` → `yield`    |              |             |     |          |
| `tween_api`            | Tween 反向变异           |              |             |     |          |
| `export_var`           | export 语法变异          |              |             |     |          |
| `onready`              | onready 语法变异         |              |             |     |          |
| `connect_api`          | Signal connect API   |              |             |     |          |
| `node_rename`          | 节点/API 改名            |              |             |     |          |
| `move_and_slide`       | 物理 API               |              |             |     |          |
| `param_order`          | 参数顺序变异               |              |             |     |          |


分类取值：

- `RESTORED_BY_CONVERTER`
- `PARTIALLY_RESTORED`
- `SURVIVES`
- `CORRUPTED`
- `NEEDS_MANUAL_REVIEW`



### A.2 汇总


| 分类             | 数量  | 占比  |
| -------------- | --- | --- |
| Converter 完全复原 |     |     |
| 部分复原           |     |     |
| 保留变异           |     |     |
| 转换后进一步损坏       |     |     |
| 需人工判断          |     |     |




## B. 实验结果分析


| 分析项               | 判断            |
| ----------------- | ------------- |
| 是否存在评测泄漏          | `待填写`         |
| 哪些算子应归入 L0 组      | `待填写`         |
| 哪些算子可作为 Agent 主考题 | `待填写`         |
| 哪些算子需要语义 Judge    | `待填写`         |
| 是否需要重构基准集         | `待填写`         |
| 最终状态              | `NOT_STARTED` |
| 可信度               | `NONE`        |




### B.1 最终基准分组


| 分组               | Operators |
| ---------------- | --------- |
| L0 Converter 验证组 | `待填写`     |
| Agent 解析修复组      | `待填写`     |
| Agent 语义修复组      | `待填写`     |
| 人工评审组            | `待填写`     |


---



# P2-07 · N21-A 官方 Demo 来源冻结、转换与快照



## A. 数据记录

> 由 runner 生成，勿手填。证据见 `artifacts/<run-id>/index.md`。



### A.1 Demo 数据集清单


| Demo ID | 名称     | Godot 源版本 | Tag/Commit | Source URL | 文件数 | 总大小 | 状态            |
| ------- | ------ | --------- | ---------- | ---------- | --- | --- | ------------- |
| D001    | `待填写`  | 3.5/3.6   | `待填写`      | `待填写`      |     |     | `NOT_STARTED` |
| D002    | `待填写`  | 3.5/3.6   | `待填写`      | `待填写`      |     |     | `NOT_STARTED` |
| D003    | `按需增加` | `待填写`     | `待填写`      | `待填写`      |     |     | `NOT_STARTED` |




### A.2 来源完整性


| Demo ID | Source tree hash | Git clean | 原始 `.godot/` 已移除 | 来源冻结证据 |
| ------- | ---------------- | --------- | ---------------- | ------ |
| D001    |                  |           |                  |        |
| D002    |                  |           |                  |        |




### A.3 转换执行结果


| Demo ID | Validate rc | Convert rc | Wall time | 修改文件 | 新增  | 删除  | 重命名 | TODO 数 | 跳过文件 | Timeout/Crash |
| ------- | ----------- | ---------- | --------- | ---- | --- | --- | --- | ------ | ---- | ------------- |
| D001    |             |            |           |      |     |     |     |        |      |               |
| D002    |             |            |           |      |     |     |     |        |      |               |




### A.4 转换后标准步骤


| Demo ID | Upgrade Tool | V3 import | UID 重建 | Snapshot hash | Snapshot 路径 | 日志  |
| ------- | ------------ | --------- | ------ | ------------- | ----------- | --- |
| D001    |              |           |        |               | `待填写`       |     |
| D002    |              |           |        |               | `待填写`       |     |




### A.5 与官方 4.x Demo 的弱参考比较


| Demo ID | 对应 4.x Demo | 同名文件比例 | 删除比例 | 新增比例 | 重命名比例 | 是否可作强 GT |
| ------- | ----------- | ------ | ---- | ---- | ----- | -------- |
| D001    | `待填写`       |        |      |      |       |          |
| D002    | `待填写`       |        |      |      |       |          |




## B. 实验结果分析


| 分析项                            | 判断            |
| ------------------------------ | ------------- |
| Demo 来源是否可复现                   | `待填写`         |
| 转换是否全部完成                       | `待填写`         |
| 是否存在跳过或 timeout                | `待填写`         |
| 转换快照是否成功冻结                     | `待填写`         |
| 官方 4.x Demo 是否可作强 ground truth | `待填写`         |
| 哪些 Demo 需要剔除                   | `待填写`         |
| 哪些 Demo 可以进入残余统计               | `待填写`         |
| N21-A 状态                       | `NOT_STARTED` |
| 可信度                            | `NONE`        |


---



# P2-08 · N19 自动迁移后 Import 成本



## A. 数据记录

> 由 runner 生成，勿手填。证据见 `artifacts/<run-id>/index.md`。



### A.1 每个 Demo 的 COLD/WARM 时间


| Demo ID | 文件数 | 资源数 | 总大小 | Cache | Repeat | V3 wall time | Exit code | Peak RSS |
| ------- | --- | --- | --- | ----- | ------ | ------------ | --------- | -------- |
| D001    |     |     |     | COLD  | 3      |              |           |          |
| D001    |     |     |     | WARM  | 3      |              |           |          |
| D002    |     |     |     | COLD  | 3      |              |           |          |
| D002    |     |     |     | WARM  | 3      |              |           |          |




### A.2 汇总统计


| Demo ID | COLD 平均 | COLD P95 | WARM 平均 | WARM P95 | 冷热比 | 方差  | 失败率 |
| ------- | ------- | -------- | ------- | -------- | --- | --- | --- |
| D001    |         |          |         |          |     |     |     |
| D002    |         |          |         |          |     |     |     |
| 总体      |         |          |         |          |     |     |     |




### A.3 规模相关性


| 指标             | 与 import 时间的观察关系 |
| -------------- | ---------------- |
| 文件数            | `待填写`            |
| 资源数            | `待填写`            |
| 项目总大小          | `待填写`            |
| Shader 数       | `待填写`            |
| 音频/纹理资源        | `待填写`            |
| `class_name` 数 | `待填写`            |




## B. 实验结果分析


| 分析项                 | 判断            |
| ------------------- | ------------- |
| Import 是否为主要迭代成本    | `待填写`         |
| COLD/WARM 差异是否显著    | `待填写`         |
| 是否需要 cache snapshot | `待填写`         |
| 是否需要条件性 import      | `待填写`         |
| 是否需要 workspace 预热   | `待填写`         |
| 建议的单轮时间预算           | `待填写`         |
| 最终状态                | `NOT_STARTED` |
| 可信度                 | `NONE`        |


---



# P2-09 · N21-B 官方 Demo 残余问题统计



## A. 数据记录

> 由 runner 生成，勿手填。证据见 `artifacts/<run-id>/index.md`。



### A.1 每个 Demo 的 Verifier 结果


| Demo ID | PROJECT_CHECK | Parse | Compile | Import/Resource | UID | Shader | Runtime | Warning | Infra failure |
| ------- | ------------- | ----- | ------- | --------------- | --- | ------ | ------- | ------- | ------------- |
| D001    |               |       |         |                 |     |        |         |         |               |
| D002    |               |       |         |                 |     |        |         |         |               |
| 总计      |               |       |         |                 |     |        |         |         |               |




### A.2 原始错误与根因去重


| Demo ID | 原始错误行 | 归一化 signature | 根因簇 | 级联症状 | FP  | FN/盲区 |
| ------- | ----- | ------------- | --- | ---- | --- | ----- |
| D001    |       |               |     |      |     |       |
| D002    |       |               |     |      |     |       |
| 总计      |       |               |     |      |     |       |




### A.3 Converter 行为分布


| 类别      | 数量  | 占比  | 代表案例  | 证据  |
| ------- | --- | --- | ----- | --- |
| 正确转换    |     |     | `待填写` |     |
| 部分转换    |     |     | `待填写` |     |
| 插入 TODO |     |     | `待填写` |     |
| 明确跳过    |     |     | `待填写` |     |
| 静默跳过    |     |     | `待填写` |     |
| 错误转换    |     |     | `待填写` |     |
| 谎报已转换   |     |     | `待填写` |     |
| Timeout |     |     | `待填写` |     |
| Crash   |     |     | `待填写` |     |
| 破坏性修改   |     |     | `待填写` |     |




### A.4 根因类别分布


| 根因类别               | 根因簇数 | 占全部根因 | 涉及 Demo 数 | 自动修复候选 | 需要 Judge | 需要人工 |
| ------------------ | ---- | ----- | --------- | ------ | -------- | ---- |
| API rename         |      |       |           |        |          |      |
| 方法签名变化             |      |       |           |        |          |      |
| 参数顺序变化             |      |       |           |        |          |      |
| `instance()`       |      |       |           |        |          |      |
| `yield`/`await`    |      |       |           |        |          |      |
| Tween              |      |       |           |        |          |      |
| 生命周期变化             |      |       |           |        |          |      |
| 节点/属性改名            |      |       |           |        |          |      |
| Signal/connect API |      |       |           |        |          |      |
| Scene/resource 序列化 |      |       |           |        |          |      |
| UID                |      |       |           |        |          |      |
| Shader             |      |       |           |        |          |      |
| Autoload/addon     |      |       |           |        |          |      |
| C#/GDExtension     |      |       |           |        |          |      |
| 二进制资源              |      |       |           |        |          |      |
| Converter 缺陷       |      |       |           |        |          |      |
| 4.0→4.7 漂移         |      |       |           |        |          |      |
| 未分类                |      |       |           |        |          |      |




### A.5 版本漂移归类


| Bucket           | 数量  | 占比  | 判定依据  |
| ---------------- | --- | --- | ----- |
| 3.x → 4.0 基础迁移残余 |     |     | `待填写` |
| 4.0 → 4.7 API 漂移 |     |     | `待填写` |
| Converter 自身缺陷   |     |     | `待填写` |
| Demo 上游结构性重写     |     |     | `待填写` |
| 无法判断             |     |     | `待填写` |




### A.6 严重度分布


| 严重度                   | 数量  | 占比  | 是否阻塞          |
| --------------------- | --- | --- | ------------- |
| Fatal/Crash           |     |     | 是             |
| Parse Error           |     |     | 是             |
| Compile Error         |     |     | 是             |
| Import/Resource Error |     |     | 视结果           |
| Runtime Error         |     |     | 是             |
| Warning               |     |     | 否             |
| TODO/Semantic Risk    |     |     | 不阻塞解析，但阻塞迁移完成 |
| Infra Failure         |     |     | 不得算作修复失败      |




### A.7 可处理性分布


| 处理方式              | 数量  | 占比  |
| ----------------- | --- | --- |
| 机械 L0 规则可修复       |     |     |
| Agent 可依据错误直接修复   |     |     |
| 需要 RAG            |     |     |
| 需要 Agent-as-Judge |     |     |
| 需要人工              |     |     |
| 不支持               |     |     |




### A.8 代表性残余案例


| Case ID | Demo | 文件  | 原始消息 | 根因  | Converter 是否修改 | 最终归类 | 证据  |
| ------- | ---- | --- | ---- | --- | -------------- | ---- | --- |
| C001    |      |     |      |     |                |      |     |
| C002    |      |     |      |     |                |      |     |
| C003    |      |     |      |     |                |      |     |




## B. 实验结果分析



### B.1 总体迁移效果


| 指标                       | 结果    |
| ------------------------ | ----- |
| Demo 总数                  | `待填写` |
| 成功完成 converter 的 Demo    | `待填写` |
| Converter 后直接通过 verifier | `待填写` |
| 至少存在一个阻塞根因的 Demo         | `待填写` |
| 需要人工处理的 Demo             | `待填写` |
| 平均每个 Demo 的根因簇数          | `待填写` |
| 中位根因簇数                   | `待填写` |
| P95 根因簇数                 | `待填写` |
| TODO 总数                  | `待填写` |
| 语义风险总数                   | `待填写` |




### B.2 核心判断


| 分析项                  | 判断            |
| -------------------- | ------------- |
| 官方 converter 的总体覆盖率  | `待填写`         |
| 最常见残余问题              | `待填写`         |
| 最昂贵残余问题              | `待填写`         |
| 最常见 verifier 噪声      | `待填写`         |
| 最严重 verifier 盲区      | `待填写`         |
| 3→4.0 与 4.0→4.7 问题比例 | `待填写`         |
| 是否支持“解析清零 = 迁移完成”    | 否；具体证据待填写     |
| RAG 应优先覆盖的主题         | `待填写`         |
| Agent 应优先处理的错误类型     | `待填写`         |
| 必须 escalate 的类型      | `待填写`         |
| N21 最终状态             | `NOT_STARTED` |
| 可信度                  | `NONE`        |




### B.3 支持边界



#### 自动支持

- `待填写`



#### 有条件支持

- `待填写`



#### 必须人工审核

- `待填写`



#### 明确不支持

- `待填写`

---



# 第二阶段综合结论



## 4.1 Converter 能力边界


| 能力                      | 结论    |
| ----------------------- | ----- |
| CLI 是否可用                | `待填写` |
| 大文件是否覆盖                 | `待填写` |
| 是否存在静默跳过                | `待填写` |
| 是否支持 TODO 输出            | `待填写` |
| `instance()` 覆盖率        | `待填写` |
| Shader 转换是否可靠           | `待填写` |
| Converter 报告是否可信        | `待填写` |
| 是否需要 ProjectUpgradeTool | `待填写` |
| 是否需要自建 L0 规则            | `待填写` |




## 4.2 官方 Demo 残余问题 Top 10


| 排名  | 类别    | 根因簇数 | 占比  | 建议处理层 |
| --- | ----- | ---- | --- | ----- |
| 1   | `待填写` |      |     | `待填写` |
| 2   | `待填写` |      |     | `待填写` |
| 3   | `待填写` |      |     | `待填写` |
| 4   | `待填写` |      |     | `待填写` |
| 5   | `待填写` |      |     | `待填写` |
| 6   | `待填写` |      |     | `待填写` |
| 7   | `待填写` |      |     | `待填写` |
| 8   | `待填写` |      |     | `待填写` |
| 9   | `待填写` |      |     | `待填写` |
| 10  | `待填写` |      |     | `待填写` |


---



# 5. 跨实验决策表


| 决策                  | 依赖实验            | 最终选择  | 证据  |
| ------------------- | --------------- | ----- | --- |
| 项目级 verifier 命令     | N08             | `待填写` |     |
| Signature 结构        | N09、N04         | `待填写` |     |
| 是否强制 warm-up        | N03、N01         | `待填写` |     |
| 条件性 import 规则       | N03、N06、N12、N19 | `待填写` |     |
| Autoload FP 过滤      | N01、N02         | `待填写` |     |
| Warning 获取方式        | N05、N10         | `待填写` |     |
| UID 处理方式            | N06、N16         | `待填写` |     |
| Shader 验证方式         | N07、N18         | `待填写` |     |
| C#/GDExtension 入队规则 | N13             | `待填写` |     |
| Workspace 锁         | N14             | `待填写` |     |
| Converter timeout   | N11             | `待填写` |     |
| Agent 基准算子          | N20             | `待填写` |     |
| RAG 语料优先级           | N17、N21         | `待填写` |     |
| 人工升级边界              | N07、N13、N18、N21 | `待填写` |     |


---



# 6. 最终系统配置草案

> 仅在所有相关实验结束后填写。

```yaml
godot:
  version: "待填写"
  build_hash: "待填写"

verifier:
  project_check: "待填写"
  require_warm_cache: null
  use_runtime_cross_check: null
  enable_warnings: null
  allow_debug: false
  timeout_seconds: null
  use_process_group: true

signature:
  local:
    include: [kind, res_path, symbol, normalized_message]
    exclude: [line_number, absolute_path, memory_address, timing_value]
  noise:
    include: [kind, msg_template]
    exclude: [res_path, symbol, line_number, absolute_path, memory_address, timing_value, numeric_value]
  sort_as_set: true

import_policy:
  class_name_added: null
  class_name_modified: null
  gd_file_added: null
  ordinary_gd_body_changed: null
  scene_resource_changed: null
  uid_changed: null

noise_filters:
  autoload: "待填写"
  addon_singleton: "待填写"
  invalid_uid: "待填写"
  cascade_symptoms: "待填写"

gateway:
  reject_csproj: null
  reject_gdextension: null
  reject_binary_resources: null
  reject_large_files: null

converter:
  executable: "待填写"
  timeout_seconds: null
  max_file_kb: null
  max_line_size: null
  require_prescan: null
  verify_with_diff: true

concurrency:
  workspace_lock_required: null
  max_parallel_godot_processes: null
```

---



# 7. 最终结论



## 7.1 已确认

- `待填写；每条必须引用实验编号和日志。`



## 7.2 未复现

- `待填写；必须注明环境、重复次数和缓存状态。`



## 7.3 尚无定论

- `待填写；说明缺少什么证据。`



## 7.4 被环境阻塞

- `待填写。`



## 7.5 产品和架构结论

- `待填写。`



## 7.6 最终结论摘要

```text
待填写。

建议至少回答以下问题：

1. Godot 4.7.1 下可靠的 verifier 组合是什么？
2. 哪些输出是已确认的假阳性？
3. 哪些错误类别是 verifier 的盲区？
4. 哪些 patch 必须触发 re-import？
5. 官方 converter 对 Godot 3.5/3.6 Demo 的实际覆盖率如何？
6. 自动迁移后的主要残余问题是什么？
7. 哪些问题可以由机械规则修复？
8. 哪些问题需要 Agent、RAG、Judge 或人工？
9. “解析清零”和“迁移完成”之间还存在多大差距？
10. 系统明确不支持哪些仓库或资源类型？
```

---



# 附录 A · 实验执行顺序

```text
第一阶段：
N09
→ N08
→ N03
→ N01
→ N02
→ N10
→ N04
→ N05
→ N06
→ N12
→ N07
→ N13
→ N14

第二阶段：
N15
→ N16
→ N11
→ N17
→ N18
→ N20
→ N21-A（来源冻结、转换、快照）
→ N19（从冻结快照测 import）
→ N21-B（从冻结快照执行 verifier 和残余统计）
```

---

