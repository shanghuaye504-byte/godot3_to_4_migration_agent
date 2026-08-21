"""给「输入材料」盖指纹，不是给 Godot 输出做 signature。

类比：digest = 食材批次号；normalize 的 signature = 这道菜尝起来像什么。
两者绝不能混：stdout 变了不影响 digest；换了 fixture / Godot 二进制，digest 必须变。

算什么（合在一起变成 inputs_digest）：
  fixture 文件树 hash
  annotation YAML hash（即使 N09 的 stability 还不读埋点表）
  derived patch hash（N09 没有）
  Godot 可执行文件 hash（Fake 则用 fake:version）

实验级 digest 再把各 group 的 digest 与上游 artifacts/latest/<dep>.json 的
文件 hash 合成一张 N 一个指纹。比的是「这张 N 和它自己上次」，不是 N08 vs N09。

谁调用：runner 开场算 experiment_digest，再传 group digest 给
capture.run_measurement(..., inputs_digest=...)。
capture / process 都不自己算 digest。

check_freshness：
  MISSING — 上游 latest 不存在，拒跑（--force-stale 也无效）
  STALE   — 与自己上次存档 digest 不同，默认拒跑，须 --force-stale 才重跑
  FRESH   — 无存档（第一次）或与上次相同
STALE 不是自动重跑；旧结论作废，要实验者按 README 第 6 层顺序显式重跑。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Optional

from .types import EngineProfile


class BlockedExperimentError(Exception):
    pass


def compute_file_hash(path: Path) -> str:
    return hashlib.sha1(Path(path).read_bytes()).hexdigest()


def compute_tree_hash(root: Path, *, exclude: set[str] = frozenset({".git", ".godot"})) -> str:
    root = Path(root)
    lines = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if any(part in exclude for part in path.relative_to(root).parts):
            continue
        rel = path.relative_to(root).as_posix()
        lines.append(f"{rel}:{compute_file_hash(path)}")
    return hashlib.sha1("\n".join(lines).encode("utf-8")).hexdigest()


def compute_build_hash(engine_profile: EngineProfile) -> str:
    if engine_profile.fake:
        return hashlib.sha1(f"fake:{engine_profile.version}".encode("utf-8")).hexdigest()
    binary_path = Path(engine_profile.executable[-1])
    return hashlib.sha1(binary_path.read_bytes()).hexdigest()


def latest_record_path(artifacts_root: Path, exp_id: str) -> Path:
    """跨 run-id 的成功指针：artifacts/latest/<exp_id>.json。Fake 跑不得读写此文件。"""
    return Path(artifacts_root) / "latest" / f"{exp_id}.json"


def compute_experiment_digest(group_digests: dict, upstream_export_hashes: dict) -> str:
    """一张 N 一个指纹：各 group digest + 上游 latest 文件 hash。"""
    parts = [f"group:{gid}={group_digests[gid]}" for gid in sorted(group_digests)]
    for key in sorted(upstream_export_hashes):
        parts.append(f"upstream:{key}={upstream_export_hashes[key]}")
    return hashlib.sha1("\n".join(parts).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class DigestComponents:
    fixture_hash: str
    annotation_hash: str = ""
    derived_patch_hash: Optional[str] = None
    upstream_export_hashes: dict = field(default_factory=dict)
    build_hash: str = ""


def compute_inputs_digest(components: DigestComponents) -> str:
    parts = [
        f"fixture_hash={components.fixture_hash}",
        f"annotation_hash={components.annotation_hash}",
        f"derived_patch_hash={components.derived_patch_hash or ''}",
        f"build_hash={components.build_hash}",
    ]
    for key in sorted(components.upstream_export_hashes):
        parts.append(f"upstream:{key}={components.upstream_export_hashes[key]}")
    return hashlib.sha1("\n".join(parts).encode("utf-8")).hexdigest()


@dataclass
class FreshnessResult:
    status: Literal["FRESH", "STALE", "MISSING", "BLOCKED"]
    reason: str
    digest: str


def check_freshness(
    depends_on: list[str],
    upstream_export_paths: dict,
    current_digest: str,
    recorded_digest_path: Optional[Path] = None,
) -> FreshnessResult:
    for name in depends_on:
        export_path = upstream_export_paths.get(name)
        if export_path is None or not Path(export_path).exists():
            return FreshnessResult(
                status="MISSING",
                reason=f"依赖 {name} 的导出文件不存在: {export_path}",
                digest=current_digest,
            )

    if recorded_digest_path is not None and Path(recorded_digest_path).exists():
        try:
            recorded = json.loads(Path(recorded_digest_path).read_text(encoding="utf-8"))
            recorded_digest = recorded.get("inputs_digest")
        except (json.JSONDecodeError, OSError):
            recorded_digest = None
        if recorded_digest is not None and recorded_digest != current_digest:
            return FreshnessResult(
                status="STALE",
                reason=(
                    "inputs_digest 与上次记录不一致，配方或上游 latest 已变化；"
                    "旧结论作废。默认拒绝重跑；确认后使用 --force-stale。"
                    "下游须按 README 第 6 层顺序逐张重跑。"
                ),
                digest=current_digest,
            )

    return FreshnessResult(status="FRESH", reason="", digest=current_digest)
