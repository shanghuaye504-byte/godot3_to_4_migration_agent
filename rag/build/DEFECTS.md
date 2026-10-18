# 知识库构建：问题与复现

[全项目执行顺序](../../LANDMARKS.md) · [全项目问题总账](../../DEFECTS.md) · [上级文档](../DEFECTS.md) · [本级路标](../build/LANDMARKS.md)

按执行顺序排列。**已复现/源码确认**指已有代码证据；**规划风险**指组件尚未实现，复现描述是先要写下的失败测试。所有代码修复仍未完成，不能把新文档当作修复结果。

## 本级负责的问题

复现均在临时项目/数据库执行；需要 Git 时先提交干净来源，注入成功 sync；需要引擎的条目先完成 S00。源码链接用于定位，精确函数名写在正文，避免依赖易漂移行号。

<a id="rag-01"></a>

### RAG-01：散文写入与读取路径不一致，测试靠 skip 避开

**顺序 / 状态**：[S12](../../LANDMARKS.md)；已复现及源码确认；代码待修。

**范围与原因**：parser 写入 _raw/official_upgrading_guide，manifest、清理器和测试仍查 tier_b_prose 根。真实输入未进入指纹，测试也没验证到。

**具体表现**：8 份 prose.jsonl 实际存在，但 test_prose_jsonl_present 跳过；修改这些散文可能不改变 manifest 中的输入锁定。

**如何复现**：运行 rag/test/test_build_artifacts.py 中该测试并加 -rs 查看 skip；对照 parser 的写入路径与 build_tier_a 的 glob。

**修复办法**：统一路径函数，manifest 记录相对路径和内容哈希，清理器与测试复用同一枚举；预期产物已提交时缺失应 fail，不用 skip 掩盖。

- [ ] **验收测试**：8 份文件实际被枚举；修改任一输入会改变指纹；空目录/缺输入显式失败。

**关键源码**：[parse_upgrading_docs.py](parse_upgrading_docs.py)、[build_tier_a.py](build_tier_a.py)、[clean_prose_jsonl.py](clean_prose_jsonl.py)、[test_build_artifacts.py](../test/test_build_artifacts.py)。

<a id="rag-05"></a>

### RAG-05：旧构建和评测命令仍是占位壳

**顺序 / 状态**：[S12](../../LANDMARKS.md)；源码确认；清理待做。

**范围与原因**：真实 B 构建由 chunk_and_embed 完成，旧 build_tier_b 仍退出；旧评测命令也仍抛未实现异常。新用户按旧入口无法完成任务。

**具体表现**：运行 build_tier_b.py 看见占位退出，而 README 可能仍指向它。

**如何复现**：只读检查三个旧入口的 main/顶层代码；以子进程调用 --help，记录退出信息。不要为复现触发真实嵌入构建。

**修复办法**：旧入口转发到现有命令并明确弃用提示，或删除并同步所有引用；删除误生成的 :memory:.ses。

- [ ] **验收测试**：兼容入口参数能转发，--skip-embed 不下载模型；文档无指向已删入口的链接。

**关键源码**：[build_tier_b.py](build_tier_b.py)、[chunk_and_embed.py](chunk_and_embed.py)、[gen_eval_set.py](../eval/gen_eval_set.py)、[run_ablation.py](../eval/run_ablation.py)。
