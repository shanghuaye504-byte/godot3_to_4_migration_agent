"""N02 采集脚本：addon 单例假阳性（#111515）。P1-5。

脚本只采集；Δ 归类交给 analyzer/delta.py。
本文件只记录契约，不含实现。

================================================================
1. 身份与依赖
================================================================

N = "N02"
依赖：N01（先知道静态 [autoload] 的 FP 行为，才能判断 addon 是不是同根同源）
启动时读 artifacts/latest/N01.json；缺失或 STALE 则按契约处理。
repeat = 3
导出：artifacts/latest/N02.json（符号白名单实现成本裁决的采集输入）
判定：python analyzer/delta.py artifacts/<run-id>/N02/

对照：NP-AUTOLOAD（最近邻探针，不是 CleanControl）。
本实验不跑 V8——--debug 已由 N08 一次性裁决。

================================================================
2. fixture / derived
================================================================

fixture：fixtures/phase1/NP-ADDON（plugin.gd 在 _enable_plugin() 里 add_autoload_singleton("DummySingleton", ...)）
derived：derived/NP-ADDON@plugin-enabled/{patch.diff, provenance.yaml}
优先 apply_derived；build hash 空或不一致则退回 manual gate（GUI 启用插件，把新 diff 冻回 derived/）。
若 GUI 写入二进制或不可移植内容（ARCHITECTURE §7），derived 方案作废，永久 manual gate。
原始 NP-ADDON 必须保持「插件未启用」的干净状态。

================================================================
3. 步骤表（一个 measure 对应一行）
================================================================

  0  —   apply_derived(NP-ADDON@plugin-enabled)，不可用则 manual gate
         本实验的核心事实：启用插件后 project.godot 到底被写了什么
  1  V5  整个项目          WARM  ×3   运行时单例是否注册成功（证明符号真实存在）
  2  V2  uses_addon.gd     WARM  ×3   check-only 是否报 DummySingleton 找不到
  3  V2  uses_addon.gd     COLD  ×3   冷态是否加剧（与 N01 的 COLD/WARM 结论对照）
  4  V1  全项目哨兵        WARM  ×3   项目级扫描是否放大该 FP

================================================================
4. finally 清理
================================================================

杀进程组、删工作区、校验原 NP-ADDON 仍为插件未启用、git clean。
"""
