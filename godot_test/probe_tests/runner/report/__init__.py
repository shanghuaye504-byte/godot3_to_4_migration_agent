"""Report 层：从 artifact 生成报告 A 节与证据索引。B 节仍人手写。

本轮只实现 index.md 证据索引；generate.py（填 reports/README.md A 节）下一阶段。
"""

from . import index

__all__ = ["index"]
