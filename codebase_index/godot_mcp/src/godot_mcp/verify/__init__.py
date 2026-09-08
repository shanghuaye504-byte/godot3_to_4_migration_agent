"""verify 子包：headless 校验子进程（一次性 spawn → 收输出 → 退出）。

权限边界：commands.py 是唯一定义"能跑哪些 Godot 命令"的地方（白名单 key 是
V1 / V2 / V3）；runner.py 只负责执行，V1 时由 sentinel.py 写入/删除哨兵。
"""
