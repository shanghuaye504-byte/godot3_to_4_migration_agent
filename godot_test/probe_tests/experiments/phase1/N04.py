"""N04 采集脚本：级联错误淹没根因。P1-6。

脚本只采集步骤 2–4；步骤 1 是对 N09 artifacts 的离线分析，判定交给 analyzer/cascade.py。
本文件只记录契约，不含实现。

================================================================
1. 身份与依赖
================================================================

N = "N04"
依赖：N09（归一化规则必须先定，否则去重数不可信）、N08
启动时校验 artifacts/latest/N09.json 存在且未过期；缺失 BLOCKED，不得绕过。
repeat = 3
导出：artifacts/latest/N04.json（放大倍数与根因↔症状配对的采集输入）
判定：python analyzer/cascade.py artifacts/<run-id>/N04/

步骤 1 复用 N09 步骤 7、8 的 NP-CASCADE V3 / V1 原始日志，不重跑。

================================================================
2. fixture / derived
================================================================

group np-syntax  → fixtures/phase1/NP-SYNTAX
                   分母必须是 scene_bad.gd（与 NP-CASCADE 的 root_bad.gd 同构：func f() -> void 缺冒号）
                   不得用 orphan_bad_parse.gd（另一种形态：func broken(:）
group np-cascade → fixtures/phase1/NP-CASCADE（1 个坏根 + 5 个直接依赖 + 1 个二级依赖）
无 derived patch。
dep_2–dep_5 不再逐个跑：dep_1 与 leaf 已覆盖直接依赖 / 二级依赖。

================================================================
3. 步骤表（一个 measure 对应一行）
================================================================

  1  —   复用 N09 步骤 7、8 的 NP-CASCADE V3 / V1 日志
         分子：一个根因在项目级扫描下产生多少条 error
         分析前必须先扣掉哨兵 preload 坏文件产生的人造级联边（__probe_ 前缀）
  2  V2  NP-SYNTAX scene_bad.gd     WARM  ×3   分母：同构单根错误在单文件通道下产生多少条
  3  V2  NP-CASCADE dep_1.gd        WARM  ×3   直接依赖被单独 check 时报的是根因还是症状
  4  V2  NP-CASCADE leaf.gd         WARM  ×3   二级依赖被单独 check 时报什么（传递性有多远）

放大倍数 = NP-CASCADE 项目级 error 行数 / scene_bad.gd 单文件 error 行数。

================================================================
4. finally 清理
================================================================

杀进程组、删本实验新建的工作区、校验原 fixture 仍 clean。不删除 N09 的 artifacts。
"""
