# N01 artifacts

证据索引，不是判定。

- run-id: `20260822-164829`
- inputs_digest: `720465e2c7e9dd11f3ecb53db7907bf4027700862bf0a7d1c8f4e07c9200c4af`
- Godot: `/usr/local/bin/godot4`
- version: `4.7.1.stable.official.a13da4feb`
- build hash: `a13da4feb`
- fake: `false`
- platform: `Darwin 25.3.0 / arm64`
- force_stale: `false`

## measurements

| group | step | cache | repeat | cmd | rc | timeout | wall_s |
| --- | --- | --- | --- | --- | --- | --- | --- |
| np-autoload | s1 | COLD | 1 | V2 | 0 | False | 0.192541 |
| np-autoload | s1 | COLD | 2 | V2 | 0 | False | 0.192419 |
| np-autoload | s1 | COLD | 3 | V2 | 0 | False | 0.193195 |
| np-autoload | s2 | COLD | 1 | V5 | 0 | False | 0.283631 |
| np-autoload | s2 | COLD | 2 | V5 | 0 | False | 0.187698 |
| np-autoload | s2 | COLD | 3 | V5 | 0 | False | 0.18484 |
| np-autoload | s3 | COLD | 1 | V3 | 0 | False | 1.544061 |
| np-autoload | s4 | WARM | 1 | V2 | 0 | False | 0.187293 |
| np-autoload | s4 | WARM | 2 | V2 | 0 | False | 0.183504 |
| np-autoload | s4 | WARM | 3 | V2 | 0 | False | 0.187198 |
| np-autoload | s5 | WARM | 1 | V1 | 0 | False | 0.18253 |
| np-autoload | s5 | WARM | 2 | V1 | 0 | False | 0.19119 |
| np-autoload | s5 | WARM | 3 | V1 | 0 | False | 0.18529 |
| np-autoload | s7 | WARM | 1 | V2 | 0 | False | 0.184512 |
| np-autoload | s7 | WARM | 2 | V2 | 0 | False | 0.18069 |
| np-autoload | s7 | WARM | 3 | V2 | 0 | False | 0.184207 |
| np-autoload | s8 | WARM | 1 | V5 | 0 | False | 0.187384 |
| np-autoload | s8 | WARM | 2 | V5 | 0 | False | 0.184404 |
| np-autoload | s8 | WARM | 3 | V5 | 0 | False | 0.181108 |

## inputs

```json
{
  "fixtures": {
    "phase1/NP-AUTOLOAD": "405f9e2e585ec9bd12e2a990c692f927f88e5343fa930bd5b20e733c444c1a5b"
  },
  "annotations": {
    "phase1/NP-AUTOLOAD": "f2dd46fbbe8e19a95b26be51735076ff02117e68e148253dea7652e847a9f166"
  },
  "derived": {},
  "godot_build_hash": "a13da4feb",
  "godot_path": "/usr/local/bin/godot4",
  "godot_fake": false,
  "upstream": {
    "N09": "31919eb4683934a49a4a7fad005697608419731c135b9dea6bf9b055e18df428",
    "N08": "9dbcb580aa021423bd8a6607bb260c93c54ee6390ad9f2827ec429270cac4b8c",
    "N03": "066b348923ec459331078473aef3e9885b65420607cd2f35bf48e6604df07eb9"
  }
}
```
