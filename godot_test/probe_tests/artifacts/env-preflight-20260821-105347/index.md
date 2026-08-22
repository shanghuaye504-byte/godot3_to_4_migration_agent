# env-preflight-20260821-105347

环境预检，不是 N01–N21 实验 run。未改动任何 fixture。

**已被 `env-preflight-20260821-180807` 取代。** 本目录保留为历史：当时 `process.py` 仍为骨架，故进程组终止记为 `BLOCKED`。

| 文件 | 内容 |
|---|---|
| `godot-identity.txt` | `--version`、realpath、fat binary 架构、宿主 arch |
| `godot-quarantine.txt` | xattr `com.apple.quarantine`、`spctl` Gatekeeper |
| `godot-smoke.txt` | 在 `workspaces/` 副本上跑 `--headless --path --quit`（exit 0，打印 `CLEAN_OK`） |
| `godot-smoke.stdout.log` / `godot-smoke.stderr.log` | 冒烟原始日志 |
| `fixture-godot-scan.txt` | `find fixtures -type d -name .godot`（0 个） |
| `fixture-godot-scan-after.txt` | 冒烟后复扫（空） |
| `fixture-git-status.txt` | fixture 的 `git status` / `git diff` / `git ls-files` |
| `artifacts-location.txt` | artifacts 与 fixtures 为兄弟目录 |
| `process-group-kill.txt` | 宿主 `start_new_session` + `os.killpg(SIGKILL)` |
| `runner-process-source.txt` | `runner/kernel/process.py` 仍为骨架 |

临时工作区已删除：`workspaces/env-preflight-20260821-105347-CleanControl`
