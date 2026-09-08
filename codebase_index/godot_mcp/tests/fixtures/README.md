# fixtures/ —— 实现阶段要放的样例数据

现在是空的，实现到对应步骤时按需添加，不要提前臆造内容（拿真实 `godot4` 输出样例）：

| 文件（待添加） | 用途 | 对应实现步骤 |
| --- | --- | --- |
| `check_only_clean.txt` | 一次干净通过的 `--check-only` stdout/stderr 样例 | `verify_filter`，`FilterResult.status == CLEAN` 分支 |
| `check_only_autoload_false_positive.txt` | 触发 issue #78587 签名的 stdout 样例（`--check-only` 不加载 autoload 导致的误报） | `rules.py` 已知误报过滤 |
| `check_only_resource_not_imported.txt` | 资源未导入产生的假错误样例 | `rules.py` 噪声过滤 |
| `check_only_real_error.txt` | 一条真实语法/类型错误（非误报）样例 | `rules.py`，确认真错误不会被误滤掉 |
| `sample_ok.gd` / `sample_broken.gd` | 供 `verify/runner.py` 手测 V2 时使用的最小 GDScript 样例 | `runner.py` 手测（参考 `../../index/tests/fixtures/player.gd` 的最小化风格） |

样例文本从真实跑一遍 `godot4 --headless --check-only --script <file>` 的输出里摘取，
不要手写猜测的报错格式——噪声过滤规则是对着真实输出的字符串特征写的，假样例会掩盖真实差异。
