# artifacts

运行产物根目录。布局：

```text
artifacts/<run-id>/<N>/<group_id>/<step-id>/<cache_state>/<repeat_idx>/
artifacts/<run-id>/<N>/<group_id>/cleanup.json
artifacts/<run-id>/index.md
artifacts/latest/<N>.json
```

`latest/<N>.json` 是跨 run 的成功指针（含 `inputs_digest`）。仅真实实验全部 group OK 后写入；`--fake` 不写。STALE 时默认拒绝，`--force-stale` 才覆盖。

本目录只存放实验结果，不得写入 fixtures/。

当前已有环境预检 run：`env-preflight-20260821-105347/`（见该目录 `index.md`）。N01–N21 实验产物尚未生成。
