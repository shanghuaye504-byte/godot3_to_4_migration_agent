"""probe_tests.runner 包入口。

- kernel：统一执行与原始测量落盘；不知道实验赢了没有；忽略 YAML analysis.*
- analyzers：只被 Analyzer.py 调用，写入 report/<phase>/<N>/
- report：生成 artifacts/<run-id>/index.md 证据索引（不是判定）

判定入口是 probe_tests/Analyzer.py，不是 python -m runner。
人写实验报告在 reports/README.md。本文件只作包标记。
"""
