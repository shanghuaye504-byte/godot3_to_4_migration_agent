"""N06 采集脚本：invalid UID 严重度与资源引用变更后的 import 触发。P1-8。

脚本只采集；状态机交给 analyzer/sequence.py，Δ 归类交给 analyzer/delta.py。
本文件只记录契约，不含实现。

================================================================
1. 身份与依赖
================================================================

N = "N06"
依赖：N08、N09、N03（脚本侧的 import 触发结论先落地）
启动时读上游 latest JSON；缺失或 STALE 则按契约处理。
repeat：观测步 ×3，建缓存 / 补 import 步为 1
导出：artifacts/latest/N06.json
      （严重度策略；import_trigger_policy 的资源侧：scene_ext_resource_changed、uid_changed）
判定：python analyzer/sequence.py / analyzer/delta.py artifacts/<run-id>/N06/

原 N12-b 并入步骤 9–12，不再单独执行。
全程一个工作区、严格按序。禁止在 fixture 里保存错误 UID。

================================================================
2. fixture / derived
================================================================

fixture：fixtures/phase1/NP-RESOURCE（main.tscn 通过 ext_resource 引用 sub.tscn）
derived：derived/NP-RESOURCE@uid-baseline/{patch.diff, provenance.yaml}
优先 apply_derived；build hash 空或不一致则 manual gate（GUI 打开并保存，把 diff 冻回 derived/）。
伪造 UID、改 ext_resource 都是本脚本的私事，不进 util，只发生在临时工作区。

================================================================
3. 步骤表（一个 measure 对应一行）
================================================================

  1   —   apply_derived(NP-RESOURCE@uid-baseline)，不可用则 manual gate
          先有正确的 UID 基线，才有资格伪造
  2   V3  整个项目          COLD→WARM ×1   正确基线下 import 是否干净，并建立 WARM
  3   V1  全项目哨兵        WARM      ×3   正确基线的输出（本实验的第一优先对照物）
  4   —   本脚本把 .uid / .tscn 里的 uid:// 改成伪造值（不进 util）
  5   V2  sub.gd            WARM      ×3   单文件通道能不能看见 UID 问题
  6   V1  全项目哨兵        WARM      ×3   invalid UID 以什么严重度前缀出现
  7   V3  整个项目          WARM      ×3   import 能否自愈伪造的 UID
  8   V1  全项目哨兵        WARM      ×3   补 import 之后噪声是否消失
  9   —   本脚本把 main.tscn 的 ext_resource 指向另一个路径（原 N12-b 触发物）
 10   V1  全项目哨兵（不 import） WARM ×3   资源引用变更后不 import 会不会报错
 11   V3  整个项目          WARM      ×1   补 import
 12   V1  全项目哨兵        WARM      ×3   补 import 之后是否干净

步骤 10 观察的是「缓存没被清」时的行为；前后落盘 cache manifest。

================================================================
4. finally 清理
================================================================

杀进程组、删工作区（错误 UID 一并销毁）、校验原 fixture 仍为正确基线之前的干净状态。
"""
