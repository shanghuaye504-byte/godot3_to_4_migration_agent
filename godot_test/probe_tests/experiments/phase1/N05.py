"""N05 采集脚本：warning 与 error 严重度混淆。P1-7。

脚本只采集；Δ 归类交给 analyzer/delta.py。
本文件只记录契约，不含实现。

================================================================
1. 身份与依赖
================================================================

N = "N05"
依赖：N08（V8 已判定不可用，本实验不再重试 --debug）、N09
启动时读上游 latest JSON；缺失或 STALE 则按契约处理。
repeat = 3
导出：artifacts/latest/N05.json（严重度采集策略的采集输入）
判定：python analyzer/delta.py artifacts/<run-id>/N05/

对照：CleanControl 的 BG（背景里本来就有多少 WARNING）。
原方案里的 V8 对照删除：warning 只能走项目设置这一条路。

================================================================
2. fixture / derived
================================================================

fixture：fixtures/phase1/NP-WARN（warn.gd 埋 warning；addons/noisy/noisy.gd 验证 exclude_addons）
无 derived patch。
配置片段：experiments/common/fragments/np-warn-debug.ini
  gdscript/warnings/enable=true + exclude_addons=true
配置注入只发生在「启用 warning」组的临时工作区，用 probe.settings，不写回 fixture。

================================================================
3. 步骤表（一个 measure 对应一行；两个 group）
================================================================

group default（默认设置，不注入片段）:
  1  V2  warn.gd           WARM  ×3   默认设置下单文件通道有没有 warning
  2  V1  全项目哨兵        WARM  ×3   默认设置下项目级扫描有没有 warning
  3  V3  整个项目          COLD  ×3   import 通道有没有 warning

group warn-enabled（probe.settings(np-warn-debug.ini)）:
  4  —   注入片段
  5  V2  warn.gd           WARM  ×3   是否以 WARNING: 前缀出现在 stderr 里
  6  V1  全项目哨兵        WARM  ×3   项目级扫描下的 warning 数量与前缀
  7  V3  整个项目          COLD  ×3   exclude_addons 是否真的屏蔽了 addons/noisy/noisy.gd 的 warning

================================================================
4. finally 清理
================================================================

杀进程组、删工作区、校验原 fixture 仍 clean（project.godot 未被改写）。
"""
