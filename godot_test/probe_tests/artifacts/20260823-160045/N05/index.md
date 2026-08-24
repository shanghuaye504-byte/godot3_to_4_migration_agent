# N05 artifacts

证据索引，不是判定。

- run-id: `20260823-160045`
- inputs_digest: `6b36c76c7f2b5d360d4d28542c4c12bef8f2ac6c3464ddef0a8b5be293fc1575`
- Godot: `/usr/local/bin/godot4`
- version: `4.7.1.stable.official.a13da4feb`
- build hash: `a13da4feb`
- fake: `false`
- platform: `Darwin 25.3.0 / arm64`
- force_stale: `false`

## measurements

| group | step | cache | repeat | cmd | rc | timeout | wall_s |
| --- | --- | --- | --- | --- | --- | --- | --- |
| default | s1 | WARM | 1 | V2 | 0 | False | 0.189269 |
| default | s1 | WARM | 2 | V2 | 0 | False | 0.18254 |
| default | s1 | WARM | 3 | V2 | 0 | False | 0.184533 |
| default | s2 | WARM | 1 | V1 | 0 | False | 0.184853 |
| default | s2 | WARM | 2 | V1 | 0 | False | 0.178689 |
| default | s2 | WARM | 3 | V1 | 0 | False | 0.184989 |
| default | s3 | COLD | 1 | V3 | 0 | False | 1.452153 |
| default | s3 | COLD | 2 | V3 | 0 | False | 1.457741 |
| default | s3 | COLD | 3 | V3 | 0 | False | 1.451778 |
| warn-enabled | s5 | WARM | 1 | V2 | 0 | False | 0.186458 |
| warn-enabled | s5 | WARM | 2 | V2 | 0 | False | 0.183379 |
| warn-enabled | s5 | WARM | 3 | V2 | 0 | False | 0.186497 |
| warn-enabled | s6 | WARM | 1 | V1 | 0 | False | 0.184338 |
| warn-enabled | s6 | WARM | 2 | V1 | 0 | False | 0.186411 |
| warn-enabled | s6 | WARM | 3 | V1 | 0 | False | 0.186993 |
| warn-enabled | s7 | COLD | 1 | V3 | 0 | False | 1.250401 |
| warn-enabled | s7 | COLD | 2 | V3 | 0 | False | 1.258807 |
| warn-enabled | s7 | COLD | 3 | V3 | 0 | False | 1.255838 |

## inputs

```json
{
  "fixtures": {
    "phase1/NP-WARN": "4f700527b65fd52f9b1dc6367b898774a54602b12271b561ff6f3cd97c201377"
  },
  "annotations": {
    "phase1/NP-WARN": "ab2faa2088724659471467d71672081add0d067a61e067a2aed60d572c7c7f3a"
  },
  "derived": {},
  "godot_build_hash": "a13da4feb",
  "godot_path": "/usr/local/bin/godot4",
  "godot_fake": false,
  "upstream": {
    "N09": "31919eb4683934a49a4a7fad005697608419731c135b9dea6bf9b055e18df428",
    "N08": "9dbcb580aa021423bd8a6607bb260c93c54ee6390ad9f2827ec429270cac4b8c"
  }
}
```
