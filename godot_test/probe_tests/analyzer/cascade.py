"""analyzer/cascade.py —— 根因候选与症状配对、放大倍数。

用法：
    python analyzer/cascade.py artifacts/<run-id>/N04/ [--out reports/<run-id>/N04/cascade/]

服务：N04
输入：N04 自己的步骤 2–4 日志 + N09 已落盘的 NP-CASCADE V3/V1 日志（步骤 1 复用，不重跑）
输出：reports/<run-id>/N04/cascade/

必须先扣掉哨兵 preload 坏文件产生的人造级联边（__probe_ 前缀），否则放大倍数被高估。
分母必须是 NP-SYNTAX 的 scene_bad.gd，不得用 orphan_bad_parse.gd。

放大倍数 = NP-CASCADE 项目级 error 行数 / scene_bad.gd 单文件 error 行数。

判定规则草案（只作为归类线索，不由本脚本宣布 CONFIRMED）：
    at: 位置指向引擎内部路径（modules/gdscript/*.cpp）的行 = 症状
    指向 res:// 的行 = 根因候选

五个数都要落盘：原始错误行数、去重后 signature 数、根因候选数、症状数、放大倍数，
外加一张「根因 error ↔ 症状 error」文案配对表。

禁止：import 实验脚本；修改 artifacts/；写死 fixture 名。
本文件只记录契约，不含实现。
"""
