"""N03 采集脚本：class_name 冷缓存假阳性与新增 class_name 的 import 触发。P1-3。

脚本只采集；有序状态机判定交给 analyzer/sequence.py。
本文件只记录契约，不含实现。

================================================================
1. 身份与依赖
================================================================

N = "N03"
依赖：N09、N08
启动时读 artifacts/latest/N09.json 与 N08.json；缺失或 STALE 则按 §0.5.4 / ARCHITECTURE §8 处理。
repeat：判定步 ×3，T2/T5 为 1（只建缓存，不参与判定）
导出：artifacts/latest/N03.json（import_trigger_policy 的脚本侧：class_name_added、gd_file_added）
判定：python analyzer/sequence.py artifacts/<run-id>/N03/

原 N12-a 就是 T4–T6，不再单独执行。
T1–T6 不可并行、不可重排。

================================================================
2. fixture / derived
================================================================

fixture：fixtures/phase1/NP-GLOBALCLASS
无 derived patch。
late_class.gd 与 uses_late.gd 由本脚本在 T3 之后自己创建（一次性操作，不进 util）。
T6 完成后删除工作区，不在 fixture 里留下 late 文件。

================================================================
3. 步骤表（一个 measure 对应一行）
================================================================

T1  V2  uses_class.gd     COLD      ×3   冷缓存下是否报 Identifier not found: ProbeFoo
T2  V3  整个项目          COLD→WARM ×1   重建 class cache、建立 WARM 基线，不参与判定
T3  V2  uses_class.gd     WARM      ×3   import 之后是否干净
    —— 脚本在工作区生成 late_class.gd + uses_late.gd（不 import）——
T4  V2  uses_late.gd      PRESERVE  ×3   新增带新 class_name 的文件后，不 import 会不会报错
T5  V3  整个项目          PRESERVE→WARM ×1  补 import
T6  V2  uses_late.gd      WARM      ×3   补 import 之后是否干净

T4/T5 用 PRESERVE 保住 T2 建立的缓存；这两步前后必须落盘 cache manifest，
用来事后证明缓存确实没变。
每一步都快照 .godot/global_script_class_cache.cfg 的内容与 hash。

================================================================
4. finally 清理
================================================================

杀进程组、删工作区（含 late 文件）、校验原 fixture 仍 clean、无 late 文件残留。
"""
