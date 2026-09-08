"""verify_gate 测试共享辅助：构造最小 ClassifiedEvent / ProjectFilterView / 状态。"""

from __future__ import annotations

from godot_mcp.verify_filter.models import ClassifiedEvent, ProjectFilterView
from godot_mcp.verify_gate.models import ProjectVerifyState, VerifyGateRequest


def make_event(local_signature: str, *, role: str = "root_cause") -> ClassifiedEvent:
    return ClassifiedEvent(
        prefix="SCRIPT ERROR",
        message=f"Compile Error: {local_signature}",
        at_function="GDScript::reload",
        at_location=f"res://{local_signature}.gd:1",
        res_path=f"res://{local_signature}.gd",
        target_res_path=None,
        line_in_project=1,
        engine_location=None,
        source_stream="stderr",
        raw_block=f"SCRIPT ERROR: Compile Error: {local_signature}",
        kind="compile_error",
        symbol=local_signature,
        msg_template="Compile Error: <SYM>",
        local_signature=local_signature,
        noise_signature=f"noise-{local_signature}",
        role=role,  # type: ignore[arg-type]
    )


def make_view(
    *root_sigs: str,
    symptoms: tuple[str, ...] = (),
    pointers: tuple[str, ...] = (),
    dropped: tuple[str, ...] = (),
    status: str | None = None,
    shader_checked: bool = False,
) -> ProjectFilterView:
    roots = [make_event(sig) for sig in root_sigs]
    return ProjectFilterView(
        status=status or ("HAS_ERRORS" if roots else "CLEAN"),  # type: ignore[arg-type]
        root_cause_errors=roots,
        pending_pointers=[make_event(sig, role="pointer") for sig in pointers],
        symptoms=[make_event(sig, role="symptom") for sig in symptoms],
        dropped=[make_event(sig, role="false_positive") for sig in dropped],
        caveats=[],
        untrusted_files=frozenset(),
        gdscript_complete=not roots and not pointers,
        shader_checked=shader_checked,
    )


def make_state(
    *,
    workspace_id: str = "ws-1",
    session_id: str = "sess-1",
) -> ProjectVerifyState:
    return ProjectVerifyState(
        workspace_id=workspace_id,
        session_id=session_id,
        signature_history=[],
        per_file_patch_count={},
        per_file_last_signature_set={},
        infra_failure_streak=0,
        rounds_used=0,
        cost_used_usd=0.0,
        circuit_state="CLOSED",
    )


def make_request(
    view: ProjectFilterView,
    *,
    round_index: int,
    patched_files: frozenset[str] = frozenset(),
    infra_status: str = "OK",
    round_cost_usd: float = 0.0,
    workspace_id: str = "ws-1",
    session_id: str = "sess-1",
) -> VerifyGateRequest:
    return VerifyGateRequest(
        workspace_id=workspace_id,
        session_id=session_id,
        round_index=round_index,
        command="MERGED",
        project_view=view,
        patched_files=patched_files,
        infra_status=infra_status,  # type: ignore[arg-type]
        round_cost_usd=round_cost_usd,
    )
