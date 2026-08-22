"""analyzer/capability.py —— 只提取能力与职责矩阵，无对错。

用法：
    python analyzer/capability.py artifacts/<run-id>/N15/ [--out reports/<run-id>/N15/capability/]

服务：N15
输入：已落盘的 N15 目录（--help 原文、各独立副本的 diff / stdout / process-status）
输出：reports/<run-id>/N15/capability/

提取：
    convert / 3to4 / upgrade 相关 CLI 入口是否存在（以 --help 原文为准，不以源码存在为准）
    --validate-conversion-3to4 / --convert-3to4 能否对最小 config_version=4 项目调用
    --convert-3to4 是否真的改了文件（以 diff 为准，不看 stdout）
    upgrade tool 改了哪些文件类型（GDScript、UID、.tscn、.tres、资源路径、import cache）
    用 V3 --import 近似替代 upgrade tool 时的边界

本脚本只出能力矩阵，不宣布流水线形状、不写 CONFIRMED。
「报告成功但文件未变化」本身就是一条要记录的观测。

禁止：import 实验脚本；修改 artifacts/；写死 fixture 名。
本文件只记录契约，不含实现。
"""
