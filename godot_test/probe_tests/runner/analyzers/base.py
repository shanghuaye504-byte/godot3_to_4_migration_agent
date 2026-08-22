"""Analyzer 基类接口。

consume 事后从 artifacts 重建的 RawResult（LoadedShot），按 YAML 的
analysis.type 分派。产物写 report/<phase>/<N>/，不是 artifacts/。
只由 Analyzer.py（python Analyzer.py --path）调用；kernel 不引用本模块。

8 类 analysis.type 通过 register()/dispatch() 分派；本轮只有 "stability"
真正 register 了实现。其余类型 dispatch 时回退到 status="NOT_IMPLEMENTED"
的占位形状，由 Analyzer.py 写入 report/.../dispatch.json。
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Callable, Optional

import yaml


@dataclasses.dataclass
class Evaluation:
    status: str
    aggregation: str
    details: dict = dataclasses.field(default_factory=dict)


@dataclasses.dataclass(frozen=True)
class AnnotationMarker:
    """镜像 annotations/phase1/NP-AUTOLOAD.yaml 的真实字段形状。"""

    marker_id: str
    file: str
    intent: str = ""
    match: dict = dataclasses.field(default_factory=dict)
    filterable: Optional[bool] = None
    expect_silent: bool = False


def load_annotations(path: Path) -> list:
    path = Path(path)
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    markers = data.get("markers", [])
    return [
        AnnotationMarker(
            marker_id=m["id"],
            file=m.get("file", ""),
            intent=m.get("intent", ""),
            match=m.get("match", {}),
            filterable=m.get("filterable"),
            expect_silent=bool(m.get("expect_silent", False)),
        )
        for m in markers
    ]


SHAPE_BY_TYPE = {
    "baseline_delta": {"real_bucket": None, "clean_bucket": None, "fn_bucket": None},
    "capability_probe": {"capability_matrix": None},
    "corpus_survey": {"signature_histogram": None},
    "interference": {"pairwise_matrix": None},
    "liveness": {"process_tree_report": None},
    "stability": {"vertical": None, "horizontal": None},
    "state_sequence": {"sequence_diff": None},
    "transform_diff": {"before_after_diff": None},
}


_REGISTRY: dict = {}


def register(analysis_type: str, fn: Callable) -> None:
    _REGISTRY[analysis_type] = fn


def dispatch(analysis_type: str, *args, **kwargs) -> Evaluation:
    fn = _REGISTRY.get(analysis_type)
    if fn is None:
        shape = SHAPE_BY_TYPE.get(analysis_type, {})
        return Evaluation(status="NOT_IMPLEMENTED", aggregation="none", details=dict(shape))
    return fn(*args, **kwargs)
