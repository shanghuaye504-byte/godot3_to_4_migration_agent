"""inputs_digest 陈旧检测。

摘要 fixture hash、annotation hash、derived patch hash、上游 export JSON、
Godot build hash。N09 重跑导致 normalization profile 变化时，下游实验必须
被标记为 STALE，不得静默复用旧结论。
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
                reason="inputs_digest 与上次记录不一致，上游可能已变化",
                digest=current_digest,
            )

    return FreshnessResult(status="FRESH", reason="", digest=current_digest)
