-- L3：场景旁路表。由 connect_rw 在 schema.sql 之后执行。
-- 不并进 files / symbols / edges / classes。列定义以 NEXT_STEP.md 第 4.2 节为准。
-- scene_files / scene_nodes / scene_refs 的 line 都是 1-based；symbols.line 仍是 0-based。

CREATE TABLE IF NOT EXISTS scene_files(
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

CREATE TABLE IF NOT EXISTS scene_nodes(
  path TEXT, node_path TEXT, name TEXT, type TEXT, parent_path TEXT,
  script_ext_id TEXT, instance_ext_id TEXT, is_placeholder INT,
  in_unresolved_subtree INT,  -- 弃权用的是这一列，不是 subject 字符串
  line INT,                   -- 1-based
  PRIMARY KEY(path, node_path)
);

CREATE TABLE IF NOT EXISTS scene_ext(
  path TEXT, ext_id TEXT, type TEXT, uid TEXT,
  ref_path TEXT, resolved_file TEXT,   -- NULL = 解析不到
  line INT,
  PRIMARY KEY(path, ext_id)
);

CREATE TABLE IF NOT EXISTS scene_sub(
  path TEXT, sub_id TEXT, type TEXT, line INT,
  PRIMARY KEY(path, sub_id)
);

CREATE TABLE IF NOT EXISTS scene_conn(
  path TEXT, signal TEXT, from_path TEXT, to_path TEXT, method TEXT,
  line INT
);

CREATE TABLE IF NOT EXISTS scene_refs(
  path TEXT, line INT, col INT, kind TEXT,
  symbol TEXT, node_path TEXT, target_file TEXT, detail TEXT
);
CREATE INDEX IF NOT EXISTS idx_refs_symbol ON scene_refs(symbol);
CREATE INDEX IF NOT EXISTS idx_refs_target ON scene_refs(target_file);
CREATE INDEX IF NOT EXISTS idx_refs_kind   ON scene_refs(kind, symbol);

-- 只在「冻结 baseline」时写一次，之后只读
CREATE TABLE IF NOT EXISTS scene_baseline(
  fingerprint TEXT PRIMARY KEY,
  path TEXT, code TEXT, tier TEXT, subject TEXT
);

CREATE TABLE IF NOT EXISTS scene_member_baseline(
  script_path TEXT,          -- 相对 project_root 的 .gd
  kind TEXT,                 -- 本阶段只有 class | func
  name TEXT,
  PRIMARY KEY(script_path, kind, name)
);
