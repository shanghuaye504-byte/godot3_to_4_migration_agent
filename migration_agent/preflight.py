"""环境预检：版本、引擎、语料指纹和观测配置格式。

这里只检查配置写得对不对。不安装 OpenTelemetry，不连接 Collector，
也不向 Langfuse 或 Phoenix 发送数据，不调用模型。
"""

from __future__ import annotations

import hashlib
import importlib
import importlib.metadata as metadata
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

import yaml

# 项目锁定的 OpenTelemetry 语义约定版本。S14 再按这个版本接 SDK。
OTEL_SEMCONV_VERSION = "1.37.0"
DEFAULT_GODOT = "/usr/local/bin/godot4"
REPO_ROOT = Path(__file__).resolve().parents[1]

_ENV_REF = re.compile(r"^\$\{([A-Z_][A-Z0-9_]*)\}$")
_TOP_KEYS = frozenset(
    {"profile", "godot_binary", "rules_manifest", "rules_db", "corpus_dir", "otel"}
)
_OTEL_KEYS = frozenset(
    {
        "protocol",
        "semantic_conventions_version",
        "collector_endpoint",
        "langfuse_endpoint",
        "phoenix_endpoint",
        "credentials",
    }
)
_CREDENTIAL_KEYS = frozenset(
    {"langfuse_public_key", "langfuse_secret_key", "phoenix_api_key"}
)
_ENDPOINT_FIELDS = ("collector_endpoint", "langfuse_endpoint", "phoenix_endpoint")
GodotRunner = Callable[[str], tuple[str, str]]


class PreflightError(ValueError):
    """配置或依赖不满足预检，调用方应把这段说明当作失败原因。"""


@dataclass
class PreflightReport:
    """一次预检的结果。backend_status 不是“后端已经连通”。"""

    ok: bool
    python_version: str
    packages: dict[str, str]
    godot_path: str
    godot_version: str | None
    godot_status: str
    rules_godot_version: str | None
    manifest_sha256: str | None
    rules_db_sha256: str | None
    corpus_present: bool
    profile: str
    protocol: str
    semantic_conventions_version: str
    backend_status: str
    errors: list[str] = field(default_factory=list)


def require_imports(module_names: list[str]) -> None:
    """导入主环境应具备的模块。缺任何一个都明确失败。"""
    missing = []
    for name in module_names:
        try:
            importlib.import_module(name)
        except ImportError:
            missing.append(name)
    if missing:
        raise PreflightError(f"主环境缺少依赖: {', '.join(missing)}")


def locked_package_versions(lock_text: str, names: set[str]) -> dict[str, str]:
    """从 uv.lock 的 [[package]] 段读取指定包的版本。"""
    found: dict[str, str] = {}
    in_package = False
    current_name: str | None = None
    for line in lock_text.splitlines():
        if line.startswith("[[package]]"):
            in_package = True
            current_name = None
            continue
        if line.startswith("[["):
            in_package = False
            current_name = None
            continue
        if not in_package:
            continue
        if line.startswith("name = "):
            current_name = line.split("=", 1)[1].strip().strip('"')
        elif line.startswith("version = ") and current_name in names:
            found[current_name] = line.split("=", 1)[1].strip().strip('"')
    missing = names - set(found)
    if missing:
        raise PreflightError(f"lock 中缺少包: {sorted(missing)}")
    return found


def default_godot_runner(binary: str) -> tuple[str, str]:
    """运行 godot --version。找不到、超时和非零退出分成不同状态。"""
    if not Path(binary).is_file() and shutil.which(binary) is None:
        return "missing", binary
    try:
        completed = subprocess.run(
            [binary, "--version"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return "timeout", binary
    except FileNotFoundError:
        return "missing", binary
    text = (completed.stdout or completed.stderr or "").strip()
    if completed.returncode != 0:
        return "failed", text or f"exit {completed.returncode}"
    return "ok", text


def run_preflight(
    config_path: str | Path,
    *,
    godot_runner: GodotRunner | None = None,
    repo_root: Path | None = None,
) -> PreflightReport:
    """读取预检配置并返回报告。配置错误直接抛出，引擎和产物问题写进报告。"""
    root = (repo_root or REPO_ROOT).resolve()
    raw = _load_mapping(Path(config_path))
    _reject_unknown(raw, _TOP_KEYS, "预检配置")
    profile = raw.get("profile")
    if profile not in {"offline", "dual"}:
        raise PreflightError(f"未知 profile: {profile}")
    otel = raw.get("otel")
    if not isinstance(otel, dict):
        raise PreflightError("otel 必须是映射")
    _reject_unknown(otel, _OTEL_KEYS, "otel")
    protocol = otel.get("protocol")
    if protocol != "http/protobuf":
        raise PreflightError(f"协议只接受 OTLP HTTP（http/protobuf），收到: {protocol}")
    semconv = otel.get("semantic_conventions_version")
    if semconv != OTEL_SEMCONV_VERSION:
        raise PreflightError(
            f"语义约定版本必须是 {OTEL_SEMCONV_VERSION}，收到: {semconv}"
        )
    _validate_credentials(otel.get("credentials"))
    if profile == "dual":
        for name in _ENDPOINT_FIELDS:
            if name not in otel:
                raise PreflightError(f"dual profile 缺少地址: {name}")
    for name in _ENDPOINT_FIELDS:
        if name in otel:
            _validate_endpoint(name, otel[name])

    require_imports(["codeindex", "rag", "rag.retriever.schemas"])
    godot_path = _resolve_godot(raw.get("godot_binary"))
    manifest_path = _resolve_repo_path(root, raw.get("rules_manifest"), "rules_manifest")
    rules_path = _resolve_repo_path(root, raw.get("rules_db"), "rules_db")
    corpus_path = _resolve_repo_path(root, raw.get("corpus_dir"), "corpus_dir")

    errors: list[str] = []
    rules_version: str | None = None
    manifest_sha: str | None = None
    rules_sha: str | None = None
    if manifest_path.is_file():
        manifest_sha = _sha256(manifest_path)
        rules_version = _manifest_godot_version(manifest_path)
    else:
        errors.append(f"找不到规则清单: {manifest_path}")
    if rules_path.is_file():
        rules_sha = _sha256(rules_path)
    else:
        errors.append(f"找不到规则库: {rules_path}")
    corpus_present = corpus_path.is_dir()
    if not corpus_present:
        errors.append(f"找不到语料目录: {corpus_path}")

    status, detail = (godot_runner or default_godot_runner)(godot_path)
    godot_version: str | None = None
    if status == "missing":
        errors.append(f"找不到 Godot 引擎: {godot_path}")
    elif status == "timeout":
        errors.append(f"Godot 版本检查超时: {godot_path}")
    elif status == "failed":
        errors.append(f"Godot 版本检查失败: {detail}")
    elif status == "ok":
        godot_version = detail
        if rules_version and not _version_matches(detail, rules_version):
            status = "version_mismatch"
            errors.append(f"Godot 版本 {detail} 与规则库 {rules_version} 不一致")
    else:
        errors.append(f"无法识别的引擎状态: {status}")

    return PreflightReport(
        ok=not errors,
        python_version=sys.version.split()[0],
        packages={
            "tree-sitter": metadata.version("tree-sitter"),
            "tree-sitter-language-pack": metadata.version("tree-sitter-language-pack"),
        },
        godot_path=godot_path,
        godot_version=godot_version,
        godot_status=status,
        rules_godot_version=rules_version,
        manifest_sha256=manifest_sha,
        rules_db_sha256=rules_sha,
        corpus_present=corpus_present,
        profile=profile,
        protocol=protocol,
        semantic_conventions_version=semconv,
        backend_status="not_required" if profile == "offline" else "pending_acceptance",
        errors=errors,
    )


def _load_mapping(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise PreflightError(f"找不到预检配置: {path}")
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise PreflightError("预检配置顶层必须是映射")
    return loaded


def _reject_unknown(data: dict[str, Any], allowed: frozenset[str], where: str) -> None:
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise PreflightError(f"{where} 含未知键: {', '.join(unknown)}")


def _validate_credentials(credentials: Any) -> None:
    if credentials is None:
        return
    if not isinstance(credentials, dict):
        raise PreflightError("凭据必须是映射")
    _reject_unknown(credentials, _CREDENTIAL_KEYS, "凭据")
    for key, value in credentials.items():
        if not isinstance(value, str) or _ENV_REF.fullmatch(value) is None:
            raise PreflightError(f"凭据 {key} 只能引用环境变量，例如 ${{LANGFUSE_SECRET_KEY}}")


def _validate_endpoint(name: str, value: Any) -> None:
    if not isinstance(value, str):
        raise PreflightError(f"{name} 地址必须是字符串")
    if _ENV_REF.fullmatch(value):
        return
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise PreflightError(f"{name} 地址必须是 http(s) URL 或环境变量引用")


def _resolve_godot(value: Any) -> str:
    if value is None or value == "":
        return os.environ.get("GODOT_BINARY") or DEFAULT_GODOT
    if not isinstance(value, str):
        raise PreflightError("godot_binary 必须是字符串")
    match = _ENV_REF.fullmatch(value)
    if match is None:
        return value
    env_name = match.group(1)
    env_value = os.environ.get(env_name)
    if env_value:
        return env_value
    if env_name == "GODOT_BINARY":
        return DEFAULT_GODOT
    raise PreflightError(f"环境变量 {env_name} 未设置")


def _resolve_repo_path(root: Path, value: Any, field_name: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise PreflightError(f"缺少 {field_name}")
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = root / path
    return path.resolve()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _manifest_godot_version(path: Path) -> str:
    payload = json.loads(path.read_text(encoding="utf-8"))
    version = payload.get("manifest", {}).get("godot_version")
    if not isinstance(version, str) or not version:
        raise PreflightError(f"规则清单缺少 godot_version: {path}")
    return version


def _version_matches(actual: str, expected: str) -> bool:
    head = actual.strip().split()[0] if actual.strip() else ""
    return head == expected or head.startswith(expected + ".")
