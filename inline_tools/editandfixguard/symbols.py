"""判据 2（语法回归）、G2.1（符号消失）、G5.1（反向迁移）。

行为依据 NEXT_STEP.md「Step 4 判据 2、G2.1、G5.1」与「不许自行解释的约定」。
在内存中跑 tree-sitter：不调用 writer，不写 `index.db`，不修改
`GdscriptParser` 的「`has_error` 则抛异常、不返回半套符号」约定。

符号解析复用 `codeindex.parsers.gdscript.GdscriptParser`；它只认
class/func/signal/var/const/enum 六种 kind，注释和字符串里的 `func`
天然不会被当成符号（tree-sitter 把它们切到注释/字符串节点）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import tree_sitter as ts
from tree_sitter_language_pack import configure, get_language
from tree_sitter_language_pack.options import PackConfig

from codeindex.parsers.gdscript import GdscriptParser

# 沙箱里默认缓存目录（~/Library/Caches）不可写；指到 tmp 下，首次使用时下载
configure(PackConfig(cache_dir="/private/tmp/tree-sitter-language-pack"))

from . import rules_db

# 稳定错误码 / violation id
SYNTAX_REGRESSION = "SYNTAX_REGRESSION"
SYMBOL_REMOVED = "SYMBOL_REMOVED"
REVERSE_MIGRATION = "REVERSE_MIGRATION"
RULES_DB_UNAVAILABLE = "RULES_DB_UNAVAILABLE"

# 判据 2 的符号 kind 只认这六种（与 GdscriptParser 产出一致）
SYMBOL_KINDS = frozenset({"class", "func", "signal", "var", "const", "enum"})

_parser = GdscriptParser()


@dataclass(frozen=True)
class SymbolViolation:
    """一条判据 2 / G2.1 / G5.1 违规。"""

    id: str
    file: str
    symbol: str | None
    message: str
    block: bool = True


@dataclass
class SymbolCheckResult:
    """判据 2、G2.1、G5.1 的合并输出。violations 为空表示通过。"""

    violations: list[SymbolViolation] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(v.block for v in self.violations)


def _error_node_count(source: str) -> int:
    """tree-sitter 的 error 节点数：含 `is_error` 与 `is_missing`，与
    `root.has_error` 的范围一致。纯内存解析，不写任何索引。"""
    parser = ts.Parser(get_language("gdscript"))
    tree = parser.parse(source.encode())
    count = 0
    stack = [tree.root_node]
    while stack:
        node = stack.pop()
        if node.is_error or node.is_missing:
            count += 1
        stack.extend(node.children)
    return count


def _symbol_names(source: str, path: str) -> set[str]:
    """两边 error 节点都为 0 时才调用：整份符号的名字集合（六种 kind）。

    `GdscriptParser.parse` 在 `has_error` 时抛 SyntaxError；调用方已保证
    error 计数为 0，这里不捕这个异常（约定：不返回半套符号）。
    """
    result = _parser.parse(path, source)
    return {s.name for s in result.symbols if s.kind in SYMBOL_KINDS}


def _scope_names(declared_scope: list[str] | None) -> set[str]:
    """`res://player.gd#func:名字` → `名字`；纯路径条目没有符号名，跳过。"""
    names: set[str] = set()
    for entry in declared_scope or []:
        if "#" in entry:
            anchor = entry.split("#", 1)[1]
            if ":" in anchor:
                names.add(anchor.split(":", 1)[1])
    return names


def check_symbols(
    file: str,
    old_text: str,
    new_text: str,
    *,
    declared_scope: list[str] | None = None,
    rules_db_path: Path | None = None,
) -> SymbolCheckResult:
    """对一对内存文本跑判据 2、G2.1、G5.1。

    参数：
        file: res:// 形式的路径（仅用于报错信息）。
        old_text / new_text: 写前 / 写后的内存文本。
        declared_scope: G2.1 的豁免清单，消失符号须逐个以 ``#kind:名字`` 列出。
        rules_db_path: G5.1 要查的规则库；为 None 时跳过 G5.1。

    计数规则（「不许自行解释的约定」）：两边只要有一边 error 节点数大于 0，
    就不做符号集合差；`new` 的计数大于 `old` 时报 SYNTAX_REGRESSION 且不再
    报符号消失；`new` 不大于 `old` 且并非两边都为 0 时，判据 2 与 G2.1 都
    不拒绝。`create` 时 old_text 为空，判据 2 不触发。
    """
    result = SymbolCheckResult()

    # create：old_text 为空，判据 2 不触发；G5.1 仍要查（新符号可能是旧名）
    if old_text == "":
        if rules_db_path is not None:
            result.violations.extend(_check_reverse_migration(file, new_text, rules_db_path))
        return result

    old_errors = _error_node_count(old_text)
    new_errors = _error_node_count(new_text)

    # 判据 2：new 的 error 节点多于 old → SYNTAX_REGRESSION，不报符号消失
    if new_errors > old_errors:
        result.violations.append(SymbolViolation(
            id=SYNTAX_REGRESSION,
            file=file,
            symbol=None,
            message=f"error node count rose from {old_errors} to {new_errors}",
        ))
        return result

    # 两边都为 0 才做符号集合差；有一边大于 0（且 new ≤ old）时判据 2/G2.1 不拒绝
    if old_errors == 0 and new_errors == 0:
        before = _symbol_names(old_text, file)
        after = _symbol_names(new_text, file)
        disappeared = before - after
        if disappeared:
            declared = _scope_names(declared_scope)
            undeclared = disappeared - declared
            for name in sorted(undeclared):
                result.violations.append(SymbolViolation(
                    id=SYMBOL_REMOVED,
                    file=file,
                    symbol=name,
                    message=f"symbol {name!r} removed without declared_scope entry",
                ))
        # G5.1：新出现的名字落在 old_symbol 列 → REVERSE_MIGRATION
        if rules_db_path is not None:
            result.violations.extend(
                _check_reverse_migration(file, new_text, rules_db_path, before=before, after=after)
            )
    return result


def _check_reverse_migration(
    file: str,
    new_text: str,
    rules_db_path: Path,
    *,
    before: set[str] | None = None,
    after: set[str] | None = None,
) -> list[SymbolViolation]:
    """G5.1：`S_after − S_before` 的名字落在 `old_symbol` 列 → REVERSE_MIGRATION。

    旧文本里已有的旧符号不因此失败（只对「新出现」的名字报警）。规则库
    打不开 → RULES_DB_UNAVAILABLE 且本检查拒绝。查询不限 symbol_kind。
    """
    try:
        old_symbols = rules_db.load_old_symbols(rules_db_path)
    except Exception:
        return [SymbolViolation(
            id=RULES_DB_UNAVAILABLE,
            file=file,
            symbol=None,
            message=f"rules db unavailable: {rules_db_path}",
        )]

    if before is None or after is None:
        # create 路径：before 为空集，after 现算
        before = set()
        after = _symbol_names(new_text, file) if new_text else set()

    appeared = after - before
    violations: list[SymbolViolation] = []
    for name in sorted(appeared):
        if name in old_symbols:
            violations.append(SymbolViolation(
                id=REVERSE_MIGRATION,
                file=file,
                symbol=name,
                message=f"new symbol {name!r} matches old_symbol in rules db",
            ))
    return violations
