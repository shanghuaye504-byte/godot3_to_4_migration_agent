"""Artifact 落盘与事后重建。

路径：artifacts/<run-id>/<N>/<group_id>/<step-id>/<cache_state>/<repeat_idx>/
原始测量：metadata.json、argv.json、stdout.log、stderr.log、process-status.json、
fs-before.json、fs-after.json、workspace.diff、cache-manifest.json。
判定文件不进本目录（由 analyzer 写 report/<phase>/<N>/）。
group 级 cleanup.json 写在 artifacts/<run-id>/<N>/<group_id>/cleanup.json。
成功的真实实验另写 artifacts/latest/<N>.json（跨 run 的 digest 指针）。
"""

from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .types import CacheState, FsEntry, FsSnapshot, Measurement, ProcessStatus, RawResult

_CACHE_STATES = {"COLD", "WARM", "PRESERVE"}


def step_artifact_dir(
    artifacts_root: Path,
    run_id: str,
    exp_id: str,
    group_id: str,
    step_id: str,
    cache_state: str,
    repeat_idx: int,
) -> Path:
    directory = (
        Path(artifacts_root)
        / run_id
        / exp_id
        / group_id
        / step_id
        / str(cache_state)
        / str(repeat_idx)
    )
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def write_json(path: Path, data, *, sort_keys: bool = True) -> None:
    Path(path).write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=sort_keys, default=str),
        encoding="utf-8",
    )


def write_text(path: Path, content: str) -> None:
    Path(path).write_text(content, encoding="utf-8")


def write_metadata(directory: Path, raw: RawResult, engine_profile: dict) -> None:
    write_json(
        directory / "metadata.json",
        {
            "measurement": dataclasses.asdict(raw.measurement),
            "step_id": raw.step_id,
            "inputs_digest": raw.inputs_digest,
            "cwd": raw.cwd,
            "hooks_applied": list(raw.hooks_applied),
            "env_overrides": dict(raw.env_overrides),
            "engine_profile": engine_profile,
            "started_at": raw.process.started_at,
            "ended_at": raw.process.ended_at,
        },
    )


def write_argv(directory: Path, argv: list) -> None:
    write_json(directory / "argv.json", argv, sort_keys=False)


def write_stdout(directory: Path, text: str) -> None:
    write_text(directory / "stdout.log", text)


def write_stderr(directory: Path, text: str) -> None:
    write_text(directory / "stderr.log", text)


def write_process_status(directory: Path, status: ProcessStatus) -> None:
    write_json(directory / "process-status.json", dataclasses.asdict(status))


def write_fs_snapshot(directory: Path, snapshot: FsSnapshot, which: str) -> None:
    write_json(directory / f"fs-{which}.json", dataclasses.asdict(snapshot))


def write_workspace_diff(directory: Path, diff_text: str) -> None:
    write_text(directory / "workspace.diff", diff_text)


def write_cache_manifest(directory: Path, manifest: dict) -> None:
    write_json(directory / "cache-manifest.json", manifest)


def write_cleanup(directory: Path, cleanup_report: dict) -> None:
    write_json(directory / "cleanup.json", cleanup_report)


def write_latest_record(
    artifacts_root: Path,
    *,
    exp_id: str,
    run_id: str,
    inputs_digest: str,
    groups: list,
    engine_profile: dict,
) -> Path:
    """写入 artifacts/latest/<exp_id>.json。调用方须保证非 fake 且 groups 全 OK。"""
    path = Path(artifacts_root) / "latest" / f"{exp_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(
        path,
        {
            "exp_id": exp_id,
            "run_id": run_id,
            "inputs_digest": inputs_digest,
            "groups": groups,
            "engine_profile": {
                "build_hash": engine_profile.get("build_hash", ""),
                "version": engine_profile.get("version", ""),
            },
            "fake": False,
        },
    )
    return path


def write_step_artifacts(
    directory: Path,
    raw: RawResult,
    cache_manifest: dict,
    engine_profile: dict,
) -> None:
    write_metadata(directory, raw, engine_profile)
    write_argv(directory, raw.argv)
    write_stdout(directory, raw.stdout)
    write_stderr(directory, raw.stderr)
    write_process_status(directory, raw.process)
    write_fs_snapshot(directory, raw.fs_before, "before")
    write_fs_snapshot(directory, raw.fs_after, "after")
    write_workspace_diff(directory, raw.workspace_diff)
    write_cache_manifest(directory, cache_manifest)


@dataclass(frozen=True)
class LoadedShot:
    """从磁盘重建的一条测量，附带相对 artifacts/<run-id>/ 的路径。"""

    raw: RawResult
    group_id: str
    artifact_rel: str
    log_paths: tuple[str, ...]


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _read_text(path: Path) -> str:
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def _cache_state(value) -> CacheState:
    if isinstance(value, CacheState):
        return value
    return CacheState(str(value))


def _measurement(data: dict) -> Measurement:
    return Measurement(
        project=str(data.get("project") or ""),
        command=str(data.get("command") or ""),
        cache_state=_cache_state(data.get("cache_state") or "COLD"),
        repeat_idx=int(data.get("repeat_idx") or 0),
    )


def _process_status(data: dict) -> ProcessStatus:
    return ProcessStatus(
        pid=int(data.get("pid") or 0),
        pgid=int(data.get("pgid") or 0),
        returncode=data.get("returncode"),
        signal=data.get("signal"),
        timed_out=bool(data.get("timed_out")),
        wall_time_seconds=float(data.get("wall_time_seconds") or 0),
        started_at=str(data.get("started_at") or ""),
        ended_at=str(data.get("ended_at") or ""),
    )


def _fs_snapshot(data: Optional[dict]) -> FsSnapshot:
    data = data or {}
    entries = tuple(
        FsEntry(
            rel_path=str(item.get("rel_path") or ""),
            size=int(item.get("size") or 0),
            mtime_ns=int(item.get("mtime_ns") or 0),
            sha1=str(item.get("sha1") or ""),
            is_dir=bool(item.get("is_dir")),
        )
        for item in data.get("entries") or ()
    )
    return FsSnapshot(taken_at=str(data.get("taken_at") or ""), entries=entries)


def load_raw_result(directory: Path) -> RawResult:
    """只凭 step 目录重建 RawResult。缺 cwd/hooks_applied 的旧落盘用空值。"""
    directory = Path(directory)
    meta = _read_json(directory / "metadata.json")
    argv = _read_json(directory / "argv.json") if (directory / "argv.json").is_file() else []
    status_path = directory / "process-status.json"
    process = _process_status(_read_json(status_path) if status_path.is_file() else {})
    return RawResult(
        measurement=_measurement(meta.get("measurement") or {}),
        step_id=str(meta.get("step_id") or directory.parent.parent.name),
        argv=list(argv),
        cwd=str(meta.get("cwd") or ""),
        env_overrides=dict(meta.get("env_overrides") or {}),
        stdout=_read_text(directory / "stdout.log"),
        stderr=_read_text(directory / "stderr.log"),
        process=process,
        fs_before=_fs_snapshot(
            _read_json(directory / "fs-before.json") if (directory / "fs-before.json").is_file() else {}
        ),
        fs_after=_fs_snapshot(
            _read_json(directory / "fs-after.json") if (directory / "fs-after.json").is_file() else {}
        ),
        workspace_diff=_read_text(directory / "workspace.diff"),
        hooks_applied=list(meta.get("hooks_applied") or []),
        inputs_digest=str(meta.get("inputs_digest") or ""),
    )


def load_shot(directory: Path, *, run_dir: Path, group_id: str) -> LoadedShot:
    directory = Path(directory)
    run_dir = Path(run_dir)
    artifact_rel = directory.relative_to(run_dir).as_posix()
    log_paths = tuple(
        (directory / name).relative_to(run_dir).as_posix()
        for name in ("stdout.log", "stderr.log")
        if (directory / name).is_file()
    )
    return LoadedShot(
        raw=load_raw_result(directory),
        group_id=group_id,
        artifact_rel=artifact_rel,
        log_paths=log_paths,
    )


def iter_step_dirs(exp_dir: Path):
    exp_dir = Path(exp_dir)
    if not exp_dir.is_dir():
        return
    for group_dir in sorted(p for p in exp_dir.iterdir() if p.is_dir()):
        for step_dir in sorted(p for p in group_dir.iterdir() if p.is_dir()):
            for cache_dir in sorted(
                p for p in step_dir.iterdir() if p.is_dir() and p.name in _CACHE_STATES
            ):
                for repeat_dir in sorted(
                    p for p in cache_dir.iterdir() if p.is_dir() and p.name.isdigit()
                ):
                    yield group_dir.name, repeat_dir


def load_run_shots(run_dir: Path, exp_id: str) -> list:
    """扫描 artifacts/<run-id>/<N>/ 下已落盘的 step，重建 LoadedShot 列表。"""
    run_dir = Path(run_dir)
    shots = []
    for group_id, repeat_dir in iter_step_dirs(run_dir / exp_id):
        if not (repeat_dir / "metadata.json").is_file():
            continue
        shots.append(load_shot(repeat_dir, run_dir=run_dir, group_id=group_id))
    return shots


def load_exp_shots(exp_dir: Path) -> list:
    """--path 指向 artifacts/<run-id>/<N>/ 时重建 LoadedShot。"""
    exp_dir = Path(exp_dir).resolve()
    return load_run_shots(exp_dir.parent, exp_dir.name)
