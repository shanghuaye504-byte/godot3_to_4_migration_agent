"""analyzer/corpus.py —— 数据集迭代 + 聚合统计。

用法：
    python analyzer/corpus.py artifacts/<run-id>/N21/ [--out reports/<run-id>/N21/corpus/]

服务：N21
输入：已落盘的 N21 目录（每 Demo 的 A0–B3 日志、diff、wall time）
输出：reports/<run-id>/N21/corpus/

按 N21.py 注释里的分类体系逐条归类（Converter 行为 / Verifier 阶段 / 根因类别），
统计 TODOConverter3To4 与 instance() 残余、shader 残余、import 耗时聚合。
无法自动判断的进入 UNCLASSIFIED_NEEDS_REVIEW，不能静默丢弃。
converter 的 stdout 不作为 checkpoint；报告成功但文件未变化要单独成条。

每条残余记录必须落齐 N21 卡片 D 节字段。
本脚本出分布与聚合，不宣布支持边界、不写 CONFIRMED。

禁止：import 实验脚本；修改 artifacts/；写死 fixture 名。
本文件只记录契约，不含实现。
"""
