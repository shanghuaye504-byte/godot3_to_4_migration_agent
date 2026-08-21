"""apply_derived_patch：应用 derived/<fixture>@<state>/patch.diff。

应用前需校验 provenance.yaml 的 Godot build hash；不一致则退回 manual gate。
本轮范围之外（N02/N06 manual gate 由用户本人手动操作），仅提供接口契约：
`kernel/workspace.py` 的 `apply_derived_patch_if_present` 会捕获这里抛出的
NotImplementedError，转成 status="NOT_IMPLEMENTED" 的结果而不是让进程崩溃。
"""

from __future__ import annotations

from pathlib import Path


def apply(workspace: Path, derived_dir: Path):
    raise NotImplementedError(
        "apply_derived_patch 本轮未实现，需人工介入（manual gate）"
    )
