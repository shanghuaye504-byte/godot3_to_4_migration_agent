# AGENTS.md

本文件管辖本目录及其全部子目录。与更深目录中的 `AGENTS.md` 冲突时，以更深的文件为准。系统、开发者或用户提示优先于本文件。

内容与根目录 `CLAUDE.md` 对齐（Claude Code 读 `CLAUDE.md`；Codex 读 `AGENTS.md`）。

# godot3_to_4_migration_agent — 全局协作规则

## 语言规则(强制)

- 思维链(thinking)、工具调用、内部推理过程一律使用英文，以保证推理准确性。
- 最终呈现给用户的所有输出——聊天回复、生成的 Markdown 文档(README/ARCHITECTURE)、
代码内 docstring 与行内注释——必须是简体中文。
- 代码标识符(变量名/函数名/类名)保持英文规范命名，不做中文化。

## 架构基线

- 总体架构见 `ARCHITECTURE.md`，任何子模块设计不得与其冲突；如有冲突，先在对话中提出。
- 子模块清单与导航：见 `ARCHITECTURE.md` 中的"模块导航"表。

## 目录与文档规范

- 每个目录必须有就地 README.md，禁止把该目录的说明文档集中搬到别处。
- L3 就地设计说明书(函数设计思路 / 功能草案 / schema 草稿 / AI 生成的执行 plan)
一律放在目标目录下的 `DESIGN_NOTES.md`，禁止提交进 Git，禁止与 README 内容混写。
- 架构级、跨模块、有后果的决策记录到 docs/adr/，只增不改，必须提交。
- 修改某目录代码后，必须同步更新该目录 README.md，不允许文档滞后于代码。

## 依赖管理规则

- 包管理只允许两层：项目根一层、子模块根一层，禁止在子模块内部子目录新增 pyproject.toml。
- 子模块的 build/dev/test 类依赖必须声明在 [dependency-groups]，禁止用  
[project.optional-dependencies]，避免下游引用该子模块作为包时被动带上这些依赖。

## 项目文档

各级目录下的/doc中存放的文档更多的是ai自己生成，供agent查阅的中间件，请你在调研代码库的时候不要过多的引入太多docs里面的内容放在上下文中，以免被噪声干扰，仅仅在需要查询的时候检索一下。各级目录下的docs，readme等文档中可能有一些旧的已经被淘汰的feature，请你以代码文件中的具体实现为准。



## 项目特定上下文

我先把关键事实查实，再给你唯一结论。# 结论先给：做「Godot 3→4 存量项目批量迁移收尾 Agent」

一句话定义：

> 输入一个 Godot 3.x 仓库，先跑官方确定性转换器 `--convert-3to4` 吃掉机械部分，然后由 Agent 循环处理**转换器搞不定的残余编译/解析错误**，用 `godot --headless --check-only` 的真实报错作为客观 reward，直到错误清零、判定无进展、或超出成本预算 → 升级人工。全流程做成可横向扩容的批处理服务。

先回答你最尖锐的那个问题，因为如果这一问答不好，整个项目在面试里就是废的。

---



### 一、为什么这件事不该直接丢给 Claude Code

你的质疑完全正确，而且你必须主动在面试里先讲这一段。但 Godot 3→4 迁移恰好是少数几个「自建 Agent 明显优于通用 coding agent」的场景，理由是四条，且都可量化：

**1. 痛点的形态是「一次性 × N 个仓库」，不是「一个仓库 × 人陪着」**

Claude Code 是 human-in-the-loop、单仓库、交互式。而这个痛点的真实形态是：一个工作室有 20~40 个内部 addon/工具/原型仓库卡在 3.x；整个 Godot 生态有大量 3.x addon 至今没人迁。没人会坐在那里陪 Claude Code 干 40 遍。需要的是**提交一批仓库、无人值守跑完、产出「哪些自动过了 / 哪些残留 / 哪些必须人看」的机器可读报告**。这个 harness 就是项目本体。

**2. 80% 的工作量根本不该花 token**

`AnimatedSprite→AnimatedSprite2D`、`OS.get_ticks_msec→Time.get_ticks_msec`、`instance()→instantiate()` 这些是**确定性重命名表**。让前沿模型逐行改这些是纯烧钱。正确架构是三级：


| 层   | 手段                                    | 覆盖            | 成本      |
| --- | ------------------------------------- | ------------- | ------- |
| L0  | 官方 `--convert-3to4` + 你自己的 rename 规则表 | 大头机械改名        | 0       |
| L1  | 小模型 + 版本锁定的 RAG（拿到精确迁移规则）             | 语义型残余错误       | 低       |
| L2  | 大模型 / 人工                              | L1 反复失败、跨文件重构 | 高，但只占少数 |


**这个分级路由本身就是你的工程贡献，而且能用「$ / 仓库」直接量化。** 面试里「我把单仓库成本从 $X 降到 $X/15，同时修复率不降」比任何架构图都好使。

**3. 版本特异性知识：参数记忆打不过锁定版本的检索**

我查到的真实例子：Godot 4.4 把 `@export_file` 的内部存储从 res 路径改成了 uid，这是**没写进升级文档的破坏性变更**（issue #104379 里用户明确抱怨文档还写着 "path to a file"，要求补进 breaking change 页）；4.4 引入 UID 后跨机器 git 协作会大量报 `ext_resource, invalid UID`。这种冷门、版本绑定、文档滞后的知识，通用模型的参数记忆是模糊且过时的，而一个版本锁定的检索库能精确命中。**这可以做 with-RAG / without-RAG 消融实验，用同一个模型，出一个百分点差值** —— 这就是你 RAG 有效性的硬证据，不是"我接了个向量库"。

**4. Claude Code 不产出审计与升级策略**

迁移服务必须回答：哪些 error 残留、哪个补丁被判定为语义不安全、哪个仓库触发熔断、每仓库花了多少钱。这是服务，不是对话。

**最后一招（强烈建议做）**：把 Claude Code 当成你的 baseline 写进评测表。

> Baseline: Claude Code，3 个真实仓库，人工介入 N 次，成本 $X，parse-clean 率 Y%  
> Ours: 全自动，成本 $X/15，parse-clean 率 Y'%，可疑修复由 judge 标出 K 处

这样你就把「为什么不用 Claude Code」从一个坑，变成了你 README 里最亮的一张表。

---



### 二、调研证据（我查到的，不是编的，都可以在面试里引用）

**痛点真实存在且官方承认不完整：**

- 官方文档明确说 `--convert-3to4` 是有限的：默认跳过 >4MB 或 >100k 行的文件；`instance()→instantiate()` 的转换"依赖自定义代码"（即可能失败）；ArrayMesh 的 `.res/.tres` 格式 4.0 与 3.x 不兼容需手工处理。
- issue **#63672**：转换器会 hang、>500kb 文件失败；报告者实测「被标记为已转换的文件」里 shader 没转对（另开 **#63673**）、mesh 转换损坏（**#63550**）。
- 论坛真实案例（2025-05、2025-12）：用户跑完转换器仍然一堆报错，`yield(get_tree(),"idle_frame")` → `await get_tree().process_frame`、Tween API 整体重构这类**语义级**改动必须人工重排代码行 —— 这正是 L1 Agent 的用武之地。

**客观 reward 信号真实可用，且它本身带缺陷（这是宝藏）：**

- 社区 CI 实践中标准校验就是这两条：  
`godot --headless --editor --import --quit --path .`（刷新导入缓存）  
`godot --headless --check-only --quit --path .`（解析全部 GDScript）
- 但这个信号有**已知假阳性**：issue **#78587**（`--check-only` 不加载 autoload，误报 `Class "singleton" hides an autoload singleton`）、issue **#111515**（引用 addon 单例时 `--check-only` 误报 `Identifier not found`，加 `--debug` 还会 signal 11 崩溃）。
- 论坛（2026-01）：想看 warning 必须加 `--debug`，但 **godot 会掉进交互式 debugger 无限挂住，用户只能用** `timeout` **杀掉它**。

最后这条你先记住 —— 它让"超时与进程杀死"从装饰变成了**没有它项目就跑不起来**的刚性需求。

---



### 三、Agent 循环（这是 Agent 不是 workflow）

```
[L0 确定性预处理] --convert-3to4 + 规则表  (无 LLM)
        ↓
[verify] godot --headless --import --quit  →  --check-only --quit
        ↓  结构化 error 列表 (Pydantic)
┌──────────────── ReAct 循环（下一步由模型基于观察决定）────────────────┐
│  triage: 这批 error 里哪个是根因？哪些是级联症状？哪些是已知假阳性？   │
│    ↓ 模型自主选择工具（序列不固定、长度不固定）                       │
│  read_file(path, range) / grep_symbol / read_scene_tree(.tscn)        │
│  retrieve_migration_rule(symbol)  ← RAG                               │
│  apply_patch(unified_diff)                                            │
│    ↓                                                                  │
│  run_verify()  →  对比 error signature 集合的 delta                   │
│    ├ 清零 → 退出                                                      │
│    ├ 变少 → 继续                                                      │
│    ├ 签名集不变 N 次 → 判定无进展，换策略（扩大上下文/升级模型）       │
│    ├ A→B→A 震荡 → 判定死循环，直接 escalate                           │
│    └ 新增 error → 回滚该 patch，记账，重规划                          │
└──────────────────────────────────────────────────────────────────────┘
        ↓
[Agent-as-Judge] 独立 LLM 审 diff：是真修根因，还是"骗过编译器"？
        ↓
report: parse-clean / 残留 error / 可疑修复 / 成本 / 是否需人工

```

**为什么这是 Agent 而不是 workflow**：路径不写死在图里。同一个 `Nonexistent function` 报错，模型可能选择「直接查 rename 表改掉」、「先 grep 全仓库看这个符号被引用了几处再改」、「读 .tscn 确认节点结构后改」、「判定这是级联症状先不管它」。**工具调用序列和长度由观察结果决定**，这是面试官问"和 workflow 区别"时你唯一需要的答案。

---



### 四、逐项对照你要踩的坑（每一个都是刚性需求，不是为用而用）


| 你要练的                 | 在本项目中为什么**必须**有                                                                                                                                                                                                                                                                             |
| -------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **超时 / 进程杀死**        | 已验证：`--check-only --debug` 会掉进交互 debugger 永久挂死；转换器本身有 hang 的 issue；大项目 `--import`要几分钟。必须 subprocess timeout + 进程组 kill + 区分「超时」与「失败」两种语义。                                                                                                                                                   |
| **死循环检测**            | 用 error signature 集合的哈希做指纹。三种真实模式：签名集 N 轮不变（无进展）、A→B→A 震荡（改这个坏那个）、同一文件反复被 patch 但 signature 不动。计数器存 Redis 供跨 worker 共享。                                                                                                                                                                     |
| **熔断**               | 两层。① 仓库级：某仓库 verify 连续 3 次崩溃/超时（项目本身已损坏）→ 开路，停止调度，标 needs-human，避免把 worker 池打满。② 模型级：LLM 429/5xx 达阈值 → 开路。                                                                                                                                                                                  |
| **降级**               | 真正有意义的降级链：大模型不可用 → 小模型；小模型也不行 → **退化成纯规则模式**（只应用 RAG 里确定性的 rename 表，不做语义推理），产出「部分迁移 + 明确残留清单」而不是整单失败。这才是有业务含义的降级，不是"返回兜底话术"。                                                                                                                                                                |
| **并发冲突 + 分布式锁**      | 硬约束：同一 workspace 有 `.godot/` 导入缓存和 UID 缓存（issue #115011 显示这个缓存本身就脆弱到要手删），两个进程并发 verify 同一目录必然互相污染。所以每 workspace 一把 Redis 锁（`SET NX PX` + fencing token + lease 续约，处理"worker 卡住但锁没过期"）。另外每个 Godot 进程吃几百 MB 内存，需要一个 Redis 全局信号量限制并发进程数。                                                       |
| **Redis（真业务用法）**     | ① Streams + Consumer Group 做任务队列（`XADD`/`XREADGROUP`/`XACK`，`XAUTOCLAIM` 回收死掉 worker 的 pending 任务）② workspace 租约锁 ③ 熔断器状态 ④ error-signature 重试计数（跨 worker 共享才有意义）⑤ **LLM 响应缓存，key = hash(error_signature + file_slice)** —— 跨仓库命中率会很高（同一个 API 破坏性变更在几十个仓库里长得一样），这是能报数字的真实降本 ⑥ embedding 缓存。 |
| **RAG（且是个好 RAG 场景）** | 语料：官方 upgrading_to_godot_4 的巨型重命名表（几百条，塞不进 context）+ 各 4.x 版本 changelog + 转换器已知缺陷 issue + 论坛高质量修复贴。**关键设计点：检索 key 是报错里的符号名，所以必须 BM25 + 向量混合 —— dense embedding 对** `OS.get_ticks_msec` **这种精确符号匹配很弱，纯向量会挂。** 这是个能讲清 why 的检索决策。                                                              |
| **Agent-as-Judge**   | 编译器能证明"能过"，不能证明"没改坏"。最常见的偷懒修复：删掉报错那行、注释掉、把函数体换成 `pass`、`yield` 改 `await` 时把逻辑顺序改错。judge 专抓这些 → 你会有**两个正交指标**：parse-clean 率（客观）与语义保真率（judge）。                                                                                                                                                |


---



### 五、数据与评测（这块决定含金量，别省）

**三套数据，作用不同：**

**A. 真实未迁移仓库（真实性）**  
awesome-godot 的 3.x 条目、godot-demo-projects 的 3.x 分支、GitHub 搜 `language:GDScript` 且 `project.godot` 的 `config_version` 是 3.x 那一档（Godot 4 是 5）且最后 commit 早于 2023 的仓库。取 8~12 个中小仓库。这些**没有 ground truth**，只能用 error 数下降 + judge 打分评。

**B. 反向变异集（无限量 + 完美 ground truth）← 这是你评测的杀手锏**  
拿一个**已经是 4.x 的**健康仓库，机械地反向应用重命名表，把它"退化"成 Godot 3 风味（`instantiate()→instance()`、`Time.get_ticks_msec→OS.get_ticks_msec`、`await x.finished→yield(x,"finished")`…）。于是：

- 原始文件就是**逐字精确的 ground truth**，可以算 exact-match 修复精度
- 可以批量生成上百条样本 → **这就是你的压测集**
- 可以按错误类型分层统计"哪类 API 破坏 Agent 最容易翻车"
- 顺带给了 RAG 一个**真正的检索 ground truth**：你知道每条错误对应哪条迁移规则 → 能算 Recall@5，能做 BM25 vs vector vs hybrid 的消融

**C. Issue 复现集（难例）**  
从我上面那些 issue / 论坛帖里抽真实报错和最小复现，作为 hard case。数量少但故事性极强（"这条 case 来自 godot issue [#63673，官方转换器至今不处理](#63673，官方转换器至今不处理) shader"）。

**要报的指标：**

修复侧：parse-clean 率、error 削减率、逐错修复精度（B 集 exact/semantic match）、假修复率（judge）、judge 与人工标注的一致性（手标 50 条 diff 验一下你的 judge，这个严谨度大多数候选人没有）  
检索侧：Recall@5、混合检索相对单路的提升  
工程侧：p50/p95 单仓库耗时、超时率、平均迭代轮数、死循环触发率、熔断触发次数、1/2/4 worker 的吞吐曲线与锁竞争、LLM 缓存命中率、$/仓库、L0 确定性预处理省下的 token 占比

---



### 六、可预期的 badcase（面试弹药，且我已经给你找到了出处）

这几条你几乎必然会遇到，提前知道能让你 Day 6 直接产出高质量归因：

1. **reward 信号自带假阳性**（issue #78587 / [#111515）：](#111515）：)`--check-only` 不加载 autoload 和 addon 单例，会误报 `Identifier not found`。Agent 会去"修"一个根本不存在的 bug，甚至把正确代码改坏。→ 解法：error triage 节点 + 已知假阳性签名过滤 + 交叉验证（`godot --quit` 能正常启动说明该符号其实存在）。**"我的客观 reward 本身是有噪声的，我怎么去噪" 这个话题的深度，远超普通候选人。**
2. **级联错误淹没根因**：一个脚本坏了会在十几个文件里刷 `Failed to compile depended scripts`（我抓到的真实日志就是这样）。Agent 会去追症状。→ 解法：按依赖图给 error 排序，只攻根节点，症状 error 不计入重试计数（否则误触发熔断）。
3. `yield`**→**`await` **的震荡**：正则级替换能过解析，但 Tween/协程需要重排语句顺序（论坛真实案例就是要"把 6-11 行挪到 15-16 行之间"）。编译过了，逻辑坏了 → 这是 judge 的经典战功。
4. **shader 没有解析期信号**（issue [#63673）：](#63673）：)`.gdshader` 的问题 `--check-only` 抓不到 → 属于"客观信号覆盖不到的错误类别"，必须走独立通道或直接 escalate。这是个很好的"我知道我的验证边界在哪"的表态。
5. **warning 不是 error**：`ext_resource, invalid UID` 是 warning，一旦被误当修复目标，Agent 会永远修不完 → 终止条件必须严格定义在 error 上。

---



### 七、7 天闭环计划

**Day 1 — 验证 harness（最重要，先把 reward 做对）**  
Docker 装 Godot 4.x headless（锁死版本）。实现 `verify(workspace) -> VerifyReport`：跑 import + check-only，subprocess timeout + 进程组 kill，stderr 解析成结构化 `GodotError(kind, file, line, symbol, message, signature)`。同时写完反向变异生成器。  
✅ 交付：5 个仓库能稳定拿到结构化 error 列表；50 条带 ground truth 的变异样本。

**Day 2 — RAG**  
抓官方升级文档（重命名表**按符号切成结构化行**，不要傻切 chunk）、4.x changelog、精选 issue/论坛。BM25 + dense 混合 + rerank。用变异集的已知映射做检索评测。  
✅ 交付：Recall@5 数字 + 三种检索方案对比表。

**Day 3 — LangGraph 单机闭环**  
Pydantic schema：`GodotError` / `FixProposal(diff, rationale, cited_rule)` / `VerifyReport` / `JudgeVerdict`。工具：`read_file` `grep_symbol``read_scene_tree` `retrieve_migration_rule` `apply_patch` `run_verify` `escalate`。ReAct 循环 + max_steps。  
✅ 交付：单仓库能从 N 个 error 跑到 0 或 escalate。

**Day 4 — 鲁棒性**  
无进展检测、震荡检测、patch 失败回滚、LLM 重试退避、单仓库 token/成本预算上限、三级降级链。  
✅ 交付：故意喂一个修不好的 case，能干净地判死循环并升级，不会烧光预算。

**Day 5 — 拆微服务 + Redis**  
FastAPI gateway（提交 job / 查状态）→ Redis Streams + Consumer Group → N 个 fix-worker → verify sandbox（限内存/CPU）。workspace 租约锁 + fencing、全局 Godot 进程信号量、熔断状态、跨 worker signature 计数、LLM/embedding 缓存、幂等键。  
✅ 关键 demo：**起 3 个 worker，跑到一半** `kill -9` **掉一个**，展示 `XAUTOCLAIM` 回收 pending 任务 + 锁 lease 过期后被安全接管、任务不丢不重复执行副作用。这个演示在面试里含金量极高。

**Day 6 — 评测 + judge + baseline**  
跑全量。judge 上 rubric，手标 50 条验一致性。**在 3 个仓库上跑 Claude Code 做 baseline，记录成本和人工介入次数。** 出 badcase 分类表。  
✅ 交付：完整指标表 + 对比 baseline 表 + badcase 归因。

**Day 7 — 两三个针对性优化 + 交付物**  
从 badcase 里挑最贵的 2~3 个（大概率是"假阳性误修"和"级联错误追症状"）做优化，记录前后数字。README、架构图、录屏、简历条目。

---

