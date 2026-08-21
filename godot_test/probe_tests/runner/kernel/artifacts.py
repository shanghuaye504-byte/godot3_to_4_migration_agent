"""Artifact 落盘。

路径：artifacts/<run-id>/<N>/<group_id>/<step-id>/<cache_state>/<repeat_idx>/
文件：metadata.json、argv.json、stdout.log、stderr.log、process-status.json、
fs-before.json、fs-after.json、workspace.diff、cache-manifest.json、
signatures.json、evaluation.json。group 级 cleanup.json 写在
artifacts/<run-id>/<N>/<group_id>/cleanup.json。
成功的真实实验另写 artifacts/latest/<N>.json（跨 run 的 digest 指针）。
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

from .types import FsSnapshot, ProcessStatus, RawResult


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


def write_signatures(directory: Path, signature_pairs: list) -> None:
    write_json(directory / "signatures.json", signature_pairs, sort_keys=False)


def write_evaluation(directory: Path, evaluation: dict) -> None:
    write_json(directory / "evaluation.json", evaluation)


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
    signatures: list,
    evaluation: dict,
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
    write_signatures(directory, signatures)
    write_evaluation(directory, evaluation)
