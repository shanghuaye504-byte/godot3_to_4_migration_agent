# 场景检查与基线：问题与复现

[全项目执行顺序](../../../../../LANDMARKS.md) · [全项目问题总账](../../../../../DEFECTS.md) · [上级文档](../../../DEFECTS.md) · [本级路标](LANDMARKS.md)

按执行顺序排列。**已复现/源码确认**指已有代码证据；**规划风险**指组件尚未实现，复现描述是先要写下的失败测试。所有代码修复仍未完成，不能把新文档当作修复结果。

## 本级负责的问题

复现均在临时项目/数据库执行；需要 Git 时先提交干净来源，注入成功 sync；需要引擎的条目先完成 S00。源码链接用于定位，精确函数名写在正文，避免依赖易漂移行号。

<a id="scn-01"></a>

### SCN-01：真实规则库查错表，旧类型检查被静默跳过

**顺序 / 状态**：[S04](../../../../../LANDMARKS.md#s04)；已复现；代码待修。

**范围与原因**：场景 L4 要查迁移旧类名。真实库表为 migration_rules，loader 查询 rules 后捕获异常，退化为规则不可用。测试只建 rules，掩盖了集成问题。

**具体表现**：场景节点仍是 KinematicBody2D，使用真实 rules.db 检查却没有 E_UNMIGRATED_TYPE，只有 rules_unavailable=True。

**如何复现**：用 check_scene 检查含 type="KinematicBody2D" 的 format=3 场景，rules_db_path 指向仓库 rag/artifacts/rules.db；查看 problems 与 rules_unavailable。

**修复办法**：只读识别 migration_rules；若保留兼容 rules，要检测实际列。旧类型集合须按适用版本和 rename/remove 规则筛选，不能把所有 class 行都当非法类型。

- [ ] **验收测试**：同时用真实库、最小兼容库、缺失库和合法新类型作测试；不可用状态必须出现在覆盖报告。

**关键源码**：[rules.py](rules.py)、[rules.db](../../../../../rag/artifacts/rules.db)、[test_rules.py](../../../tests/scene/test_rules.py)。

<a id="scn-02"></a>

### SCN-02：只检查一个场景，却宣布其他场景已修复

**顺序 / 状态**：[S04](../../../../../LANDMARKS.md#s04)；已复现；代码待修。

**范围与原因**：增量 scene_check 只收集本次闭包的问题，diff_baseline 却对比全库基线；没检查到被误解为不存在。

**具体表现**：a.tscn、b.tscn 都有 format=2；仅检查 a，返回 fixed 中却含仍未修改的 b。

**如何复现**：索引两个坏场景，收集问题并 freeze_baseline；调用 scene_check(conn, root, paths=["a.tscn"])，检查 fixed。

**修复办法**：向 diff_baseline 传入实际已检查场景集合，只在该集合内计算 fixed；成员消失检查也应用同一范围。完整扫描时才允许全库比较。

- [ ] **验收测试**：先复现 a/b 反例，再测空闭包、.gd 反查场景、真实修复、场景删除；路径统一使用库中的相对路径。

**关键源码**：[check.py](check.py)、[baseline.py](baseline.py)。

<a id="scn-03"></a>

### SCN-03：同名回调跨脚本误报，并且只报第一个引用

**顺序 / 状态**：[S05](../../../../../LANDMARKS.md#s05)；已复现；代码待修。

**范围与原因**：E_MEMBER_GONE 只按回调名字查 scene_refs，没有确认连接目标挂载的脚本；SQL 的 LIMIT 1 又截断其他引用。

**具体表现**：enemy.gd 删除 _on_hit，仍被错误地报告为 player.tscn 的问题；该场景实际上只挂 player.gd。

**如何复现**：创建 enemy/player 两脚本，只有 player.tscn 连接 _on_hit；冻结后删除 enemy 中该函数并重索引，调用 member_gone_problems。另建两个引用场景验证漏报。

**修复办法**：由 scene_conn.to_path 归一化目标节点，再经 scene_nodes.script_ext_id 与 scene_ext.resolved_file 判断归属；遍历全部匹配。继承/实例子树无法证明时明确弃权。

- [ ] **验收测试**：覆盖同名不同脚本、多个场景、同场景多个目标、根节点与子节点；修正旧测试中“脚本挂子节点但连接指向根”的错误夹具。

**关键源码**：[baseline.py](baseline.py)、[schema.sql](schema.sql)、[test_baseline.py](../../../tests/scene/test_baseline.py)。

<a id="scn-04"></a>

### SCN-04：基线有底层函数，却没有安全的生产冻结入口

**顺序 / 状态**：[S05](../../../../../LANDMARKS.md#s05)；源码确认；入口待实现。

**范围与原因**：freeze_baseline 能写入旧错误和成员，但 CLI/宿主没有调用入口；函数还会先删旧基线，恢复时误调用会把回归洗成历史问题。

**具体表现**：改坏函数后再次冻结，原来的“新回归”被当作 pre_existing。空问题基线也无法仅凭行数判断是否已冻结。

**如何复现**：查看 CLI 帮助确认没有 scene-freeze；临时库连续两次调用 freeze_baseline，比较 scene_baseline 内容，确认会被覆盖。

**修复办法**：新增 run_scene_freeze 和 scene-freeze CLI；读取场景正文调用现有 check_scene，再在事务内冻结。另存冻结标记、L0 commit 和规则指纹；默认拒绝重复冻结，resume 只校验。

- [ ] **验收测试**：测试首次冻结、零问题冻结、重复拒绝、事务失败不留半基线、resume 不覆写。

**关键源码**：[baseline.py](baseline.py)、[check.py](check.py)、[cli.py](../cli.py)。
