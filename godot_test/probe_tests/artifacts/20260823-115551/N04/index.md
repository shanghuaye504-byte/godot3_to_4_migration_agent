# N04 artifacts

证据索引，不是判定。

- run-id: `20260823-115551`
- inputs_digest: `007344b705e424250e4bbf3839c0217325658f7863fda7b536170553a125b808`
- Godot: `/usr/local/bin/godot4`
- version: `4.7.1.stable.official.a13da4feb`
- build hash: `a13da4feb`
- fake: `false`
- platform: `Darwin 25.3.0 / arm64`
- force_stale: `false`

## measurements

| group | step | cache | repeat | cmd | rc | timeout | wall_s |
| --- | --- | --- | --- | --- | --- | --- | --- |
| np-syntax | s3 | WARM | 1 | V2 | 0 | False | 0.185378 |
| np-syntax | s3 | WARM | 2 | V2 | 0 | False | 0.184731 |
| np-syntax | s3 | WARM | 3 | V2 | 0 | False | 0.179413 |
| np-cascade | s1 | COLD | 1 | V3 | 0 | False | 1.56534 |
| np-cascade | s1 | COLD | 2 | V3 | 0 | False | 1.454044 |
| np-cascade | s1 | COLD | 3 | V3 | 0 | False | 1.273908 |
| np-cascade | s2 | WARM | 1 | V1 | 0 | False | 0.183395 |
| np-cascade | s2 | WARM | 2 | V1 | 0 | False | 0.183061 |
| np-cascade | s2 | WARM | 3 | V1 | 0 | False | 0.179395 |
| np-cascade | s4 | WARM | 1 | V2 | 0 | False | 0.184851 |
| np-cascade | s4 | WARM | 2 | V2 | 0 | False | 0.183465 |
| np-cascade | s4 | WARM | 3 | V2 | 0 | False | 0.179846 |
| np-cascade | s5 | WARM | 1 | V2 | 0 | False | 0.186146 |
| np-cascade | s5 | WARM | 2 | V2 | 0 | False | 0.179499 |
| np-cascade | s5 | WARM | 3 | V2 | 0 | False | 0.185629 |

## inputs

```json
{
  "fixtures": {
    "phase1/NP-SYNTAX": "0f0817ea847ca09889a7abc1d2352ab9df56734bc8a24eb1cfd9ed544ed318d8",
    "phase1/NP-CASCADE": "3693a2e29b303ee718609dda4e7a3004c732719316237b13d6858f58596be4a3"
  },
  "annotations": {
    "phase1/NP-SYNTAX": "3000a2bbee6c60fa93c7296142a321da93584c06dc7156c530f275124e83f8e2",
    "phase1/NP-CASCADE": "e5c653e4595a876f668f7d4995424dde9b2803ac62915c1b410b6a733f529d59"
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
