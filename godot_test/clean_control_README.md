# CleanControl 测试脚本说明

本目录用于在 **CleanControl**（Godot 4.7.1 最小对照项目）上，批量执行 `working_notebook/day1/reports/CLI.md` 中定义的 headless 指令集，并记录 stdout、stderr、退出码与耗时，供 verifier 噪声分析使用。

## 目录结构

```
godot_test/
├── clean_control/                 # CleanControl 测试项目（project.godot + main.tscn + 3 个脚本）
├── clean_control_test_script.py   # 本 README 对应的测试脚本
├── clean_control_log/             # 运行后自动生成：各指令号的日志与汇总
└── clean_control_README.md        # 本文件
```

## 前置条件

1. **Godot 4.7.1** 已安装，且可在终端调用（本机常见为 `godot4`）。
2. **Python 3**（脚本仅用标准库，无需额外依赖）。
3. 在**普通终端**中运行（非受限沙盒环境）。Godot 启动时会写入 `user://logs/`（对应系统用户目录），若环境禁止写入该路径，可能导致引擎异常退出。
4. `godot4` 并非官方可执行文件的固定名称，而是本机为 Godot 4 引擎二进制注册的**别名**（alias）；如果你的环境中该别名不存在或指向其他版本，请改用实际可执行文件路径，或通过下文的 `GODOT_BIN` 环境变量指定。

验证 Godot 版本：

```bash
godot4 --version
# 期望：4.7.1.stable.official...
```

若 `godot4` 不在 PATH 中，可通过环境变量指定：

```bash
export GODOT_BIN="/path/to/godot4"
```



## 脚本作用

`clean_control_test_script.py` 针对 **单个指令号**（如 `V1`、`V7S`、`A3`）在 `clean_control/` 项目上执行重复测试：


| 行为      | 说明                                                     |
| ------- | ------------------------------------------------------ |
| 重复次数    | 每个指令重复 **3 次**                                         |
| 冷 / 热缓存 | 每轮先删 `.godot/` 跑 **cold**，再保留缓存跑 **hot** → 共 **6 次**运行 |
| 超时      | 单次运行 **15 秒**；超时则 **kill 整个进程组**（`SIGKILL`）            |
| 进程组     | 每次运行使用独立 session（`start_new_session=True`），便于超时后清理子进程  |
| 落盘      | 分别保存 stdout、stderr、exit code、耗时；并生成 JSON 汇总与 TSV 速览    |


指令格式与验证目标见：`working_notebook/day1/reports/CLI.md`。

## 基本用法

进入 `godot_test` 目录后，传入一个指令号：

```bash
cd "/Users/yy_catmax/workspace/Godot Workspace/godot3_to_4_migration_agent/godot_test"

python3 clean_control_test_script.py V1
```

指令号**不区分大小写**（`v1`、`V7S`、`a3` 均可）。

### `--path`（项目目录）与 `--script`（脚本资源路径）的来源

脚本对这两者分别处理，且都可以覆盖：


| 参数   | 传给 Godot 的哪个 flag                      | 默认值                                                                                                                   | 路径类型                                                                         | 覆盖方式                                                                       |
| ---- | -------------------------------------- | --------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------- | -------------------------------------------------------------------------- |
| 项目目录 | `--path`（所有指令共用）                       | `clean_control_test_script.py` **所在目录**下的 `clean_control/`，由 `Path(__file__).resolve().parent / "clean_control"` 计算得到 | **文件系统绝对路径**，与运行脚本时的当前工作目录（cwd）无关                                            | `--project-dir <路径>`（支持绝对路径，或相对当前 cwd 的相对路径，脚本会自动 `resolve()` 成绝对路径）       |
| 脚本目标 | `--script`（仅 `V2`/`V7S`/`V8S` 使用） | `res://main.gd` | **Godot 资源路径**（`res://...`），按 `--path`/`--project-dir` 指向的项目根解析，**不是**文件系统路径 | `--script <res路径或裸文件名>`（如 `res://other.gd`、`other.gd`，脚本会自动补全 `res://` 前缀） |


示例：

```bash
# 用 V2 检查 clean_control 项目里的另一个脚本
python3 clean_control_test_script.py V2 --script res://other.gd

# 针对另一个 Godot 项目跑 V1（--project-dir 传绝对或相对路径均可）
python3 clean_control_test_script.py V1 --project-dir /path/to/other_project
python3 clean_control_test_script.py V1 --project-dir ../other_project
```

若不传 `--project-dir`/`--script`，则始终使用上表的默认值（即固定跑在 `clean_control/` 项目的 `res://main.gd` 上）。

#### 方式二：直接改脚本里的默认值（不想每次都敲命令行参数时用）

`--project-dir`/`--script` 命令行参数只是**临时覆盖**，每次运行都要重新传。如果你想**永久改变默认的项目路径 / 脚本目标**（例如以后长期测试另一个项目），可以直接编辑 `clean_control_test_script.py` 里对应的常量：


| 要改的默认值               | 变量名                   | 所在行号       | 示例                                                                                                                              |
| -------------------- | --------------------- | ---------- | ------------------------------------------------------------------------------------------------------------------------------- |
| 默认项目目录（`--path`）     | `DEFAULT_PROJECT_DIR` | 第 **41** 行 | `DEFAULT_PROJECT_DIR = SCRIPT_DIR / "clean_control"` → 改成 `Path("/abs/path/to/other_project")` 或 `SCRIPT_DIR / "other_project"` |
| 默认脚本资源路径（`--script`） | `DEFAULT_SCRIPT_GD`   | 第 **47** 行 | `DEFAULT_SCRIPT_GD = "res://main.gd"` → 改成 `"res://other.gd"`                                                                   |


此外脚本顶部还有两个常量，如需调整重复测试的行为也可以直接改：


| 要改的行为     | 变量名           | 所在行号       | 说明                                           |
| --------- | ------------- | ---------- | -------------------------------------------- |
| 每个指令的重复次数 | `REPEAT`      | 第 **49** 行 | 默认 `3`（配合 cold/hot 共 6 次运行）                  |
| 单次运行超时秒数  | `TIMEOUT_SEC` | 第 **50** 行 | 默认 `15`；`V8`/`V8S`（`--debug`，预期挂死）等指令频繁超时可调大 |


> 注意：直接改源码属于全局默认值改动，会影响之后所有不传 `--project-dir`/`--script` 的调用；只是临时测一次，优先用命令行参数（方式一），避免忘记改回来。



### 支持的指令号

各指令号严格对照 `CLI.md` 指令集表实现，其中 `V7`/`V8` 在 `CLI.md` 中写作
「V1/V2 + `--verbose`」「V1/V2 + `--debug`」，本脚本拆成不带后缀（基于 V1，
项目级 check）与带 `S` 后缀（基于 V2，单文件级 check）两个变体：


| 指令号   | 命令                                                                | 简要说明                                                                     |
| ----- | ----------------------------------------------------------------- | ------------------------------------------------------------------------ |
| `V1`  | `--headless --path $P --check-only --quit`                        | 项目级 check                                                                |
| `V2`  | `--headless --path $P --script res://main.gd --check-only --quit` | 单文件 check                                                                |
| `V3`  | `--headless --path $P --editor --import --quit`                   | editor 模式下 import                                                        |
| `V4`  | `--headless --path $P --import --quit`                            | 不带 `--editor` 的 import                                                   |
| `V5`  | `--headless --path $P --quit`                                     | 纯启动项目（触发 autoload 注册）                                                    |
| `V6`  | `--headless --path $P --quit-after 2`                             | 更强的防挂死启动                                                                 |
| `V7`  | V1 + `--verbose`                                                  | 项目级 check + verbose                                                      |
| `V7S` | V2 + `--verbose`                                                  | 单文件 check + verbose                                                      |
| `V8`  | V1 + `--debug`                                                    | 项目级 check + debug（**预期挂死**，需 timeout）                                    |
| `V8S` | V2 + `--debug`                                                    | 单文件 check + debug（**预期挂死**，需 timeout）                                    |
| `A3`  | `--headless --editor --recovery-mode --path $P --import --quit`   | recovery-mode 对照（按 CLI.md 定义仅用于 addon 类项目，此处默认仍跑在 `clean_control` 上作为基线） |

> 已从脚本中移除与 V 系列重复的指令：`A1`（≈`V4`）、`A2`（≈`V3`）、`B1`（≈`V2`）、`B2`（≈`V1`）、`C`（≈`V6`）。`CLI.md` 中仍保留其定义供查阅，但本测试脚本不再实现。




## 命令行执行示例



### 单条指令

```bash
python3 clean_control_test_script.py V1
python3 clean_control_test_script.py V2
python3 clean_control_test_script.py A3
```



### 指定 Godot 可执行文件

```bash
GODOT_BIN=/usr/local/bin/godot4 python3 clean_control_test_script.py V1
```



### 批量跑全部指令集

```bash
for cmd in V1 V2 V3 V4 V5 V6 V7 V7S V8 V8S A3; do
  python3 clean_control_test_script.py "$cmd"
done
```



### 查看帮助

```bash
python3 clean_control_test_script.py -h
```



## 输出说明

运行后在 `godot_test/clean_control_log/` 下生成：

```
clean_control_log/
├── _matrix.tsv                          # 所有指令累积速览（追加写入）
└── <指令号>/                            # 例如 V1/
    ├── <指令号>_iter1_cold.stdout.log
    ├── <指令号>_iter1_cold.stderr.log
    ├── <指令号>_iter1_hot.stdout.log
    ├── <指令号>_iter1_hot.stderr.log
    ├── ...                              # iter2、iter3 同理
    └── <指令号>_summary.json            # 该指令 6 次运行的完整 JSON 汇总
```



### `_matrix.tsv` 行格式

每跑完一次会向终端打印并追加一行，例如：

```
V1_iter1_cold	rc=0	wall=0.182s	timed_out=False
```

字段：`tag`（运行标签）、`rc`（退出码）、`wall`（墙钟耗时）、`timed_out`（是否超时）。

### `<指令号>_summary.json`

包含：`instruction`、`godot_bin`、`project_dir`、`script_gd`（本次实际使用的 `--script` 资源路径，即使指令号不使用 `--script` 也会记录默认值）、`repeat`、`timeout_sec`、`generated_at`，以及每次运行的：

- `cmd`：实际 argv
- `cwd`：工作目录
- `returncode` / `timed_out` / `wall_time_sec`
- `stdout_file` / `stderr_file` 及字节数
- `started_at` / `finished_at`



## 冷 / 热缓存含义

- **cold**：运行前删除 `clean_control/.godot/`，模拟首次打开项目。
- **hot**：紧接 cold 后再跑，复用刚生成的编辑器/导入缓存，模拟二次启动。

同一 iter 内 cold → hot 成对出现，便于对比缓存对输出噪声与耗时的影响。

## 注意事项

1. **测试项目路径默认固定**：不传 `--project-dir` 时脚本始终针对 `godot_test/clean_control/`，不会修改其他目录；传入 `--project-dir` 后会改为对该目录执行 `--path`，但日志仍写在本脚本旁的 `clean_control_log/` 下（按指令号分子目录，不区分项目）。
2. **`--script` 指向**：`V2`/`V7S`/`V8S` 中的 `--script` 默认指向 `res://main.gd`（挂在 `Node2D` 上的场景脚本，非独立 `MainLoop` 工具脚本）。若需验证“正确”的 `--script` 路径，可用 `--script` 指定继承 `SceneTree` 的验证脚本，无需改脚本源码。
3. **`V8`/`V8S`（`--debug`）预期挂死**，依赖 15 秒超时 + `killpg` 强制回收；**`V3`/`V4`/`A3`（`--import`）** 可能耗时较长或产生较多输出，同样受 15 秒超时约束。若频繁 `timed_out=True`，可调整脚本第 **50** 行的 `TIMEOUT_SEC`（见上文"方式二"）。
4. **`A3`（`--recovery-mode`）** 按 `CLI.md` 定义本应仅在包含 addon 的项目上跑，此脚本默认仍指向 `clean_control` 作为基线对照；如需针对真实 addon 项目验证，可用 `--project-dir` 传入该 addon 项目的路径。
5. **日志目录**位于 `godot_test/clean_control_log/`，重复运行同一指令号会**覆盖**该指令号子目录下的日志，但 `_matrix.tsv` 为**追加**模式。



## 与 CLI 报告的关系

- 指令定义与验证目标：`working_notebook/day1/reports/CLI.md`
- Godot 官方参数说明：`working_notebook/day1/logs/00_help.txt`
- 噪声统计与结论：待写入 `working_notebook/day1/reports/cleancontrol_base_noise.md`（跑完各指令后人工或脚本分析 `clean_control_log/`）



## 快速自检

跑一条最快的检查指令（`V1`，仅解析不跑主循环）：

```bash
cd godot_test
python3 clean_control_test_script.py V1
```

期望：6 次运行均 `rc=0`，`timed_out=False`，且 `clean_control_log/V1/` 下生成 12 个 `.log` 文件与 1 个 `V1_summary.json`。