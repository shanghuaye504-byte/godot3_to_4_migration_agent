"""L2：单文件语义。

尚未实现。验收见 codebase_index/NEXT_STEP.md 的 Step 2。

以后负责：
- 由 SceneDoc 得到节点全路径、根列表、外部资源编号表、连接和引用边。
- 标出 instance / instance_placeholder / 继承场景上看不全的子树。
- 引用边带上原文 span。这一层不说对错。
- 不 import os、pathlib、sqlite3，不读磁盘。
"""
