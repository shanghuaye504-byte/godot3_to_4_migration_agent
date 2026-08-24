"""probe：多个实验共用的同构落盘 API。

采集脚本按 `from experiments.util import probe` 使用本模块。
调用约定见 ARCHITECTURE.md §3 / §5；落盘形状见 §6；V1–V8 语义见 README §0.2。

干跑：PROBE_GODOT 指向任意可执行文件（util 自测用 testing/fake_godot.py）。
假二进制产物不得被任何「已确认」结论引用。
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import signal
import subprocess
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

PROBE_ROOT = Path(__file__).resolve().parents[2]
FIXTURES_DIR = PROBE_ROOT / "fixtures"
ANNOTATIONS_DIR = PROBE_ROOT / "annotations"
DERIVED_DIR = PROBE_ROOT / "derived"
FRAGMENTS_DIR = PROBE_ROOT / "experiments" / "common" / "fragments"
ARTIFACTS_DIR = PROBE_ROOT / "artifacts"
WORKSPACES_DIR = PROBE_ROOT / "workspaces"
LATEST_DIR = ARTIFACTS_DIR / "latest"

SENTINEL_NAME = "__probe_sentinel.gd"
SENTINEL_RES = f"res://{SENTINEL_NAME}"
WARM_MARKER = Path(".godot") / ".probe-warm-ok.json"
DEFAULT_TIMEOUT = 30
DEFAULT_REPEAT = 3
CACHE_STATES = ("COLD", "WARM", "PRESERVE")
HELPER_PREFIX = "__probe_"

_VERSION_RE = re.compile(r"Godot Engine v([^\s]+)", re.I)
_SHA1_RE = re.compile(r"\b([0-9a-f]{7,40})\b", re.I)

_current_run: Run | None = None


class ProbeError(Exception):
    """util 运行期错误。"""


class BlockedError(ProbeError):
    """上游缺失或不可用，实验不得继续。"""


class StaleError(ProbeError):
    """上游 inputs_digest 已变，默认拒绝。"""


class ManualGateError(ProbeError):
    """derived patch 的 build hash 空或不一致，退回 GUI。"""


@dataclass
class Workspace:
    """临时工作区。path 是副本根目录；fixture 形如 phase1/CleanControl。"""

    path: Path
    fixture: str
    fixture_src: Path
    fixture_digest_before: str
    group_id: str | None = None
    warmed: bool = False

    def __fspath__(self) -> str:
        return str(self.path)


@dataclass
class GodotIdentity:
    executable: list[str]
    path: str
    version: str
    build_hash: str
    binary_sha1: str
    platform: str
    fake: bool
    stdout: str
    stderr: str


@dataclass
class ProcessResult:
    rc: int | None
    signal: int | None
    timed_out: bool
    wall_time: float
    stdout: str
    stderr: str
    pid: int | None = None


@dataclass
class Run:
    N: str
    run_id: str
    repeat_default: int
    timeout_seconds: int
    identity: GodotIdentity
    inputs_digest: str
    inputs: dict[str, Any]
    force_stale: bool
    artifact_root: Path
    measurements: list[dict[str, Any]] = field(default_factory=list)
    live_procs: list[subprocess.Popen] = field(default_factory=list)
    finished: bool = False

    def measure(
        self,
        ws: Workspace,
        *,
        group: str,
        step: str,
        cmd: str,
        cache: str,
        target: str | None = None,
        repeat: int | None = None,
        timeout_seconds: int | None = None,
        include: Sequence[str] | None = None,
        base: str | None = None,
    ) -> list[dict[str, Any]]:
        """一次测量的全部同构动作，对应 README 步骤表的一行。"""
        cache_state = _norm_cache(cache)
        n_repeat = self.repeat_default if repeat is None else int(repeat)
        timeout = self.timeout_seconds if timeout_seconds is None else int(timeout_seconds)
        if n_repeat < 1:
            raise ProbeError(f"repeat 必须 ≥ 1，得到 {n_repeat}")

        results: list[dict[str, Any]] = []
        # README §0.1：repeat_idx ∈ {1..R}
        for idx in range(1, n_repeat + 1):
            results.append(
                self._measure_once(
                    ws,
                    group=group,
                    step=step,
                    cmd=cmd,
                    cache_state=cache_state,
                    repeat_idx=idx,
                    target=target,
                    timeout=timeout,
                    include=include,
                    base=base,
                )
            )
        return results

    def _measure_once(
        self,
        ws: Workspace,
        *,
        group: str,
        step: str,
        cmd: str,
        cache_state: str,
        repeat_idx: int,
        target: str | None,
        timeout: int,
        include: Sequence[str] | None,
        base: str | None,
    ) -> dict[str, Any]:
        uses_sentinel = _cmd_uses_sentinel(cmd, base=base, target=target)

        def _build(ws_path: Path) -> list[str]:
            return _build_argv(self.identity.executable, cmd, ws_path, target=target, base=base)

        return self._record_measurement(
            ws,
            group=group,
            step=step,
            cmd_label=cmd,
            cache_state=cache_state,
            repeat_idx=repeat_idx,
            timeout=timeout,
            build_argv=_build,
            uses_sentinel=uses_sentinel,
            sentinel_include=include,
            extra_metadata={"target": target, "base": base},
        )

    def measure_raw(
        self,
        ws: Workspace,
        *,
        group: str,
        step: str,
        argv: Sequence[str],
        cache: str,
        cmd_label: str,
        repeat: int | None = None,
        timeout_seconds: int | None = None,
    ) -> list[dict[str, Any]]:
        """一次原始命令行测量，供 V1–V8 之外的一次性能力探测使用（例如 N15）。

        `argv` 由调用方给出完整命令行（不含可执行文件本身，即不含
        `self.identity.executable`——本函数会自动前置）；`cmd_label` 只是
        写进 `metadata.json.cmd` / index.md 供人和 analyzer 识别，不参与
        README §0.2 的 V1–V8 语义（不触发哨兵、不做 V-code 专属校验）。
        """
        cache_state = _norm_cache(cache)
        n_repeat = self.repeat_default if repeat is None else int(repeat)
        timeout = self.timeout_seconds if timeout_seconds is None else int(timeout_seconds)
        if n_repeat < 1:
            raise ProbeError(f"repeat 必须 ≥ 1，得到 {n_repeat}")

        fixed_argv = list(self.identity.executable) + list(argv)

        results: list[dict[str, Any]] = []
        for idx in range(1, n_repeat + 1):
            results.append(
                self._record_measurement(
                    ws,
                    group=group,
                    step=step,
                    cmd_label=cmd_label,
                    cache_state=cache_state,
                    repeat_idx=idx,
                    timeout=timeout,
                    build_argv=lambda _ws_path, _a=fixed_argv: list(_a),
                    uses_sentinel=False,
                    sentinel_include=None,
                    extra_metadata={"target": None, "base": None, "raw_argv": True},
                )
            )
        return results

    def _record_measurement(
        self,
        ws: Workspace,
        *,
        group: str,
        step: str,
        cmd_label: str,
        cache_state: str,
        repeat_idx: int,
        timeout: int,
        build_argv,
        uses_sentinel: bool,
        sentinel_include: Sequence[str] | None,
        extra_metadata: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """一次测量的全部同构落盘动作（应用缓存态、跑进程、写 artifact）。

        被 `_measure_once`（V1–V8）与 `measure_raw`（原始 argv）共用，
        两者只在"怎么算出 argv / 要不要哨兵"上不同，落盘形状必须一致
        才能让 analyzer 不区分来源地读取同一套 artifact（ARCHITECTURE §6）。
        """
        applied: list[str] = []
        if cache_state == "COLD":
            cold(ws)
            applied.append("cold")
        elif cache_state == "WARM":
            warm(ws)
            applied.append("warm")

        dest = (
            self.artifact_root
            / group
            / step
            / cache_state
            / str(repeat_idx)
        )
        dest.mkdir(parents=True, exist_ok=True)

        cache_before = _cache_manifest(ws.path)
        fs_before = snapshot(ws)
        sentinel_ctx = sentinel(ws, include=sentinel_include) if uses_sentinel else _null_cm()
        argv: list[str] = []
        proc: ProcessResult | None = None
        try:
            with sentinel_ctx:
                if uses_sentinel:
                    applied.append("sentinel")
                argv = build_argv(ws.path)
                proc = _run_process(argv, cwd=ws.path, timeout=timeout, live=self.live_procs)
        finally:
            if uses_sentinel:
                _remove_sentinel(ws.path)

        fs_after = snapshot(ws)
        cache_after = _cache_manifest(ws.path)
        if cache_state == "PRESERVE":
            applied.append("preserve")

        assert proc is not None
        record = {
            "group_id": group,
            "step_id": step,
            "cache_state": cache_state,
            "repeat_idx": repeat_idx,
            "cmd": cmd_label,
            "dir": str(dest.relative_to(ARTIFACTS_DIR)),
            "rc": proc.rc,
            "timed_out": proc.timed_out,
            "wall_time": proc.wall_time,
        }
        metadata = {
            "N": self.N,
            "run_id": self.run_id,
            "group_id": group,
            "step_id": step,
            "cache_state": cache_state,
            "repeat_idx": repeat_idx,
            "cmd": cmd_label,
            "fixture": ws.fixture,
            "inputs_digest": self.inputs_digest,
            "cwd": str(ws.path),
            "applied_helpers": applied,
            "env_overrides": _env_overrides(),
            "timeout_seconds": timeout,
            "godot": {
                "executable": self.identity.executable,
                "path": self.identity.path,
                "version": self.identity.version,
                "build_hash": self.identity.build_hash,
                "fake": self.identity.fake,
            },
            "force_stale": self.force_stale,
        }
        metadata.update(dict(extra_metadata or {}))
        _write_json(dest / "metadata.json", metadata)
        _write_json(dest / "argv.json", argv)
        (dest / "stdout.log").write_text(proc.stdout, encoding="utf-8")
        (dest / "stderr.log").write_text(proc.stderr, encoding="utf-8")
        _write_json(
            dest / "process-status.json",
            {
                "rc": proc.rc,
                "signal": proc.signal,
                "timed_out": proc.timed_out,
                "wall_time": proc.wall_time,
                "pid": proc.pid,
            },
        )
        _write_json(dest / "fs-before.json", fs_before)
        _write_json(dest / "fs-after.json", fs_after)
        (dest / "workspace.diff").write_text(diff(fs_before, fs_after), encoding="utf-8")
        _write_json(
            dest / "cache-manifest.json",
            {"before": cache_before, "after": cache_after},
        )
        self.measurements.append(record)
        return record

    def finish(self, exports: Mapping[str, Any] | None = None) -> Path:
        """写 index.md；非 fake 时写 artifacts/latest/<N>.json。"""
        _kill_live(self.live_procs)
        index_path = self.artifact_root / "index.md"
        index_path.write_text(_render_index(self), encoding="utf-8")
        payload = {
            "N": self.N,
            "run_id": self.run_id,
            "inputs_digest": self.inputs_digest,
            "inputs": self.inputs,
            "godot": {
                "path": self.identity.path,
                "version": self.identity.version,
                "build_hash": self.identity.build_hash,
                "binary_sha1": self.identity.binary_sha1,
                "platform": self.identity.platform,
                "fake": self.identity.fake,
            },
            "artifact_dir": str(self.artifact_root.relative_to(PROBE_ROOT)),
            "measurement_count": len(self.measurements),
            "exports": dict(exports or {}),
            "usable_for_confirmed": not self.identity.fake,
        }
        latest = LATEST_DIR / f"{self.N}.json"
        if self.identity.fake:
            # 假二进制不得成为下游「已确认」输入；仍把指针写到 run 目录供查阅。
            _write_json(self.artifact_root / "export.json", payload)
        else:
            LATEST_DIR.mkdir(parents=True, exist_ok=True)
            _write_json(latest, payload)
            _write_json(self.artifact_root / "export.json", payload)
        self.finished = True
        return index_path


def start(
    N: str,
    *,
    repeat_default: int = DEFAULT_REPEAT,
    timeout_seconds: int = DEFAULT_TIMEOUT,
    fixtures: Sequence[str] = (),
    derived: Sequence[str] = (),
    depends_on: Sequence[str] = (),
    force_stale: bool | None = None,
    run_id: str | None = None,
) -> Run:
    """建 run-id、采集环境身份、算 inputs_digest、校验上游。"""
    global _current_run
    force = _resolve_force_stale(force_stale)
    identity = _collect_identity()
    upstream = _load_upstreams(depends_on, identity=identity, force_stale=force)
    inputs = _collect_inputs(
        fixtures=fixtures,
        derived=derived,
        identity=identity,
        upstream=upstream,
    )
    digest = _digest_inputs(inputs)
    rid = run_id or _new_run_id()
    artifact_root = ARTIFACTS_DIR / rid / N
    artifact_root.mkdir(parents=True, exist_ok=True)
    run = Run(
        N=N,
        run_id=rid,
        repeat_default=repeat_default,
        timeout_seconds=timeout_seconds,
        identity=identity,
        inputs_digest=digest,
        inputs=inputs,
        force_stale=force,
        artifact_root=artifact_root,
    )
    _current_run = run
    _write_json(
        artifact_root / "run.json",
        {
            "N": N,
            "run_id": rid,
            "inputs_digest": digest,
            "godot": {
                "path": identity.path,
                "version": identity.version,
                "build_hash": identity.build_hash,
                "fake": identity.fake,
            },
            "force_stale": force,
        },
    )
    return run


@contextmanager
def workspace(fixture: str, *, group: str | None = None) -> Iterator[Workspace]:
    """复制 fixture 到 workspaces/，退出时销毁并校验原 fixture 仍 clean。"""
    run = _require_run()
    src = _fixture_path(fixture)
    if not src.is_dir():
        raise ProbeError(f"fixture 不存在: {fixture} ({src})")
    before = _tree_digest(src)
    slug = fixture.replace("/", "-")
    dest = WORKSPACES_DIR / f"{run.run_id}-{run.N}-{slug}"
    if dest.exists():
        shutil.rmtree(dest)
    WORKSPACES_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dest, symlinks=True)
    ws = Workspace(
        path=dest,
        fixture=fixture,
        fixture_src=src,
        fixture_digest_before=before,
        group_id=group,
    )
    try:
        yield ws
    finally:
        _kill_live(run.live_procs)
        if dest.exists():
            shutil.rmtree(dest, ignore_errors=True)
        after = _tree_digest(src)
        leftover = dest.exists()
        fixture_clean = after == before and _fixture_has_no_probe_files(src)
        cleanup = {
            "workspace_removed": not leftover,
            "workspace_path": str(dest),
            "fixture": fixture,
            "fixture_clean": fixture_clean,
            "fixture_digest_before": before,
            "fixture_digest_after": after,
            "probe_files_in_fixture": not _fixture_has_no_probe_files(src),
        }
        if group:
            (run.artifact_root / group).mkdir(parents=True, exist_ok=True)
            _write_json(run.artifact_root / group / "cleanup.json", cleanup)
        else:
            _write_json(run.artifact_root / f"cleanup-{slug}.json", cleanup)
        if leftover:
            raise ProbeError(f"工作区未删除: {dest}")
        if not fixture_clean:
            raise ProbeError(f"原 fixture 已脏: {fixture}")


def cold(ws: Workspace) -> None:
    """删除工作区 .godot/。对应缓存态 COLD。"""
    godot_dir = ws.path / ".godot"
    if godot_dir.exists():
        shutil.rmtree(godot_dir)
    ws.warmed = False


def warm(ws: Workspace) -> None:
    """跑一次 V3 并确认成功。已有 warm 标记则跳过。"""
    marker = ws.path / WARM_MARKER
    if marker.is_file() and (ws.path / ".godot").is_dir():
        ws.warmed = True
        return
    run = _require_run()
    argv = _build_argv(run.identity.executable, "V3", ws.path)
    proc = _run_process(argv, cwd=ws.path, timeout=run.timeout_seconds, live=run.live_procs)
    if proc.timed_out or proc.rc != 0:
        raise ProbeError(
            f"warm (V3) 失败 fixture={ws.fixture} rc={proc.rc} timed_out={proc.timed_out}"
        )
    (ws.path / ".godot").mkdir(parents=True, exist_ok=True)
    _write_json(
        marker,
        {
            "ok": True,
            "rc": proc.rc,
            "wall_time": proc.wall_time,
        },
    )
    ws.warmed = True


@contextmanager
def sentinel(ws: Workspace, include: Sequence[str] | None = None) -> Iterator[Path]:
    """写入 res://__probe_sentinel.gd，退出时删除。"""
    path = _write_sentinel(ws.path, include=include)
    try:
        yield path
    finally:
        _remove_sentinel(ws.path)


def apply_derived(ws: Workspace, name: str) -> Path:
    """校验 provenance.yaml 的 build hash 后 git apply patch.diff。"""
    run = _require_run()
    ddir = DERIVED_DIR / name
    patch = ddir / "patch.diff"
    prov_path = ddir / "provenance.yaml"
    if not patch.is_file():
        raise ManualGateError(f"derived patch 不存在: {patch}")
    prov = _read_simple_yaml(prov_path) if prov_path.is_file() else {}
    expected = str(prov.get("build_hash") or "").strip()
    actual = run.identity.build_hash
    if not expected or expected != actual:
        raise ManualGateError(
            f"derived {name} build hash 空或不一致 "
            f"(provenance={expected!r} current={actual!r})；退回 manual gate"
        )
    check = _git_apply(patch, ws.path, check=True)
    if check.returncode != 0:
        raise ManualGateError(
            f"git apply --check 失败 ({name}): {check.stderr or check.stdout}"
        )
    applied = _git_apply(patch, ws.path, check=False)
    if applied.returncode != 0:
        raise ProbeError(f"git apply 失败 ({name}): {applied.stderr or applied.stdout}")
    return patch


def run_help(run: Run, *, timeout_seconds: int = 10, group: str = "help", step: str = "1") -> dict[str, Any]:
    """跑一次 `--help`：不涉及项目，不建 workspace，不做 fs snapshot。

    只服务一次性能力探测（N15）：CLI 入口是否存在，只能从 `--help` 原文判断，
    不能只凭源码里存在对应代码就判定可用（README §P2-1 判据）。
    """
    dest = run.artifact_root / group / step
    dest.mkdir(parents=True, exist_ok=True)
    argv = list(run.identity.executable) + ["--help"]
    proc = _run_process(argv, cwd=PROBE_ROOT, timeout=timeout_seconds, live=run.live_procs)
    record = {
        "group_id": group,
        "step_id": step,
        "cache_state": "N/A",
        "repeat_idx": 1,
        "cmd": "--help",
        "dir": str(dest.relative_to(ARTIFACTS_DIR)),
        "rc": proc.rc,
        "timed_out": proc.timed_out,
        "wall_time": proc.wall_time,
    }
    metadata = {
        "N": run.N,
        "run_id": run.run_id,
        "group_id": group,
        "step_id": step,
        "cache_state": "N/A",
        "repeat_idx": 1,
        "cmd": "--help",
        "target": None,
        "base": None,
        "fixture": None,
        "inputs_digest": run.inputs_digest,
        "cwd": str(PROBE_ROOT),
        "applied_helpers": [],
        "env_overrides": _env_overrides(),
        "timeout_seconds": timeout_seconds,
        "godot": {
            "executable": run.identity.executable,
            "path": run.identity.path,
            "version": run.identity.version,
            "build_hash": run.identity.build_hash,
            "fake": run.identity.fake,
        },
        "force_stale": run.force_stale,
    }
    _write_json(dest / "metadata.json", metadata)
    _write_json(dest / "argv.json", argv)
    (dest / "stdout.log").write_text(proc.stdout, encoding="utf-8")
    (dest / "stderr.log").write_text(proc.stderr, encoding="utf-8")
    _write_json(
        dest / "process-status.json",
        {
            "rc": proc.rc,
            "signal": proc.signal,
            "timed_out": proc.timed_out,
            "wall_time": proc.wall_time,
            "pid": proc.pid,
        },
    )
    run.measurements.append(record)
    return record


def _git_apply(patch: Path, ws: Path, *, check: bool) -> subprocess.CompletedProcess:
    """对工作区应用 unified diff，不借用父仓库的 index。

    workspaces/ 在仓库树内（gitignore）。默认 `git apply` 会从仓库根解析
    `project.godot`，找不到就 Skipped 且 rc=0，patch 实际没打上。
    """
    cmd = ["git", "apply"]
    if check:
        cmd.append("--check")
    cmd.extend(["--verbose", str(patch)])
    env = os.environ.copy()
    env["GIT_CEILING_DIRECTORIES"] = str(ws.resolve().parent)
    proc = subprocess.run(cmd, cwd=str(ws), capture_output=True, text=True, env=env)
    text = f"{proc.stdout or ''}{proc.stderr or ''}"
    if proc.returncode == 0 and "Skipped patch" in text:
        return subprocess.CompletedProcess(
            proc.args,
            1,
            proc.stdout,
            (proc.stderr or "") + "Skipped patch treated as failure\n",
        )
    return proc


def snapshot(ws: Workspace | Path) -> dict[str, Any]:
    """工作区文件树快照（相对路径 → {sha256, size}）。"""
    root = Path(ws)
    files: dict[str, Any] = {}
    if not root.is_dir():
        return {"root": str(root), "files": files}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        files[rel] = {
            "sha256": _file_sha256(path),
            "size": path.stat().st_size,
        }
    return {"root": str(root), "files": files}


def diff(before: Mapping[str, Any], after: Mapping[str, Any]) -> str:
    """两个 snapshot 之间的路径级 diff（增删改）。"""
    a = (before or {}).get("files") or {}
    b = (after or {}).get("files") or {}
    keys = sorted(set(a) | set(b))
    lines = ["--- fs-before", "+++ fs-after"]
    changed = 0
    for key in keys:
        if key in a and key not in b:
            lines.append(f"- {key}  sha256={a[key]['sha256']} size={a[key]['size']}")
            changed += 1
        elif key not in a and key in b:
            lines.append(f"+ {key}  sha256={b[key]['sha256']} size={b[key]['size']}")
            changed += 1
        elif a[key]["sha256"] != b[key]["sha256"]:
            lines.append(
                f"~ {key}  {a[key]['sha256']} -> {b[key]['sha256']} "
                f"size {a[key]['size']} -> {b[key]['size']}"
            )
            changed += 1
    if changed == 0:
        lines.append("no file changes")
    return "\n".join(lines) + "\n"


def settings(ws: Workspace, fragment: str) -> None:
    """把 experiments/common/fragments/<fragment> 追加到临时 project.godot。"""
    src = FRAGMENTS_DIR / fragment
    if not src.is_file():
        raise ProbeError(f"fragment 不存在: {src}")
    project = ws.path / "project.godot"
    extra = src.read_text(encoding="utf-8")
    if not extra.endswith("\n"):
        extra += "\n"
    prev = project.read_text(encoding="utf-8") if project.is_file() else ""
    if prev and not prev.endswith("\n"):
        prev += "\n"
    project.write_text(prev + extra, encoding="utf-8")


def annotations(fixture: str) -> dict[str, Any]:
    """只读埋点表。不做匹配。"""
    path = _annotation_path(fixture)
    if not path.is_file():
        return {"path": str(path), "exists": False, "text": ""}
    return {
        "path": str(path),
        "exists": True,
        "text": path.read_text(encoding="utf-8"),
        "sha256": _file_sha256(path),
    }


# ---------------------------------------------------------------------------
# internals
# ---------------------------------------------------------------------------


def _require_run() -> Run:
    if _current_run is None:
        raise ProbeError("先调用 probe.start() 再建工作区 / 测量")
    return _current_run


def _resolve_force_stale(force_stale: bool | None) -> bool:
    if force_stale is not None:
        return bool(force_stale)
    return "--force-stale" in sys.argv or os.environ.get("PROBE_FORCE_STALE") == "1"


def _new_run_id() -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%Y%m%d-%H%M%S")


def _godot_executable() -> list[str]:
    raw = os.environ.get("PROBE_GODOT", "").strip()
    if not raw:
        raw = "/usr/local/bin/godot4"
    path = Path(raw)
    if path.suffix == ".py":
        return [sys.executable, str(path.resolve())]
    return [str(path)]


def _collect_identity() -> GodotIdentity:
    exe = _godot_executable()
    target = Path(exe[-1])
    binary_sha1 = _file_sha1(target) if target.is_file() else ""
    proc = _run_process(exe + ["--version"], cwd=PROBE_ROOT, timeout=10, live=None)
    blob = (proc.stdout or "") + "\n" + (proc.stderr or "")
    version = ""
    m = _VERSION_RE.search(blob)
    if m:
        version = m.group(1)
    elif proc.stdout.strip():
        version = proc.stdout.strip().splitlines()[0]
    build_hash = ""
    if version:
        build_hash = version.rsplit(".", 1)[-1]
    sha_m = _SHA1_RE.search(blob)
    if sha_m and not build_hash:
        build_hash = sha_m.group(1)
    fake = (
        "FAKE_GODOT" in blob
        or "fake.probe_tests" in version
        or "fake_godot.py" in str(target)
    )
    plat = f"{platform.system()} {platform.release()} / {platform.machine()}"
    return GodotIdentity(
        executable=exe,
        path=str(target),
        version=version or "unknown",
        build_hash=build_hash or binary_sha1[:12],
        binary_sha1=binary_sha1,
        platform=plat,
        fake=fake,
        stdout=proc.stdout,
        stderr=proc.stderr,
    )


def _load_upstreams(
    names: Sequence[str],
    *,
    identity: GodotIdentity,
    force_stale: bool,
) -> list[dict[str, Any]]:
    loaded: list[dict[str, Any]] = []
    for name in names:
        path = LATEST_DIR / f"{name}.json"
        if not path.is_file():
            raise BlockedError(f"BLOCKED: 上游 {name} 的 {path.relative_to(PROBE_ROOT)} 不存在")
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("fake") or not data.get("usable_for_confirmed", True):
            raise BlockedError(f"BLOCKED: 上游 {name} 来自假二进制，不得作为已确认输入")
        stored = data.get("inputs_digest") or ""
        fresh = _recompute_upstream_digest(data, identity)
        if fresh and stored and fresh != stored:
            msg = f"STALE: 上游 {name} inputs_digest 已变 stored={stored} current={fresh}"
            if not force_stale:
                raise StaleError(msg + "；确认沿用旧结论时传 --force-stale")
        loaded.append(data)
    return loaded


def _recompute_upstream_digest(data: Mapping[str, Any], identity: GodotIdentity) -> str:
    stored = dict(data.get("inputs") or {})
    if not stored:
        return ""
    fixtures = list((stored.get("fixtures") or {}).keys())
    derived = list((stored.get("derived") or {}).keys())
    fresh = _collect_inputs(
        fixtures=fixtures,
        derived=derived,
        identity=identity,
        upstream=[],
    )
    fresh["upstream"] = stored.get("upstream") or {}
    return _digest_inputs(fresh)


def _collect_inputs(
    *,
    fixtures: Sequence[str],
    derived: Sequence[str],
    identity: GodotIdentity,
    upstream: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    fixture_hashes = {f: _tree_digest(_fixture_path(f)) for f in fixtures}
    anno_hashes = {}
    for f in fixtures:
        p = _annotation_path(f)
        anno_hashes[f] = _file_sha256(p) if p.is_file() else ""
    derived_hashes = {}
    for name in derived:
        ddir = DERIVED_DIR / name
        parts = []
        for fn in ("patch.diff", "provenance.yaml"):
            p = ddir / fn
            parts.append(_file_sha256(p) if p.is_file() else "")
        derived_hashes[name] = _sha256_text("|".join(parts))
    upstream_hashes = {
        str(u.get("N")): str(u.get("inputs_digest") or "") for u in upstream
    }
    return {
        "fixtures": fixture_hashes,
        "annotations": anno_hashes,
        "derived": derived_hashes,
        "godot_build_hash": identity.build_hash,
        "godot_path": identity.path,
        "godot_fake": identity.fake,
        "upstream": upstream_hashes,
    }


def _digest_inputs(inputs: Mapping[str, Any]) -> str:
    blob = json.dumps(inputs, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return _sha256_text(blob)


def _fixture_path(fixture: str) -> Path:
    return FIXTURES_DIR / fixture


def _annotation_path(fixture: str) -> Path:
    return ANNOTATIONS_DIR / f"{fixture}.yaml"


def _norm_cache(cache: str) -> str:
    value = cache.strip().upper()
    if value not in CACHE_STATES:
        raise ProbeError(f"cache_state 必须是 {CACHE_STATES}，得到 {cache!r}")
    return value


def _cmd_uses_sentinel(cmd: str, *, base: str | None, target: str | None) -> bool:
    c = cmd.upper()
    if c == "V1":
        return True
    if c in {"V7", "V8"}:
        resolved = _resolve_base(c, base=base, target=target)
        return resolved == "V1"
    return False


def _resolve_base(cmd: str, *, base: str | None, target: str | None) -> str:
    if base:
        return base.upper()
    if cmd.upper() == "V7":
        return "V2" if target else "V1"
    if cmd.upper() == "V8":
        return "V2" if target else "V1"
    return cmd.upper()


def _script_res(target: str | None) -> str:
    if not target:
        raise ProbeError("V2 需要 target（脚本路径，如 res://main.gd 或 main.gd）")
    t = target.strip()
    if t.startswith("res://"):
        return t
    return "res://" + t.lstrip("/")


def _build_argv(
    executable: Sequence[str],
    cmd: str,
    ws: Path,
    *,
    target: str | None = None,
    base: str | None = None,
) -> list[str]:
    path = str(ws.resolve())
    c = cmd.upper()
    extra: list[str] = []
    core = c
    if c == "V7":
        core = _resolve_base(c, base=base, target=target)
        extra = ["--verbose"]
    elif c == "V8":
        core = _resolve_base(c, base=base, target=target)
        extra = ["--debug"]
    flags: list[str]
    if core == "V1":
        flags = [
            "--headless",
            "--path",
            path,
            "--check-only",
            "--script",
            SENTINEL_RES,
            "--quit",
        ]
    elif core == "V2":
        flags = [
            "--headless",
            "--path",
            path,
            "--script",
            _script_res(target),
            "--check-only",
            "--quit",
        ]
    elif core == "V3":
        flags = ["--headless", "--path", path, "--editor", "--import", "--quit"]
    elif core == "V4":
        flags = ["--headless", "--path", path, "--import", "--quit"]
    elif core == "V5":
        flags = ["--headless", "--path", path, "--quit"]
    elif core == "V6":
        flags = ["--headless", "--path", path, "--quit-after", "2"]
    else:
        raise ProbeError(f"未知 cmd: {cmd}")
    return list(executable) + flags + extra


def _run_process(
    argv: Sequence[str],
    *,
    cwd: Path,
    timeout: int,
    live: list[subprocess.Popen] | None,
) -> ProcessResult:
    t0 = time.perf_counter()
    proc = subprocess.Popen(
        list(argv),
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    if live is not None:
        live.append(proc)
    timed_out = False
    stdout_b = b""
    stderr_b = b""
    try:
        stdout_b, stderr_b = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        _killpg(proc)
        try:
            stdout_b, stderr_b = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            _killpg(proc)
            stdout_b, stderr_b = proc.communicate(timeout=2)
    wall = time.perf_counter() - t0
    if live is not None and proc in live:
        live.remove(proc)
    rc = proc.returncode
    sig: int | None = None
    if rc is not None and rc < 0:
        sig = -rc
    return ProcessResult(
        rc=rc,
        signal=sig,
        timed_out=timed_out,
        wall_time=round(wall, 6),
        stdout=_decode(stdout_b),
        stderr=_decode(stderr_b),
        pid=proc.pid,
    )


def _killpg(proc: subprocess.Popen) -> None:
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        try:
            proc.kill()
        except OSError:
            pass


def _kill_live(live: list[subprocess.Popen]) -> None:
    while live:
        proc = live.pop()
        if proc.poll() is None:
            _killpg(proc)
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass


def _write_sentinel(root: Path, include: Sequence[str] | None) -> Path:
    suffixes = tuple(include) if include else (".gd",)
    resources: list[str] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.name.startswith(HELPER_PREFIX):
            continue
        if path.suffix not in suffixes:
            continue
        rel = path.relative_to(root).as_posix()
        resources.append(f"res://{rel}")
    lines = [
        "extends RefCounted",
        "# generated by probe.sentinel; not part of the fixture",
    ]
    for i, res in enumerate(resources):
        lines.append(f"const _p{i} = preload(\"{res}\")")
    if not resources:
        lines.append("func _init() -> void:")
        lines.append("    pass")
    text = "\n".join(lines) + "\n"
    dest = root / SENTINEL_NAME
    dest.write_text(text, encoding="utf-8")
    return dest


def _remove_sentinel(root: Path) -> None:
    dest = root / SENTINEL_NAME
    if dest.exists():
        dest.unlink()


def _cache_manifest(root: Path) -> dict[str, Any]:
    godot = root / ".godot"
    if not godot.exists():
        return {"exists": False, "files": {}}
    files: dict[str, Any] = {}
    for path in sorted(godot.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        files[rel] = {"sha256": _file_sha256(path), "size": path.stat().st_size}
    return {"exists": True, "files": files}


def _fixture_has_no_probe_files(src: Path) -> bool:
    for path in src.rglob("*"):
        if path.is_file() and path.name.startswith(HELPER_PREFIX):
            return False
    return True


def _tree_digest(root: Path) -> str:
    h = hashlib.sha256()
    if not root.is_dir():
        return h.hexdigest()
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        h.update(path.read_bytes())
        h.update(b"\0")
    return h.hexdigest()


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _file_sha1(path: Path) -> str:
    h = hashlib.sha1()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _decode(data: bytes) -> str:
    return data.decode("utf-8", errors="replace")


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _env_overrides() -> dict[str, str]:
    keys = ("PROBE_GODOT", "PROBE_FORCE_STALE", "PROBE_RUN_ID")
    return {k: os.environ[k] for k in keys if k in os.environ}


def _read_simple_yaml(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    if not path.is_file():
        return data
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        data[key.strip()] = val.strip().strip("\"'")
    return data


def _render_index(run: Run) -> str:
    lines = [
        f"# {run.N} artifacts",
        "",
        "证据索引，不是判定。",
        "",
        f"- run-id: `{run.run_id}`",
        f"- inputs_digest: `{run.inputs_digest}`",
        f"- Godot: `{run.identity.path}`",
        f"- version: `{run.identity.version}`",
        f"- build hash: `{run.identity.build_hash}`",
        f"- fake: `{str(run.identity.fake).lower()}`",
        f"- platform: `{run.identity.platform}`",
        f"- force_stale: `{str(run.force_stale).lower()}`",
        "",
        "## measurements",
        "",
        "| group | step | cache | repeat | cmd | rc | timeout | wall_s |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for m in run.measurements:
        lines.append(
            f"| {m['group_id']} | {m['step_id']} | {m['cache_state']} | "
            f"{m['repeat_idx']} | {m['cmd']} | {m['rc']} | {m['timed_out']} | {m['wall_time']} |"
        )
    lines.append("")
    lines.append("## inputs")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(run.inputs, indent=2, ensure_ascii=False))
    lines.append("```")
    lines.append("")
    return "\n".join(lines)


@contextmanager
def _null_cm() -> Iterator[None]:
    yield
