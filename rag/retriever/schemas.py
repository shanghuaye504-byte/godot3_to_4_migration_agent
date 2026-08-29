"""Pydantic contracts for A-layer rows and (later) retrieval.

``MigrationRule`` is 1:1 with the DDL in ``rag/build/README.md`` §5.
SQLite stores JSON columns as TEXT and flags as INTEGER 0/1; this model uses
``list`` / ``dict`` / ``bool``. Adapters must ``model_validate`` before writing
JSONL. RetrievalQuery / router pieces beyond MigrationRule are not required
for this build round.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator

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
    """One B-layer retrieval unit. Shape matches retriever/README.md §4
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
