# N06 artifacts

证据索引，不是判定。

- run-id: `20260823-171359`
- inputs_digest: `ad84c36674156ecd3fb832de6dc09de6a93ec8350d2c117e938c2a7597720d16`
- Godot: `/usr/local/bin/godot4`
- version: `4.7.1.stable.official.a13da4feb`
- build hash: `a13da4feb`
- fake: `false`
- platform: `Darwin 25.3.0 / arm64`
- force_stale: `false`

## measurements

| group | step | cache | repeat | cmd | rc | timeout | wall_s |
| --- | --- | --- | --- | --- | --- | --- | --- |
| np-resource | s2 | COLD | 1 | V3 | 0 | False | 1.445799 |
| np-resource | s3 | WARM | 1 | V1 | 0 | False | 0.185711 |
| np-resource | s3 | WARM | 2 | V1 | 0 | False | 0.186461 |
| np-resource | s3 | WARM | 3 | V1 | 0 | False | 0.180133 |
| np-resource | s5 | WARM | 1 | V2 | 0 | False | 0.187018 |
| np-resource | s5 | WARM | 2 | V2 | 0 | False | 0.180861 |
| np-resource | s5 | WARM | 3 | V2 | 0 | False | 0.178578 |
| np-resource | s6 | WARM | 1 | V1 | 0 | False | 0.187755 |
| np-resource | s6 | WARM | 2 | V1 | 0 | False | 0.184349 |
| np-resource | s6 | WARM | 3 | V1 | 0 | False | 0.183391 |
| np-resource | s7 | WARM | 1 | V3 | 0 | False | 1.266606 |
| np-resource | s7 | WARM | 2 | V3 | 0 | False | 1.460886 |
| np-resource | s7 | WARM | 3 | V3 | 0 | False | 1.261525 |
| np-resource | s8 | WARM | 1 | V1 | 0 | False | 0.177419 |
| np-resource | s8 | WARM | 2 | V1 | 0 | False | 0.182893 |
| np-resource | s8 | WARM | 3 | V1 | 0 | False | 0.185277 |
| np-resource | s10 | WARM | 1 | V1 | 0 | False | 0.184483 |
| np-resource | s10 | WARM | 2 | V1 | 0 | False | 0.185118 |
| np-resource | s10 | WARM | 3 | V1 | 0 | False | 0.184944 |
| np-resource | s11 | WARM | 1 | V3 | 0 | False | 1.262577 |
| np-resource | s12 | WARM | 1 | V1 | 0 | False | 0.183682 |
| np-resource | s12 | WARM | 2 | V1 | 0 | False | 0.177513 |
| np-resource | s12 | WARM | 3 | V1 | 0 | False | 0.180788 |

## inputs

```json
{
  "fixtures": {
    "phase1/NP-RESOURCE": "e8cf6d84a1841f73dbf9e23da3b194f05a70970024058123822977c1646617a9"
  },
  "annotations": {
    "phase1/NP-RESOURCE": "e2e6260358311f73a48ab09bbf5e899e23810090d401bb3570099eaa5a1655f4"
  },
  "derived": {
    "NP-RESOURCE@uid-baseline": "4f5d06554946240d7ada4d679444772ff7105e66d36cad74e9944774b782641d"
  },
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
