"""L5：组装 codeindex scene-check 的返回。

尚未实现。验收见 codebase_index/NEXT_STEP.md 的 Step 5。

以后负责：
- 调用 rules 与 baseline，输出 regression / pre_existing / fixed / coverage。
- 不传路径时全量；传入路径时用 scene_refs.target_file 反查相关场景。
- 不写盘，不拦 edit。有 regression 时仍由 CLI 返回退出码 0。
"""
