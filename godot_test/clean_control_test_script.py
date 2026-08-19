#!/usr/bin/env python3
"""CleanControl headless CLI 冷/热缓存回归测试脚本。

对照 working_notebook/day1/reports/CLI.md 的指令集，针对单个指令号
（V1-V8、V7S、V8S、A3）在 CleanControl 项目上做重复测试：

- 重复 3 次，每次都测一轮"干净 .godot/ 缓存"（cold）和一轮"热缓存"（hot）；
- 每次运行单独计时，超时 15 秒；
- 每次运行都放在新的进程组（session）里，超时后对整个进程组发 SIGKILL；
- stdout / stderr / exit code / 耗时分别落盘，另外生成 JSON 汇总和 TSV 速览表。

用法：
    python3 clean_control_test_script.py V1
    python3 clean_control_test_script.py a3
    GODOT_BIN=/path/to/godot4 python3 clean_control_test_script.py V7S

    # 覆盖 V2/V7S/V8S 使用的 --script 目标（Godot 资源路径，非文件系统路径）
    python3 clean_control_test_script.py V2 --script res://other.gd

    # 覆盖默认测试项目目录（默认固定为脚本所在目录下的 clean_control/）
    python3 clean_control_test_script.py V1 --project-dir /path/to/other_project
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

SCRIPT_DIR = Path(__file__).resolve().parent
# 默认测试项目目录：始终基于本脚本文件自身的绝对路径（Path(__file__).resolve()）
# 计算得到，与当前工作目录（运行 python3 的 cwd）无关。可用 --project-dir 覆盖。
DEFAULT_PROJECT_DIR = SCRIPT_DIR / "clean_control"
LOG_ROOT = SCRIPT_DIR / "clean_control_log"

# V2/V7S/V8S 默认使用的 --script 目标：Godot 资源路径（res://...），
# 不是文件系统路径，按项目根（--path/--project-dir 指向的目录）解析。
# 可用 --script 覆盖。
DEFAULT_SCRIPT_GD = "res://main.gd"

REPEAT = 3
TIMEOUT_SEC = 15


def normalize_script_arg(raw: str) -> str:
    """把用户传入的 --script 值规整成 Godot 资源路径（res://...）。

    允许传 `res://foo.gd`、`foo.gd`、`/foo.gd`、`.gd`（等价于默认脚本）等写法。
    """
    raw = raw.strip()
    if not raw or raw == ".gd":
        return DEFAULT_SCRIPT_GD
    if raw.startswith("res://"):
        return raw
    return "res://" + raw.lstrip("/")


def find_godot_binary() -> str:
    env_bin = os.environ.get("GODOT_BIN")
    if env_bin:
        return env_bin
    for name in ("godot4", "godot", "Godot"):
        found = shutil.which(name)
        if found:
            return found
    raise SystemExit(
        "找不到 Godot 可执行文件。请把 godot4 放进 PATH，或设置环境变量 "
        "GODOT_BIN 指向可执行文件路径。"
    )


def build_command_table(
    godot_bin: str, project_dir: Path, script_gd: str
) -> dict[str, tuple[list[str], Optional[Path]]]:
    """按 CLI.md 的指令格式列出每个指令号对应的 (argv, cwd)。

    V7/V8 在 CLI.md 中写作 "V1/V2 + --verbose"、"V1/V2 + --debug"，
    此处拆成 V7（基于 V1）/ V7S（基于 V2）、V8（基于 V1）/ V8S（基于 V2）
    两组，以便分别验证项目级与单文件级 check 加上对应 flag 后的差异。
    A3（--recovery-mode）按 CLI.md 说明仅用于 addon 类项目对照，
    这里默认仍指向 project_dir（默认 clean_control）作为基线对照，
    如需真实 addon 项目请通过 --project-dir 传入其他项目路径。

    project_dir：传给 --path 的项目目录，取自 resolve_instruction 已解析出的
    绝对路径（见 main() 中 --project-dir 的处理）。
    script_gd：传给 --script 的 Godot 资源路径，仅 V2/V7S/V8S 使用。
    """
    p = str(project_dir)
    return {
        "V1": ([godot_bin, "--headless", "--path", p, "--check-only", "--quit"], None),
        "V2": ([godot_bin, "--headless", "--path", p, "--script", script_gd, "--check-only", "--quit"], None),
        "V3": ([godot_bin, "--headless", "--path", p, "--editor", "--import", "--quit"], None),
        "V4": ([godot_bin, "--headless", "--path", p, "--import", "--quit"], None),
        "V5": ([godot_bin, "--headless", "--path", p, "--quit"], None),
        "V6": ([godot_bin, "--headless", "--path", p, "--quit-after", "2"], None),
        "V7": ([godot_bin, "--headless", "--path", p, "--check-only", "--quit", "--verbose"], None),
        "V7S": ([godot_bin, "--headless", "--path", p, "--script", script_gd, "--check-only", "--quit", "--verbose"], None),
        "V8": ([godot_bin, "--headless", "--path", p, "--check-only", "--quit", "--debug"], None),
        "V8S": ([godot_bin, "--headless", "--path", p, "--script", script_gd, "--check-only", "--quit", "--debug"], None),
        "A3": ([godot_bin, "--headless", "--editor", "--recovery-mode", "--path", p, "--import", "--quit"], None),
    }


def resolve_instruction(
    instr: str, godot_bin: str, project_dir: Path, script_gd: str
) -> tuple[str, list[str], Optional[Path]]:
    table = build_command_table(godot_bin, project_dir, script_gd)
    key = instr.strip().upper()
    if key not in table:
        valid = ", ".join(sorted(table.keys(), key=lambda k: (len(k), k)))
        raise SystemExit(f"未知指令号 '{instr}'。可用指令号：{valid}")
    argv, cwd = table[key]
    return key, argv, cwd


def clean_cache(project_dir: Path) -> None:
    cache_dir = project_dir / ".godot"
    if cache_dir.exists():
        shutil.rmtree(cache_dir, ignore_errors=True)


def run_once(
    argv: list[str], cwd: Optional[Path], log_dir: Path, tag: str, project_dir: Path
) -> dict:
    out_path = log_dir / f"{tag}.stdout.log"
    err_path = log_dir / f"{tag}.stderr.log"

    started_at = datetime.now(timezone.utc).isoformat()
    t0 = time.monotonic()
    timed_out = False
    proc: Optional[subprocess.Popen] = None
    rc: Optional[int] = None

    with open(out_path, "wb") as f_out, open(err_path, "wb") as f_err:
        try:
            proc = subprocess.Popen(
                argv,
                cwd=str(cwd) if cwd else None,
                stdout=f_out,
                stderr=f_err,
                start_new_session=True,  # 独立 session/进程组，pgid == pid
            )
            rc = proc.wait(timeout=TIMEOUT_SEC)
        except subprocess.TimeoutExpired:
            timed_out = True
            if proc is not None:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except ProcessLookupError:
                    pass
                try:
                    rc = proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    rc = proc.returncode

    wall = round(time.monotonic() - t0, 3)
    finished_at = datetime.now(timezone.utc).isoformat()

    return {
        "tag": tag,
        "cmd": argv,
        "cwd": str(cwd) if cwd else str(project_dir),
        "pid": proc.pid if proc else None,
        "returncode": rc,
        "timed_out": timed_out,
        "wall_time_sec": wall,
        "started_at": started_at,
        "finished_at": finished_at,
        "stdout_file": str(out_path.relative_to(SCRIPT_DIR)),
        "stderr_file": str(err_path.relative_to(SCRIPT_DIR)),
        "stdout_bytes": out_path.stat().st_size,
        "stderr_bytes": err_path.stat().st_size,
    }


def append_matrix(matrix_path: Path, record: dict) -> None:
    line = (
        f"{record['tag']}\trc={record['returncode']}\t"
        f"wall={record['wall_time_sec']}s\ttimed_out={record['timed_out']}"
    )
    print(line)
    with open(matrix_path, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="CleanControl headless CLI 冷/热缓存回归测试脚本（对照 CLI.md 指令集）"
    )
    parser.add_argument(
        "instruction",
        help="指令号，例如 V1、V5、V7S、A3（大小写不敏感，对应 CLI.md 指令集表）",
    )
    parser.add_argument(
        "--script",
        dest="script",
        default=None,
        help=(
            "覆盖 V2/V7S/V8S 使用的 --script 目标（Godot 资源路径 res://...，"
            "非文件系统路径）。可传 'res://foo.gd'、'foo.gd' 等，默认 "
            f"'{DEFAULT_SCRIPT_GD}'。对不使用 --script 的指令号无效。"
        ),
    )
    parser.add_argument(
        "--project-dir",
        dest="project_dir",
        default=None,
        help=(
            "覆盖默认测试项目目录（传给各指令的 --path）。可传绝对路径，"
            "或相对当前工作目录的相对路径，脚本会自动解析为绝对路径。默认为 "
            f"本脚本所在目录下的 clean_control/（即 '{DEFAULT_PROJECT_DIR}'）。"
        ),
    )
    args = parser.parse_args()

    project_dir = (
        Path(args.project_dir).expanduser().resolve()
        if args.project_dir
        else DEFAULT_PROJECT_DIR
    )
    script_gd = normalize_script_arg(args.script) if args.script else DEFAULT_SCRIPT_GD

    project_file = project_dir / "project.godot"
    if not project_file.exists():
        raise SystemExit(f"未找到 project.godot：{project_file}")

    godot_bin = find_godot_binary()
    instr_key, argv_template, cwd = resolve_instruction(
        args.instruction, godot_bin, project_dir, script_gd
    )

    log_dir = LOG_ROOT / instr_key
    log_dir.mkdir(parents=True, exist_ok=True)
    matrix_path = LOG_ROOT / "_matrix.tsv"

    records: list[dict] = []
    for i in range(1, REPEAT + 1):
        clean_cache(project_dir)
        cold_record = run_once(
            argv_template, cwd, log_dir, f"{instr_key}_iter{i}_cold", project_dir
        )
        records.append(cold_record)
        append_matrix(matrix_path, cold_record)

        hot_record = run_once(
            argv_template, cwd, log_dir, f"{instr_key}_iter{i}_hot", project_dir
        )
        records.append(hot_record)
        append_matrix(matrix_path, hot_record)

    summary_path = log_dir / f"{instr_key}_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "instruction": instr_key,
                "godot_bin": godot_bin,
                "project_dir": str(project_dir),
                "script_gd": script_gd,
                "repeat": REPEAT,
                "timeout_sec": TIMEOUT_SEC,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "runs": records,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )

    print(f"[{instr_key}] 完成 {len(records)} 次运行（{REPEAT} 次 x 冷/热各一轮）")
    print(f"[{instr_key}] 日志目录：{log_dir}")
    print(f"[{instr_key}] 汇总文件：{summary_path}")


if __name__ == "__main__":
    sys.exit(main())


