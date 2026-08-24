# N15 artifacts

证据索引，不是判定。

- run-id: `20260823-235214`
- inputs_digest: `be847219d0264877bc64af89806917daedb1287d02e0c8c8ed60e4ed11b3ad90`
- Godot: `/usr/local/bin/godot4`
- version: `4.7.1.stable.official.a13da4feb`
- build hash: `a13da4feb`
- fake: `false`
- platform: `Darwin 25.3.0 / arm64`
- force_stale: `false`

## measurements

| group | step | cache | repeat | cmd | rc | timeout | wall_s |
| --- | --- | --- | --- | --- | --- | --- | --- |
| help | 1 | N/A | 1 | --help | 0 | False | 0.02103 |
| validate | validate-conversion-3to4 | COLD | 1 | validate-conversion-3to4 | 0 | False | 0.182388 |
| convert | convert-3to4 | COLD | 1 | convert-3to4 | 0 | False | 0.181882 |
| convert-args | convert-3to4-args | COLD | 1 | convert-3to4-args | 0 | False | 0.186563 |
| v3-boundary-raw | v3 | COLD | 1 | V3 | 0 | False | 1.449006 |
| v3-boundary-converted | convert-3to4 | COLD | 1 | convert-3to4 | 0 | False | 0.186806 |
| v3-boundary-converted | v3 | COLD | 1 | V3 | 0 | False | 1.45974 |

## inputs

```json
{
  "fixtures": {
    "phase2/CP-MINIMAL": "9f55c5a087787bc232a6c839de26aea12e64358314712bff6641bf45828da461"
  },
  "annotations": {
    "phase2/CP-MINIMAL": "b5a145aac2877a67f21c4e0d2bfef985b682eb200c3d95627a14caec9a644c1d"
  },
  "derived": {},
  "godot_build_hash": "a13da4feb",
  "godot_path": "/usr/local/bin/godot4",
  "godot_fake": false,
  "upstream": {}
}
```
