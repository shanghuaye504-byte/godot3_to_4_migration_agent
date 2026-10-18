# 受控编辑与守卫：问题与复现

[全项目执行顺序](../../LANDMARKS.md) · [全项目问题总账](../../DEFECTS.md) · [上级文档](../DEFECTS.md) · [本级路标](../editandfixguard/LANDMARKS.md)

按执行顺序排列。**已复现/源码确认**指已有代码证据；**规划风险**指组件尚未实现，复现描述是先要写下的失败测试。所有代码修复仍未完成，不能把新文档当作修复结果。

## 本级负责的问题

复现均在临时项目/数据库执行；需要 Git 时先提交干净来源，注入成功 sync；需要引擎的条目先完成 S00。源码链接用于定位，精确函数名写在正文，避免依赖易漂移行号。

<a id="edt-01"></a>

### EDT-01：包入口没有导出约定的 edit API

**顺序 / 状态**：[S06](../../LANDMARKS.md)；源码确认；代码待修。

**范围与原因**：实现位于 edit.py，但包 __init__.py 仍是占位。上层按公开包导入时无法得到约定的函数。

**具体表现**：from inline_tools.editandfixguard import edit 可能得到子模块，直接调用会报 module 不可调用。

**如何复现**：在干净 Python 进程执行上述 import，检查 callable(edit)；与直接导入 edit.py 中的 edit 函数对照。

**修复办法**：公开导出 edit、Hunk 和需要的稳定结果类型；写明唯一推荐 import，避免函数与同名模块混淆。

- [ ] **验收测试**：增加公开入口导入与 callable 断言；原子模块测试继续运行。

**关键源码**：[__init__.py](__init__.py)、[edit.py](edit.py)。

<a id="edt-02"></a>

### EDT-02：函数改名后场景仍用旧名，编辑流水线没有提醒

**顺序 / 状态**：[S06](../../LANDMARKS.md)；源码确认；代码待修。

**范围与原因**：check_rename_consistency 已实现，却没有接入 edit；传入的 db_path 也未使用。单个 .gd 能提交，场景连接留着旧回调。

**具体表现**：把 on_hit 改为 on_damage，场景 connection.method 仍为 on_hit，编辑结果没有 INCONSISTENT_RENAME。

**如何复现**：临时 Git 项目含脚本与该连接；用声明 scope 的 Hunk 改函数名，注入成功 sync，检查返回 guard.violations。

**修复办法**：两边 AST 无错误时检测 class/func/signal 的删除与新增并触发旧名引用检查；多改名不得用 next(iter(...)) 任意配对。只需警告时可以传旧名集合，纯删除走删除守卫。

- [ ] **验收测试**：覆盖单改名、多改名、纯删除、坏 AST 与 signal；断言 warning 不阻止合法提交。

**关键源码**：[edit.py](edit.py)、[scene_names.py](scene_names.py)、[symbols.py](symbols.py)。

<a id="edt-03"></a>

### EDT-03：索引文件存在就关闭 grep 回退，导致漏报

**顺序 / 状态**：[S06](../../LANDMARKS.md)；已复现；代码待修。

**范围与原因**：改名检查把“数据库文件存在”当作“全部名字已覆盖”。空库、查询失败或过期库会让旧回调从检查中消失。

**具体表现**：不用索引能 grep 到 old_callback；传一个已经建表但没有场景数据的索引后，警告变成 0 条。

**如何复现**：临时场景写 connection.method="old_callback"；分别不传 db_path 和传空索引调用 check_rename_consistency，比较 violations。

**修复办法**：查询返回成功与覆盖状态，不只返回 hits；对未覆盖、查询失败或过期范围回退 grep，并对结果去重。

- [ ] **验收测试**：测试无库、空库、坏 schema、完整索引、过期索引和结果去重。

**关键源码**：[scene_names.py](scene_names.py)。

<a id="edt-04"></a>

### EDT-04：写后复核把存量场景错误当作新回归

**顺序 / 状态**：[S07](../../LANDMARKS.md)；已复现；代码待修。

**范围与原因**：写前比较 post-pre 差集，写后却只要看到任何问题就回滚。两个阶段使用了不同准则。

**具体表现**：只改 format=2 场景的一项无关合法属性，存量 E_NOT_CONVERTED 仍在，写后返回 SCENE_REGRESSION。

**如何复现**：用 format=2 场景比较 check_scene_invariants(old, new)，再将 new 写到临时磁盘，调用 _verify_on_disk；观察写前允许、写后拒绝。

**修复办法**：写后仍先确认磁盘字节等于候选文本，再以原始 old_text 比较新增问题；不能把原有问题清零作为每个局部补丁的前提。

- [ ] **验收测试**：端到端测试存量问题保留可提交、新增错误被拒且文件/HEAD 恢复、真正修复存量错误可提交。

**关键源码**：[edit.py](edit.py)、[scene_names.py](scene_names.py)。

<a id="edt-05"></a>

### EDT-05：create 绕过语法和反向迁移检查

**顺序 / 状态**：[S07](../../LANDMARKS.md)；已复现；代码待修。

**范围与原因**：edit.py 的 .gd 守卫条件排除了 create；写后又只比较磁盘文本与同一候选文本的错误数，无法发现候选本来就坏。

**具体表现**：create 内容为 func broken(:，当前 ok=True 并产生 commit，实际上有一个语法错误节点。

**如何复现**：初始化干净临时 Git 仓库，调用 edit(file="bad.gd", kind="create", content="func broken(:\n", sync_fn=成功桩)，再统计错误节点和 HEAD。

**修复办法**：create 显式检查新文件语法、适用的 G5.1 与新增文本风险；check_symbols 的空旧文本分支本身不负责语法，不能只接该函数。

- [ ] **验收测试**：坏语法不得写入或提交；合法新文件可提交；空文件与无结尾换行的行为也要明确。

**关键源码**：[edit.py](edit.py)、[symbols.py](symbols.py)。

<a id="edt-06"></a>

### EDT-06：非脚本文件缺通用守卫，场景删除也未覆盖

**顺序 / 状态**：[S08](../../LANDMARKS.md)；源码确认；代码待修。

**范围与原因**：完整文本守卫只在 .gd patch 路径。场景仅检查结构；shader、project.godot、cfg 没有相同的删除和偷懒检查。

**具体表现**：删除场景的 connection 行仍是合法场景；删除 shader 的关键逻辑也不一定产生文本语法错误。

**如何复现**：对临时 .tscn 删除一个 connection，对 .gdshader 删除大段逻辑；用相同删改规模分别调用 edit，并与 .gd 的 guard 路径对照。

**修复办法**：按能力组合通用文本守卫与各后缀专用检查；场景同样需要删除风险提示。合法迁移允许有依据的 scope/rule 豁免，不把所有删除一律拒绝。

- [ ] **验收测试**：每个白名单后缀各有允许与拒绝/警告样本；信号连接删除必须可被风险检查或后续 Judge 发现。

**关键源码**：[edit.py](edit.py)、[guard.py](guard.py)、[precheck.py](precheck.py)。

<a id="edt-07"></a>

### EDT-07：G5.1 只看声明名字，既漏旧 API 又误杀用户函数

**顺序 / 状态**：[S08](../../LANDMARKS.md)；已复现；代码待修。

**范围与原因**：当前取声明集合差，再与所有 owner 的 old_symbol 混比。它既看不到调用点，也无法证明同名用户声明属于旧引擎 API。

**具体表现**：extends KinematicBody2D 或 .instance() 没被拦；自定义 func get_name() 却被当作另一类型的旧方法拒绝。

**如何复现**：绕开 edit 直接调用 check_symbols(file, "", new_text, rules_db_path=真实库)，分别传上述三类代码并比较 violations。

**修复办法**：声明删除检查保留；旧 API 使用检查另取 AST 类型/调用证据并确认 owner、版本、动作。归属未知时给风险提示，不凭裸名字硬拒；与 codemod 共用保守适用判断。

- [ ] **验收测试**：成对测试真正旧 API 与同名用户函数/变量；已有旧问题不因无关编辑被重新拒绝。

**关键源码**：[symbols.py](symbols.py)、[rules_db.py](rules_db.py)。

<a id="edt-08"></a>

### EDT-08：git apply 临时补丁文件未清理

**顺序 / 状态**：[S08](../../LANDMARKS.md)；源码确认；代码待修。

**范围与原因**：apply_check/apply_index 创建 delete=False 的临时文件，正常和异常路径均无 unlink。批处理时会积累磁盘垃圾。

**具体表现**：连续提交 100 个补丁，临时目录可能多出约 200 个 .patch 文件。

**如何复现**：测试中把 NamedTemporaryFile 定位到专用临时目录，调用 apply_check 和 apply_index，比较调用前后的 .patch 文件集合；再注入 git 异常。

**修复办法**：将 subprocess 调用包在 try/finally，finally 删除补丁文件；保留原始成功/失败结果，不因清理覆盖诊断。

- [ ] **验收测试**：成功、失败、超时三条路径都不留临时文件。

**关键源码**：[git_txn.py](git_txn.py)。

<a id="edt-09"></a>

### EDT-09：同步没有绑定当前项目，整轮回滚又只刷新一个文件

**顺序 / 状态**：[S11](../../LANDMARKS.md)；源码确认；整合待修。

**范围与原因**：sync_file 虽接收 root，实际 codeindex 子进程仍加载全局配置；revert 能 reset 多个文件，却只调用一个 file 的 sync。

**具体表现**：编辑输出工作区 B，却让 CLI 按配置中的项目 A 写索引；回滚 a/b 后只刷新 a，b 的旧符号还留在库里。

**如何复现**：桩替换 subprocess.run，检查 sync_file 的 argv/env 没有项目绑定；在临时 Git 中提交两个文件后 reset，记录 sync_fn 收到的路径集合。

**修复办法**：宿主注入绑定本 run Config 的 sync_fn/索引适配器。整组回滚计算前后 changed paths，刷新全部；index_stale 时禁止依赖旧索引继续决策。

- [ ] **验收测试**：两个项目同时存在时修改 B 只影响 B；多文件回滚后的库与源码一致；同步失败可报告并重建，不偷偷成功。

**关键源码**：[sync_index.py](sync_index.py)、[edit.py](edit.py)、[cli.py](../../codebase_index/index/src/codeindex/cli.py)。
