"""N07 采集脚本：shader verifier 盲区（漏报，不是假阳性）。P1-9。

脚本只采集；Δ 归类交给 analyzer/delta.py。
本文件只记录契约，不含实现。

================================================================
1. 身份与依赖
================================================================

N = "N07"
依赖：N08（命令能力）、N09（归一化）
启动时读上游 latest JSON；缺失或 STALE 则按契约处理。
repeat = 3
导出：artifacts/latest/N07.json（验证边界声明；哨兵是否扩展到 shader 的 capability）
判定：python analyzer/delta.py artifacts/<run-id>/N07/

对照：同项目 good.gdshader（第一优先，区分「这个 shader 坏」与「任何 shader 都不报」）> CleanControl。
每一步都必须与 good.gdshader 侧的输出对比。

若确认 V2 的 preload 方案成立，本实验只输出 capability，不直接改写其他 fixture；
是否把哨兵 preload 扩展到 .gdshader 由 probe.sentinel(include=...) 统一控制，不在各脚本里各写一份。

================================================================
2. fixture / derived
================================================================

fixture：fixtures/phase1/NP-SHADER
  坏 bad.gdshader → mat.tres → 挂在 main.tscn 的 Sprite2D 上
  shader_user.gd 用 preload 引用它
  同项目另有 good.gdshader → good_mat.tres 作为正确 shader 对照
无 derived patch。

================================================================
3. 步骤表（一个 measure 对应一行）
================================================================

  1  V2  shader_user.gd    COLD  ×3   preload 能否把 shader 错误「抬」到 GDScript 解析期
  2  V3  整个项目          COLD  ×3   import 阶段是否报 shader 错误
  3  V2  shader_user.gd    WARM  ×3   暖态下是否仍然可见
  4  V5  整个项目          WARM  ×3   场景启动阶段是否报（main.tscn 上挂着坏材质）
  5  V1  全项目哨兵        WARM  ×3   默认哨兵（只 preload *.gd）的覆盖范围到哪

每一步标注信号来源：脚本解析 / 资源 import / 场景启动。三类必须分开存。

================================================================
4. finally 清理
================================================================

杀进程组、删工作区、校验原 fixture 仍 clean。
"""
