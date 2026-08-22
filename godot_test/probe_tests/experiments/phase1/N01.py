"""N01 采集脚本：autoload 假阳性（#78587）。P1-4。

脚本只采集；Δ 归类交给 analyzer/delta.py。
本文件只记录契约，不含实现。

================================================================
1. 身份与依赖
================================================================

N = "N01"
依赖：N09、N08、N03（COLD/WARM 是否有效已由 N03 裁定）
启动时读上游 latest JSON；缺失或 STALE 则按契约处理。
repeat = 3；步骤 2（warm-up）为 1
导出：artifacts/latest/N01.json（autoload 过滤策略的采集输入）
判定：python analyzer/delta.py artifacts/<run-id>/N01/

对照优先级：同项目 clean 埋点 AL-MAIN（main.gd 走场景）> CleanControl BG。
埋点 AL-RES-LOADER（res_loader.gd.disabled，#120225）本轮不启用，见 README §2.3。

================================================================
2. fixture / derived
================================================================

fixture：fixtures/phase1/NP-AUTOLOAD（Config 注册为 autoload；uses_autoload.gd 孤立脚本调 Config.ping()）
无 derived patch。
两个 .disabled 文件在任何情况下都不得同时启用。
所有改名与配置注入只发生在临时工作区，禁止写回 fixture。

================================================================
3. 步骤表（一个 measure 对应一行）
================================================================

  1  V2  uses_autoload.gd     COLD      ×3   冷缓存下是否报 Identifier not found: Config
  2  V3  整个项目             COLD→WARM ×1   建立 WARM 基线，不参与判定
  3  V5  整个项目             WARM      ×3   运行时是否正常打印 Config.ping() called
  4  V2  uses_autoload.gd     WARM      ×3   WARM 下是否仍然报错 → 能否用强制 warm-up 规避
  5  V1  全项目哨兵           WARM      ×3   项目级扫描会不会把这个 FP 放大
  6  —   rename_file 启用 shadow_config.gd.disabled（埋点 AL-SHADOW）  造出与 FP 文案相似的真错误
  7  V2  shadow_config.gd     WARM      ×3   Class "Config" hides an autoload singleton 是否出现
  8  V5  整个项目             WARM      ×3   真错误是否同样在运行时暴露（与步骤 3 对比）

步骤 6 的 rename 是本脚本的私事，不进 util。
步骤 6–8 不是可选装饰：假阳性本体与真错误必须分别确认，否则过滤器会把真错误一起吃掉。

================================================================
4. finally 清理
================================================================

杀进程组、删工作区、校验原 fixture 仍 clean（.disabled 文件保持未启用）。
"""
