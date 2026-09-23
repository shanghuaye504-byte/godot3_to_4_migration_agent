# 场景解析 + 场景校验：实现指导

本文件只覆盖两件事：把 `.tscn` / `.tres` 解析进现有 codeindex，以及用 `codeindex scene-check` 给出场景侧的可证错误。编排层、edit 工具、生产环境的 load sweep 都不在本阶段。

---

## 0. 两条不可动摇的设计公理

### 公理 1：解析器不做判断，校验器不做解析

| | 解析器（L0–L2） | 校验器（L4 / L5） |
| --- | --- | --- |
| 唯一职责 | 把文本变成模型 | 对模型做语义判断 |
| 允许报的错 | 只有语法不成立（Godot 自己也读不了） | 语义 / 引用 / 成员消失 |
| 禁止做的事 | 禁止说「这个类型不存在」 | 禁止重新扫文本 |
| 失败姿态 | 永不抛异常，返回 `problems[]` + 尽可能完整的部分模型 | 信息不足时弃权，不猜 |

### 公理 2：ERROR 只用可证事实，不做引擎类白名单

| 判断形式 | 需要什么 | 可否当作 ERROR |
| --- | --- | --- |
| 「`type="CharacterBody2D"` 是不是合法引擎类？」 | 完整 ClassDB | 否。缺一个类就误报。本阶段不做 ClassDB dump |
| 「`type="KinematicBody2D"` 是不是 rules.db 里的旧类名，且不是本仓库的 `class_name`？」 | 已有规则库的 `old_symbol` + 本仓库 `classes` 表 | 是 |
| 「baseline 时这个脚本有 `class_name Player` / `func _on_died`，现在没有了，场景还指着它？」 | 冻结的成员快照 + 当前符号表 + `scene_refs` | 是。这是时序事实，不是白名单 |

推论：

- 凡是「X 是否为合法引擎 API」一律不做，也不做成 WARN 充数。
- 凡是文件内闭合、文件系统事实、规则库黑名单、baseline 成员差分，可以是 ERROR。
- 信息不够（实例子树、继承场景、脚本语法错误、规则库缺失）就弃权，写入 `coverage`，不报 ERROR。

---

## 1. 六层功能架构（含物理位置）

解析、落库、规则都在 `codebase_index/index/src/codeindex/` 里，和现有 daemon、`writer.reindex_batch` 共用同一个 SQLite、同一次写事务。场景表是旁路，不进 `edges`，也不进 `files`。

对外只有现有 CLI，不新开包、不新开进程、不做 MCP：

- `codeindex find-symbol`：原有 `matches` 不动，追加场景引用。
- `codeindex scene-check`：本阶段新增的唯一子命令。Agent 用 Bash 调，stdout 一行 JSON。
- `verify` MCP 继续只校验脚本。收尾门是以后编排层在 verify 返回 CLEAN 之后再调 `scene-check`；本阶段不实现编排层，只把命令契约写清楚。

```
.tscn/.tres
    │
    ▼
L0 lexer.py ──► L1 model.py ──► L2 resolve.py ──► L3 index.py
词法/值            文档模型          单文件语义         同库异表，写入 reindex_batch 的同一事务
                                                      │
                              ┌───────────────────────┴────────────────────────┐
                              ▼                                                ▼
                    L4 rules.py                                         find-symbol
                    现算 ERROR，不缓存                              同一 JSON 追加 scene_usages
                              │
                              ▼
                    L5 baseline.py
                    fingerprint 差分 + E_MEMBER_GONE
                              │
                              ▼
                    codeindex scene-check     （CLI，不是 MCP）
```

| 层 | 模块 | 输入 → 输出 | 纯度 |
| --- | --- | --- | --- |
| L0 | `scene/lexer.py` | `text → RawSection[]` | 纯函数 |
| L1 | `scene/model.py` | `RawSection[] → SceneDoc` | 纯函数 |
| L2 | `scene/resolve.py` | `SceneDoc → SceneModel` | 纯函数，不碰文件系统 |
| L3 | `scene/index.py` | `SceneModel → SQLite` | 有 IO。挂在现有 writer 事务里 |
| L4 | `scene/rules.py` | 模型 + 索引 + 规则库路径 → `Problem[]` | 只读。每次现算，不落 problem 缓存 |
| L5 | `scene/baseline.py` | `Problem[]` + 冻结快照 → regression / pre_existing / fixed | 只读快照；快照本身只在冻结时写一次 |

L2 不做跨文件判断。`serialize.py` 若写，只给少量手写 fixture 调试，不在生产路径，也不作为 Step 2 的前置。

---

## 2. L0 / L1：格式规范

### 2.1 已核实的格式事实

| 事实 | 影响 |
| --- | --- |
| 首行 `[gd_scene format=3 uid="uid://..."]` 或 `[gd_resource type="X" script_class="Y" format=3 uid=...]` | `format=2` 表示仍是 Godot 3 文本。这是事实，不是预测 |
| `load_steps` 在较新 4.x 已废弃 | 不要用它做校验 |
| section：`gd_scene` / `gd_resource` / `ext_resource` / `sub_resource` / `node` / `connection` / `resource` / `editable` | 未知 section 记 `W_UNKNOWN_SECTION`（不升 ERROR），正文仍尽量保留 |
| Godot 4 的 ext/sub id 是字符串 `id="1_7bt6s"`；Godot 3 是整数 `id=1` | 两种都要解析 |
| `ExtResource("id")` 与 `SubResource("id")` 的 id 空间独立，可以重名 | 分表，不合并 |
| `path` 可以是 `res://`，也可以是相对该文件的路径 | 解析时两种都试 |
| 行首（允许前导空白）以 `;` 开始的是注释 | 词法器必须跳过，否则注释里的 `[` 会撕裂 section |
| 场景应有且仅有一个根（无 `parent=` 的 node）。文档写明否则导入失败 | 0 个或大于 1 个是 ERROR |
| 非根 `parent` 不含根节点名；直接子节点为 `"."` | `parent == "."` 时路径为 `name`，否则 `parent + "/" + name` |
| node 经常有 `type`，但实例覆盖节点可以没有 | 无 `type` 且无 `instance` / `instance_placeholder`，又不在实例子树里，才是 ERROR |
| 其他合法 node 键：`instance` / `instance_placeholder` / `index` / `groups` / `owner`，以及未列出的键 | heading 的键值是开放集合，禁止按键名白名单丢弃 |
| `NodePath("")` 不是错误 | 空路径不要报 |

heading 属性不要做白名单。没见过的键照进 `attrs`。

### 2.2 值语法（L0 必须能保留，不必理解语义）

```
value := string | stringname | nodepath_lit | int | float | bool | null
        | call | array | typed_array | dict
string      := "..."     转义: \" \\ \n \t \r \/ \uXXXX
stringname  := &"..."
nodepath_lit:= ^"..."
call        := Ident "(" [value {"," value}] ")"
array       := "[" [value {"," value}] [","] "]"
typed_array := "Array" "[" Type "]" "(" array ")"
dict        := "{" [ value ":" value {"," value} ] [","] "}"
```

三个必须处理的坑：

1. 多行值。`array` / `dict` / `call` 可跨行（`PackedVector2Array(...)` 经常上千个数）。用括号深度驱动，不按行切。深度统计必须跳过字符串里的括号。
2. 嵌套属性名。`theme_override_colors/font_color`、`metadata/foo`、`libraries/""`（键可以是带引号的空串）。键保持原始字符串，不要 split 后丢信息。
3. 没见过的 `Foo(...)` 不要报错，保留为 `Call{name, args}`。Godot 3 的 `PoolByteArray` / `Transform` / `Quat` 走这条，不单独列白名单。

### 2.3 数据结构（每个节点都带 span）

```python
@dataclass(frozen=True)
class Span:
    byte_start: int
    byte_end: int
    line: int          # 1-based。场景侧统一用这个，与 Godot 报错对齐
    col: int           # 1-based

@dataclass
class Value:
    kind: Literal["str","strname","nodepath","int","float","bool","null",
                  "call","array","dict","typed_array"]
    raw: str
    span: Span
    name: str | None = None
    items: list["Value"] = ()
    pairs: list[tuple["Value","Value"]] = ()

@dataclass
class Section:
    kind: str
    attrs: dict[str, Value]                 # heading 里的 k=v，键开放
    props: list[tuple[str, Value]]          # 保序、允许重复键。不要用 dict
    span: Span
    heading_span: Span

@dataclass
class SceneDoc:
    path: str
    doc_kind: Literal["scene","resource"]
    format: int | None
    uid: str | None
    script_class: str | None
    sections: list[Section]
    problems: list[Problem]                 # 仅语法级
```

`props` 用 list：重复键是真实损坏，dict 会吞掉。

### 2.4 语法级 problems（全部 ERROR，且确定）

| code | 条件 |
| --- | --- |
| `P_UNTERMINATED_STRING` | 字符串未闭合 |
| `P_UNBALANCED_BRACKET` | `(` / `[` / `{` 到 EOF 深度未归零 |
| `P_MALFORMED_HEADING` | `[...]` 内不是 `ident (k=v)*` |
| `P_MISSING_FILE_DESCRIPTOR` | 首个 section 不是 `gd_scene` / `gd_resource` |
| `P_PROP_BEFORE_SECTION` | 文件描述符之前出现 `k = v` |
| `P_GIT_CONFLICT_MARKER` | 出现 `<<<<<<<` / `=======` / `>>>>>>>` |
| `W_UNKNOWN_SECTION` | section 名不在已知列表。不升 ERROR，避免以后加 section 就打挂 |

二进制（文件含 NUL）和超限文件不走这张表，见 L3 的 `parse_status`。

---

## 3. L2：单文件语义模型

```python
@dataclass
class SceneModel:
    path: str
    doc_kind: str
    format: int | None
    uid: str | None
    script_class: str | None
    ext: dict[str, ExtRes]          # id -> {type, uid, ref_path, span}
    sub: dict[str, SubRes]
    nodes: list[SceneNode]
    node_by_path: dict[str, SceneNode]
    root_paths: list[str]           # 0 个或大于 1 个交给 L4，L2 只记录
    conns: list[Connection]
    editables: list[str]
    refs: list[Ref]
    unresolved_subtrees: list[str]  # instance / instance_placeholder 的路径前缀
    is_inherited: bool              # 根节点带 instance=
```

### 三个算法

节点全路径：

```
第一个无 parent 的 node → node_path = "."
其余: parent == "." 时路径为 name，否则 parent + "/" + name
之后每一个无 parent 的 node 追加进 root_paths（L2 不报错）
```

实例子树（后面所有「是否存在」类 ERROR 的弃权范围）：

```
node 有 instance= 或 instance_placeholder= → unresolved_subtrees += node_path
根节点有 instance= → is_inherited = True，unresolved_subtrees += "."
```

落在这些前缀下的节点、连接、NodePath，其「本地是否存在」不得报 ERROR。真相在别的文件里。

引用边（递归所有 Value，全部带 Span）：

| `Ref.kind` | 来源 | 索引用途 |
| --- | --- | --- |
| `node_type` | `[node type="X"]` | find-symbol；`E_UNMIGRATED_TYPE`；`E_MEMBER_GONE` |
| `res_type` | ext/sub 的 `type=` | `E_UNMIGRATED_TYPE` |
| `ext_path` | `ext_resource path=` | 路径是否存在 |
| `ext_use` / `sub_use` | `ExtResource` / `SubResource` | id 是否声明 |
| `script_ref` | `script = ExtResource` | 反查「谁引用了这个 .gd」 |
| `instance` | `instance = ExtResource` | 环检测；实例子树 |
| `conn_method` | `[connection method=]` | `E_MEMBER_GONE`（func） |
| `conn_signal` | `[connection signal=]` | 只索引，本阶段不单独判 |
| `nodepath` / `group` | 字面量 | 只索引，本阶段不判 |
| `prop_key` | 挂了脚本的节点上的属性键 | 先索引。export 差分本阶段不判 |
| `script_class` | `.tres` 的 `script_class=` | 只索引，本阶段不判 |

`prop_key` 在索引时不要用 rules.db 过滤。规则会变，过滤后的索引会脏。挂了脚本的节点，属性键全部入库。

L2 到此不判断对错。

---

## 4. L3：工程索引

### 4.1 和现有 writer 的挂接

现有 daemon 的 `_should_index` 只放行 registry 里的 `.gd` / `.cs` / `.cpp` / `.h` / `.hpp`。不改扫描范围的话，watcher 永远看不到场景，`find-symbol` 的场景引用会一直是旧的。

做法：

- `.tscn` / `.tres` **不要**塞进 tree-sitter registry，也 **不要**写入现有 `files` 表。送进 GDScript parser 会变成「户口还在、符号为空」的失败行。
- 扩展 daemon 全量扫描和 watcher 过滤，让这两种后缀进入 `reindex_batch` 的路径列表。
- `reindex_batch` 仍是一个 SQLite 事务。事务内按后缀分叉：代码走原 `_reindex_single_file`，场景走场景解析器。
- 单个场景解析失败不得弄垮这批事务：捕获后记 `parse_status`，同批其他文件照常提交。
- 删除场景文件时删掉该 path 在全部 `scene_*` 表中的行。

`parse_status`：

| 值 | 含义 | 算不算语法 ERROR |
| --- | --- | --- |
| `OK` | 解析完成 | 语法 problems 另计 |
| `MALFORMED` | 有语法级 problem，模型可能不完整 | 是，报那些 P 级 |
| `BINARY` | 含 NUL，不当文本解析 | 否。写入 coverage，不喷语法错误 |
| `SKIPPED_OVERSIZE` | 单文件 > 4MB | 否。与官方 converter 静默跳过的门槛对齐。写入 coverage，不要假装扫过 |

`scene_index_stale`：某场景文件的 mtime 新于 `scene_files.indexed_at`，或 daemon 还没扫过场景。只作标志，不当第三套校验结果。

### 4.2 表

不改已有 `edges` / `files` / `symbols`。不建 `scene_problems`：L4 每次现算，规则一改缓存即脏。

```sql
CREATE TABLE scene_files(
  path TEXT PRIMARY KEY,
  doc_kind TEXT,
  format INT,
  uid TEXT,
  script_class TEXT,
  sha TEXT,
  mtime INT,
  parse_status TEXT,          -- OK | MALFORMED | BINARY | SKIPPED_OVERSIZE
  problem_count INT,
  root_count INT,
  is_inherited INT,
  indexed_at INT
);

CREATE TABLE scene_nodes(
  path TEXT, node_path TEXT, name TEXT, type TEXT, parent_path TEXT,
  script_ext_id TEXT, instance_ext_id TEXT, is_placeholder INT,
  in_unresolved_subtree INT,  -- 弃权用的是这一列，不是 subject 字符串
  line INT,                   -- 1-based
  PRIMARY KEY(path, node_path)
);

CREATE TABLE scene_ext(
  path TEXT, ext_id TEXT, type TEXT, uid TEXT,
  ref_path TEXT, resolved_file TEXT,   -- NULL = 解析不到
  line INT,
  PRIMARY KEY(path, ext_id)
);

CREATE TABLE scene_sub(
  path TEXT, sub_id TEXT, type TEXT, line INT,
  PRIMARY KEY(path, sub_id)
);

CREATE TABLE scene_conn(
  path TEXT, signal TEXT, from_path TEXT, to_path TEXT, method TEXT,
  line INT
);

CREATE TABLE scene_refs(
  path TEXT, line INT, col INT, kind TEXT,
  symbol TEXT, node_path TEXT, target_file TEXT, detail TEXT
);
CREATE INDEX idx_refs_symbol ON scene_refs(symbol);
CREATE INDEX idx_refs_target ON scene_refs(target_file);
CREATE INDEX idx_refs_kind   ON scene_refs(kind, symbol);

-- 只在「冻结 baseline」时写一次，之后只读
CREATE TABLE scene_baseline(
  fingerprint TEXT PRIMARY KEY,
  path TEXT, code TEXT, tier TEXT, subject TEXT
);

CREATE TABLE scene_member_baseline(
  script_path TEXT,          -- 相对 project_root 的 .gd
  kind TEXT,                 -- 本阶段只有 class | func
  name TEXT,
  PRIMARY KEY(script_path, kind, name)
);
```

`scene_nodes.line` / `scene_refs.line` / Problem.line 都是 **1-based**。现有 `symbols.line` 仍是 **0-based**，不要改。

### 4.3 fingerprint 不含行号

```python
fingerprint = sha1(f"{code}|{path}|{subject}")
# subject 例：node_path / ext_id / "method:_on_died@Player" / "type:KinematicBody2D"
```

含行号的话，文件头插一行注释会把旧问题算成新 regression。

### 4.4 路径解析（`ref_path → resolved_file`）

按序尝试，不做 `.gd` ↔ `.cs` 同名试探（verify 遇到 `.csproj` 会整仓拒绝，这条路径走不到）：

```
1. 去掉 "::SubName" 后缀（res://a.tres::Resource_x）
2. res://X     → <workspace>/X
3. 相对路径     → dirname(当前文件) / X
4. 只有 uid://、没有 path → resolved_file = NULL，且不报 E_EXT_PATH_MISSING
5. 全失败       → resolved_file = NULL
```

intake 会清掉 `*.uid`，uid 反查通常失败。这不是场景文本写错。uid 与 path 不一致是引擎缓存里的事，静态规则看不见，见文末盲区。

### 4.5 规则库路径

`E_UNMIGRATED_TYPE` 只读打开配置里的 `migration_rules_db`（指向已建好的 `rules.db`）。codeindex **不要** `import rag`。

路径缺失或文件打不开：跳过这条规则，`coverage.rules_unavailable = true`。禁止在这种情况下把类型问题当成已通过。

查询只用 `symbol_kind = 'class'` 的 `old_symbol`。方法名、属性名不要拿来判节点类型。

### 4.6 `find-symbol` 的真实返回

当前 CLI 形状是 `{"name", "matches":[...]}`，没有 `definitions` / `edges`。`matches[].line` 是 0-based，保持逐字段不变。

在**同一个对象**上追加场景字段。`scene_usage_count` 是 `COUNT(*)`，不是返回列表的长度。列表 `LIMIT 50`。

```json
{
  "name": "Player",
  "matches": [
    {"path": "actors/player.gd", "name": "Player", "kind": "class",
     "line": 2, "end_line": 2, "class_name": "Player", "signature": "class_name Player"}
  ],
  "scene_usages": [
    {"file": "levels/l1.tscn", "line": 14, "kind": "node_type",
     "node_path": "Player", "symbol": "Player", "detail": "type=\"Player\""}
  ],
  "scene_usage_count": 3,
  "scene_usage_truncated": false,
  "scene_index_stale": false
}
```

`scene_usages[].line` 是 **1-based**。和 `matches[].line` 的 0-based 不要混用，文档和字段注释里写明。

`matches` 为空但场景里还有引用时，仍然返回 `scene_usages`，退出码用 **0**。现在的实现是 matches 为空就退出码 1。那正是「代码里符号没了、场景还指着它」的时刻，如果这时丢掉场景引用，追加字段就没有意义。

两边都空：保持今天的行为，退出码 1，`scene_usages` 为 `[]`，`scene_usage_count` 为 0。

查询：

```sql
-- 计数与列表分开。count 不受 LIMIT 影响
SELECT COUNT(*) FROM scene_refs
WHERE symbol = ?1
  AND kind IN ('node_type','res_type','conn_signal','conn_method',
               'group','script_class','prop_key','nodepath');

SELECT * FROM scene_refs
WHERE symbol = ?1 AND kind IN ( ... 同上 ... )
UNION ALL
SELECT * FROM scene_refs
WHERE target_file = ?2     -- 符号定义所在的 .gd；matches 为空时这一支可以没有
  AND kind IN ('script_ref','ext_path','instance')
LIMIT 50;
```

`call-chain` / `class-hierarchy` 不改。

---

## 5. L4：ERROR 与弃权

### 5.1 弃权是框架行为，不是每条规则各自 if

任一 ERROR，若其 **节点路径**（连接则看 `from_path` / `to_path`）落在 `unresolved_subtrees` 前缀下，或所在文件 `parse_status != OK`，则不报 ERROR，记入 `coverage.suppressed_checks`，并写明原因。

不要用 `subject` 做这件事。`subject` 会是 `method:_on_died@Player`，对不上路径前缀。

依赖某份脚本的规则（本阶段主要是 L5 的 `E_MEMBER_GONE`）：该脚本不存在，或 codeindex 里该文件语法失败（符号表被清空的那种失败），则整条弃权，同样写入 `suppressed_checks`。一个还没修完的脚本若喷出几十条场景错误，Agent 之后会无视 `scene-check`。

### 5.2 本阶段的 ERROR

| code | 判据 | 依据 |
| --- | --- | --- |
| `E_PARSE_*` | §2.4 的 P 级 | 词法不成立 |
| `E_NO_SCENE_ROOT` | `gd_scene` 且根数量为 0 | 导入会失败 |
| `E_MULTIPLE_ROOTS` | 根数量 > 1 | 同上 |
| `E_EXT_ID_UNDECLARED` | `ExtResource("X")` 无对应声明 | 文件内闭合 |
| `E_SUB_ID_UNDECLARED` | `SubResource("X")` 无对应声明 | 文件内闭合 |
| `E_DUPLICATE_EXT_ID` / `E_DUPLICATE_SUB_ID` | 同一 id 声明两次 | 文件内闭合 |
| `E_EXT_PATH_MISSING` | `ref_path` 非空且 `resolved_file` 为空 | 文件系统。纯 uid、无 path 的不报 |
| `E_SCRIPT_REF_NOT_SCRIPT` | `script = ExtResource` 的目标扩展名不是 `.gd` | 文件系统。不试 `.cs` |
| `E_NODE_PARENT_MISSING` | `parent` 在本文件节点树里不存在，且不在实例子树 / 继承场景的弃权范围内 | 文件内闭合 |
| `E_NODE_NO_TYPE` | 无 `type` / `instance` / `instance_placeholder`，且不在弃权范围内 | 无法构造节点 |
| `E_CONN_NODE_MISSING` | `from` / `to` 在本文件不存在，且不在弃权范围内 | 文件内闭合 |
| `E_UNMIGRATED_TYPE` | node/ext/sub 的 type 属于规则库 `old_symbol` 且 `symbol_kind=class`，并且不是本仓库任一 `class_name` | 黑名单 + 本仓库类表。用户自己写了 `class_name KinematicBody2D` 时不报 |
| `E_NOT_CONVERTED` | `format == 2` | 文件仍是 Godot 3 文本 |
| `E_INSTANCE_CYCLE` | `instance` 边成环 | 图事实 |

`E_MEMBER_GONE` 放在 L5，因为它依赖冻结快照，不是单文件事实。

### 5.3 Problem

```python
@dataclass
class Problem:
    fingerprint: str
    code: str
    tier: Literal["ERROR"]       # 本阶段对外只出 ERROR
    path: str
    line: int                     # 1-based
    col: int
    node_path: str | None         # 弃权键。连接可填 from/to 中触发的那条
    subject: str                  # 稳定标识，不含行号
    message: str
    evidence: str                 # 原文切片，来自 span，不靠重新打印文件
```

`evidence` 必须是原文里的切片，这样以后 edit 能拿它当锚点。做不到唯一时，问题仍可报，但 `evidence` 留空，不要造一段「看起来像原文」的文本。

---

## 6. L5：baseline、`E_MEMBER_GONE`、CLI

### 6.1 为什么需要成员差分

官方 converter 不会留下「改个函数名就能修好」的债。`--check-only` 也看不见下面两类，而它们都是修复循环里 LLM 自己造成的：

- 改了 `class_name`，`.tscn` 的 `type=` 还是旧名。旧名不在 rules.db 里，`E_UNMIGRATED_TYPE` 抓不到。
- 改了信号回调的函数名，`[connection method=]` 还是旧名。

`@export` 改名会导致场景属性被引擎静默丢掉，verify 和 load 都是 CLEAN。这条更危险，但当前 GDScript parser 把所有 `var` 存成 `kind=var`，分不出 `@export`。本阶段不做。等符号上有 export 标记后再加，不为此做 ClassDB，也不挡住 L0。

### 6.2 `E_MEMBER_GONE`

冻结 baseline 时，把当时 codeindex 里每个项目脚本的 `class_name` 和 `func` 写入 `scene_member_baseline`。这份表之后只读，不随后来的重新索引更新。

检查时：

```
对快照中的 (script_path, kind, name)：
    当前该 script_path 的符号表里已经没有这个 (kind, name)
    且场景仍引用它：
        kind=class → scene_refs.kind=node_type 且 symbol=name
        kind=func  → scene_refs.kind=conn_method 且 symbol=name
                     且该连接 to 节点所挂脚本（含项目内 extends 链）是 script_path
    → 报 E_MEMBER_GONE
```

不会误报的原因：`Sprite2D`、`_ready` 这类引擎名字从来不会出现在项目符号快照里，所以不会进入「消失」集合。

弃权：该脚本当前语法失败，或 `extends` 链在走到引擎类之前就断了且本条 func 只可能定义在缺失的那一截上。弃权写入 `suppressed_checks`，不报 ERROR。

`class` 这一支不需要链完整：`class_name` 是文件级事实。`func` 这一支在链不完整时，只对**快照里确实记在这个 script_path 上**的函数做比较，不要猜父类里还有没有同名函数。

### 6.3 三分法

冻结时机：converter 与首次把场景扫进索引之后、LLM 第一次改文件之前。冻结 = 全量跑一次 L4+L5（此时 `E_MEMBER_GONE` 应为空，因为快照就是当前符号），把 fingerprint 写入 `scene_baseline`。

```
regression    = 现在有、baseline 没有     # 唯一可用来拦「任务完成」的集合
pre_existing  = 现在有、baseline 也有     # 默认只返回 count 与 by_code，不刷明细
fixed         = baseline 有、现在没有
```

`E_MEMBER_GONE` 在冻结时不存在，之后才出现，因此自然落在 `regression`。

### 6.4 `codeindex scene-check`

```
codeindex scene-check [--path PATH ...]
```

- 不传 `--path`：全量。
- 传了路径：这些文件，加上 `scene_refs.target_file` 反查到的、引用了这些 `.gd` 的场景。闭包在命令内部完成。
- 本阶段不做 `edit_journal`。edit 工具还不存在，日记不该写进 codeindex。调用方把改过的路径传进来即可。

stdout 一行 JSON：

```python
{
  "regression": [Problem, ...],
  "pre_existing": {"count": N, "by_code": {...}},
  "fixed": [{"fingerprint", "code", "path"}],
  "coverage": {
    "files_total": N,
    "files_ok": N,
    "files_parse_failed": [paths],
    "files_skipped_oversize": [paths],
    "files_binary": [paths],
    "suppressed_checks": [{"path", "node_path", "reason"}],
    "rules_unavailable": false,
    "scene_index_stale": false
  },
  "summary": {"error": N, "by_code": {...}}
}
```

退出码：

| 码 | 含义 |
| --- | --- |
| 0 | 检查跑完了。有没有 regression 只看 JSON。不要用 1 表示「有问题」，1 在 `find-symbol` 里是「查无此符号」 |
| 2 | 库没准备好（没 config、daemon 没起来、db 不在）。与现有 CLI 的「还没准备好」一致 |

`scene-check` 不拦文件写入，只给以后的收尾门用。修一个场景 regression 常常要再改脚本，拿它禁止 edit 会死锁。

将来的收尾条件（本阶段不实现，只作为命令的调用约定）：

```
迁移完成 ⟺ verify 的项目级检查为 CLEAN 且 gdscript_complete
         ∧ scene-check 不带 --path 时 regression 为空
         ∧ coverage.files_parse_failed 为空
         ∧ coverage.rules_unavailable 为 false
```

超限与二进制留在 coverage 里，不单独把任务打成失败：那些文件本阶段没有静态结论。编排层以后可以据此升级人工，但那不是这条命令的退出码。

---

## 7. 实现顺序与测试

语料先用几十个真实 `.tscn` / `.tres`：Godot 3 与 Godot 4、converter 前后、含 instance、继承场景、多行 `Packed*Array`、`;` 注释、相对路径。不要在 Step 1 之前收集几千个文件。全库规模留到规则稳定之后。

### Step 1 — L0 + L1

生产路径靠 span 切原文，不靠把文件打印回去。Godot 的空格、浮点和注释没有稳定的打印规范，字节级往返会变成主工期。

| 测试 | 通过标准 |
| --- | --- |
| span 切片 | 每个 `Value` / `Section` 的 `text[byte_start:byte_end] == raw`；`line` / `col` 与逐字节换行计数一致 |
| 覆盖 | 去掉注释和空白后，每个字节都落在某个 span 里 |
| 格式矩阵 | format 2 与 3、整数 id 与字符串 id、`;` 注释、多行 Packed 数组、`theme_override_colors/font_color`、`libraries/""`、`&"..."`、`^"..."`、`Array[Node]([])`、转义、空 `NodePath("")`、尾随逗号、CRLF、无尾换行。span 测试全过 |
| 不抛 | 语料 + 随机截断 / 字节翻转：零未捕获异常，问题进 `problems[]` |
| P 级 | 每个 `P_*` 至少 1 个正例 + 1 个易混淆反例 |
| 未知构造器 | `PoolByteArray(...)` / `NotARealType(...)` 保留为 call，不报语法错误 |

`serialize.py` 可以给三五个手写 fixture 做调试，不作为本步通过条件。

### Step 2 — L2

| 测试 | 通过标准 |
| --- | --- |
| 节点树 | 含多层嵌套、`parent="."`、同名兄弟的 fixture，`node_by_path` 与人工标注一致 |
| 多根 / 无根 | 0、1、2 个根时 `root_paths` 长度正确 |
| 实例子树 | 继承场景、`instance=`、`instance_placeholder` 的 `unresolved_subtrees` / `is_inherited` 与标注一致 |
| 引用边 | 语料上 `ext_use` / `sub_use` 的条数，等于在字符串之外数到的 `ExtResource("` / `SubResource("` 次数 |
| 纯度 | L2 的导入不含 `os` / `pathlib` / `sqlite3` |

### Step 3 — L3 + `find-symbol`

| 测试 | 通过标准 |
| --- | --- |
| 路径 | `res://`、相对路径、`::` 后缀、只有 uid 没有 path。前三类 `resolved_file` 正确；最后一类为 NULL 且不产生 `E_EXT_PATH_MISSING` |
| 同事务 | 一批里夹一个坏场景，其他 `.gd` 与好场景仍然提交；坏场景是 `MALFORMED` 而不是整批回滚 |
| 增量等于全量 | 随机编辑后，增量 sync 的 `scene_*` 与全量重建逐行一致 |
| 扫描范围 | daemon 全量扫描与 watcher 能看见 `.tscn` / `.tres`；这些文件不出现在 `files` 表 |
| 超限 / 二进制 | > 4MB 为 `SKIPPED_OVERSIZE`；含 NUL 为 `BINARY`。二者都进入 coverage，不产生 P 级洪水 |
| `scene_usages` | 一个 `class_name`、一个 `func`、一个脚本路径，在场景里被引用时，`find-symbol` 都能带回。`scene_usage_count` 等于全表计数，大于 50 时 `scene_usage_truncated=true` |
| matches 为空 | 符号已从 `.gd` 删除、场景仍引用：退出码 0，`matches=[]`，`scene_usages` 非空 |
| 向后兼容 | 无场景引用时，`matches` 的字段与旧实现一致（仍是 0-based `line`）。不要求整个 JSON 逐字节相同，因为多了场景字段 |

### Step 4 — L4 ERROR

| 测试 | 通过标准 |
| --- | --- |
| Godot 单向差分 | 对这份小语料里 Godot 4 项目的每个文本场景，`ResourceLoader.load`（只 load，不 instantiate）。单文件超时；进程崩溃则记下该文件并从下一个续跑。**Godot load 成功的文件，我们不报任何 ERROR。** 反向（load 失败 ⇒ 我们必须报）不做 |
| 变异注入 | 在干净文件上注入每一类 E 级故障，每类多例。检出率 100%，`code` 正确，`subject` 不含行号 |
| 弃权 | 把同样的注入放进实例子树或继承场景：ERROR 数为 0，且 `suppressed_checks` 用 `node_path` 记下来 |
| 自定义类排除 | 仓库里有 `class_name KinematicBody2D` 时，不报 `E_UNMIGRATED_TYPE` |
| 规则库缺失 | 不配置 `migration_rules_db` 时不报 `E_UNMIGRATED_TYPE`，`rules_unavailable=true` |
| fingerprint | 文件任意位置插删空行或注释，已有 problem 的 fingerprint 不变 |
| 确定性 | 同输入跑多次，problem 集合一致 |

### Step 5 — L5 + `scene-check`

| 测试 | 通过标准 |
| --- | --- |
| 三分法 | 冻结后修好若干、弄坏若干、留下若干：`fixed` / `regression` / `pre_existing` 的个数精确 |
| 行号漂移 | 文件头插入 100 行后，旧问题仍是 pre_existing，`regression` 为空 |
| `E_MEMBER_GONE` class | 冻结后把 `class_name Player` 改成别的名字，场景 `type="Player"` 仍在 → 一条 regression。场景改成新名字后这条消失 |
| `E_MEMBER_GONE` func | 冻结后重命名被 `[connection method=]` 指向的函数，且没改场景 → regression。引擎回调 `_ready`（快照里没有）不报 |
| 不误伤引擎类型 | 场景里的 `Sprite2D` / `CharacterBody2D` 不产生 `E_MEMBER_GONE` |
| 脚本损坏则弃权 | 目标 `.gd` 语法失败时，不报 `E_MEMBER_GONE`，有 `suppressed_checks` |
| `--path` 闭包 | 传入 `a.gd` 时，结果包含引用它的场景上的问题，不漏；不包含无关场景上新造的问题 |
| 退出码 | 有 regression 时仍是 0；db 不存在时是 2 |
| 快照不跟着变 | baseline 冻结后再索引，`scene_member_baseline` 仍是冻结时的成员，而不是最新符号表 |

---

## 8. 本阶段明确不做

| 不做 | 理由 |
| --- | --- |
| ClassDB dump、引擎类 / 属性 / 信号白名单 | 缺一项就误报 |
| 把「是不是合法引擎 API」做成 WARN 充数 | 没有 ClassDB 时，信号缺失、NodePath 悬空、兄弟重名、参数个数、动画轨道要么误报，要么抓不住 `E_MEMBER_GONE` 已经覆盖的事 |
| `@export` 消失检测 | parser 分不出 export 与普通 var。后续给符号加标记后再做。这是静默丢属性，优先级高于那些 WARN，但不要挡本阶段 |
| `project.godot`、可达性、主场景 / autoload 文件是否存在 | autoload 误报过滤已经在 verify 里。不要在索引里再做一份 |
| `.gd` 与 `.cs` 同名试探 | verify 遇到 C# 工程会整仓拒绝 |
| 字节级 `serialize(parse(text)) == text` 作为全语料门槛 | 见 Step 1 |
| 先收集数千个场景再写解析器 | 几十个覆盖格式矩阵即可 |
| `edit_journal`、用 mtime 当第三套 scene-check 结果 | edit 还不存在。mtime 只用于 `scene_index_stale` |
| `scene_problems` 缓存、`round_seen` | 规则一改就脏。每次现算 |
| 生产环境的 load-only 收尾门 | 见下一节。本阶段 load 只服务 Step 4 的单向差分 |
| 把场景错误塞进 verify 的 `signature_set` | 不改 verify。场景回归由 `scene-check` 自己的 fingerprint 差分表达 |
| 用 `scene-check` 禁止 edit | 中间态必然有 regression，会死锁 |
| 新的 `scene_refs` 工具或 MCP | 引用从 `find-symbol` 漏出；校验是 CLI 子命令 |
| 场景边写入 `edges` | 会污染 call-chain / class-hierarchy |
| `load_steps` 一致性、构造器参数个数 | 废弃字段 / 跨版本 arity，会误报 |
| 编排层、收尾门进程、Multi-Agent | 本阶段只交付可被将来收尾门调用的命令 |

---

## 9. 已知盲区（静态规则原理上看不见）

这些不是本阶段的失败，是覆盖度声明。`ResourceLoader.load` 能看见其中一部分，但生产收尾门本阶段不做。以后若做：独立超时与重试预算，不计入 verify 的连续失败熔断；只 load，不 instantiate，不跑 `_ready`。

- uid 与 `path=` 不一致、uid 重复。intake 清过 `*.uid` 之后，文本里的 uid 更不能当事实。
- 资源类型不匹配（属性要 Texture2D，实际是别的资源）。
- 只存在于 uid / 二进制资源里的循环包含。文本 `instance` 边的环已经由 `E_INSTANCE_CYCLE` 覆盖。
- `SKIPPED_OVERSIZE` 与 `BINARY` 文件的内部错误。
- shader 编译与语义。headless 不编译 shader。
- `@export` 改名导致的属性静默丢弃。
- 数值语义变化（例如 `extents` → `size` 差一倍）。引用仍然闭合，任何存在性检查都是 CLEAN。

---

## 10. 一页速查

| 层 | 对外 | 关键测试 |
| --- | --- | --- |
| L0 / L1 | 内部 | span 切片等于原文；注释与空白之外被 span 盖住；不抛 |
| L2 | 内部 | 实例子树精确；引用边与字符串外出现次数一致；零文件系统依赖 |
| L3 | `find-symbol` 追加字段；daemon / sync 扫到场景 | 增量等于全量；matches 为空仍返回场景引用且退出码 0；超限与二进制进 coverage |
| L4 | 内部，现算 | Godot 能加载 ⇒ 零 ERROR；变异注入零漏报；按 `node_path` 弃权 |
| L5 | `codeindex scene-check` | fingerprint 不含行号；`E_MEMBER_GONE` 只抓快照里消失且场景仍引用的 class / func |

两个数字决定这套东西能不能信：Godot 能 load 的文件上 ERROR 数是 0；`E_MEMBER_GONE` 在「改了 class / func、没改场景」的 fixture 上出现，在引擎类型上不出现。
