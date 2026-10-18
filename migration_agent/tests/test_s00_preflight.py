"""S00：环境预检与真实接口契约。先写反例，再实现 preflight。"""

from __future__ import annotations

import dataclasses
import importlib
import inspect
import os
import re
import sys
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

REPO_ROOT = Path(__file__).resolve().parents[2]
GODOT_SRC = REPO_ROOT / "codebase_index" / "godot_mcp" / "src"
if str(GODOT_SRC) not in sys.path:
    sys.path.insert(0, str(GODOT_SRC))

from codeindex.config import load_config  # noqa: E402
from godot_mcp.verify_gate.models import VerifyGateResult  # noqa: E402
from inline_tools.editandfixguard.edit import edit  # noqa: E402
from migration_agent.preflight import (  # noqa: E402
    OTEL_SEMCONV_VERSION,
    PreflightError,
    locked_package_versions,
    require_imports,
    run_preflight,
)
from rag.retriever.schemas import RetrievalQuery  # noqa: E402

_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)\s]+)\)")
_DOC_FILES = (
    REPO_ROOT / "LANDMARKS.md",
    REPO_ROOT / "DEFECTS.md",
    REPO_ROOT / "migration_agent" / "LANDMARKS.md",
)


def _write_config(path: Path, **overrides: object) -> Path:
    payload: dict[str, object] = {
        "profile": "offline",
        "godot_binary": "/usr/local/bin/godot4",
        "rules_manifest": "rag/artifacts/manifest.lock.json",
        "rules_db": "rag/artifacts/rules.db",
        "corpus_dir": "rag/artifacts/corpora/default/corpus.lance",
        "otel": {
            "protocol": "http/protobuf",
            "semantic_conventions_version": OTEL_SEMCONV_VERSION,
        },
    }
    payload.update(overrides)
    path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path


def _ok_runner(_binary: str) -> tuple[str, str]:
    return "ok", "4.7.1.stable.official.a13da4feb"


def test_retrieval_query_old_shape_rejected() -> None:
    with pytest.raises(ValidationError):
        RetrievalQuery(query="instance", error_code=None)  # type: ignore[call-arg]


def test_retrieval_query_symbols_and_version_ok() -> None:
    query = RetrievalQuery(symbols=["instance"], target_version="4.7.1")
    assert query.target_version == "4.7.1"
    assert query.symbols == ["instance"]


def test_gate_result_uses_decision_not_action() -> None:
    names = {item.name for item in dataclasses.fields(VerifyGateResult)}
    assert "decision" in names
    assert "action" not in names


def test_edit_signature_and_failure_keys(tmp_path: Path) -> None:
    params = inspect.signature(edit).parameters
    for name in ("project_root", "file", "kind", "hunks"):
        assert name in params
    result = edit(tmp_path, file="res://a.gd", kind="patch", hunks=[])
    for key in ("ok", "commit", "guard", "index_stale"):
        assert key in result
    assert result["ok"] is False


def test_old_config_keys_missing_project_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CODEBASE_PROJECT_ROOT", raising=False)
    path = tmp_path / "old.yaml"
    path.write_text("workspace_root: /tmp/workspace\ngodot_bin: godot4\n", encoding="utf-8")
    with pytest.raises(KeyError, match="project_root"):
        load_config(path)


def test_absolute_loader_stable_across_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CODEBASE_PROJECT_ROOT", raising=False)
    project = tmp_path / "proj"
    project.mkdir()
    rules = tmp_path / "rules.db"
    rules.write_bytes(b"")
    path = tmp_path / "config.yaml"
    path.write_text(
        f"project_root: {project}\nmigration_rules_db: {rules}\n",
        encoding="utf-8",
    )
    first_dir = tmp_path / "cwd-a"
    second_dir = tmp_path / "cwd-b"
    first_dir.mkdir()
    second_dir.mkdir()
    monkeypatch.chdir(first_dir)
    first = load_config(path)
    monkeypatch.chdir(second_dir)
    second = load_config(path)
    assert first.project_root == second.project_root == project.resolve()
    assert first.migration_rules_db == second.migration_rules_db == rules.resolve()


def test_unknown_preflight_key(tmp_path: Path) -> None:
    path = _write_config(tmp_path / "bad.yaml", workspace_root="/tmp/nope")
    with pytest.raises(PreflightError, match="未知"):
        run_preflight(path, godot_runner=_ok_runner)


def test_missing_engine(tmp_path: Path) -> None:
    path = _write_config(tmp_path / "missing.yaml", godot_binary=str(tmp_path / "no-such-godot"))
    report = run_preflight(path)
    assert report.ok is False
    assert report.godot_status == "missing"
    assert any("引擎" in item or "godot" in item.lower() for item in report.errors)


def test_version_mismatch(tmp_path: Path) -> None:
    path = _write_config(tmp_path / "mismatch.yaml")
    report = run_preflight(path, godot_runner=lambda _binary: ("ok", "4.6.0.stable"))
    assert report.ok is False
    assert report.godot_status == "version_mismatch"


def test_grpc_protocol_rejected(tmp_path: Path) -> None:
    path = _write_config(
        tmp_path / "grpc.yaml",
        otel={
            "protocol": "grpc",
            "semantic_conventions_version": OTEL_SEMCONV_VERSION,
        },
    )
    with pytest.raises(PreflightError, match="协议"):
        run_preflight(path, godot_runner=_ok_runner)


def test_bad_endpoint_rejected(tmp_path: Path) -> None:
    path = _write_config(
        tmp_path / "endpoint.yaml",
        profile="dual",
        otel={
            "protocol": "http/protobuf",
            "semantic_conventions_version": OTEL_SEMCONV_VERSION,
            "collector_endpoint": "grpc://127.0.0.1:4317",
            "langfuse_endpoint": "${LANGFUSE_OTLP_ENDPOINT}",
            "phoenix_endpoint": "${PHOENIX_OTLP_ENDPOINT}",
        },
    )
    with pytest.raises(PreflightError, match="地址"):
        run_preflight(path, godot_runner=_ok_runner)


def test_plaintext_secret_rejected(tmp_path: Path) -> None:
    path = _write_config(
        tmp_path / "secret.yaml",
        otel={
            "protocol": "http/protobuf",
            "semantic_conventions_version": OTEL_SEMCONV_VERSION,
            "credentials": {"langfuse_secret_key": "sk-live-secret"},
        },
    )
    with pytest.raises(PreflightError, match="环境变量"):
        run_preflight(path, godot_runner=_ok_runner)


def test_offline_profile_does_not_need_backend(tmp_path: Path) -> None:
    path = _write_config(tmp_path / "offline.yaml")
    report = run_preflight(path, godot_runner=_ok_runner)
    assert report.ok is True
    assert report.profile == "offline"
    assert report.backend_status == "not_required"
    assert report.manifest_sha256
    assert report.rules_db_sha256
    assert report.corpus_present is True
    assert report.rules_godot_version == "4.7.1"


def test_dual_profile_stays_pending(tmp_path: Path) -> None:
    path = _write_config(
        tmp_path / "dual.yaml",
        profile="dual",
        otel={
            "protocol": "http/protobuf",
            "semantic_conventions_version": OTEL_SEMCONV_VERSION,
            "collector_endpoint": "http://127.0.0.1:9/v1/traces",
            "langfuse_endpoint": "https://cloud.langfuse.com/api/public/otel/v1/traces",
            "phoenix_endpoint": "${PHOENIX_OTLP_ENDPOINT}",
            "credentials": {
                "langfuse_public_key": "${LANGFUSE_PUBLIC_KEY}",
                "langfuse_secret_key": "${LANGFUSE_SECRET_KEY}",
            },
        },
    )
    report = run_preflight(path, godot_runner=_ok_runner)
    assert report.ok is True
    assert report.backend_status == "pending_acceptance"


def test_same_config_is_stable_across_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = _write_config(tmp_path / "stable.yaml").resolve()
    first_dir = tmp_path / "one"
    second_dir = tmp_path / "two"
    first_dir.mkdir()
    second_dir.mkdir()
    monkeypatch.chdir(first_dir)
    first = run_preflight(path, godot_runner=_ok_runner)
    monkeypatch.chdir(second_dir)
    second = run_preflight(path, godot_runner=_ok_runner)
    assert first.godot_path == second.godot_path
    assert first.manifest_sha256 == second.manifest_sha256
    assert first.rules_db_sha256 == second.rules_db_sha256


def test_parser_locks_match() -> None:
    root_lock = (REPO_ROOT / "uv.lock").read_text(encoding="utf-8")
    index_lock = (REPO_ROOT / "codebase_index" / "index" / "uv.lock").read_text(encoding="utf-8")
    names = {"tree-sitter", "tree-sitter-language-pack"}
    assert locked_package_versions(root_lock, names) == locked_package_versions(index_lock, names)


def test_missing_import_fails_clearly() -> None:
    with pytest.raises(PreflightError, match="缺少依赖"):
        require_imports(["definitely_not_installed_s00"])


def test_runtime_imports_resolve() -> None:
    require_imports(["codeindex", "rag", "rag.retriever.schemas"])
    assert importlib.import_module("rag").__file__


def test_doc_relative_links_resolve() -> None:
    missing: list[str] = []
    for doc in _DOC_FILES:
        text = doc.read_text(encoding="utf-8")
        for target in _LINK_RE.findall(text):
            if target.startswith(("http://", "https://", "mailto:")):
                continue
            relative = target.split("#", 1)[0]
            if not relative:
                continue
            resolved = (doc.parent / relative).resolve()
            if not resolved.exists():
                missing.append(f"{doc.relative_to(REPO_ROOT)} -> {target}")
    assert missing == []


def test_real_godot_matches_rules_manifest() -> None:
    path = REPO_ROOT / "migration_agent" / "env.preflight.example.yaml"
    report = run_preflight(path)
    assert report.godot_status == "ok", report.errors
    assert report.godot_version.startswith("4.7.1")
    assert report.rules_godot_version == "4.7.1"
    assert report.ok is True
    assert report.python_version
    assert report.packages["tree-sitter-language-pack"] == "1.20.0"
