"""fix_guard 判据与裁决。本文件有判据 1（爆炸半径）、判据 3（删除比例）、
判据 4（偷懒修复）与 Step 8 裁决；判据 2 在 symbols.py，判据 5 在 scene_names.py。

行为依据 NEXT_STEP.md「Step 3 判据 1 爆炸半径」与「不许自行解释的约定」。
输入是 Step 2 产出的规范 unified diff（hunk 头 1-based）与宿主注入的
root_cause_errors / pointers / declared_scope / rule_id。

`res_path` 是「引用方 / 报错所在文件」，`target_res_path` 是「pointer 指向的
目标文件」，两者不合并（verify_filter/models.py 的约定）。
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# 稳定错误码 / violation id
OUTSIDE_BLAST_RADIUS = "OUTSIDE_BLAST_RADIUS"
DELETION_RATIO = "DELETION_RATIO"      # G4.2：warn，不 block
BULK_DELETE = "BULK_DELETE"            # G4.1：block，allow_bulk_delete 可豁免
FILE_TRUNCATED = "FILE_TRUNCATED"      # block，无豁免
LAZY_PASS = "LAZY_PASS"                # 判据 4：整行 pass，block
LAZY_TODO = "LAZY_TODO"                # 判据 4：TODO/FIXME/XXX/HACK 与 # ...，warn
LAZY_KEPT_ORIGINAL = "LAZY_KEPT_ORIGINAL"  # 判据 4：注释自称保持原样，block
LAZY_NOT_IMPLEMENTED = "LAZY_NOT_IMPLEMENTED"  # 判据 4：push_error 自报未实现，block
COMMENTED_OUT = "COMMENTED_OUT"        # 判据 4：把旧行注释掉冒充修改，block

# 「不许自行解释的约定」：根因文件上 |行差| > 15 拒绝
RADIUS_N = 15

_HUNK_HEADER = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


@dataclass(frozen=True)
class GuardViolation:
    """一条判据违规。`block` 为 True 时参与 reject 判定。"""

    id: str
    file: str
    line: int | None
    message: str
    block: bool = True


@dataclass
class GuardResult:
    """判据输出。violations 里 block=True 的条目决定 reject；overrides 记被豁免的 block id。"""

    violations: list[GuardViolation] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    overrides: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(v.block for v in self.violations)


def parse_udiff_changed_lines(udiff: str) -> dict[str, list[int]]:
    """把规范 unified diff 解析成 {新文件路径: 变更行号列表（1-based，新文件侧）}。

    「变更行」只取 `+` 行（新增行）在新文件侧的行号；context 行不计入，
    否则锚定 context 会把爆炸半径撑大 ±3 行。不读 `symbols.line`。
    """
    changed: dict[str, list[int]] = {}
    current_file: str | None = None
    new_line = 0
    for line in udiff.splitlines():
        if line.startswith("+++"):
            raw = line[4:].strip()
            # difflib 的 tofile 形如 "b/foo.gd"，去掉 b/ 前缀
            current_file = raw[2:] if raw.startswith("b/") else raw
            changed.setdefault(current_file, [])
        elif line.startswith("@@"):
            match = _HUNK_HEADER.match(line)
            if match:
                new_line = int(match.group(3))
        elif current_file is not None:
            if line.startswith("+"):
                changed[current_file].append(new_line)
                new_line += 1
            elif line.startswith("-"):
                pass  # 删除行不占新文件行号
            else:
                new_line += 1  # context 行
    return changed


def _scope_file(entry: str) -> str:
    """`res://player.gd#func:名字` → `res://player.gd`；纯路径原样返回。"""
    return entry.split("#", 1)[0]


def _load_rule_symbols(rules_db_path: Path | None, rule_id: Any) -> set[str] | None:
    """rule_id 在规则库中存在时返回该行的 old_symbol 集合；否则返回 None。

    表名用库里实际存在的 `migration_rules` 或 `rules`，列用 `id` 与
    `old_symbol`。库打不开、id 不存在都返回 None（豁免不生效）。
    """
    if rules_db_path is None or rule_id is None or not Path(rules_db_path).is_file():
        return None
    try:
        conn = sqlite3.connect(f"file:{rules_db_path}?mode=ro", uri=True)
        try:
            tables = {row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )}
            table = "migration_rules" if "migration_rules" in tables else (
                "rules" if "rules" in tables else None
            )
            if table is None:
                return None
            rows = conn.execute(
                f"SELECT old_symbol FROM {table} WHERE id = ?", (rule_id,)
            ).fetchall()
            if not rows:
                return None
            return {row[0] for row in rows}
        finally:
            conn.close()
    except sqlite3.Error:
        return None


def check_blast_radius(
    udiff: str,
    *,
    root_cause_errors: list[dict[str, Any]],
    pointers: list[dict[str, Any]],
    declared_scope: list[str] | None = None,
    rule_id: Any = None,
    rules_db_path: Path | None = None,
    file_texts: dict[str, str] | None = None,
) -> GuardResult:
    """判据 1 爆炸半径：diff 触及的行必须落在集合 C 内。

    C = 根因 ``(res_path, line)`` 的 15 行邻域 ∪ ``pointers[].target_res_path``
    整份 ∪ ``declared_scope`` 整份。根因 ``line`` 为 ``None`` 时该文件不提供
    距离，也不因此整份放行，除非它同时是 pointer 目标或在 declared_scope 里。

    ``rule_id`` 在规则库中存在时，允许改根因文件上 ``old_symbol`` 出现的行；
    id 不存在或库打不开则豁免不生效。``file_texts`` 提供 ``{res_path: 文本}``
    供该豁免逐行匹配符号；缺某文件文本时该文件的豁免保守不生效。
    """
    result = GuardResult()
    changed = parse_udiff_changed_lines(udiff)
    if not changed:
        return result

    # 集合 C 的三块来源
    root_points: dict[str, list[int | None]] = {}
    for error in root_cause_errors:
        res_path = error.get("res_path")
        if res_path:
            root_points.setdefault(res_path, []).append(error.get("line"))

    pointer_targets: set[str] = {
        p["target_res_path"] for p in pointers if p.get("target_res_path")
    }
    scope_files: set[str] = {_scope_file(s) for s in (declared_scope or [])}

    # rule_id 豁免：只对根因文件上 old_symbol 出现的行生效
    rule_symbols = _load_rule_symbols(rules_db_path, rule_id)

    for file, lines in changed.items():
        res_file = file if file.startswith("res://") else f"res://{file}"

        # pointer 目标 / declared_scope：整份放行
        if res_file in pointer_targets or res_file in scope_files:
            continue

        root_lines = root_points.get(res_file)
        if root_lines is None:
            result.violations.append(GuardViolation(
                id=OUTSIDE_BLAST_RADIUS,
                file=res_file,
                line=lines[0],
                message=f"file not in blast radius C: {res_file}",
            ))
            continue

        # 根因文件：逐行判距离。line 为 None 的根因不提供距离。
        known_lines = [ln for ln in root_lines if ln is not None]
        for changed_line in lines:
            if known_lines and any(
                abs(changed_line - root) <= RADIUS_N for root in known_lines
            ):
                continue
            if rule_symbols and _line_has_symbol(
                (file_texts or {}).get(res_file), changed_line, rule_symbols
            ):
                continue
            result.violations.append(GuardViolation(
                id=OUTSIDE_BLAST_RADIUS,
                file=res_file,
                line=changed_line,
                message=(
                    f"line {changed_line} is more than {RADIUS_N} lines from "
                    f"every root cause in {res_file}"
                ),
            ))
    return result


def _line_has_symbol(text: str | None, line: int, symbols: set[str]) -> bool:
    """rule_id 豁免：文件第 ``line`` 行（1-based）是否出现任一 ``old_symbol``。

    没有文件文本时保守返回 False（豁免不生效）。
    """
    if text is None:
        return False
    lines = text.split("\n")
    if line < 1 or line > len(lines):
        return False
    content = lines[line - 1]
    return any(symbol in content for symbol in symbols)


def _count_added_removed(udiff: str) -> tuple[int, int]:
    """从规范 udiff 数 added / removed 行；`+++` 与 `---` 行不计入。"""
    added = 0
    removed = 0
    for line in udiff.splitlines():
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+"):
            added += 1
        elif line.startswith("-"):
            removed += 1
    return added, removed


def check_deletion(
    udiff: str,
    *,
    file: str,
    old_text: str,
    new_text: str,
    allow_bulk_delete: bool = False,
) -> GuardResult:
    """判据 3：删除比例与截断。

    - G4.2 比值 warn：`removed - added > 10` 且 `added < removed * 0.3` →
      `DELETION_RATIO`，warn 不 block。
    - G4.1 批量删除：删除行数 `> max(30, 文件行数的 40%)` 且未设
      `allow_bulk_delete` → `BULK_DELETE`，block。`allow_bulk_delete=True`
      只豁免本项，比值 warn 仍在，并把豁免记入 ``overrides``。
    - 截断：`new_text` 为空或字节数 `< old_text 的 10%` → `FILE_TRUNCATED`，
      block，无豁免。
    """
    result = GuardResult()
    added, removed = _count_added_removed(udiff)

    # 截断无豁免，优先判
    if new_text == "" or len(new_text.encode()) < len(old_text.encode()) * 0.1:
        result.violations.append(GuardViolation(
            id=FILE_TRUNCATED,
            file=file,
            line=None,
            message=f"new_text is empty or smaller than 10% of old_text: {file}",
        ))
        return result

    # G4.2 比值 warn：无论 G4.1 是否豁免都在
    if removed - added > 10 and added < removed * 0.3:
        result.violations.append(GuardViolation(
            id=DELETION_RATIO,
            file=file,
            line=None,
            message=f"removed {removed} lines but added only {added}: {file}",
            block=False,
        ))

    # G4.1 批量删除
    old_line_count = len(old_text.split("\n"))
    threshold = max(30, old_line_count * 0.4)
    if removed > threshold:
        if allow_bulk_delete:
            result.overrides.append(BULK_DELETE)
        else:
            result.violations.append(GuardViolation(
                id=BULK_DELETE,
                file=file,
                line=None,
                message=f"removed {removed} lines exceeds threshold {threshold:.0f}: {file}",
            ))
    return result


# ---------- 判据 4：偷懒修复 ----------

# 整行 pass（允许前导空白）
_PASS_LINE = re.compile(r"^\s*pass\s*$")
# TODO / FIXME / XXX / HACK 与 `# ...` 省略号
_TODO_LINE = re.compile(r"#\s*(TODO|FIXME|XXX|HACK)\b")
_ELLIPSIS_LINE = re.compile(r"#\s*\.\.\.")
# 注释自称「保持原样」
_KEPT_ORIGINAL = re.compile(r"#.*(original|unchanged|as before|其余|不变)")
# push_error("... not implement ...")
_PUSH_ERROR_NOT_IMPLEMENTED = re.compile(
    r"push_error\(\s*[\"'][^\"']*not implement", re.IGNORECASE
)


def _added_lines(udiff: str) -> list[str]:
    """udiff 里全部 `+` 行的内容（去掉前导 `+`）；`+++` 头不计。"""
    return [
        line[1:]
        for line in udiff.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    ]


def _removed_lines(udiff: str) -> list[str]:
    """udiff 里全部 `-` 行的内容（去掉前导 `-`）；`---` 头不计。"""
    return [
        line[1:]
        for line in udiff.splitlines()
        if line.startswith("-") and not line.startswith("---")
    ]


def check_lazy_fix(udiff: str, *, file: str) -> GuardResult:
    """判据 4：偷懒修复。只扫 udiff 的 `+` 行；文件里原有的内容不算。

    - 整行 `pass` → `LAZY_PASS`，block。
    - `# TODO` / `FIXME` / `XXX` / `HACK` 与 `# ...` → `LAZY_TODO`，warn。
    - 注释含 `original` / `unchanged` / `as before` / `其余` / `不变` →
      `LAZY_KEPT_ORIGINAL`，block。
    - `push_error` 引号内匹配 `not implement` → `LAZY_NOT_IMPLEMENTED`，block。
    - `-` 行 strip 后等于 `+` 行去掉一个前导 `#` 再 strip → `COMMENTED_OUT`，block。

    本判据没有 override。
    """
    result = GuardResult()
    added = _added_lines(udiff)
    removed = _removed_lines(udiff)

    for line in added:
        if _PASS_LINE.match(line):
            result.violations.append(GuardViolation(
                id=LAZY_PASS, file=file, line=None,
                message=f"added line is a bare pass: {line.strip()!r}",
            ))
        if _TODO_LINE.search(line) or _ELLIPSIS_LINE.search(line):
            result.violations.append(GuardViolation(
                id=LAZY_TODO, file=file, line=None, block=False,
                message=f"added line has TODO/FIXME/XXX/HACK or ellipsis: {line.strip()!r}",
            ))
        if _KEPT_ORIGINAL.search(line):
            result.violations.append(GuardViolation(
                id=LAZY_KEPT_ORIGINAL, file=file, line=None,
                message=f"added comment claims code is unchanged: {line.strip()!r}",
            ))
        if _PUSH_ERROR_NOT_IMPLEMENTED.search(line):
            result.violations.append(GuardViolation(
                id=LAZY_NOT_IMPLEMENTED, file=file, line=None,
                message=f"added push_error says not implemented: {line.strip()!r}",
            ))

    # COMMENTED_OUT：- 行 strip == + 行去掉一个前导 # 再 strip
    stripped_removed = {line.strip() for line in removed}
    for line in added:
        stripped = line.strip()
        if stripped.startswith("#"):
            uncommented = stripped[1:].strip()
            if uncommented and uncommented in stripped_removed:
                result.violations.append(GuardViolation(
                    id=COMMENTED_OUT, file=file, line=None,
                    message=f"added line comments out a removed line: {stripped!r}",
                ))
    return result


# ---------- Step 8 裁决 ----------


def _violation_to_dict(v: Any) -> dict[str, Any]:
    """三种判据的 violation dataclass 统一成返回 JSON 里的字典。

    字段固定为 id / file / line / message / block；锚点失败等带 candidates
    的违规由调用方在 anchor 阶段直接以 dict 形式并入，本函数不丢这些键。
    """
    if isinstance(v, dict):
        return v
    entry = {
        "id": v.id,
        "file": v.file,
        "line": getattr(v, "line", None),
        "message": v.message,
        "block": v.block,
    }
    if hasattr(v, "symbol"):
        entry["symbol"] = v.symbol
    return entry


def verdict(
    *results: Any,
    anchor_warnings: list[str] | None = None,
    anchor_error: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """把各判据的结果收成 pass / warn / reject。本步不落盘。

    参数：
        results: 各判据的 Result 对象（GuardResult / SymbolCheckResult /
            SceneCheckResult），或 already-dict 的 violation 列表。
        anchor_warnings: Step 2 锚定的 warnings（如 FUZZY_ANCHOR）。
        anchor_error: Step 2 锚定失败时的 error dict（含 candidates）。

    规则（「不许自行解释的约定」）：
        - 任一 block 未被其 override 接住 → reject。
        - 只有 warn → warn；否则 pass。
        - FUZZY_ANCHOR 不单独构成 reject；没有 block 时 verdict 至少是 warn。
        - reject 时 counts_as_verify_round 为 false；pass 与 warn 时为 true。
        - override 进入返回 JSON。
    """
    blocks: list[dict[str, Any]] = []
    warns: list[dict[str, Any]] = []
    overrides: list[str] = []

    if anchor_error is not None:
        blocks.append({
            "id": anchor_error.get("code", "ANCHOR_ERROR"),
            "file": None,
            "line": None,
            "message": anchor_error.get("message", ""),
            "block": True,
            **({"candidates": anchor_error["candidates"]} if "candidates" in anchor_error else {}),
        })

    for result in results:
        for v in getattr(result, "violations", []):
            entry = _violation_to_dict(v)
            if entry.get("block", True):
                blocks.append(entry)
            else:
                warns.append(entry)
        overrides.extend(getattr(result, "overrides", []))

    # override 接住对应 id 的 block
    unblocked = [b for b in blocks if b["id"] not in overrides]

    fuzzy = bool(anchor_warnings) and any("FUZZY_ANCHOR" in w for w in anchor_warnings)

    if unblocked:
        decision = "reject"
    elif warns or fuzzy:
        decision = "warn"
    else:
        decision = "pass"

    return {
        "verdict": decision,
        "violations": [_violation_to_dict(b) for b in blocks] + [_violation_to_dict(w) for w in warns],
        "overrides": overrides,
        "warnings": list(anchor_warnings or []),
        "counts_as_verify_round": decision != "reject",
    }
