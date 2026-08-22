"""N08 采集脚本：exit code 可信度、启动成功语义与 --debug 存活性。P1-2。

脚本只采集；交叉表与存活性判定交给 analyzer/exitcode.py。
本文件只记录契约，不含实现。

================================================================
1. 身份与依赖
================================================================

N = "N08"
依赖：N09（signature 规格已定，才能判断输出是否等价）
启动时读 artifacts/latest/N09.json；缺失 BLOCKED，digest 已变则拒绝（--force-stale 例外）。
repeat = 3；步骤 10 为 1
导出：artifacts/latest/N08.json（exit_code_policy、V4/V6/V7 能力、V8 存活性观测输入）
判定：python analyzer/exitcode.py artifacts/<run-id>/N08/

原 N10 已并入本卡片的步骤 10，不再单独执行。

================================================================
2. fixture / derived
================================================================

按 fixture 分 group，步骤不能按项目矩阵批量展开。
group clean-control → fixtures/phase1/CleanControl（无错 rc 基线）
group np-syntax     → fixtures/phase1/NP-SYNTAX（真错）
group np-autoload   → fixtures/phase1/NP-AUTOLOAD（纯假阳性候选；只采 rc，有真错误=否由 N01 回填）
步骤 10 若在 NP-SYNTAX 上未复现，允许在 NP-ADDON 上补跑一次 V8；两次都未复现则停，不再追加。
无 derived patch。

================================================================
3. 步骤表（一个 measure 对应一行）
================================================================

  1  V1  CleanControl 全项目哨兵              WARM  ×3   无错时 rc 是否为 0
  2  V2  NP-SYNTAX orphan_bad_parse.gd        WARM  ×3   单文件真错时 rc 是否 ≠ 0
  3  V1  NP-SYNTAX 全项目哨兵                 WARM  ×3   项目级真错时 rc 是否 ≠ 0
  4  V3  NP-SYNTAX 整个项目                   COLD  ×3   import 通道遇真错时的 rc
  5  V4  NP-SYNTAX 整个项目                   COLD  ×3   不带 --editor 能否 import
  6  V5  NP-SYNTAX 整个项目                   WARM  ×3   B9：有坏脚本时能否启动成功、rc 是否为 0
  7  V6  NP-SYNTAX 整个项目                   WARM  ×3   --quit-after 2 是否改变 rc 与防挂死
  8  V7  NP-SYNTAX，V1 + --verbose            WARM  ×3   verbose 是否给出结构化信息，rc 是否变化
  9  V2  NP-AUTOLOAD uses_autoload.gd         COLD  ×3   只有假阳性时 rc 会不会被污染成 ≠ 0
 10  V8  NP-SYNTAX orphan_bad_parse.gd        WARM  ×1   --debug 是否挂死或 signal 11
     独立工作区；timeout 30；独立进程组；无论进程状态如何 finally 里 killpg。
     未复现才允许 NP-ADDON 补跑同一观测，两次都未复现则停。

================================================================
4. finally 清理
================================================================

杀进程组（尤其步骤 10）、删工作区、校验原 fixture 仍 clean。
"""
