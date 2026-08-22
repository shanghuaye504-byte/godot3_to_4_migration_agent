"""N21 采集脚本：官方 3.5/3.6 Demo 自动迁移残余问题分布。P2-2。

脚本只采集；数据集迭代与聚合统计交给 analyzer/corpus.py。
本文件只记录契约，不含实现。

================================================================
1. 身份与依赖
================================================================

N = "N21"
依赖：N15（流水线形状）+ 第一阶段全部策略
      （signature 规格、exit code 策略、import 触发表、严重度策略、shader 边界）
启动时必须读 artifacts/latest/N15.json；能力门失败则本实验 BLOCKED，不得静默跳过。
其余上游 latest JSON 缺失或 STALE 同样按契约处理。
repeat：A 段为 1；B1–B3 为 3
导出：artifacts/latest/N21.json（残余分布、支持边界、import 成本的采集输入）
判定：python analyzer/corpus.py artifacts/<run-id>/N21/

吸收了原 N19（import 耗时）、N17（TODO 与 instance() 残余）、N18（shader 残余）、N11（大文件预扫描）。
converter 的 stdout 不作为 checkpoint；一切以文件 diff 与后续 verifier 结果为准。
converter 调用一律包 timeout + killpg。

================================================================
2. fixture / derived / manifest
================================================================

仓库里不留 datasets/。每个 Demo 按下面的 in-script manifest（URL + commit）
clone 到 workspaces/。当前为骨架，不含具体 Demo 条目。

# manifest 规划字段（每条 Demo）:
#   id, name, source_version, tag_or_commit, source_url,
#   tree_hash, file_count, total_size, godot4_demo_ref（弱参考，不能默认逐文件一致）

官方对应 4.x Demo 只能作为弱参考。
A3 冻结之后不得再在同一目录上运行任何会修改文件的步骤；B1–B3 各自消费只读快照的副本。

================================================================
3. 步骤表（一个 measure 对应一行；每个 Demo 独立转换工作区）
================================================================

A0  预扫描     Demo manifest              ×1   文件树 hash、文件数、资源规模，
                                               以及最大 .gd 字节数与最长单行（原 N11）
A1  converter  每个 Demo 一个独立转换工作区 ×1   完整 diff、stdout、TODO 数、明确跳过与静默跳过；
                                               记录是否 timeout、是否被 killpg
A2  upgrade 或 V3  同一转换工作区 COLD    ×1   按 N15 的结论选路，把项目带到可 import 状态
A3  冻结快照   转换结果                    —    冻结为只读 converted snapshot

B1  V1  snapshot 副本  COLD  ×3   残余问题全集 + cold import 成本
B2  V1  snapshot 副本  WARM  ×3   残余是否与 COLD 一致 + warm 成本（原 N19）
B3  V5  snapshot 副本  WARM  ×3   启动阶段才暴露的残余
B4  离线分类  A1–B3 的全部日志与 diff      —    交给 analyzer/corpus.py，本脚本不分类

无法自动判断的进入 UNCLASSIFIED_NEEDS_REVIEW，不能静默丢弃。
报告成功但文件未变化本身就是一条要记录的结论。

================================================================
分类体系（从旧 taxonomy.yaml 迁入；判定由 corpus.py 做，脚本不计算）
================================================================

A. Converter 行为
    正确转换；部分转换；插入 TODOConverter3To4；明确跳过；静默跳过；
    错误转换；报告成功但文件未变化；timeout；crash；产生破坏性文件修改。

B. Verifier 阶段
    parse error；compile error；import/resource error；invalid UID warning；
    shader error；startup/runtime error；warning；
    verifier false positive；verifier false negative；infrastructure failure。

C. 根因类别
    API rename；方法签名变化；参数顺序变化；instance() / scene 实例化；
    yield / await 时序；Tween 重构；生命周期变化；节点或属性改名；
    signal/connect API；scene/resource 序列化；UID；shader；autoload/addon；
    C#/GDExtension；二进制资源；converter 缺陷；4.0→4.7 版本漂移；其他待人工确认。

D. 每条残余记录字段
    demo_id source_version source_commit godot_build_hash
    path file_type raw_message normalized_signature severity
    phase root_cause_category version_drift_bucket
    converter_touched_file converter_todo_present
    verifier_command cache_state repeat_count
    is_root_cause is_cascade auto_fixable needs_judge needs_human

================================================================
4. finally 清理
================================================================

杀进程组、删转换工作区与 B 段副本（只读 snapshot 若需保留则另议，默认实验结束即空）、
校验 fixtures/ 未被改写。仓库里不留下 clone 的 Demo 源码。
"""
