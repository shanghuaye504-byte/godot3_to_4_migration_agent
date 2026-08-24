# ISSUE：import / 冷缓存覆盖缺口

- 状态：open（本轮不补实验，收尾时再开一张卡片）
- 来源：N03 跑完后对照「哪些全局名会冷启动失效」的盘点
- 证据：`artifacts/20260822-144626/N03/`（T1 冷报 `ProbeFoo`、T4 新增 `ProbeLate` 不 import 报错）

## 已经覆盖

| 现象 | 实验 | 备注 |
| --- | --- | --- |
| `class_name` 冷启动假阳性 | N03 T1 vs T3 | 已跑 |
| 新增带 `class_name` 的 `.gd` 后缓存陈旧 | N03 T4 vs T6 | 已跑；只测了**新建文件** |
| 静态 `[autoload]` | N01；N08 步骤 9 已见 COLD `Config` | N01 尚未正式采集 |
| 插件 `add_autoload_singleton` | N02 | 未跑 |
| UID / `ext_resource` | N06 | 未跑 |
| shader 可见性（漏报） | N07 | 未跑 |

本轮明确不做：C#/GDExtension（N13 硬拒）、`ResourceFormatLoader` 变种（缓解手段与 autoload 相同）、并发 import（N14 无条件串行锁）。

## 缺口（收尾时补实验）

卡片或 `import_trigger_policy` 里写了、但**没有对应步骤**的，优先补：

1. **改已有 `class_name`（rename）**  
   N03 目的写了「新增 / 修改」，步骤只有新建 `late_class.gd`，没有把 `ProbeFoo` 改名后再 PRESERVE。修改名 ≠ 新增文件。

2. **`ordinary_gd_body_changed`**  
   policy 表有这一项，注释是「N03 T3 与 N06 步骤 3 对照」。那两步都没改普通 `.gd` 函数体。缺：只改正文、不碰 `class_name`、不 import，看是否报错。

其次、policy 没写但同类冷缓存可能误报：

3. **`class_name` 的内部类 / 静态类型名**（如 `ProbeFoo.Inner`）——默认跟全局类表走，没有单独探针。

4. **二进制 import 产物的冷 `preload`**（`.png`→`.ctex`、部分 `.tres` / PackedScene）——N06 测文本 UID/引用，N07 测 shader 盲区，没有 COLD vs WARM 的贴图/场景 preload。

## 补实验时建议

- 仍用 **一份工作区 + PRESERVE**，不要逐步新开副本（和 N03 同一形态）。
- 可并进 N03 增补步，或单独一张小卡片；不要为第 3、4 项先拆很多 N。
- 脚本只采集；不在采集里写 `CONFIRMED`。
