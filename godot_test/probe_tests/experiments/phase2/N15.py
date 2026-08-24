#!/usr/bin/env python3
"""N15 正式采集脚本：converter 与 ProjectUpgradeTool 的 CLI 能力门。P2-1。

按 README.md P2-1 步骤表采集，并补上 reports/README.md 判据表里多出的
`max_file_kb` / `max_line_size` 参数验证。能力矩阵与职责判定交给
analyzer/capability.py；本脚本只落盘，不下结论（不写 pipeline 形状、
不写 CONFIRMED）。假 Godot 禁止用于本实验——能力门问的是真实二进制。

步骤（对应 README §P2-1 步骤表 + reports/README.md 判据表的补充项）：

  1   --help                                    不涉及项目        探测 convert/3to4/upgrade 相关入口是否存在
  2   --validate-conversion-3to4                副本 A (validate) 是否能对最小 config_version=4 项目调用成功
  3   --convert-3to4                             副本 B (convert)  是否真的改了文件（以 diff 为准，不看 stdout）
  3b  --convert-3to4 <max_file_kb> <max_line_size>  副本 B2 (convert-args)  是否接受这两个可选参数
  4   upgrade tool 入口探测（离线，读步骤 1 的 --help 原文）         有没有独立于 convert/validate 的 upgrade 入口
  5   V3  未转换副本 (v3-boundary-raw)  COLD     --import 单独能否替代 converter 的文本改写
  5b  V3  已转换副本 (v3-boundary-converted)  COLD  converter 转换后，V3 还会补哪些文件（UID / import cache）

步骤 2–5b 各用一个独立副本，不在同一工作区连续执行，保证文件变更可归因
（README §P2-1 判据）。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

PROBE_ROOT = Path(__file__).resolve().parents[2]
if str(PROBE_ROOT) not in sys.path:
    sys.path.insert(0, str(PROBE_ROOT))

from experiments.util import probe  # noqa: E402
from experiments.util.probe import (  # noqa: E402
    ARTIFACTS_DIR,
    BlockedError,
    ProbeError,
    StaleError,
)

N = "N15"
FIXTURE = "phase2/CP-MINIMAL"
CONVERT_ARGS = ("4096", "100000")  # max_file_kb, max_line_size；远大于 fixture 里任何文件

HELP_KEYWORDS = (
    "convert-3to4",
    "validate-conversion-3to4",
    "upgrade",
    "ProjectUpgradeTool",
    "3to4",
)


def main() -> int:
    import os

    os.environ.pop("PROBE_GODOT", None)

    try:
        run = probe.start(
            N,
            repeat_default=1,
            timeout_seconds=60,
            fixtures=(FIXTURE,),
        )
        if run.identity.fake:
            raise ProbeError(
                "BLOCKED: N15 正式采集禁止假 Godot（能力门问的是真实二进制）。"
                f" 当前可执行文件是 {run.identity.path}"
            )

        # 1  --help  不涉及项目  ×1
        help_rec = probe.run_help(run)
        help_dest = ARTIFACTS_DIR / help_rec["dir"]
        help_stdout = _read(help_dest / "stdout.log")
        help_stderr = _read(help_dest / "stderr.log")
        flags_found = _scan_help_flags(help_stdout + "\n" + help_stderr)
        _write_json(help_dest / "flags-found.json", flags_found)

        # 2  --validate-conversion-3to4  副本 A (validate)  ×1
        with probe.workspace(FIXTURE, group="validate") as ws:
            recs = run.measure_raw(
                ws,
                group="validate",
                step="validate-conversion-3to4",
                argv=[
                    "--headless",
                    "--path",
                    str(ws.path),
                    "--validate-conversion-3to4",
                    "--quit",
                ],
                cache="COLD",
                cmd_label="validate-conversion-3to4",
            )
            _write_no_file_content_changed(ARTIFACTS_DIR / recs[0]["dir"])

        # 3  --convert-3to4  副本 B (convert)  ×1
        with probe.workspace(FIXTURE, group="convert") as ws:
            recs = run.measure_raw(
                ws,
                group="convert",
                step="convert-3to4",
                argv=[
                    "--headless",
                    "--path",
                    str(ws.path),
                    "--convert-3to4",
                    "--quit",
                ],
                cache="COLD",
                cmd_label="convert-3to4",
            )
            convert_dest = ARTIFACTS_DIR / recs[0]["dir"]
            _write_file_change_summary(convert_dest)

        # 3b  --convert-3to4 <max_file_kb> <max_line_size>  副本 B2 (convert-args)  ×1
        with probe.workspace(FIXTURE, group="convert-args") as ws:
            recs = run.measure_raw(
                ws,
                group="convert-args",
                step="convert-3to4-args",
                argv=[
                    "--headless",
                    "--path",
                    str(ws.path),
                    "--convert-3to4",
                    *CONVERT_ARGS,
                    "--quit",
                ],
                cache="COLD",
                cmd_label="convert-3to4-args",
            )
            args_dest = ARTIFACTS_DIR / recs[0]["dir"]
            _write_file_change_summary(args_dest)
            _write_json(
                args_dest / "args-echo.json",
                {"max_file_kb": CONVERT_ARGS[0], "max_line_size": CONVERT_ARGS[1]},
            )

        # 4  upgrade tool 入口探测（离线；不发起新进程；不静默跳过）
        upgrade_dest = run.artifact_root / "upgrade-tool"
        upgrade_dest.mkdir(parents=True, exist_ok=True)
        upgrade_hit = flags_found.get("upgrade", []) or flags_found.get("ProjectUpgradeTool", [])
        _write_json(
            upgrade_dest / "skip.json",
            {
                "searched_in": str((help_dest / "stdout.log").relative_to(PROBE_ROOT)),
                "help_text_sha256": _sha256_text(help_stdout + help_stderr),
                "found": bool(upgrade_hit),
                "hits": upgrade_hit,
                "reason": (
                    "found upgrade/ProjectUpgradeTool keyword in --help output"
                    if upgrade_hit
                    else "no upgrade/ProjectUpgradeTool keyword found in --help output; "
                    "step 4 (upgrade tool invocation) is not applicable this run"
                ),
            },
        )

        # 5  V3  未转换副本 (v3-boundary-raw)  COLD  ×1
        # --import 单独作用于 3.x 语法/config_version=4 项目时的边界。
        with probe.workspace(FIXTURE, group="v3-boundary-raw") as ws:
            run.measure(ws, group="v3-boundary-raw", step="v3", cmd="V3", cache="COLD")

        # 5b  V3  已转换副本 (v3-boundary-converted)  COLD  ×1
        # 先 convert-3to4，再 V3：converter 之后，import 还会补哪些文件。
        with probe.workspace(FIXTURE, group="v3-boundary-converted") as ws:
            run.measure_raw(
                ws,
                group="v3-boundary-converted",
                step="convert-3to4",
                argv=[
                    "--headless",
                    "--path",
                    str(ws.path),
                    "--convert-3to4",
                    "--quit",
                ],
                cache="COLD",
                cmd_label="convert-3to4",
            )
            probe.cold(ws)
            run.measure(
                ws, group="v3-boundary-converted", step="v3", cmd="V3", cache="COLD"
            )

        run.finish(
            exports={
                "kind": "converter-capabilities",
                "help_contains": {
                    kw: bool(flags_found.get(kw)) for kw in HELP_KEYWORDS
                },
                "upgrade_tool_entry_found": bool(upgrade_hit),
                "groups": [
                    "help",
                    "validate",
                    "convert",
                    "convert-args",
                    "upgrade-tool",
                    "v3-boundary-raw",
                    "v3-boundary-converted",
                ],
            }
        )
    except (BlockedError, StaleError, ProbeError) as exc:
        sys.stderr.write(f"{exc}\n")
        return 2
    return 0


def _scan_help_flags(text: str) -> dict[str, list[str]]:
    """在 --help 原文里找每个关键词命中的整行原文（不判断"是否可用"）。"""
    hits: dict[str, list[str]] = {kw: [] for kw in HELP_KEYWORDS}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        for kw in HELP_KEYWORDS:
            if kw.lower() in stripped.lower():
                hits[kw].append(_strip_ansi(stripped))
    return hits


_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


_CONVERT_FILE_RE = re.compile(r'file - "([^"]+)"')
_CHANGED_RE = re.compile(r"File was changed", re.I)
_NOT_CHANGED_RE = re.compile(r"File was (?:NOT|not) changed", re.I)


def _parse_convert_stdout(text: str) -> dict[str, bool | None]:
    """从 --convert-3to4 的 stdout 里按文件名提取"stdout 是否报告改动"。

    只做文本抽取，不代表真实文件是否变化——真实变化以 sha256 diff 为准
    （见 _write_file_change_summary）。
    """
    reported: dict[str, bool | None] = {}
    lines = text.splitlines()
    for i, line in enumerate(lines):
        m = _CONVERT_FILE_RE.search(line)
        if not m:
            continue
        filename = m.group(1)
        status: bool | None = None
        for follow in lines[i + 1 : i + 3]:
            if _NOT_CHANGED_RE.search(follow):
                status = False
                break
            if _CHANGED_RE.search(follow):
                status = True
                break
        reported[filename] = status
    return reported


def _write_file_change_summary(dest: Path) -> None:
    """交叉核对 stdout 报告的"改了没"与 fs-before/fs-after 的 sha256 diff。

    专门标出"stdout 说变了但字节没变"（或反过来）的文件，供
    analyzer/capability.py 与后续 N21 的分类体系直接复用。
    """
    stdout_text = _read(dest / "stdout.log")
    reported = _parse_convert_stdout(stdout_text)
    fs_before = _read_json(dest / "fs-before.json")
    fs_after = _read_json(dest / "fs-after.json")
    before_files = (fs_before or {}).get("files") or {}
    after_files = (fs_after or {}).get("files") or {}
    all_paths = sorted(set(before_files) | set(after_files) | set(reported))

    summary: list[dict[str, Any]] = []
    for path in all_paths:
        before = before_files.get(path)
        after = after_files.get(path)
        actually_changed = (before is None) != (after is None) or (
            before is not None and after is not None and before["sha256"] != after["sha256"]
        )
        reported_changed = None
        for name, status in reported.items():
            if path == name or path.endswith("/" + name):
                reported_changed = status
                break
        summary.append(
            {
                "path": path,
                "actually_changed": actually_changed,
                "reported_changed": reported_changed,
                "mismatch": (
                    reported_changed is not None and reported_changed != actually_changed
                ),
            }
        )
    _write_json(dest / "file-change-summary.json", summary)


def _write_no_file_content_changed(dest: Path) -> None:
    """validate 步骤的轻量版摘要：只确认文件内容（不含 .godot/）是否真的没被改。

    --validate-conversion-3to4 按设计不应改任何项目文件，只是预览。
    """
    fs_before = _read_json(dest / "fs-before.json")
    fs_after = _read_json(dest / "fs-after.json")
    before_files = {
        k: v for k, v in ((fs_before or {}).get("files") or {}).items() if not k.startswith(".godot/")
    }
    after_files = {
        k: v for k, v in ((fs_after or {}).get("files") or {}).items() if not k.startswith(".godot/")
    }
    unchanged = before_files == after_files
    _write_json(
        dest / "content-unchanged.json",
        {"project_files_unchanged": unchanged, "excluded_prefix": ".godot/"},
    )


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _sha256_text(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


if __name__ == "__main__":
    sys.exit(main())
