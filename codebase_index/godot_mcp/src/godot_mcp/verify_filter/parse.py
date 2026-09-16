"""解析器 —— 方案文档 §5。把原始 stdout/stderr 切成 `RawEvent`，再分类成 `ClassifiedEvent`。

行语法（4.7.1 实测，§5.1，不要放宽到"任意 ERROR"）：Godot 一条事件 = 1 行前缀 +
1 行 `at:` continuation。匹配优先级固定为 `AT_SCRIPT → AT_ENGINE → AT_SHADER →
AT_GENERIC`（更具体的模式先尝试，避免宽泛正则吞掉本该被精确捕获的内容）。

§5.3 的十份"黄金原文"必须逐字（含空白）能够解析，样例放在
`tests/verify_filter/fixtures/godot_4_7_1/`，不要凭记忆重写。

不解析进事件的内容（§5.4）：`Godot Engine v...` 横幅、项目自己的 `print`、空 stderr
（结果是零事件，不是解析失败）。

**实现顺序的一处例外（如实记录）**：方案文档 §3 把 `parse.py` 排在 `signature.py`
之前，但 `classify()` 要产出完整的 `ClassifiedEvent`（`local_signature` 是必填字段，
§7 pipeline 图里 R8 去重也靠它），所以 `classify()` 内部必须调用 `signature.py`
的纯函数。这是唯一一处"排在前面的模块反过来依赖排在后面的模块"，原因是
`signature.py` 本身零依赖、是最底层的纯函数。
"""

from __future__ import annotations

import re
from typing import Literal

from godot_mcp.verify_filter import signature as _sig
from godot_mcp.verify_filter.models import ClassifiedEvent, Kind, RawEvent, Role

# --- 行语法正则（§5.1） ---

PREFIX = re.compile(
    r"^(?P<prefix>SCRIPT ERROR|SHADER ERROR|ERROR|WARNING): (?P<message>.*)$",
    re.MULTILINE,
)
AT_SCRIPT = re.compile(
    r"^\s+at: (?P<func>\S+) \((?P<res>res://[^:)]+):(?P<line>\d+)\)$",
    re.MULTILINE,
)
AT_ENGINE = re.compile(
    r"^\s+at: (?P<func>\S+) \((?P<eng>[^)]+\.(?:cpp|h|mm):\d+)\)$",
    re.MULTILINE,
)
AT_SHADER = re.compile(
    r"^\s+at: \(null\) \(:?(?P<line>\d+)\)$",
    re.MULTILINE,
)
AT_GENERIC = re.compile(
    r"^\s+at: (?P<func>\S+) \((?P<loc>[^)]*)\)$",
    re.MULTILINE,
)

# --- message 里抽 res_path 的兜底正则（§5.1"字段怎么填"：at: 是引擎路径时从 message 抽） ---

_MSG_WRAPPER_LOAD = re.compile(
    r'Failed to load script "(?P<path>res://[^"]+)" with error "(?:Parse error|Compilation failed)"\.'
)
_MSG_FAILED_LOADING = re.compile(r"Failed loading resource: (?P<path>res://\S+?)\.$")
_MSG_BUSY = re.compile(r"Busy\. \[Resource file (?P<path>res://[^:]+):(?P<line>\d+)\]")

# --- pointer 文案：target_res_path 只从这两个抽（§4"陷阱"/§5.2） ---

_MSG_POINTER_PRELOAD = re.compile(r'Could not preload resource script "(?P<path>res://[^"]+)"\.')
_MSG_POINTER_RESOLVE = re.compile(r'Could not resolve script "(?P<path>res://[^"]+)"\.')

# --- §5.2 表格：inner message 再分类。按顺序尝试，命中第一个即用；顺序即表格顺序。 ---

_MSG_IDENTIFIER_NOT_FOUND = re.compile(r"Compile Error: Identifier not found: (?P<sym>\S+)")
_MSG_HIDES_AUTOLOAD = re.compile(r'Parse Error: Class "(?P<sym>[^"]+)" hides an autoload singleton\.')
_MSG_NOT_DECLARED = re.compile(r'Parse Error: Identifier "(?P<sym>[^"]+)" not declared in the current scope\.')
_MSG_DEPENDED_SCRIPTS = re.compile(r"Compile Error: Failed to compile depended scripts\.")
_MSG_UID_DUPLICATE = re.compile(r"UID duplicate detected between (?P<a>res://\S+) and (?P<b>res://\S+)\.")
_MSG_DEBUGGER_PLUGIN = re.compile(r"Plugin is not attached to debugger\.")
_MSG_SHADER_COMPILE_FAILED = re.compile(r"Shader compilation failed\.")
_MSG_SHADER_INVALID_ARGS = re.compile(r'Invalid arguments for the built-in function: "(?P<func>[^"]+)"\.')


def _stream_events(text: str, *, source_stream: Literal["stdout", "stderr"]) -> list[RawEvent]:
    """把一个流（stdout 或 stderr）切成 `RawEvent` 列表。"""
    if not text:
        return []

    lines = text.splitlines()
    n = len(lines)
    events: list[RawEvent] = []
    i = 0
    while i < n:
        line = lines[i]
        m = PREFIX.match(line)
        if not m:
            i += 1
            continue

        prefix = m.group("prefix")
        message = m.group("message")
        at_line = lines[i + 1] if i + 1 < n else ""

        at_function: str | None = None
        at_location: str | None = None
        res_path: str | None = None
        target_res_path: str | None = None
        line_in_project: int | None = None
        engine_location: str | None = None
        consumed_at_line = False

        script_m = AT_SCRIPT.match(at_line)
        engine_m = AT_ENGINE.match(at_line) if not script_m else None
        shader_m = AT_SHADER.match(at_line) if not (script_m or engine_m) else None
        generic_m = AT_GENERIC.match(at_line) if not (script_m or engine_m or shader_m) else None

        if script_m:
            consumed_at_line = True
            at_function = script_m.group("func")
            at_location = f"{script_m.group('res')}:{script_m.group('line')}"
            res_path = script_m.group("res")
            if prefix == "SCRIPT ERROR":
                line_in_project = int(script_m.group("line"))
        elif engine_m:
            consumed_at_line = True
            at_function = engine_m.group("func")
            at_location = engine_m.group("eng")
            engine_location = engine_m.group("eng")
        elif shader_m:
            consumed_at_line = True
            at_location = at_line.strip()
        elif generic_m:
            consumed_at_line = True
            at_function = generic_m.group("func")
            at_location = generic_m.group("loc")
            if re.search(r"\.(?:cpp|h|mm):\d+$", generic_m.group("loc")):
                engine_location = generic_m.group("loc")

        if res_path is None:
            for rx in (_MSG_WRAPPER_LOAD, _MSG_FAILED_LOADING, _MSG_BUSY):
                mm = rx.search(message)
                if mm:
                    res_path = mm.group("path")
                    break

        for rx in (_MSG_POINTER_PRELOAD, _MSG_POINTER_RESOLVE):
            mm = rx.search(message)
            if mm:
                target_res_path = mm.group("path")
                break

        raw_block_lines = [line]
        if consumed_at_line:
            raw_block_lines.append(at_line)
        raw_block = "\n".join(raw_block_lines)

        events.append(
            RawEvent(
                prefix=prefix,  # type: ignore[arg-type]
                message=message,
                at_function=at_function,
                at_location=at_location,
                res_path=res_path,
                target_res_path=target_res_path,
                line_in_project=line_in_project,
                engine_location=engine_location,
                source_stream=source_stream,
                raw_block=raw_block,
            )
        )

        i += 2 if consumed_at_line else 1

    return events


def parse_raw_events(stdout: str, stderr: str) -> list[RawEvent]:
    """把一份 stdout/stderr 切成 `RawEvent` 列表（§5.1）。

    先按"前缀行"切块，再读下一块是否是合法的 `at:` continuation；不要先写"一个大
    regex 扫全文"（方案文档 §3："必须先切行、再分类、再过滤"）。

    stderr 优先解析（黄金样例全部来自 stderr），stdout 附加在后面——V5 的 stdout 里
    shader 相关的 `E   4->` 源码上下文属于增强信息，本函数只把它们当普通事件切出来，
    不在这里做"挂到对应 shader 事件 raw_block"的关联（那属于更高层的展示逻辑，
    §5.3 提到的这条增强不是 `root_cause` 判定所必需，当前实现从简）。
    """
    events = _stream_events(stderr, source_stream="stderr")
    events.extend(_stream_events(stdout, source_stream="stdout"))
    return events


def _classify_message(prefix: str, message: str) -> tuple[Kind, str | None, Role]:
    """按 §5.2 表格顺序尝试匹配，返回 (kind, symbol, 默认 role)。

    未匹配的 `ERROR:`/`SCRIPT ERROR:` 默认为 engine_error/root_cause——宁可不滤，
    不可默删（§5.2 末尾）。
    """
    if prefix == "SHADER ERROR":
        m = _MSG_SHADER_INVALID_ARGS.search(message)
        if m:
            return "shader_error", m.group("func"), "root_cause"
        return "shader_error", None, "root_cause"

    if prefix == "WARNING":
        if _MSG_UID_DUPLICATE.search(message):
            return "warning", None, "root_cause"  # 簇根；R5 决定最终形态
        return "warning", None, "root_cause"  # 默认 root_cause，R7 会降级（不进 root_cause_errors）

    # SCRIPT ERROR / ERROR 共用下面的表
    m = _MSG_IDENTIFIER_NOT_FOUND.search(message)
    if m:
        return "compile_error", m.group("sym"), "root_cause"  # 待 autoload 规则（R2）

    # 注意：hides-autoload-singleton / not-declared 这两条在 §5.2 表里就是 kind=parse_error
    # 的具体文案，本函数只负责 kind/symbol，不在这里直接判定 role="protected"——是否
    # protected 由 §7.1（`rules/protect.py`）统一按"kind=parse_error 且非 pointer"来
    # 判定，这里保持中性默认值 "root_cause"，避免同一条规则在两个模块里各判一次。
    m = _MSG_HIDES_AUTOLOAD.search(message)
    if m:
        return "parse_error", m.group("sym"), "root_cause"

    m = _MSG_NOT_DECLARED.search(message)
    if m:
        return "parse_error", m.group("sym"), "root_cause"

    if _MSG_POINTER_PRELOAD.search(message) or _MSG_POINTER_RESOLVE.search(message):
        return "parse_error", None, "pointer"

    if _MSG_DEPENDED_SCRIPTS.search(message):
        return "compile_error", None, "symptom"

    if _MSG_WRAPPER_LOAD.search(message):
        return "resource_error", None, "symptom"

    if _MSG_FAILED_LOADING.search(message) or _MSG_BUSY.search(message):
        return "resource_error", None, "root_cause"  # UID 簇候选；R5 可能改写为 cluster_member

    if _MSG_DEBUGGER_PLUGIN.search(message):
        return "engine_error", None, "infra_noise"

    if _MSG_SHADER_COMPILE_FAILED.search(message):
        return "shader_error", None, "symptom"

    if message.startswith("Parse Error:"):
        # "其余 Parse Error"：§5.2 表里默认就是 root_cause，不是 protected。
        # §7.1 会把"kind=parse_error 且非 pointer"的事件统一升级为 protected
        # （覆盖本函数刚判定的这一条，以及上面 hides-autoload/not-declared 两条）。
        return "parse_error", None, "root_cause"

    if message.startswith("Compile Error:"):
        return "compile_error", None, "root_cause"

    return "engine_error", None, "root_cause"


def classify(events: list[RawEvent]) -> list[ClassifiedEvent]:
    """对每条 `RawEvent` 的 `message` 按 §5.2 表格再分类，产出默认角色的 `ClassifiedEvent`。

    同时调用 `signature.py` 填好 `local_signature`（见模块 docstring"实现顺序的一处例外"）。
    这一步只填默认值，§7.1 的 protected 标记与 R1–R7 的过滤判断由 `pipeline.py`
    编排的 `rules/*.py` 负责，这里不做。
    """
    classified: list[ClassifiedEvent] = []
    for event in events:
        kind, symbol, role = _classify_message(event.prefix, event.message)

        # pointer 事件的 symbol 语义上等于 target_res_path（方案文档 §4 数据模型注解）
        if role == "pointer" and event.target_res_path:
            symbol = event.target_res_path

        normalized = _sig.normalize_message(event.message, res_path=event.res_path, symbol=symbol)
        local_sig = _sig.local_signature(
            kind=kind,
            res_path=event.res_path,
            symbol=symbol,
            normalized_message=normalized,
        )

        classified.append(
            ClassifiedEvent(
                prefix=event.prefix,
                message=event.message,
                at_function=event.at_function,
                at_location=event.at_location,
                res_path=event.res_path,
                target_res_path=event.target_res_path,
                line_in_project=event.line_in_project,
                engine_location=event.engine_location,
                source_stream=event.source_stream,
                raw_block=event.raw_block,
                kind=kind,
                symbol=symbol,
                local_signature=local_sig,
                role=role,
            )
        )
    return classified
