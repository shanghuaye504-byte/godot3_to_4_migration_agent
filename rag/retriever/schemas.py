"""Pydantic 契约：枚举、A/B 行模型、Agent 入参/出参。

本文件负责：与 ``rag/build/README.md`` §5 DDL 1:1 的 ``MigrationRule``，
与 CHUNKING.md Lance 列对齐的 ``ProseChunk``（不含 vector 列），以及
``docs/contracts.md`` 中的 ``RetrievalQuery`` / ``RetrievalResult``。

禁止：IO、SQL、检索；不要给 ``MigrationRule`` / ``ProseChunk`` 加字段。

对应文档：``docs/contracts.md``、``ARCHITECTURE.md`` 模块地图。
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Any, Literal

from pydantic import (
    BaseModel,
    Field,
    computed_field,
    field_validator,
    model_validator,
)

from rag.version_codec import version_to_code


class SymbolKind(str, Enum):
    class_ = "class"
    method = "method"
    property = "property"
    signal = "signal"
    enum = "enum"
    constant = "constant"
    builtin = "builtin"
    shader = "shader"
    theme = "theme"
    color = "color"
    project_setting = "project_setting"
    singleton = "singleton"
    utility = "utility"
    rewrite = "rewrite"
    trap = "trap"


class ChangeKind(str, Enum):
    rename = "rename"
    remove = "remove"
    add = "add"
    signature = "signature"
    type = "type"
    move = "move"
    split = "split"
    replace = "replace"
    default = "default"
    behavior = "behavior"
    rewrite = "rewrite"
    trap = "trap"
    false_positive = "false_positive"


class DetectionMethod(str, Enum):
    agent_retrieval = "agent_retrieval"
    agent_retrieval_or_escalate = "agent_retrieval_or_escalate"
    static_scan_post_l0 = "static_scan_post_l0"
    verify_error_filter = "verify_error_filter"
    # YAML-only; never written to rules.db
    not_actively_handled = "not_actively_handled"
    preflight_probe_recommended = "preflight_probe_recommended"


class AgentAction(str, Enum):
    apply_rename = "apply_rename"
    apply_and_warn = "apply_and_warn"
    do_not_fix = "do_not_fix"
    escalate_human = "escalate_human"
    note_only = "note_only"


SKIP_DETECTION_METHODS = frozenset(
    {
        DetectionMethod.not_actively_handled,
        DetectionMethod.preflight_probe_recommended,
    }
)

AGENT_VISIBLE_DETECTION_METHODS = (
    DetectionMethod.agent_retrieval,
    DetectionMethod.agent_retrieval_or_escalate,
)


class MigrationRule(BaseModel):
    id: str
    old_symbol: str | None = None
    new_symbol: str | None = None
    owner: str | None = None
    symbol_kind: SymbolKind
    change: ChangeKind
    rule_kind: str | None = None
    match_tokens: list[str] = Field(default_factory=list)
    trigger: dict[str, Any] | None = None
    since_version: str | None = None
    since_version_code: int = 0
    until_version: str | None = None
    until_version_code: int | None = None
    detection_method: DetectionMethod = DetectionMethod.agent_retrieval
    semantic_risk: bool = False
    converter_gap: bool = False
    verifier_blind: bool = False
    agent_action: AgentAction | None = None
    system_action: str | None = None
    warning: str | None = None
    snippet: str | None = None
    source: str
    source_url: str | None = None
    confidence: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _fill_since_version_code(self) -> MigrationRule:
        if self.since_version and self.since_version_code == 0:
            self.since_version_code = version_to_code(self.since_version)
        return self


class ProseChunk(BaseModel):
    """One B-layer retrieval unit. Shape matches retriever/docs/tier-b.md
    and the LanceDB row in CHUNKING.md §8.4.3 (vector is stored alongside,
    not on this model).
    """

    id: str
    text: str
    heading_path: list[str]
    since_version: str | None = None
    since_version_code: int = 0
    related_symbols: list[str] = Field(default_factory=list)
    source: str
    source_file: str
    source_url: str | None = None

    @model_validator(mode="after")
    def _fill_since_version_code(self) -> ProseChunk:
        if self.since_version and self.since_version_code == 0:
            self.since_version_code = version_to_code(self.since_version)
        return self


class RetrievalMode(str, Enum):
    """开不开 A / 开不开 B。不是 YAML ``tier_b.channels``。"""

    hybrid = "hybrid"
    exact_only = "exact_only"
    semantic_only = "semantic_only"


_VERSION_RE = re.compile(r"^\d+\.\d+(?:\.\d+)?$")


class RetrievalQuery(BaseModel):
    """Agent 唯一能填的检索入参。权重 / k / 通道不在这张表里。"""

    error_text: str | None = None
    symbols: list[str] = Field(default_factory=list)
    query_text: str | None = None
    target_version: str
    file_hint: str | None = None
    kinds: list[SymbolKind] | None = None
    retrieval_mode: RetrievalMode = RetrievalMode.hybrid
    top_k: int = 8
    top_k_a: int | None = None
    top_k_b: int | None = None
    request_id: str | None = None

    @field_validator("target_version")
    @classmethod
    def _check_version(cls, value: str) -> str:
        if not _VERSION_RE.fullmatch(value):
            raise ValueError("target_version 只接受 \\d+.\\d+ 或 \\d+.\\d+.\\d+，例如 4.7.1")
        return value

    @field_validator("top_k", "top_k_a", "top_k_b")
    @classmethod
    def _check_k(cls, value: int | None) -> int | None:
        if value is None:
            return value
        if not 1 <= value <= 50:
            raise ValueError("top_k / top_k_a / top_k_b 必须在 1～50")
        return value

    @model_validator(mode="after")
    def _need_query_input(self) -> RetrievalQuery:
        has_text = bool(self.error_text and self.error_text.strip())
        has_query = bool(self.query_text and self.query_text.strip())
        has_symbols = bool(self.symbols)
        if not (has_text or has_query or has_symbols):
            raise ValueError("error_text / symbols / query_text 至少提供一个")
        return self

    @computed_field  # type: ignore[prop-decorator]
    @property
    def target_version_code(self) -> int:
        return version_to_code(self.target_version)


class StructuredHit(BaseModel):
    rule: MigrationRule
    score: float
    match_reason: str


class ProseHit(BaseModel):
    chunk: ProseChunk
    score: float
    match_reason: Literal["bm25", "vector", "hybrid"]


class UnifiedHit(BaseModel):
    layer: Literal["A", "B"]
    score: float
    structured: MigrationRule | None = None
    prose: ProseChunk | None = None


class RetrievalResult(BaseModel):
    resolved_symbols: list[str]
    target_version_code: int
    structured_hits: list[StructuredHit]
    prose_hits: list[ProseHit]
    merged: list[UnifiedHit]
    coverage: Literal["rule_hit", "prose_only", "no_hit"]
    recommended_action: AgentAction | None
    escalate_suggested: bool
    cache_hit: bool
    took_ms: float
