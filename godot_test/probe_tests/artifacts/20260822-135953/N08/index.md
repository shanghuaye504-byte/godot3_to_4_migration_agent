# N08 artifacts

证据索引，不是判定。

- run-id: `20260822-135953`
- inputs_digest: `9dbcb580aa021423bd8a6607bb260c93c54ee6390ad9f2827ec429270cac4b8c`
- Godot: `/usr/local/bin/godot4`
- version: `4.7.1.stable.official.a13da4feb`
- build hash: `a13da4feb`
- fake: `false`
- platform: `Darwin 25.3.0 / arm64`
- force_stale: `false`

## measurements

| group | step | cache | repeat | cmd | rc | timeout | wall_s |
| --- | --- | --- | --- | --- | --- | --- | --- |
| clean-control | v1 | WARM | 1 | V1 | 0 | False | 0.187445 |
| clean-control | v1 | WARM | 2 | V1 | 0 | False | 0.179336 |
| clean-control | v1 | WARM | 3 | V1 | 0 | False | 0.182356 |
| np-syntax | v2 | WARM | 1 | V2 | 0 | False | 0.189806 |
| np-syntax | v2 | WARM | 2 | V2 | 0 | False | 0.183909 |
| np-syntax | v2 | WARM | 3 | V2 | 0 | False | 0.188952 |
| np-syntax | v1 | WARM | 1 | V1 | 0 | False | 0.180702 |
| np-syntax | v1 | WARM | 2 | V1 | 0 | False | 0.183506 |
| np-syntax | v1 | WARM | 3 | V1 | 0 | False | 0.181866 |
| np-syntax | v3 | COLD | 1 | V3 | 0 | False | 1.25851 |
| np-syntax | v3 | COLD | 2 | V3 | 0 | False | 1.265664 |
| np-syntax | v3 | COLD | 3 | V3 | 0 | False | 1.250689 |
| np-syntax | v4 | COLD | 1 | V4 | 0 | False | 1.457221 |
| np-syntax | v4 | COLD | 2 | V4 | 0 | False | 1.259811 |
| np-syntax | v4 | COLD | 3 | V4 | 0 | False | 1.257848 |
| np-syntax | v5 | WARM | 1 | V5 | 0 | False | 0.186051 |
| np-syntax | v5 | WARM | 2 | V5 | 0 | False | 0.179157 |
| np-syntax | v5 | WARM | 3 | V5 | 0 | False | 0.175656 |
| np-syntax | v6 | WARM | 1 | V6 | 0 | False | 0.18042 |
| np-syntax | v6 | WARM | 2 | V6 | 0 | False | 0.175479 |
| np-syntax | v6 | WARM | 3 | V6 | 0 | False | 0.180386 |
| np-syntax | v7 | WARM | 1 | V7 | 0 | False | 0.180143 |
| np-syntax | v7 | WARM | 2 | V7 | 0 | False | 0.181825 |
| np-syntax | v7 | WARM | 3 | V7 | 0 | False | 0.184564 |
| np-autoload | v2 | COLD | 1 | V2 | 0 | False | 0.185412 |
| np-autoload | v2 | COLD | 2 | V2 | 0 | False | 0.188435 |
| np-autoload | v2 | COLD | 3 | V2 | 0 | False | 0.184734 |
| np-syntax | v8 | WARM | 1 | V8 | -6 | False | 0.277679 |

## inputs

```json
{
  "fixtures": {
    "phase1/CleanControl": "b6b536f72483d82711282d32bb492e30375e45f85ab4c86aba75565b60d5a957",
    "phase1/NP-SYNTAX": "0f0817ea847ca09889a7abc1d2352ab9df56734bc8a24eb1cfd9ed544ed318d8",
    "phase1/NP-AUTOLOAD": "405f9e2e585ec9bd12e2a990c692f927f88e5343fa930bd5b20e733c444c1a5b",
    "phase1/NP-ADDON": "fcf0347b8b2882f6f7a5df55a2b7b534dc6c7ee6be1d7ba31cf6fd869cd1ee51"
  },
  "annotations": {
    "phase1/CleanControl": "07425f8d5505bf9b3157cd566c14cadf447352cf6f87fa1a2cc3feb0d9851b72",
    "phase1/NP-SYNTAX": "3000a2bbee6c60fa93c7296142a321da93584c06dc7156c530f275124e83f8e2",
    "phase1/NP-AUTOLOAD": "f2dd46fbbe8e19a95b26be51735076ff02117e68e148253dea7652e847a9f166",
    "phase1/NP-ADDON": "a9f48b1f486b2e4548dc04098f640cdef0354d1be05a14564d1c46f4db8dd26d"
  },
  "derived": {},
  "godot_build_hash": "a13da4feb",
  "godot_path": "/usr/local/bin/godot4",
  "godot_fake": false,
  "upstream": {
    "N09": "31919eb4683934a49a4a7fad005697608419731c135b9dea6bf9b055e18df428"
  }
}
```
