"""probe_tests.runner 包入口。

三层职责：
- kernel：统一执行（工作区、进程、缓存态、artifact 落盘、finally 清理）
- analyzers：按 analysis.type 做异构判定，写出 evaluation.json
- report：从 artifact 生成报告 A 节与证据索引

本文件目前只作包标记，不含实现。
"""
