# 索引与验证底座：问题与复现

[全项目执行顺序](../LANDMARKS.md) · [全项目问题总账](../DEFECTS.md) · [上级文档](../DEFECTS.md) · [本级路标](../codebase_index/LANDMARKS.md)

按执行顺序排列。**已复现/源码确认**指已有代码证据；**规划风险**指组件尚未实现，复现描述是先要写下的失败测试。所有代码修复仍未完成，不能把新文档当作修复结果。

## 下级导航

- [符号与依赖索引](index/DEFECTS.md)
- [Godot 验证栈](godot_mcp/DEFECTS.md)

## 本范围问题索引

- [ ] S02 · [IDX-01 · 中文让符号名和调用关系切片错位](index/DEFECTS.md)
- [ ] S03 · [IDX-02 · 现有依赖边不足以排序根因脚本](index/DEFECTS.md)
- [ ] S04 · [SCN-01 · 真实规则库查错表，旧类型检查被静默跳过](index/src/codeindex/scene/DEFECTS.md)
- [ ] S04 · [SCN-02 · 只检查一个场景，却宣布其他场景已修复](index/src/codeindex/scene/DEFECTS.md)
- [ ] S05 · [SCN-03 · 同名回调跨脚本误报，并且只报第一个引用](index/src/codeindex/scene/DEFECTS.md)
- [ ] S05 · [SCN-04 · 基线有底层函数，却没有安全的生产冻结入口](index/src/codeindex/scene/DEFECTS.md)
- [ ] S09 · [VER-01 · 局部检查污染全库历史，造成假震荡](godot_mcp/DEFECTS.md)
- [ ] S09 · [VER-02 · 熔断已 OPEN，下一次健康输出又允许继续](godot_mcp/DEFECTS.md)
- [ ] S09 · [VER-03 · retry_gate YAML 没接到默认工具入口](godot_mcp/DEFECTS.md)
- [ ] S10 · [VER-04 · 快照漏场景/项目配置，相关修改无法驱动重导](godot_mcp/DEFECTS.md)
- [ ] S10 · [VER-05 · class_name 与重复 UID 的重导触发有盲区](godot_mcp/DEFECTS.md)
- [ ] S11 · [VER-06 · 全局单槽状态和锁范围不适合多次仓库运行](godot_mcp/DEFECTS.md)

## 本级负责的问题

复现均在临时项目/数据库执行；需要 Git 时先提交干净来源，注入成功 sync；需要引擎的条目先完成 S00。源码链接用于定位，精确函数名写在正文，避免依赖易漂移行号。

<a id="cfg-01"></a>

### CFG-01：规则库相对路径跟着启动目录漂移

**顺序 / 状态**：[S02](../LANDMARKS.md)；源码确认；代码待修。

**范围与原因**：index 配置把 migration_rules_db 的相对路径直接 resolve，基准是进程 CWD；同一份配置从不同目录启动可能打开不同规则库。

**具体表现**：配置在 /tmp/configs/config.yaml，规则路径为 rules.db；从项目根启动时却寻找项目根/rules.db。

**如何复现**：在临时目录创建配置及相邻 rules.db；分别在两个不同 CWD 调用 load_config(config_path)，比较 migration_rules_db。当前结果随 CWD 改变。

**修复办法**：明确一个规则：配置中的相对路径一律相对配置文件目录；环境变量覆盖值单独规范化。不存在就明确失败，不按“哪个文件存在”切换解释。

- [ ] **验收测试**：覆盖绝对路径、相对路径、文件缺失和切换 CWD；同时确认 project_root、index_state_dir 的解析语义写清。

**关键源码**：[config.py](index/src/codeindex/config.py)、[config.example.yaml](config.example.yaml)。
