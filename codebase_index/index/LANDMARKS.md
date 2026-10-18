# 符号与依赖索引：实现路标

[全项目执行顺序](../../LANDMARKS.md) · [全项目问题总账](../../DEFECTS.md) · [上级文档](../LANDMARKS.md) · [本级问题](DEFECTS.md)

更新：2026-10-17。以当前代码为现状；下文未勾选项均为待修复/待开发。**按根目录 S00→S25 执行，到本目录时再展开；本级编号不重新从 1 开始。**

## 当前能力与要新增的 API

已有 `find_symbol/call_chain/class_hierarchy/status`，入口在 `db/queries.py`；已有 `scene-check`，没有 `scene-freeze`。不要让宿主调用尚不存在的 find_refs/get_file_outline/get_dependencies。

S03 新增文件依赖查询与 `rank_root_cause_files(conn, error_files)`，结果包含稳定顺序、循环分组和未解析边。先补 parser/存储再排序；路径归一化使用相对项目根的 POSIX 路径，进入 Godot 工具时才转换 `res://`。

默认落地方式：在同一个 index.db 新增脚本专用 `file_dependencies` 表（file_id 外键、kind、target_path、target_class、line、resolution），不把 scene 关系塞进来。ParseResult 增加有默认空列表的 dependencies，writer 随文件重索引原子替换。目标能解析时保存相对路径；类名/动态表达式未解析时保留原始目标和原因。增加索引 schema 版本迁移及重建测试，架构记录在本步追加 ADR。

S05 新增 `run_scene_freeze(conn, project_root, *, rules_db_path, baseline_sha, ...)` 与 CLI。它先读取场景正文并收集 L4 问题，再事务化调用 `freeze_baseline(conn, problems)`；函数签名中的冻结元信息属于本轮新增约定，应与 L0 测试一起固定。

## 写库所有权

宿主批处理默认采用**进程内索引适配器**：每 worker 只持自己的连接，写入复用 `writer.reindex_batch`，不同时启动 daemon 写同一库。CLI/daemon 保留为外部使用模式；若外部模式有 daemon，freeze/sync 也须遵守同一写库串行规则。不要让两个模式无约束混用。

## 验收入口

`uv run --project codebase_index/index pytest codebase_index/index/tests -q`。测试前由 S00 准备兼容的 Tree-sitter 解析器与缓存；依赖加载失败不能解释为“项目没有符号”。

## 下级导航

- [场景检查与基线](src/codeindex/scene/LANDMARKS.md)

## 本目录执行清单

<a id="s02"></a>

### S02：修中文索引与配置路径

- [ ] 完成 [S02](../../LANDMARKS.md#s02) 的本范围任务。

**先决条件**：根队列中本步之前的验收门已通过；新增/缺陷测试先写，再改实现。

**做什么**：先修 GDScript UTF-8 字节切片；路径规则按上级 S02 同步。

**交付物**：交付正确名字、调用边和类型切片。

**验收**：中文注释/字符串/标识符和 attribute-call 全覆盖。

**问题详情与复现**：[IDX-01 · 中文让符号名和调用关系切片错位](DEFECTS.md#idx-01)。

<a id="s03"></a>

### S03：补依赖提取，再做根因排序

- [ ] 完成 [S03](../../LANDMARKS.md#s03) 的本范围任务。

**先决条件**：根队列中本步之前的验收门已通过；新增/缺陷测试先写，再改实现。

**做什么**：提取顶层/函数体 preload 与路径/类名 extends 的文件依赖。新增 rank_root_cause_files，返回排序及无法解析的证据；不查询不存在的 relations 表。

**交付物**：交付依赖查询 API；循环先聚成组，再按被依赖关系排序；同分时使用稳定路径排序。

**验收**：链式、经无报错中间节点、循环、未知目标和中文脚本均有反例；根因优先，未知不伪装已解析。

**问题详情与复现**：[IDX-02 · 现有依赖边不足以排序根因脚本](DEFECTS.md#idx-02)。

<a id="s04"></a>

- [ ] **S04 · 修真实规则库接入和场景增量对比**：[场景检查与基线](src/codeindex/scene/LANDMARKS.md#s04)；先完成根队列的前置步骤，验收看负责目录。

<a id="s05"></a>

### S05：修场景回调归属并接通一次性冻结

- [ ] 完成 [S05](../../LANDMARKS.md#s05) 的本范围任务。

**先决条件**：根队列中本步之前的验收门已通过；新增/缺陷测试先写，再改实现。

**做什么**：先修同名回调跨脚本误报和多引用漏报，再实现 run_scene_freeze/scene-freeze；冻结要保存独立标记及 L0 commit。

**交付物**：交付单事务冻结与重复冻结拒绝。空问题基线也有标记，恢复不重新冻结。

**验收**：根/子节点、跨脚本同名、多个场景；重复与中断冻结不洗掉原有证据。

**问题详情与复现**：[SCN-03 · 同名回调跨脚本误报，并且只报第一个引用](src/codeindex/scene/DEFECTS.md#scn-03)；[SCN-04 · 基线有底层函数，却没有安全的生产冻结入口](src/codeindex/scene/DEFECTS.md#scn-04)。

**具体落点**：[场景检查与基线](src/codeindex/scene/LANDMARKS.md#s05)。

## 完成一项怎么记

在相关 DEFECTS 条目附测试名称/命令、实际结果与版本；只勾本步验收通过的项目。涉及代码的目录同步 README。L3 草稿放本地 DESIGN_NOTES；跨模块有后果的决定落 docs/adr。文档修订完成不等于业务修复完成。
