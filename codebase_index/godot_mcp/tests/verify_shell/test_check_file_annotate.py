"""`annotate_check_file_view`：A 挪 Identifier、B 保留根因、与 R2/语法正交。"""

from __future__ import annotations

from pathlib import Path

from godot_mcp.verify_filter import filter_verify_output, merge_command_results
from godot_mcp.verify_shell.cache import CLASS_CACHE_REL
from godot_mcp.verify_shell.check_file_annotate import (
    CAVEAT_CLASS_CACHE_STALE,
    DIRECTIVE_CLASS_CACHE_STALE,
    DIRECTIVE_UNREGISTERED_AUTOLOAD,
    annotate_check_file_view,
    caveat_unregistered_autoload,
    merge_shell_directive,
)

_FIXTURES = Path(__file__).resolve().parents[1] / "verify_filter" / "fixtures" / "godot_4_7_1"


def _load(name: str) -> str:
    return (_FIXTURES / name).read_text(encoding="utf-8")


def _write_class_cache(tmp_path: Path, entries: list[tuple[str, str]]) -> None:
    dest = tmp_path / CLASS_CACHE_REL
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not entries:
        dest.write_text("list=[]\n", encoding="utf-8")
        return
    chunks: list[str] = []
    for name, path in entries:
        res = path if path.startswith("res://") else f"res://{path}"
        chunks.append(
            "{\n"
            f'"class": &"{name}",\n'
            f'"path": "{res}"\n'
            "}"
        )
    dest.write_text("list=[" + ",".join(chunks) + "]\n", encoding="utf-8")


def _view(stderr: str, keys: frozenset[str] = frozenset()):
    return merge_command_results(
        filter_verify_output("", stderr, command="V2", autoload_keys=keys),
        {},
    )


def _annotate(tmp_path: Path, stderr: str, keys: frozenset[str] = frozenset()):
    return annotate_check_file_view(
        _view(stderr, keys),
        project_root=tmp_path,
        autoload_keys=keys,
    )


def test_stale_sample_h_demotes_not_declared(tmp_path: Path) -> None:
    (tmp_path / "probe_foo.gd").write_text("class_name ProbeFoo\n", encoding="utf-8")
    _write_class_cache(tmp_path, [])
    original = _view(_load("sample_h_cold_class_name.log"))
    assert original.root_cause_errors
    annotated = _annotate(tmp_path, _load("sample_h_cold_class_name.log"))
    assert annotated.view.root_cause_errors == []
    assert annotated.view.status == "CLEAN"
    assert annotated.view.gdscript_complete is True
    assert CAVEAT_CLASS_CACHE_STALE in annotated.view.caveats
    assert "shader_not_checked" in annotated.view.caveats
    assert "res://uses_class.gd" in annotated.view.untrusted_files
    assert annotated.directive is DIRECTIVE_CLASS_CACHE_STALE
    assert annotated.view.dropped == original.dropped
    assert annotated.view.symptoms == original.symptoms
    assert annotated.view.pending_pointers == original.pending_pointers


def test_consistent_sample_h_keeps_not_declared(tmp_path: Path) -> None:
    (tmp_path / "probe_foo.gd").write_text("class_name ProbeFoo\n", encoding="utf-8")
    _write_class_cache(tmp_path, [("ProbeFoo", "res://probe_foo.gd")])
    annotated = _annotate(tmp_path, _load("sample_h_cold_class_name.log"))
    assert annotated.view.status == "HAS_ERRORS"
    assert any(e.symbol == "ProbeFoo" for e in annotated.view.root_cause_errors)
    assert CAVEAT_CLASS_CACHE_STALE not in annotated.view.caveats
    assert annotated.directive is None
    assert not any(
        c.startswith("identifier_not_found_maybe_unregistered_autoload:")
        for c in annotated.view.caveats
    )


def test_stale_h_and_e_keeps_syntax_and_uses_a_directive(tmp_path: Path) -> None:
    (tmp_path / "probe_foo.gd").write_text("class_name ProbeFoo\n", encoding="utf-8")
    _write_class_cache(tmp_path, [])
    stderr = _load("sample_h_cold_class_name.log") + _load("sample_e_real_syntax_error.log")
    annotated = _annotate(tmp_path, stderr)
    assert annotated.view.status == "HAS_ERRORS"
    assert annotated.view.gdscript_complete is False
    symbols = {e.symbol for e in annotated.view.root_cause_errors}
    messages = [e.message for e in annotated.view.root_cause_errors]
    assert "ProbeFoo" not in symbols
    assert any("Expected parameter name" in msg for msg in messages)
    assert CAVEAT_CLASS_CACHE_STALE in annotated.view.caveats
    assert "res://uses_class.gd" in annotated.view.untrusted_files
    assert annotated.directive is DIRECTIVE_CLASS_CACHE_STALE


def test_stale_only_syntax_has_caveat_but_no_directive(tmp_path: Path) -> None:
    (tmp_path / "probe_foo.gd").write_text("class_name ProbeFoo\n", encoding="utf-8")
    _write_class_cache(tmp_path, [])
    annotated = _annotate(tmp_path, _load("sample_e_real_syntax_error.log"))
    assert annotated.view.status == "HAS_ERRORS"
    assert any("Expected parameter name" in e.message for e in annotated.view.root_cause_errors)
    assert CAVEAT_CLASS_CACHE_STALE in annotated.view.caveats
    assert annotated.directive is None


def test_unregistered_autoload_keeps_root_cause(tmp_path: Path) -> None:
    _write_class_cache(tmp_path, [])
    annotated = _annotate(tmp_path, _load("sample_d_addon_singleton_fp.log"))
    assert annotated.view.status == "HAS_ERRORS"
    assert any(e.symbol == "DummySingleton" for e in annotated.view.root_cause_errors)
    expected = caveat_unregistered_autoload("DummySingleton")
    assert expected in annotated.view.caveats
    assert annotated.directive is DIRECTIVE_UNREGISTERED_AUTOLOAD
    assert CAVEAT_CLASS_CACHE_STALE not in annotated.view.caveats


def test_r2_whitelist_does_not_emit_b_caveat(tmp_path: Path) -> None:
    _write_class_cache(tmp_path, [])
    keys = frozenset({"Config"})
    annotated = _annotate(tmp_path, _load("sample_a_autoload_fp_cold.log"), keys)
    assert annotated.view.root_cause_errors == []
    assert "compile_truncated:res://uses_autoload.gd" in annotated.view.caveats
    assert not any(
        c.startswith("identifier_not_found_maybe_unregistered_autoload:")
        for c in annotated.view.caveats
    )
    assert annotated.directive is None


def test_stale_compile_identifier_swallows_b(tmp_path: Path) -> None:
    (tmp_path / "probe_foo.gd").write_text("class_name ProbeFoo\n", encoding="utf-8")
    _write_class_cache(tmp_path, [])
    annotated = _annotate(tmp_path, _load("sample_d_addon_singleton_fp.log"))
    assert annotated.view.root_cause_errors == []
    assert CAVEAT_CLASS_CACHE_STALE in annotated.view.caveats
    assert not any(
        c.startswith("identifier_not_found_maybe_unregistered_autoload:")
        for c in annotated.view.caveats
    )
    assert annotated.directive is DIRECTIVE_CLASS_CACHE_STALE
    assert "res://uses_addon.gd" in annotated.view.untrusted_files


def test_hides_autoload_not_demoted_when_stale(tmp_path: Path) -> None:
    (tmp_path / "probe_foo.gd").write_text("class_name ProbeFoo\n", encoding="utf-8")
    _write_class_cache(tmp_path, [])
    annotated = _annotate(
        tmp_path,
        _load("sample_b_autoload_shadow_real.log"),
        frozenset({"Config"}),
    )
    assert annotated.view.status == "HAS_ERRORS"
    assert any("hides an autoload singleton" in e.message for e in annotated.view.root_cause_errors)
    assert CAVEAT_CLASS_CACHE_STALE in annotated.view.caveats
    assert annotated.directive is None


def test_pointer_not_demoted_when_stale(tmp_path: Path) -> None:
    (tmp_path / "probe_foo.gd").write_text("class_name ProbeFoo\n", encoding="utf-8")
    _write_class_cache(tmp_path, [])
    original = _view(_load("sample_f_pointer_dep1.log"))
    annotated = _annotate(tmp_path, _load("sample_f_pointer_dep1.log"))
    assert annotated.view.pending_pointers == original.pending_pointers
    assert annotated.view.root_cause_errors == []
    assert annotated.view.gdscript_complete is False
    assert CAVEAT_CLASS_CACHE_STALE in annotated.view.caveats
    assert annotated.directive is None


def test_multiple_compile_identifiers_emit_sorted_b_caveats(tmp_path: Path) -> None:
    _write_class_cache(tmp_path, [])
    stderr = _load("sample_a_autoload_fp_cold.log") + _load("sample_d_addon_singleton_fp.log")
    annotated = _annotate(tmp_path, stderr)
    symbols = [e.symbol for e in annotated.view.root_cause_errors]
    assert "Config" in symbols
    assert "DummySingleton" in symbols
    config_i = annotated.view.caveats.index(caveat_unregistered_autoload("Config"))
    dummy_i = annotated.view.caveats.index(caveat_unregistered_autoload("DummySingleton"))
    assert config_i < dummy_i
    assert annotated.directive is DIRECTIVE_UNREGISTERED_AUTOLOAD


def test_merge_shell_directive_priority() -> None:
    assert (
        merge_shell_directive(hard_stop=True, gate_directive="g", shell_directive="s")
        is None
    )
    assert (
        merge_shell_directive(hard_stop=False, gate_directive="g", shell_directive="s")
        == "g"
    )
    assert (
        merge_shell_directive(hard_stop=False, gate_directive=None, shell_directive="s")
        == "s"
    )
    assert (
        merge_shell_directive(hard_stop=False, gate_directive=None, shell_directive=None)
        is None
    )
    assert (
        merge_shell_directive(hard_stop=True, gate_directive=None, shell_directive="s")
        is None
    )
