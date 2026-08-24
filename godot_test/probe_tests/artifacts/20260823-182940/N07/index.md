# N07 artifacts

证据索引，不是判定。

- run-id: `20260823-182940`
- inputs_digest: `596cccfcd0b676a3ad98e723f5662040792b33d5a9db6f62e252e6065f44d970`
- Godot: `/usr/local/bin/godot4`
- version: `4.7.1.stable.official.a13da4feb`
- build hash: `a13da4feb`
- fake: `false`
- platform: `Darwin 25.3.0 / arm64`
- force_stale: `false`

## measurements

| group | step | cache | repeat | cmd | rc | timeout | wall_s |
| --- | --- | --- | --- | --- | --- | --- | --- |
| np-shader | s1 | COLD | 1 | V2 | 0 | False | 0.181675 |
| np-shader | s1 | COLD | 2 | V2 | 0 | False | 0.184928 |
| np-shader | s1 | COLD | 3 | V2 | 0 | False | 0.180743 |
| np-shader | s2 | COLD | 1 | V3 | 0 | False | 1.25807 |
| np-shader | s2 | COLD | 2 | V3 | 0 | False | 1.451149 |
| np-shader | s2 | COLD | 3 | V3 | 0 | False | 1.54707 |
| np-shader | s3 | WARM | 1 | V2 | 0 | False | 0.188235 |
| np-shader | s3 | WARM | 2 | V2 | 0 | False | 0.183067 |
| np-shader | s3 | WARM | 3 | V2 | 0 | False | 0.184192 |
| np-shader | s4 | WARM | 1 | V5 | 0 | False | 0.186599 |
| np-shader | s4 | WARM | 2 | V5 | 0 | False | 0.178965 |
| np-shader | s4 | WARM | 3 | V5 | 0 | False | 0.179012 |
| np-shader | s5 | WARM | 1 | V1 | 0 | False | 0.17495 |
| np-shader | s5 | WARM | 2 | V1 | 0 | False | 0.183903 |
| np-shader | s5 | WARM | 3 | V1 | 0 | False | 0.187112 |

## inputs

```json
{
  "fixtures": {
    "phase1/NP-SHADER": "4dfdfcd80d746180439486b5276df42d3e089fa084bae3f201f06e0909f75807"
  },
  "annotations": {
    "phase1/NP-SHADER": "5f321ddfe5ebb0f5bed028b1a2f4584e68f38af48ce05349c97f0c8418760860"
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
