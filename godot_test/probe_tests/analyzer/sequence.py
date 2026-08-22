"""analyzer/sequence.py —— 有序状态机，断言写在状态转移上。

用法：
    python analyzer/sequence.py artifacts/<run-id>/<N>/ [--out reports/<run-id>/<N>/sequence/]

服务：N03、N06
输入：已落盘的有序步骤目录（含 PRESERVE 步骤前后的 cache-manifest.json）
输出：reports/<run-id>/<N>/sequence/

N03：T1 冷报错而 T3 干净 → 冷缓存假阳性；T4 报错而 T6 干净 → patch 后缓存陈旧。
     须核对 global_script_class_cache.cfg 快照，证明 T4/T5 的 PRESERVE 确实没清缓存。
N06：正确 UID 基线 → 伪造 → 观察 → 补 import → 改 ext_resource → 观察 → 补 import。
     步骤 10 报错而步骤 12 干净 → 资源引用变更后必须重跑 import。

本脚本只报告转移上的观测（哪一步有无目标文案、缓存 hash 是否变），
不宣布 CONFIRMED / import_trigger_policy 的最终取值。

禁止：import 实验脚本；修改 artifacts/；写死 fixture 名。
本文件只记录契约，不含实现。
"""
