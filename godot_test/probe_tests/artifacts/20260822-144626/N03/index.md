# N03 artifacts

证据索引，不是判定。

- run-id: `20260822-144626`
- inputs_digest: `066b348923ec459331078473aef3e9885b65420607cd2f35bf48e6604df07eb9`
- Godot: `/usr/local/bin/godot4`
- version: `4.7.1.stable.official.a13da4feb`
- build hash: `a13da4feb`
- fake: `false`
- platform: `Darwin 25.3.0 / arm64`
- force_stale: `false`

## measurements

| group | step | cache | repeat | cmd | rc | timeout | wall_s |
| --- | --- | --- | --- | --- | --- | --- | --- |
| np-globalclass | t1 | COLD | 1 | V2 | 0 | False | 0.188333 |
| np-globalclass | t1 | COLD | 2 | V2 | 0 | False | 0.186767 |
| np-globalclass | t1 | COLD | 3 | V2 | 0 | False | 0.186256 |
| np-globalclass | t2 | COLD | 1 | V3 | 0 | False | 1.56324 |
| np-globalclass | t3 | WARM | 1 | V2 | 0 | False | 0.182864 |
| np-globalclass | t3 | WARM | 2 | V2 | 0 | False | 0.186241 |
| np-globalclass | t3 | WARM | 3 | V2 | 0 | False | 0.183589 |
| np-globalclass | t4 | PRESERVE | 1 | V2 | 0 | False | 0.182072 |
| np-globalclass | t4 | PRESERVE | 2 | V2 | 0 | False | 0.178568 |
| np-globalclass | t4 | PRESERVE | 3 | V2 | 0 | False | 0.179508 |
| np-globalclass | t5 | PRESERVE | 1 | V3 | 0 | False | 1.463917 |
| np-globalclass | t6 | WARM | 1 | V2 | 0 | False | 0.190176 |
| np-globalclass | t6 | WARM | 2 | V2 | 0 | False | 0.184455 |
| np-globalclass | t6 | WARM | 3 | V2 | 0 | False | 0.18297 |

## inputs

```json
{
  "fixtures": {
    "phase1/NP-GLOBALCLASS": "1feb22f193011701a7a52eaff91feffce56c3f8de5b0be02ba51c00a0d893a02"
  },
  "annotations": {
    "phase1/NP-GLOBALCLASS": "0955c81d9b98628f86f750a386a5b3c1b8a0e787a1bc0bea77978694f489c15e"
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
