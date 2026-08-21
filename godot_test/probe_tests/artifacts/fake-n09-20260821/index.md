# fake-n09-20260821

证据索引。路径含 group / cache_state / repeat，避免互相覆盖。

> 本 run 使用 Fake Godot，**不得**作为已确认结论引用。

Run ID: `fake-n09-20260821`

## 摘要

```json
{
  "exp_id": "N09",
  "fake": true,
  "groups": [
    {
      "group_id": "clean-control",
      "status": "OK",
      "inputs_digest": "f3ab6df26c23253d9e2f53d48e21a9bd14898346"
    },
    {
      "group_id": "np-cascade",
      "status": "OK",
      "inputs_digest": "0d6703f69069df908d108079bb3f9a58b0cae87c"
    }
  ]
}
```

## N09

- 实验级 `evaluation.json`: `N09/evaluation.json`
- 实验级 `groups.json`: `N09/groups.json`

| Group | Step | Cache | Repeat | stdout | stderr | metadata | 目录 |
|---|---|---|---|---|---|---|---|
| clean-control | v1-cold | COLD | 0 | `stdout.log` | `stderr.log` | `metadata.json` | `N09/clean-control/v1-cold/COLD/0` |
| clean-control | v2-cold | COLD | 0 | `stdout.log` | `stderr.log` | `metadata.json` | `N09/clean-control/v2-cold/COLD/0` |
| clean-control | v3-cold | COLD | 0 | `stdout.log` | `stderr.log` | `metadata.json` | `N09/clean-control/v3-cold/COLD/0` |
| clean-control | v4-warm | WARM | 0 | `stdout.log` | `stderr.log` | `metadata.json` | `N09/clean-control/v4-warm/WARM/0` |
| clean-control | v5-warm | WARM | 0 | `stdout.log` | `stderr.log` | `metadata.json` | `N09/clean-control/v5-warm/WARM/0` |
| clean-control | v6-warm | WARM | 0 | `stdout.log` | `stderr.log` | `metadata.json` | `N09/clean-control/v6-warm/WARM/0` |
| clean-control | v7-warm | WARM | 0 | `stdout.log` | `stderr.log` | `metadata.json` | `N09/clean-control/v7-warm/WARM/0` |
| np-cascade | v2-warm | WARM | 0 | `stdout.log` | `stderr.log` | `metadata.json` | `N09/np-cascade/v2-warm/WARM/0` |
| np-cascade | v3-cold | COLD | 0 | `stdout.log` | `stderr.log` | `metadata.json` | `N09/np-cascade/v3-cold/COLD/0` |
| np-cascade | v3-warm | WARM | 0 | `stdout.log` | `stderr.log` | `metadata.json` | `N09/np-cascade/v3-warm/WARM/0` |
| np-cascade | v9-warm | WARM | 0 | `stdout.log` | `stderr.log` | `metadata.json` | `N09/np-cascade/v9-warm/WARM/0` |

### Cleanup

- `N09/clean-control/cleanup.json`
- `N09/np-cascade/cleanup.json`
