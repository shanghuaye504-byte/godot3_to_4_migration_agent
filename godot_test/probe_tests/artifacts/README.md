# artifacts

运行产物根目录。布局：

```text
artifacts/<run-id>/<N>/<group_id>/<step-id>/<cache_state>/<repeat_idx>/
artifacts/<run-id>/<N>/<group_id>/cleanup.json
artifacts/<run-id>/index.md
artifacts/latest/<N>.json
```

`latest/<N>.json` 是跨 run 的成功指针（含 `inputs_digest`）。仅真实实验全部 group OK 后写入；`--fake` 不写。STALE 时默认拒绝，`--force-stale` 才覆盖。

本目录只存放 kernel 原始测量（stdout/stderr/argv/process/fs/diff/metadata）。判定与中间结果写在 `report/<phase>/<N>/`，人写结论在 `reports/README.md`。不得写入 fixtures/。

当前环境预检：`env-preflight-20260821-180807/`（见该目录 `index.md`）。旧预检 `env-preflight-20260821-105347/` 保留为历史，不必删除。N09 真跑见 `n09-20260821/`；指针 `latest/N09.json`。
