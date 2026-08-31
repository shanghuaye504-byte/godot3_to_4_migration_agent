"""生成 A/B 层检索评测集。

从 ``artifacts/rules.db`` 和 ``artifacts/corpora/default/corpus.lance`` 中随机抽样，
生成 groundtruth 与对应的自然语言查询。查询面向 RAG 服务（``RetrievalQuery``），
不是 SQL。

输出结构::

    eval/test_tier_a/
        groundtruth.jsonl   # 30 条 groundtruth
        queries.jsonl       # 30 条 query -> gt_id 配对
    eval/test_tier_b/
        groundtruth.jsonl
        queries.jsonl

每条 groundtruth 包含 ``type``（single/composite）和 ``items`` 列表。
组合样本的 ``items`` 长度为 2~5。

随机种子固定为 42，保证可复现。

注意：``test_tier_a/`` 与 ``test_tier_b/`` 的 queries 都已人工正向对齐。
再跑会把 ``new_symbol`` 写回 A 层 ``symbols``，并用 heading 模板覆盖 B 层。
详见 ``eval/docs/generation_notes.md``。
"""

from __future__ import annotations

import argparse
import json
import random
import sqlite3
import sys
from pathlib import Path
from typing import Any

_RAG_ROOT = Path(__file__).resolve().parent.parent
RULES_DB = _RAG_ROOT / "artifacts" / "rules.db"
CORPUS_DIR = _RAG_ROOT / "artifacts" / "corpora" / "default"

A_OUT = Path(__file__).resolve().parent / "test_tier_a"
B_OUT = Path(__file__).resolve().parent / "test_tier_b"

TARGET_VERSION = "4.7.1"
SEED = 42

SINGLE_COUNT = 10
COMPOSITE_COUNT = 20
COMPOSITE_MIN = 2
COMPOSITE_MAX = 5


def _load_rules(limit: int | None = None) -> list[dict[str, Any]]:
    conn = sqlite3.connect(RULES_DB)
    conn.row_factory = sqlite3.Row
    sql = """
        SELECT id, old_symbol, new_symbol, owner, symbol_kind, change,
               warning, snippet, source, source_url, agent_action,
               since_version, since_version_code
        FROM migration_rules
        WHERE detection_method IN ('agent_retrieval', 'agent_retrieval_or_escalate')
          AND old_symbol IS NOT NULL
          AND change IN ('rename', 'remove', 'signature', 'type', 'move',
                         'replace', 'behavior', 'rewrite')
        ORDER BY id
    """
    rows = [dict(r) for r in conn.execute(sql)]
    conn.close()
    if limit:
        rows = rows[:limit]
    return rows


def _load_chunks(limit: int | None = None) -> list[dict[str, Any]]:
    import lancedb

    db = lancedb.connect(str(CORPUS_DIR))
    tbl = db.open_table("corpus")
    rows = tbl.search().limit(10000).to_list()
    rows = [
        {
            "id": str(r["id"]),
            "text": str(r["text"]),
            "heading_path": list(r.get("heading_path") or []),
            "related_symbols": list(r.get("related_symbols") or []),
            "source": str(r.get("source") or ""),
            "source_file": str(r.get("source_file") or ""),
            "source_url": r.get("source_url"),
            "since_version": r.get("since_version"),
            "since_version_code": int(r.get("since_version_code") or 0),
        }
        for r in rows
    ]
    if limit:
        rows = rows[:limit]
    return rows


def _pick_composite_sizes(total_items: int, n_groups: int, min_size: int, max_size: int) -> list[int]:
    """把 total_items 分成 n_groups 组，每组大小在 [min_size, max_size] 之间。"""
    if n_groups * min_size > total_items or n_groups * max_size < total_items:
        raise ValueError(
            f"无法把 {total_items} 条分成 {n_groups} 组，每组 {min_size}~{max_size} 条"
        )
    sizes = [min_size] * n_groups
    remaining = total_items - sum(sizes)
    idx = 0
    while remaining > 0:
        add = min(max_size - sizes[idx], remaining)
        sizes[idx] += add
        remaining -= add
        idx = (idx + 1) % n_groups
    random.shuffle(sizes)
    return sizes


def _group_by_key(rows: list[dict[str, Any]], key: str, sizes: list[int]) -> list[list[dict[str, Any]]]:
    """按 key 分组，从每组中抽取指定数量的行，形成组合样本。"""
    buckets: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        buckets.setdefault(str(r.get(key) or "unknown"), []).append(r)

    groups: list[list[dict[str, Any]]] = []
    used_ids: set[str] = set()
    for size in sizes:
        candidates = [r for r in rows if r["id"] not in used_ids]
        if len(candidates) < size:
            candidates = [r for r in rows if r["id"] not in used_ids] or rows
        group = candidates[:size]
        for r in group:
            used_ids.add(r["id"])
        groups.append(group)
    return groups


def _a_item_to_dict(rule: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": rule["id"],
        "old_symbol": rule["old_symbol"],
        "new_symbol": rule["new_symbol"],
        "owner": rule["owner"],
        "symbol_kind": rule["symbol_kind"],
        "change": rule["change"],
        "warning": rule["warning"],
        "snippet": rule["snippet"],
        "source": rule["source"],
        "source_url": rule["source_url"],
        "agent_action": rule["agent_action"],
        "since_version": rule["since_version"],
    }


def _b_item_to_dict(chunk: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": chunk["id"],
        "text": chunk["text"],
        "heading_path": chunk["heading_path"],
        "related_symbols": chunk["related_symbols"],
        "source": chunk["source"],
        "source_file": chunk["source_file"],
        "source_url": chunk["source_url"],
        "since_version": chunk["since_version"],
    }


def _a_error_text(rule: dict[str, Any]) -> str:
    """根据规则字段生成类似 Godot 报错的自然语言文本。"""
    old = rule.get("old_symbol") or ""
    new = rule.get("new_symbol") or ""
    kind = rule.get("symbol_kind") or ""
    owner = rule.get("owner") or ""
    base = owner or "Node"

    if kind == "class":
        return f"Could not find type '{old}' in the current scope."
    if kind in {"method", "function"}:
        return f"Invalid call. Nonexistent function '{old}' in base '{base}'."
    if kind == "property":
        return f"Invalid set index '{old}' (on base: '{base}') with value of type ..."
    if kind == "signal":
        return f"Cannot find signal '{old}' in '{base}'."
    if kind == "constant":
        return f"Identifier '{old}' is not declared in the current scope."
    if kind == "singleton":
        return f"Parser Error: Identifier '{old}' is not a singleton."
    if kind == "project_setting":
        return f"Project setting '{old}' is not recognized in Godot 4."
    if old and new:
        return f"Migration error: '{old}' is no longer available; use '{new}' instead."
    if old:
        return f"Invalid call. Nonexistent function '{old}'."
    if new:
        return f"Identifier '{new}' not found after migration."
    return "Migration error: unknown API change."


def _a_query_for_single(rule: dict[str, Any], target_version: str) -> dict[str, Any]:
    symbols = []
    for s in [rule.get("old_symbol"), rule.get("new_symbol")]:
        if s and s not in symbols:
            symbols.append(s)
    return {
        "error_text": _a_error_text(rule),
        "symbols": symbols,
        "target_version": target_version,
        "retrieval_mode": "exact_only",
    }


def _a_query_for_composite(rules: list[dict[str, Any]], target_version: str) -> dict[str, Any]:
    error_bits = [_a_error_text(r) for r in rules]
    symbols = []
    for r in rules:
        for s in [r.get("old_symbol"), r.get("new_symbol")]:
            if s and s not in symbols:
                symbols.append(s)
    return {
        "error_text": " ".join(error_bits),
        "symbols": symbols[:10],
        "target_version": target_version,
        "retrieval_mode": "exact_only",
    }


def _b_clean_token(text: str) -> str | None:
    """清理 heading/符号，去掉 doc 引用标记和标点。"""
    import re

    # 去掉 :ref:`...` 或 <class_...> / <doc_...>
    text = re.sub(r":ref:`([^`]+)`", r"\1", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = text.strip("`[]<>\"' ")
    # 只保留看起来像标识符/短语的 token
    if not text:
        return None
    lower = text.lower()
    noise = {
        "breaking changes",
        "behavior changes",
        "",
        ":",
        "#",
        "region",
        "endregion",
    }
    if text in noise or lower.startswith("doc_") or "_doc_" in lower:
        return None
    if not re.search(r"[A-Za-z0-9_]", text):
        return None
    return text


def _b_topic(chunk: dict[str, Any]) -> str:
    """从 chunk 中提取一个简短、自然的主题词。"""
    heading = chunk.get("heading_path") or []
    for h in reversed(heading):
        clean = _b_clean_token(h)
        if clean:
            return clean.replace("_", " ")
    syms = chunk.get("related_symbols") or []
    for s in syms:
        clean = _b_clean_token(s)
        if clean and " " not in clean:
            return clean.replace("_", " ")
    return "this migration topic"


def _b_query_for_single(chunk: dict[str, Any], target_version: str) -> dict[str, Any]:
    topic = _b_topic(chunk)
    templates = [
        f"How do I migrate {topic} from Godot 3 to Godot 4?",
        f"What changed with {topic} in Godot 4?",
        f"Explain the Godot 4 change for {topic}.",
        f"My project breaks on {topic} after upgrading to Godot 4. What should I do?",
        f"Documentation for migrating {topic} to Godot 4.",
    ]
    symbols = []
    for s in chunk.get("related_symbols") or []:
        clean = _b_clean_token(s)
        if clean and " " not in clean and clean not in symbols:
            symbols.append(clean)
    return {
        "error_text": "",
        "query_text": random.choice(templates),
        "symbols": symbols[:5],
        "target_version": target_version,
        "retrieval_mode": "semantic_only",
    }


def _b_query_for_composite(chunks: list[dict[str, Any]], target_version: str) -> dict[str, Any]:
    topics = [_b_topic(c) for c in chunks]
    topic_text = ", ".join(topics[:3])
    templates = [
        f"How do I migrate {topic_text} and related systems from Godot 3 to Godot 4?",
        f"What are the breaking changes around {topic_text} in Godot 4?",
        f"My Godot 3 project needs updates for {topic_text}. Where is the guidance?",
        f"Explain Godot 4 migration for {topic_text} together.",
    ]
    symbols = []
    for c in chunks:
        for s in c.get("related_symbols") or []:
            clean = _b_clean_token(s)
            if clean and " " not in clean and clean not in symbols:
                symbols.append(clean)
    return {
        "error_text": "",
        "query_text": random.choice(templates),
        "symbols": symbols[:5],
        "target_version": target_version,
        "retrieval_mode": "semantic_only",
    }


def _build_a_set(target_version: str, seed: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rules = _load_rules()
    random.seed(seed)
    random.shuffle(rules)

    single_rules = rules[:SINGLE_COUNT]
    remaining = rules[SINGLE_COUNT:]

    composite_total = SINGLE_COUNT * 1 + COMPOSITE_COUNT * ((COMPOSITE_MIN + COMPOSITE_MAX) // 2)
    composite_total = min(composite_total, len(remaining))
    sizes = _pick_composite_sizes(
        composite_total, COMPOSITE_COUNT, COMPOSITE_MIN, COMPOSITE_MAX
    )

    groups = _group_by_key(remaining, "symbol_kind", sizes)

    groundtruth: list[dict[str, Any]] = []
    queries: list[dict[str, Any]] = []
    idx = 0
    for rule in single_rules:
        gt_id = f"a_{idx:04d}"
        groundtruth.append(
            {
                "gt_id": gt_id,
                "type": "single",
                "target_version": TARGET_VERSION,
                "items": [_a_item_to_dict(rule)],
            }
        )
        queries.append({"gt_id": gt_id, "query": _a_query_for_single(rule, target_version)})
        idx += 1

    for group in groups:
        gt_id = f"a_{idx:04d}"
        groundtruth.append(
            {
                "gt_id": gt_id,
                "type": "composite",
                "target_version": target_version,
                "items": [_a_item_to_dict(r) for r in group],
            }
        )
        queries.append({"gt_id": gt_id, "query": _a_query_for_composite(group, target_version)})
        idx += 1

    return groundtruth, queries


def _build_b_set(target_version: str, seed: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    chunks = _load_chunks()
    random.seed(seed + 1)
    random.shuffle(chunks)

    single_chunks = chunks[:SINGLE_COUNT]
    remaining = chunks[SINGLE_COUNT:]

    composite_total = SINGLE_COUNT * 1 + COMPOSITE_COUNT * ((COMPOSITE_MIN + COMPOSITE_MAX) // 2)
    composite_total = min(composite_total, len(remaining))
    sizes = _pick_composite_sizes(
        composite_total, COMPOSITE_COUNT, COMPOSITE_MIN, COMPOSITE_MAX
    )

    groups = _group_by_key(remaining, "source_file", sizes)

    groundtruth: list[dict[str, Any]] = []
    queries: list[dict[str, Any]] = []
    idx = 0
    for chunk in single_chunks:
        gt_id = f"b_{idx:04d}"
        groundtruth.append(
            {
                "gt_id": gt_id,
                "type": "single",
                "target_version": target_version,
                "items": [_b_item_to_dict(chunk)],
            }
        )
        queries.append({"gt_id": gt_id, "query": _b_query_for_single(chunk, target_version)})
        idx += 1

    for group in groups:
        gt_id = f"b_{idx:04d}"
        groundtruth.append(
            {
                "gt_id": gt_id,
                "type": "composite",
                "target_version": target_version,
                "items": [_b_item_to_dict(c) for c in group],
            }
        )
        queries.append({"gt_id": gt_id, "query": _b_query_for_composite(group, target_version)})
        idx += 1

    return groundtruth, queries


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="生成 A/B 层检索评测集")
    parser.add_argument(
        "--target-version",
        default=TARGET_VERSION,
        help=f"目标 Godot 版本（默认 {TARGET_VERSION}）",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=SEED,
        help=f"随机种子（默认 {SEED}）",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).resolve().parent,
        help="评测集输出根目录（默认 eval/）",
    )
    args = parser.parse_args(argv)

    target_version = args.target_version
    seed = args.seed

    print(f"加载 A 层规则库: {RULES_DB}")
    a_gt, a_q = _build_a_set(target_version, seed)
    print(f"生成 A 层: {len(a_gt)} 条 groundtruth / {len(a_q)} 条查询")

    print(f"加载 B 层语料库: {CORPUS_DIR}")
    b_gt, b_q = _build_b_set(target_version, seed)
    print(f"生成 B 层: {len(b_gt)} 条 groundtruth / {len(b_q)} 条查询")

    out_a = args.out / "test_tier_a"
    out_b = args.out / "test_tier_b"
    _write_jsonl(out_a / "groundtruth.jsonl", a_gt)
    _write_jsonl(out_a / "queries.jsonl", a_q)
    _write_jsonl(out_b / "groundtruth.jsonl", b_gt)
    _write_jsonl(out_b / "queries.jsonl", b_q)

    print(f"输出:\n  {out_a}\n  {out_b}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
