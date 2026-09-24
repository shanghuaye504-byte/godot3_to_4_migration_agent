-- codeindex 数据库 schema —— 唯一权威来源（design.md 2.7）
--
-- SQL 术语和「用 player.gd 一行行填表」的走读：
--   codebase_index/index/docs/schema_walkthrough.md
-- （docs/ 按仓库约定 gitignore，给开发者/AI 看，不进 git）
--
-- ---------------------------------------------------------------------------
-- 语句怎么读（schema 里会出现的四种）
--
-- CREATE TABLE  建表。括号里每一行是一列：名字 + 类型 + 约束。
--   INTEGER PRIMARY KEY  这一行的身份证（SQLite 的 rowid）。
--   NOT NULL / UNIQUE    不许空 / 整列不能重复。
--   REFERENCES files(id) 外键：这一格必须等于 files 里已有的某个 id。
--   ON DELETE CASCADE    父行（files 那一行）被删时，子行自动一起删，避免孤儿。
--
-- CREATE INDEX ... ON 表(列)  给这一列做目录，让 WHERE 列 = ? 不用全表扫。
--   这里的 ON 表示「索引建在哪张表的哪一列」，和 JOIN ... ON 不是同一个 ON。
--
-- JOIN 表 ON 条件  查询时才出现（本文件没有 JOIN）。意思是两张表按条件把行夹在一起。
--
-- CTE（WITH RECURSIVE）也是查询写法，不是表。call-chain / 祖先链用它一层层往上爬。
--   schema 里不会 CREATE TABLE callers；那只是查询里的临时名字。
-- ---------------------------------------------------------------------------
--
-- 四张表 = 一个文件户口 + 三种关系（不要合成一张宽表）：
--
--   files     这个 .gd/.cs/.cpp 文件本身
--   symbols   定义：名字声明在第几行     → find-symbol
--   edges     调用边：谁 ──调用──► 谁     → call-chain
--   classes   继承边：谁 ──extends──► 谁  → class-hierarchy
--
-- edges / classes 的另一端存源码原文（to_name / base_name），不存 symbols.id。
-- 引擎 API（queue_free、CharacterBody2D）在本仓库里往往没有定义行，边仍然合法。
-- 查询时用字符串去对 symbols.name / classes.name：对上就展开，对不上就停。
--
-- 三条 CLI 的 WHERE 列 ↔ 索引（查询应走 SEARCH 不是 SCAN）：
--   find-symbol      symbols.name = ?           idx_symbols_name
--   call-chain       edges.to_name = ?          idx_edges_to_name
--   class-hierarchy  classes.name / base_name   idx_classes_name / idx_classes_base
--
-- 增量：files.path UNIQUE + content_hash。hash 没变 skipped；变了清该 file_id 子行再插入。


-- ---------------------------------------------------------------------------
-- files：一个源文件一行。子表的父表。
-- UNIQUE(path) 给 writer 定位「这文件在不在库里」，不是给 Agent 按路径搜符号的
-- （按路径搜是 rg）。status 用 MAX(indexed_at) 判断索引是否过期。
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS files (
    id              INTEGER PRIMARY KEY,
    path            TEXT NOT NULL UNIQUE,       -- 相对 project_root；UNIQUE 供 upsert 定位
    content_hash    TEXT NOT NULL,              -- sha256；与库中一致则整文件 skipped
    language        TEXT NOT NULL,              -- gdscript / csharp / cpp（registry 写入）
    last_synced_by  TEXT NOT NULL DEFAULT 'watcher',  -- 'watcher' | 'sync_cmd'，只供调试，不是检索键
    indexed_at      REAL NOT NULL               -- epoch 秒；status 用 MAX(indexed_at) 判断是否过期
);

-- ---------------------------------------------------------------------------
-- symbols：定义位置。「take_damage 写在哪个文件第几行？」
--
-- 例子（player.gd，files.id=1）：
--   name=take_damage  kind=func  line=8  class_name=Player
--
-- 查询：先 WHERE name=?（idx_symbols_name），再 JOIN files ON files.id = symbols.file_id
-- 把 file_id 换成路径。同名可以有多行（跨文件 / 重载），所以 name 不是 UNIQUE。
-- idx_symbols_file 给 writer 按文件清符号用。
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS symbols (
    id          INTEGER PRIMARY KEY,
    file_id     INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,                  -- find-symbol 的检索键（精确匹配）
    kind        TEXT NOT NULL,                  -- class / func / signal / var / const / enum
    line        INTEGER NOT NULL,               -- 0-based
    end_line    INTEGER NOT NULL,
    class_name  TEXT,                           -- 所属类；顶层符号为 NULL（展示用，不是检索键）
    signature   TEXT                            -- 展示用签名原文，不参与 WHERE
);

CREATE INDEX IF NOT EXISTS idx_symbols_name ON symbols(name);    -- WHERE name=?
CREATE INDEX IF NOT EXISTS idx_symbols_file ON symbols(file_id); -- writer 按文件清符号

-- ---------------------------------------------------------------------------
-- edges：调用边。一行 = 源码里的一次调用，按箭头读：
--
--   from_symbol  ──kind=call──►  to_name     （写在第 line 行）
--   take_damage  ──────────────►  _die        player.gd:11
--   _die         ──────────────►  queue_free  player.gd:15
--
-- 「谁调用了 _die？」= WHERE to_name='_die'，读出 from_symbol（= take_damage）。
-- 「谁又调用了 take_damage？」= 再用这个名字当 to_name 查下一层。这就是递归 CTE。
--
-- to_name 是源码原文，不是 symbols.id。queue_free 是引擎函数，库里可以没有定义行。
-- kind: call | extends | preload。call-chain 只吃 call。
-- idx_edges_from 留给以后「这个函数调用了谁」的正向展开。
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS edges (
    id          INTEGER PRIMARY KEY,
    file_id     INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    from_symbol TEXT NOT NULL,                  -- 调用方在本文件里的名字
    to_name     TEXT NOT NULL,                  -- 被调用方原始文本；call-chain 的检索键
    line        INTEGER NOT NULL,
    kind        TEXT NOT NULL                   -- call / extends / preload
);

CREATE INDEX IF NOT EXISTS idx_edges_to_name ON edges(to_name);     -- 「谁调用了 X」
CREATE INDEX IF NOT EXISTS idx_edges_from ON edges(from_symbol);    -- 「X 调用了谁」（预留）

-- ---------------------------------------------------------------------------
-- classes：继承边。一行 = 一个类声明，按箭头读：
--
--   name    ──extends──►  base_name
--   Player  ────────────►  CharacterBody2D     player.gd:0
--   Boss    ────────────►  Player              （若另有 boss.gd）
--
-- 祖先链：WHERE name='Player' 得到 base_name，再拿它去 WHERE name=... 往上爬（递归 CTE）。
-- 子类列表：WHERE base_name='Player' → Boss。
--
-- 不复用 symbols(kind='class')：继承查询要沿「父类名字」爬，和「按名字找定义」不是一条路。
-- CharacterBody2D 是引擎类，库里没有它的 classes 行，祖先链在这一层自然停。
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS classes (
    id          INTEGER PRIMARY KEY,
    file_id     INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,                  -- class_name 声明；无则取文件名 stem
    base_name   TEXT,                           -- extends 的原始文本；子类查询的检索键
    line        INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_classes_name ON classes(name);       -- 起点 / 往上爬祖先
CREATE INDEX IF NOT EXISTS idx_classes_base ON classes(base_name);  -- 列出子类

-- SCENE_INDEX_TODO(step3-schema): 见 codebase_index/NEXT_STEP.md 第 7 节开头的「标记」说明。
-- 不要改 files / symbols / edges / classes。场景建表在 scene/schema.sql，由 connect_rw 额外执行。
