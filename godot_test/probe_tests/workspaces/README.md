# workspaces

`probe.workspace` 从 fixtures/ 复制出的临时工作区。实验结束必须销毁，本目录应为空。

退出时校验原 fixture 仍 clean。禁止在原 fixture 上直接跑，也不得把工作区留到脚本结束之后。
