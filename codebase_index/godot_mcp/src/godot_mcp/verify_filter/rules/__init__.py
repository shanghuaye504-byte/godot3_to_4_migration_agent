"""§7.1–§7.8 的具体规则，一条规则一个文件（方案文档 §13："不要揉成一个 800 行 rules.py"）。

执行顺序固定，由 `pipeline.py` 编排，本包内的模块不互相调用、不关心自己在流水线里的
位置——每个模块只认"输入是上一步 `replace()` 过的事件集合，输出是本规则处理完的新
集合"这一件事。

- `protect.py`     §7.1 保护名单（先打标，后续规则碰到 protected 必须 skip）
- `sentinel.py`    R1 哨兵人造边
- `autoload_fp.py` R2 autoload / addon 假阳性（核心规则）
- `cascade.py`     R3 `Failed to compile depended scripts` 症状
- `wrappers.py`    R4 `Failed to load script` 包装行（含窄"升级例外"）
- `uid_cluster.py` R5 UID 重复簇压缩
- `infra.py`       R6 调试器插件噪声
- `warning.py`     R7 warning 与终止条件（补齐：此前的文件布局漏了这一条）
"""

from __future__ import annotations
