# LANDMARKS 校验报告

> 这是 2026-10-17 的历史校验记录。当前可执行顺序和问题维护入口已迁入 [LANDMARKS.md](LANDMARKS.md) 与 [DEFECTS.md](DEFECTS.md)，下文原建议不再作为单独开发队列。


校验日期：2026-10-17。校验基准：`701315b05fdd433d5b6eb0d112a8d406203c8245`。

工作目录：`/Users/yy_catmax/.codex/worktrees/landmarks-audit/godot3_to_4_migration_agent`。

## 1. 结论

**总体方向成立，但不能直接照原文逐项实施。** 底层已有实质实现，`migration_agent` 的 L0、编排、trace、eval 则确实只有包骨架。保留“本地隔离工作区 + 进程内组合 + SQLite + 后续多进程批处理”的方向是合理的，无需为当前单机目标补回 FastAPI / Redis。

需要先修订的不是模块划分，而是四个实现前提：

1. 多份路标使用了不存在的 API、字段和 Gate 决策。按这些示例编写宿主会接不上现有实现。
2. 全库 GDScript 哨兵已经实现，`load_sweep` 的现状分析遗漏了它；拟议的扫描命令又因 `--check-only` 不会执行扫描逻辑。
3. L0 将字符串置信标签当数值筛选，并高估了“全局符号唯一”所能证明的安全性。
4. trace schema 尚不能兑现可靠恢复、跨运行评测和完整成本账本；“100% 确定性续跑”“完美语义 Ground Truth”“98% 完成”等表述缺少相应证据。

此外，本次复现了路标未列出的中文索引切片错误、依赖边信息不足、改名检查的索引旁路漏报和运行产物阻塞写工具等问题。应将这些纳入先决条件。

本次交付是校验与修改建议，**没有修改业务实现，也没有把原路标的待办标记为完成**。

## 2. 调研和验证范围

已阅读根目录及全部 14 份下级 `LANDMARKS.md`，沿调用链检查写工具、符号/场景索引、验证命令/哨兵/采集/过滤/Gate/状态、RAG 构建/检索/缓存/观测及现有评测代码。旧 `AGENTS.md` 和规划文档只用于定位，不作为实现完成的证据。

验证结果：

- `inline_tools/tests` 与 `inline_tools/editandfixguard/tests`：**183 passed**。
- `codebase_index/index/tests`：**202 passed**。
- `codebase_index/godot_mcp/tests`：**231 passed**。
- `rag/test`：**92 passed，1 skipped**。跳过项是 `test_prose_jsonl_present`，对应路标已指出的散文路径错位；另有一条保留超长函数整体切块的预期 warning。
- 直接只读查询真实 `rules.db`：**8260 条规则**，`schema_version=2`、目标版本元数据为 `4.7.1`；LanceDB 实际 **317 行**。
- 真实 A 层查询 `Spatial` 命中 `official_renames:4.0:_:class:Spatial`；真实混合查询得到 3 条 B 层结果。未重新跑完整检索超参消融。
- 下文的关键反例使用临时目录和临时 Git 仓库复现；验证状态反例使用注入的模拟 Godot 输出，不冒充真实引擎运行。

环境说明：复用了原项目已有虚拟环境，但通过 `PYTHONPATH` 指向**本 worktree 源码**。初次用根虚拟环境跑索引测试，因其 `tree-sitter-language-pack 1.20.0` 的默认缓存目录受限而失败；改用索引子模块现有 `1.15.8` 环境后 202 项通过。RAG 初次未指定模型缓存时也有一次模型加载失败，指定现有缓存后通过。这两类初次失败不能记为已确认的业务回归。

当前 `PATH` 与路标指定的 `/Applications/Godot.app/Contents/MacOS/Godot` 均未找到 Godot，**没有执行真实转换、V1/V2/V3 或 load sweep**。下文引擎命令语义结合仓库源码与官方 4.6 文档判断；不据此宣称完成了目标 `4.7.1` 的引擎验收。

## 3. 应先纠正的接口与验证契约

### 3.1 上层路标的 API 示例与当前实现不一致【阻断整合】

主要涉及 `migration_agent/orchestrator/LANDMARKS.md`、`migration_agent/l0/LANDMARKS.md`、`codebase_index/index/LANDMARKS.md` 和共享配置示例。

当前实际入口是：

- 验证：`godot_mcp.verify_gate.tool.run_verify_tool(kind, target, *, config, gate_cfg, state_store, ...)`；不存在规划中的 `execute_verify_shell`。
- 验证结果：`VerifyGateResult.project_status / decision / hard_stop / diff / root_cause_errors / pointers / gdscript_complete / shader_checked / probe_incomplete / untrusted_files`；没有 `gate.action`。
- Gate 决策：`CONTINUE`、`NO_PROGRESS_WARN`、`FILE_STUCK_WARN`、`OSCILLATION_ESCALATE`、`BUDGET_EXCEEDED`、`CIRCUIT_OPEN`。没有 `PASS`、`UPGRADE_MODEL_TIER`、`ROLLBACK_AND_RETRY`，也没有现成的 `rollback_patch_id`。
- 验证状态：`ProjectVerifyState`，不是 `WorkspaceVerifyState`；没有示例中的 `last_good_signatures` 或 `no_progress_streak`。
- 读取：`inline_tools.read.read(project_root, path, line_from=1, line_to=None)`。
- 搜索：`inline_tools.grep.grep(project_root, pattern=None, glob=None, path=None, context=0, max_results=100)`；没有 `workspace_root`、`output_mode` 参数。
- 编辑：`inline_tools.editandfixguard.edit.edit(project_root, *, file, kind, hunks, content, ...)`，返回 `ok / commit / guard / index_stale`；没有 `edit_file(old_string, new_string, replace_all)` 或 `status == "COMMITTED"`。
- 场景：`codeindex.scene.check.scene_check(conn, project_root, *, paths, rules_db_path)`；单文件 L4 则是 `check_scene(text, path, ...)`，不能传数据库连接代替正文。
- 冻结：`codeindex.scene.baseline.freeze_baseline(conn, problems)` 已有；`run_scene_freeze` 是**拟新增 API**，不是可直接复用的现有函数。
- 检索：`RetrievalQuery` 的字段是 `error_text / query_text / symbols / target_version / ...`；`target_version` 必填。规划中的 `RetrievalQuery(query=..., error_code=...)` 实测抛 `ValidationError`。结果字段是 `structured_hits / prose_hits`，不是 `rule_hits / chunk_hits`。
- 执行器：`verify.runner` 提供 `run_verify(V1/V2/V3, ...)` 和内部 `_spawn`，没有 `run_subprocess`；没有 `godot_mcp.verify.parser` 这个模块。
- 索引查询已有 `find_symbol / call_chain / class_hierarchy / status`；`find_refs / get_file_outline / get_dependencies / rank_root_cause_files` 不能一概当作已有函数。

证据：`verify_gate/models.py:18`、`verify_gate/tool.py:47`、`scene/check.py:37`、`inline_tools/editandfixguard/edit.py:39`、`rag/retriever/schemas.py:162`。

**建议**：先写小型宿主适配层，明确“现有能力”与“宿主新增策略”。升级模型、恶化判定、整轮回滚由宿主负责，读取实际 `decision` 与签名差集；不要等待底层返回不存在的决策。保留 Hunk 型写工具；若要向模型提供字符串替换接口，应单独说明如何转成唯一锚定的 Hunk，不能绕过守卫。

共享配置同样需要修订。现有键是 `project_root / index_state_dir / godot_binary / migration_rules_db`，索引库路径由配置派生为 `.codeindex/index.db`。规划使用的 `workspace_root / db_path / godot_bin / rules_db_path` 不能直接交给现有 loader：复制其 YAML 实测得到 `KeyError: 'project_root'`。

实际 Gate 配置示例应使用：

```yaml
retry_gate:
  rounds_limit: 20
  no_progress_window: 3
  oscillation_window: 3
  file_stuck_threshold: 3
  infra_failure_streak_limit: 3
```

路标给出的 `max_rounds_per_workspace / no_progress_limit / repeated_patch_limit / infra_breaker_threshold / allow_v3_auto_repair` 五个键会被 loader **全部作为未知字段拒绝**。宿主也可以直接注入 `RetryGateConfig`，无需为进程内组合强行修改底层 Config。

### 3.2 `load_sweep` 应调整目的和命令【阻断验收】

路标称当前工作区检查只能覆盖启动链，遗漏了已实现的生产行为：

- `verify/sentinel.py:25` 枚举工作区 `.gd`，生成 `__probe_sentinel.gd`，逐个写入常量 `preload`。
- `verify/commands.py:50` 的 V1 固定使用 `--check-only --script res://__probe_sentinel.gd`。
- `verify_shell/collect.py:39` 已组合条件 V3、V1、多目标 V2 下钻及收尾 V3。

所以“新增 sweep 才第一次覆盖孤立 `.gd`”不成立。V1 的扫描有明确排除项，且仍存在已声明的过滤盲区；但不能忽略现有哨兵，重新按裸命令设计整套验证。

拟议命令 `godot --headless --check-only -s res://.godot_migration_sweep.gd --quit` **只解析扫描脚本，不运行其中的动态 `ResourceLoader.load()` 循环**。官方命令行文档也明确将 `--check-only` 定义为仅解析并退出：[Godot 命令行说明](https://docs.godotengine.org/en/4.6/tutorials/editor/command_line_tutorial.html)。

**建议**：将新增 sweep 缩小为“现有哨兵/V3 未证明的资源与不可信文件的补充验证”。若要动态执行，移除 `--check-only`，由脚本显式 `quit()`，配合执行超时、逐资源开始/完成标记、期望资源清单和崩溃后的未检查清单。新增执行模式要有受控入口，不能把自由 Godot argv 暴露给 Agent。

`ResourceLoader.load()` 成功也不证明场景实例化、`_ready`、异步时序、视觉或实际 shader 渲染正确。是否实例化场景、是否需要渲染探针应单独定义；当前不能把它们合并宣称为“完整语义通过”。

### 3.3 `CLEAN` 必须带覆盖条件

复现：构造无根因但有 pending pointer 的视图，实际结果为 `project_status=CLEAN`、`probe_incomplete=True`、`gdscript_complete=False`、`decision=CONTINUE`。`merge.py` 还明确允许 `untrusted_files` 非空而状态为 CLEAN。

**建议**：宿主成功条件至少同时核对基础设施健康、非硬停止、脚本完整性、pending pointer、场景错误与覆盖、静态陷阱分类、要求的资源验证覆盖。不可信文件必须补证或进入报告/人工结论，不能只看 `CLEAN` 或根因集合为空。

场景 `pre_existing` 只说明错误在基线里已有，不能表示该错误被豁免为迁移成功。反过来，继承场景弃权、二进制资源、超大文件跳过也不能被静默视为完整通过。

### 3.4 回滚与索引同步需要宿主的显式策略

“出现新签名就回滚”过于简单。修掉一个语法根因后，引擎可能首次暴露原来被遮挡的另一个错误；`GateDiff` 的注释也明确说明，某个签名消失可能只是被新错误遮挡。应区分确定回归、可解释的诊断暴露和未知变化，结合新错误位置、修改范围与验证覆盖判定，不能将签名数量单调下降作为唯一准则。

一轮若允许提交 1–3 个关联补丁，应保存整轮开始提交和全部 patch ID，明确回滚整个候选组还是单个补丁，并同步全部受影响文件。当前 `edit(kind="revert")` 可以 reset 到某提交，但只调用传入单文件的 sync，不能天然保证整组回滚后索引全更新。

`sync_index.py:14` 还有跨工作区接线风险：虽接收 `project_root`，实际执行的只是 `codeindex sync <绝对目标路径>`，没有把该 root 传入配置。宿主注入验证 Config，不会自动改变这个 CLI 的默认项目。应提供绑定本 run 配置的 `sync_fn` 或进程内索引适配器；`index_stale=True` 后先刷新，再用索引做 triage/守卫。

## 4. 已有缺陷清单：多数判断成立，但修法需补强

### 4.1 `inline_tools/editandfixguard` 的六项缺陷

六项均可保留：公开导出缺失、改名一致性未接线、写后场景误回滚、create 未接入检查、其他后缀守卫缺失、临时 `.patch` 文件未清理。证据分别在 `__init__.py`、`edit.py:103`、`edit.py:184` 和 `git_txn.py:52`。

复现实例：

- `kind=create` 创建 `func broken(:`：返回 `ok=True` 并提交，但 Tree-sitter 检出 1 个错误节点。
- 带存量 `format=2` 的场景，写前 `check_scene_invariants(old, old).ok=True`；同内容写后复核却返回 `SCENE_REGRESSION`。

修复建议补充：

- create 的 `check_symbols` 现有分支**不会自行检查语法节点数**，必须另做语法检查。路标文字称其已检查新文件语法不准确，不过后面的显式节点检查建议是必要的。
- `next(iter(added_names))` 不能作为真实改名配对；多函数同时改名时任意配对并不可靠。当前一致性函数仅用旧名集合即可报警；若后续需要新旧映射，应要求显式映射或通过结构匹配证明。
- 一致性检查还有未列出的漏报：`scene_names.py:182` 只要 `db_path` 文件存在，就把全部旧名标为 covered，不再 grep。**已建表但未索引场景的空索引**下，旧回调仍在场景里却不报警；不用索引时 grep 能找到 1 项。索引存在不能代表覆盖完整；应按成功查询与覆盖状态决定回退。
- G5.1 当前比较的是**声明的符号集合**，不是所有 API 使用。直接调用该检查，`extends KinematicBody2D` 与 `.instance()` 都未被拦截；自定义 `func get_name()` 却因规则库有别的 owner 的旧方法而被拒绝。仅把 create 接线，不能兑现“新脚本旧 API 全被拦截”。应明确守卫范围，并对使用点、owner 和规则动作做保守判断。
- `.tscn/.tres` 也只有场景不变量路径。若目标是通用文本防删逻辑，不能只给另外三类后缀补通用守卫而遗漏场景中的信号删除等变更。

### 4.2 场景缺陷成立，示例函数名/字段需改

已确认：

- **SCN-BUG-1**：真实库是 `migration_rules`，loader 查 `rules`。真实 `KinematicBody2D` 场景检查实测 `rules_unavailable=True` 且没有 `E_UNMIGRATED_TYPE`。
- **SCN-BUG-2**：冻结 `a.tscn` 与 `b.tscn` 的错误后只检查 a，实测 b 被错误放入 `fixed`。
- **SCN-BUG-3**：删掉 `enemy.gd` 的 `_on_hit`，只挂载 `player.gd` 的场景仍被报 `func:_on_hit@enemy.gd`；源码也确有 `LIMIT 1`。
- 缺少 freeze 生产入口，且现有 `freeze_baseline` 可以清空后重写，宿主 `--resume` 不应再次调用它。

增量范围过滤、目标脚本归属检查和多引用覆盖方向正确。但具体方案要按实际 schema 实现：

- `diff_baseline()` 实际返回 `DiffResult`，并非 `(bool, BaselineDiff)`。
- `Problem` 的路径是 `p.path`，没有 `p.location.path`。
- `scene_refs` 没有 `to_node_path` 列。需要结合 `scene_conn.to_path`、节点路径归一化、`scene_nodes.script_ext_id` 与 `scene_ext.resolved_file` 或相应引用绑定确定脚本；不能按示例 SQL 直接查不存在的列。
- freeze 应先从磁盘读取场景正文，调用实际 `check_scene(text, path, ...)` 收集问题，再在写事务内冻结，并记录冻结版本/提交，默认拒绝覆盖已有基线。
- 现有部分测试将脚本挂在子节点而连接指向根节点，却期待该脚本函数被判为回调归属。修正归属后应一起修正夹具，不能把这些旧断言当作正确性依据。

### 4.3 索引器有两项未列入路标的重要前提

**中文导致 UTF-8 切片错位【高优先级，已复现】**。

`parsers/gdscript.py:38` 用 Tree-sitter 的字节偏移直接切 Python `str`。输入：

```gdscript
# 中文
class_name Player
extends Node
func move():
    print(1)
```

实际 class 名变成 `er\next`，函数名变成 `():\n`，基类变成 `\nfun`。这会同时污染查询、守卫和依赖分析。应统一在 UTF-8 bytes 上切片后 decode，并覆盖中文注释、字符串和标识符；新 codemod 也必须统一字节/字符坐标。

**现有依赖索引不足以支撑规划中的拓扑排序【高优先级，已复现】**。

真实表是 `edges / classes`，没有 `relations`。更关键的是：

- 顶层 `const Dep = preload("res://dep.gd")` 没有生成 preload 边。
- 函数体内 preload 的边只保存 `to_name="preload"`，没有保存目标资源路径。
- `extends "res://base.gd"` 在本次样例中没有生成 `class_decl`。

所以不是单纯“增加一个排序函数”即可。应先补齐依赖提取或新增窄范围的宿主依赖抽取，保留源路径与目标路径/类名，再解析 class_name。排序需要处理循环依赖、未解析目标以及经过无报错中间脚本的传递依赖；SCC 折叠后排序比只计算报错子图出度更稳妥。

该改动属于真实代码前提，应显式更新相关过时的“不改 GDScript parser”规则，不能继续让旧任务约束阻止必要修复。

### 4.4 Godot 验证模块的问题成立，修复示例沿用了旧结构

- **MCP-BUG-1** 成立：当前 `check_file` 也调用同一个 `evaluate`。以 `{A,B} → 空集 → {A,B}` 复现得到 `OSCILLATION_ESCALATE`。但路标给的 `GateOutput`、`filter_result.primary_diagnostics` 等不是实际对象，不能直接粘贴。
- **MCP-BUG-2** 成立：连续 3 次 CRASH 后再给健康结果，复现得到 `circuit_state=OPEN`，但 `decision=CONTINUE / hard_stop=False`。应既定义显式重置策略，也在工具入口避免 OPEN 后继续启动昂贵进程；仅在 evaluate 最后补条件不够。
- **MCP-BUG-3** 成立：默认调用没有传入配置路径。不过当前已能显式注入 `gate_cfg`，宿主可先使用它。
- **MCP-BUG-4** 的“快照漏后缀”成立，**“补后缀就能恢复文件”不成立**。`snapshot.py` 只产生内存文本和触发用 diff，没有恢复快照的函数；`collect.py` 也没有失败回滚事务。扩展后缀能改善触发与差异观察，真实回滚仍需宿主 Git 事务/恢复协议。
- **MCP-BUG-5** 指出的两个检测盲区成立，但实际 UID 事件是 `ClassifiedEvent(kind="resource_error")`，通过 message 识别，不是示例中的 `ConditionalSignalEvent(kind="UID_DUPLICATE")`。正则修改也应匹配触发器中的 diff 行格式，保留 `+/-` 前缀。
- 删除 Redis 占位类合理，属于低优先级清理。

另需补充**每次仓库运行独立的 StateStore**：默认 `_DEFAULT_STORE` 是单槽全局实例。同一进程依次检查两个临时项目，复现第二个项目 `round_index=2`。进程池 worker 会复用进程，不能认为物理目录隔离就自动隔离状态。

`evaluate` 和 `store.save` 当前位于 workspace lock 外，编辑工具也不持该锁。宿主应保证同工作区的写入/验证串行，必要时以任务全生命周期锁防止重复 `--resume`，不能把 daemon 锁等同于所有 Git/文件事务的互斥锁。

## 5. L0 规划：分层正确，安全条件需要重写

### 5.1 数值 confidence 筛选与真实 schema 不兼容

真实 `confidence` 是 TEXT：8234 条为 NULL，16 条为 `verified`，10 条为 `needs_review`。

直接执行规划中的 `symbol_kind='class' AND confidence>=0.9`，SQLite 实测筛出 **3 条 `needs_review` 的 behavior 规则**，而不是计划中的安全改名。相比之下，`class + change='rename' + agent_action='apply_rename' + owner IS NULL` 有 **198 条**。这只是候选集，不等于可以无条件落地。

`OS.get_ticks_msec → Time.get_ticks_msec` 也不是库里的 class rename；对其完整写法和方法名查询，本次均未找到规则。`instance → instantiate` 实际动作是 `apply_and_warn`，不能当作 `apply_rename` 的代表。

**建议**：以真实 `change / agent_action / since_version_code / until_version_code / semantic_risk / converter_gap` 等字段建立版本化白名单；处理多跳改名和冲突映射。置信标签保持枚举语义，不做数值比较。

### 5.2 AST 定位不等于符号归属已证明

替换所有 `identifier/type` 虽能避开注释和字符串，仍可能改到用户声明或局部遮蔽的同名变量。唯一 new_symbol 也不能证明调用对象是对应引擎类型。带 owner 的规则必须确认接收者类型；无法确认的规则仅给建议或升级处理。

场景类型应覆盖实际需要的 `[node] / [gd_resource] / [sub_resource] / [ext_resource]` 等类型槽位，而不只处理 node 与 ext_resource。失败解析文件和大文件必须明确跳过/升级策略。当前写工具本身拒绝 >4MB 文件，所以“L0 补转换器大文件”与“循环仍能用同一工具修大文件”并不天然同时成立。

### 5.3 intake 必须先完成运行产物与事务边界

根路标提到了 `.gitignore`、UID 和 V3，但 L0 子文档的步骤没有完整落实这些先决条件：

- `.codeindex/`、`.godot/`、锁文件、trace DB 及 `-wal/-shm`、生成探针与报告要在首次编辑前有明确存放/忽略策略。临时仓库仅写入未忽略的 `.migration_trace.db`，`precheck` 就实测返回 `DIRTY_WORKTREE`。
- 原样 `copytree` 还可能带入旧 `.codeindex` 与运行产物；已有目标目录在非 resume 模式应拒绝接管，避免来源混淆。
- 转换器可能新增文件或改扩展名，`git commit -am` 不会纳入新增文件；应明确检查变化并受控暂存全部转换结果，处理空变更。
- 需要原始来源提交与“L0 完成后的 Agent 回滚下限”两个边界。UID 清理、首次 V3 和它们产生的受版本控制变更完成后，再形成 L0 完成边界、索引并冻结；resume 不得重新转换或重新冻结。
- 转换超时不能只记录布尔值后继续称成功，必须定义部分转换产物是恢复、重做还是升级。

### 5.4 trap_scan 要区分确定错误与疑似风险

残留 yield、setget 很多已是解析错误；它们可以作为补充定位，不能重复计入收益。`TEXTURE_PIXEL_SIZE` 与 `world_vertex_coords` 在官方 4.6 CanvasItem shader 文档仍是合法项，不能按词出现即作为残留错误：[CanvasItem shader 参考](https://docs.godotengine.org/en/4.6/tutorials/shaders/shader_reference/canvas_item_shader.html)。

建议为 finding 增加规则/版本、证据、严重度和置信状态。确定不兼容项可阻塞，疑似语义风险允许“已审阅/误报/需人工”状态；修复后重扫，避免 pending_traps 永远不变。根路标点名的 `extents` 尺寸语义陷阱没有进入子文档的五项清单，应按资源类型补齐，不能用统一倍数或仅改名处理。

## 6. trace、恢复、缓存与并发的缺口

### 6.1 Git 与 SQLite 之间需要恢复协议

`gate_state_json` 只能解决状态落盘，不能让两个独立系统自动原子提交。进程可能在 Git commit 后、trace 写入前退出；也可能在 apply --index 后退出，留下脏树。

建议定义可核对的阶段，例如“准备事务 → 补丁已提交 → 验证已完成 → 轮次已落账”，保存事务 ID、前后 commit、工作树指纹，并在恢复时对账。恢复应覆盖完整 `ProjectVerifyState`，包括 `previous_view / source_snapshot`，以及宿主模型层级、成本和未完成动作。对账无法解释的工作区应退出并给人工清单，不重复执行副作用。

这不要求恢复后 LLM 输出逐字一致；应把承诺改为“可对账、幂等的恢复”，删除“100% 确定性续跑”。

### 6.2 现有 schema 不足以支持评测和全链路观测

- `repo_id PRIMARY KEY` 不能区分同一仓库的 baseline、消融、重复试验与 resume。应有独立 `run_id`，保留来源提交、实验条件、随机种子、实际模型与版本/配置指纹。
- 一轮规划允许 1–3 个 patch，但 `round_traces` 只有一个 `patch_commit_sha / diff_text`。需按 patch/attempt 记录，包含拒绝、回滚和失败；成本不能只在成功提交时入账。
- 当前表没有逐次工具调用、RAG 查询/命中、原始验证日志和基础设施状态。使用事件表或有版本的日志引用即可，不必立即搭建远程监控平台。
- 现有 RAG 已有 observer 协议，可接入；但 `retrieve_cached()` 命中时直接返回，不触发 end hook。宿主工具边界还需记录缓存命中，否则“每次检索都有账”不成立。
- 记录输入/输出/缓存 token、失败调用、重试、Judge 成本与定价版本；调用前检查并预留预算，不能只在调用结束后发现超额。

### 6.3 缓存拓扑和 key 必须明确

每工作区一份 trace DB 适合隔离，但不会自然形成跨仓库缓存。需要独立共享缓存位置，或明确统一数据库按 run_id 分区的方案。SQLite WAL 仍需短事务、忙等待和迁移策略。

LLM 修复缓存的 key 至少应纳入源/目标版本、规则与语料指纹、模型/提示与工具契约版本、必要的接收者/文件上下文。命中只能复用候选修复，仍须锚定、守卫和验证；不能将归一化的一行文本作为语义等价证明。

### 6.4 本地多进程方向正确，故障语义不要过度承诺

每工作区独立目录、每 worker 启动后加载 RAG 句柄、全局 Godot 槽位控制是合理起点。不要跨进程传 SQLite/Lance/模型句柄；所有 converter、V1/V2/V3、sweep 都要走同一限流边界。

现有 flock 不覆盖整次迁移。Manager semaphore 也不会因 worker 被 `kill -9` 就自动补回计数，已新建 session 的 Godot 子进程还可能存活。若保留崩溃恢复目标，需要监督/重建池、跟踪并回收子进程及重新核对任务状态；先只承诺正常批处理也可以，但须写明范围。

## 7. RAG 收尾规划基本正确，需缩小结论强度

可保留：散文路径对齐、manifest 输入补齐、占位入口清理、扩充错误符号提取、将已选配置作为生产候选，以及通过现有 observer 接 trace。实际规则/语料数量也与 RAG 路标一致；L0 文档的“6626 条”应同步为本次查到的 8260 条或改为启动时读取。

配置示例有一个结构问题：`tier_b.rrf_k` 应是 `tier_b.fusion.rrf_k`；`bm25/vector.enabled` 不是现有字段，通道开关是 `tier_b.channels`。当前 Pydantic 会忽略这些多余键，错误配置不一定报错。实测把顶层 `rrf_k` 设为 17，实际 fusion 仍为默认 60。

30 条 B 查询上的既有记录支持“这份样本里 identity 优于 MiniLM、0.3:0.7 是已选折中”，不支持“对真实迁移全局最优”。会话记录本身显示 1:1 在 Recall@10 上更高，而 0.3:0.7 第一命中更好，存在指标取舍。

报告的 `Prec_GT@K = |GT∩topK| / |GT|` 实际是 Recall@K 的分母，不能当作通常分母为 K 的 Precision。应改名或同时报告真正 Precision，避免误读。

已有评测脚本的 `--a-only` 会复用旧 B 明细并重新生成整份报告，因此报告生成时间和总耗时不代表 B 层当次实测。后续应分别保存各层运行时间、语料/配置/模型指纹和是否复用历史结果。

本次只确认当前真实库可打开且可检索，没有重新证明历史得分或吞吐。建议在冻结后的独立测试集上比较新旧 YAML，再决定生产默认值。

## 8. eval 规划应前移最小验收，并修正真值与评分

### 8.1 反向变异可用，但“完美语义真值”不成立

原始 4.x 文件是可靠的**参考实现/字节真值**，不是唯一合法修复。等价修复可以不同于原文，`FileAccess.open → File.new` 等也不是可普遍一对一反转的算子。

必须补充：

- `ground_truth.json` 放在评测器可读、被测 Agent 不可读的目录。按现有方案放进 sample 项目，read/grep 和模型会直接看到完整参考答案，造成泄漏。
- 先确认原项目通过目标验证，确认 mutation 确实生效，并记录它经过 L0 后是否仍残留。分别报告 L0 收益和 Agent 收益，避免只测试可机械恢复的项目。
- 每个算子限制适用语法与上下文；固定种子，训练/调参/测试按来源仓库或规则族隔离，防止同源副本泄漏。
- `ground_truth_rule_id` 使用实际数据库 ID；示例 `class:KinematicBody2D->CharacterBody2D` 不是当前库里的 ID。
- 真正 Exact Match 按字节比较；“忽略空白后相等”须另命名，且不能移除字符串内容或 GDScript 的结构性缩进。保留独立行为/属性测试衡量等价修复。
- 多条相关规则时，Recall@5 用 relevant ID 集合，区分未调用检索和调用后未召回。

`godot_test/clean-control-4x` 在当前 worktree 不存在，不能当作已验收 fixture。已提交的 `godot_test/probe_tests/fixtures/phase1/CleanControl` 可作候选，但仍应在锁定引擎上重新验收。

### 8.2 Judge 给风险判断，不能证明语义保真

保留独立 Judge 与人工校准，但建议将 `SEMANTIC_SAFE` 的对外表述收窄为“Judge 未发现语义风险”。输入应包含原始/转换边界上下文、必要的调用方/信号场景，而非只有 diff 和检索规则。未提交或回滚的假修复也应留证据，最终保留补丁与最终净 diff 都应能被审计。

增加 `INSUFFICIENT_EVIDENCE / JUDGE_ERROR`，Judge 超时、无权限或解析失败不得算作 Agent 语义错误。人工校准需包括真修复、假修复和存疑样本，报告分歧/误放/误杀，别只报一个一致率。Judge 消费的项目文本和 rationale 均应当作数据，忽略其中的指令。

### 8.3 最小 eval 不宜等到最后

完整批处理、模型对比和性能曲线可以后做；最小固定样本集与独立验证器要在首个编排闭环前就存在。否则只能证明模块单测通过，不能证明系统的成功/失败条件正确。

建议至少覆盖：正常残余修复、存量场景错误、autoload 不可信文件、循环依赖、无进展、恶化后回滚、转换超时、补丁提交后中断恢复，以及已知好/已知坏的收尾资源。结合本次复现反例建立验收边界。

## 9. 各级路标的逐份结论

- **根 `LANDMARKS.md`**：模块划分与单机去分布式方向保留；修订恢复保证、全局单槽状态、已有哨兵、实际配置和 CLI 打包前提。
- **`inline_tools/LANDMARKS.md`**：read/grep 已实现的判断成立；文档同步可做。改名索引回退与声明检查范围需增加说明。
- **`inline_tools/editandfixguard/LANDMARKS.md`**：六项问题成立；修订 create 语法解释、多改名配对及未覆盖的后缀/索引漏报。
- **`codebase_index/LANDMARKS.md`**：底座已有实现成立；数据库路径、配置键与引擎版本描述需统一。
- **`codebase_index/index/LANDMARKS.md`**：freeze 和路径解析问题成立；依赖排序先补提取能力，新增中文偏移缺陷。
- **`codebase_index/index/src/codeindex/scene/LANDMARKS.md`**：三个核心缺陷成立；修复示例按实际函数、返回类型及 SQL 列重写。冗余表达式清理可后置。
- **`codebase_index/godot_mcp/LANDMARKS.md`**：状态隔离、熔断、配置和触发盲区判断成立；修订实际模型与“快照回滚”描述，增加每 run 独立状态与串行事务要求。
- **`rag/LANDMARKS.md`**：数据规模与主体完成判断成立；删除无量化依据的 98%，把剩余工作表述为整合/验收缺口。
- **`rag/build/LANDMARKS.md`**：路径和 stub 问题成立；将旧路径测试的 skip 改为真实验证，补齐构建输入指纹。
- **`rag/retriever/LANDMARKS.md`**：调优与符号提取方向成立；修订 YAML 嵌套和“最优”表述，区分指标及历史复用。
- **`migration_agent/LANDMARKS.md`**：宿主包建设范围合理；明确新增依赖、实际模型配置、目标引擎版本与可安装的 CLI。根文档 `migrate-godot` 和子文档 `migrate-agent` 名称应统一。
- **`migration_agent/l0/LANDMARKS.md`**：两阶段策略保留；修订 confidence、安全白名单、真实执行器、工作区接管和 L0 完成边界。
- **`migration_agent/orchestrator/LANDMARKS.md`**：闭环思路保留；API/决策/sweep 必须改，明确整轮补丁回滚和覆盖验收。
- **`migration_agent/trace/LANDMARKS.md`**：SQLite 方向保留；补 run_id、事件/attempt、跨系统对账和独立缓存位置。
- **`migration_agent/eval/LANDMARKS.md`**：Judge、变异和批处理方向保留；真值隔离、适用域、替代正确解、校准及崩溃语义需要补齐。

全部路标的导航还绑定到另一台工作树的绝对 `file:///Users/.../.gemini/...` 路径。建议统一相对链接，并去掉易漂移的旧行号；根 `ARCHITECTURE.md` 在当前提交中也不存在，不应当作已存在的权威入口。

索引总览中的 FTS5、`watchdog` 描述也需改：当前符号查询依赖普通 SQLite 表及索引，未发现 FTS5 建表；文件监听使用的是 `watchfiles`。这些属于文档清理，不需要为使文档“正确”而额外实现新设施。

## 10. 验证命令与后续实施入口

以下为本次通过的四组测试命令。虚拟环境路径为本机已有环境，源码路径以本 worktree 为准：

```bash
PYTHONPATH=.:codebase_index/index/src '/Users/yy_catmax/workspace/Godot Workspace/godot3_to_4_migration_agent/.venv/bin/python' -m pytest inline_tools/tests inline_tools/editandfixguard/tests -q -p no:cacheprovider
PYTHONPATH=codebase_index/index/src '/Users/yy_catmax/workspace/Godot Workspace/godot3_to_4_migration_agent/codebase_index/index/.venv/bin/python' -m pytest codebase_index/index/tests -q -p no:cacheprovider
PYTHONPATH=codebase_index/godot_mcp/src '/Users/yy_catmax/workspace/Godot Workspace/godot3_to_4_migration_agent/codebase_index/godot_mcp/.venv/bin/python' -m pytest codebase_index/godot_mcp/tests -q -p no:cacheprovider
PYTHONPATH=. HF_HUB_OFFLINE=1 FASTEMBED_CACHE_PATH=/Users/yy_catmax/.cache/fastembed '/Users/yy_catmax/workspace/Godot Workspace/godot3_to_4_migration_agent/rag/.venv/bin/python' -m pytest rag/test -q -p no:cacheprovider
```

进入开发前，建议先将本报告中阻断整合的契约纠正回各级路标，并把新发现的底层问题纳入 Phase 0。随后以最小样本验证 L0—编辑—验证—报告的单仓闭环，再扩展持久恢复、Judge 和多仓批处理。完整功能拆分可沿用原来的目录结构；具体依赖顺序与验收门见同目录未入 Git 的 `DESIGN_NOTES.md`。
