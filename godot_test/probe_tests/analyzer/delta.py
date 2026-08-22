"""analyzer/delta.py —— Δ = noise_signature 减法，再用 local_signature 对埋点表归类。

用法：
    python analyzer/delta.py artifacts/<run-id>/<N>/ [--out reports/<run-id>/<N>/delta/]

服务：N01、N02、N05、N06、N07
输入：已落盘的实验目录 + 只读 annotations/（不写死 fixture 名，按 artifacts 元数据定位）
输出：reports/<run-id>/<N>/delta/

两步不可合并（README §0.4.2）：
  1. BG(cmd, state) = CleanControl 在该 (cmd,state) 下 ERROR/SCRIPT ERROR/WARNING 的 noise_signature 集
  2. Δ = 探针输出中 noise_signature 不在 BG 里的行
  3. 用 local_signature + 埋点表把 Δ 命中 → REAL 桶，未命中 → CLEAN 桶

陷阱：模板化会把 Identifier not found: Config（N01）和 Identifier not found: ProbeFoo（N03）
折成同一个 noise_signature。所以 BG 减法只做粗筛，TP/FP 归类必须回到 local_signature。

埋点表只记录「埋了什么 + 怎么匹配」，不预言引擎文案。
real/clean 是归类桶，不是事先标注。
SEV-MISMATCH / BG-DRIFT / CONFIRMED 不由本脚本宣布，escalate 给人。

禁止：import 实验脚本；修改 artifacts/；写死 fixture 名。
本文件只记录契约，不含实现。
"""
