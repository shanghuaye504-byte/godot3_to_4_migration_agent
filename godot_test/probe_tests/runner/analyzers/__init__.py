"""Analyzer 层：按 YAML 的 analysis.type 分派。

八类：capability_probe / stability / baseline_delta / state_sequence /
liveness / transform_diff / interference / corpus_survey。
实现放在同目录各模块；只被 Analyzer.py / 事后选型脚本调用。
Kernel 与 python -m runner 不 import 本包。
"""

from . import stability  # noqa: F401
