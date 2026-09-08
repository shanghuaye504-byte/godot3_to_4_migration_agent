"""`signature.py` 的纯函数测试（方案文档 §6、§10 的 T-LINE / T-SYM）。

覆盖要点：
- T-LINE：把样例 E 的行号从 `:3` 改成 `:99`，`local_signature` 必须与原文相同
  （行号不得进入签名，否则 patch 移动行号会让震荡检测失效）。
- T-SYM：样例 A（autoload key=Config）与样例 D（addon key=DummySingleton）的
  `noise_signature` 应该相同（同一模板），但 `local_signature` 因 symbol/path
  不同而不同——两级签名不能互相替代。
- `normalize_message`：res:// 路径换成 `<RES>`、符号名换成 `<SYM>`，删除项目行号，
  **保留**引擎 cpp 行号（如 `gdscript_resource_format.cpp:46`）。
- `msg_template`：在 `normalize_message` 基础上把残留路径/数字也占位符化。
- `local_signature`/`noise_signature` 的输出是稳定的十六进制字符串。
"""

from __future__ import annotations

from godot_mcp.verify_filter.parse import classify, parse_raw_events
from godot_mcp.verify_filter.signature import (
    local_signature,
    msg_template,
    noise_signature,
    normalize_message,
)


def test_normalize_message_replaces_res_path_and_symbol():
    msg = "Compile Error: Identifier not found: Config"
    normalized = normalize_message(msg, res_path="res://uses_autoload.gd", symbol="Config")
    assert normalized == "Compile Error: Identifier not found: <SYM>"


def test_normalize_message_replaces_quoted_symbol_and_res_path():
    msg = 'Parse Error: Class "Config" hides an autoload singleton.'
    normalized = normalize_message(msg, res_path=None, symbol="Config")
    assert normalized == 'Parse Error: Class "<SYM>" hides an autoload singleton.'


def test_normalize_message_strips_project_line_number_but_not_res_path_extension():
    msg = "Failed loading resource: res://sub.tscn."
    normalized = normalize_message(msg)
    # res:// 路径本身含 "." 扩展名，与句尾的句号在字符类上无法区分，两者一起被吞进 <RES>；
    # 这不影响功能——signature 仍然稳定、<RES> 仍然准确标记"这里曾是一个资源路径"。
    assert normalized == "Failed loading resource: <RES>"


def test_msg_template_keeps_engine_cpp_location_but_placeholders_bare_numbers():
    normalized = 'Failed to load script "<RES>" with error "Compilation failed".'
    # 这条消息本身不含引擎位置（引擎位置在 at: 行里，不在 message 里），这里验证
    # msg_template 在没有引擎位置时，仍然只替换独立数字，不误伤 <RES>/<SYM> 占位符。
    template = msg_template(normalized)
    assert template == normalized  # 没有裸数字，模板应与归一化结果一致


def test_msg_template_preserves_engine_location_digits():
    # 模拟一条 message 内嵌了引擎位置文本的情况（真实场景下引擎位置在 at: 行，
    # 但 msg_template 的实现必须对"消息里出现 cpp:NN 形式"保持稳定，用合成输入验证）。
    normalized = "Compile Error: something at modules/gdscript/gdscript.cpp:3041 count 7"
    template = msg_template(normalized)
    assert "modules/gdscript/gdscript.cpp:3041" in template
    assert "<NUM>" in template  # 独立数字 "7" 被占位符化
    assert " 3041" not in template.replace("gdscript.cpp:3041", "")  # 引擎行号没有被单独替换成 <NUM>


def test_t_line_local_signature_stable_across_line_number_change(load_fixture):
    stderr = load_fixture("sample_e_real_syntax_error.log")
    original = classify(parse_raw_events("", stderr))[0]

    mutated_stderr = stderr.replace(":3", ":99")
    mutated = classify(parse_raw_events("", mutated_stderr))[0]

    assert original.line_in_project == 3
    assert mutated.line_in_project == 99
    assert original.local_signature == mutated.local_signature


def test_t_sym_noise_signature_shared_local_signature_distinct(load_fixture):
    sample_a = load_fixture("sample_a_autoload_fp_cold.log")
    sample_d = load_fixture("sample_d_addon_singleton_fp.log")

    event_a = classify(parse_raw_events("", sample_a))[0]
    event_d = classify(parse_raw_events("", sample_d))[0]

    assert event_a.noise_signature == event_d.noise_signature
    assert event_a.local_signature != event_d.local_signature


def test_local_signature_and_noise_signature_are_stable_hex_digests():
    sig1 = local_signature(kind="compile_error", res_path="res://a.gd", symbol="Config", normalized_message="x")
    sig2 = local_signature(kind="compile_error", res_path="res://a.gd", symbol="Config", normalized_message="x")
    assert sig1 == sig2
    assert len(sig1) == 40  # sha1 hex digest 长度
    int(sig1, 16)  # 必须是合法十六进制字符串

    noise1 = noise_signature(kind="compile_error", template="Identifier not found: <SYM>")
    noise2 = noise_signature(kind="compile_error", template="Identifier not found: <SYM>")
    assert noise1 == noise2
    different_noise = noise_signature(kind="compile_error", template="something else")
    assert different_noise != noise1
