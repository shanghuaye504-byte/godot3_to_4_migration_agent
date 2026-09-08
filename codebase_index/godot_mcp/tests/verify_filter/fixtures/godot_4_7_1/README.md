# fixtures/godot_4_7_1/ —— 黄金原文样例

> **状态：已落地。** 下表十个 `.log` 文件与 `project_godot_with_autoload.ini` 已从
> `godot_test/probe_tests/artifacts/` 逐字拷贝（用 `Read` 工具核对过字节内容，不是凭
> 记忆重写），实现 `verify_filter/` 时直接读取这些文件即可，不需要再去 artifacts 里找。

`verifier_filter_scheme.md` §5.3/§10 要求的十份"黄金原文"必须**逐字**（含空白、大小写、
冒号位置）从真实探针 artifacts 里拷贝，不要凭记忆重写——正则最容易失配的地方恰好是这些
"看起来无关紧要"的空白细节。

| 文件（待添加） | 对应样例 | 摘自 |
| --- | --- | --- |
| `sample_a_autoload_fp_cold.log` | A：autoload FP（N01 COLD V2） | `godot_test/probe_tests/artifacts/20260822-164829/N01/np-autoload/s1/COLD/1/stderr.log` |
| `sample_b_autoload_shadow_real.log` | B：真 autoload 冲突（N01 AL-SHADOW） | `.../20260822-164829/N01/np-autoload/s7/WARM/1/stderr.log` |
| `sample_c_autoload_v1_amplified.log` | C：V1 放大 + 哨兵症状（N01 V1 WARM） | `.../20260822-164829/N01/np-autoload/s5/WARM/1/stderr.log` |
| `sample_d_addon_singleton_fp.log` | D：addon 单例 FP（N02，与 A 同规则） | `.../20260822-225134/N02/np-addon/s2/WARM/1/stderr.log` |
| `sample_e_real_syntax_error.log` | E：真语法错误（N08/N04 分母） | `.../20260822-135953/N08/np-syntax/v2/WARM/1/stderr.log` |
| `sample_f_pointer_dep1.log` | F：一级依赖 pointer（N04 dep_1） | `.../20260823-115551/N04/np-cascade/s4/WARM/1/stderr.log` |
| `sample_g_pointer_leaf_cascade.log` | G：二级依赖 + depended scripts（N04 leaf） | `.../20260823-115551/N04/np-cascade/s5/WARM/1/stderr.log` |
| `sample_h_cold_class_name.log` | H：冷缓存 class_name（N03 T1，禁止当 autoload FP 删） | `.../20260822-144626/N03/np-globalclass/t1/COLD/1/stderr.log` |
| `sample_i_uid_duplicate_cluster.log` | I：UID 重复簇（N06 V3） | `.../20260823-180913/N06/np-resource/s7/WARM/1/stderr.log` |
| `sample_j_shader_error.log` | J：shader 错误（N07 V3） | `.../20260823-182940/N07/np-shader/s2/COLD/1/stderr.log` |

以及一份 `project_godot_with_autoload.ini`（`[autoload]` 段样例，`Config="*res://config.gd"` +
`DummySingleton="*uid://qmfp8cu17gl2"`，供 `test_autoload_keys.py` 使用；`uid://` 这条是
故意保留的真实值，不要"规整"成 `res://`——那正是 `autoload.py` 不能断言值格式的证据）。

具体 run-id 目录名以实现当天 `godot_test/probe_tests/artifacts/` 下的实际内容为准，上表
路径可能需要微调；核心约束不变：**从真实产物摘，不要手写猜测的报错格式**。
