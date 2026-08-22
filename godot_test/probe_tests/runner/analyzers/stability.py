"""通用 stability：把 repeat 塌陷成三元组记录。

对每个 (project, command, cache_state)，比较该三元组下全部 repeat 的
stderr（error lines）与 stdout 行集合（不考虑顺序）。集合不同则为 false。
再取各 repeat 都出现过的错误行，按各自日志中的相对顺序比较；顺序不同则为 false。

不写 signature-rules.draft.yaml，不下 BG-DRIFT / CONFIRMED，不填 reports/README.md。
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from .base import Evaluation, register

ESCALATE_PROMPT = (
    "本文件只报告行集合是否相同、公共错误行顺序是否相同。"
    "字段抹除规格仍按 reports/README.md §0.4 由人/模型另写，不由本 analyzer 决定。"
    "Fake 产物不得当已确认结论。"
)

_FILE_COMMENT = (
    "repeat 塌陷：每个 (project, command, cache_state) 一条。"
    "error_lines_set_same / stdout_lines_set_same 按行集合（忽略顺序）比较各 repeat；"
    "不同则为 false。common_error_order_same 只保留各 repeat 都出现的错误行，"
    "再比相对顺序；不同则为 false。"
)


def _cache_value(measurement) -> str:
    cache = measurement.cache_state
    return cache.value if hasattr(cache, "value") else str(cache)


def _triple_key(shot) -> tuple:
    m = shot.raw.measurement
    return (m.project, m.command, _cache_value(m))


def _nonempty_lines(text: str) -> list:
    return [line for line in (text or "").splitlines() if line.strip()]


def _shot_logs(shot) -> list:
    return list(shot.log_paths)


def _sets_same(seqs: list) -> bool:
    if len(seqs) < 2:
        return True
    first = set(seqs[0])
    return all(set(seq) == first for seq in seqs[1:])


def _common_order_same(seqs: list) -> bool:
    """过滤掉并非所有 repeat 都有的行，再比剩下行的相对顺序。"""
    if len(seqs) < 2:
        return True
    common = set(seqs[0])
    for seq in seqs[1:]:
        common &= set(seq)
    filtered = [[line for line in seq if line in common] for seq in seqs]
    return all(item == filtered[0] for item in filtered[1:])


def _only_in_some(seqs: list) -> list:
    sets = [set(seq) for seq in seqs]
    if not sets:
        return []
    union = set()
    intersection = set(sets[0])
    for item in sets:
        union |= item
        intersection &= item
    return sorted(union - intersection)


def _collapse_triple(shots: list) -> dict:
    shots = sorted(shots, key=lambda s: s.raw.measurement.repeat_idx)
    sample = shots[0].raw.measurement
    logs = []
    for shot in shots:
        logs.extend(_shot_logs(shot))

    error_seqs = [_nonempty_lines(shot.raw.stderr) for shot in shots]
    stdout_seqs = [_nonempty_lines(shot.raw.stdout) for shot in shots]

    error_lines_set_same = _sets_same(error_seqs)
    stdout_lines_set_same = _sets_same(stdout_seqs)
    common_error_order_same = _common_order_same(error_seqs)

    record = {
        "_comment": _FILE_COMMENT,
        "_logs": sorted(set(logs)),
        "measurement": {
            "project": sample.project,
            "command": sample.command,
            "cache_state": _cache_value(sample),
        },
        "repeats": [s.raw.measurement.repeat_idx for s in shots],
        "error_lines_set_same": error_lines_set_same,
        "stdout_lines_set_same": stdout_lines_set_same,
        "common_error_order_same": common_error_order_same,
    }
    if not error_lines_set_same:
        record["error_lines_only_in_some_repeats"] = _only_in_some(error_seqs)
    if not stdout_lines_set_same:
        record["stdout_lines_only_in_some_repeats"] = _only_in_some(stdout_seqs)
    return record


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=False, default=str),
        encoding="utf-8",
    )


def evaluate(
    *,
    shots: list = None,
    out_dir=None,
    run_id: str = "",
    run_dir=None,
    fake: bool = False,
    **_ignored,
) -> Evaluation:
    shots = list(shots or [])
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    by_triple = defaultdict(list)
    for shot in shots:
        by_triple[_triple_key(shot)].append(shot)

    items = [_collapse_triple(group) for _, group in sorted(by_triple.items())]

    doc = {
        "_comment": _FILE_COMMENT,
        "_escalate": {"prompt": ESCALATE_PROMPT},
        "_fake": fake,
        "_logs": "各 item._logs 列出该三元组用到的 stdout.log / stderr.log（相对 artifacts/<run-id>/）",
        "run_id": run_id,
        "run_dir": str(run_dir) if run_dir else "",
        "items": items,
    }
    _write_json(out_dir / "vertical.json", doc)

    stale = out_dir / "horizontal.json"
    if stale.is_file():
        stale.unlink()

    readme = "\n".join(
        [
            "stability：repeat 塌陷报告（vertical.json）。",
            "",
            "每个 (project, command, cache_state) 一条。",
            "error_lines_set_same / stdout_lines_set_same：各 repeat 行集合是否相同（忽略顺序）；不同为 false。",
            "common_error_order_same：只保留各 repeat 都有的错误行，再比顺序；不同为 false。",
            "",
            "escalate:",
            ESCALATE_PROMPT,
            "",
        ]
    )
    (out_dir / "README.txt").write_text(readme, encoding="utf-8")

    return Evaluation(
        status="EXTRACTED",
        aggregation="repeat_collapse",
        details={
            "out_dir": str(out_dir),
            "triples": len(items),
            "shots": len(shots),
            "fake": fake,
            "all_sets_and_order_same": all(
                item["error_lines_set_same"]
                and item["stdout_lines_set_same"]
                and item["common_error_order_same"]
                for item in items
            )
            if items
            else True,
        },
    )


register("stability", evaluate)
