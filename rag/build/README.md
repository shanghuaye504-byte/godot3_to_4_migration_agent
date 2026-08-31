# A 层编译：数据库 Schema 设计说明

关于IR设计流程：

[https://chatgpt.com/share/6a8e83f1-54f8-83e8-af3b-0d18cd25b025](https://chatgpt.com/share/6a8e83f1-54f8-83e8-af3b-0d18cd25b025)

这份文档是 A 层知识库的**协议说明书**。它写给以后要改 parser、写扫描器、或解释「为什么不让 Agent 去发现数值陷阱」的人看。运行时的包结构见上一级 [rag/README.md](../README.md)；每个 adapter 具体用什么库/正则解析,看 [build/PARSING.md](PARSING.md)——这份文档只锁字段协议,不重复"怎么解析"的细节。

读完应能回答四件事：

1. `artifacts/rules.db` 里一张表的每一列是什么、谁来填、谁来读。
2. 官方三种完全不像的原材料（cpp 数组、两份 API 快照、逐版本 rst）如何变成同一行。
3. 人工 YAML 如何叠加上去——以及为什么大多数「陷阱」**根本不会被 Agent 检索到**。
4. 七份 4.x 升级文档如何在 build 期拍平，检索时按目标版本一次滤出，而不是让 Agent 连跳七次。

本轮只锁定协议。Parser 还没写；adapter 的输入输出形状以本文为准。

---

## 1. 先分清：不是所有「规则」都该进 Agent 循环

迁移流水线里其实有三种完全不同的工作，之前容易被揉成「都写进字典让 Agent 查」：

```text
L0  官方转换器（确定性改名）
  → L0.5 用本库改名表对全仓库再跑一遍幂等替换（补被跳过的大文件）
  → 确定性陷阱扫描器（无报错信号的坑，直接写报告）（这个很重要，因为数据库中有些规则是agent检索不到的，是给这一阶段用的规则）
  → verify（产出报错列表）
  → 已知假阳性过滤器（autoload / addon 单例）
  → ReAct 循环（只处理：有报错信号、且规则库覆盖得到的问题）
```

ReAct 循环的燃料是**错误信号**。凡是「改完不报错、但运行结果已经错了」的情况，循环里没有观测，提示词再好也只是让模型凭空找茬。正确做法是把这类检查从循环里拿出来，做成零 token 的确定性脚本。

因此 YAML 里的 `detection_method` 不是装饰字段，而是**这一行编译进数据库之后，哪个子系统允许看见它**。


| `detection_method`            | 谁读                            | 进不进 `retrieve_migration_rule` |
| ----------------------------- | ----------------------------- | ----------------------------- |
| `agent_retrieval`             | Agent 检索                      | 是                             |
| `agent_retrieval_or_escalate` | Agent 检索；若 A/B 都无命中则禁止瞎改，直接人工 | 是                             |
| `static_scan_post_l0`         | L0 后静态扫描器                     | **否**                         |
| `verify_error_filter`         | verify 出口过滤器                  | **否**                         |
| `not_actively_handled`        | 谁都不读                          | **不入库**                       |
| `preflight_probe_recommended` | 谁都不读                          | **不入库**                       |


官方三源默认全部是 `agent_retrieval`。YAML 按条目自己声明。声明为后两种的条目只留在 vault 里当档案（面试和后续评估能引用 `id`），不写进 SQLite，避免扫描器和检索器读到「故意不处理」的行产生误动作。

`upgrading_to_godot_4.rst`（3.x → 4.0 总指南）**整篇**也不入库。它是给 Agent 的常驻 context：篇幅可控、几乎每条 3→4 语义问题都会提到。Build 只把它拷到 `artifacts/agent_context/upgrading_to_godot_4.rst`。真正按行拆进数据库的，是旁边那七份**增量**文档 `upgrading_to_godot_4.1.rst` … `4.7.rst`，外加这篇总指南里**唯一被单独抽出来的例外**——`Updating shaders` 小节，见 6.4。

**shader 不是 C++/C#，不能套同一条排除规则。** cpp 的 `shaders_renames` 数组、rst 的 Rendering 小节、以及 6.4 里抽出来的 shader 散文，只要能提取出「旧写法 → 新写法/新行为」，就和其他 `symbol_kind` 一样正常走 `agent_retrieval`——它不因为「和 shader 有关」就被降级成 context-only 或者被丢弃。真正被排除的只有 Godot 引擎自己的 C++实现源码（++`project_converter_3_to_4.cpp` ++之类)和 cpp 表里的 C# 数组，理由完全不同：C# 数组是同一份数据的另一种命名法，重复入库只会产生双份命中；引擎 C++ 源码是实现细节，不是迁移规则，shader 报错要的是「语言规范变了」而不是「渲染器怎么实现这个变量」。这两条排除和「shader 数据本身要不要入库」是两件独立的事，不要混着说。

---



## 2. 目录：原材料、中间行、成品

```text
rag/
├── vault/                          # 只读原材料
│   ├── tier_a_official/            # cpp / extension_api / 4.x rst / 3→4 rst
│   ├── tier_a_manual/              # YAML（陷阱 + 语义重构 + 工程说明）
│   └── tier_b_prose/               # 散文原材料：人工维护的原文 + build 解析 4.x rst 时
│                                   #   自动抽出的非结构化段落（*.prose.jsonl，按标题预分段）
│                                   #   下一阶段 chunk_prose.py / embed_prose.py / build_tier_b.py 只读这里
├── build/                          # 工厂：脚本 + 中间产物
│   ├── README.md                   # 本文件（协议）
│   ├── parse_renames_cpp.py
│   ├── diff_extension_api.py
│   ├── parse_upgrading_docs.py     # 只解析 4.1–4.7（+ upgrading_to_godot_4.rst 的 Updating shaders 例外）
│   │                               #   结构化行 → intermediate/rst_4x.jsonl；非结构化段落 → vault/tier_b_prose/
│   ├── build_tier_a.py             # 读 intermediate，写 artifacts/rules.db
│   └── intermediate/               # 编译中间行（jsonl），不进生产镜像，只服务本阶段的 rules.db
│       ├── renames.jsonl
│       ├── api_diff.jsonl
│       ├── rst_4x.jsonl
│       └── manual.jsonl
└── artifacts/                      # 唯一出厂成品
    ├── rules.db                    # 本协议的 SQLite
    ├── agent_context/
    │   └── upgrading_to_godot_4.rst
    ├── corpus.lance/               # B 层（另一份协议）
    └── manifest.lock.json          # 出厂回执（vault 逐文件 sha256）。和 vault/manifest.json、
                                    #   检索 cache_key 的关系见 docs/hash_and_manifest.md
```

约定：

- Adapter **禁止**直接写 `rules.db`。凡是能落成 `MigrationRule` 行的，只往 `build/intermediate/` 追加 JSONL，一行一个下面定义的对象。
- `parse_upgrading_docs.py` 是唯一一个有两个出口的 adapter：能落成 `MigrationRule` 行的写 `intermediate/rst_4x.jsonl`；抽不出符号对、只是散文说明的，写 `vault/tier_b_prose/`（按来源文件落一个 `*.prose.jsonl`）。这不是写 `rules.db`，是把这批原材料从"藏在 rst 里"搬到"vault 里现成待编译"，供**下一阶段** B 层编译读取，本阶段不生成 embedding、不碰 `corpus.lance`。
- `build_tier_a.py` 是唯一写库的程序：读全部 jsonl + 再读一遍 YAML（YAML 已是接近最终行，仍先落一份 `manual.jsonl` 方便 diff 构建结果），合并后写入 `artifacts/rules.db`。
- Worker 镜像只带 `artifacts/` 和 `retriever/`，不带 `vault/`、不带 `build/`、不带 `intermediate/`。

---



## 3. 为什么是一张表，而不是按源拆表

三种官方原材料形状差很远：

- cpp 是 `{old, new}` 对；
- `extension_api.json` 是两份全量快照，要做集合差；
- rst 是「粗体类名 + 动词短语 + 兼容性勾选」的半结构化表，外加散文。

YAML 又引入第四种形状：`trigger` 可能是符号、文件 glob、报错正则、或「去 project.godot 里对字段」。

尽管如此，**检索、扫描、过滤都需要同一套身份字段**（id、版本、来源、警告文本）。拆成 `renames` / `api_deltas` / `traps` 三张表，Agent 工具和扫描器都要 union，评测集也要 union。代价是协议分叉，收益只是列更瘦一点。

所以采用：**一张** `migration_rules`**，缺的列为空，源特定细节进** `payload` **JSON，扫描器/过滤器特定的匹配条件进** `trigger` **JSON。** 用 `detection_method` 决定谁有权 SELECT 到这一行。这和「一种中间行、一个后端」一致，同时满足「陷阱不要进 Agent 循环」。

放弃上一版的 YAML `overlay` / `insert`。原因：数值陷阱并不是「在 extents→size 那条改名上打个标」——L0 之后场景里往往已经没有 `extents` 这个词了，扫描必须找的是类型 `RectangleShape2D` 还在不在。这是一条独立检查，不是对改名行的 UPDATE。假阳性过滤、shader 升级策略同理。YAML 每一条都是 **insert 一行**，靠 `detection_method` 告诉系统把它交给哪条通路。

---



## 4. 列设计



### 4.1 身份与查表键


| 列              | 类型             | 含义                                                                                                                                                            |
| -------------- | -------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `id`           | TEXT PK        | 稳定可引用。官方行用 `source:since:owner:symbol_kind:old_or_new`；YAML 用文件里的 `TRAP-001` / `REWRITE-001`                                                                  |
| `old_symbol`   | TEXT NULL      | 旧名字。`change=add` 时为空                                                                                                                                          |
| `new_symbol`   | TEXT NULL      | 新名字。`change=remove` 时为空                                                                                                                                       |
| `owner`        | TEXT NULL      | 所属类 / 单例。cpp 全局正则改名经常为空，这是正常的                                                                                                                                 |
| `symbol_kind`  | TEXT           | 这是**什么符号**：`class` `method` `property` `signal` `enum` `constant` `builtin` `shader` `theme` `color` `project_setting` `singleton` `utility` `rewrite` `trap` |
| `change`       | TEXT           | **发生了什么**：`rename` `remove` `add` `signature` `type` `move` `split` `replace` `default` `behavior` `rewrite` `trap` `false_positive`                          |
| `rule_kind`    | TEXT NULL      | YAML 细类，如 `semantic_risk_numeric`、`coroutine_rewrite`。官方行留空                                                                                                   |
| `match_tokens` | TEXT JSON      | 额外检索词数组。rst 反引号抽到的符号、报错子串都放这里                                                                                                                                 |
| `trigger`      | TEXT JSON NULL | 扫描器/过滤器的匹配配置，结构随 `detection_method` 变化。官方改名行为空                                                                                                                |


`symbol_kind` 和 `change` 必须拆开。否则会出现「一个枚举里既有 method 又有 remove」这种没法建索引的设计。`rule_kind` 是第三人称：只服务于 YAML 里已经存在的细分类，避免为了 `coroutine_rewrite` 去膨胀 `symbol_kind`。

### 4.2 版本


| 列                    | 类型           | 含义                                                                       |
| -------------------- | ------------ | ------------------------------------------------------------------------ |
| `since_version`      | TEXT NULL    | `"4.0"` … `"4.7"`。YAML 里「与小版本无关」的陷阱可以是 NULL，表示对任何 4.x 目标都适用              |
| `since_version_code` | INTEGER      | `major*10000 + minor*100 + patch`。`4.0` → 40000，`4.7.1` → 40701，NULL → 0 |
| `until_version`      | TEXT NULL    | 几乎总为空。API 变更是累积的，不需要失效点                                                  |
| `until_version_code` | INTEGER NULL | 同上                                                                       |


**禁止**用字符串比版本（`"4.10" < "4.9"` 会错）。SQL 侧只比较 `*_code`。Python 侧的换算函数放在 `rag/version_codec.py`（包根目录，只有一个纯函数 `version_to_code(v: str | None) -> int`，零依赖）——不要放进 `build/` 或 `retriever/` 各自的 `schemas.py`。原因是 worker 镜像不带 `build/`，但 `build_tier_a.py` 写 `since_version_code` 用的算法必须和 `retriever` 换算 `target_version_code` 用的算法逐字节一致，否则 `since_version_code <= target_version_code` 这条最关键的过滤会在两端悄悄跑出不同结果。放在包根目录，两侧各自 `from rag.version_codec import version_to_code`，只有一份实现。检索侧的完整契约见 [rag/retriever/docs/](../retriever/docs/README.md) 与 [ARCHITECTURE.md](../retriever/ARCHITECTURE.md)。

JSON 差集只有 4.0 和目标两份快照，**不知道中间哪一版改的**，所以 `since_version=4.0` 只表示「相对 4.0 已经成立」。精确生效点由 rst 行提供（`4.1`…`4.7`）。两行并存是故意的，见第 7 节。

### 4.3 分流与标记


| 列                  | 类型          | 含义                                                                                       |
| ------------------ | ----------- | ---------------------------------------------------------------------------------------- |
| `detection_method` | TEXT        | 见第 1 节。官方默认 `agent_retrieval`                                                            |
| `semantic_risk`    | INTEGER 0/1 | 改名/修复表面上对，语义或数值可能错                                                                       |
| `converter_gap`    | INTEGER 0/1 | 官方转换器故意没做或做不到                                                                            |
| `verifier_blind`   | INTEGER 0/1 | verify / `--check-only` 看不见                                                              |
| `agent_action`     | TEXT NULL   | 仅 Agent 可见行有意义：`apply_rename` `apply_and_warn` `do_not_fix` `escalate_human` `note_only` |
| `system_action`    | TEXT NULL   | 给扫描器/过滤器/维护者看的「命中后系统做什么」，来自 YAML 的 `action`                                              |
| `warning`          | TEXT NULL   | 给 Agent 或报告阅读者的短警告                                                                       |
| `snippet`          | TEXT NULL   | 短上下文，通常是 rst 表格原句或签名前后对比                                                                 |


扫描器读 `system_action` + `trigger` + `warning`，不读 `agent_action`。Agent 读 `agent_action` + `warning` + `snippet`，不读 `trigger`。

### 4.4 溯源与载荷


| 列            | 类型        | 含义                                                                                                                                    |
| ------------ | --------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| `source`     | TEXT      | `official_renames` `official_renames_skipped` `api_diff` `official_prose` `official_prose_3to4_shader` `manual_trap` `manual_rewrite` |
| `source_url` | TEXT NULL | 官方文件、GH issue、文档页                                                                                                                     |
| `confidence` | TEXT NULL | `verified` / `needs_review`。官方行可空（视为 verified）                                                                                        |
| `payload`    | TEXT JSON | 源特定 extras，**不参与 WHERE**                                                                                                              |


`payload` 约定键（没有就省略）：

- cpp：`cpp_array`、`cpp_comment`
- api_diff：`old_signature`、`new_signature`、`old_return`、`new_return`、`has_compat_wrapper`
- rst：`gdscript_compatible`、`csharp_binary_compatible`、`csharp_source_compatible`、`github`、`section`
- 默认值变化：`old_default`、`new_default`

`source=official_prose_3to4_shader` 是 3→4 总指南里**唯一**允许占行的部分（见 6.4）；除此之外这篇文件不再占行，改为常驻 context。

---



## 5. DDL

```sql
CREATE TABLE migration_rules (
  id                   TEXT PRIMARY KEY,
  old_symbol           TEXT,
  new_symbol           TEXT,
  owner                TEXT,
  symbol_kind          TEXT NOT NULL,
  change               TEXT NOT NULL,
  rule_kind            TEXT,
  match_tokens         TEXT NOT NULL DEFAULT '[]',
  trigger              TEXT,
  since_version        TEXT,
  since_version_code   INTEGER NOT NULL DEFAULT 0,
  until_version        TEXT,
  until_version_code   INTEGER,
  detection_method     TEXT NOT NULL DEFAULT 'agent_retrieval',
  semantic_risk        INTEGER NOT NULL DEFAULT 0,
  converter_gap        INTEGER NOT NULL DEFAULT 0,
  verifier_blind       INTEGER NOT NULL DEFAULT 0,
  agent_action         TEXT,
  system_action        TEXT,
  warning              TEXT,
  snippet              TEXT,
  source               TEXT NOT NULL,
  source_url           TEXT,
  confidence           TEXT,
  payload              TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX idx_mr_old         ON migration_rules(old_symbol);
CREATE INDEX idx_mr_new         ON migration_rules(new_symbol);
CREATE INDEX idx_mr_owner       ON migration_rules(owner);
CREATE INDEX idx_mr_detect      ON migration_rules(detection_method);
CREATE INDEX idx_mr_since_code  ON migration_rules(since_version_code);
CREATE INDEX idx_mr_old_since   ON migration_rules(old_symbol, since_version_code);

CREATE TABLE meta (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
```

`meta` 至少写入：`schema_version`、`godot_version`、`docs_checkout`、`api_from`、`api_to`、`built_at`。前三项版本必须和 Day 1 锁定的目标一致，评测才能复现。`schema_version` 是本文件的协议版本号（当前 `"2"`），retriever 连接数据库时**第一件事**就是断言这个值等于代码里写死的期望值，不一致就在启动时直接抛错，不要等到某一行 `MigrationRule.model_validate` 失败才发现——那时已经晚了，而且大概率不止一行出错。详见 [rag/retriever/docs/router-runtime.md](../retriever/docs/router-runtime.md) 与 [tier-a.md](../retriever/docs/tier-a.md)。

非结构化散文不进这张库，写入 `vault/tier_b_prose/`，作为**下一阶段** LanceDB（B 层）编译的原材料。SQLite 只放能精确查的行。

---



## 6. 三种官方异构源如何填这张表



### 6.1 `renames_map_3_to_4.cpp`：已经是表

每个启用的 `{ "old", "new" }` 一行。数组名映射到 `symbol_kind`：


| 数组                                                                     | `symbol_kind`     |
| ---------------------------------------------------------------------- | ----------------- |
| `class_renames`                                                        | `class`           |
| `gdscript_function_renames`                                            | `method`          |
| `gdscript_properties_renames`                                          | `property`        |
| `gdscript_signals_renames`                                             | `signal`          |
| `enum_renames`                                                         | `enum`            |
| `project_settings_renames` `project_godot_renames` `input_map_renames` | `project_setting` |
| `builtin_types_renames`                                                | `builtin`         |
| `shaders_renames`                                                      | `shader`          |
| `color_renames`                                                        | `color`           |
| `theme_override_renames`                                               | `theme`           |


固定填：`change=rename`，`since_version=4.0`，`detection_method=agent_retrieval`，`agent_action=apply_rename`，`source=official_renames`。`shaders_renames` 这 14 对（`hint_albedo→source_color`、`WORLD_MATRIX→MODEL_MATRIX` 等内置变量/uniform hint 改名）和其余 12 个数组走一模一样的路径，`symbol_kind=shader`，**不做任何特殊降级**——它们是 shader 迁移知识里已经结构化好的那一半，另一半（散文里才有的部分）见 6.4。

行尾 `// ClassA -- Breaks X` 写入 `payload.cpp_comment`。不要假装这是可靠的 `owner`：官方转换器本身就是全局正则，`owner` 允许为空。

**注释掉的条目也要入库**，但 `source=official_renames_skipped`，`converter_gap=1`，`agent_action=apply_and_warn`。它们是转换器不敢自动改的名单（`extents`、`instance` 等），对 Agent 有参考价值。它们**不进入 L0.5 全仓库替换**——被注释掉就是因为全局替换会误伤。

C# 三组数组不入库：本系统面向 GDScript，再灌一份 PascalCase 只会让查表出现双份命中。

L0.5 使用的子集：

```sql
SELECT old_symbol, new_symbol
FROM migration_rules
WHERE source = 'official_renames'
  AND change = 'rename'
  AND converter_gap = 0;
```

对全仓库做正则替换。已被官方转换器处理过的文件里旧符号已不存在，替换是 no-op。被跳过的大文件只有这一步能拿到 L0 级改名。不需要「是否为大文件」分支。

### 6.2 `extension_api_4.0.json` vs `extension_api_target.json`：快照差集

两份文件是状态快照，不是变更日志。只做 **4.0 对目标版本** 一次差集，不逐小版本两两 diff。

有用的顶层键：`classes`（methods / properties / signals / enums / constants）、`builtin_classes`（methods / members）、`global_enums`、`utility_functions`、`singletons`。

跳过：`builtin_class_sizes`、`builtin_class_member_offsets`、`native_structures`（ABI / C++，修 `.gd` 用不上）。

差集粒度是符号，不是整份 JSON：


| 集合关系                   | `change`             | `old_symbol` | `new_symbol` |
| ---------------------- | -------------------- | ------------ | ------------ |
| 只在 4.0                 | `remove`             | 有            | 空            |
| 只在目标                   | `add`                | 空            | 有            |
| 两边都有、名字相同，参数或返回或属性类型不同 | `signature` 或 `type` | 相同           | 相同           |
| 两边都有且签名一致              | 不出行                  |              |              |


不要把「删了 A + 新增 B」猜成一对 rename。真改名由 rst 用人话写（`renamed to` / `replaced with`）。JSON 只给结论：「这个符号没了 / 多了 / 签名变了」。允许和 rst 各有一行，`source` 分别为 `api_diff` 与 `official_prose`。

`hash` 变了但参数列表和返回类型没变：视为没变，不出行。目标版本里的 `hash_compatibility` 只写入 `payload.has_compat_wrapper`。

`since_version` 一律 `4.0`。检索报错走 `old_symbol`，`change=add` 的行不会被「Identifier not found」命中，不会淹没主路径。新增行只在查询打到新名字时出现，用来回答「4.7 多了什么」。

`detection_method=agent_retrieval`。`agent_action`：删除且没有 rst 替代说明 → `note_only`；仅新增可选参数 → `note_only`；必选参数或类型不兼容 → `apply_and_warn`。

### 6.3 `upgrading_to_godot_4.{1-7}.rst`：增量记录，build 期拍平

这七份不是快照，是相邻版本的 commit log。**不能**在运行时让 Agent 读七遍再自己拼。也不能拿 4.7 那一篇去「diff 出 4.0→4.7」，因为它根本不包含 4.1–4.6 写过的内容。

Build 时做的唯一合并是：解析每一份，把该份里的每条变更标上 `since_version = 文件名所记录的终点版本`，全部 insert 进同一张表。


| 文件                           | `since_version` |
| ---------------------------- | --------------- |
| `upgrading_to_godot_4.1.rst` | 4.1             |
| `upgrading_to_godot_4.2.rst` | 4.2             |
| …                            | …               |
| `upgrading_to_godot_4.7.rst` | 4.7             |


不写死「读 7 个文件」，而是 `4.0 < v <= target_version`。今天目标是 4.7.1，所以 4.1–4.7 全读；若目标改成 4.4，4.5–4.7 三份不读。

同一符号在链上被改多次：全部保留，不覆盖。检索 `since_version_code <= target_code`，再按 `since_version_code DESC` 排序，离目标最近的排前面。旧记录留给「还停在 4.3 习惯写法」的项目。

每份 rst 内部三种形状：

1. **Breaking changes 表** → A 层一行。粗体行是 `owner`；下一行动词决定 `change`（`removed` / `renamed to` / `replaced with` / `adds parameter` / `changes type` / `moved to base class` / `split into`）。兼容性三列 + `GH-xxxxx` 进 `payload`。整句进 `snippet`。反引号符号进 `match_tokens`。GDScript 列若为不兼容，`agent_action=apply_and_warn`，否则 `note_only`。
2. **Changed defaults 表** → `change=default`，`semantic_risk=1`，`payload.old_default` / `new_default`。编译能过、运行默认值变了，和数值陷阱同一类性质，但无法为每一条都写扫描脚本，所以仍进 Agent 可检索集合：只有查询里出现该符号时才返回。
3. **Behavior changes** → 能抽出类名/方法的，进 A 层（`change=behavior`，`semantic_risk=1`，`verifier_blind=1`），段落同时进 B 层。抽不出符号的整段只进 B 层。

`source=official_prose`。跟随表格的说明句复制进 `warning`；独立散文（抽不出符号、整段只能当说明看的部分）写入 `vault/tier_b_prose/`，按标题预分段（`heading_path` / `text` / `since_version` / `source_file`），作为**下一阶段** B 层编译（`chunk_prose.py` + `embed_prose.py` + `build_tier_b.py`）要读的原材料——本阶段的 parser 只负责把它从 rst 里搬出来落盘，不在这一步切分成 embedding 用的定长块，也不生成向量。

### 6.4 `upgrading_to_godot_4.rst` 的例外：`Updating shaders` 小节要单独抽出来入库

第 1 节说这篇 3→4 总指南整篇只进 `agent_context`，**唯一的例外是它的** `Updating shaders` **小节**。原因很直接：`godot --headless --import` 会把 shader 编译错误正常报出来（不是静默失败，这一点在 TRAP-003 已经用探针验证过），也就是说 shader 报错和 GDScript 报错一样能进 ReAct 循环、能被检索工具服务——那么这一小节里能提取出「旧写法 → 新写法/新行为」的条目，就应该像其他官方源一样正常入库，而不是因为「凡是 3→4 总指南就整篇当 context」这条粗规则被连带牺牲掉。

这一小节内容分两类：

1. **cpp 表已经覆盖的，不要重复抽取。** 例如 `hint_albedo is now source_color` 已经是 `shaders_renames` 数组里的一行（见 6.1），rst 里这句话只是同一件事的文字说明，抽了也是重复行，跳过。
2. **cpp 表没有的，单独建行**，`source=official_prose_3to4_shader`（这是唯一一个从 3→4 总指南里抽出来的 `source` 取值，专门标注「这行的出处是被例外处理的那一小段，不代表整篇文件都入库了」）：

  | 原文                                                      | `change`   | 说明                                                                                                                                     |
  | ------------------------------------------------------- | ---------- | -------------------------------------------------------------------------------------------------------------------------------------- |
  | 粒子 shader 的 `vertex()` 处理函数被 `start()` 和 `process()` 取代 | `rewrite`  | 不是一对一改名——原来一个函数里的逻辑要按「初始化 / 每帧」拆成两个新函数，`old_symbol="vertex"`，`match_tokens=["vertex","start","process"]`，`agent_action=apply_and_warn` |
  | Forward+/Mobile 渲染器下 NDC 的 Z 范围从 `[-1,1]` 变成 `[0,1]`    | `behavior` | 编译能过、手写 NDC 重建的 shader 会算错，`semantic_risk=1`，`verifier_blind=1`，`match_tokens=["SCREEN_UV"]`                                           |
  | 自定义 `light()` 函数的光照模型变了                                 | `behavior` | 抽不出新旧符号对，只给 `match_tokens=["light("]` 当检索挂钩，`semantic_risk=1`                                                                          |
  | 4.3 起启用 Reverse-Z，可能破坏高级 shader                         | `behavior` | `since_version=4.3`，`semantic_risk=1`，`verifier_blind=1`                                                                               |

   这四行全部 `detection_method=agent_retrieval`：它们不是「无报错信号」的陷阱（不满足 `static_scan_post_l0` 的前提），而是「有报错信号，但即使不报错也可能视觉结果错了」，所以走检索、附警告，而不是走独立扫描器。如果后续发现某一条能写出可靠的静态扫描规则（比如「grep 出手写 NDC 重建但没有按新范围换算的 shader」），可以再补一条新的 `known_traps` 条目，不需要动这张表的协议。

**上表四行是「入库」在本文里唯一的含义：写进** `rules.db` **的结构化行**，不是向量库。这一小节剩下的文字——四行各自的上下文、小节开头的背景说明——人工分类之后如果判定确实抽不出符号对但仍有检索价值，处理口径和 6.3 完全一样：写入 `vault/tier_b_prose/`，作为**下一阶段** B 层编译要读的原材料，不是本阶段直接写进 `corpus.lance`。

不要为了图省事而把整篇 `Updating shaders` 文本原样切段扔进 `vault/tier_b_prose/` 再算了——那等于把「决定哪些内容值得结构化」这件事又还给了向量检索的运气。抽取仍然是人工过一遍这一小节、按上表分类：能落成行的走 `rules.db`，剩下确实没法落成行但有价值的散文才落进 `vault/tier_b_prose/`，和 6.3 的三种 rst 形状用的是同一套判断标准，只是应用在一小段例外文本上。这条规则不是 6.4 专属：6.3 里七份增量 rst 抽不出符号的整段散文，同样落进 `vault/tier_b_prose/`，本来就是同一个 parser 的两个出口。

---



## 7. 多版本检索怎么用这张表

Agent 工具入参带 `target_version`（今天是 `4.7.1` → code 40701）。

```sql
SELECT *
FROM migration_rules
WHERE detection_method IN ('agent_retrieval', 'agent_retrieval_or_escalate')
  AND since_version_code <= :target_code
  AND (
        old_symbol = :sym
     OR new_symbol = :sym
     OR owner = :sym
     OR match_tokens LIKE '%' || :sym || '%'   -- 实现时改为 JSON 函数或额外 token 表
  )
ORDER BY since_version_code DESC, source ASC;
```

效果：

- 目标 4.7 时，`since` 为 4.1–4.7 的 rst 行 + `since` 为 4.0 的 cpp/json/rewrite 行全部候选。
- 目标若改成 4.4，4.5–4.7 的 rst 行自动消失，无需改代码。
- 同一方法在 4.2 改名、4.5 再改：两行都在，4.5 那行排前面。
- `api_diff` 的「删除」和 rst 的「请改用 X」会一起命中：一个给精确结论，一个给替代写法。不去重。

`static_scan_post_l0` 和 `verify_error_filter` 两行 **不出现在上述 SELECT 里**。扫描器另开查询：

```sql
SELECT * FROM migration_rules
WHERE detection_method = 'static_scan_post_l0'
  AND since_version_code <= :target_code;
```

过滤器同理，用 `verify_error_filter`。这样 Agent 工具即使被滥用，也查不到「请去扫 RectangleShape2D」这类指令——那不是给它的。

---



## 8. YAML 如何叠加（与现有文件兼容）

权威文件：[rag/vault/tier_a_manual/semantic_rewrites.yaml](../vault/tier_a_manual/semantic_rewrites.yaml)（一个文件里同时有 `known_traps`、`semantic_rewrites`、`build_pipeline_notes`）。

数据字段只用英文；中文只允许出现在 `#` 注释里。`build_pipeline_notes` 是给维护者看的，**不编译进库**。

不再使用 `op: overlay`。每一条 YAML 对应 insert 一行（或明确不入库）。

### 8.1 `known_traps` → 行或故意不入库


| id       | YAML `kind`                              | `detection_method`            | 入库？   | 运行时角色                                                                                                                                                                                                    |
| -------- | ---------------------------------------- | ----------------------------- | ----- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| TRAP-001 | `semantic_risk_numeric`                  | `static_scan_post_l0`         | 是     | L0 后扫 `RectangleShape2D`，写 `needs_human_review`，附原始尺寸。不进 Agent                                                                                                                                           |
| TRAP-002 | `converter_gap`                          | `static_scan_post_l0`         | 是     | 对比转换前后 `project.godot` 易丢字段                                                                                                                                                                              |
| TRAP-003 | `verifier_visible_but_no_rule_guarantee` | `agent_retrieval_or_escalate` | 是     | shader 报错**不是静默的**（`--headless --import` 会正常报出来），仍进循环；A/B 都没命中则 escalate，禁止猜着改 shader。覆盖来源是 `shaders_renames`（6.1）+ 4.x rst 的 Rendering 小节 + `Updating shaders` 例外抽取（6.4），不是把 Godot 引擎 C++ 实现源码 index 进来 |
| TRAP-004 | `cosmetic_only`                          | `not_actively_handled`        | **否** | 注释误替换，性价比最低，不建检测                                                                                                                                                                                         |
| TRAP-005 | `guard_false_positive`                   | `verify_error_filter`         | 是     | verify 出口用 C 层 autoload 列表剔除假阳性，Agent 看不到这些报错                                                                                                                                                            |
| TRAP-006 | `guard_false_positive`                   | `verify_error_filter`         | 是     | 与 005 同一过滤器，addon 单例；`confidence=needs_review`                                                                                                                                                           |
| TRAP-007 | `informational_not_a_fix_task`           | `preflight_probe_recommended` | **否** | `.uid` 由 `--import` 首次创建，pipeline 已覆盖；只提醒动手前用最小项目探针                                                                                                                                                      |


TRAP-001 的 `trigger` 找的是类型名而不是 `extents`：转换之后旧属性名可能已经消失。这正是不能 overlay 到改名行上的原因。

TRAP-003 不是「把 Godot C++ 源码 index 进 RAG」。shader 报错要的是语言规范（rst Rendering 小节 + `shaders_renames` + 6.4 的例外抽取），不是渲染器实现。匹配不到规则本身就是覆盖盲区信号，而不是「Agent 应该更努力去猜」的信号。

### 8.2 `semantic_rewrites` → 全部 `agent_retrieval`

`yield` / `Tween` / `move_and_slide` / 信号连接 / `setget` / `File` / `OS` / 注解 / EditorPlugin / RPC：`symbol_kind=rewrite`，`change=rewrite`，`source=manual_rewrite`，`agent_action=apply_and_warn`。这些不是一对一改名，Agent 必须结合上下文改写。3→4 总指南已在常驻 window 里，这些行提供的是**可检索的挂钩**（报错或符号命中时把对应警告和 `id` 拉出来），不是把整篇教程再存一遍。

`trigger.symbol` 同时写入 `old_symbol` 和 `match_tokens`，方便按符号查表。

### 8.3 大文件（YAML 里的工程说明，不是规则行）

官方转换器对超大文件有跳过阈值，且基本肯定不能靠参数关掉。对策已经编码在 L0.5：用启用的 cpp 改名表全仓库再跑一遍。不在 `migration_rules` 里为「大文件」单开一行。

---



## 9. 填表示例

cpp 启用：

```json
{
  "id": "official_renames:4.0:_:class:Area",
  "old_symbol": "Area",
  "new_symbol": "Area3D",
  "owner": null,
  "symbol_kind": "class",
  "change": "rename",
  "detection_method": "agent_retrieval",
  "since_version": "4.0",
  "since_version_code": 40000,
  "source": "official_renames",
  "agent_action": "apply_rename",
  "payload": {"cpp_array": "class_renames"}
}
```

JSON 删除：

```json
{
  "id": "api_diff:4.0:PathFollow2D:property:lookahead",
  "old_symbol": "lookahead",
  "new_symbol": null,
  "owner": "PathFollow2D",
  "symbol_kind": "property",
  "change": "remove",
  "detection_method": "agent_retrieval",
  "since_version": "4.0",
  "source": "api_diff",
  "agent_action": "note_only"
}
```

rst 拍平行（与上一行描述同一事实，允许并存）：

```json
{
  "id": "official_prose:4.1:Object:method:get_meta_list",
  "old_symbol": "get_meta_list",
  "new_symbol": "get_meta_list",
  "owner": "Object",
  "symbol_kind": "method",
  "change": "signature",
  "detection_method": "agent_retrieval",
  "since_version": "4.1",
  "since_version_code": 40100,
  "source": "official_prose",
  "snippet": "Method get_meta_list changes return type from PackedStringArray to Array[StringName]",
  "payload": {
    "gdscript_compatible": true,
    "github": "GH-76418",
    "section": "Breaking changes > Core"
  },
  "agent_action": "note_only"
}
```

YAML 静态扫描（Agent 检索不到）：

```json
{
  "id": "TRAP-001",
  "old_symbol": "RectangleShape2D",
  "owner": "RectangleShape2D",
  "symbol_kind": "trap",
  "change": "trap",
  "rule_kind": "semantic_risk_numeric",
  "detection_method": "static_scan_post_l0",
  "trigger": {
    "symbol": "RectangleShape2D",
    "match_scope": ["*.tscn", "*.tres", "*.gd"]
  },
  "semantic_risk": 1,
  "verifier_blind": 1,
  "system_action": "After L0, scan for RectangleShape2D; emit needs_human_review with original size values.",
  "source": "manual_trap",
  "confidence": "verified",
  "agent_action": null
}
```

YAML 假阳性过滤（Agent 检索不到）：

```json
{
  "id": "TRAP-005",
  "symbol_kind": "trap",
  "change": "false_positive",
  "rule_kind": "guard_false_positive",
  "detection_method": "verify_error_filter",
  "trigger": {
    "error_pattern": "Identifier not found|hides an autoload singleton",
    "cross_check": "identifier in project.godot::autoload_list"
  },
  "source": "manual_trap",
  "agent_action": null
}
```

YAML 语义重构（Agent 可检索）：

```json
{
  "id": "REWRITE-001",
  "old_symbol": "yield",
  "new_symbol": "await",
  "symbol_kind": "rewrite",
  "change": "rewrite",
  "rule_kind": "coroutine_rewrite",
  "match_tokens": ["yield"],
  "detection_method": "agent_retrieval",
  "since_version": "4.0",
  "semantic_risk": 1,
  "agent_action": "apply_and_warn",
  "source": "manual_rewrite"
}
```

---



## 10. 明确不进 `rules.db` 的东西

- `upgrading_to_godot_4.rst`，**除** `Updating shaders` **小节外**的全文 → `artifacts/agent_context/`
- rst 里抽不出符号的散文、GDExtension 示例代码 → 写入 `vault/tier_b_prose/`，供**下一阶段** B 层 LanceDB 编译使用（本阶段不生成 embedding）
- YAML `not_actively_handled` / `preflight_probe_recommended`
- YAML `build_pipeline_notes`
- cpp 的 C# 数组
- `extension_api.json` 的 ABI 尺寸 / native struct
- Godot 引擎 C++ 源码（shader 报错要的是规范，不是实现——**这一条排除的是引擎实现，不是 shader 数据本身**，shader 数据仍然正常入库，见 6.1、6.4）

---



## 11. 和运行时契约的关系

以后 `rag/retriever/schemas.py` 里的 Pydantic `MigrationRule` 必须与第 5 节列 1:1（JSON 列在 Python 里是 `list` / `dict`）。检索服务的完整接口——`RetrievalQuery` / `RetrievalResult`、A/B 两层怎么在一次调用里同时召回、怎么包成 Agent 工具——写在 [rag/retriever/docs/](../retriever/docs/README.md)，入口是 [retriever/README.md](../retriever/README.md)。本文件只负责「数据库里一行是什么」，那份目录负责「怎么把这些行服务出去」。

扫描器和过滤器不是 retriever 的一部分：它们是 Day 3/4 流水线组件，只 `SELECT detection_method = ...`，也不经过 `RetrievalQuery` 这套契约。本协议把它们的配置存在同一份 db 里，是为了「改 YAML → 重编译」一个动作更新所有通路，而不是为了让 Agent 去调用扫描器。

下一轮实现顺序：`rag/version_codec.py` → Pydantic schema（`rag/retriever/schemas.py` 补齐 RetrievalQuery / Result）→ 四个 adapter 写 jsonl → `build_tier_a.py` 建表导入 → `rag/retriever/` 下 stub 按 [retriever/docs/](../retriever/docs/README.md) 填函数体。在那之前不要改列名。