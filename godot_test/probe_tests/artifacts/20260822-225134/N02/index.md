# N02 artifacts

证据索引，不是判定。

- run-id: `20260822-225134`
- inputs_digest: `f8557bdf810d5c65ff1636609a03facb03bedd9a3765debe6e8f0eba3a3489fe`
- Godot: `/usr/local/bin/godot4`
- version: `4.7.1.stable.official.a13da4feb`
- build hash: `a13da4feb`
- fake: `false`
- platform: `Darwin 25.3.0 / arm64`
- force_stale: `false`

## measurements

| group | step | cache | repeat | cmd | rc | timeout | wall_s |
| --- | --- | --- | --- | --- | --- | --- | --- |
| np-addon | s1 | WARM | 1 | V5 | 0 | False | 0.185125 |
| np-addon | s1 | WARM | 2 | V5 | 0 | False | 0.182229 |
| np-addon | s1 | WARM | 3 | V5 | 0 | False | 0.179003 |
| np-addon | s2 | WARM | 1 | V2 | 0 | False | 0.178607 |
| np-addon | s2 | WARM | 2 | V2 | 0 | False | 0.179739 |
| np-addon | s2 | WARM | 3 | V2 | 0 | False | 0.183042 |
| np-addon | s3 | COLD | 1 | V2 | 0 | False | 0.186719 |
| np-addon | s3 | COLD | 2 | V2 | 0 | False | 0.186669 |
| np-addon | s3 | COLD | 3 | V2 | 0 | False | 0.182 |
| np-addon | s4 | WARM | 1 | V1 | 0 | False | 0.194065 |
| np-addon | s4 | WARM | 2 | V1 | 0 | False | 0.182891 |
| np-addon | s4 | WARM | 3 | V1 | 0 | False | 0.182965 |

## inputs

```json
{
  "fixtures": {
    "phase1/NP-ADDON": "fcf0347b8b2882f6f7a5df55a2b7b534dc6c7ee6be1d7ba31cf6fd869cd1ee51"
  },
  "annotations": {
    "phase1/NP-ADDON": "a9f48b1f486b2e4548dc04098f640cdef0354d1be05a14564d1c46f4db8dd26d"
  },
  "derived": {
    "NP-ADDON@plugin-enabled": "968419ebc5b631a5b1bd29cfb29461a2ecbc7ed86d7f8e1865d897192b7806a8"
  },
  "godot_build_hash": "a13da4feb",
  "godot_path": "/usr/local/bin/godot4",
  "godot_fake": false,
  "upstream": {
    "N01": "720465e2c7e9dd11f3ecb53db7907bf4027700862bf0a7d1c8f4e07c9200c4af"
  }
}
```
