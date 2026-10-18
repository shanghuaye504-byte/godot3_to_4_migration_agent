# 索引与验证底座：实现路标

[全项目执行顺序](../LANDMARKS.md) · [全项目问题总账](../DEFECTS.md) · [上级文档](../LANDMARKS.md) · [本级问题](DEFECTS.md)

更新：2026-10-17。以当前代码为现状；下文未勾选项均为待修复/待开发。**按根目录 S00→S25 执行，到本目录时再展开；本级编号不重新从 1 开始。**

## 共享配置只使用真实字段

```yaml
project_root: /absolute/path/to/project
index_state_dir: /absolute/path/to/project/.codeindex
godot_binary: /absolute/path/to/godot
migration_rules_db: /absolute/path/to/rag/artifacts/rules.db
retry_gate:
  rounds_limit: 20
  no_progress_window: 3
  oscillation_window: 3
  file_stuck_threshold: 3
  infra_failure_streak_limit: 3
```

这里的 20/3 是初始运行阈值，不是调优结论。`oscillation_window` 当前算法只识别固定 A→B→A，不能改成 5 就期待检测更长周期。

index 与 godot_mcp 的 `Config` 是各自独立类型；宿主分别创建，不互相强制 import。索引库真实路径是 `<project>/.codeindex/index.db`，不是 `.codeindex.db`。配置相对路径按 S02 明确为相对于配置文件。

## 边界

索引是符号/引用证据，不能替代引擎验证；引擎解析也不能证明行为正确。场景旁路表与脚本表保持分开。现有 watcher 是 `watchfiles`，符号查询使用普通 SQLite 索引；不为满足旧文字而新增 FTS5 或 watchdog。

## 下级导航

- [符号与依赖索引](index/LANDMARKS.md)
- [Godot 验证栈](godot_mcp/LANDMARKS.md)

## 本目录执行清单

<a id="s02"></a>

### S02：修中文索引与配置路径

- [ ] 完成 [S02](../LANDMARKS.md#s02) 的本范围任务。

**先决条件**：根队列中本步之前的验收门已通过；新增/缺陷测试先写，再改实现。

**做什么**：只负责共享配置相对路径规则，并为 index/godot_mcp 明确字段边界；UTF-8 修复在 index 子目录展开。

**交付物**：交付不随 CWD 漂移的配置解析。

**验收**：切换 CWD、缺文件、绝对/相对配置及环境覆盖测试。

**问题详情与复现**：[IDX-01 · 中文让符号名和调用关系切片错位](index/DEFECTS.md#idx-01)；[CFG-01 · 规则库相对路径跟着启动目录漂移](DEFECTS.md#cfg-01)。

**具体落点**：[符号与依赖索引](index/LANDMARKS.md#s02)。

<a id="s03"></a>

- [ ] **S03 · 补依赖提取，再做根因排序**：[符号与依赖索引](index/LANDMARKS.md#s03)；先完成根队列的前置步骤，验收看负责目录。

<a id="s04"></a>

- [ ] **S04 · 修真实规则库接入和场景增量对比**：[场景检查与基线](index/src/codeindex/scene/LANDMARKS.md#s04)；先完成根队列的前置步骤，验收看负责目录。

<a id="s05"></a>

- [ ] **S05 · 修场景回调归属并接通一次性冻结**：[符号与依赖索引](index/LANDMARKS.md#s05)、[场景检查与基线](index/src/codeindex/scene/LANDMARKS.md#s05)；先完成根队列的前置步骤，验收看负责目录。

<a id="s09"></a>

- [ ] **S09 · 隔离局部检查、修熔断和阈值接线**：[Godot 验证栈](godot_mcp/LANDMARKS.md#s09)；先完成根队列的前置步骤，验收看负责目录。

<a id="s10"></a>

- [ ] **S10 · 补验证快照与重导触发范围**：[Godot 验证栈](godot_mcp/LANDMARKS.md#s10)；先完成根队列的前置步骤，验收看负责目录。

<a id="s11"></a>

- [ ] **S11 · 绑定每次运行的状态、锁和索引同步**：[Godot 验证栈](godot_mcp/LANDMARKS.md#s11)；先完成根队列的前置步骤，验收看负责目录。

<a id="s25"></a>

### S25：验收崩溃恢复、观测降级并完成清理

- [ ] 完成 [S25](../LANDMARKS.md#s25) 的本范围任务。

**先决条件**：根队列中本步之前的验收门已通过；新增/缺陷测试先写，再改实现。

**做什么**：清理未使用 RedisStateStore 占位与相关测试/导出，校正旧 NEXT_STEP、版本和能力说明；不要删除 StateStore 协议。

**交付物**：交付一致的 index/verify 文档与无失效占位入口。

**验收**：模块回归、导入和导航检查通过。

## 完成一项怎么记

在相关 DEFECTS 条目附测试名称/命令、实际结果与版本；只勾本步验收通过的项目。涉及代码的目录同步 README。L3 草稿放本地 DESIGN_NOTES；跨模块有后果的决定落 docs/adr。文档修订完成不等于业务修复完成。
