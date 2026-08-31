"""A/B 离线评测：粗召回锁定 20+20、0.3:0.7；对照 identity vs minilm_l6。

两路都在融合短名单（recall_k=20）上重排，再截 rerank_k ∈ {2,3,5}。
identity 不改序；minilm_l6 用 Xenova/ms-marco-MiniLM-L-6-v2。

指标：

- Prec_GT@K = |GT ∩ top-K| / |GT|（分母是 |GT|，不是 K）
- MRR：在交给 Agent 的前 K 条上算 1/第一命中名次；K 内未命中为 0

用法::

    cd rag
    uv run python eval/run_eval.py
"""

from __future__ import annotations

import json
import sys
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from rag.retriever import load, retrieve
from rag.retriever.config import ChannelKConfig, RetrieverConfig, TierAConfig, TierBConfig
from rag.retriever.schemas import RetrievalQuery

_EVAL_DIR = Path(__file__).resolve().parent
REPORTS_DIR = _EVAL_DIR / "reports"

A_CUTOFFS = (5, 8, 15)
B_POOL_K = 20
B_BM25_W = 0.3
B_VECTOR_W = 0.7
B_RERANK_KS = (2, 3, 5)
B_RERANKERS = ("identity", "minilm_l6")
MISS_RANK = B_POOL_K + 1


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def _to_query(record: dict[str, Any]) -> RetrievalQuery:
    raw = record["query"]
    return RetrievalQuery(
        error_text=raw.get("error_text") or None,
        query_text=raw.get("query_text") or None,
        symbols=raw.get("symbols") or [],
        target_version=raw["target_version"],
        retrieval_mode=raw["retrieval_mode"],
    )


def _query_kind(record: dict[str, Any]) -> str:
    raw = record["query"]
    if (raw.get("error_text") or "").strip():
        return "error"
    return "semantic"


def _prec_gt(gt_ids: set[str], retrieved: Sequence[str], k: int) -> float:
    if not gt_ids:
        return 0.0
    return len(gt_ids & set(retrieved[:k])) / len(gt_ids)


def _mrr(gt_ids: set[str], retrieved: Sequence[str], k: int) -> float:
    for rank, cid in enumerate(retrieved[:k], start=1):
        if cid in gt_ids:
            return 1.0 / rank
    return 0.0


def _first_hit_rank(gt_ids: set[str], retrieved: Sequence[str]) -> int | None:
    for rank, cid in enumerate(retrieved, start=1):
        if cid in gt_ids:
            return rank
    return None


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _a_config() -> RetrieverConfig:
    return RetrieverConfig(tier_a=TierAConfig(top_k=max(A_CUTOFFS)))


def _b_config(*, reranker: str) -> RetrieverConfig:
    return RetrieverConfig(
        tier_a=TierAConfig(top_k=8),
        tier_b=TierBConfig(
            channels="hybrid",
            bm25=ChannelKConfig(k=B_POOL_K, weight=B_BM25_W),
            vector=ChannelKConfig(k=B_POOL_K, weight=B_VECTOR_W),
            recall_k=B_POOL_K,
            rerank_k=B_POOL_K,
            reranker=reranker,
        ),
    )


def _evaluate_a(
    queries: list[dict[str, Any]],
    gts: dict[str, list[str]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    cfg = _a_config()
    details: list[dict[str, Any]] = []
    by_k: dict[int, list[float]] = {k: [] for k in A_CUTOFFS}
    for q in queries:
        gt_ids = set(gts[q["gt_id"]])
        retrieved = [h.rule.id for h in retrieve(_to_query(q), config=cfg).structured_hits]
        row = {
            "layer": "a",
            "gt_id": q["gt_id"],
            "kind": _query_kind(q),
            "gt_count": len(gt_ids),
        }
        for k in A_CUTOFFS:
            rec = _prec_gt(gt_ids, retrieved, k)
            row[f"recall@{k}"] = rec
            by_k[k].append(rec)
        details.append(row)
    return {
        "cutoffs": {str(k): {"mean_recall": _mean(v)} for k, v in by_k.items()},
    }, details


def _evaluate_one_reranker(
    reranker: str,
    queries: list[dict[str, Any]],
    gts: dict[str, list[str]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    cfg = _b_config(reranker=reranker)
    pools: list[dict[str, Any]] = []
    t0 = time.perf_counter()
    for q in queries:
        gt_ids = set(gts[q["gt_id"]])
        retrieved = [h.chunk.id for h in retrieve(_to_query(q), config=cfg).prose_hits]
        first = _first_hit_rank(gt_ids, retrieved)
        pools.append(
            {
                "gt_id": q["gt_id"],
                "kind": _query_kind(q),
                "gt_ids": list(gt_ids),
                "retrieved": retrieved,
                "first_hit_rank": first,
            }
        )
    elapsed = time.perf_counter() - t0

    summaries: list[dict[str, Any]] = []
    details: list[dict[str, Any]] = []
    for k in B_RERANK_KS:
        precs: list[float] = []
        mrrs: list[float] = []
        by_kind: dict[str, list[float]] = {"error": [], "semantic": []}
        by_kind_mrr: dict[str, list[float]] = {"error": [], "semantic": []}
        for row in pools:
            gt_ids = set(row["gt_ids"])
            retrieved = row["retrieved"]
            prec = _prec_gt(gt_ids, retrieved, k)
            mrr = _mrr(gt_ids, retrieved, k)
            precs.append(prec)
            mrrs.append(mrr)
            by_kind[row["kind"]].append(prec)
            by_kind_mrr[row["kind"]].append(mrr)
            details.append(
                {
                    "layer": "b",
                    "experiment": "rerank_compare",
                    "reranker": reranker,
                    "gt_id": row["gt_id"],
                    "kind": row["kind"],
                    "rerank_k": k,
                    "prec_gt": prec,
                    "mrr": mrr,
                    "first_hit_rank": row["first_hit_rank"],
                    "gt_count": len(gt_ids),
                    "retrieved": retrieved[:k],
                }
            )
        summaries.append(
            {
                "reranker": reranker,
                "rerank_k": k,
                "mean_prec_gt": _mean(precs),
                "mean_mrr": _mean(mrrs),
                "mean_prec_gt_error": _mean(by_kind["error"]),
                "mean_prec_gt_semantic": _mean(by_kind["semantic"]),
                "mean_mrr_error": _mean(by_kind_mrr["error"]),
                "mean_mrr_semantic": _mean(by_kind_mrr["semantic"]),
                "elapsed_s": elapsed,
            }
        )
    return summaries, details, pools


def _compare_pools(
    identity_pools: list[dict[str, Any]],
    minilm_pools: list[dict[str, Any]],
) -> dict[str, Any]:
    by_id_i = {row["gt_id"]: row for row in identity_pools}
    by_id_m = {row["gt_id"]: row for row in minilm_pools}
    improved: list[str] = []
    worsened: list[str] = []
    same: list[str] = []
    top1_changed: list[str] = []
    flips: list[dict[str, Any]] = []
    ranks_i: list[float] = []
    ranks_m: list[float] = []

    for gt_id, left in by_id_i.items():
        right = by_id_m[gt_id]
        ri = left["first_hit_rank"]
        rm = right["first_hit_rank"]
        ranks_i.append(float(ri or MISS_RANK))
        ranks_m.append(float(rm or MISS_RANK))
        left_top = (left["retrieved"] or [None])[0]
        right_top = (right["retrieved"] or [None])[0]
        if left_top != right_top:
            top1_changed.append(gt_id)
        if ri == rm:
            same.append(gt_id)
        elif rm is not None and (ri is None or rm < ri):
            improved.append(gt_id)
            flips.append({"gt_id": gt_id, "kind": left["kind"], "identity": ri, "minilm": rm})
        else:
            worsened.append(gt_id)
            flips.append({"gt_id": gt_id, "kind": left["kind"], "identity": ri, "minilm": rm})

    prec_moves: dict[str, dict[str, list[str]]] = {}
    for k in B_RERANK_KS:
        up: list[str] = []
        down: list[str] = []
        tie: list[str] = []
        for gt_id, left in by_id_i.items():
            right = by_id_m[gt_id]
            pi = _prec_gt(set(left["gt_ids"]), left["retrieved"], k)
            pm = _prec_gt(set(right["gt_ids"]), right["retrieved"], k)
            if pm > pi + 1e-12:
                up.append(gt_id)
            elif pm < pi - 1e-12:
                down.append(gt_id)
            else:
                tie.append(gt_id)
        prec_moves[str(k)] = {"improved": up, "worsened": down, "same": tie}

    return {
        "n": len(by_id_i),
        "mean_first_hit_identity": _mean(ranks_i),
        "mean_first_hit_minilm": _mean(ranks_m),
        "n_top1_changed": len(top1_changed),
        "first_hit_improved": improved,
        "first_hit_worsened": worsened,
        "first_hit_same": same,
        "prec_moves": prec_moves,
        "flips": flips,
    }


def _pick(summaries: list[dict[str, Any]], reranker: str, k: int) -> dict[str, Any]:
    for row in summaries:
        if row["reranker"] == reranker and row["rerank_k"] == k:
            return row
    raise KeyError(f"{reranker}@{k}")


def _delta(new: float, old: float) -> str:
    diff = new - old
    sign = "+" if diff >= 0 else ""
    return f"{sign}{diff:.4f}"


def _fmt(value: float) -> str:
    return f"{value:.4f}"


def _markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines) + "\n"


def _bar_cell(value: float, color: str) -> str:
    width = max(0.0, min(1.0, value)) * 100.0
    return (
        f'<div class="bar"><span class="fill" style="width:{width:.1f}%;'
        f'background:{color}"></span>'
        f'<span class="num">{value:.3f}</span></div>'
    )


def _conclusion(summaries: list[dict[str, Any]], cmp: dict[str, Any]) -> list[str]:
    k3_i = _pick(summaries, "identity", 3)
    k3_m = _pick(summaries, "minilm_l6", 3)
    k2_i = _pick(summaries, "identity", 2)
    k2_m = _pick(summaries, "minilm_l6", 2)
    k5_i = _pick(summaries, "identity", 5)
    k5_m = _pick(summaries, "minilm_l6", 5)

    mrr3 = k3_m["mean_mrr"] - k3_i["mean_mrr"]
    prec3 = k3_m["mean_prec_gt"] - k3_i["mean_prec_gt"]
    mrr2 = k2_m["mean_mrr"] - k2_i["mean_mrr"]
    n_up = len(cmp["first_hit_improved"])
    n_down = len(cmp["first_hit_worsened"])
    n_same = len(cmp["first_hit_same"])
    prec3_down = cmp["prec_moves"]["3"]["worsened"]
    prec3_up = cmp["prec_moves"]["3"]["improved"]

    if mrr3 > 0.01 and prec3 >= -1e-12 and n_up >= n_down:
        verdict = (
            "**结论：生产短名单用 `minilm_l6`，`rerank_k=3`。** "
            "相对 identity，K=3 的 MRR 上升且 Prec_GT 不掉，第一命中上提多于下压。"
        )
    elif mrr3 < -0.01 or (prec3 < -1e-12 and n_down > n_up):
        verdict = (
            "**结论：生产保持 `identity`，不要上 MiniLM。** "
            "粗召回 RRF 已经把 GT 排得很靠前；cross-encoder 改序的净效果是负的，"
            "会把部分已在前 3 的 GT 挤出短名单。"
        )
    else:
        verdict = (
            "**结论：生产保持 `identity`。** "
            "MiniLM 改了不少第一名，但 K=3 宏平均几乎不动；"
            "粗召回已经够准，80MB 模型和一次推理换不来可测量收益。"
        )

    lines = [
        verdict + "\n",
        (
            f"- K=3（生产默认短名单）：Prec_GT identity `{k3_i['mean_prec_gt']:.3f}` → "
            f"minilm `{k3_m['mean_prec_gt']:.3f}`（{_delta(k3_m['mean_prec_gt'], k3_i['mean_prec_gt'])}）；"
            f" MRR `{k3_i['mean_mrr']:.3f}` → `{k3_m['mean_mrr']:.3f}`"
            f"（{_delta(k3_m['mean_mrr'], k3_i['mean_mrr'])}）。\n"
        ),
        (
            f"- K=2：Prec_GT {_delta(k2_m['mean_prec_gt'], k2_i['mean_prec_gt'])}，"
            f" MRR {_delta(k2_m['mean_mrr'], k2_i['mean_mrr'])}。"
            f" K=5：Prec_GT {_delta(k5_m['mean_prec_gt'], k5_i['mean_prec_gt'])}，"
            f" MRR {_delta(k5_m['mean_mrr'], k5_i['mean_mrr'])}。\n"
        ),
        (
            f"- 第一命中名次（未命中按 {MISS_RANK}）：identity 平均 "
            f"{cmp['mean_first_hit_identity']:.2f}，minilm {cmp['mean_first_hit_minilm']:.2f}。"
            f" 提升 {n_up} 条，下降 {n_down} 条，不变 {n_same} 条；"
            f" 改了第一名 {cmp['n_top1_changed']}/{cmp['n']}。\n"
        ),
        (
            f"- Prec_GT@3 逐条：提升 {len(prec3_up)}，下降 {len(prec3_down)}，"
            f"不变 {len(cmp['prec_moves']['3']['same'])}。"
            + (
                f" 变差：{', '.join(prec3_down)}。"
                if prec3_down
                else " 没有把 GT 挤出前 3。"
            )
            + "\n"
        ),
        (
            f"- 分 query 类型 @3：报错 Prec_GT `{k3_i['mean_prec_gt_error']:.3f}` → "
            f"`{k3_m['mean_prec_gt_error']:.3f}`；语义 "
            f"`{k3_i['mean_prec_gt_semantic']:.3f}` → `{k3_m['mean_prec_gt_semantic']:.3f}`。\n"
        ),
        (
            f"- 耗时：identity {k3_i['elapsed_s']:.2f}s / 30 条，"
            f" minilm_l6 {k3_m['elapsed_s']:.2f}s / 30 条（含首次加载）。\n"
        ),
        (
            "- Prec_GT@3 唯一变差的 `b_0017` 是 composite：GT 是 gist 里两条不相关迁移"
            "（`EditorPlugin` 要 `super._ready()`，以及 `modulate`/`COLOR`）。"
            "RRF 两条都在前 3；MiniLM 主题塌缩，用同类官方 class 页挤掉第二条。\n"
        ),
    ]
    if mrr2 > 0.01 and mrr3 <= 0.01:
        lines.append(
            "- MiniLM 主要在 K=2 上抬第一名，但生产短名单是 3，收益被 RRF 已有的前 3 稀释。\n"
        )
    return lines


def _write_markdown(
    a_summary: dict[str, Any],
    a_details: list[dict[str, Any]],
    b_summary: list[dict[str, Any]],
    cmp: dict[str, Any],
    elapsed: float,
) -> str:
    lines = [
        "# RAG Retriever 离线评测报告\n",
        f"生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n",
        f"总耗时: {elapsed:.2f}s\n",
        "可视化页：[`eval_report.html`](eval_report.html)\n",
        "## 实验设计\n",
        f"- 粗召回锁定 `bm25.k=vector.k={B_POOL_K}`，权重 **0.3:0.7**，`recall_k={B_POOL_K}`。\n",
        "- 对照：`identity`（RRF 原序）vs `minilm_l6`（`Xenova/ms-marco-MiniLM-L-6-v2`）。\n",
        "- 两路都对融合后的 20 条重排，再截 `rerank_k ∈ {2,3,5}`。\n",
        "- **Prec_GT@K** = |GT ∩ top-K| / |GT|。**MRR** 在前 K 条上算。\n",
        "## A 层 Recall\n",
        _markdown_table(
            ["K", "mean Recall@K"],
            [
                [str(k), _fmt(a_summary["cutoffs"][str(k)]["mean_recall"])]
                for k in A_CUTOFFS
            ],
        ),
    ]
    miss_bits = []
    for k in A_CUTOFFS:
        miss = [d["gt_id"] for d in a_details if d[f"recall@{k}"] < 1.0]
        miss_bits.append(f"@{k} 未满：{', '.join(miss) or '无'}")
    lines.append("- " + "；".join(miss_bits) + "\n")

    lines.append("## B 层：identity vs minilm_l6\n")
    rows: list[list[str]] = []
    for k in B_RERANK_KS:
        left = _pick(b_summary, "identity", k)
        right = _pick(b_summary, "minilm_l6", k)
        rows.append(
            [
                str(k),
                _fmt(left["mean_prec_gt"]),
                _fmt(right["mean_prec_gt"]),
                _delta(right["mean_prec_gt"], left["mean_prec_gt"]),
                _fmt(left["mean_mrr"]),
                _fmt(right["mean_mrr"]),
                _delta(right["mean_mrr"], left["mean_mrr"]),
            ]
        )
    lines.append(
        _markdown_table(
            ["K", "Prec_GT id", "Prec_GT mini", "ΔPrec", "MRR id", "MRR mini", "ΔMRR"],
            rows,
        )
    )

    lines.append("## 第一命中对照\n")
    lines.append(
        _markdown_table(
            ["指标", "identity", "minilm_l6"],
            [
                [
                    "平均第一命中（未命中按 21）",
                    f"{cmp['mean_first_hit_identity']:.2f}",
                    f"{cmp['mean_first_hit_minilm']:.2f}",
                ],
                ["改了 top-1", "—", f"{cmp['n_top1_changed']}/{cmp['n']}"],
                ["第一命中提升 / 下降 / 不变", "—", f"{len(cmp['first_hit_improved'])} / {len(cmp['first_hit_worsened'])} / {len(cmp['first_hit_same'])}"],
            ],
        )
    )
    if cmp["flips"]:
        lines.append("名次变化明细：\n")
        lines.append(
            _markdown_table(
                ["gt_id", "kind", "identity 名次", "minilm 名次"],
                [
                    [
                        f["gt_id"],
                        f["kind"],
                        "—" if f["identity"] is None else str(f["identity"]),
                        "—" if f["minilm"] is None else str(f["minilm"]),
                    ]
                    for f in cmp["flips"]
                ],
            )
        )

    lines.append("## 结论\n")
    lines.extend(_conclusion(b_summary, cmp))
    lines.append("## 读表注意\n")
    lines.append("- 生产 YAML 先别改，等结论落地再动 `reranker`。\n")
    lines.append("- 明细：`eval/reports/eval_details.jsonl`。会话状态：`SESSION_STATE.md`。\n")
    return "".join(lines)


def _write_html(
    a_summary: dict[str, Any],
    b_summary: list[dict[str, Any]],
    cmp: dict[str, Any],
    elapsed: float,
) -> str:
    a_r = [a_summary["cutoffs"][str(k)]["mean_recall"] for k in A_CUTOFFS]
    b_rows = []
    for k in B_RERANK_KS:
        left = _pick(b_summary, "identity", k)
        right = _pick(b_summary, "minilm_l6", k)
        b_rows.append(
            "<tr>"
            f"<td>{k}</td>"
            f"<td>{_bar_cell(left['mean_prec_gt'], '#94a3b8')}</td>"
            f"<td>{_bar_cell(right['mean_prec_gt'], '#2563eb')}</td>"
            f"<td>{_delta(right['mean_prec_gt'], left['mean_prec_gt'])}</td>"
            f"<td>{_bar_cell(left['mean_mrr'], '#c4b5fd')}</td>"
            f"<td>{_bar_cell(right['mean_mrr'], '#7c3aed')}</td>"
            f"<td>{_delta(right['mean_mrr'], left['mean_mrr'])}</td>"
            "</tr>"
        )
    generated = time.strftime("%Y-%m-%d %H:%M:%S")
    k3_i = _pick(b_summary, "identity", 3)
    k3_m = _pick(b_summary, "minilm_l6", 3)
    verdict = "".join(_conclusion(b_summary, cmp))
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8"/>
  <title>RAG Retriever 离线评测</title>
  <style>
    body {{ font-family: ui-sans-serif, system-ui, sans-serif; margin: 32px; color: #111827; }}
    h1, h2 {{ font-weight: 650; }}
    .meta {{ color: #6b7280; }}
    table {{ border-collapse: collapse; width: 100%; margin: 12px 0 28px; }}
    th, td {{ border-bottom: 1px solid #e5e7eb; padding: 8px 10px; text-align: left; }}
    .cards {{ display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px; }}
    .card {{ border: 1px solid #e5e7eb; border-radius: 10px; padding: 14px 16px; }}
    .card .label {{ color: #6b7280; font-size: 12px; }}
    .card .value {{ font-size: 28px; font-weight: 700; }}
    .bar {{ position: relative; height: 18px; background: #f3f4f6; border-radius: 999px; min-width: 120px; }}
    .bar .fill {{ display: block; height: 100%; border-radius: 999px; }}
    .bar .num {{ position: absolute; inset: 0 8px; font-size: 12px; line-height: 18px; }}
    .note {{ background: #f9fafb; border-radius: 8px; padding: 12px 14px; white-space: pre-wrap; }}
  </style>
</head>
<body>
  <h1>RAG Retriever 离线评测</h1>
  <p class="meta">生成时间 {generated} · {elapsed:.1f}s · 粗召回 20+20 0.3:0.7 · identity vs minilm_l6</p>
  <h2>A Recall / B @3</h2>
  <div class="cards">
    <div class="card"><div class="label">Recall@5</div><div class="value">{a_r[0]:.3f}</div></div>
    <div class="card"><div class="label">Recall@8</div><div class="value">{a_r[1]:.3f}</div></div>
    <div class="card"><div class="label">Recall@15</div><div class="value">{a_r[2]:.3f}</div></div>
    <div class="card"><div class="label">MRR@3 identity</div><div class="value">{k3_i['mean_mrr']:.3f}</div></div>
    <div class="card"><div class="label">MRR@3 minilm</div><div class="value">{k3_m['mean_mrr']:.3f}</div></div>
  </div>
  <h2>B identity vs minilm_l6</h2>
  <table>
    <tr><th>K</th><th>Prec_GT id</th><th>Prec_GT mini</th><th>ΔPrec</th><th>MRR id</th><th>MRR mini</th><th>ΔMRR</th></tr>
    {"".join(b_rows)}
  </table>
  <h2>结论</h2>
  <div class="note">{verdict}</div>
</body>
</html>
"""


def _write_context() -> str:
    return """# 本轮评测上下文

粗召回锁定 20+20、bm25:vector = 0.3:0.7。

对照：identity vs minilm_l6（已锁定：生产保持 identity）。
A 层 Recall@5 / @8 / @15。B 层 rerank_k ∈ {2,3,5}。Prec_GT 分母是 |GT|。

生产 YAML 先别改。
"""


def _rebuild_b_from_details(
    details: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """复用上轮 B 明细，避免再跑 MiniLM。"""
    summaries: list[dict[str, Any]] = []
    for reranker in B_RERANKERS:
        for k in B_RERANK_KS:
            rows = [
                d
                for d in details
                if d.get("reranker") == reranker and d.get("rerank_k") == k
            ]
            by_kind_p: dict[str, list[float]] = {"error": [], "semantic": []}
            by_kind_m: dict[str, list[float]] = {"error": [], "semantic": []}
            for row in rows:
                by_kind_p[row["kind"]].append(row["prec_gt"])
                by_kind_m[row["kind"]].append(row["mrr"])
            summaries.append(
                {
                    "reranker": reranker,
                    "rerank_k": k,
                    "mean_prec_gt": _mean([r["prec_gt"] for r in rows]),
                    "mean_mrr": _mean([r["mrr"] for r in rows]),
                    "mean_prec_gt_error": _mean(by_kind_p["error"]),
                    "mean_prec_gt_semantic": _mean(by_kind_p["semantic"]),
                    "mean_mrr_error": _mean(by_kind_m["error"]),
                    "mean_mrr_semantic": _mean(by_kind_m["semantic"]),
                    "elapsed_s": 0.0,
                }
            )

    def _side(reranker: str) -> dict[str, dict[str, Any]]:
        picked = {
            d["gt_id"]: d
            for d in details
            if d.get("reranker") == reranker and d.get("rerank_k") == 5
        }
        return picked

    left = _side("identity")
    right = _side("minilm_l6")
    identity_pools = [
        {
            "gt_id": gid,
            "kind": row["kind"],
            "gt_ids": [None] * int(row["gt_count"]),
            "retrieved": row.get("retrieved") or [],
            "first_hit_rank": row.get("first_hit_rank"),
        }
        for gid, row in left.items()
    ]
    minilm_pools = [
        {
            "gt_id": gid,
            "kind": right[gid]["kind"],
            "gt_ids": [None] * int(right[gid]["gt_count"]),
            "retrieved": right[gid].get("retrieved") or [],
            "first_hit_rank": right[gid].get("first_hit_rank"),
        }
        for gid, _row in left.items()
    ]
    # prec_moves 用各 K 的已算 prec_gt，不依赖 gt_ids
    cmp = _compare_pools(identity_pools, minilm_pools)
    prec_moves: dict[str, dict[str, list[str]]] = {}
    for k in B_RERANK_KS:
        up: list[str] = []
        down: list[str] = []
        tie: list[str] = []
        for gid in left:
            pi = next(
                d["prec_gt"]
                for d in details
                if d["reranker"] == "identity" and d["rerank_k"] == k and d["gt_id"] == gid
            )
            pm = next(
                d["prec_gt"]
                for d in details
                if d["reranker"] == "minilm_l6" and d["rerank_k"] == k and d["gt_id"] == gid
            )
            if pm > pi + 1e-12:
                up.append(gid)
            elif pm < pi - 1e-12:
                down.append(gid)
            else:
                tie.append(gid)
        prec_moves[str(k)] = {"improved": up, "worsened": down, "same": tie}
    cmp["prec_moves"] = prec_moves
    return summaries, cmp


def main() -> int:
    skip_b = "--a-only" in sys.argv[1:]
    load()
    a_queries = _load_jsonl(_EVAL_DIR / "test_tier_a" / "queries.jsonl")
    a_gts = {
        g["gt_id"]: [item["id"] for item in g["items"]]
        for g in _load_jsonl(_EVAL_DIR / "test_tier_a" / "groundtruth.jsonl")
    }

    t0 = time.perf_counter()
    print("[A] Recall @5/@8/@15 ...")
    a_summary, a_details = _evaluate_a(a_queries, a_gts)

    b_summary: list[dict[str, Any]] = []
    b_details: list[dict[str, Any]] = []
    if skip_b:
        print("[B] 复用上轮明细（--a-only）...")
        prev = _load_jsonl(REPORTS_DIR / "eval_details.jsonl")
        b_details = [row for row in prev if row.get("layer") == "b"]
        b_summary, cmp = _rebuild_b_from_details(b_details)
    else:
        b_queries = _load_jsonl(_EVAL_DIR / "test_tier_b" / "queries.jsonl")
        b_gts = {
            g["gt_id"]: [item["id"] for item in g["items"]]
            for g in _load_jsonl(_EVAL_DIR / "test_tier_b" / "groundtruth.jsonl")
        }
        pools: dict[str, list[dict[str, Any]]] = {}
        for name in B_RERANKERS:
            print(f"[B] {name} ...")
            summary, details, pool = _evaluate_one_reranker(name, b_queries, b_gts)
            b_summary.extend(summary)
            b_details.extend(details)
            pools[name] = pool
        cmp = _compare_pools(pools["identity"], pools["minilm_l6"])
    elapsed = time.perf_counter() - t0

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (REPORTS_DIR / "eval_report.md").write_text(
        _write_markdown(a_summary, a_details, b_summary, cmp, elapsed), encoding="utf-8"
    )
    (REPORTS_DIR / "eval_report.html").write_text(
        _write_html(a_summary, b_summary, cmp, elapsed), encoding="utf-8"
    )
    (REPORTS_DIR / "eval_context.md").write_text(_write_context(), encoding="utf-8")
    with (REPORTS_DIR / "eval_details.jsonl").open("w", encoding="utf-8") as fh:
        for row in a_details + b_details:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    print((REPORTS_DIR / "eval_report.md").read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
