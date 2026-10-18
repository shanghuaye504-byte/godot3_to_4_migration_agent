# 全项目问题总账：按修复与开发顺序

[完整实现指导](LANDMARKS.md) · [历史证据](LANDMARKS_REVIEW.md)。

本文件汇总全部范围的问题及新增能力的验收顺序。**先从 S00 开始，不按严重度把列表打乱。** 一项会影响后续几步时，先在首次出现处修基础，后续再做整合验收。

状态说明：已复现/源码确认＝现有实现问题；规划风险＝组件尚未实现，先写所描述的反例测试；本轮文档已纠正＝文字修了，不代表代码能力已补齐。

复现的默认环境：临时 Godot 项目、临时 SQLite/Git；不要改用户源项目。需要 Gate 对象时复用 `codebase_index/godot_mcp/tests/verify_gate/helpers.py`；需要真实引擎时先完成 S00。

## 下级导航

- [原生工具](inline_tools/DEFECTS.md)
- [索引与验证底座](codebase_index/DEFECTS.md)
- [迁移知识库](rag/DEFECTS.md)
- [宿主与命令行](migration_agent/DEFECTS.md)

## 本轮补充的观测与评测风险

新增 OTel 统一调用链缺失（TRC-05，S14）、导出/恢复混用与跨进程断链（TRC-06，S19）、平台评分来源与幂等缺失（EVAL-04，S21）。这些是尚未实现能力的设计反例，不冒充现有线上事故。S01 先固定测试契约，S14 接 Langfuse/Phoenix，后续逐步验收恢复和实验；完整顺序仍以下面队列为准。

## 全量执行与关闭清单

<a id="s00"></a>

### S00：固定环境、真实接口与观测配置

- [x] **本步全部工作**：固定 Python/依赖、目标 Godot、规则/语料指纹与 OTel 语义约定版本。检查 OTLP HTTP、Collector 和 Langfuse/Phoenix endpoint 的配置格式；凭据只引用环境变量。先补真实 API 契约，不接模型。

**交付与测试门**：交付环境与接口检查；记录四组测试结果。观测 profile 区分 offline/双后端，缺引擎或缺后端部署均写待验收，不伪造可用。 异 CWD 冒烟；未知键、缺引擎、错误协议/endpoint 明确失败；离线单测不要求后端在线。

**实现指导**：[S00](LANDMARKS.md)。

- [x] [DOC-01 · 旧规划把不存在的接口当作可复用能力](DEFECTS.md)。**范围**：`.`；**状态**：契约测试已通过。例：按旧示例读取 gate.action 会失败；RetrievalQuery(query="instance") 缺少 target_version，也没有提供有效查询字段。

<a id="s01"></a>

### S01：先建最小独立评测器与观测契约测试

- [ ] **本步全部工作**：先定义固定 case、隐藏真值、结果分类与独立验证器；同时写 OTel span/评分字段契约和内存 exporter 反例。六类项目先用 fake verifier，再补锁定引擎集成验证。

**交付与测试门**：交付正确/错误/等价替代对照，隐藏答案位于 Agent 工作区外。定义 case_id→run_id→trace/span 的关联及评分明细格式，OTel 正式接线在 S14。 错误不通过、缺证据标 INVALID/INCOMPLETE；read/grep 不读真值；fake 调用树与评分重复提交测试先固定预期。

**实现指导**：[S01](LANDMARKS.md)。

- [ ] [EVAL-01 · 参考答案放进项目副本会泄漏给 Agent](migration_agent/eval/DEFECTS.md)。**范围**：`migration_agent/eval`；**状态**：规划风险；模块未实现。例：模型搜索原报错符号时，直接在 ground_truth.json 里找到健康文件，无需完成迁移推理。

<a id="s02"></a>

### S02：修中文索引与配置路径

- [ ] **本步全部工作**：先修 UTF-8 span，再统一规则库配置相对路径。这两项会影响后面的符号守卫、场景规则和跨目录调用。

**交付与测试门**：交付 parser 切片修复和确定的路径规则；改动目录 README 同步。 中文注释/字符串/标识符正确；同配置不同 CWD 得到同规则库。

**实现指导**：[S02](LANDMARKS.md)。

- [ ] [IDX-01 · 中文让符号名和调用关系切片错位](codebase_index/index/DEFECTS.md)。**范围**：`codebase_index/index`；**状态**：已复现；代码待修。例：输入“# 中文”后接 class_name Player，实际索引名变为 er\next；func move 的名字也被切坏。
- [ ] [CFG-01 · 规则库相对路径跟着启动目录漂移](codebase_index/DEFECTS.md)。**范围**：`codebase_index`；**状态**：源码确认；代码待修。例：配置在 /tmp/configs/config.yaml，规则路径为 rules.db；从项目根启动时却寻找项目根/rules.db。

<a id="s03"></a>

### S03：补依赖提取，再做根因排序

- [ ] **本步全部工作**：提取顶层/函数体 preload 与路径/类名 extends 的文件依赖。新增 rank_root_cause_files，返回排序及无法解析的证据；不查询不存在的 relations 表。

**交付与测试门**：交付依赖查询 API；循环先聚成组，再按被依赖关系排序；同分时使用稳定路径排序。 链式、经无报错中间节点、循环、未知目标和中文脚本均有反例；根因优先，未知不伪装已解析。

**实现指导**：[S03](LANDMARKS.md)。

- [ ] [IDX-02 · 现有依赖边不足以排序根因脚本](codebase_index/index/DEFECTS.md)。**范围**：`codebase_index/index`；**状态**：已复现；能力待补。例：const Dep = preload("res://dep.gd") 没有边；函数内同样调用得到 to_name="preload"，无法知道目标文件。

<a id="s04"></a>

### S04：修真实规则库接入和场景增量对比

- [ ] **本步全部工作**：用真实 migration_rules 库打通旧类型检查，再限制增量 fixed 的计算范围。

**交付与测试门**：交付规则库兼容读取和实际已检查范围传递；保留规则不可用的覆盖标记。 旧引擎类型可检出；只查 a 不会宣称 b 已修；合法新类型不被误报。

**实现指导**：[S04](LANDMARKS.md)。

- [ ] [SCN-01 · 真实规则库查错表，旧类型检查被静默跳过](codebase_index/index/src/codeindex/scene/DEFECTS.md)。**范围**：`codebase_index/index/src/codeindex/scene`；**状态**：已复现；代码待修。例：场景节点仍是 KinematicBody2D，使用真实 rules.db 检查却没有 E_UNMIGRATED_TYPE，只有 rules_unavailable=True。
- [ ] [SCN-02 · 只检查一个场景，却宣布其他场景已修复](codebase_index/index/src/codeindex/scene/DEFECTS.md)。**范围**：`codebase_index/index/src/codeindex/scene`；**状态**：已复现；代码待修。例：a.tscn、b.tscn 都有 format=2；仅检查 a，返回 fixed 中却含仍未修改的 b。

<a id="s05"></a>

### S05：修场景回调归属并接通一次性冻结

- [ ] **本步全部工作**：先修同名回调跨脚本误报和多引用漏报，再实现 run_scene_freeze/scene-freeze；冻结要保存独立标记及 L0 commit。

**交付与测试门**：交付单事务冻结与重复冻结拒绝。空问题基线也有标记，恢复不重新冻结。 根/子节点、跨脚本同名、多个场景；重复与中断冻结不洗掉原有证据。

**实现指导**：[S05](LANDMARKS.md)。

- [ ] [SCN-03 · 同名回调跨脚本误报，并且只报第一个引用](codebase_index/index/src/codeindex/scene/DEFECTS.md)。**范围**：`codebase_index/index/src/codeindex/scene`；**状态**：已复现；代码待修。例：enemy.gd 删除 _on_hit，仍被错误地报告为 player.tscn 的问题；该场景实际上只挂 player.gd。
- [ ] [SCN-04 · 基线有底层函数，却没有安全的生产冻结入口](codebase_index/index/src/codeindex/scene/DEFECTS.md)。**范围**：`codebase_index/index/src/codeindex/scene`；**状态**：源码确认；入口待实现。例：改坏函数后再次冻结，原来的“新回归”被当作 pre_existing。空问题基线也无法仅凭行数判断是否已冻结。

<a id="s06"></a>

### S06：接通改名守卫和公开编辑入口

- [ ] **本步全部工作**：公开导出 edit；检测声明改名并查询场景引用；索引空/坏/过期时可靠回退 grep。

**交付与测试门**：交付可调用包入口和 INCONSISTENT_RENAME 警告；不任意配对多改名，不将警告误变成硬拒绝。 实际 edit 到 commit 的测试覆盖单/多改名、纯删除及索引回退。

**实现指导**：[S06](LANDMARKS.md)。

- [ ] [EDT-01 · 包入口没有导出约定的 edit API](inline_tools/editandfixguard/DEFECTS.md)。**范围**：`inline_tools/editandfixguard`；**状态**：源码确认；代码待修。例：from inline_tools.editandfixguard import edit 可能得到子模块，直接调用会报 module 不可调用。
- [ ] [EDT-02 · 函数改名后场景仍用旧名，编辑流水线没有提醒](inline_tools/editandfixguard/DEFECTS.md)。**范围**：`inline_tools/editandfixguard`；**状态**：源码确认；代码待修。例：把 on_hit 改为 on_damage，场景 connection.method 仍为 on_hit，编辑结果没有 INCONSISTENT_RENAME。
- [ ] [EDT-03 · 索引文件存在就关闭 grep 回退，导致漏报](inline_tools/editandfixguard/DEFECTS.md)。**范围**：`inline_tools/editandfixguard`；**状态**：已复现；代码待修。例：不用索引能 grep 到 old_callback；传一个已经建表但没有场景数据的索引后，警告变成 0 条。

<a id="s07"></a>

### S07：统一 create 与场景写后验收

- [ ] **本步全部工作**：新脚本显式验语法；场景写前和写后都只拒绝新增回归。

**交付与测试门**：交付失败不改变字节/HEAD、合法改动只产生目标提交的编辑事务。 新建坏脚本失败；存量坏场景的无回归改动成功；新增场景错误回滚。

**实现指导**：[S07](LANDMARKS.md)。

- [ ] [EDT-04 · 写后复核把存量场景错误当作新回归](inline_tools/editandfixguard/DEFECTS.md)。**范围**：`inline_tools/editandfixguard`；**状态**：已复现；代码待修。例：只改 format=2 场景的一项无关合法属性，存量 E_NOT_CONVERTED 仍在，写后返回 SCENE_REGRESSION。
- [ ] [EDT-05 · create 绕过语法和反向迁移检查](inline_tools/editandfixguard/DEFECTS.md)。**范围**：`inline_tools/editandfixguard`；**状态**：已复现；代码待修。例：create 内容为 func broken(:，当前 ok=True 并产生 commit，实际上有一个语法错误节点。

<a id="s08"></a>

### S08：补所有文本后缀守卫与适用范围

- [ ] **本步全部工作**：分清声明消失与旧 API 使用；按 owner/版本判断，覆盖场景/shader/配置通用风险；同时清理临时补丁泄漏。

**交付与测试门**：交付保守的符号适用检查、逐后缀守卫矩阵和完整临时文件清理。 同名自定义函数不误拒，真旧 API 有证据；成功/失败/超时均无临时补丁遗留。

**实现指导**：[S08](LANDMARKS.md)。

- [ ] [EDT-06 · 非脚本文件缺通用守卫，场景删除也未覆盖](inline_tools/editandfixguard/DEFECTS.md)。**范围**：`inline_tools/editandfixguard`；**状态**：源码确认；代码待修。例：删除场景的 connection 行仍是合法场景；删除 shader 的关键逻辑也不一定产生文本语法错误。
- [ ] [EDT-07 · G5.1 只看声明名字，既漏旧 API 又误杀用户函数](inline_tools/editandfixguard/DEFECTS.md)。**范围**：`inline_tools/editandfixguard`；**状态**：已复现；代码待修。例：extends KinematicBody2D 或 .instance() 没被拦；自定义 func get_name() 却被当作另一类型的旧方法拒绝。
- [ ] [EDT-08 · git apply 临时补丁文件未清理](inline_tools/editandfixguard/DEFECTS.md)。**范围**：`inline_tools/editandfixguard`；**状态**：源码确认；代码待修。例：连续提交 100 个补丁，临时目录可能多出约 200 个 .patch 文件。

<a id="s09"></a>

### S09：隔离局部检查、修熔断和阈值接线

- [ ] **本步全部工作**：局部检查不进入全库历史；OPEN 在启动 Godot 前短路；入口注入实际 RetryGateConfig。

**交付与测试门**：交付稳定的 VerifyGateResult；继续使用真实 decision 枚举，明确重置策略。 全库 A→局部空→全库 A 不假震荡；真全库循环会停；OPEN 后 spawn=0；自定义阈值生效。

**实现指导**：[S09](LANDMARKS.md)。

- [ ] [VER-01 · 局部检查污染全库历史，造成假震荡](codebase_index/godot_mcp/DEFECTS.md)。**范围**：`codebase_index/godot_mcp`；**状态**：已复现；代码待修。例：全库 {A,B} → 检查一个干净文件 ∅ → 全库 {A,B}，当前触发 OSCILLATION_ESCALATE。
- [ ] [VER-02 · 熔断已 OPEN，下一次健康输出又允许继续](codebase_index/godot_mcp/DEFECTS.md)。**范围**：`codebase_index/godot_mcp`；**状态**：已复现；代码待修。例：3 次 CRASH 后状态为 OPEN；再传健康输出，decision 却是 CONTINUE、hard_stop=False。
- [ ] [VER-03 · retry_gate YAML 没接到默认工具入口](codebase_index/godot_mcp/DEFECTS.md)。**范围**：`codebase_index/godot_mcp`；**状态**：源码确认；代码待修。例：把 rounds_limit 设置为 2，默认工具仍按 40 轮记账。

<a id="s10"></a>

### S10：补验证快照与重导触发范围

- [ ] **本步全部工作**：快照包含实际编辑后缀；识别内嵌 shader/项目配置、class_name 与重复 UID 双端修复。

**交付与测试门**：交付差异可见性及按需 V3 触发。快照仍只作观察，不充当文件恢复协议。 逐后缀 diff、UID 两端与 class 声明变体；用注入 spawn 验证 V3 次数，再补真实引擎检查。

**实现指导**：[S10](LANDMARKS.md)。

- [ ] [VER-04 · 快照漏场景/项目配置，相关修改无法驱动重导](codebase_index/godot_mcp/DEFECTS.md)。**范围**：`codebase_index/godot_mcp`；**状态**：源码确认；代码待修。例：只改 main.tscn 的内嵌 Shader 或 project.godot 的 autoload，快照差异可能为空。
- [ ] [VER-05 · class_name 与重复 UID 的重导触发有盲区](codebase_index/godot_mcp/DEFECTS.md)。**范围**：`codebase_index/godot_mcp`；**状态**：源码确认；代码待修。例：重复 UID 出现在 a.tscn 和 z.tscn，修 z 时只匹配到 a，未触发需要的 V3。

<a id="s11"></a>

### S11：绑定每次运行的状态、锁和索引同步

- [ ] **本步全部工作**：规定每 run 独立 StateStore、生命周期锁、串行 edit/verify 与绑定 Config 的 sync_fn。整组回滚重索引全部 changed paths。

**交付与测试门**：交付可被宿主复用的运行上下文边界；避免重复持同一非重入 flock。 两个项目不串库/串轮次；并发接管被拒；多文件回滚后源码与索引一致。

**实现指导**：[S11](LANDMARKS.md)。

- [ ] [VER-06 · 全局单槽状态和锁范围不适合多次仓库运行](codebase_index/godot_mcp/DEFECTS.md)。**范围**：`codebase_index/godot_mcp`；**状态**：已复现及源码确认；整合待修。例：同一 worker 先处理仓库 A 再处理 B，B 首次 check_file 的 round_index 为 2；并行工具调用还可能同时通过干净树检查。
- [ ] [EDT-09 · 同步没有绑定当前项目，整轮回滚又只刷新一个文件](inline_tools/editandfixguard/DEFECTS.md)。**范围**：`inline_tools/editandfixguard`；**状态**：源码确认；整合待修。例：编辑输出工作区 B，却让 CLI 按配置中的项目 A 写索引；回滚 a/b 后只刷新 a，b 的旧符号还留在库里。

<a id="s12"></a>

### S12：修 RAG 输入路径并清理失效入口

- [ ] **本步全部工作**：统一 prose 枚举和 manifest 输入哈希；旧命令转发到真实 build/eval；移除误生成会话文件。

**交付与测试门**：交付不靠 skip 的产物检查；构建测试使用临时输出，不覆盖已冻结语料。 8 份散文被锁定，修改输入使指纹变化；缺预期产物 fail；--skip-embed 不联网。

**实现指导**：[S12](LANDMARKS.md)。

- [ ] [RAG-01 · 散文写入与读取路径不一致，测试靠 skip 避开](rag/build/DEFECTS.md)。**范围**：`rag/build`；**状态**：已复现及源码确认；代码待修。例：8 份 prose.jsonl 实际存在，但 test_prose_jsonl_present 跳过；修改这些散文可能不改变 manifest 中的输入锁定。
- [ ] [RAG-05 · 旧构建和评测命令仍是占位壳](rag/build/DEFECTS.md)。**范围**：`rag/build`；**状态**：源码确认；清理待做。例：运行 build_tier_b.py 看见占位退出，而 README 可能仍指向它。

<a id="s13"></a>

### S13：修检索配置、符号提取和 OTel 观测事件

- [ ] **本步全部工作**：拒绝未知键，使用 fusion.rrf_k/channels，补真实报错句式。统一 observer 的开始/结束/缓存字段，为 S14 的 OTel 适配保留 request/call_id；候选参数留 S21 独立复验。

**交付与测试门**：交付命中/未命中均可关联的检索事件；只记录必要候选 ID、版本、排序与耗时，不将真值送进检索输入。 两次调用、一次缓存命中可观测；observer 异常不改变检索结果；宿主与库不重复记账；规则/语料可打开。

**实现指导**：[S13](LANDMARKS.md)。

- [ ] [RAG-02 · 错误配置键被忽略，调参看似成功实则未生效](rag/retriever/DEFECTS.md)。**范围**：`rag/retriever`；**状态**：已复现；配置校验待修。例：把 tier_b.rrf_k 设为 17，实际 config.tier_b.fusion.rrf_k 仍是 60。
- [ ] [RAG-03 · 报错符号提取不足，精确检索被跳过](rag/retriever/DEFECTS.md)。**范围**：`rag/retriever`；**状态**：源码确认；代码待修。例：Invalid set index 与 Function "instance" not found 不命中已有 get-index/Nonexistent-function 正则。
- [ ] [RAG-06 · 缓存命中不触发观测钩子，调用账本少一段](rag/retriever/DEFECTS.md)。**范围**：`rag/retriever`；**状态**：源码确认；整合待修。例：相同查询调用两次，第二次 cache_hit=True，却只有第一次产生 retrieve-end。

<a id="s14"></a>

### S14：实现宿主、SQLite 账本与 OTel 双后端接线

- [ ] **本步全部工作**：补根包、CLI、RunContext 与七工具适配器；实现每调用预算预留/结算。同步建单一 OTel 埋点→Collector→Langfuse/Phoenix，并将 run/round/attempt/call 关联到 trace/span。

**交付与测试门**：交付 TraceStore、budget、telemetry/observer 适配器、版本化语义映射和可选部署配置。Langfuse 看模型/成本/实验，Phoenix 看检索/调用分析；SQLite 管恢复和完整账本。 异 CWD、双 run、多 attempt、预算不足零调用；内存 exporter/假 OTLP 接收器测调用树、缓存、拒绝、脱敏与断网。再用 fake 业务做真实双后端联调，凭 trace_id 查询一致；部署不可用则保留待验收。

**实现指导**：[S14](LANDMARKS.md)。

- [ ] [ORC-01 · 宿主若照旧签名封装，工具无法完成一次调用](migration_agent/orchestrator/DEFECTS.md)。**范围**：`migration_agent/orchestrator`；**状态**：规划契约已纠正；适配器待实现。例：编辑返回 ok/commit，宿主却等 status=COMMITTED，于是漏记补丁；Gate 从不返回 UPGRADE_MODEL_TIER。
- [ ] [TRC-01 · 按 repo_id 保存一行，无法区分试验和多个补丁](migration_agent/trace/DEFECTS.md)。**范围**：`migration_agent/trace`；**状态**：规划风险；存储待实现。例：同仓库先 with-RAG 再 without-RAG，第二次启动覆盖前一 run 的状态。
- [ ] [TRC-04 · 只给成功轮次记成本，预算与可观测性不完整](migration_agent/trace/DEFECTS.md)。**范围**：`migration_agent/trace`；**状态**：规划风险；账本待实现。例：两次 LLM 重试都失败、没有 patch，但 API 已计费；旧 round_traces 可能仍显示成本 0。
- [ ] [TRC-05 · 缺少统一调用链，检索、补丁与引擎失败无法关联](migration_agent/trace/DEFECTS.md)。**范围**：`migration_agent/trace`；**状态**：新增规划风险；OTel 和后端尚未接入。例：一次缓存命中后模型生成坏补丁，guard 拒绝，随后 verify 超时；若只记 round 总耗时，就无法区分检索、模型、守卫还是引擎导致失败。

<a id="s15"></a>

### S15：实现隔离 intake 与 L0 事务边界

- [ ] **本步全部工作**：受控复制项目、原始提交、转换、UID/首次导入，形成 L0 完成提交；刷新索引并冻结一次。

**交付与测试门**：交付 run_l0_pipeline 初版及超时/不支持类型/已有目标的明确出口；转换执行器单独封装，不引用不存在的 run_subprocess。 源不变、转换新增文件入提交、缓存不弄脏树、失败不标完成、二次启动非 resume 被拒。

**实现指导**：[S15](LANDMARKS.md)。

- [ ] [L0-03 · 接管工作区会带脏产物，转换提交还可能漏新增文件](migration_agent/l0/DEFECTS.md)。**范围**：`migration_agent/l0`；**状态**：已复现的组合问题；intake 待实现。例：仅创建未忽略 .migration_trace.db，下一次编辑就 DIRTY_WORKTREE；转换生成新 .gdshader 时 -am 不提交它。

<a id="s16"></a>

### S16：增加小白名单 codemod 和可结案陷阱扫描

- [ ] **本步全部工作**：从真实规则筛候选，证明归属后才修改；扫描静默语义风险并支持复扫/确认/排除。循环期确定性替换也走唯一写工具。

**交付与测试门**：交付 dry-run 清单、逐规则替换证据与 StaticTrapFinding；初版超大/未解析文件升级人工，不承诺机械修完。 安全改名正例加同名用户符号反例；场景四类 type 槽位；合法 shader 不误报；无修改算子不计收益。

**实现指导**：[S16](LANDMARKS.md)。

- [ ] [L0-01 · 把文字置信标签按数值筛选，选中了错误规则](migration_agent/l0/DEFECTS.md)。**范围**：`migration_agent/l0`；**状态**：真实库查询已复现；codemod 待实现。例：class AND confidence>=0.9 实际返回 3 条 needs_review 的 behavior，而非 198 条候选 apply_rename 类规则。
- [ ] [L0-02 · AST 找到同名节点，不代表它属于引擎 API](migration_agent/l0/DEFECTS.md)。**范围**：`migration_agent/l0`；**状态**：规划风险；codemod 待实现。例：用户局部变量 Spatial 被改成 Node3D；自定义对象的 instance() 被误改。大于 4MB 文件又被当前写工具拒绝。
- [ ] [L0-04 · 静态陷阱误报合法语法，且没有消项机制](migration_agent/l0/DEFECTS.md)。**范围**：`migration_agent/l0`；**状态**：规划风险；扫描器待实现。例：合法 canvas_item 的 TEXTURE_PIXEL_SIZE 或 world_vertex_coords 仅因出现就触发陷阱，Agent 被迫“修”正确代码。

<a id="s17"></a>

### S17：实现补充资源扫描与完整成功条件

- [ ] **本步全部工作**：先复用 V1 哨兵与 V3，再补资源/不可信文件验证；动态脚本不带 check-only。独立 success_policy 综合各维覆盖。

**交付与测试门**：交付 load_sweep、完整资源清单、每项哨兵/超时日志与成功谓词；没有运行证据就标不完整。 先用 S01 好/坏/缺证据矩阵；然后真实引擎验证孤立坏资源、干净对照、崩溃续查。

**实现指导**：[S17](LANDMARKS.md)。

- [ ] [ORC-03 · 动态资源扫描带 check-only，循环不会执行](migration_agent/orchestrator/DEFECTS.md)。**范围**：`migration_agent/orchestrator`；**状态**：命令语义已核对；扫描器待实现。例：扫描脚本的 _initialize 中打印 SCAN_DONE 并加载坏场景；旧命令可能既没打印也没发现坏场景。
- [ ] [ORC-02 · 根因为空或 CLEAN 不等于验证完整](migration_agent/orchestrator/DEFECTS.md)。**范围**：`migration_agent/orchestrator`；**状态**：底层状态已复现；宿主成功门待实现。例：project_status=CLEAN，但 probe_incomplete=True、gdscript_complete=False；场景 pre_existing 也仍是未解决错误。

<a id="s18"></a>

### S18：接通单仓编排、原生 checkpoint 与有界路由

- [ ] **本步全部工作**：先 rule-only/fake 跑闭环，再接 L1/L2；编译图时接原生 SqliteSaver，固定 thread_id=run_id、durability="sync"，将图状态与运行时句柄分离。所有分支关联 OTel；外部副作用崩溃窗口在 S19 验收。

**交付与测试门**：交付 graph/state/prompts、checkpoint 工厂及单仓报告；图执行位置/提案/消息/完整 Gate 状态由 checkpoint 恢复，业务 SQLite 只保留审计、成本和副作用回执。 假模型闭环、有限重试/循环/预算出口；用全新进程重开同一 checkpoint 恢复提案和待执行节点；验证缓存/失败 span、持久化序列化和 run 隔离。不将此步等同于完整 kill 恢复验收。

**实现指导**：[S18](LANDMARKS.md)。

- [ ] [ORC-04 · 新增诊断就回滚，会把真正进展当作恶化](migration_agent/orchestrator/DEFECTS.md)。**范围**：`migration_agent/orchestrator`；**状态**：规划风险；宿主策略待实现。例：语法错误 A 修好，原来就存在的类型错误 B 被暴露；机械比较签名集合会将正确补丁回滚。
- [ ] [ORC-05 · 图状态恢复未指定原生 checkpointer，容易与审计账本重复实现](migration_agent/orchestrator/DEFECTS.md)。**范围**：`migration_agent/orchestrator`；**状态**：规划遗漏已纠正；checkpointer 尚未接入。例：模型已经生成补丁提案后退出，重新建图若未配置持久化 checkpointer，就无法读取原目标、消息和下一节点；只查 round 记录也不能还原 LangGraph 调度状态。

<a id="s19"></a>

### S19：实现 checkpoint 恢复与外部副作用对账

- [ ] **本步全部工作**：先持工作区锁，校验图/状态 schema、引擎和配置指纹，再对账 Git/业务 SQLite/索引；使用同一 thread_id 读取最新 checkpoint 并恢复待执行节点。以稳定 operation_id 识别已完成副作用，恢复创建关联的新 OTel trace。

**交付与测试门**：交付 resume 对账器，不自建第二套图调度器；checkpoint 管图状态，Git/SQLite 管代码回执与完整账本。已完成 L0/冻结不重做；模型请求结果不明时保留未知费用，不宣称所有外部调用恰好一次。 apply/commit/verify/下一 checkpoint 写入前四类中断；回执已存而图结果未存时安全返回旧回执，不重复受控补丁；Gate 历史/预算不重置，未知脏树或版本不匹配拒绝；新旧 OTel trace 可关联。

**实现指导**：[S19](LANDMARKS.md)。

- [ ] [TRC-02 · Git、副作用账本与图 checkpoint 之间有崩溃窗口](migration_agent/trace/DEFECTS.md)。**范围**：`migration_agent/trace`；**状态**：规划风险；恢复协议待实现。例：edit 已生成提交 C，但 apply 节点在保存结果前被 kill；checkpoint 仍停在 apply 之前。仅恢复图就再调 edit，可能重复补丁或遇到脏树。
- [ ] [TRC-06 · 观测导出与恢复混用会丢账，进程切换还会断链](migration_agent/trace/DEFECTS.md)。**范围**：`migration_agent/trace`；**状态**：新增规划风险；恢复和导出未实现。例：模型已经产生费用，但 exporter 断网；若根据后端 span 累计预算就漏账。恢复时换一个 worker，若只传 run_id，则新 trace 与原运行没有明确关联。

<a id="s20"></a>

### S20：增加共享修复缓存

- [ ] **本步全部工作**：在最小闭环与恢复可靠后，才优化跨仓复用；共享缓存库独立于每仓 trace，记录候选来源和失效原因。

**交付与测试门**：交付带版本/上下文指纹的缓存；命中仍走守卫/验证；跨仓命中率与实际节省调用可重算。 不同版本/owner 不碰撞；坏候选不重复应用；并发写不丢记录。

**实现指导**：[S20](LANDMARKS.md)。

- [ ] [TRC-03 · 每仓本地缓存不能跨仓复用，短 key 又可能复用错修复](migration_agent/trace/DEFECTS.md)。**范围**：`migration_agent/trace`；**状态**：规划风险；缓存待实现。例：两个仓库都有 .instance()，一个是 PackedScene，另一个是自定义类；过短 key 将同一补丁用到两者。

<a id="s21"></a>

### S21：扩展变异、复验 RAG 并接入平台实验

- [ ] **本步全部工作**：逐例验证健康原版、变异生效和 L0 后残留；独立复验 RAG。新增 Langfuse/Phoenix 的 dataset/experiment/score 适配，评分先本地落盘再幂等推送。

**交付与测试门**：交付可复现样本与逐项结果、两后端对象映射和 outbox。每个 case 关联 run/trace、规则/配置/评测器指纹；同一评分复用，两端不重复跑模型。 等价解/行为/字节分开；fresh/reused 和调参/测试隔离；上传断网/重复/响应丢失不重复逻辑评分，两端汇总可由本地明细复算。

**实现指导**：[S21](LANDMARKS.md)。

- [ ] [EVAL-02 · 逐字参考不等于唯一正确解，变异也可能没有测到 Agent](migration_agent/eval/DEFECTS.md)。**范围**：`migration_agent/eval`；**状态**：规划风险；评分器待实现。例：“a b”与“ab”去空白后相等但语义不同；两种等价 await 写法又可能被 Exact Match 拒绝。
- [ ] [RAG-04 · 历史复用和指标命名容易把旧结果说成新实测](rag/eval/DEFECTS.md)。**范围**：`rag/eval`；**状态**：源码和报告确认；评测待修。例：新报告显示总耗时 0.07 秒，读者误以为当天重新加载并跑完了 BGE/MiniLM；实际 B 结果来自旧明细。
- [ ] [EVAL-04 · 平台评分没有来源与幂等关联，会重复计分或混用实验](migration_agent/eval/DEFECTS.md)。**范围**：`migration_agent/eval`；**状态**：新增规划风险；评测适配器尚未实现。例：同一 case 上传超时后重试，后台出现两个得分；或无 RAG 实验的评分错挂到有 RAG trace，最终对比无法复算。

<a id="s22"></a>

### S22：实现独立 Judge、人工校准与关联标注

- [ ] **本步全部工作**：程序结果确定事实后，独立 Judge 审语义风险；原始/最终上下文齐全，缺证据与 Judge 故障分流。Judge 调用走 OTel，结果和人工标注关联原 patch/trace/span。

**交付与测试门**：交付结构化 verdict 和校准样本；人工/程序/Judge 分开命名、版本化，一份结果同步两平台，审最终净 diff 及保留 patch。 好/坏/存疑/缺证据/模型故障对照；人工误放/误杀/分歧可复算，Judge 费用完整入账，两端不重复评判。

**实现指导**：[S22](LANDMARKS.md)。

- [ ] [EVAL-03 · Judge 的证据不足与调用失败没有独立出口](migration_agent/eval/DEFECTS.md)。**范围**：`migration_agent/eval`；**状态**：规划风险；Judge 待实现。例：没有场景信号上下文时看不出回调参数丢失；Judge 超时却被当作 FAKE_FIX 会低估修复率。

<a id="s23"></a>

### S23：完成平台对比实验、baseline 与消融报告

- [ ] **本步全部工作**：冻结条件后比较有/无 RAG、有/无 L0、rule-only 和通用 coding agent；每条件独立 run_id。Langfuse/Phoenix 关联同一实验清单、trace 与评分，多次试验记录方差。

**交付与测试门**：交付修复率/覆盖/Judge 风险、成本/耗时、人工介入和失败归因。报告含本地逐项来源和后端实验链接；初始错误为零的削减率为 N/A。 本地与两端分母、指标和版本一致；引擎/Judge/导出故障单列；评测全采样，生产采样数据不当完整统计；真实 token 节省与估算分开。

**实现指导**：[S23](LANDMARKS.md)。

本步是新增能力/系统验收，不伪造已有代码 Bug；其失败对照和完成标准已列在实现指导及本步测试门。

<a id="s24"></a>

### S24：实现进程池批处理、上下文传播与限流

- [ ] **本步全部工作**：每 worker 启动后新建模型/SQLite/Lance 和 OTel provider/exporter；任务信封注入/提取 W3C traceparent/tracestate。所有 converter/V1/V2/V3/sweep 经同一 Godot 槽位边界。 每 run 独立 checkpoint 文件，worker 重开 SqliteSaver；同一 thread_id 不允许并发恢复。

**交付与测试门**：交付 batch CLI、独立运行目录、跨进程关联和正常吞吐数据；正常退出有界 flush/shutdown，不继承活跃导出线程。 1/2/4 worker 结果一致、同名不冲突、进程峰值受限；子进程 span 关联正确且不重复埋点，后端故障不打满 worker；单仓失败不抹掉其余结果。

**实现指导**：[S24](LANDMARKS.md)。

- [ ] [BATCH-01 · 杀掉 worker 后槽位与 Godot 子进程未必自动回收](migration_agent/eval/DEFECTS.md)。**范围**：`migration_agent/eval`；**状态**：规划风险；批处理待实现。例：两槽中一个 worker 持槽被 kill -9，后续任务永远少一个槽；残留 Godot 继续占内存。

<a id="s25"></a>

### S25：验收崩溃恢复、观测降级并完成清理

- [ ] **本步全部工作**：父进程监督并回收残留进程/槽位，按 S19 对账重排；标记中断 trace，以新 trace 关联恢复。清理旧占位、README/ARCHITECTURE/NEXT_STEP 与失效链接。 重新调度保留原 run_id/thread_id，调用同一 resume 入口，不重建初始图输入。

**交付与测试门**：交付 kill/断网/后端不可用测试、恢复及评分补传说明；清单对应真实证据。后端持久化/保留策略按选定部署说明，不承诺超出本地账本的可靠性。 无进程/槽位泄漏，任务不丢、受控补丁不重复，未知模型结果单列；导出有界，评分重试不重复；本地与后端差异可解释；真实引擎/后端验收与模拟测试分别报告。

**实现指导**：[S25](LANDMARKS.md)。

本步是新增能力/系统验收，不伪造已有代码 Bug；其失败对照和完成标准已列在实现指导及本步测试门。

## 根目录直接负责的问题详情

<a id="doc-01"></a>

### DOC-01：旧规划把不存在的接口当作可复用能力

**顺序 / 状态**：[S00](LANDMARKS.md)；契约测试已通过（2026-10-18）。

**范围与原因**：影响上层工具、配置和导航。现有 Gate 返回 decision，编辑器接收 Hunk；旧规划混入了另一套 action、字符串替换和配置命名。

**具体表现**：按旧示例读取 gate.action 会失败；RetrievalQuery(query="instance") 缺少 target_version，也没有提供有效查询字段。

**如何复现**：在测试中创建 RetrievalQuery(query="instance", error_code=None)，观察 ValidationError；将旧 workspace_root/godot_bin YAML 传给现有配置加载器，观察缺 project_root。

**修复办法**：按新的根路标及宿主路标绑定真实 API；尚未存在的函数标为新增。所有文档使用仓库相对链接；旧 NEXT_STEP 不再决定本轮执行顺序。

- [x] **验收测试**：`uv run pytest migration_agent/tests/test_s00_preflight.py -q`，20 passed。Python 3.11.15；tree-sitter 0.26.0；tree-sitter-language-pack 1.20.0（根 lock 与 index lock 一致，index 测试 202 passed）。Godot `/usr/local/bin/godot4` 为 `4.7.1.stable.official.a13da4feb`，与规则清单 `4.7.1` 一致。规则清单 sha256 `5edc7e58bb99ab43278a4989796b5430469cfe3b8022475d030bd2f9d77350e7`，rules.db sha256 `1fa4aa84fe8f21683e9574ea25bb1f84467bb9b66574442055c8582ad9d61f06`，语料目录存在。语义约定版本常量 `1.37.0`；offline 的后端状态是 `not_required`，没有连接 Langfuse/Phoenix。改依赖前四组回归：inline_tools 183 passed，index 202 passed，godot_mcp 231 passed，rag 92 passed / 1 skipped（`HF_HUB_OFFLINE=1`）。文档相对链接检查包含在上述 20 项里。

**关键源码**：[models.py](codebase_index/godot_mcp/src/godot_mcp/verify_gate/models.py)、[schemas.py](rag/retriever/schemas.py)、[edit.py](inline_tools/editandfixguard/edit.py)。

## 什么才算关闭

代码问题：附新增反例测试、修复后结果、模块回归结果及适用版本。设计问题：实现对应能力并通过反例；不能因规划文字已经改了就关闭。环境/引擎证据缺失：标待验收，不写“全部通过”。

每个问题只有一个详细维护位置，上面的链接直接进入负责目录；父级 DEFECTS 继续汇总其全部子目录问题。新发现问题先分配唯一 ID，再插到其依赖满足后的最早步骤，根与本级同时更新。
