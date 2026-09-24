# scenecheckfixture

给场景解析器做对照的小语料。每个版本 4 个文件：3 个是官方演示项目里的原文，1 个是按官方 TSCN 格式补出来的。解析器还没实现，这些文件现在只供以后的测试读取。

故意写坏的场景（多个根、Git 冲突标记、悬空编号）不在这里。那些由以后的变异测试临时生成。

## 许可证与来源

真实文件来自 [godotengine/godot-demo-projects](https://github.com/godotengine/godot-demo-projects) 的 Dodge the Creeps，许可证是 MIT。不是商业游戏项目。

| 本地文件 | 上游 |
| --- | --- |
| `godot3/real_dodge_hud.tscn` | 分支 `3.5`，`2d/dodge_the_creeps/HUD.tscn` |
| `godot3/real_dodge_player.tscn` | 分支 `3.5`，`2d/dodge_the_creeps/Player.tscn` |
| `godot3/real_dodge_main.tscn` | 分支 `3.5`，`2d/dodge_the_creeps/Main.tscn` |
| `godot4/real_dodge_hud.tscn` | 分支 `master`，`2d/dodge_the_creeps/hud.tscn` |
| `godot4/real_dodge_player.tscn` | 分支 `master`，`2d/dodge_the_creeps/player.tscn` |
| `godot4/real_dodge_main.tscn` | 分支 `master`，`2d/dodge_the_creeps/main.tscn` |

格式依据是 Godot 文档仓库 `/godotengine/godot-docs` 的 TSCN 说明：Godot 3 为 `format=2`、整数 id、`ExtResource(1)`；Godot 4 为 `format=3`、字符串 id、`ExtResource("1_abc")`，并可带 `uid://`。`;` 开头是注释。`load_steps` 从 4.6 起应忽略。相对路径合法。同一文件里外部编号和内部编号可以相同。

两个 `generated_format_matrix.tscn` 使用 CRLF，且文件末尾没有换行。

## 每个文件覆盖什么

`godot3/real_dodge_hud.tscn`：`format=2`、整数 id、`ExtResource( 1 )` 带空格、`SubResource`、`parent="."`、信号连接、`__meta__` 字典。

`godot3/real_dodge_player.tscn`：`PoolColorArray`、`Vector2` / `Vector3`、多层数组、`AnimatedSprite`、`body_entered` 连接。

`godot3/real_dodge_main.tscn`：`instance=ExtResource`、`PoolVector2Array`、`parent="MobPath"`、多条连接。

`godot3/generated_format_matrix.tscn`：`;` 注释、相对路径 `icon.png`、根节点 `instance`（继承场景）、`instance_placeholder`、`groups`、空 `NodePath("")`、`custom_colors/font_color`、转义引号、尾随逗号、`KinematicBody2D`。CRLF，无结尾换行。

`godot4/real_dodge_hud.tscn`：`format=3`、`uid`、`theme_override_fonts/font`、多行字符串、`&"start_game"`。

`godot4/real_dodge_player.tscn`：`PackedColorArray`、`&"right"`、`AnimatedSprite2D`、`unique_id`、`ExtResource("1")`。

`godot4/real_dodge_main.tscn`：`PackedVector2Array`、嵌套场景、`Marker2D`。

`godot4/generated_format_matrix.tscn`：文档中的 Ball 结构，加上外部编号与内部编号同为 `1_7bt6s`、`node_paths`、`Transform3D`、`Array[Node]([])`、`libraries/""`、`theme_override_colors/font_color`、`instance_placeholder`、`binds= [`（等号后有空格）、`;` 注释、相对路径。CRLF，无结尾换行。

## 测试时怎样算通过

这 8 个文件旁边没有 `player.gd`、贴图或 `project.godot`。Step 1 和 Step 2 只读文件字节，缺资源不是解析失败。通过是指：该步列出的预期全部成立，并且没有未捕获异常。多报一条不在预期里的语法错误，或把 `format=2` 的 `E_NOT_CONVERTED` 当成解析失败，都算不通过。

六个 `real_dodge_*.tscn`：

- Step 1：语法问题为空。Godot 3 的三份是 `format=2`、整数 id；Godot 4 的三份是 `format=3`、字符串 id。
- Step 2：根数量都是 1。两份 `real_dodge_main` 含有 `instance` 节点；`MobSpawnLocation` 的父路径是 `MobPath`。

`godot3/generated_format_matrix.tscn`：

- Step 1：`;` 注释不产生节点，也不产生语法错误。空 `NodePath("")`、尾随逗号、转义引号能读完。CRLF 和无结尾换行不抛异常。`KinematicBody2D` 不是语法错误。
- Step 2：根数量是 1。根节点带 `instance`，所以 `is_inherited` 为真；落在这棵继承子树里的「本地找不到」不报 ERROR，记入弃权。`instance_placeholder` 被标成看不全的子树。

`godot4/generated_format_matrix.tscn`：

- Step 1：外部编号和内部编号同为 `1_7bt6s` 不算重复 id。`Array[Node]([])`、`libraries/""`、`binds= [`、`Transform3D` 能读完。`;` 注释不进节点。CRLF 和无结尾换行不抛异常。
- Step 2：根数量是 1。根上的 `instance` 使 `is_inherited` 为真；`instance_placeholder` 单独标成看不全的子树。

后面几步不要把「文件不在磁盘上」当成夹具坏了：

- Step 3：把夹具目录当工程根时，`res://` 指向的脚本和贴图不在磁盘上，`resolved_file` 为空是对的。两个 generated 里的相对路径 `icon.png` 要解析到该 `.tscn` 所在目录；文件仍可以不存在。
- Step 4：四个 Godot 3 文件都应报 `E_NOT_CONVERTED`，因为 `format` 是 2。这不是解析失败。四个 Godot 4 文件的 `format` 都是 3，其中三个真实文件没有语法级 ERROR。`godot3/generated_format_matrix.tscn` 里的 `KinematicBody2D` 只有在配置了 `migration_rules_db` 时才报 `E_UNMIGRATED_TYPE`；没配规则库时不报这条，并标 `rules_unavailable`。继承根和 `instance_placeholder` 下面的「本地找不到」必须弃权。不要用这 8 个孤立文件做「Godot 能 load 就不报 ERROR」：它们引用的资源不在旁边，那一项用以后单独准备的可加载小工程。
- Step 5：若把当前这 8 个文件冻成 baseline，上面的 `E_NOT_CONVERTED` 是旧账，不是 regression。成员消失、退出码和旧测试回归不要改这 8 个文件来做，另建带 `.gd` 的临时工程。
