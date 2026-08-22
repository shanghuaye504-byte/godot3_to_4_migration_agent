# env-preflight-20260821-180807

环境预检（取代 `env-preflight-20260821-105347`）。不是 N01–N21 实验 run。未改动任何 fixture。

旧预检保留作历史：当时 `process.py` 仍为骨架，故「进程组终止」记为 `BLOCKED`。本次 `process.py` 已含 `Popen` + `start_new_session` + `killpg`。

| 文件 | 内容 |
|---|---|
| `godot-identity.txt` | `--version`、realpath、fat binary 架构、宿主 arch、sw_vers、Python |
| `godot-quarantine.txt` | xattr `com.apple.quarantine`、`spctl` Gatekeeper |
| `godot-smoke.txt` | 在 `workspaces/` 副本上跑 `--headless --path --quit`（exit 0，打印 `CLEAN_OK`） |
| `godot-smoke.stdout.log` / `godot-smoke.stderr.log` | 冒烟原始日志 |
| `fixture-godot-scan.txt` | `find fixtures -type d -name .godot`（1 个：CleanControl，已入库） |
| `fixture-godot-scan-after.txt` | 冒烟后复扫（仍为 1，来自已跟踪的 fixture，不是冒烟写入） |
| `fixture-git-status.txt` | fixture 已跟踪 99 文件；`git status`/`diff` 空；untracked 0 |
| `artifacts-location.txt` | artifacts 与 fixtures 为兄弟目录 |
| `process-group-kill.txt` | `runner.kernel.process.run` 对 Fake hang 1s timeout：`timed_out` + signal 9，无残留 |
| `runner-process-source.txt` | `process.py` 含 Popen / killpg / start_new_session，无「骨架」注释 |

临时工作区已删除：`workspaces/env-preflight-20260821-180807-CleanControl`
