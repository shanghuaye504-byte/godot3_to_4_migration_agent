"""``rag`` — Godot 3→4 迁移 Agent 的 A/B 层知识库包。

包的边界见 rag/README.md：这个 ``__init__.py`` 本身故意留空，
不要在这里 import 子模块，`rag.retriever` / `rag.version_codec`
各自独立 import 即可，避免引入不必要的启动期依赖。
"""
