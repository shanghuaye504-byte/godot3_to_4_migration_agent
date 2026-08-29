"""Diff ``extension_api_4.0.json`` vs ``extension_api_target.json`` → api_diff.jsonl.

Symbol-level set difference only (one 4.0→target pass). ``hash`` is ignored.
ABI keys (``builtin_class_sizes``, ``builtin_class_member_offsets``,
``native_structures``) are skipped. Overloads with the same name are compared
as a set of signatures so a dict-by-name does not drop rows.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from typing import Any, Iterable

from pathlib import Path

_BUILD_DIR = Path(__file__).resolve().parent
if str(_BUILD_DIR) not in sys.path:
    sys.path.insert(0, str(_BUILD_DIR))

from _util import (  # noqa: E402
    INTERMEDIATE,
    OFFICIAL,
    header_version_string,
    make_id,
    write_jsonl,
    write_report_json,
)
from rag.retriever.schemas import (  # noqa: E402
    AgentAction,
    ChangeKind,
    DetectionMethod,
    MigrationRule,
    SymbolKind,
)

SINCE = "4.0"
SKIP_TOPLEVEL = frozenset(
    {"builtin_class_sizes", "builtin_class_member_offsets", "native_structures"}
)


def _index_named(items: Iterable[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = defaultdict(list)
    for item in items:
        out[item["name"]].append(item)
    return out


def _return_type(method: dict) -> str | None:
    if "return_type" in method:
        return method["return_type"]
    rv = method.get("return_value")
    if isinstance(rv, dict):
        return rv.get("type")
    return None


def _arg_seq(method: dict) -> tuple[tuple[str | None, str | None], ...]:
    args = method.get("arguments") or []
    return tuple((a.get("name"), a.get("type")) for a in args)


def _method_sig(method: dict) -> tuple:
    return (
        _arg_seq(method),
        _return_type(method),
        bool(method.get("is_vararg", False)),
        bool(method.get("is_static", False)),
    )


def _has_compat(method: dict) -> bool:
    hc = method.get("hash_compatibility")
    return bool(hc)


def _only_optional_params_added(old: dict, new: dict) -> bool:
    old_args = old.get("arguments") or []
    new_args = new.get("arguments") or []
    old_seq = _arg_seq(old)
    new_seq = _arg_seq(new)
    if _return_type(old) != _return_type(new):
        return False
    if len(new_args) <= len(old_args):
        return False
    if old_seq != new_seq[: len(old_seq)]:
        return False
    extras = new_args[len(old_args) :]
    return bool(extras) and all("default_value" in a for a in extras)


def _signature_action(old: dict, new: dict) -> AgentAction:
    if _only_optional_params_added(old, new):
        return AgentAction.note_only
    return AgentAction.apply_and_warn


def _payload_methods(old: dict | None, new: dict | None) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    if old is not None:
        payload["old_signature"] = [_arg_seq(old), _return_type(old)]
    if new is not None:
        payload["new_signature"] = [_arg_seq(new), _return_type(new)]
        payload["old_return"] = _return_type(old) if old is not None else None
        payload["new_return"] = _return_type(new)
        if _has_compat(new):
            payload["has_compat_wrapper"] = True
    elif old is not None:
        payload["old_return"] = _return_type(old)
    return {k: v for k, v in payload.items() if v is not None}


def _rule(
    *,
    owner: str | None,
    symbol_kind: SymbolKind,
    change: ChangeKind,
    old_symbol: str | None,
    new_symbol: str | None,
    agent_action: AgentAction,
    payload: dict[str, Any] | None = None,
    extra: str | None = None,
    snippet: str | None = None,
) -> MigrationRule:
    symbol = old_symbol or new_symbol
    return MigrationRule(
        id=make_id("api_diff", SINCE, owner, symbol_kind.value, symbol, extra),
        old_symbol=old_symbol,
        new_symbol=new_symbol,
        owner=owner,
        symbol_kind=symbol_kind,
        change=change,
        since_version=SINCE,
        detection_method=DetectionMethod.agent_retrieval,
        agent_action=agent_action,
        snippet=snippet,
        source="api_diff",
        payload=payload or {},
    )


def _diff_named(
    old_map: dict[str, list[dict]],
    new_map: dict[str, list[dict]],
    *,
    owner: str | None,
    symbol_kind: SymbolKind,
    compare,
    on_change,
) -> list[MigrationRule]:
    """Generic name-set diff. ``compare(old_list, new_list)`` returns None if equal."""
    rows: list[MigrationRule] = []
    names = set(old_map) | set(new_map)
    for name in sorted(names):
        in_old = name in old_map
        in_new = name in new_map
        if in_old and not in_new:
            rows.append(
                _rule(
                    owner=owner,
                    symbol_kind=symbol_kind,
                    change=ChangeKind.remove,
                    old_symbol=name,
                    new_symbol=None,
                    agent_action=AgentAction.note_only,
                    payload=_payload_methods(old_map[name][0], None)
                    if symbol_kind == SymbolKind.method
                    else {},
                )
            )
        elif in_new and not in_old:
            new_item = new_map[name][0]
            payload = (
                _payload_methods(None, new_item) if symbol_kind == SymbolKind.method else {}
            )
            rows.append(
                _rule(
                    owner=owner,
                    symbol_kind=symbol_kind,
                    change=ChangeKind.add,
                    old_symbol=None,
                    new_symbol=name,
                    agent_action=AgentAction.note_only,
                    payload=payload,
                )
            )
        else:
            delta = compare(old_map[name], new_map[name])
            if delta is not None:
                rows.extend(on_change(name, old_map[name], new_map[name], delta))
    return rows


def _compare_method_lists(old_list: list[dict], new_list: list[dict]) -> str | None:
    old_sigs = {_method_sig(m) for m in old_list}
    new_sigs = {_method_sig(m) for m in new_list}
    if old_sigs == new_sigs:
        return None
    return "signature"


def diff_methods(
    old_items: list[dict],
    new_items: list[dict],
    *,
    owner: str | None,
    kind: SymbolKind = SymbolKind.method,
) -> list[MigrationRule]:
    old_map = _index_named(old_items)
    new_map = _index_named(new_items)

    def on_change(name, old_list, new_list, _delta):
        old, new = old_list[0], new_list[0]
        return [
            _rule(
                owner=owner,
                symbol_kind=kind,
                change=ChangeKind.signature,
                old_symbol=name,
                new_symbol=name,
                agent_action=_signature_action(old, new),
                payload=_payload_methods(old, new),
            )
        ]

    return _diff_named(
        old_map,
        new_map,
        owner=owner,
        symbol_kind=kind,
        compare=_compare_method_lists,
        on_change=on_change,
    )


def diff_properties(
    old_items: list[dict], new_items: list[dict], *, owner: str | None, kind: SymbolKind
) -> list[MigrationRule]:
    old_map = _index_named(old_items)
    new_map = _index_named(new_items)

    def compare(ol, nl):
        return None if ol[0].get("type") == nl[0].get("type") else "type"

    def on_change(name, ol, nl, _d):
        return [
            _rule(
                owner=owner,
                symbol_kind=kind,
                change=ChangeKind.type,
                old_symbol=name,
                new_symbol=name,
                agent_action=AgentAction.apply_and_warn,
                payload={
                    "old_signature": ol[0].get("type"),
                    "new_signature": nl[0].get("type"),
                },
            )
        ]

    return _diff_named(
        old_map,
        new_map,
        owner=owner,
        symbol_kind=kind,
        compare=compare,
        on_change=on_change,
    )


def diff_signals(
    old_items: list[dict], new_items: list[dict], *, owner: str | None
) -> list[MigrationRule]:
    old_map = _index_named(old_items)
    new_map = _index_named(new_items)

    def compare(ol, nl):
        return None if _arg_seq(ol[0]) == _arg_seq(nl[0]) else "signature"

    def on_change(name, ol, nl, _d):
        return [
            _rule(
                owner=owner,
                symbol_kind=SymbolKind.signal,
                change=ChangeKind.signature,
                old_symbol=name,
                new_symbol=name,
                agent_action=AgentAction.apply_and_warn,
                payload=_payload_methods(ol[0], nl[0]),
            )
        ]

    return _diff_named(
        old_map,
        new_map,
        owner=owner,
        symbol_kind=SymbolKind.signal,
        compare=compare,
        on_change=on_change,
    )


def _enum_value_names(enum: dict) -> tuple[str, ...]:
    return tuple(v["name"] for v in enum.get("values") or [])


def diff_enums(
    old_items: list[dict], new_items: list[dict], *, owner: str | None
) -> list[MigrationRule]:
    old_map = _index_named(old_items)
    new_map = _index_named(new_items)

    def compare(ol, nl):
        return None if _enum_value_names(ol[0]) == _enum_value_names(nl[0]) else "signature"

    def on_change(name, ol, nl, _d):
        return [
            _rule(
                owner=owner,
                symbol_kind=SymbolKind.enum,
                change=ChangeKind.signature,
                old_symbol=name,
                new_symbol=name,
                agent_action=AgentAction.note_only,
                payload={
                    "old_signature": list(_enum_value_names(ol[0])),
                    "new_signature": list(_enum_value_names(nl[0])),
                },
            )
        ]

    return _diff_named(
        old_map,
        new_map,
        owner=owner,
        symbol_kind=SymbolKind.enum,
        compare=compare,
        on_change=on_change,
    )


def diff_constants(
    old_items: list[dict], new_items: list[dict], *, owner: str | None
) -> list[MigrationRule]:
    old_map = _index_named(old_items)
    new_map = _index_named(new_items)

    def compare(ol, nl):
        o, n = ol[0], nl[0]
        if o.get("type") != n.get("type"):
            return "type"
        if o.get("value") != n.get("value"):
            return "default"
        return None

    def on_change(name, ol, nl, delta):
        change = ChangeKind.type if delta == "type" else ChangeKind.default
        payload: dict[str, Any] = {
            "old_signature": ol[0].get("type"),
            "new_signature": nl[0].get("type"),
        }
        if delta == "default":
            payload["old_default"] = ol[0].get("value")
            payload["new_default"] = nl[0].get("value")
        return [
            _rule(
                owner=owner,
                symbol_kind=SymbolKind.constant,
                change=change,
                old_symbol=name,
                new_symbol=name,
                agent_action=AgentAction.apply_and_warn
                if delta == "type"
                else AgentAction.note_only,
                payload=payload,
            )
        ]

    return _diff_named(
        old_map,
        new_map,
        owner=owner,
        symbol_kind=SymbolKind.constant,
        compare=compare,
        on_change=on_change,
    )


def _diff_class_container(
    old_cls: dict | None,
    new_cls: dict | None,
    *,
    owner: str,
    method_key: str = "methods",
    member_key: str = "properties",
    member_kind: SymbolKind = SymbolKind.property,
    include_signals: bool = True,
    include_enums: bool = True,
    include_constants: bool = True,
) -> list[MigrationRule]:
    rows: list[MigrationRule] = []
    old_cls = old_cls or {}
    new_cls = new_cls or {}
    rows.extend(diff_methods(old_cls.get(method_key) or [], new_cls.get(method_key) or [], owner=owner))
    rows.extend(
        diff_properties(
            old_cls.get(member_key) or [],
            new_cls.get(member_key) or [],
            owner=owner,
            kind=member_kind,
        )
    )
    if include_signals:
        rows.extend(
            diff_signals(old_cls.get("signals") or [], new_cls.get("signals") or [], owner=owner)
        )
    if include_enums:
        rows.extend(diff_enums(old_cls.get("enums") or [], new_cls.get("enums") or [], owner=owner))
    if include_constants:
        rows.extend(
            diff_constants(
                old_cls.get("constants") or [], new_cls.get("constants") or [], owner=owner
            )
        )
    return rows


def diff_classes(old_api: dict, new_api: dict) -> list[MigrationRule]:
    old_map = {c["name"]: c for c in old_api.get("classes") or []}
    new_map = {c["name"]: c for c in new_api.get("classes") or []}
    rows: list[MigrationRule] = []
    for name in sorted(set(old_map) | set(new_map)):
        old_c, new_c = old_map.get(name), new_map.get(name)
        if old_c and not new_c:
            rows.append(
                _rule(
                    owner=name,
                    symbol_kind=SymbolKind.class_,
                    change=ChangeKind.remove,
                    old_symbol=name,
                    new_symbol=None,
                    agent_action=AgentAction.note_only,
                )
            )
            rows.extend(_diff_class_container(old_c, None, owner=name))
        elif new_c and not old_c:
            rows.append(
                _rule(
                    owner=name,
                    symbol_kind=SymbolKind.class_,
                    change=ChangeKind.add,
                    old_symbol=None,
                    new_symbol=name,
                    agent_action=AgentAction.note_only,
                )
            )
            rows.extend(_diff_class_container(None, new_c, owner=name))
        else:
            rows.extend(_diff_class_container(old_c, new_c, owner=name))
    return rows


def diff_builtin_classes(old_api: dict, new_api: dict) -> list[MigrationRule]:
    old_map = {c["name"]: c for c in old_api.get("builtin_classes") or []}
    new_map = {c["name"]: c for c in new_api.get("builtin_classes") or []}
    rows: list[MigrationRule] = []
    for name in sorted(set(old_map) | set(new_map)):
        old_c, new_c = old_map.get(name), new_map.get(name)
        if old_c and not new_c:
            rows.append(
                _rule(
                    owner=name,
                    symbol_kind=SymbolKind.builtin,
                    change=ChangeKind.remove,
                    old_symbol=name,
                    new_symbol=None,
                    agent_action=AgentAction.note_only,
                )
            )
            rows.extend(
                _diff_class_container(
                    old_c,
                    None,
                    owner=name,
                    member_key="members",
                    include_signals=False,
                    include_enums=False,
                    include_constants=False,
                )
            )
        elif new_c and not old_c:
            rows.append(
                _rule(
                    owner=name,
                    symbol_kind=SymbolKind.builtin,
                    change=ChangeKind.add,
                    old_symbol=None,
                    new_symbol=name,
                    agent_action=AgentAction.note_only,
                )
            )
            rows.extend(
                _diff_class_container(
                    None,
                    new_c,
                    owner=name,
                    member_key="members",
                    include_signals=False,
                    include_enums=False,
                    include_constants=False,
                )
            )
        else:
            rows.extend(
                _diff_class_container(
                    old_c,
                    new_c,
                    owner=name,
                    member_key="members",
                    include_signals=False,
                    include_enums=False,
                    include_constants=False,
                )
            )
    return rows


def diff_global_enums(old_api: dict, new_api: dict) -> list[MigrationRule]:
    return diff_enums(old_api.get("global_enums") or [], new_api.get("global_enums") or [], owner=None)


def diff_utility(old_api: dict, new_api: dict) -> list[MigrationRule]:
    return diff_methods(
        old_api.get("utility_functions") or [],
        new_api.get("utility_functions") or [],
        owner=None,
        kind=SymbolKind.utility,
    )


def diff_singletons(old_api: dict, new_api: dict) -> list[MigrationRule]:
    old_map = _index_named(old_api.get("singletons") or [])
    new_map = _index_named(new_api.get("singletons") or [])

    def compare(ol, nl):
        return None if ol[0].get("type") == nl[0].get("type") else "type"

    def on_change(name, ol, nl, _d):
        return [
            _rule(
                owner=name,
                symbol_kind=SymbolKind.singleton,
                change=ChangeKind.type,
                old_symbol=name,
                new_symbol=name,
                agent_action=AgentAction.apply_and_warn,
                payload={"old_signature": ol[0].get("type"), "new_signature": nl[0].get("type")},
            )
        ]

    # add/remove need symbol_kind=singleton — _diff_named uses the kind we pass
    return _diff_named(
        old_map,
        new_map,
        owner=None,
        symbol_kind=SymbolKind.singleton,
        compare=compare,
        on_change=on_change,
    )


def run_diff(old_api: dict, new_api: dict) -> list[MigrationRule]:
    rows: list[MigrationRule] = []
    rows.extend(diff_classes(old_api, new_api))
    rows.extend(diff_builtin_classes(old_api, new_api))
    rows.extend(diff_global_enums(old_api, new_api))
    rows.extend(diff_utility(old_api, new_api))
    rows.extend(diff_singletons(old_api, new_api))
    # Touch SKIP_TOPLEVEL so a future reader sees we deliberately ignored them.
    for _key in SKIP_TOPLEVEL:
        old_api.get(_key)
        new_api.get(_key)
    return rows


def main() -> int:
    old_path = OFFICIAL / "extension_api_4.0.json"
    new_path = OFFICIAL / "extension_api_target.json"
    print(f"diff_extension_api: loading {old_path.name} / {new_path.name} …")
    old_api = json.loads(old_path.read_text(encoding="utf-8"))
    new_api = json.loads(new_path.read_text(encoding="utf-8"))
    rows = run_diff(old_api, new_api)
    out = INTERMEDIATE / "api_diff.jsonl"
    n = write_jsonl(out, rows)
    by_change: dict[str, int] = defaultdict(int)
    for r in rows:
        by_change[r.change.value] += 1
    report = {
        "api_from": header_version_string(old_api),
        "api_to": header_version_string(new_api),
        "rule_count": n,
        "by_change": dict(by_change),
    }
    write_report_json("api_diff", report)
    print(f"diff_extension_api: wrote {n} rows → {out}")
    print(f"  by change: {dict(by_change)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
