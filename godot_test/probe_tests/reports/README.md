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


| 状态                        | 含义              |
| ------------------------- | --------------- |
| `NOT_STARTED` / `RUNNING` | 尚未开始 / 正在执行     |
| `CONFIRMED`               | 现象稳定复现，证据充分     |
| `PARTIAL`                 | 只确认了实验中的一部分现象   |
| `NOT_REPRODUCED`          | 按计划执行后未复现       |
| `INCONCLUSIVE`            | 结果不稳定或证据不足      |
| `BLOCKED`                 | 因环境、工具或上游依赖无法执行 |


可信度：`HIGH`（多次重复一致 + 对照正常 + 缓存态明确）、`MEDIUM`（日志完整但重复不足或依赖人工判断）、`LOW`（单次观察或无可靠对照）、`NONE`（尚无结论）。

---



# 1. 环境



## 1.1 元数据


| 字段                    | 实测值                                                                                                  |
| --------------------- | ---------------------------------------------------------------------------------------------------- |
| 报告版本                  | `0.2.0`                                                                                              |
| 最后更新                  | `2026-08-22 00:05 +0800`                                                                             |
| 执行人员                  | `yy_catmax`（git: `shanghuaye504-byte <shanghuaye504@gmail.com>`）                                     |
| 操作系统 / 架构             | `macOS 26.3.1`（Darwin 25.3.0）/ `arm64`，`sysctl.proc_translated=0`                                    |
| Python                | `3.13.9`（`/Users/yy_catmax/miniconda3/bin/python`）                                                   |
| Godot 可执行文件           | `/usr/local/bin/godot4` → `Godot.app/Contents/MacOS/Godot`                                           |
| Godot 版本 / build hash | `4.7.1.stable.official.a13da4feb` / `a13da4feb`（二进制 sha1 `9fab64a7acbe2af2690e3ac7c3249b40363b76bb`） |
| 构建来源                  | 官方构建（Developer ID `Prehensile Tales B.V.`，Gatekeeper `Notarized Developer ID`）                       |
| 环境预检 Run ID           | `env-preflight-20260821-180807`（旧预检 `env-preflight-20260821-105347` 保留为历史）                           |




## 1.2 环境校验

证据目录：`artifacts/env-preflight-20260821-180807/`。


| 检查项                    | 结果                                                                                                                  | 状态                                                     |
| ---------------------- | ------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------ |
| Godot 版本与 headless 冒烟  | `4.7.1.stable.official.a13da4feb`；CleanControl 副本 `--headless --quit` 退出码 0，stdout 含 `CLEAN_OK`                     | `CONFIRMED`                                            |
| 二进制架构                  | universal（`x86_64`+`arm64`），未走 Rosetta                                                                              | `CONFIRMED`                                            |
| macOS quarantine 不阻止执行 | 带 `com.apple.quarantine` 但 `spctl` 为 `accepted`；`--version` 与冒烟均 exit 0                                             | `CONFIRMED`                                            |
| Fixture git 状态 clean   | 99 个文件已入库，`git status` / `git diff` 空                                                                               | `CONFIRMED`                                            |
| Fixture 中无 `.godot/`   | 计数 1：`CleanControl/.godot/` 已被跟踪入库，不是冒烟写回的                                                                          | `PARTIAL`                                              |
| artifacts 位于 fixture 外 | `artifacts/` 与 `fixtures/` 为兄弟目录                                                                                    | `CONFIRMED`                                            |
| 采集侧支持进程组终止             | 旧 `runner/kernel/process.py` 已验证 `start_new_session=True` + `killpg`，Fake hang 测得 `timed_out=True`、signal 9、无残留 pid | `CONFIRMED`（**架构改为** `experiments/util` **后必须重跑同一检查**） |


---



# 2. 看板

顺序即执行顺序。实验设计与步骤表见 [../README.md](../README.md) 第 4、5 层；本轮裁剪掉的实验及其先验结论见该文 §2.3，不在本报告出现。

## 2.1 第一阶段（9 条）


| 执行序  | 实验  | 主题                           | 状态            | 核心结论  | 可信度    |
| ---- | --- | ---------------------------- | ------------- | ----- | ------ |
| P1-1 | N09 | 非确定性与归一化                     | `NOT_STARTED` | `待填写` | `NONE` |
| P1-2 | N08 | exit code、启动语义、`--debug` 存活性 | `NOT_STARTED` | `待填写` | `NONE` |
| P1-3 | N03 | `class_name` 冷缓存与 import 触发  | `NOT_STARTED` | `待填写` | `NONE` |
| P1-4 | N01 | autoload 假阳性                 | `NOT_STARTED` | `待填写` | `NONE` |
| P1-5 | N02 | addon 单例假阳性                  | `NOT_STARTED` | `待填写` | `NONE` |
| P1-6 | N04 | 级联错误与根因放大                    | `NOT_STARTED` | `待填写` | `NONE` |
| P1-7 | N05 | warning 与 error 严重度          | `NOT_STARTED` | `待填写` | `NONE` |
| P1-8 | N06 | invalid UID 严重度与资源引用变更       | `NOT_STARTED` | `待填写` | `NONE` |
| P1-9 | N07 | shader verifier 盲区           | `NOT_STARTED` | `待填写` | `NONE` |




## 2.2 第二阶段（2 条）


| 执行序  | 实验  | 主题                           | 状态            | 核心结论  | 可信度    |
| ---- | --- | ---------------------------- | ------------- | ----- | ------ |
| P2-1 | N15 | converter 与 upgrade tool 能力门 | `NOT_STARTED` | `待填写` | `NONE` |
| P2-2 | N21 | 官方 Demo 自动迁移残余分布             | `NOT_STARTED` | `待填写` | `NONE` |


---



# 3. 第一阶段结论

每节只有四块：状态行、判据实测、结论、决策。表格里填的是**判据需要的那几个值**，不是全部测量数据。

---



## P1-1 · N09 非确定性与归一化

`NOT_STARTED` · 可信度 `NONE` · 证据 `artifacts/n09-20260821/N09/` → `reports/n09-20260821/N09/stability/`


| 判据                                         | 实测                                                                                                                                                                                                                      |
| ------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 重复间行集合是否一致（内容确定性）                          | `完全一致`                                                                                                                                                                                                                  |
| 重复间输出顺序是否一致                                | `完全一致`                                                                                                                                                                                                                  |
| 出现哪些动态字段（绝对路径 / 行号 / 内存地址 / 随机 ID / 耗时数字）  | `无绝对路径，无随机地址，无时间数字，但是需要注意的是有行号，这个行号信息在修改代码后会动态变化，不能作为新增错误的判据，但是行号信息要传给llm作为信号。确认报错中的地址全是相对的，无随机字段，只有报错的代码行号是一个需要注意后期去噪的字段。``但是要注意ERROR后面跟的是系统代码中抓到的错误，行号固定。而SCRIPT ERROR后面跟的是项目脚本的错误，需要去除行号作为reward，但是给llm做判断时需要带上行号。` |
| 横向（CleanControl vs NP-CASCADE）暴露哪些随项目而变的字段 | `无任何随项目变化的字段，只有具体报错的代码文件名不同。确认无横向漂移，同一错误在不同的项目下的签名是一致的：但是引用的具体gd代码文件名不同。`                                                                                                                                               |
| CleanControl 背景是否漂移（BG-DRIFT）              | `已确认无漂移，每次产出的5个repeat报错的信息和顺序完全一致。`                                                                                                                                                                                     |


**结论**：`confirmed`

**决策**：两级 signature 的字段规格 → 写进 §5 `signature`。纵向发现的字段两级都抹；横向发现的字段 `local` 留、`noise` 抹；行号必须排除；error 集合按排序后的 set 比较。后续实验重复次数：`待填写`（默认 3）。

---



## P1-2 · N08 exit code、启动语义与 `--debug` 存活性

`NOT_STARTED` · 可信度 `NONE` · 证据 `artifacts/<run-id>/N08/` → `reports/<run-id>/N08/exitcode/`


| 判据                                       | 实测                                                                                                                           |
| ---------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| 干净项目 rc（期望 0）                            | `0`                                                                                                                          |
| 单文件真错 rc（期望 ≠0）                          | `0`                                                                                                                          |
| 项目级真错 rc（期望 ≠0）                          | `0`                                                                                                                          |
| 纯假阳性 rc（期望 0，标签待 N01 确认）                 | `0`                                                                                                                          |
| V8 结局：挂死 / signal 11 / 正常退出，以及是否有残留子进程   | `--debug模式确认直接崩溃，signal11复现成功，直接禁用--debug参数，不作为reward`                                                                       |
| 有坏脚本时 V5 能否启动成功（B9）                      | `有坏脚本时V5仍然可以启动rc为0，说明V5无法作为有效reward。`                                                                                        |
| V4 不带 `--editor` 能否 import；V6/V7 是否改变 rc | partial confirmed`是否带--editor模式行为完全一致，import，因此不带--editor再跑一遍import不会得出任何有效新的信息。``但是是否禁用V4，还不能定论，后期还需要运行一个实际带有资源文件的项目来观察。` |


**结论**：`脚本错误是rc仍然是0`（关键判断是“是否存在有错但 rc=0”）

**决策**：`VerifyReport.success` 用 `exit_code == 0` 还是三态 `CLEAN` / `HAS_ERRORS` / `INFRA_FAILURE` → §5 `verifier.success_source`；`--debug` 是否永久禁入、进程管理是否必须 killpg → §5 `verifier.allow_debug`、`process`。

---



## P1-3 · N03 `class_name` 冷缓存与 import 触发

`NOT_STARTED` · 可信度 `NONE` · 证据 `artifacts/<run-id>/N03/` → `reports/<run-id>/N03/sequence/`


| 判据                                           | 实测                                                                                                              |
| -------------------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| T1（COLD）是否报 `Identifier not found: ProbeFoo` | `是的，会报错`                                                                                                        |
| T3（import 后）是否干净 → 冷缓存假阳性                    | `import之后是干净的，因此V1和V2的报错是假阳性，并且的确会随着先import缓存而消除，因此修改class_name必须先运行import（V3）之后才可继续使用V1和V2当作reward，否则报错是不可靠的。` |
| T4（新增 `class_name`，不 import）是否报错             | `新增的class_name的确会报错`                                                                                            |
| T6（补 import 后）是否干净 → 缓存陈旧                    | `是，新增class_name必须重新import，否则会假阳性报错。`                                                                            |
| `global_script_class_cache.cfg` 在各步是否真的被重建   | 这个cfg的确会随着import进行重建。                                                                                           |


**结论**：`confirmed：冷启动必须先import，新增class_name必须重import。`

**决策**：是否强制 warm-up（§5 `verifier.require_warm_cache`）；`import_trigger_policy` 的 `class_name_added` / `gd_file_added` / `ordinary_gd_body_changed` 三项 → §5 `import_policy`。T4 报错则必须做条件性 import 触发器，代价是每轮 patch 多花一次 import。

---



## P1-4 · N01 autoload 假阳性

`NOT_STARTED` · 可信度 `NONE` · 证据 `artifacts/<run-id>/N01/` → `reports/<run-id>/N01/delta/`


| 判据                                                         | 实测                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| ---------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| COLD 下 V2 是否报 `Identifier not found: Config`（埋点 `AL-USES`） | `出现，与预期一致，是假阳性。`SCRIPT ERROR: Compile Error: Identifier not found: Config at: GDScript::reload (res://uses_autoload.gd:4) ERROR: Failed to load script "res://uses_autoload.gd" with error "Compilation failed". at: load (modules/gdscript/gdscript_resource_format.cpp:46)                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| WARM 下是否仍报                                                 | 结论：强制warm-up无法消除这个FP，仍然会报同样的报错信息。                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| V5 是否打印 `Config.ping() called`（证明符号真实存在）                   | `结论：这个不会报任何错误。与issue原文复现的不同，stdout上面输出的是CONFIG_ALIVE。但是仍然证明了config存在，是一个假阳性。因此可以用V5通过与否来验证V2和V1的autoload是否是假阳性。`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| V1 项目级扫描是否放大该 FP                                           | `放大到所有引用它的gd脚本，引用它的脚本都会报错。引用他的脚本报错信息都指向Config，因此可以一起过滤掉，但是值得注意的是：哨兵脚本因为引用了使用Config的脚本，也报错了，报出的错误是不带Config的，不过好在这个compile error不会阻塞其他的真阳性报错信息的输出，因此可以过滤掉哨兵脚本的compile error（因为哨兵脚本出现compile error，这个error一定是出现在其他脚本并且已经输出在哨兵脚本的报错前面了，所以哨兵脚本的compile error可以过滤掉）`SCRIPT ERROR: Compile Error: Identifier not found: Config at: GDScript::reload (res://main.gd:4) SCRIPT ERROR: Compile Error: Identifier not found: Config at: GDScript::reload (res://uses_autoload.gd:4) SCRIPT ERROR: Compile Error: Failed to compile depended scripts. at: GDScript::reload (res://__probe_sentinel.gd:0) ERROR: Failed to load script "res://__probe_sentinel.gd" with error "Compilation failed". at: load (modules/gdscript/gdscript_resource_format.cpp:46) |
| 真错误埋点 `AL-SHADOW` 的精确文案（不得被过滤）                             | 实测虽然有FP，但是命名冲突的时候仍然会报错，并且这次的报错是真实的。好在两次报错的签名不同，这次是Parse Error，因此可以利用签名不同来区分，这个报错可以进reward。SCRIPT ERROR: Parse Error: Class "Config" hides an autoload singleton. at: GDScript::reload (res://shadow_config.gd:1) ERROR: Failed to load script "res://shadow_config.gd" with error "Parse error". at: load (modules/gdscript/gdscript_resource_format.cpp:46)                                                                                                                                                                                                                                                                                                                                                                                      |


**结论**：`待填写`（三选一：FP 在 COLD+WARM 都存在 / 只在 COLD / 不复现）

**决策**：§5 `noise_filters.autoload` 取值——`[autoload]` 段白名单 + V5 交叉验证 / 强制 warm-up 即可 / 无需处理。同时决定 §5 `verifier.require_warm_cache`。

---



## P1-5 · N02 addon 单例假阳性

`NOT_STARTED` · 可信度 `NONE` · 证据 `artifacts/<run-id>/N02/` → `reports/<run-id>/N02/delta/`


| 判据                                                            | 实测                                                                                                                                                                                                                                                                   |
| ------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 启用插件后 `DummySingleton` 是否出现在 `project.godot` 的 `[autoload]` 段 | 符号已经在 `[autoload]` 里，`--check-only` 仍然当它不存在。白名单读 `project.godot` 即可，不必去扫 `add_autoload_singleton`。                                                                                                                                                                   |
| V2 是否报单例找不到                                                   | 同样的报错SCRIPT ERROR: Compile Error: Identifier not found: DummySingleton at: GDScript::reload (res://uses_addon.gd:4) ERROR: Failed to load script "res://uses_addon.gd" with error "Compilation failed". at: load (modules/gdscript/gdscript_resource_format.cpp:46) |
| V5 是否证明单例在运行时注册成功                                             | `成功，说明是个假阳性`                                                                                                                                                                                                                                                         |
| 与 N01 是否同根同源（同一条过滤规则能否通吃）                                     | `完全可以`                                                                                                                                                                                                                                                               |
| 插件启用状态来自 derived patch 还是 manual gate                         | `插件由derived patch可以实现启用，启发：在headless调试中，可以让agent自己通过修改特定字段来启用插件，不必经由GUI。但是这里需要再考虑一下，因为要保证所有的addon代码都要被校验，哨兵的设计需要谨慎，因为不见得所有的addon都在脚本中引用了。`                                                                                                                           |


**结论**：`额外小实验得到的结论：`  
分两层看：引擎先打哪些行，过滤器再删哪一行。

**1. Godot 会不会挡住后面的错（和过滤器无关）**

- 后面是 **Parse Error**（未声明标识符、类型赋错、语法错误）：**不会挡**。这些行会出现。而且这时 `Identifier not found: Config` **常常根本不会出现**（解析已失败，编译阶段不跑，autoload 假阳性来不及打）。
- 后面是 **Compile Error**（例如对已声明的 `Node` 调不存在的方法）：**会被 Godot 挡住**。日志里往往只剩 `Compile Error: Identifier not found: Config`，后面那句编译错误**不会出现在 stderr 里**。

**2. 过滤器会不会让后面的错“出不来”**

- **Parse Error：不会。** 它们要么已经在日志里（滤不滤 Config 都在），要么 Config 那句本来就没打出来。滤掉 Config **不可能**让 Parse Error 消失。
- **Compile Error：过滤器也删不掉它们，因为它们根本没被打出来。** 滤掉 Config 之后，文件可能只剩 `Failed to load script ... Compilation failed`。看起来更“干净”，但同文件里可能还有 Godot 没报的编译错误。这不是过滤器误删，是 `--check-only` **在 Config 处停编译** 造成的漏报。

**3. 过滤器设计要点**

只删这一类行，且符号必须是 `[autoload]` 的 **key**：

Compile Error: Identifier not found: Config

Compile Error: Identifier not found: DummySingleton

不要做的事：

- 不要滤 `Parse Error: Class "…" hides an autoload singleton`（真冲突）。
- 不要滤 `Parse Error: Identifier "X" not declared in the current scope`（真缺失；模板也和 FP 不同）。
- 不要因为滤掉了 Config，就把**整份脚本/整个项目**标成干净。同文件若只有 Config FP，后面的 Compile Error 可能已被引擎吞掉；最多删这一行噪声，**不要**据此宣布“没有别的编译问题”。
- 不要靠 V5 决定滤不滤。
- `Failed to load script` / `Failed to compile depended scripts` 不是 autoload 白名单该管的，留给级联规则。

**决策**：§5 `noise_filters.addon_singleton` 取值——复用 autoload 白名单（约 20 行）/ 扫 addon 源码里的 `add_autoload_singleton`（约 200 行，不可靠）/ 不过滤直接 escalate。

---



## P1-6 · N04 级联错误与根因放大

`NOT_STARTED` · 可信度 `NONE` · 证据 `artifacts/<run-id>/N04/` + 复用 `artifacts/n09-20260821/N09/` → `reports/<run-id>/N04/cascade/`


| 判据                                           | 实测                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| -------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| NP-CASCADE 项目级原始 error 行数（已扣除哨兵人造级联边）        | 项目级扫描的时候，只输出了根因所在脚本的报错信息，但这不能说明错误不会级联，只是因为哨兵脚本SCRIPT ERROR: Parse Error: Could not preload resource script "res://root_bad.gd". at: GDScript::reload (res://__probe_sentinel.gd:10) SCRIPT ERROR: Parse Error: Could not resolve script "res://root_bad.gd". at: GDScript::reload (res://__probe_sentinel.gd:10) ERROR: Failed to load script "res://__probe_sentinel.gd" with error "Parse error". at: load (modules/gdscript/gdscript_resource_format.cpp:46)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| 同构单根分母：`scene_bad.gd` 单文件 error 行数           | 观察：对比其他几个引用他的文件，无论是哨兵的一级引用，还是其他的直接的一级引用都不会报具体的indent错误类型，而是报“could not preload”“could not resolve”，但是好在哨兵和引用的报错都可以定位到根因，对根因跑V2可以找到具体的错误类型。SCRIPT ERROR: Parse Error: Unexpected "Indent" in class body. at: GDScript::reload (res://scene_bad.gd:4) ERROR: Failed to load script "res://scene_bad.gd" with error "Parse error". at: load (modules/gdscript/gdscript_resource_format.cpp:46)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| 放大倍数                                         | `待填写`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| 去重后 signature 数 / 根因候选数 / 症状数                | `待填写`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| 「`at:` 指向引擎内部路径 = 症状」这条规则是否成立                | `待填写`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| 直接依赖（`dep_1`）与二级依赖（`leaf`）被单独 check 时报根因还是症状 | 观察1:直接引用错误脚本的报错，错误信息中写的不是级联症状，确实是根音，这一点上没有放大，和哨兵脚本引用根因错误脚本的错误描述是完全一致的，但是值得注意的是，报错信息的位置at引用的是一级引用错误脚本的那一行。 SCRIPT ERROR: Parse Error: Could not preload resource script "res://root_bad.gd". at: GDScript::reload (res://dep_1.gd:3) SCRIPT ERROR: Parse Error: Could not resolve script "res://root_bad.gd". at: GDScript::reload (res://dep_1.gd:3) ERROR: Failed to load script "res://dep_1.gd" with error "Parse error". at: load (modules/gdscript/gdscript_resource_format.cpp:46) 观察2:二级引用输出的仍然是根因，报错信息的签名是完全一致的，从这个角度上说错误不会级联，但是有意思的是，报错引用的位置at的是一级引用根因脚本的位置（即和上面的一级引用实验中的报错位置一致，这证明了多级引用一个错误根因脚本的情况下，报错信息不会级联，引用的出错位置是一级引用错误脚本的那个脚本中引用错误脚本的行），但是值得注意的是，二级引用的情况下，二级引用的脚本多了一个compile error：Failed to compile depended scripts，这个的确是一个级联放大噪声。出现depended scripts的错误，可以当作噪声过滤掉。因此补做实验三级引用，看看这时候会不会有更多的报错。SCRIPT ERROR: Parse Error: Could not preload resource script "res://root_bad.gd". at: GDScript::reload (res://dep_1.gd:3) SCRIPT ERROR: Parse Error: Could not resolve script "res://root_bad.gd". at: GDScript::reload (res://dep_1.gd:3) SCRIPT ERROR: Compile Error: Failed to compile depended scripts. at: GDScript::reload (res://leaf.gd:0) ERROR: Failed to load script "res://leaf.gd" with error "Compilation failed". at: load (modules/gdscript/gdscript_resource_format.cpp:46)观察3:当引入3级引用时，一样只会报根因的parseerror，错误的定位在一级引用出错脚本的这一行。但是会再多一条compile error：破案了，一级引用会报错但是不会compile error，但是二级和以上的引用，虽然不回抛出parse error，但是每层引用抛出一个compile error。重要观察四：和哨兵脚本一样，出现“could not preload；could not resolve”这样的错误的时候，并不会报那个could not resolve的脚本的真实错误，必须专门去V2一下那个could not resolve的脚本才能错误修复，因此哨兵脚本和级联错误的脚本出错的下一步动作就是：V2排查那个出错的根因脚本。总结：compile error级联产生但是不作为reward，仅仅喂给llm做参考。只看parse error的话不会级联，不论是哨兵还是多级引用都会在第一级引用（直接引用）错误脚本的preload处发出两条报错，报错中指明了是哪一个脚本出错，但是不显示具体错误。同时，最终的ERROR：字段随着引用层数的增加会变化，有的显示parser error，间接引用则显示compile error，不过最后的ERROR字段会显示错误对应的引擎源码的行，这个可以当作出现的是同一个症状的依据。 |




额外的实验和重要观察：**脚本一共 10 个** `.gd`**（另有** `config.gd` **本体，应能解析）**

语法根因（缺冒号，同 scene_bad）

  syn_a.gd  ──preload──► syn_a_l2.gd  ──preload──► syn_a_l3.gd

  syn_b.gd  ──preload──► syn_b_l2.gd

autoload 一级（调用 Config）

  al_l1.gd  ──preload──► al_l2.gd（二级：preload al_l1，自己也调 Config）

  uses_autoload.gd

  main.gd

干净

  config.gd   （autoload 实现）

出错/依赖出错的有 **8 个**：`syn_a`、`syn_b`、`syn_a_l2`、`syn_a_l3`、`syn_b_l2`、`al_l1`、`al_l2`、`uses_autoload`，外加 `main.gd` 也引用 Config。

**V1 哨兵 stderr（全部）**

SCRIPT ERROR: Parse Error: Could not preload resource script "res://syn_a.gd".

```
      at: GDScript::reload (res://__probe_sentinel.gd:7)
```

SCRIPT ERROR: Parse Error: Could not resolve script "res://syn_a.gd".

```
      at: GDScript::reload (res://__probe_sentinel.gd:7)
```

SCRIPT ERROR: Parse Error: Could not preload resource script "res://syn_b.gd".

```
      at: GDScript::reload (res://__probe_sentinel.gd:10)
```

SCRIPT ERROR: Parse Error: Could not resolve script "res://syn_b.gd".

```
      at: GDScript::reload (res://__probe_sentinel.gd:10)
```

ERROR: Failed to load script "res://__probe_sentinel.gd" with error "Parse error".

**结论：V1 报不全。** 只点了哨兵**直接 preload 的两个语法根** `syn_a.gd`、`syn_b.gd`，而且文案是 `Could not preload/resolve`，不是缺冒号那句 `Unexpected Indent`。

没出现的：

- 语法二/三级：`syn_a_l2`、`syn_a_l3`、`syn_b_l2`（没有 `Failed to compile depended scripts`）
- autoload 一/二级：`al_l1`、`al_l2`、`uses_autoload`、`main`（没有 `Identifier not found: Config`）

哨兵自己先解析失败，编译段不跑，autoload 假阳性和更长的 preload 链都进不了这份 V1 日志。要看到那些，得像 N04 那样对 `dep_1` / `leaf` 单跑 V2。  

**结论**：`confirmed`

**决策**：`VerifyReport` 是否需要 `root_cause_errors` 字段（§5 `verifier.report_shape`）；症状 error 是否排除在重试计数器与熔断阈值之外（§5 `retry.count_symptoms`）。

---



## P1-7 · N05 warning 与 error 严重度

`NOT_STARTED` · 可信度 `NONE` · 证据 `artifacts/<run-id>/N05/` → `reports/<run-id>/N05/delta/`


| 判据                                                              | 实测                                                                |
| --------------------------------------------------------------- | ----------------------------------------------------------------- |
| 默认设置下 warning 是否根本不出现                                           | `warning根本不会出现`                                                   |
| 注入 `gdscript/warnings/enable=true` 后是否以 `WARNING:` 前缀出现在 stderr | `不会出现warning，warning只有debug模式才可看到，但是debug被确认永久禁用，因此直接不看warning了，` |
| `exclude_addons=true` 是否真的屏蔽了 addon 内 warning                   | `warning根本无法收集，这一点没必要讨论了。`                                        |
| CleanControl 背景里本来有多少 WARNING                                   | `无任何warning`                                                      |


**结论**：`confirmed`

**决策**：§5 `verifier.enable_warnings`——是否采集 warning 作为 Judge 的辅助证据。无论结果如何，`severity != ERROR` 的行不进 reward 与终止条件（这条已定，不需实验支撑）。

---



## P1-8 · N06 invalid UID 严重度与资源引用变更

`NOT_STARTED` · 可信度 `NONE` · 证据 `artifacts/<run-id>/N06/` → `reports/<run-id>/N06/sequence/`、`.../delta/`


| 判据                                           | 实测                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| -------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `invalid UID` 的严重度前缀（`WARNING:` 还是 `ERROR:`） | `单独的UID被破坏或则会篡改不会有任何报错，但是如果出现重复的uid在运行V3时就会报错和报warning，并且会使import失败，解决方案是删除项目中重复的UID，再次运行V3会自动地重建。下面的出现在Warning后面的Error都是随着UID重复产生的，（记住他们的signature，即出现在引擎源码的行号，他们跟在UID duplicated warning后面出现的确是个真错误，需要去通过删除warning里面报错的两个场景的UID，然后重新import来解决，但是这里需要注意的是后面出现的ERROR数量是一个严重度假阳性，他们事实上是同一个问题，不要当作多个问题解决，和上面的error信息压缩成一条即可。`WARNING: UID duplicate detected between res://sub.tscn and res://main.tscn. at: *process*file_system (editor/file_system/editor_file_system.cpp:1405)ERROR: Parse Error: Busy. [Resource file res://sub.tscn:6] at: *parse*node_tag (scene/resources/resource_format_text.cpp:293)ERROR: Failed loading resource: res://sub.tscn. at: *load (core/io/resource*loader.cpp:317)ERROR: Parse Error: Busy. [Resource file res://main.tscn:7] at: *parse*node_tag (scene/resources/resource_format_text.cpp:293)ERROR: Failed loading resource: res://main.tscn. at: *load (core/io/resource*loader.cpp:317)ERROR: Plugin is not attached to debugger. at: is_active (editor/debugger/editor_debugger_plugin.cpp:102)删除UID重新import是不会报错并可以正确的重建的。 |
| V3 重新 import 能否自愈伪造的 UID                     | `不可以自愈，单独的UID被篡改根本不回报错，不论是V1，V2的脚本检查还是V3重新import，即不报错也不会重建正确的UID。所以假UID问题是无法通过headless检测并消除的，只能通过删除全部uid然后重建`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| `ext_resource` 指向变更后不 import 是否报错            | `资源引用更改不会报错，这个不会有假阳性`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| 补 import 之后是否干净                              | `由于根本不报错这一条没有价值`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| 正确 UID 基线来自 derived patch 还是 manual gate     | `来自patch`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |


**结论**：`confirmed`

**决策**：§5 `noise_filters.invalid_uid`——前缀过滤（成本 0）还是必须维护非阻塞 error 文案白名单；`import_policy` 的 `scene_ext_resource_changed` / `uid_changed` 两项；入队前是否强制跑一次 UID 规范化。

---



## P1-9 · N07 shader verifier 盲区

`NOT_STARTED` · 可信度 `NONE` · 证据 `artifacts/<run-id>/N07/` → `reports/<run-id>/N07/delta/`


| 判据                                       | 实测                                                                                                                                                                                                                                                                                                                                                                                                                 |
| ---------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| V2（`preload` shader 的脚本）是否报错             | `不报错`                                                                                                                                                                                                                                                                                                                                                                                                              |
| V3 import 阶段是否报错                         | `会报错的，因此这个错误对于V2和V1都是假阴性，只有通过V3 import才可以识别出来。`SHADER ERROR: Invalid arguments for the built-in function: "vec4(float,float,float)". at: (null) (:4) ERROR: Shader compilation failed. at: shader_set_code (servers/rendering/dummy/storage/material_storage.cpp:192)                                                                                                                                            |
| V5 场景启动阶段是否报错                            | `会报错：`SHADER ERROR: Invalid arguments for the built-in function: "vec4(float,float,float)". at: (null) (:4) ERROR: Shader compilation failed. at: shader_set_code (servers/rendering/dummy/storage/material_storage.cpp:192) 但是好消息是多了一条stdout的信息来指明shader中的错误在哪里，V5可以产生额外的关于错误shader的有效信息：Godot Engine v4.7.1.stable.official.a13da4feb - [https://godotengine.org](https://godotengine.org) --Main Shader-- 2 |
| 默认 V1 哨兵（只 preload `*.gd`）能否覆盖           | `哨兵只覆盖gd，不会对shader进行校验`                                                                                                                                                                                                                                                                                                                                                                                            |
| `good.gdshader` 侧是否静默（排除“所有 shader 都不报”） | `goodshader会静默，badshader也不会在V2报错，但是V3import会报错，V5不仅会报错还会生成其他的有效信息在stdout中。`                                                                                                                                                                                                                                                                                                                                        |


**结论**：`import和V5启动阶段可见，好消息，不需要escalate`（三选一，价值递减：全部静默 → 盲区 / import 阶段可见 → 免费信号 / V2 可抬升 → 哨兵可扩展）

**决策**：§5 `verifier.shader_coverage`——`.gdshader` 走 escalate、进 reward、或扩展哨兵到 `.gdshader`。这一条直接决定对外的验证边界声明。

---



# 4. 第二阶段结论

---



## P2-1 · N15 converter 与 upgrade tool 能力门

`NOT_STARTED` · 可信度 `NONE` · 证据 `artifacts/<run-id>/N15/` → `reports/<run-id>/N15/capability/`


| 判据                                                                                                | 实测                                                                |
| ------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------- |
| `--validate-conversion-3to4` 是否存在且可对最小项目调用                                                        | `存在，且stdout会输出其认为要改动的文件，但是不会真的改动，是个无副作用操作`                        |
| `--convert-3to4` 是否存在且**真的改了文件**（以 diff 为准）                                                       | `真的改动了文件但是：``但是：必须以diff为准，stdout会将没有进行改动的文件也描述成`converted files: |
| 是否接受 `max_file_kb` / `max_line_size` 参数                                                           | `可以带参数，带参数以后也可以进行正确的转换`                                           |
| ProjectUpgradeTool 是否有 headless CLI 入口                                                            | `没有入口`                                                            |
| 职责矩阵：converter / upgrade tool / `--import` 各改哪类文件（GDScript、`.tscn`、`.tres`、UID、资源路径、import cache） | `待填写`                                                             |


**结论**：


| **工具**                       | **能做什么**                                                                  | **不能做什么**                                                  |
| ---------------------------- | ------------------------------------------------------------------------- | ---------------------------------------------------------- |
| `--validate-conversion-3to4` | 预览改动清单，**不碰文件**                                                           | 不执行实际转换                                                    |
| `--convert-3to4`             | 改写 `.gd`/`.tscn`/`.tres` 文本内容、`.shader→.gdshader` 改名、`project.godot` 版本升级 | 不生成 UID、不建 import 缓存、`stdout` 报告与实际文件变化可能不一致（`child.tscn`） |
| `--import`（V3）               | 补 UID sidecar、建 import 缓存                                                 | **完全不具备 3.x→4.x 文本改写能力**；作用于未转换项目时只会报错（但 rc 仍为 0，不可信）      |
| 独立 upgrade tool              | 不存在                                                                       | —                                                          |


这意味着第二阶段的流水线只有一种可行形状：

converter (--convert-3to4)  →  V3 (--editor --import)  →  verifier

不存在"跳过 converter 直接用 --import 升级"这条路径，因为 V3 对未转换项目会产生真实解析错误；也不需要第二个 upgrade tool 环节，因为它不存在。

转换后，优先用V1进行错误检验，先使用静态解析纠错再V3校验无法用静态检验检验出的问题，比如shader和UID。

**决策**：第二阶段流水线形状 → §5 `pipeline`：`converter → upgrade tool → verifier` 还是 `converter → --import → verifier`；是否需要第二个固定版本的 Godot 二进制；是否需要从 `renames_map_3_to_4.cpp` 自建 L0。能力门失败则 N21 记 `BLOCKED`。

---



## P2-2 · N21 官方 Demo 自动迁移残余分布

`NOT_STARTED` · 可信度 `NONE` · 证据 `artifacts/<run-id>/N21/` → `reports/<run-id>/N21/corpus/`

完整分布表（converter 行为分布、根因类别分布、严重度分布、可处理性分布、代表案例）由 `analyzer/corpus.py` 写在上面的 `reports/` 目录里，**不抄进本文**。这里只留摘要与判断。


| 判据                                              | 实测    |
| ----------------------------------------------- | ----- |
| Demo 总数 / converter 成功完成数 / 转换后直接通过 verifier 的数 | `待填写` |
| 每个 Demo 的根因簇数：均值 / 中位 / P95                     | `待填写` |
| Top 3 残余根因类别                                    | `待填写` |
| `TODOConverter3To4` 总数，以及是否机器可解析                | `待填写` |
| shader 残余：`.shader` 是否正确转为 `.gdshader`、引用是否同步   | `待填写` |
| converter 报告成功但文件未变化的案例数                        | `待填写` |
| 最大 `.gd` 字节数与最长单行（判断大文件跳过问题是否成立）                | `待填写` |
| COLD / WARM import 耗时（按 Demo 规模归一化）             | `待填写` |
| `UNCLASSIFIED_NEEDS_REVIEW` 条数                  | `待填写` |
| 3.x→4.0 残余与 4.0→4.7 漂移的比例                       | `待填写` |


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


| 实验  | 现象                | 是否确认  | 规避 / 过滤策略 | 证据    |
| --- | ----------------- | ----- | --------- | ----- |
| N09 | 输出非确定性            | `待填写` | `待填写`     | `待填写` |
| N08 | exit code 不可信     | `待填写` | `待填写`     | `待填写` |
| N03 | 冷缓存 / patch 后缓存陈旧 | `待填写` | `待填写`     | `待填写` |
| N01 | autoload 假阳性      | `待填写` | `待填写`     | `待填写` |
| N02 | addon 单例假阳性       | `待填写` | `待填写`     | `待填写` |
| N04 | 级联放大              | `待填写` | `待填写`     | `待填写` |
| N05 | warning 严重度       | `待填写` | `待填写`     | `待填写` |
| N06 | invalid UID 严重度   | `待填写` | `待填写`     | `待填写` |
| N07 | shader 盲区（假阴性）    | `待填写` | `待填写`     | `待填写` |




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

