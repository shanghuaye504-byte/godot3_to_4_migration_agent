"""共享落盘工具包（唯一允许被多个实验脚本 import 的东西）。

对外暴露 probe。异构步骤留在各 Nxx.py；同构动作才进本包：
起进程组、超时 killpg、按固定形状落盘、销毁工作区、算摘要。

一次性特例（伪造 UID、改 ext_resource、生成 late class、生成大文件、
config_version 降级）写在用它的那个脚本里，不进本包。
"""

from . import probe

__all__ = ["probe"]
