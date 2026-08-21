"""两级 signature 归一化。

local_signature = sha1(kind | res_path | symbol | normalized_msg)
noise_signature = sha1(kind | msg_template)   （msg_template 在 normalized_msg
基础上再抹掉 res_path/symbol，只用于 BG 减法，不用于 TP/FP 归类）

字段抹除规则由 N09 校准后写入 signature-rules.yaml；该文件目前是骨架，没有
正则表时回退到覆盖 README 明确要求的默认规则（行号/内存地址/耗时/绝对路径）。
"""

from __future__ import annotations

import dataclasses
import hashlib
import re
from pathlib import Path
from typing import Optional

import yaml


@dataclasses.dataclass(frozen=True)
class OutputLine:
    kind: str
    raw: str
    res_path: str = ""
    symbol: str = ""
    line_no: Optional[int] = None


_DEFAULT_STRIP_PATTERNS = [
    (re.compile(r":(\d+)\)"), ":<LINE>)"),
    (re.compile(r"line\s+\d+", re.IGNORECASE), "line <LINE>"),
    (re.compile(r"0x[0-9a-fA-F]+"), "<ADDR>"),
    (re.compile(r"\b\d+(?:\.\d+)?\s*(?:ms|msec|s|sec)\b"), "<TIME>"),
    (re.compile(r"/(?:[\w.\-]+/)+[\w.\-]+"), "<ABS_PATH>"),
]


@dataclasses.dataclass
class SignatureRules:
    strip_patterns: list = dataclasses.field(default_factory=lambda: list(_DEFAULT_STRIP_PATTERNS))
    noise_strip_fields: tuple = ("res_path", "symbol")


def load_signature_rules(path: Path) -> SignatureRules:
    path = Path(path)
    if not path.exists():
        return SignatureRules()
    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    raw_patterns = data.get("strip_patterns") if data else None
    if not raw_patterns:
        return SignatureRules()
    patterns = [(re.compile(p["pattern"]), p.get("replacement", "")) for p in raw_patterns]
    return SignatureRules(
        strip_patterns=patterns,
        noise_strip_fields=tuple(data.get("noise_strip_fields", ("res_path", "symbol"))),
    )


def _normalize_msg(raw: str, rules: SignatureRules) -> str:
    normalized = raw
    for pattern, replacement in rules.strip_patterns:
        normalized = pattern.sub(replacement, normalized)
    return normalized


def local_signature(line: OutputLine, rules: SignatureRules) -> str:
    normalized_msg = _normalize_msg(line.raw, rules)
    parts = [line.kind, line.res_path, line.symbol, normalized_msg]
    return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()


def noise_signature(line: OutputLine, rules: SignatureRules) -> str:
    template = _normalize_msg(line.raw, rules)
    if "res_path" in rules.noise_strip_fields and line.res_path:
        template = template.replace(line.res_path, "<RES>")
    if "symbol" in rules.noise_strip_fields and line.symbol:
        template = template.replace(line.symbol, "<SYM>")
    parts = [line.kind, template]
    return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()


def compute_signatures(lines: list, rules: SignatureRules) -> list:
    return [
        {
            "raw": line.raw,
            "kind": line.kind,
            "res_path": line.res_path,
            "symbol": line.symbol,
            "line_no": line.line_no,
            "local_signature": local_signature(line, rules),
            "noise_signature": noise_signature(line, rules),
        }
        for line in lines
    ]


_KIND_PATTERNS = [
    ("script_error", re.compile(r"SCRIPT ERROR", re.IGNORECASE)),
    ("parse_error", re.compile(r"Parse Error", re.IGNORECASE)),
    ("compile_error", re.compile(r"Compile Error|Compilation failed", re.IGNORECASE)),
    ("warning", re.compile(r"WARNING", re.IGNORECASE)),
    ("error", re.compile(r"ERROR", re.IGNORECASE)),
]

_RES_PATH_RE = re.compile(r"res://[\w./\-]+")
_LINE_NO_RE = re.compile(r":(\d+)\)|line\s+(\d+)", re.IGNORECASE)
_SYMBOL_RE = re.compile(r'Identifier "([^"]+)"|Identifier not found: "?([^"\s]+)"?|class "([^"]+)"')


def _classify_kind(raw: str) -> str:
    for kind, pattern in _KIND_PATTERNS:
        if pattern.search(raw):
            return kind
    return "other"


def _extract_res_path(raw: str) -> str:
    m = _RES_PATH_RE.search(raw)
    return m.group(0) if m else ""


def _extract_line_no(raw: str) -> Optional[int]:
    m = _LINE_NO_RE.search(raw)
    if not m:
        return None
    for group in m.groups():
        if group:
            return int(group)
    return None


def _extract_symbol(raw: str) -> str:
    m = _SYMBOL_RE.search(raw)
    if not m:
        return ""
    return next((g for g in m.groups() if g), "")


def parse_output_lines(text: str) -> list:
    lines = []
    for raw in text.splitlines():
        if not raw.strip():
            continue
        kind = _classify_kind(raw)
        if kind == "other":
            continue
        lines.append(
            OutputLine(
                kind=kind,
                raw=raw,
                res_path=_extract_res_path(raw),
                symbol=_extract_symbol(raw),
                line_no=_extract_line_no(raw),
            )
        )
    return lines
