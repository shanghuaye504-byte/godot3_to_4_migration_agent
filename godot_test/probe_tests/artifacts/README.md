# artifacts

原始测量根目录（唯一真相源）。布局见 ARCHITECTURE.md §6：

```text
artifacts/<run-id>/<N>/<group_id>/<step-id>/<cache_state>/<repeat_idx>/
    metadata.json argv.json stdout.log stderr.log process-status.json
    fs-before.json fs-after.json workspace.diff cache-manifest.json
artifacts/<run-id>/<N>/<group_id>/cleanup.json
artifacts/<run-id>/<N>/index.md          证据索引，不是判定
artifacts/latest/<N>.json                该实验导出给下游的结论输入
```

路径必须含 `group_id`、`cache_state`、`repeat_idx`，否则重复运行会互相覆盖。

`latest/<N>.json` 含 `inputs_digest`。上游 JSON 缺失则下游 BLOCKED；digest 已变（STALE）默认拒绝，须显式 `--force-stale` 才覆盖，并把该标记写进 `metadata.json`。假 Godot 干跑不写 `latest/`（`usable_for_confirmed=false`），以免污染下游。

本目录只存放采集侧原始测量。判定文件（`signatures.json`、`evaluation.json`）不进 artifacts，写在 `reports/<run-id>/<N>/<analyzer-name>/`。人写结论在 `reports/README.md`。不得写入 fixtures/。

干跑时用 `PROBE_GODOT` 指向任意可执行文件（util 自测：`experiments/util/testing/fake_godot.py`）；假二进制产物不得被任何「已确认」结论引用。
