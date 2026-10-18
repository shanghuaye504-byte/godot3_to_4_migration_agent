# 符号与依赖索引：问题与复现

[全项目执行顺序](../../LANDMARKS.md) · [全项目问题总账](../../DEFECTS.md) · [上级文档](../DEFECTS.md) · [本级路标](LANDMARKS.md)

按执行顺序排列。**已复现/源码确认**指已有代码证据；**规划风险**指组件尚未实现，复现描述是先要写下的失败测试。所有代码修复仍未完成，不能把新文档当作修复结果。

## 下级导航

- [场景检查与基线](src/codeindex/scene/DEFECTS.md)

## 本范围问题索引

- [ ] S04 · [SCN-01 · 真实规则库查错表，旧类型检查被静默跳过](src/codeindex/scene/DEFECTS.md#scn-01)
- [ ] S04 · [SCN-02 · 只检查一个场景，却宣布其他场景已修复](src/codeindex/scene/DEFECTS.md#scn-02)
- [ ] S05 · [SCN-03 · 同名回调跨脚本误报，并且只报第一个引用](src/codeindex/scene/DEFECTS.md#scn-03)
- [ ] S05 · [SCN-04 · 基线有底层函数，却没有安全的生产冻结入口](src/codeindex/scene/DEFECTS.md#scn-04)

## 本级负责的问题

复现均在临时项目/数据库执行；需要 Git 时先提交干净来源，注入成功 sync；需要引擎的条目先完成 S00。源码链接用于定位，精确函数名写在正文，避免依赖易漂移行号。

<a id="idx-01"></a>

### IDX-01：中文让符号名和调用关系切片错位

**顺序 / 状态**：[S02](../../LANDMARKS.md#s02)；已复现；代码待修。

**范围与原因**：Tree-sitter 给 UTF-8 字节偏移，GdscriptParser 却用它切 Python 字符串。中文出现在节点前面后，后续名字都会错位。影响索引、守卫和根因排序。

**具体表现**：输入“# 中文”后接 class_name Player，实际索引名变为 er\next；func move 的名字也被切坏。

**如何复现**：调用 GdscriptParser().parse("a.gd", "# 中文\nclass_name Player\nextends Node\nfunc move():\n\tprint(1)\n")，打印 symbols 和 class_decl。应得到 Player/move/Node，当前得到错位文本。

**修复办法**：所有 Tree-sitter span 都在 source.encode("utf-8") 上切片后 decode；同步排查 attribute-call 的直接切片。不要把场景 lexer 的字符坐标混为同一种坐标。

- [ ] **验收测试**：先补中文注释、字符串、标识符和 attribute-call 四个反例，再修 parser；断言名字、源码切片与边目标。

**关键源码**：[gdscript.py](src/codeindex/parsers/gdscript.py)。

<a id="idx-02"></a>

### IDX-02：现有依赖边不足以排序根因脚本

**顺序 / 状态**：[S03](../../LANDMARKS.md#s03)；已复现；能力待补。

**范围与原因**：根因排序需要 A.gd 依赖 B.gd 的文件边。当前顶层 preload 未提取，函数内 preload 只记录函数名，路径 extends 也可能丢失。

**具体表现**：const Dep = preload("res://dep.gd") 没有边；函数内同样调用得到 to_name="preload"，无法知道目标文件。

**如何复现**：解析包含路径 extends、顶层 preload 和函数体 preload 的脚本，打印 ParseResult；确认顶层目标缺失、函数内目标只剩 preload。再查询真实 schema，确认没有 relations 表。

**修复办法**：新增文件依赖提取，保留源路径、目标资源路径/类名、边种类和位置；复用 edges/classes 时需版本化 schema，不能直接依赖不存在的 relations。循环图先折叠强连通分量再排序。

- [ ] **验收测试**：测试顶层/函数内 preload、class_name/路径 extends、经无报错中间节点的传递依赖、循环及未解析目标；未知目标需显式标记。

**关键源码**：[gdscript.py](src/codeindex/parsers/gdscript.py)、[schema.sql](src/codeindex/db/schema.sql)、[queries.py](src/codeindex/db/queries.py)。
