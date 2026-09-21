上来先说结论，然后逐条拆。

四个问题的答案，一句话版：

问题	答案
1. 场景文件大不大、解析贵不贵	不大、极便宜。 .tscn 是纯文本 INI-like 格式，正则/行扫就能拿到全部类型名和引用。成本远低于你已有的 tree-sitter 索引，不该成为不索引的理由
2. 没有 verifier 怎么保证正确性	别去找"跑出来的 reward"，改用"静态闭合不变量"当 reward。 场景改名的正确性本质是引用一致性（可判定），不是运行时行为（不可判定）。这是唯一能给出确定性保证的路
3. headless 能不能跑一帧、能不能查出场景错误	能跑（--quit-after N），而且能查出结构性错误（缺 ext_resource / 未知 class / 脚本挂载失败 / 循环依赖）。但查不出渲染、shader 编译、GPU、输入、物理稳态问题
4. 上 GUI 有没有帮助	对你要解决的"改名一致性"几乎没帮助（多出的都是渲染/shader 层信号，和改名无关），但对 shader 语义是唯一手段。代价：需要 GPU / X11，CI 里不稳。建议：不进主循环
下面展开。

一、.tscn 的规模与解析成本
格式事实

.tscn 是 INI-like 纯文本，结构极其规整，全部信息都在方括号头和 key = value 里：

ini
[gd_scene load_steps=3 format=3 uid="uid://c8n2..."]

[ext_resource type="Script" path="res://player.gd" id="1_7bt6s"]
[ext_resource type="Texture2D" uid="uid://bx4k..." path="res://icon.png" id="2_a1b2c"]

[node name="Player" type="CharacterBody2D"]
script = ExtResource("1_7bt6s")

[node name="Sprite" type="Sprite2D" parent="."]
texture = ExtResource("2_a1b2c")

你做跨 .gd + .tscn 改名一致性需要的信息，只有四类，全部是行首可锚定的：

需要的信息	在哪	抓取方式
引用了哪些外部文件	[ext_resource ... path="res://..."]	行首 [ext_resource
节点用了什么类型	[node ... type="CharacterBody2D"]	行首 [node
脚本挂在哪个节点	script = ExtResource("id") → 查表	两步
内嵌资源类型	[sub_resource type="..."]	行首 [sub_resource
信号连接	[connection signal="x" from=".." to=".." method="y"]	行首 [connection
没有嵌套块、没有多行值需要平衡括号（属性值可能跨行，但那是 Array/Dictionary 字面量，与上述五类无关）。所以：不需要 tree-sitter、不需要写 parser generator，一个逐行状态机 + 5 条正则就完整覆盖。

规模

典型场景：几 KB ～ 几十 KB，几十到几百个 [node]
中型项目：几百到一两千个 .tscn
病态离群：单个 .tscn 上 MB 甚至十几 MB（手工搭的大关卡、TileMap 数据内嵌、误把资源 embed 进场景）
成本量级对比： 你现在的 codeindex 对 .gd 是完整 tree-sitter CST 解析（还要 has_error 检查、抽 func/signal/var/const/enum、抽函数体调用边）。逐行正则扫 .tscn 比这便宜一个数量级以上。你 codeindex 的 up 预算是 120s 全量扫描 —— 加进 .tscn 的边际成本基本在噪声里。

⚠️ 唯一真需要设上限的地方：那些 MB 级离群 .tscn。这和你 intake precheck 要扫的"官方 converter 静默跳过的大文件"是同一批文件，一次扫描两个用途。

但是：要不要塞进 codeindex？

我建议不塞。 理由是你自己定的架构约束：

codeindex 的 schema 是 classes / functions / symbols / edges(kind='call'|'extends') —— 为代码符号设计
.tscn 的边是 node--type-->Class、scene--ext_resource-->file、node--script-->file、signal--method-->func，语义完全不同，硬塞进 edges 会污染 call-chain / class-hierarchy 的语义
你明确说了"已实现的不改"
更干净的做法：独立一张 scene_refs 表（或独立 sqlite），由 scene_check 组件维护。 它只服务两件事：① codemod 的改名目标清单；② 一致性校验。不参与 find-symbol / call-chain。

代价：LLM 想搜场景里的字符串，走 grep（你本来就要给它，因为 grep 是唯一能看见 .tscn 的通道）。结构化查询走 scene_check。边界清晰，零侵入。

二、没有 reward 怎么保证场景改动正确 ← 这是核心问题
先把问题拆成两个性质完全不同的部分，混在一起谈就没法要到保证：

性质	能不能给保证
(a) 引用一致性：.gd 改了 class_name / 脚本路径 / 信号方法名，.tscn 里对应引用是否同步	纯静态、可判定	✅ 能给确定性保证
(b) 运行时行为：改完以后游戏玩起来对不对、物理数值是否合理、视觉是否正确	不可判定	❌ 任何自动 verifier 都给不了
关键认知：你要解决的"跨 .gd + .tscn 改名一致性"100% 属于 (a)。 它之所以现在没有 verifier，不是因为它不可验证，而是因为你把希望寄托在"让 Godot 跑起来告诉我对不对"上了。而 (a) 根本不需要跑 Godot —— 它是个图闭合问题。

用"闭合不变量"替代 reward

把 reward 从"外部环境反馈"换成"改写前后的不变量检查"。改名操作的正确性定义为：

一次改名是正确的，当且仅当：改名前后，引用图的"悬空边数"不增加，且被改名符号的旧名在全仓的出现次数归零。
具体落成 5 条可机械判定的检查（全部零 Godot）：

#	不变量	检查方式	捕获的真实 bug
I1	.tscn 的每个 ext_resource path 都存在于磁盘	文件系统 stat	改名/移动文件忘了改场景
I2	每个 [node type="X"] 的 X ∈ (引擎类白名单 ∪ 仓库 class_name 集合)	查 codeindex classes 表 + 引擎类清单	3→4 类型改名漏了场景（KinematicBody2D 残留）
I3	每个 script = ExtResource(id) 指向的 .gd 存在且语法可解析	codeindex 已有 has_error 信息	脚本挂载失败
I4	每个 [connection method="m" to="N"]，m 存在于 N 挂载脚本的 func 集合	codeindex functions 表	⭐ 改函数名忘了改信号连接 —— 这是最高频、最隐蔽的一类
I5	旧符号在全仓（含 .tscn/.tres）出现次数 = 0	grep	改了一半
这 5 条里有 4 条直接复用 codeindex 已有的表，几乎不用新代码。

为什么这比"跑起来"更强

这是个反直觉但重要的点：

I4 类 bug，跑一帧也查不出来。 信号连接的 method 不存在，Godot 在加载场景时确实会报错（"Node method not found"），但只有当那个场景真的被加载。你的入口场景之外的 300 个场景不会被加载 → 静态检查覆盖率 100%，跑一帧覆盖率 ≈1%
I1/I2 同理：静态检查是全仓穷举，跑游戏是单路径抽样
静态检查可复现、无超时、无崩溃、零 flaky，能直接进你的 Gate 签名
所以对场景改名这件事：静态一致性检查不是"退而求其次的替代品"，它是比运行时更强的 oracle。

落成 reward 的形式

让 scene_check 输出与你 verify 同构的结构：

json
{
  "scene_status": "CLEAN | HAS_ERRORS",
  "violations": [
    {"kind":"dangling_ext_resource|unknown_node_type|missing_script|
             orphan_connection_method|stale_old_symbol",
     "scene_path":"res://x.tscn", "line":42,
     "symbol":"KinematicBody2D", "local_signature":"..."}
  ],
  "signature_set": ["..."],
  "coverage": {"scenes_scanned": 312, "scenes_skipped_oversize": 2}
}

关键：signature_set 与 verify 同构 → 你的 Gate 无进展 / A→B→A 震荡检测直接对场景生效，不用写新的 Gate。这是把已有投资复用到新维度上，成本近乎零。

三、headless 能跑一帧吗？能查出什么？
能跑

Godot 4 有两个相关参数：

--quit-after <N>：跑 N 帧后退出（N=1 就是"跑一帧"）。这是你记得的那个
--quit：第一个 idle frame 后立刻退出
配合 --headless（= --display-driver headless + --audio-driver Dummy），可以做到：真正走完 _ready() → 至少一个 _process() → 退出。

也可以更精确控制：用 --script 跑一个自写的 SceneTree 脚本，遍历 ResourceLoader.load() 所有 .tscn（只 load 不 instantiate），或者 instantiate() 但不 add_child。

headless 一帧能查出的（结构性错误）

这些是在 资源加载 / 场景反序列化 阶段产生的，与渲染无关，headless 完整保留：

能查出	典型报错
ext_resource 路径不存在	Failed loading resource: res://...
未知节点类型	Cannot get class 'KinematicBody2D'
脚本挂载失败（语法错 / class 不存在）	Failed to load script ... Parse Error
UID 失效 / 冲突	UID duplicate / Invalid UID
场景循环依赖	Cyclic resource inclusion
.tres 资源类型不匹配	Resource type mismatch
autoload 初始化失败	_ready 里的 runtime error
信号连接 method 不存在（仅被加载的场景）	Node method not found
headless 一帧查不出的

这就是你直觉里担心的部分，而且比你想的更广：

查不出	原因
shader 编译错误 / 语义错误	headless 用 dummy rendering driver，根本不编译 shader
纹理 / 材质 / mesh 视觉损坏	无 rasterization
RenderingDevice / viewport / 后处理	无 GPU 上下文
音频逻辑	Dummy audio driver
输入相关逻辑	无输入事件源
"跑一帧之后才会崩"的逻辑（状态机第 N 帧、计时器、物理稳态）	一帧不够
未被加载路径上的一切	覆盖率问题（见上）
数值语义错误（extents→size 尺寸差 2 倍）	不报错，行为静默错误 ← 你的 static_scan_post_l0 就是为这个准备的
⚠️ 一个必须知道的陷阱

你的白名单里已经明确 --debug 会 signal 11。跑一帧是远比 --check-only 危险的操作：它会真的执行用户的 _ready()，而迁移中途的项目大概率就是会崩。

这意味着：--quit-after 1 产出的 crash 信号，信噪比极低。 崩了你根本分不清是"场景真的坏"还是"某个 _ready 里有个与场景无关的 nil 解引用"。而你整个系统的核心价值是去噪后的根因。

所以我的建议：

阶段	用不用跑一帧
主修复循环（每轮）	❌ 不用。用 scene_check 静态不变量，快、稳、全覆盖、可签名
收尾门（一次，GDScript 已 CLEAN 后）	✅ 用，但只用 load-only 遍历（ResourceLoader.load() 不 instantiate），避免执行 _ready
真跑 --quit-after 1	🟡 可选的额外证据，INFRA_FAILURE 不进 Gate、不硬停止，只写进 trace 当观察指标
load-only 遍历是甜点：它能拿到上面"能查出"那一整列（缺引用、未知类型、脚本挂载、UID、循环依赖），同时完全不执行游戏逻辑，所以不会有 _ready 崩溃噪声，也是全仓穷举而非单路径。信噪比最高的一档。

四、上真 GUI 有帮助吗？
多出来的信号

GUI 相比 headless 新增	对"改名一致性"有用吗
shader 真实编译（GLSL/SPIR-V 报错）	❌ 无关
纹理/材质/mesh 实际上传 GPU	❌ 无关
viewport / 后处理 / RenderingDevice 错误	❌ 无关
视觉正确性（只有截图对比才能量）	❌ 无关
全部新增信号都在渲染层，而你的改名问题一个都不在渲染层。

代价

需要 GPU / X11 / Wayland；CI 容器里要 xvfb + Mesa 软渲染（软渲染本身又会引入一批假错误）
启动慢、flaky、可能挂住不退出
你的 verify 设计是 timeout + killpg 整进程组、区分 TIMEOUT/CRASH —— GUI 会显著抬高 TIMEOUT 率，进而误触发你的 CIRCUIT_OPEN（连续 3 次 infra 失败熔断）。这会直接污染你的核心指标
结论

不进主循环，不进收尾门。

唯一值得考虑的位置：如果你以后要做 shader 语义验证（你现在明确不做），那 GUI 是唯一手段。届时作为独立的、离线的、不影响 Gate 的旁路跑，结果只写 trace。

另外：--editor --import（你的 V3）本来就已经覆盖了"资源导入 / UID / shader 能否被编辑器接受"这一层的大部分价值，且已经在你白名单里、已经稳定。GUI 的增量非常有限。

总结成执行清单
1. 索引：.tscn/.tres 用独立的 scene_refs 表，逐行正则 5 条，不进 codeindex 的 edges。成本可忽略。同时对 MB 级离群文件设上限并登记（与 intake precheck 共用一次扫描）。

2. Verifier：场景的 reward = 5 条静态闭合不变量（I1 悬空引用 / I2 未知类型 / I3 脚本挂载 / I4 信号 method 孤儿 / I5 旧符号残留），其中 4 条直接复用 codeindex 已有表。输出 signature_set 与 verify 同构 → 白拿 Gate 的震荡/无进展检测。

3. headless 跑帧：--quit-after N 存在且能查结构性错误，但信噪比差（会执行 _ready，迁移中途必崩）。用 load-only 的 ResourceLoader.load() 遍历做收尾门，全覆盖 + 零逻辑执行，是信噪比最优解。真跑帧只当旁路观察，不进 Gate。

4. GUI：对改名一致性零增益，只增渲染层信号；且会抬高 TIMEOUT 率误触 CIRCUIT_OPEN，污染核心指标。不做。

最重要的一句：场景改名的正确性是图闭合问题（可判定），不是行为正确性问题。你不缺 reward，你缺的是承认静态不变量就是 reward——而且它比跑游戏覆盖率高两个数量级、零 flaky、能直接进你已有的 Gate。

要不要我接着给 scene_refs 的 5 条正则 + 逐行状态机（含多行数组值的跳过逻辑），还是 I1–I5 五条不变量的具体 SQL/实现（复用你 codeindex 的 classes/functions 表）？我建议先做 I4 —— 它是唯一现有工具链完全盲、且真实项目里高频踩的一类。

先给一个会改变整个设计的重新框定，因为它同时回答了你三个问题的一半。

0. 关键重构：converter 先跑 → 建立 baseline → reward 用 delta
你提到"LLM 修复前先跑一次官方 converter"。这件事的顺序决定了整套设计：

① 官方 converter 3→4  ──►  ② --editor --import  ──►  ③ 建 index + scene_refs
                                                            │
                                                            ▼
                                                   ④ 冻结 baseline 违规集
                                                            │
                                                            ▼
                                                   ⑤ LLM 修复循环（reward = Δ）
                                                            │
                                                            ▼
                                                   ⑥ 收尾门：静态全量 + load-only

为什么第 ④ 步是整个设计的支点：

converter 跑完之后，场景文件里一定还有残留违规（下面 1.3 会列清单）。如果你的 scene_check 直接把"绝对违规数"喂给 LLM，会发生两件坏事：

LLM 一开局就看到几十上百条它没造成的错误 → 去追 converter 的遗留债 → 偏离主任务（你的主任务是让 GDScript CLEAN）
它自己改名造成的 1 条新违规，淹没在 80 条历史违规里 → 恰好丢掉了你最想抓的信号
所以：在 ③ 之后立刻冻结一份 baseline 违规集合（按 signature 存盘）。此后 reward 只看 delta。

reward 类别	定义	处置
REGRESSION	signature ∉ baseline，本轮新出现	⛔ 硬负反馈，必须修——这是"改名忘了迁移"的精确捕获
FIXED	signature ∈ baseline，已消失	✅ 正向信号，计入进展
PRE_EXISTING	signature ∈ baseline，仍存在	🟡 只报数，不阻塞，进 backlog
这一刀下去，你的 reward 信噪比从"几十条噪声里找 1 条"变成"0 条噪声，1 条信号"。而且 delta 语义天然复用你已有的 signature_set 震荡/无进展检测。

一、.tscn 解析要不要进 codeindex
1.1 我上次的建议有一半是错的
你的反驳完全正确：如果 LLM 搜 Player 只看到 .gd 的命中，它就没有任何线索知道还有 3 个 .tscn 引用了它。这不是"它可能忘"，这是你没给它信息，它必然忘。任何依赖"LLM 记得主动再查一次 scene_check"的设计都会漏。

但我反对把场景边塞进 edges 表也是对的（会污染 call-chain / class-hierarchy 的图语义）。

这两件事其实不冲突，因为它们是不同层：

存储分离，读取合一。
层	决策
存储	.tscn 引用存独立表 scene_refs，不进 edges。call-chain / class-hierarchy 的遍历完全不受影响
读取	find-symbol 的返回结果里追加一个 scene_usages 段，由 scene_refs 表 join 出来
find-symbol Player 的返回变成：

json
{
  "symbol": "Player",
  "definitions": [{"file":"res://actors/player.gd","line":3,"kind":"class_name"}],
  "code_usages": [ ...原有... ],
  "scene_usages": [
    {"scene":"res://levels/l1.tscn","line":14,"ref_kind":"script_attach","node":"Player"},
    {"scene":"res://ui/hud.tscn","line":8,"ref_kind":"ext_resource_path"},
    {"scene":"res://levels/l2.tscn","line":51,"ref_kind":"connection_method","detail":"signal=died method=_on_player_died"}
  ],
  "scene_usage_count": 3
}

⭐ 最关键的一行是 scene_usage_count。 哪怕 LLM 不读详情，只要它 > 0，就是一个无法忽略的视觉标记：「你要改的东西，场景里有 3 处引用」。这比任何 prompt 里的"请记得检查场景文件"都有效一个量级——把约束放进它一定会读的数据结构里，而不是放进它可能会忽略的指令里。

同样地给 find-symbol 对函数的返回加 scene_usages，因为信号连接引用的是方法名，这是最高频的漏改点。

1.2 解析实现（逐行状态机，约 150 行）
.tscn / .tres 同格式。唯一的真陷阱是多行属性值（Dictionary / 长 Array 会被 Godot 写成跨行），所以不能无脑用 ^\[ 判段头。

smalltalk
状态: depth = 0   # ( [ { 的净余量
逐行:
    if depth == 0 and 行匹配 ^\[(gd_scene|gd_resource|ext_resource|sub_resource|node|connection|editable|resource)\b:
        → 解析段头属性（key="v" / key=数字 的键值对）
        → 切换 current_section
    else:
        → 属性行: ^\s*([\w/:.]+)\s*=\s*(.*)$  抓 key
        → 累加 depth += 该行 ( [ { 数 - ) ] } 数   （需跳过字符串字面量内的括号）

抽出 5 类记录，落 scene_refs：

ref_kind	来源	存什么
ext_resource_path	[ext_resource type=.. uid=.. path=.. id=..]	path, uid, type, id
node_type	[node name=.. type=.. parent=..]	type, node_path
script_attach	script = ExtResource("id") → 查 id 表	目标 .gd 路径, 所在 node_path
connection_method	[connection signal=.. from=.. to=.. method=..]	signal, from, to, method, binds
sub_resource_type	[sub_resource type=..]	type
另外顺手建节点树（name + parent → 全路径），给 Layer 1 的 intra-file 检查用。

成本：纯行扫，无 CST。比你现有 tree-sitter 解析 .gd 便宜一个数量级，在 120s 预算里是噪声。唯一要设的闸门是 MB 级离群 .tscn——它们和 converter 静默跳过的那批是同一批文件，一次扫描登记两用（超限文件标 SKIPPED_OVERSIZE 并计入 coverage，不假装扫过了）。

已知盲区（必须显式记账，不能装作没有）：Godot 4.4+ 以 uid:// 为主键，path= 理论上可能与 uid 指向不一致。静态解析只信 path=。uid 层的真相只有引擎自己知道 → 这正是 Q3 的 load-only 存在的理由。

1.3 converter 跑完之后，LLM 还需要动 .tscn 吗？
需要，但性质完全变了。 官方 converter 对 .tscn 做的是已知 3→4 重命名表的文本替换（类名、属性名、信号名）。它覆盖得相当好。所以 LLM 要动场景的场合，主力不是"补 converter 漏掉的引擎重命名"，而是"为自己的重构善后"：

#	LLM 动 .tscn 的原因	触发的违规类型	频率
A	⭐ 它自己改了函数名（为修错误而重命名 / 改签名），而该函数是信号回调	connection_method 孤儿	最高
B	⭐ 它自己移动/重命名/拆分了 .gd 文件	ext_resource_path 悬空 + script_attach 失效	最高
C	它改了 class_name	自定义节点类型失效	高
D	converter 静默跳过的超大 .tscn，整个文件还是 3.x 类名	node_type 未知（成批）	中，但集中
E	3.x 中被移除且无 1:1 映射的节点（converter 无从下手）	node_type 未知	中
F	属性名改了但数值语义变了（经典：extents → size，含义差 2 倍）	⚠️ 静默错误，不报错	中
G	自定义 Resource 的 class_name 改名 → .tres 失配	类型不匹配	低
H	节点本身改名，导致 parent= / connection from/to 断裂	intra-file 路径断裂	低但致命
这张表是整个 verifier 设计的需求来源，注意两个结论：

A、B、C 三类（占绝对多数）全部是 LLM 自己制造的 regression → 它们必然 ∉ baseline → delta reward 能 100% 精确抓住。这印证了 §0 的设计。
F 类永远不会被任何 verifier 抓到（语法对、引用对、能加载、能跑）。这是你 static_scan_post_l0 的地盘，不要试图让 scene_check 承担它，只在报告里保留一个"高风险属性清单"提示位。
二、五条不变量：整合成一条流水线
2.1 先纠正一个说法：这不是 5 个检查，是 1 个图 + 5 条规则
正确的心智模型是：

一次解析 → 建一张引用图 → 在同一张图上跑 5 条规则 → 一份输出。
它们不能分开跑，因为共享同一份解析结果和同一份 codeindex 快照。分开跑 = 重复解析 + 可能读到不一致的快照。

2.2 按依赖分三层（这是"5 条"的正确组织方式）
分层的意义是：层数越低越可靠、越不可能误报。误报是这套系统的头号敌人——一旦 LLM 学会忽略 scene_check 的输出，你就永久失去了这个信号。

Layer 1 — 文件内自洽（只需要 .tscn 自己）

零外部依赖，零误报可能。

规则	检查	抓 §1.3 的
I0 · 格式完整	段头可解析；format=3；ExtResource("id") 引用的 id 已在本文件声明；括号平衡	手改烂了、converter 半途而废
I6 · 节点路径自洽	每个 parent="A/B" 能在本文件节点树里解析到；[connection from/to] 的节点路径存在	H
⚠️ I6 的误报陷阱：场景里有 instance=ExtResource(...)（实例化子场景）或 [editable path=..] 时，被引用的节点定义在别的文件里，本地解析不到。此时必须判为 UNRESOLVED 并计入 coverage 缺口，绝不能报错。这是我最强调的一条实现纪律。
Layer 2 — 跨文件解析（需要 codeindex + 文件系统 + 引擎类清单）

主力层，抓 §1.3 的 A/B/C/D/E。

规则	检查	实现（全部是现成表的 join）	抓
I1 · 引用不悬空	每个 ext_resource.path 在磁盘存在	stat()	B、D
I2 · 节点类型已知	node_type ∈ (引擎类集合 ∪ codeindex classes.class_name)	一次 set 查	C、D、E
I3 · 脚本挂载有效	script_attach 目标存在 + codeindex 里 has_error = false	查 classes / 文件表	B
I3b · 脚本与节点类型兼容（可选，强力）	脚本 extends X，节点 type=Y，要求 Y 是 X 或其子类	用 edges(kind='extends') + 引擎继承树	脚本挂错节点
I4 · 信号方法不孤儿	connection.method ∈ (to 节点所挂脚本的 functions，沿 extends 链向上)	查 functions + 爬 extends	⭐ A（最高频）
关于 I2 的引擎类集合：用 Godot 自己生成，别手维护。一次性跑
godot --headless --script dump_classdb.gd → ClassDB.get_class_list() + 每个类的父类 → 存成 JSON。这份 JSON 同时供 I2（存在性）和 I3b（继承链）用，按引擎版本缓存。

关于 I4 的向上查找：方法可能定义在父类或引擎基类（_on_button_pressed 定义在自己，但 _ready 来自 Node）。所以必须沿 extends 链爬到引擎类，命中引擎类的方法集就算通过。爬不到顶（extends 未知类）→ UNRESOLVED，不报错。

可选 I4b · 参数数量：method 的形参数 应 = 信号参数数 + binds 数（考虑默认值）。命中率不错，但需要 codeindex 存了形参列表；若没存就跳过，不值得为它改 schema。
Layer 3 — 时序 delta（需要 baseline 快照）

规则	检查	实现
I5 · 旧符号归零	上一快照存在、当前快照已消失的符号，不得仍出现在任何 .tscn / .tres 里	见下
I5 的实现是这套设计里最聪明的一块，值得单独讲。

我上次说"grep 旧名"，但**"旧名"从哪来？** 如果依赖 LLM 主动声明"我把 X 改成了 Y"，它一定会忘——那就又回到了原点。

正确做法：从 codeindex 快照差分里自动推导。

每轮修复后重建 codeindex（你本来就要增量重建）
  symbols_gone = symbols(T-1) \ symbols(T)      # 消失的符号 = 被改名或被删
  for s in symbols_gone:
      if s 仍出现在任何 .tscn/.tres 里:
          → I5 违规: "符号 s 已从代码中消失，但 res://x.tscn:42 仍在引用"

零 LLM 配合、零人工维护、自动捕获每一次改名遗漏。 而且它捕获的是 I1~I4 可能漏掉的那些"不在结构化引用位置、而是躺在某个属性字符串里"的名字（比如 animation = "old_name"、导出的 NodePath、StringName 字面量）。

I5 与 I1~I4 的关系：I1I4 是位置已知的强检查（精确，能定位到语义角色）；I5 是位置未知的弱检查（可能误报，但召回兜底）。所以 I5 的违规默认输出为 WARN 而非 ERROR，除非它同时被 I1I4 中某条确认。强弱分级，避免 grep 噪声污染硬 reward。

2.3 统一输出（与 verify 同构）
json
{
  "scene_status": "CLEAN | REGRESSION | PRE_EXISTING_ONLY",
  "counts": {"regression": 1, "fixed": 3, "pre_existing": 42, "warn": 5},
  "regressions": [
    {
      "sig": "orphan_connection|res://levels/l1.tscn|Player|died|_on_player_died",
      "rule": "I4",
      "severity": "ERROR",
      "scene": "res://levels/l1.tscn", "line": 51,
      "msg": "connection method '_on_player_died' 不存在于 Player 所挂脚本 res://actors/player.gd",
      "hint_symbol": "_on_player_died",
      "likely_cause": "renamed_in_code"
    }
  ],
  "signature_set": ["orphan_connection|res://levels/l1.tscn|..."],
  "coverage": {
    "scenes_total": 314, "scanned": 311,
    "skipped_oversize": 2, "unresolved_rules": {"I6": 18, "I4": 7}
  }
}

三个设计要点：

signature_set 与 verify 同构 → 你现成的 Gate 无进展检测 / A→B→A 震荡检测直接对场景生效，零新代码。
coverage 必须输出。 "扫了 311/314，I6 有 18 处无法解析" 是诚实的；隐藏它会让你误以为 CLEAN 意味着正确。
likely_cause + hint_symbol 给 LLM 可操作的下一步，而不是只丢一个错误。
2.4 什么时候调用：两处，而不是一处
这是你问题 2 的核心，我的答案很明确：Agent 自测和收尾门都要有，但职责完全不同。

A. Agent 自测（主循环内）	B. 收尾门（Gate）
触发	每次编辑触及 .gd/.tscn 后	GDScript 已 CLEAN、准备收工时
范围	--changed-only（受影响的场景子集）	全量
层	Layer 1 + 2 + 3	Layer 1 + 2 + 3 + load-only
阻塞	不阻塞，但 regression > 0 时输出顶到最前面	⛔ regression > 0 → 打回
目的	即时 reward，在错误还热的时候纠正	最终担保
耗时	< 1s	数秒 ~ 十几秒
--changed-only 的范围怎么算（性能关键）：
从本轮 diff 涉及的 .gd 文件出发，反查 scene_refs 里引用了它们的场景，再并上本轮直接改动的 .tscn。这是个一跳反向索引查询，毫秒级。全量 314 个场景重扫也就几百毫秒，但 changed-only 让输出也变干净了——LLM 只看到和它刚做的事有关的东西。

⚠️ 防绕过：Gate 必须拒绝"陈旧"的 scene_check

你不想改已实现的 verify，所以 scene_check 是独立工具。这留下一个洞：LLM 可能干脆不调用它。

堵法不是在 prompt 里求它，而是在 Gate 上加一条硬约束：

Gate 关闭条件:
    verify == CLEAN
AND scene_check 的运行时刻 晚于 最后一次文件修改时刻
AND scene_check.regression == 0

即：Gate 自己在关闭前强制跑一次全量 scene_check，不信任 LLM 报上来的结果。LLM 在循环里跑 scene_check 是为了自己少走弯路（它有动力），Gate 跑是为了正确性（不依赖它的动力）。这两个动机分开，设计就稳了。

三、收尾门的 load-only：它到底验什么
3.1 一句话定位
静态检查（第二章）是你对 Godot 资源加载器的一次"重新实现"。load-only 是拿引擎本体去校验你的实现对不对。
它不是"多一层保险"这么廉价的说法，它验的是一类你的正则原理上看不见的东西。

3.2 具体做法
gdscript
# tools/load_sweep.gd —— godot --headless --script tools/load_sweep.gd
# 用法: 从 file_list.txt 读待验文件, 从 resume_at 续跑
for path in paths:
    print("###BEGIN ", path)          # 哨兵：用于 stderr 归因
    var r = ResourceLoader.load(path, "", ResourceLoader.CACHE_MODE_IGNORE)
    print("###END ", path, " ok=", r != null)

只 load()，不 instantiate()，绝不 add_child()。

阶段	会发生	_ready 跑吗
load()	反序列化、递归解析全部 ext_resource、解析类名、编译脚本、加载纹理/材质、构造 SubResource	❌ 不跑
instantiate()	真正 new 出节点、跑 _init	❌ 不跑（但 _init / @tool 会跑）
add_child()	进场景树	✅ 跑
所以 load() 拿到了几乎全部资源层的真相，同时零游戏逻辑执行。这正是我反对 --quit-after 1 的理由：后者会执行 _ready()，而迁移中途的项目必然在 _ready 里崩，产出的 crash 信噪比极低，你根本分不清"场景坏了"还是"某个 _ready 里有个与场景无关的 nil"。

三个必须做的工程细节：

哨兵归因：Godot 的 error 输出是非结构化的散装 stderr。###BEGIN/###END 框住，才能把错误行归属到具体文件。没有这一步，load-only 的输出对 LLM 毫无价值。
崩溃续跑：某个文件能把进程整个带崩。外层脚本记录进度，进程死了就从下一个文件重启，把崩的那个标成 LOAD_CRASH（这本身是最强的信号）。没有续跑机制，一个坏文件会让整个 sweep 只返回一行。
前置依赖：必须在 --editor --import 之后跑。否则纹理缺 .import 产物，会喷出一大片与场景无关的假错误。你的 V3 已经在做了，顺序对上就行。
3.3 它能抓出什么——分三类
① 静态检查抓不到的（load-only 的独有价值）

问题	为什么正则看不见
uid:// 与 path= 不一致 / UID 失效 / UID 重复	UID 真相在引擎的 uid cache 里，不在文本里
资源类型不匹配：属性要 Texture2D，.tres 实际是 Material	需要真实的类型系统
循环资源包含：A 实例化 B，B 实例化 A	需要真实的递归加载图
.import 产物缺失/损坏	在 .godot/imported/ 里，文本不可见
脚本在真实上下文中的编译失败：class_name 注册顺序、跨文件常量/内部类解析	单文件 tree-sitter 只能验语法，验不了跨文件语义
自定义 Resource 的 class_name 与 .tres 头部失配	需要 ClassDB 实时状态
format 版本不兼容 / 二进制 .scn .res	压根不是文本
converter 静默跳过的超大文件里的一切	你也跳过了它们（SKIPPED_OVERSIZE）→ load-only 是这批文件唯一的覆盖手段 ⭐
最后一条特别值得注意：它精确填上了你静态检查里那个已知且诚实记账的覆盖缺口。两个机制的盲区互补，这不是巧合，是设计出来的。

② 与静态检查重叠的（重叠本身是有用的）

ext_resource 悬空、未知节点类型、脚本挂载失败、.tres 缺失。

重叠的价值：如果 load-only 报了某个错，而静态检查是 CLEAN，说明你的静态检查有 bug 或有盲区。把这类不一致单独记进 trace，就是你这套检查器的自我改进回路。

③ 它也抓不到的（别抱幻想）

shader 编译/语义（headless 不编译 shader）、视觉正确性、音频、输入、物理稳态、以及 §1.3 的 F 类数值语义错误（extents→size 差 2 倍）。

3.4 打回还是警告？—— 按可归因性分级，不是按严重性
这是你直接问到的点。我的建议：

load-only 结果	是否 ∈ baseline	处置
错误可映射到 I1~I4 某条规则	新增	⛔ 打回重改。可归因、可复现、可操作
同上	已存在	🟡 WARN + backlog（converter 遗留债，不是 LLM 的错）
独有类错误（UID / 类型失配 / 循环 / import）	新增	⛔ 打回重改，并附引擎原始报错行
同上	已存在	🟡 WARN
LOAD_CRASH（进程死在某文件上）	新增	⛔ 打回——这是最硬的证据
同上	已存在	🟡 WARN + 列入"引擎无法加载"清单
进程整体 timeout / 环境异常 / signal 11 且无法归因到单文件	—	⚪ INFRA_FAILURE，只写 trace，既不打回也不阻塞
核心原则：只在"新增 + 可归因到具体文件"时打回。

理由：打回是昂贵操作（多一轮迭代），必须保证打回的每一条都是 LLM 真的能修的。历史遗留债和环境噪声打回只会让它在无法完成的任务上震荡——正好触发你的 CIRCUIT_OPEN 熔断，白白烧掉一次运行。

同时要给 load-only 单独的重试预算，它不能共用 verify 的 INFRA_FAILURE 熔断计数器。否则一个 flaky 的 sweep 会误熔断整个任务。

四、落地清单（按依赖顺序）
#	做什么	依赖	备注
1	dump_classdb.gd → 引擎类名 + 继承树 JSON	无	一次性，按引擎版本缓存。I2 / I3b 的地基
2	.tscn/.tres 逐行状态机 → scene_refs 表	无	~150 行。注意多行值的 depth 跟踪
3	find-symbol 返回追加 scene_usages + scene_usage_count	2	⭐ 投入产出比最高的一步，直接治"忘记改场景"
4	Layer 1 规则（I0 / I6）	2	零误报。I6 遇 instance 必须 UNRESOLVED
5	Layer 2 规则（I1 / I2 / I3 / I4）	1,2 + codeindex	⭐ 先只做 I4——最高频、现有工具全盲
6	baseline 冻结（converter + import + index 之后）	4,5	delta reward 的前提，不可省
7	Layer 3（I5，codeindex 快照差分）	6	自动推导旧名，零 LLM 配合
8	scene_check --changed-only 暴露给 Agent	4~7	反向索引求受影响场景
9	Gate 强制全量 scene_check + 陈旧性检查	8	不信任 LLM 的自报结果
10	load_sweep.gd + 哨兵归因 + 崩溃续跑	--editor --import	只 load，不 instantiate
11	load-only 结果按 §3.4 分级接入 Gate	10,6	独立重试预算，不共用熔断计数
如果只能做三件事：3（find-symbol 带 scene_usages）+ 5 里的 I4 + 6（baseline delta）。

这三件覆盖了 §1.3 表里频率最高的 A、B、C 三类，而且都是纯静态、零 flaky、可直接接入你现成的 Gate signature 机制。

收束一下三个问题的答案：

进 codeindex——但只在读取层进。 存储用独立 scene_refs（不污染 edges 图语义），find-symbol 的返回里 join 出 scene_usages。你担心的"LLM 忘记改场景"是真问题，但解法是把场景引用摆进它必读的数据结构，不是把边塞进图。converter 跑完后 LLM 仍需动 .tscn，但主力是为自己的重构善后（改函数名→信号连接、移文件→ext_resource、改 class_name），这类违规 100% 是新增的，delta reward 能精确抓住。

5 条规则 = 1 张图 + 3 层规则 + 1 条流水线 + 1 份同构输出。 按依赖分层（文件内自洽 / 跨文件解析 / 时序 delta），误报必须降级为 UNRESOLVED 并计入 coverage。两处调用：Agent 自测（changed-only，给即时 reward）+ Gate 全量（强制跑，不信自报，regression > 0 打回）。reward 用 delta 而非绝对值，靠 converter 后冻结的 baseline 分离历史债。

load-only（只 ResourceLoader.load()，不 instantiate）验的是你的正则原理上看不见的那一层：UID 一致性、资源类型匹配、循环包含、import 产物、跨文件脚本编译、以及你主动跳过的超大文件。按"新增 + 可归因到具体文件"打回，历史债和环境噪声只警告，并且给它独立的重试预算，别让它误触发 verify 的熔断。

要不要我下一步直接给 _on_* 信号连接的 I4 完整实现（含沿 extends 链向上查到引擎类的解析逻辑、以及 UNRESOLVED 的判定边界）？它是这批里唯一"现有工具链完全盲、真实项目高频踩、且实现不到百行"的，先做它能最快验证整套设计值不值。


先做一件最重要的事：撤回一个我说错的判断。

一、§1.3 的证据审查：我的"A 类最高频"是错的
你的质问完全正确，我逐条交代。

1.1 直接回答："converter 的遗留问题里，有需要靠改函数名来解决的吗？"
几乎没有。 converter 只认引擎 API 名字，它的遗留债主要是：不存在 1:1 映射的类/属性（Tween 节点消失、TileMap/TileSet 格式重做）、语义变了但名字对得上（extents→size）、静默跳过的超大文件。这些没有一个是"改个函数名就能解决"的。

我把"LLM 会改函数名"标成最高频，是从"重构型 agent 的一般行为"外推的，不是从 Godot 3→4 的具体错误清单推出来的。这是过度概括，必须降级。

1.2 但"LLM 改名"这条路径没有消失，它的真实驱动源是另外三个
我原来给的理由（"为修错误而重命名"）太含混。换成可验证的机制：

驱动源	机制	Godot 4 里的表现	converter 能修吗	会改什么
D1 · 基类成员遮蔽变成硬错误	Godot 4 禁止脚本成员与原生基类成员同名	var scale / var position 挂在 Node2D 上 → 报错	❌ 需要语义分析，超出文本替换能力	⭐ 改变量名（常常是 @export 变量）
D2 · class_name 全局唯一	4.x 里 class_name 进全局命名空间，重名即报错；且与引擎类重名也报错	两个 class_name Utils	❌	⭐ 改 class_name
D3 · 虚函数签名必须严格匹配	4.x 对 override 的参数类型/数量检查更严	_unhandled_key_input(event: InputEventKey) 报错	部分	改签名（不一定改名）
D4 · 虚函数加下划线前缀	3.x can_drop_data → 4.x _can_drop_data（get_drag_data、EditorPlugin 全套同理）	声明处名字必须变	✅ converter 的 method rename 表覆盖	通常已被修好
结论：真正高频的不是"改函数名"，而是"改变量名（D1）"和"改 class_name（D2）"。

1.3 这个修正反而让场景校验更重要，因为它暴露了一个我漏掉的、更糟的漏洞
D1 改的往往是 @export 变量。而 .tscn 里存的节点属性值长这样：

[node name="Player" type="CharacterBody2D"]
script = ExtResource("1_abc")
move_speed = 320.0        # ← 对应脚本里的 @export var move_speed

如果 LLM 因为遮蔽错误把 @export var scale 改成 move_scale，.tscn 里那行 scale = 2.0 会被 Godot 静默丢弃——不报错、不警告、加载成功、数值回到默认值。 游戏行为坏了，而你的 verify、load-only、--check-only 全部显示 CLEAN。

这比我原先担心的信号孤儿危险得多（信号孤儿至少运行时会喷错）。所以规则表必须加一条，而且它优先级高于我原来吹的 I4：

I7 · 场景属性必须在脚本里有声明
对每个挂了脚本的 node，检查 .tscn 里设置的属性名 ∈（脚本声明的属性 ∪ 沿 extends 链的引擎类属性）。不在 → 该值会被静默丢弃。
1.4 修正后的优先级表（取代上次的 A~H）
排序	场景违规	驱动源	捕获规则	严重性
1	属性静默丢弃	D1	I7	⚠️ 静默，最危险
2	自定义节点类型失效	D2	I2	报错，显眼
3	ext_resource 悬空 / 脚本挂载失效	移动/拆分文件	I1 / I3	报错
4	信号回调孤儿	D3 或少量重命名	I4	运行时报错
5	未知节点类型（成批）	converter 跳过的大文件 / 无映射节点	I2	报错，非 LLM 造成
6	数值语义漂移（extents→size）	converter 设计局限	❌ 测不出来	⚠️ 静默
所以"只做三件事"的推荐要改：I7 > I2 > I1/I3 > I4。 上一轮我让你先做 I4，那是基于错误的频率判断，请以这张表为准。

二、codeindex 里的旁路场景解析：具体实现
2.1 "旁路"的准确含义：同库、不同表、同事务、同 generation
同一个 SQLite 文件（JOIN 零成本、快照天然一致）
├── 主索引（现有，不动）: files / symbols / classes / functions / edges
└── 场景旁路（新增）:     scene_files / scene_nodes / scene_res / scene_refs

三条硬纪律：

绝不往 edges 插场景边 —— call-chain、class-hierarchy 的图语义保持纯净。
共用 generation 列 —— 每次索引重建 +1。所有查询带 generation = current，避免读到半新半旧。
场景解析失败不得让整次索引失败 —— 单文件 try/catch，落 parse_status。
2.2 表结构
sql
CREATE TABLE scene_files(
  scene_id INTEGER PRIMARY KEY, path TEXT UNIQUE, generation INTEGER,
  mtime INTEGER, size INTEGER, content_hash TEXT,
  format INTEGER,                      -- gd_scene format=3 ?
  parse_status TEXT,                   -- OK | MALFORMED | SKIPPED_OVERSIZE | BINARY
  node_count INTEGER
);

CREATE TABLE scene_nodes(
  scene_id INTEGER, node_path TEXT,    -- 归一化全路径 "Player/Sprite2D"
  name TEXT, parent_path TEXT,
  type TEXT,                           -- type="..."，实例化节点为 NULL
  instance_res_id TEXT,                -- instance=ExtResource("x")
  script_res_id  TEXT,                 -- script = ExtResource("y")
  line INTEGER,
  PRIMARY KEY(scene_id, node_path)
);

CREATE TABLE scene_res(                -- ext_resource 声明表（id → path 的解引用字典）
  scene_id INTEGER, res_id TEXT, type TEXT, path TEXT, uid TEXT, line INTEGER,
  PRIMARY KEY(scene_id, res_id)
);

CREATE TABLE scene_refs(               -- ⭐ 核心：一切"指向外部符号"的引用
  scene_id INTEGER, line INTEGER,
  ref_kind TEXT,                       -- 见下表
  target_norm TEXT,                    -- 归一化后的目标（路径 / 类名 / 方法名 / 属性名）
  node_path TEXT,                      -- 引用发生在哪个节点上
  detail TEXT                          -- JSON: {signal, from, to, binds, prop_value_kind, ...}
);
CREATE INDEX idx_refs_target ON scene_refs(generation, target_norm);  -- 正向：符号→场景
CREATE INDEX idx_refs_path   ON scene_refs(generation, ref_kind, target_norm);
CREATE INDEX idx_nodes_script ON scene_nodes(generation, script_res_id);

ref_kind 枚举（7 种，覆盖全部规则的输入）：

ref_kind	target_norm 存什么	服务规则
res_path	res://a/b.gd	I1
node_type	CharacterBody2D	I2
script	脚本 res 路径	I3 / I3b
conn_method	方法名	I4
node_prop	属性名	⭐ I7
parent_path / conn_endpoint	节点路径	I6
string_literal	可疑字符串值（动画名、NodePath 等）	I5（弱）
⭐ 索引 idx_refs_target 是整套设计的引擎。正向查 = "谁引用了 X"（喂 find-symbol）；反向查 = "改了 X 影响哪些场景"（喂 changed-only）。同一个索引，两个方向，这是为什么必须同库。
2.3 实现顺序（每步都可独立测试、独立回滚）
步	内容	验收	风险
S1	纯函数 parser：.tscn → 中间结构。逐行状态机 + 多行值的括号 depth 跟踪	对 20 个真实场景做 golden test；含 instance、editable、超大文件	无（不接触现有代码）
S2	建表 + 写入，挂在现有增量索引流程尾部。只写不读	索引耗时增幅 < 15%；parse_status 分布合理	低。失败就只是多几张空表
S3	两个内部查询函数：refs_of(symbol) / scenes_affected_by(gd_paths)	单元测试	无
S4	⭐ find-symbol 返回追加 scene_usages + scene_usage_count	老字段逐字节不变（加字段是向后兼容的）	低
S5	引擎类清单 JSON（dump_classdb.gd），含继承树与每类属性/方法集	类数、随机抽查	无
S6	规则引擎，按 §1.4 顺序：I7 → I2 → I1/I3 → I6 → I4	每条规则独立开关，可单跑	中（误报风险，见 §3.3）
S7	baseline 冻结 + delta	—	低
S8	scene_outline 工具	—	无
S1~S4 做完就已经拿到了这套设计一半以上的价值（治"LLM 不知道场景引用了它要改的东西"），而且此时还没有任何规则、任何误报风险。建议 S4 之后先跑一轮真实任务看效果，再决定 S6 做几条。

2.4 codeindex 该暴露给 LLM 哪些工具
先直接回答你的问题：scene_refs 不应该是工具，它是表。 把它做成工具会让 LLM 多一次它经常想不起来调的调用——正是你在问题 1 里担心的那种失败。它的内容应该从已有工具的返回里漏出来。

工具	状态	说明
find-symbol	改（加字段）	加 scene_usages[] + scene_usage_count。⭐ 最高价值的一步
search / grep 类	改（加字段）	命中所在文件若被场景引用，加 scene_usage_count 标记
call-chain / class-hierarchy	不动	保持图语义纯净
scene_outline(path)	新增	返回紧凑节点树（名/类型/脚本/连接），替代读 5000 行 .tscn。LLM 真要改场景时必需
scene_check(scope)	新增	规则流水线
scene_refs(target)	不要	已被 find-symbol 吸收
净增 2 个工具。 这是有意的克制：工具越多，LLM 漏调的概率越高；把信息推到它必读的返回里，比给它一个可选工具可靠得多。

三、五条规则是 verifier 还是 gate？
3.1 明确定位：一个引擎，两个调用点，两套严重性策略
它不是 gate 在"禁止修改"的意义上。这点必须说清楚：

永远不要因为场景校验不通过而阻止 LLM 编辑文件。
理由很实在：修一个场景 regression 常常需要先编辑更多文件（比如把变量名改回去要动 .gd）。如果"不通过就禁止改"，会直接死锁。

正确的是：gate 阻塞的是"任务完成"，不是"文件写入"。

调用点 A：主循环	调用点 B：收尾门
角色	reporter / reward	gate
范围	changed-only	全量 + load sweep
谁触发	LLM 调 + 规则强制注入（见 §4.4）	固定逻辑，LLM 无法触发也无法跳过
效果	生成报错文本给 LLM	regression > 0 → 打回，继续循环
阻塞编辑	❌ 从不	❌ 从不
3.2 I5 是"零成本顺带"吗？——不是，我上次说得太轻巧
拆成两半就清楚了：

I5a（结构化位置）	I5b（自由文本扫描）
做什么	消失的符号，查 idx_refs_target 精确命中	消失的符号，grep 全部 .tscn 文本
成本	⭐ 接近零（一次索引查询）	全量文本扫 + 误报过滤
误报	无	高：update、size、state 这类短名到处命中
额外依赖	需要持久化上一代 symbol 集合（几十 KB）	同左
覆盖	与 I1~I4/I7 高度重叠	独有：动画名、NodePath、StringName 字面量
建议：I5a 做（顺手），I5b 推迟，且做出来也只能是 WARN，绝不进硬 reward。 我上次把 I5 整体说成"聪明且免费"，那是把 I5a 的成本和 I5b 的价值混在一起讲了，不成立。

3.3 统一流水线：一次解析，一张图，七条规则
angelscript
scene_check(scope, rules) →

 阶段 0  解析（带缓存）
   for f in scope:
       if cache[(path, mtime, size)] 命中: 取内存图
       else: 解析 → 存 scene_* 表 → 入缓存
       parse_status != OK → 记 coverage，跳过后续规则

 阶段 1  组图（纯内存，无 IO）
   解引用 ExtResource("id") → 真实路径
   节点树：name + parent → 全路径
   join codeindex: 脚本路径 → class / extends / functions / properties / has_error
   载入引擎 ClassDB JSON（进程级缓存，跨调用复用）

 阶段 2  规则（同一张图上跑，顺序 = 依赖顺序）
   I0 格式完整 ─┐
   I6 路径自洽 ─┴─ Layer1，零外部依赖，零误报
   I7 属性存在 ─┐
   I2 类型已知  │
   I1 引用不悬空│── Layer2，需 codeindex + ClassDB
   I3 脚本有效  │
   I4 信号方法 ─┘
   I5a 消失符号 ─── Layer3，需上一代快照
   短路: I3 失败(脚本不存在/有语法错) → 该节点的 I7/I4 判 UNRESOLVED，不报错
                                        ← ⭐ 防雪崩的关键

 阶段 3  分类
   for v in violations:
       v.sig ∉ baseline → REGRESSION   (硬信号)
       v.sig ∈ baseline → PRE_EXISTING (只报数)
   FIXED = baseline − current

 阶段 4  输出（signature_set 与 verify 同构 → 直接复用现有震荡/无进展检测）

性能三件套：解析缓存按 (path, mtime, size)；ClassDB JSON 进程级常驻；changed-only 把 314 个场景缩到个位数。全量重扫也只有几百毫秒级，性能不是瓶颈，误报才是。

⭐ 阶段 2 里那条短路规则是整个流水线最重要的一行。 迁移中途一定有脚本还带语法错，如果不短路，一个坏脚本会让挂它的那个节点喷出 20 条 I7 + 5 条 I4 假错误，LLM 两轮之后就学会忽略 scene_check 的全部输出——那你就永久失去这个信号了。

3.4 复用 vs 新建
复用	新建
SQLite 连接 / 增量索引调度 / mtime 缓存	.tscn parser（S1）
classes/functions/edges(extends) 表	scene_* 四张表
signature_set 震荡 & 无进展检测	规则引擎 + baseline 存储
Gate 框架、INFRA_FAILURE 熔断模式	ClassDB dump 脚本
四、diff 从哪来、regression 是什么、工具签名、收尾门
4.1 不要读 diff，读 edit 工具的日志
你自己给了答案：edit 是唯一能写文件的事务性工具。那它在 commit 的瞬间就精确知道改了哪些文件——这是比任何事后 diff 都更可靠的信息源，而且是免费的。

sql
CREATE TABLE edit_journal(
  seq INTEGER PRIMARY KEY, ts INTEGER, generation INTEGER,
  path TEXT, op TEXT,        -- modify | create | delete | rename
  old_path TEXT
);

edit 的 commit 里追加一行（同事务，保证"文件改了但日志没记"不可能发生）。

三级降级，保证永不失效：

级	来源	何时用
1	edit_journal（权威）	正常
2	索引 mtime/hash 比对	日志缺失 / 外部工具改了文件（converter！）
3	全量	收尾门、或前两级不可信
⭐ 第 2 级必须存在：官方 converter 不走 edit 工具，它改了几百个文件。baseline 建立时必须用第 2 或第 3 级。

受影响场景的计算（一跳反查，毫秒级）：

sql
-- 直接改的场景
SELECT path FROM scene_files WHERE path IN (:changed)
UNION
-- 引用了被改 .gd 的场景
SELECT sf.path FROM scene_refs r JOIN scene_files sf USING(scene_id)
WHERE r.generation = :g AND r.ref_kind IN ('res_path','script')
  AND r.target_norm IN (:changed_gd)
UNION
-- class_name 变动的脚本 → 用它作自定义 node type 的场景
SELECT sf.path FROM scene_refs r JOIN scene_files sf USING(scene_id)
WHERE r.ref_kind='node_type' AND r.target_norm IN (:changed_class_names);

第三条 UNION 别忘，它对应 §1.4 的 2 号高频项。

4.2 regression 的精确定义
gherkin
signature = rule_id | scene_path | 稳定定位符 | 目标
  I7: "I7|res://l1.tscn|Player|move_speed"
  I4: "I4|res://l1.tscn|Player→HUD|died|_on_player_died"
❌ 不含行号（行号会随无关编辑漂移，导致同一违规被判成新 regression）

baseline = 在 converter + --editor --import + 首次建索引 之后，
           LLM 第一次编辑之前，全量跑一次 scene_check 得到的 signature 集合
           → 落盘，此后只读，永不更新

REGRESSION   = current ∖ baseline     ← 100% 由 LLM 造成 → 硬负反馈
PRE_EXISTING = current ∩ baseline     ← converter 遗留债 → 只报数
FIXED        = baseline ∖ current     ← 正向进展

与 baseline 的关系一句话：baseline 是"LLM 进场前的原罪清单"，regression 是"LLM 自己新造的罪"。只追后者。 这样 LLM 看到的输出里 0 条噪声——这是它愿意相信这个工具的唯一前提。

⭐ "不含行号"这一条不能省。 否则 LLM 在文件开头加一行注释，下游所有违规行号 +1，全部被误判成 regression，你的硬 reward 瞬间变成纯噪声。

4.3 工具签名：一个，用 scope 区分
reasonml
scene_check(
  scope: "changed" | "all" | list[path]   = "changed"
  rules: list[str] | "default"
  include_pre_existing: bool = false      # 主循环 false（干净），收尾门 true（写报告）
)

理由：两套签名 = 两套代码路径 = 主循环通过、收尾门失败的诡异 bug。收尾门只是用 scope="all" 调同一个函数。

4.4 收尾门做成固定逻辑：可以，而且必须
Gate.can_finish():
    verify(all) == CLEAN                                      # 已有
 && scene_check(scope="all").regression == 0                  # Gate 自己跑，不信 LLM 自报
 && load_sweep().new_attributable_failures == 0
 → 任一不满足：把结果注入下一轮 observation，继续循环（不阻塞编辑）

关键：Gate 不读 LLM 报上来的结果，Gate 自己跑。 LLM 在主循环里跑 scene_check 是因为这对它有好处（少走弯路）；Gate 跑是因为正确性不能依赖它的自觉。两个动机分开，设计才稳。

再加一条强制注入，治"LLM 干脆不调"：编辑涉及 @export 变量 / class_name / 文件重命名 / func 签名时，harness 自动在下一轮 observation 尾部附上 changed-only 结果，不等它调用。

五、MCP 拓扑：verifier 是独立 stdio server，场景校验放哪
5.1 三个选项
方案	做法	评价
A ⭐	场景工具放 codeindex server；verifier 保持只管脚本；Gate 在 orchestrator 侧组合两者	✅ 推荐
B	写一个聚合 proxy server，暴露单个 verify，内部 fan-out 到两个 server	⚠️ 多一跳、两个 server 生命周期耦合、错误归因变模糊
C	verifier 内部 shell 调 scene-check CLI	❌ 最差：CLI 每次冷启动、重复打开 DB、缓存全丢、可能读到不一致快照
A 的决定性理由：场景校验的输入是 scene_refs ⋈ codeindex，它必须和索引在同一个进程、同一个 DB 连接、同一个 generation。搬到 verifier 里就意味着跨进程读别人的 SQLite，你会立刻撞上快照一致性和缓存失效问题。数据在哪，计算就在哪。

5.2 你担心的"语义上 verify 应该管场景" —— 用 orchestrator 的结果后处理解决，成本极低
你不需要合并 server。harness 拿到 verify 的返回后，在返回文本尾部追加一段：

excel
=== verify: CLEAN (0 errors) ===

⚠️ 场景状态未同步：自上次 scene_check 后有 3 个文件被修改。
   建议调用 scene_check(scope="changed")。
   受影响场景：res://levels/l1.tscn, res://ui/hud.tscn

效果等同于"verify 同时校验了场景"，但零架构改动、零耦合。 orchestrator 本来就看得见 edit_journal 的时间戳和 scene_check 的上次运行时刻，判断"陈旧"是一次时间戳比较。

5.3 "破坏自动发现"这个担忧可以放下
绝大多数 harness 里，工具清单是你注入给模型的，不是模型自己爬的。所以加一个 server / 加两个工具，都不构成破坏。真正的成本从来不是发现机制，而是 LLM 的注意力预算——这才是我坚持"只新增 2 个工具"的原因。

六、load-only 到底是什么
六.0 先纠正术语：Godot 没有 --load-only 这个 flag
我用了一个不存在的名字，对不起。官方 CLI 只有 --check-only（配合 --script 只做语法解析）、--import、--quit、--quit-after、--headless、-s/--script。

"load-only" 是我给一个模式起的名字，不是 flag：

用 --headless -s 跑一个自己写的 MainLoop 脚本，对全部资源只调 ResourceLoader.load()，绝不 instantiate()、绝不 add_child()。
6.1 为什么这能避开你踩过的 --quit-after 崩溃坑
命令	实际做的事	会执行游戏逻辑吗	你的经历
--check-only -s x.gd	单文件语法解析	❌	已用，很稳
--import	导入资源产物	❌	已用，很稳
--quit-after N	跑主场景 N 帧：实例化 → 进树 → _ready → _process	✅ 全跑	⛔ 崩了，被你禁用
load sweep（推荐）	反序列化 + 递归解析依赖 + 编译脚本 + 构造 SubResource	❌ 不跑（_ready/_process 都不触发）	未试
⭐ --quit-after 崩溃是必然的，不是环境问题：迁移中途的项目，_ready() 里几乎一定有半迁移的代码。它测的是"游戏能不能跑"，而你现在只想知道"资源结构对不对"。load sweep 精确地只要后者——拿到引擎级的资源层真相，同时零游戏逻辑执行。

6.2 实现
gdscript
# tools/load_sweep.gd   —— godot --headless -s tools/load_sweep.gd
extends MainLoop     # 必须是 MainLoop/SceneTree 实现（-s 的硬性要求）

func _initialize():
    var list := FileAccess.open("user://sweep_list.txt", FileAccess.READ)
    var start := int(OS.get_environment("SWEEP_RESUME_AT"))
    var i := 0
    while not list.eof_reached():
        var p := list.get_line().strip_edges()
        if p == "" or i < start: i += 1; continue
        print("###BEGIN %d %s" % [i, p])          # 哨兵：错误归因
        var r = ResourceLoader.load(p, "", ResourceLoader.CACHE_MODE_IGNORE)
        print("###END %d ok=%s" % [i, r != null])
        r = null
        i += 1

func _process(_d): return true   # 立即结束

三个必须做的工程细节（缺任何一个，产出就没用）：

###BEGIN/###END 哨兵 —— Godot 的错误是非结构化散装 stderr。没有哨兵框住，你无法把错误行归属到文件，输出对 LLM 价值为零。
崩溃续跑 —— 某个文件能把进程整个带崩。外层脚本读最后一个未闭合的 ###BEGIN，标 LOAD_CRASH，用 SWEEP_RESUME_AT=i+1 重启。没有这个，一个坏文件会让整次 sweep 只返回一行。
必须在 --import 之后跑 —— 否则纹理缺 .import 产物，喷一大片与场景无关的假错误。
6.3 它能给出哪些 reward
✅ 独有价值（静态解析原理上看不见）：

信号	为什么正则做不到
uid:// 失效 / 与 path= 不一致 / UID 重复	UID 真相在引擎 uid cache，不在文本里
资源类型不匹配（属性要 Texture2D，实际给了 Material）	需要真实类型系统
循环资源包含	需要真实递归加载图
.import 产物缺失/损坏	在 .godot/imported/，文本不可见
脚本在真实上下文的编译失败（class_name 注册顺序、跨文件常量/内部类）	tree-sitter 单文件只能验语法，验不了跨文件语义
二进制 .scn/.res	根本不是文本
⭐ SKIPPED_OVERSIZE 那批超大文件里的一切	你的静态扫描主动跳过了它们 → load sweep 是这批文件唯一的覆盖手段
最后一条特别值钱：它正好填上你静态检查里那个已诚实记账的覆盖缺口。两个机制的盲区互补，这是设计出来的，不是巧合。

🔁 与静态检查重叠（重叠本身有用）： ext_resource 悬空、未知节点类型、脚本挂载失败。

若 load sweep 报错而 scene_check 是 CLEAN → 说明你的规则有 bug 或盲区。把这类不一致单独记进 trace，就是这套检查器的自我改进回路。
❌ 它也抓不到（别抱幻想）： shader 编译（headless 不编）、_ready 里的运行时错误、视觉/音频正确性、以及 §1.4 的 6 号"数值语义漂移"（extents→size：语法对、引用对、能加载，就是数值差 2 倍）。

6.4 打回还是警告：按可归因性分级，不按严重性
结果	∈ baseline？	处置
可归因到具体文件的加载失败	新增	⛔ 打回（可复现、可操作）
同上	已存在	🟡 WARN + backlog（converter 遗留债）
LOAD_CRASH	新增	⛔ 打回（最硬的证据）
同上	已存在	🟡 WARN + "引擎无法加载"清单
进程整体 timeout / 无法归因到单文件	—	⚪ INFRA_FAILURE，只写 trace，不打回不阻塞
原则：只在"新增 + 可归因到具体文件"时打回。 打回是昂贵操作（多烧一轮），必须保证每一条 LLM 真能修。历史债和环境噪声打回只会让它在不可完成的任务上震荡，正好触发你的 CIRCUIT_OPEN，白烧一次运行。

⭐ load sweep 必须有独立的重试预算，不能共用 verify 的 INFRA_FAILURE 计数器，否则一次 flaky sweep 会误熔断整个任务。

七、收束
先撤回： §1.3 我说"LLM 改函数名"是最高频，这是从 agent 一般行为外推的，没有 Godot 3→4 的证据支持，converter 遗留债里也确实没有靠改函数名能解决的问题。真实驱动是 D1 基类成员遮蔽（改 @export 变量名）和 D2 class_name 全局唯一（改类名）。这个修正反而暴露了一个更危险、我上次漏掉的漏洞：@export 改名导致 .tscn 属性值被静默丢弃，全套现有检查都是 CLEAN。所以新增 I7 并把它排到第一位，优先级取代我上次推荐的 I4。

七个实现决策：

场景解析同库、独立表、共用 generation，edges 绝不污染；idx_refs_target 一个索引同时服务"谁引用我"和"我影响谁"。
只给 LLM 加 2 个工具（scene_check / scene_outline）；scene_refs 是表不是工具，它的内容从 find-symbol 的 scene_usages 漏出来——把约束放进它必读的返回里，别放进它可选调用的工具里。
规则 = reporter + gate 双身份，但永不阻塞编辑，只阻塞"任务完成"。一次解析、一张图、七条规则、按依赖排序；脚本有错就短路成 UNRESOLVED，防假错误雪崩——这是保住 LLM 信任的生命线。
I5 不免费：I5a（结构化查询）顺手做，I5b（文本 grep）推迟且只能是 WARN。
diff 来自 edit_journal，不是 git；但必须保留 mtime 降级级，因为 converter 不走你的 edit 工具。signature 不含行号，否则加一行注释就让硬 reward 变成纯噪声。
MCP 拓扑选 A：场景工具留在 codeindex（数据在哪计算在哪），verifier 不动；"语义统一"用 orchestrator 对 verify 返回值做后处理追加提示来实现，零架构改动。Gate 自己跑全量，不信 LLM 自报。
--load-only 不存在，是我编的名字；实际是 --headless -s + 自写 MainLoop + 只 ResourceLoader.load()。它避开了你踩过的 --quit-after 崩坑（那是必然崩，因为它跑 _ready），并且是你那批超大跳过文件唯一的覆盖手段。
如果只做三件事：find-symbol 带 scene_usages（S1~S4）→ I7 → baseline delta。三件都是纯静态、零 flaky、直接接你现成的 Gate signature 机制，而且覆盖了修正后频率表的第 1 名。

要不要我下一步把 I7 完整写出来（含 @export 属性从 codeindex 取、沿 extends 链爬到 ClassDB 属性集、instance= 场景的属性覆盖如何判 UNRESOLVED、以及哪些内置属性必须白名单豁免）？它现在是优先级第一，且是唯一能捕获"静默数据丢失"这类 verify/load sweep 双盲区的规则。

# 一、为什么不给 Bash？grep / read / glob 不也是 Bash 命令吗？




你的质疑完全合理：`grep`、`read`、`glob` 这三个工具的**实现**确实就是 `rg` / `sed -n` / `find`。所以区别不在"能不能做这件事"，而在**调用面的性质**。




## 1.1 核心区别：白名单 vs 图灵完备




|维度|`grep` / `read` 工具|Bash|
|---|---|---|
|可能的行为集合|**有限且可枚举**。参数 schema 固定，实现里写死 `rg --json -e <pattern>`|**无限**。`$(...)`、`;`、`\|`、`>`、`&&`、`eval`、`python -c`、`curl`|
|副作用|**可证明为只读**（进程只有 read syscall 路径）|**不可判定**。你无法靠静态检查确定一条 shell 命令是否写盘|
|失败模式|结构化 error code|任意退出码 + 任意 stderr|
|审计|每次调用 = 一条 `{tool, args, result}` 记录|一条 `bash("...")` 记录，参数是**不透明字符串**|




最关键一点：**`grep` 是 `bash` 的一个真子集，但"允许 grep"不等于"允许 bash"**。给了 bash，你不是多给了 grep，你是把 LLM 的动作空间从"有限集合"扩成了"任意程序"。




这在安全领域叫 **capability（能力）vs. shell（外壳）**。给 capability 你能推理系统性质，给 shell 你只能事后观测。




## 1.2 对你这个项目：三个具体的、会毁掉你论文的后果




### 后果 A：写通道旁路 → fix_guard 直接作废




这是**致命的**。你的整个"防假修复"设计建立在一个不变式上：




> **所有对工作区的写入都经过 `edit` 工具，因此都经过 fix_guard。**




有了 bash，LLM 可以：




```bash
sed -i 's/func compute/func compute_old/' res/foo.gd   # 绕过 guard
python3 -c "open('foo.gd','w').write('extends Node\n')" # 整文件清空
git checkout -- .                                      # 篡改你的审计链
echo "pass" >> foo.gd                                   # 判据4 看不见
```




而且这**不需要 LLM 有恶意**。它只是在"最省事地让 verify 变绿"这个目标下做局部最优。`sed -i` 对模型来说是完全自然的工具选择——训练数据里满地都是。




一旦发生一次，你的实验结论就从"假修复率 X%"退化成"**被我们的 guard 抓到的假修复率 X%，未抓到的未知**"。审稿人会直接问这个。




### 后果 B：你自己的设计哲学不一致




你在 verify 上做的最漂亮的决策是：




> schema 里故意没有 `session_id`、`phase`、`unified_diff`；**Agent 不能拼 Godot argv，不能点名 V1/V2/V3**；白名单只有三条命令，`--debug` 明确不进白名单（会 signal 11）。




这个决策的价值是：**verify 的能力边界是可声明、可验证的**。你能写"本工具不会做 X"并且这是真的。




如果同一个 Agent 手里有 bash，那它可以自己跑：




```bash
godot --headless --path . --debug --check-only   # 你排除的 signal 11 路径
godot --headless --import                        # 你排除的不带 --editor 的 import
```




你排除 `--debug` 是因为实测会崩。LLM 不知道，它会试。于是你精心设计的白名单变成**建议**而非**约束**，而 `INFRA_FAILURE` / `CIRCUIT_OPEN` 的计数开始被工具外的崩溃污染。




**一个系统的能力边界取决于最宽的那个入口。** 给了 bash，最宽的入口就是 bash，verify 的所有边界声明都降级为"我们建议的用法"。




### 后果 C：verify 的 caveats 契约被破坏




你的 verify 返回 `untrusted_files`、`class_cache_stale`、`probe_incomplete`，语义是"这些文件我不敢保证"。这个契约成立的前提是**工作区状态只由 intake + edit 改变**，所以 verify 的 COLD/WARM 判定、快照 diff、V3 触发表都是准确的。




bash 一旦动了文件而没走 edit：




- 快照 diff 算出的 `patched_files` 是错的 → `FILE_STUCK_WARN` 失效
- V3 触发表可能漏触发（改了 `.tres` 但快照上一轮已拍）→ `shader_checked` 说谎
- codeindex 的库没 sync → `find_symbol` 返回陈旧行号 → LLM 下一个 patch 基于幻觉




## 1.3 那 glob 为什么要合并进 grep，而不是单独开一个？




因为 **rg 本身就是 glob + grep 的合体**：




```
rg --files -g "**/*.tscn"              # 纯 glob（列文件）
rg -g "**/*.tscn" "KinematicBody"      # glob + 内容匹配
```




单独开 `glob` 工具只是给 LLM 多一个决策点（"我该用 glob 还是 grep？"），没有增加任何能力。**一个 tool + `pattern=None` 退化为列文件**，schema 更小、prompt 更短、路由歧义更少。这和你把 V1/V2/V3 藏进 `kind` 是同一个手法。




## 1.4 那 `read` 为什么必须单独存在，不能用 grep 代替？




因为它们的**输出契约根本不同**：




||grep|read|
|---|---|---|
|输出|稀疏、不连续的匹配行|**连续区间，带绝对行号**|
|用途|定位（我该看哪）|生成 patch 的锚点（原文长什么样）|
|对 edit 的作用|无|**决定 patch 能否 apply 成功**|




`edit` 的成功率几乎完全取决于 LLM 手里有没有**逐字正确的原文**。grep 带 `-C 3` 也不行——上下文窗口边界不可控、多个 hunk 会交叠、缩进可能被截断。GDScript 是**缩进敏感语言**，锚点差一个 tab 就 apply 失败。




所以 `read` 不是"方便"，是 `edit` 的**前置依赖**。




## 1.5 如果你坚持要 bash，最低限度的安全形态




我不推荐，但给你一个折中方案备选：




```
bash_ro(command: str)
  # 1. shlex 解析，拒绝: ; | & > >> < $( ) ` && || eval exec
  # 2. argv[0] 必须 ∈ {rg, fd, sed, awk, head, tail, wc, cat, jq}
  # 3. sed/awk 禁止 -i / -i'' / "w" 命令
  # 4. 所有路径参数 realpath 后必须在 workspace 内（防 ../../）
  # 5. 禁止 godot / git / python / curl / uv
  # 6. 只读挂载检查（如果跑容器：workspace 挂 ro，edit 走单独的 rw 通道）
```




你会发现：**写完这个白名单，你花的工程量比直接写 3 个结构化工具更大，而且能力还更弱**（因为要禁掉管道，awk/sed 的表达力就没了）。这就是为什么主流 agent 框架最终都收敛到结构化工具而不是受限 shell。




**结论：不给 bash。这不是安全洁癖，这是让你的"假修复率"这个数字能成立的唯一方式。**




---




# 二、`edit` 的 apply 过程：diff 从哪来？




你问到了点子上，而且这里我要**修正上一轮的说法**。




## 2.1 三种候选 wire format




|方案|LLM 输出什么|问题|
|---|---|---|
|**A. 整文件重写**|完整新文件内容|① **laziness**：模型会写 `# ... 其余代码不变 ...` 然后你真的把代码删了；② token 成本随文件长度线性增长；③ **爆炸半径无法判定**——整文件都是"改动"，fix_guard 判据 1 失效|
|**B. 真·unified diff（带行号）**|`@@ -142,7 +142,9 @@` + 上下文|LLM **数不准行号**。它要同时算旧行号、新行号、hunk 长度。任何一个错，`git apply` 直接拒。实践中失败率高得离谱|
|**C. 锚定替换（anchored replace）**|`old_string` / `new_string`，**不带行号**|要求 `old_string` 在文件中唯一，否则歧义|




## 2.2 实证数据指向一个混合方案




Aider 做过一个专门测 laziness 的 benchmark，结论很有意思：




- SEARCH/REPLACE 格式：GPT-4 Turbo 得分 20%，12 个任务出现"偷懒注释"
- **unified diff 格式：61%，只有 4 个任务偷懒**




但关键细节在这句：




> "Aider tells GPT **not to include line numbers**, and just interprets each hunk from the unified diffs **as a search and replace operation**."




也就是说，**Aider 所谓的 "unified diff" 其实是 B 的外形 + C 的语义**：




- 用 diff 的 `-` / `+` / 空格前缀语法（模型在训练数据里见过海量 diff，格式熟悉度高）
- **但不要行号**（避开模型不会算数的短板）
- 服务端把每个 hunk 当"上下文 + `-` 行 = 要找的文本，上下文 + `+` 行 = 要换的文本"来做搜索替换




而且 diff 形状本身**降低偷懒**——因为 `-` / `+` 的逐行结构让"省略一段"在语法上显得不自然，而整文件重写里省略一段太容易了。




**这对你直接相关**：laziness 就是 fix_guard 判据 4 要抓的东西。**wire format 的选择本身就在影响你的假修复率**。选对格式，你在源头上就少了一批假修复。




## 2.3 我建议的 `edit` schema




```python
edit(
  kind: "patch" | "create" | "revert",




  # kind="patch"
  file: str,                    # "res://scripts/player.gd" 或相对路径
  hunks: [ {
      context_before: str,      # 0~3 行，原文逐字
      remove: str,              # 要删的行（逐字，含缩进）
      add: str,                 # 要加的行
      context_after: str,
  } ],
  # —— 没有任何行号字段 ——




  # kind="create"
  content: str,




  # kind="revert"
  to_commit: str | None,        # None = 回退上一次 edit




  # 可选：豁免声明（见第四节）
  declared_scope: [str] | None, # 声明本次要跨到哪些文件/符号
  rule_id: str | None,          # 来自 retrieve 的 A 层规则 id
  justification: str | None,
)
```




## 2.4 服务端 11 步流水线




这是**全部新增工程量的核心**，我逐步写清楚：




```
┌─ 0. 前置检查 ────────────────────────────────────────┐
│ • 工作区必须 clean（git status --porcelain 为空）      │
│   不 clean → ToolError: DIRTY_WORKTREE                │
│   （说明上一轮事务没收尾，或有人绕过了 edit）           │
│ • file 必须在 workspace 内（realpath 防 ../）          │
│ • 扩展名白名单：.gd .tscn .tres .gdshader .godot .cfg  │
└───────────────────────────────────────────────────────┘
          ↓
┌─ 1. 锚定（anchoring）────────────────────────────────┐
│ 对每个 hunk：                                         │
│ needle = context_before + remove + context_after       │
│                                                       │
│ ① 精确匹配 needle → 命中次数 n                        │
│    n == 1  → 拿到绝对行号，成功                        │
│    n == 0  → 降级 ②                                   │
│    n >  1  → 返回 AMBIGUOUS_ANCHOR + 所有候选行号，     │
│              要求 LLM 补更多 context。不写盘            │
│                                                       │
│ ② 归一化重试：行尾空白 strip、CRLF→LF、                │
│    tab/space 等价（GDScript 混用很常见）               │
│                                                       │
│ ③ 模糊匹配：difflib.SequenceMatcher ratio > 0.92       │
│    命中 → 接受但打 warning: FUZZY_ANCHOR               │
│    不命中 → ANCHOR_NOT_FOUND + 返回最相似的 3 个片段    │
│              （带真实行号，让 LLM 能自纠）              │
└───────────────────────────────────────────────────────┘
          ↓
┌─ 2. hunk 冲突检测 ──────────────────────────────────┐
│ 同一次调用的多个 hunk 行区间不得交叠 → 交叠则拒        │
└───────────────────────────────────────────────────────┘
          ↓
┌─ 3. 内存中构造新内容 ───────────────────────────────┐
│ new_text = 按行号从后往前替换（避免行号漂移）          │
│ 【此刻还没有任何文件被写】                             │
└───────────────────────────────────────────────────────┘
          ↓
┌─ 4. 生成规范 unified diff ─────────────────────────┐
│ difflib.unified_diff(old_lines, new_lines, n=3)       │
│ → 这是服务端生成的、行号一定正确的 patch              │
│                                                       │
│ 为什么还要生成它？三个理由：                           │
│  ① fix_guard 判据 1 需要 hunk 的真实行号              │
│  ② 你已经有 parse_unified_diff（V3 触发表 / Gate 用） │
│  ③ 审计：它是这次改动的规范化物证，进 trace_store     │
└───────────────────────────────────────────────────────┘
          ↓
┌─ 5. fix_guard（落盘前，见第四节）──────────────────┐
│ 输入：udiff + old_text + new_text + 本轮 verify 根因  │
│ verdict = pass | warn | reject                        │
│ reject → 【不写盘、不 commit、不计 verify 轮次】       │
│          返回 violations[]，LLM 可自纠                 │
└───────────────────────────────────────────────────────┘
          ↓
┌─ 6. git apply --check（dry run）──────────────────┐
│ 确认 patch 与磁盘状态一致（防 TOCTOU）                │
└───────────────────────────────────────────────────────┘
          ↓
┌─ 7. git apply --index ─────────────────────────────┐
│ 同时更新工作树和 index。                               │
│ ★ 不加 --reject → 默认全 patch 原子性（见第三节）     │
└───────────────────────────────────────────────────────┘
          ↓
┌─ 8. 语法后置检查（廉价，可选但强烈建议）────────────┐
│ tree-sitter 对新内容 parse                            │
│ CST has_error → 立刻 revert，返回 SYNTAX_BROKEN        │
│ 理由：你的 codeindex 对 has_error 文件会整文件作废，   │
│       让它落盘 = 主动制造符号表空洞                    │
└───────────────────────────────────────────────────────┘
          ↓
┌─ 9. git commit ────────────────────────────────────┐
│ message 编码审计信息（见第三节 3.6）                   │
│ → 得到 commit sha = 新的事务点                         │
└───────────────────────────────────────────────────────┘
          ↓
┌─ 10. codeindex sync <file> ────────────────────────┐
│ 绕过 500ms 防抖，单事务立刻重建                        │
│ 保证下一次 find_symbol 不是陈旧数据                    │
└───────────────────────────────────────────────────────┘
          ↓
┌─ 11. trace_store 落盘 ─────────────────────────────┐
│ {round, file, patch_hash, guard_verdict, commit, ...} │
└───────────────────────────────────────────────────────┘
```




## 2.5 回答你的原问题




> diff 是根据两次 LLM 修改的文件计算出来的，还是 LLM 直接生成 diff？




**都不是，是第三种**：




- LLM 生成的是 **hunk 形状的锚定替换指令（无行号）**——对模型自然，格式熟悉度高，不用算数
- **服务端做锚定**，把锚点解析成真实行号
- **服务端用 difflib 生成规范 udiff**——行号一定正确，`git apply` 一定能吃
- 再交给 git 落盘




> 这个对 LLM 修改代码来说会不会不自然？




不会，而且比另外两种都自然：




- 比整文件重写自然：不用重复输出没改的几百行
- 比带行号 udiff 自然：不用算行号（这是模型的已知短板）
- 锚定失败时，服务端返回**带真实行号的相似候选**，LLM 第二次几乎必中




`context_before/after` 就是"哪一处"的自然表达，和人读 diff 的方式一致。




---




# 三、git 的事务机制：它到底怎么保证原子性？




先说清一件事：**git 不是 ACID 数据库，没有通用事务**。但它有三个**原子原语**，组合起来足够支撑你要的事务语义。




## 3.1 原语一：对象库是 content-addressed + 不可变




blob / tree / commit 的文件名 = 内容的 SHA。所以：




- 写对象**天然幂等**：写两次结果一样，不存在"写坏一半"
- 对象**永不原地修改**
- 实现上仍是"写临时文件 → `rename(2)` 就位"




意义：**历史数据永远不会被破坏**。你的 baseline commit 一旦生成，物理上不会被后续操作损坏。




## 3.2 原语二：lockfile API（`O_CREAT|O_EXCL` + 原子 rename）




对于**有固定名字**的可变文件（`index`、`refs/heads/main`、`packed-refs`），git 走统一的 lockfile 协议：




```
1. open("index.lock", O_CREAT | O_EXCL)   ← 互斥：已存在则失败
2. 把新内容完整写进 index.lock
3. rename("index.lock", "index")          ← 提交：POSIX 保证原子
```




`rename(2)` 的原子性意味着：**任何并发读者看到的，要么是完整旧内容，要么是完整新内容，绝无中间态**。




而且 git 注册了 `atexit(3)` + 信号处理器，进程异常退出时自动清理残留 lockfile。




> 这个机制你其实已经在用了——verify 的工作区 flock 是同一思路。




## 3.3 原语三：ref transaction（两阶段提交）




`git update-ref --stdin` 支持显式事务动词：




```
start      # 开始事务
update refs/heads/main <new> <old>
update refs/heads/wip  <new> <old>
prepare    # 为所有排队的 ref 创建 lockfile；任一锁失败 → 整个事务 abort
commit     # 全部提交
abort      # 全部回滚，释放锁
```




语义是：**"如果所有 ref 都能同时锁住且 old-oid 匹配，则全部执行；否则一个都不执行。"** 这是真正的 all-or-nothing。




而且"事务在会话结束时若无显式 commit 则自动 abort"——**默认安全**。




（注意文档的诚实说明：并发读者仍可能看到修改的子集。所以这是**写者之间的原子性**，不是完整的快照隔离。对你的单 Agent 场景足够。）




## 3.4 原语四（最直接相关）：`git apply` 默认就是全或无




man page 原话：




> "**For atomicity, `git apply` by default fails the whole patch and does not touch the working tree when some of the hunks do not apply.** This option (`--reject`) makes it apply the parts of the patch that are applicable..."




**这就是你要的语句级事务，白送的。**




所以：




- ✅ `git apply patch` — 全或无
- ❌ `git apply --reject patch` — **绝对不要用**。它会半截应用 + 留 `.rej` 文件，把工作区搞成不一致中间态
- ⚠️ `git apply --3way` — 冲突时会**留 conflict marker 在文件里**。对 GDScript 来说 `<<<<<<<` 会让文件变成语法垃圾。建议**不用**，或者用了之后强制跑第 8 步语法检查并 revert




## 3.5 组装成你的事务模型：三层回滚粒度




```
会话级         intake_baseline (commit B0)
                    │
轮级           round 1 → commit R1 ──┐
                    │                 │ git reset --hard R1
轮级           round 2 → commit R2 ──┘
                    │
语句级         edit 调用 → git apply（全或无，失败时磁盘未动）
```




|层级|触发条件|操作|成本|
|---|---|---|---|
|**语句级**|hunk 不匹配 / guard reject|什么都不做（git apply 本就没动盘）|**零**|
|**轮级**|verify 显示根因变多、或 `OSCILLATION_ESCALATE`|`git reset --hard <上一轮 sha>` + `git clean -fd -e .godot` + `codeindex sync` 受影响文件|低|
|**会话级**|`CIRCUIT_OPEN` / 放弃|`git reset --hard B0`，或直接删工作区重跑 intake|中|




## 3.6 具体实现：`edit` 的事务代码骨架




```python
def edit_apply(file, hunks, ...):
    # ---- BEGIN TRANSACTION ----
    if run("git status --porcelain").strip():
        raise ToolError("DIRTY_WORKTREE")          # 前置不变式




    base_sha = run("git rev-parse HEAD").strip()   # 回滚点




    old_text = read(file)
    new_text, udiff = anchor_and_build(file, hunks, old_text)   # 纯内存




    verdict = fix_guard(udiff, old_text, new_text, cur_root_causes)
    if verdict.blocked:
        return {"ok": False, "guard": verdict}     # 未写盘 → 无需回滚




    try:
        run(f"git apply --check {patchfile}")      # dry run
        run(f"git apply --index {patchfile}")     # 原子落盘




        if tree_sitter_has_error(file):
            raise SyntaxBroken()




        commit = run(f'git commit -m "{msg(...)}" --no-verify')
        # ---- COMMIT ----




    except Exception as e:
        run(f"git reset --hard {base_sha}")
        run("git clean -fd -e .godot -e .import")
        # ---- ROLLBACK ----
        return {"ok": False, "reject_reason": str(e)}




    run(f"codeindex sync {file}")                  # 索引跟上
    trace_store.record(...)
    return {"ok": True, "commit": commit, "guard": verdict}
```




commit message 编码审计信息，让 git log 本身成为 trace 的冗余副本：




```
fix(round=7): res://scripts/player.gd




sig-before: a3f91c2e
sig-after:  b7d04e18
rule-id:    R-0142
guard:      pass
patch-hash: 9c1f...
```




## 3.7 四个必须知道的坑




### 坑 1：`*.uid` 和 baseline commit 的顺序 ⚠️ 最容易踩




你的 intake **首轮会 wipe `*.uid`**。如果你的 baseline commit 拍在 wipe **之前**，那么任何 `git reset --hard B0` 都会**把 `.uid` 文件恢复回来**——而这些 uid 是 Godot 3 时代的、你本来故意删掉的。verify 的 UID 重复簇压缩逻辑会突然看到一批不该存在的文件。




**解法（二选一）**：




- baseline commit 拍在 `*.uid` wipe **之后**（推荐，语义最干净：baseline = "intake 完成态"）
- 或者 `.gitignore` 加 `*.uid`，让它们永远不进版本控制




另外 `.gitignore` 必须包含：`.godot/`、`.import/`、`*.uid`（如选方案二）、`.codeindex/`。否则 verify 的 import 缓存和 codeindex 的库会被 `reset --hard` / `clean -fd` 毁掉，下一轮强制变 COLD，白跑一次 V3。




import的全部内容和uid都不进入git之中。




### 坑 2：`reset --hard` 不删 untracked 文件




如果 LLM 通过 `edit(kind="create")` 新建了文件但还没 commit，`reset --hard` 留着它。必须配 `git clean -fd`，但**一定要带 `-e`**：




```bash
git clean -fd -e .godot -e .import -e .codeindex
```




漏了 `-e` 会把 verify 的 import 缓存删光。（被gitignore忽略的文件也会别删除，要慎用）




这个要再次考虑




### 坑 3：不要用 `git stash`




`stash` 有自己的状态机（`stash@{0}` 栈、可能冲突的 pop、untracked 要 `-u`），而且 pop 冲突时会留 conflict marker。**commit + reset 的状态机简单得多，而且每一步都留下不可变的物证**。审计场景下永远选 commit。




### 坑 4：不要用 `git worktree` / 多工作区




你的 verify 是**进程内单槽状态、一对一工作区**，工作区路径来自 config。多 worktree 会让"LLM 改的"和"verify 看的"分叉——这正是我上一轮建议拿掉"edit 自建工作区"的原因。




### 兜底：reflog




即使误操作了 `reset --hard`，`git reflog` 在默认 90 天内还能找回被丢弃的 commit。设 `gc.reflogExpire` 长一点，你的实验数据就有额外保险。




---




# 四、fix_guard 五条判据：原理与设计动机




先说 guard 存在的根本原因，这决定了所有判据的形状：




> **verify 能告诉你"错误消失了"，但它在原理上无法区分"错误消失"的两种路径：**
> 
> - **真修复**：代码语义修正，符合 4.7.1 API
> - **假修复**：把报错的代码删掉 / 注释掉 / 换成 `pass`
> 
> 因为对 `--check-only` 来说，**这两者是完全等价的输入**。




这不是 verify 的缺陷，是**编译器类验证器的固有盲区**。任何"编译通过 = 成功"的 reward 都可以被"删掉不通过的代码"这条捷径 hack。这在 RL 里叫 reward hacking，在你这里的表现就是**假修复**。




所以 guard 不是 verify 的补丁，它是**一个正交维度的验证器**：verify 看"错误是否消失"，guard 看"消失的方式是否合法"。




---




## 判据 1（P0）：爆炸半径 — 改动位置必须贴着根因




### 原理：修复的局部性假设




一次合法的编译错误修复，其改动应当**空间上局部化在错误位置附近**。这不是启发式，是有依据的：Godot 的 `SCRIPT ERROR` 已经精确指到 `res_path` + `line`，修它需要改的就是那一行或它所在的函数。




形式化：




```
Δ = { (file, line) | 本次 patch 的 hunk 覆盖的行 }
C = { (e.res_path, e.line) | e ∈ 本轮 root_cause_errors }
     ∪ { p.target_res_path | p ∈ pointers }      # 指针下钻的合法目标
     ∪ declared_scope                             # 显式声明的跨文件改动




要求：∀ (f, l) ∈ Δ, ∃ c ∈ C 使得 f == c.file ∧ |l - c.line| ≤ N   (N = 15)
```




### 为什么在你的系统里必要性特别高




**① 你是唯一有条件做这个检查的人。**




通用 coding agent 拿不到"干净的根因 + 精确行号"——它们的编译输出里混着级联症状、警告、包装行。你的 verify 已经做完了 **parse → classify → protected → 哨兵人造边 → autoload FP → 级联压缩 → UID 簇压缩 → warning 降级 → 签名去重** 这一整条流水线，输出的 `root_cause_errors` 是**最小必要集合且带行号**。




这意味着 `C` 这个集合是**干净且小**的。如果你用未过滤的日志，`C` 会包含几百个级联症状的位置，覆盖半个项目，爆炸半径检查就退化成恒真——毫无约束力。




**你的去噪 verify 是判据 1 能成立的唯一前提。这是你系统的独特资产。**




**② 它抓的是"越改越远"这个特定失效模式。**




假修复最常见的形态不是"改错了一行"，而是"改动范围失控"：




- 为了让 `Identifier not found` 消失，把引用它的整个函数删掉
- 为了让某个 preload 解析通过，把整个 `preload` 块注释掉
- 在 `A→B→A` 震荡中，每轮改动范围越来越大（典型的"试探性乱改"）




这些在"改动位置分布 vs 错误位置分布"上有**极强的信号**，而且**不需要理解任何语义**就能检测。




**③ 它天然对 pointer 下钻规则做了强制。**




你已经定了纪律：**pointer 必须对 `target_res_path` 下钻，禁止对 `res_path`（引用方）下钻**。判据 1 把这条从"prompt 里的建议"升级为"落盘前的硬检查"——因为 `res_path` 不在 `C` 里，改引用方会直接被拒。




**这是把软约束硬化的典型例子，而且零额外成本。**




**④ 实现成本几乎为零。** verify 已经返回 `res_path` 和 `line`，patch 的行号在第 4 步生成 udiff 时就有了。就是个区间比较。




### 必须设计的豁免通道（否则会挡死正常修复）




判据 1 的最大风险是**误伤合法的跨文件改动**。比如 signal 改名，定义方和所有连接方都要改，但报错可能只在定义方。




所以必须有三条豁免：




| 豁免             | 机制                                                             | 为什么安全                                         |
| -------------- | -------------------------------------------------------------- | --------------------------------------------- |
| **pointer 目标** | `pointers[].target_res_path` 自动进 `C`                           | 这是 verify 自己给出的合法下钻目标                         |
| **规则驱动**       | `rule_id` 非空且来自 retrieve 的 A 层 → 允许改该规则声明的所有 `old_symbol` 出现位置 | 规则库是人工审核过的知识，可信                               |
| **显式声明**       | `declared_scope=[...]` + `justification`                       | 强迫 LLM **先声明再改**，而不是事后解释。声明本身进 trace，可事后统计滥用率 |




第三条是关键设计：**它不阻止跨文件改动，它只要求跨文件改动必须被显式声明。** 这把"不受控的扩散"变成"有记录的扩散"。滥用率本身就是一个可报告的指标。




这里需要进一步展开。




---




## 判据 2（P0）：符号消失 — 功能存量不得净减少




### 原理：用符号数作为"功能存量"的代理指标




假修复的另一大类是**删除式修复**。`--check-only` 只做语法 + 标识符解析，所以：




```gdscript
# 原文（报错：Identifier "KinematicBody" not found）
func move_player(delta):
    var body: KinematicBody = get_parent()
    body.move_and_slide(velocity * delta)




# 真修复
func move_player(delta):
    var body: CharacterBody3D = get_parent()
    body.velocity = velocity
    body.move_and_slide()




# 假修复 —— 对 verify 完全等价于真修复
# (整个函数被删掉了)
```




第三种情况，verify 返回 `CLEAN`、`gdscript_complete=true`。**verify 在原理上永远看不见这个问题。**




判据 2 的做法：apply 前后对同一文件做 AST 符号抽取，比较**符号集合**：




```
S_before = { (kind, name) | 符号 ∈ old_text }   # func / signal / class_name / const / enum / var
S_after  = { (kind, name) | 符号 ∈ new_text }




disappeared = S_before − S_after
若 disappeared ≠ ∅ 且未在 declared_scope 声明 → reject
```




### 为什么是 P0




**① 它覆盖的是最高频、最隐蔽的假修复形态。** "删掉报错的东西"是让编译器满意的最短路径，模型在优化压力下会自然发现它。




**② 它和 verify 完全正交。** 判据 1 看"改动位置"，判据 2 看"改动后果"。一个 patch 可以在爆炸半径内（就改了那一行所在的函数）但删掉了整个函数——判据 1 放过，判据 2 拦住。




**③ 用 AST 而非文本，避免误报。** 这是你已有 tree-sitter 索引的直接红利：注释里的 `func foo()`、字符串里的 `"signal_name"` 都不算符号。纯文本 grep 会大量误报。




**④ 你的 codeindex 已经在做这件事了。** 它入库的正是 `class_name / extends / func / signal / var / const / enum`。你只需要读它，不需要新写 parser。




**⑤ 对 Godot 特别重要：符号是跨文件契约。** GDScript 的 `func` / `signal` 会被 `.tscn` 的信号连接、其他脚本的 `call()` / `connect()` 引用。删掉一个 `signal`，编译期无感，**运行期整条交互链断掉**。而你的 codeindex **不含 `.tscn`**，所以这个断裂没有任何静态检查会发现——除了判据 2。
这一条需要格外注意一些。




### 实现上的一个关键选择




有两种做法，我建议第二种：




|方案|流程|问题|
|---|---|---|
|A. 落盘后比对|apply → `codeindex sync` → 查符号 → 违规则 reset + 再 sync|要写两次库，回滚时索引可能处于中间态；而且违反了"guard 在落盘前跑"的原则|
|**B. 内存 parse** ✅|直接用 tree-sitter 对 `old_text` / `new_text`抽符号，**不落库**|需要复用 parser 但不走 daemon。工程量小，语义干净|




方案 B 的额外好处：`create` / 新文件也能处理（库里还没这个文件）。




### 必须处理的合法删除




有些删除是对的——比如 4.x 移除了某个虚函数，`func _notification()` 里的老逻辑就该删。所以：




```
declared_scope 里显式列出要删的符号，如：
  declared_scope = ["res://player.gd#func:_integrate_forces"]
  justification  = "4.x 移除 _integrate_forces，逻辑迁移到 _physics_process"
```




同样是**先声明再改**。声明进 trace，事后可抽样人工复核——这就是你"假修复率"的标注入口。




---




## 判据 3（P1）：净删除量




### 为什么它不被判据 1、2 覆盖




- 判据 1 管**位置**（改在哪）
- 判据 2 管**符号**（有没有丢功能单元）
- 判据 3 管**体量**（丢了多少代码）




漏网场景：LLM 保留了 `func compute():` 的签名（判据 2 通过：符号还在），但把函数体 40 行全删了换成 `pass`。位置也在根因附近（判据 1 通过）。**只有体量检查能抓住。**




### 规则设计




```
added   = udiff 里 '+' 行数
removed = udiff 里 '-' 行数




reject 条件：
  removed - added > 10  AND  added < removed * 0.3
  # 即：大量删除 且 几乎没有对应新增
```




为什么要这个"且"：合法的 API 迁移常常是 `removed ≈ added`（一行换一行），或 `added > removed`（一行拆成三行）。**单纯看删除量会误伤**。真正的信号是"**删了很多，但没补回来**"。




判据 3 设 P1 而非 P0，因为它的信号强度不如 1、2，阈值需要在你的语料上调。建议**先以 warn 上线，收集分布后再决定是否 block**。 




---




## 判据 4（P1）：懒惰标记（pass / 注释化 / 占位）




### 为什么需要它：它对应 Aider 实测的 laziness 现象




Aider 的 benchmark 显示 GPT-4 Turbo 在 12/133 的重构任务上输出"lazy comments"——写 `# ...add logic here...` 代替实现。这不是个别模型的毛病，是**长代码生成的普遍倾向**。




GDScript 场景下的具体形态（这些都是"编译通过但语义为空"）：




```gdscript
func compute_damage(base): pass              # 空实现
func compute_damage(base):
    # TODO: 迁移到 4.x API                   # 占位注释
    return 0
# var body: KinematicBody = ...              # 整行注释化（最常见！）
func on_hit(): push_error("not implemented")  # 假实现
func update(): return                         # 提前返回
```




第三种（**注释掉报错行**）在迁移场景下极其高频，因为它是让 `Identifier not found` 消失的最省力方式——而且它同时绕过判据 2（符号还在）和可能绕过判据 3（注释不算删除行，`-x` / `+#x` 是 1删1增）。




**所以判据 4 不是判据 3 的补充，它抓的是一个判据 3 结构上看不见的形态。**




### 为什么正则够用，不需要 AST




三个理由：




1. **形态有限**且高度模板化，正则召回率很高
2. 这是**新增内容检测**（只扫 udiff 的 `+` 行），不是全文件分析，上下文需求低
3. **误报成本低**——返回的是 violation 文本，LLM 看到就能自纠（"我确实写了 pass，我补上实现"）。这和硬拒的成本完全不同




具体规则（只扫 `+` 行）：




```python
LAZY_PATTERNS = [
    r'^\+\s*pass\s*$',                                    # 裸 pass
    r'^\+\s*#\s*(TODO|FIXME|XXX|HACK)',                   # 占位注释
    r'^\+\s*#\s*\.{3}',                                   # "# ..."
    r'^\+\s*#.*(original|unchanged|as before|其余|不变)',  # 省略标记
    r'^\+.*push_error\(["\'].*not implement',              # 假实现
]
# 额外：注释化检测
#   若某个 '-' 行的内容 strip 后 == 某个 '+' 行去掉前导 '#' 后的内容
#   → COMMENTED_OUT violation（这条是最值钱的）
```




**最后那条"注释化检测"是判据 4 的核心，不要漏**。它是纯字符串比较，十行代码，抓的是迁移场景第一高频的假修复。




---




## 判据 5（P2）：`.gd` ↔ `.tscn` 重命名一致性




### 原理：你的索引有一个结构性盲区




你的 codeindex **只索引 `.gd/.cs/.cpp/.h/.hpp`，明确不索引 `.tscn/.tres`**。而 `.tscn` 里存着：




```ini
[ext_resource type="Script" uid="uid://c8xyz" path="res://player.gd" id="1_7bt6s"]
[node name="Player" type="CharacterBody2D"]
script = ExtResource("1_7bt6s")
[connection signal="health_changed" from="Player" to="HUD" method="_on_health_changed"]
```




这意味着：**符号在 `.gd` 和 `.tscn` 之间形成契约，但你没有任何工具能同时看到两端。**




后果：LLM 把 `class_name Player` 改成 `class_name PlayerBody`，或把 `signal health_changed` 改名，`.tscn`里的引用**不会报编译错误**（场景是运行期加载的），但场景实际已经坏了。




### 检测方式




```
若 patch 改动了 .gd 中的 class_name / func / signal 名字：
    old_name = 被改掉的名字
    grep -r "\b{old_name}\b" --glob "*.tscn" --glob "*.tres"
    若仍有命中 → violation: INCONSISTENT_RENAME
                  附上所有命中位置
```




### 为什么是 P2




因为 **`rule_codemod` 会吃掉大部分改名**（它同时改 `.gd` 和 `.tscn`，见第六节）。判据 5 只是兜住 LLM **自由改名**时的漏网情况。




但它的**指标价值很高**：它直接产出你清单里的"**跨 `.gd` + `.tscn` 符号改名是否原子一致**"这个数字。




---




## guard 的整体裁决策略




不要所有判据都硬拒——那会让循环卡死。建议分级：




|判据|默认动作|override 途径|
|---|---|---|
|1 爆炸半径|**block**|`declared_scope` / `rule_id`|
|2 符号消失|**block**|`declared_scope` 显式列出要删的符号|
|3 净删除|warn（观察期）→ block|`justification`|
|4 懒惰标记|**block**（注释化）/ warn（TODO）|无（这个不该 override）|
|5 tscn 一致性|warn + 附命中位置|自动进下一轮待办|




三条铁律：




1. **block 时不写盘、不 commit、不计 verify 轮次。** 这很重要——guard 拒绝是"LLM 的一次草稿被退回"，不是"一轮修复失败"。如果计轮，LLM 会因为格式问题耗光预算。
2. **返回结构化 violations，附具体位置和原因。** LLM 要能据此自纠，而不是盲猜。
3. **所有 override 都记进 trace_store。** override 率本身是个指标；override 后的 patch 是人工复核的优先抽样对象。




---




# 五、`scene_check` 和 `trace_store` 到底干什么




## 5.1 `scene_check`：补上"场景"这个系统性盲区




### 你当前系统里，场景是完全的盲区




把你的三个工具对场景的覆盖列出来：




|工具|对 `.tscn` / `.tres` 的覆盖|
|---|---|
|verify|快照后缀 `.gd/.gdshader/.shader/.tres/.uid` —— **明确不含 `.tscn`**；`--check-only` 只编译脚本，不加载场景|
|codeindex|只索引 `.gd/.cs/.cpp/.h/.hpp` —— **不索引 `.tscn`**|
|retrieve|迁移知识库，不看仓库文件|




结论：**一个 Godot 项目所有场景文件都可以是完全损坏的，而你的三个工具一致报告 `CLEAN` + `gdscript_complete=true`。**




这对 Godot 迁移是致命的，因为 Godot 项目的**大部分结构信息在场景里而不在脚本里**：节点树、类型、信号连接、资源引用。




### 为什么这些损坏是静默的




`.tscn` 是**运行期/编辑器期加载**的，不参与脚本编译。三类静默损坏：




**① 类型名未迁移**




```ini
[node name="Player" type="KinematicBody2D"]   # 4.x 已改名 CharacterBody2D
```




脚本编译不受影响。加载场景时 Godot 找不到这个类 → 节点丢失或整场景加载失败。




**② `ext_resource` 死引用**




```ini
[ext_resource type="Script" path="res://scripts/old_name.gd" id="1_abc"]
```




脚本改名/移动后 path 失效。而且——




**③ UID 失效（这条和你的 intake 直接相关）**




你的 intake **首轮 wipe `*.uid`**。Godot 4 的 `.tscn` 里 `ext_resource` 同时带 `uid://` 和 `path=`。uid 文件被删后，uid 解析失败，Godot 会 fallback 到 `path`。**如果 path 也因为重构变了，引用就彻底断了**——而这个断裂只有加载时才暴露。




**你自己的 intake 行为，在特定条件下会制造场景断链。** 这是 `scene_check` 存在的最直接理由。




### 两级实现




**Level 1：静态解析（零成本、确定性、必做）**




`.tscn` / `.tres` 是纯文本 INI-like 格式，正则/简单 parser 就能完整提取。不需要起 Godot。




```
输入：workspace 内所有 .tscn / .tres
解析：
  [ext_resource type=X uid=U path=P id=I]
  [sub_resource type=X id=I]
  [node name=N type=T parent=... ]
  script = ExtResource("I")
  [connection signal=S from=F to=T method=M]




检查：
  ① dangling_path      : P 指向的文件不存在
  ② unresolved_ext_id  : 被 ExtResource("I") 引用的 I 未在头部声明
  ③ unmigrated_type    : T 或 X ∈ rules.db 的 old_symbol 集合  ★ 复用规则库
  ④ orphan_uid         : uid://... 但对应 .uid 文件不存在 且 path 也不存在
  ⑤ broken_connection  : method=M 在 to=T 挂的脚本里找不到  ★ 复用 codeindex
  ⑥ dangling_script    : script 指向的 .gd 存在但 class_name 已改
```




注意 ③ 和 ⑤ 的巧妙之处：**它们复用你已有的 rules.db 和 codeindex，不需要新知识。**




- ③ 用 rules.db 的 `old_symbol` 列表当"过时类型名黑名单"
- ⑤ 用 codeindex 查 `find_symbol(M)` 是否存在于目标脚本 —— 这正好补上"信号连接"这个 codeindex 看不见的边




**Level 2：加载 smoke（可选，收尾跑一次）**




```gdscript
# __scene_smoke.gd
func _init():
    for path in _walk_all_tscn():
        var res = ResourceLoader.load(path)     # ★ 只 load，不 instantiate
        if res == null:
            print("SMOKE_FAIL: ", path)
```




**为什么只 `load` 不 `instantiate`：**




- `instantiate()` 会触发 `_init()`，进入 SceneTree 后触发 `_ready()` / `_enter_tree()`
- 用户代码可能有无限循环、网络请求、文件写入、`get_node()` 空指针崩溃
- 这些崩溃是**运行时逻辑问题，不是迁移问题**，会污染你的指标
- `load()` 已经能验证：资源解析、类型存在、ext_resource 可达、script 附加成功 —— 这正是迁移关心的全部




### 为什么必须独立，不能塞进 verify




**这是一个重要的设计决策，理由有三条：**




1. **你不想改 verify**（你明确说了）
2. **会污染 `signature_set`。** verify 的 Gate 靠"根因签名集合"做震荡/无进展判定。场景错误的生命周期和脚本错误完全不同（场景错误往往要等脚本全部修完才能修），混进去会让 `A→B→A` 误判和 `NO_PROGRESS_WARN` 乱响
3. **语义分层更清晰。** verify 的契约是"GDScript 编译根因"，这个契约的干净是它的价值所在。场景是另一个维度




所以 `scene_check` 的输出**不进 Gate、不影响 `hard_stop`**，它是一个独立的报告。`decision` 由 verify 独占。




### 调用时机




```
intake 之后                → 拿 baseline 场景健康度（对照基线！）
每次 rule_codemod 之后     → 确认改名没搞坏场景（Level 1，秒级）
verify 报 CLEAN 之后       → 收尾必跑（Level 1 + Level 2）
```




**最后一条是关键**：你已经定了"CLEAN + `gdscript_complete=true` 若伴随 caveat 不是迁移完成"。`scene_check`让这个判断**有了正面证据**——"GDScript 干净 **且** 所有场景可加载"才是完成。




---




## 5.2 `trace_store`：你四个指标的唯一数据源




### 为什么必须存在：三个硬约束




**约束 1：verify 的状态是内存态，MCP 退出即丢。**




你自己写的：




> "状态在内存里，MCP 退出即丢；**进程重启会丢掉熔断计数和快照**"




所以跨会话的任何统计都不可能从 verify 里拿到。




**约束 2：`remaining_budget` 只有 `rounds_used / rounds_limit`。**




你自己写的：




> "只有 `rounds_used` / `rounds_limit`（默认上限 40）。**不管 token/美元**"




所以"每文件成本"这个指标，verify 一个字节都提供不了。




**约束 3：你的四个目标指标全部是跨轮聚合量。**




|指标|需要什么|单次 verify 能给吗|
|---|---|---|
|假修复率|所有 patch + guard 裁决 + 人工复核标注|❌ verify 看不见 patch|
|残差清除率|baseline 根因数 **和** 终态根因数|❌ 只有当轮|
|每文件成本|token / 美元 / 触碰文件数|❌ 完全不管钱|
|vs Claude Code|两条 pipeline 的可比记录|❌|




**没有 trace_store，你的实验部分写不出来。** 它不是工程便利，它是论文的数据层。




### 表设计




```sql
-- 会话级
CREATE TABLE sessions (
  session_id      TEXT PRIMARY KEY,
  repo_url        TEXT,
  pinned_commit   TEXT,          -- 语料可复现的关键
  godot_version   TEXT,          -- "4.7.1"
  agent_config    TEXT,          -- JSON: model, temperature, prompt_hash
  baseline_commit TEXT,          -- intake 后的 B0
  started_at, ended_at,
  final_status    TEXT,          -- clean / hard_stop:REASON / abandoned
  -- baseline 快照（残差清除率的分母）
  baseline_root_cause_count INT,
  baseline_scene_issue_count INT,
  eligibility     TEXT           -- 为什么这个仓库可用/被排除
);




-- 轮级（一次 verify 调用 = 一行）
CREATE TABLE rounds (
  session_id, round_index,
  project_status        TEXT,   -- CLEAN / HAS_ERRORS / INFRA_FAILURE
  decision              TEXT,   -- CONTINUE / NO_PROGRESS_WARN / ...
  hard_stop             BOOL,
  signature_set_hash    TEXT,   -- ★ 不存全文，存 hash
  root_cause_count      INT,
  pointer_count         INT,
  diff_new, diff_resolved, diff_persisted   INT,
  gdscript_complete, shader_checked, probe_incomplete  BOOL,
  untrusted_file_count  INT,
  caveats               TEXT,   -- JSON
  head_commit           TEXT,   -- ★ 关联到 git
  -- 成本（verify 不给，宿主记）
  tokens_in, tokens_out INT,
  cost_usd              REAL,
  wallclock_ms          INT,
  PRIMARY KEY (session_id, round_index)
);




-- 根因明细（残差分析用）
CREATE TABLE root_causes (
  session_id, round_index,
  local_signature TEXT, kind TEXT, res_path TEXT, line INT,
  symbol TEXT, role TEXT, target_res_path TEXT
);




-- patch 级（假修复率的载体）
CREATE TABLE patches (
  patch_id      TEXT PRIMARY KEY,
  session_id, round_index,
  source        TEXT,   -- "llm" / "rule_codemod" / "converter"
  file          TEXT,
  patch_hash    TEXT,   -- ★ sha256(规范化 udiff)
  udiff         TEXT,   -- 全文，事后复核用
  lines_added, lines_removed  INT,
  guard_verdict TEXT,   -- pass / warn / reject
  applied       BOOL,
  commit_sha    TEXT,
  rule_id       TEXT,
  declared_scope TEXT,
  justification TEXT,
  -- 人工标注（事后填，假修复率的 ground truth）
  human_label   TEXT,   -- real_fix / fake_fix / partial / unreviewed
  human_note    TEXT
);




CREATE TABLE guard_violations (
  patch_id, criterion INT, severity TEXT, detail TEXT
);




-- 检索级（RAG 有效性）
CREATE TABLE retrievals (
  session_id, round_index, request_id,
  query_kind TEXT,              -- error_text / symbols / query_text
  coverage   TEXT,              -- rule_hit / prose_only / no_hit
  top_rule_id TEXT,
  recommended_action TEXT,
  escalate_suggested BOOL,
  cache_hit BOOL, took_ms INT,
  -- 下游关联：这次检索有没有导致成功的 patch？
  led_to_patch_id TEXT
);




-- 场景健康度
CREATE TABLE scene_checks (
  session_id, round_index, level INT,   -- 1=static 2=smoke
  dangling_path_count, unresolved_ext_id_count,
  unmigrated_type_count, orphan_uid_count,
  broken_connection_count, load_fail_count  INT,
  detail TEXT
);
```




### 关键设计点




**① 为什么存 `signature_set_hash` 而不是全文**




- 全文可能很大（几百个签名 × 40 轮）
- hash 足够复现 Gate 的判定：`NO_PROGRESS` 就是连续 N 轮 hash 相同，`A→B→A` 就是 hash 序列 `h1,h2,h1`
- **你能离线复现 verify 的 Gate 决策，甚至离线重新调阈值**——把 3/3/3/3/40 换成别的值，重跑判定，看哪组参数更好。这是一个免费的消融实验
- 明细在 `root_causes` 表里，需要时能 join 回来




**② 为什么 `patch_hash` 是重要字段**




同一个 `patch_hash` 在一个 session 里出现两次 = LLM **提交了完全相同的补丁两次**。这是 `A→B→A` 震荡的**物证级证据**——比签名震荡更硬，因为它证明的是"Agent 在重复同一个动作"而不只是"错误在循环"。




**③ `source` 字段让成本论点能成立**




```sql
-- rule_codemod 消化了多少 vs LLM 消化了多少
SELECT source, COUNT(*), SUM(lines_added + lines_removed)
FROM patches WHERE applied = 1 GROUP BY source;
```




如果 codemod 吃掉 70% 的改动而成本为 0，你的"每文件成本"优势就有了**机制解释**，而不是"我们省了 token"这种没有说服力的说法。




**④ `human_label` 是假修复率的唯一 ground truth**




guard 只能给出"被拦下的可疑 patch"。真实的假修复率需要**对 `guard_verdict='pass'` 的 patch 做抽样人工复核**——因为 guard 会漏。




```
guard 拦截率      = count(reject) / count(*)
guard 精确率      = count(reject ∧ label=fake) / count(reject)
guard 召回率      = count(reject ∧ label=fake) / count(label=fake)
真实假修复率      = count(label=fake) / count(applied=1)
```




**这四个数字是你这篇工作最硬的贡献。** 没有 `human_label` 字段，你只能报"我们拦了 X 个"，报不出"我们拦对了多少、漏了多少"。




**⑤ 指标推导公式**




```sql
-- 残差清除率
(baseline_root_cause_count - final_root_cause_count) * 1.0
  / baseline_root_cause_count




-- 每文件成本
SUM(cost_usd) / COUNT(DISTINCT patches.file)




-- 一致性违规数
SUM(scene_checks.unmigrated_type_count + broken_connection_count)
  WHERE round_index = (最后一轮)




-- 收敛效率
rounds_used, 以及 root_cause_count 随 round_index 的下降曲线
```




**⑥ 它顺便解决了 verify 的状态易失问题**




进程重启后，从 trace_store 读最近 N 轮的 `project_status` 和 `signature_set_hash`，就能**在宿主层重建**熔断计数和震荡检测。你不用改 verify 一行代码，只是在外面加了一层持久化的 Gate 影子。




---




# 六、`rule_codemod`：你的理解对不对？




> 我理解的是：将 converter 无法覆盖的文件，用官方迁移规则表先自己过一遍机械性的符号重命名。




**方向完全正确，核心机制你抓住了。** 但有三处需要扩展，每一处都影响它的价值。




---




## 修正 1：它补的不只是"文件覆盖盲区"，还有"时间差"和"规模盲区"




"converter 无法覆盖的"这个说法太窄了。实际有四类缺口：




|缺口|说明|为什么 converter 不管|
|---|---|---|
|**① 时间差**★最重要|`--convert-3to4` 的映射表是 **3.x → 4.0** 时代的。你的 target 是 **4.7.1**。4.0→4.7 之间 Godot 自己又改过一批 API|converter 根本不知道 4.7 的存在|
|**② 规模盲区**|超大文件（>4MB / 超长行）converter **静默跳过**，不报错|设计如此，为了避免卡死|
|**③ 语义盲区**|`extents → size` 这类改完不报错但逻辑已坏的（你的 `static_scan_post_l0`）|converter 做的是文本/符号映射，不做语义|
|**④ 上下文依赖**|同名符号在不同基类上有不同映射，converter 的表是扁平的|表达力不够|




**① 是你最有力的论点**：你的 rules.db 是**锁定 4.7.1 的**。这意味着 `rule_codemod` 不是"重做 converter 做过的事"，而是**填补 converter 在时间轴上的空白**——这是 converter 原理上不可能做到的（它是 4.0 时代冻结的代码）。




**② 直接解决你清单里的"哪些大文件被静默跳过"**：intake 的 precheck 标出被跳过的文件，`rule_codemod` 专门处理它们。这两个组件是配对设计的。




---




## 修正 2：它不是"先跑一次"，而是**循环内可重入**




你的措辞"先自己过一遍"暗示它是个前置步骤。实际上它应该在循环里被反复调用：




```
intake
  └─ converter + precheck
       ↓
  rule_codemod (第 1 次：批量、高置信度规则)     ← 你想的这一次
       ↓
  ┌──── verify ────────────────────────────────┐
  │  root_cause_errors[0]                       │
  │      ↓                                      │
  │  retrieve_migration_rule(error_text=...)    │
  │      ↓                                      │
  │  ┌─ A 层命中 且 agent_action 是机械替换 ──┐  │
  │  │   → rule_codemod(rule_id=R-xxx)      │  │ ← 循环内重入
  │  │     零 LLM 成本、确定性               │  │
  │  └───────────────────────────────────────┘  │
  │  ┌─ prose_only / no_hit / 需要判断 ──────┐  │
  │  │   → LLM: read/grep/codeindex → edit  │  │
  │  └───────────────────────────────────────┘  │
  └─────────────────────────────────────────────┘
```




**为什么必须可重入：错误是分层暴露的。**




GDScript 的编译是短路的。文件 A 有个 parse error，编译器根本不会走到它后面的代码，所以后面的 `KinematicBody` 引用**这一轮不会报**。修掉 parse error 之后，下一轮才暴露出来。




同理，你的 `pointers` 机制本身就说明这一点——preload 链要一层层下钻，每层都可能暴露新的待改名符号。




**所以"机械改名"这件事在整个会话里是持续需要的，不是一次性的。**




这也带来一个漂亮的成本论点：**路由让确定性的改动走 codemod（成本 0），只把需要判断的残差给 LLM。**这才是"每文件成本"能显著低于 baseline 的真实机制。




---




## 修正 3：它必须同时改 `.tscn`/`.tres`，而且必须带守卫




### 3a. 同时改场景 —— 这是 codemod 最独特的价值




类型改名在两个地方出现：




```gdscript
# player.gd
extends KinematicBody2D          ← codemod 改这里
var body: KinematicBody2D
```




```ini
# player.tscn
[node name="Player" type="KinematicBody2D"]    ← 也必须改这里！
```




**只改脚本 = 制造场景断链。** 而你的 codeindex 不含场景、verify 快照不含 `.tscn`，这个断链没有任何工具会发现。




好消息：`.tscn` 的类型名出现位置是**结构化且有限**的：




- `[node ... type="X"]`
- `[ext_resource type="X" ...]`
- `[sub_resource type="X" ...]`
- `[gd_resource type="X" ...]`




**只改这些字段的值，不碰任何用户文本**（`name=`、property 值、字符串）。这是安全的、确定性的。




**这一步直接消掉你清单里"跨 `.gd` + `.tscn` 符号改名是否原子一致"这个空白**——而且不需要把场景塞进 codeindex（那会是个大工程）。




### 3b. 必须带守卫 —— 不能全仓无脑 sed




四类必须处理的风险：




**① 只在标识符位置替换，不碰字符串/注释**




```gdscript
var s = "KinematicBody2D is deprecated"   # ✗ 不能改（字符串）
# KinematicBody2D 迁移备注                 # ✗ 不能改（注释）
extends KinematicBody2D                   # ✓ 改（标识符）
```




这需要 AST 定位。**你已经有 tree-sitter parser 了**，用它拿到 identifier 节点的字节区间，只在这些区间内替换。




（附带说明：你写了"tree-sitter parsers 只服务索引，不能改写 AST，无 codemod API"。这里**不需要 AST 改写**——只需要 AST **定位** + 文本替换。这是最稳的 codemod 形态，不用处理 AST → 源码的还原问题，注释和格式全部原样保留。）




**② owner / 上下文约束**




rules.db 的 `owner` 字段就是为这个准备的。同一个方法名在不同类上可能有不同的迁移路径：




```
rule: old_symbol="get_node_or_null", owner="Node"        → 不变
rule: old_symbol="instance",         owner="PackedScene" → instantiate
rule: old_symbol="instance",         owner=<其他>        → 不动！
```




无 owner 约束的规则只能改**全局唯一**的符号（如类名 `KinematicBody2D`）。有 owner 约束的需要类型推断——**做不到就别改，交给 LLM**。这是正确的取舍：codemod 只做它 100% 确定的部分。




**③ 幂等 / 已迁移检测**




如果符号已经是 `new_symbol`，跳过。如果一个 token 被多条规则命中，**报冲突不猜**：




```json
{ "conflict": "res://a.gd:42", "token": "size",
  "candidates": ["R-0142 extents→size", "R-0311 size→get_size()"],
  "action": "escalate_to_llm" }
```




**④ dry-run 先出 plan**




```
rule_codemod(mode="plan", rule_ids=[...])
→ { "plan": [
      {"file":"res://player.gd","line":3,"col":8,
       "rule_id":"R-0142","old":"KinematicBody2D","new":"CharacterBody2D",
       "context":"extends KinematicBody2D"},
      ...
    ],
    "conflicts": [...],
    "skipped": [{"reason":"in_string_literal", ...}] }
```




plan 审过之后才 apply，**而且 apply 必须走 `edit` 同一个通道**（带 `rule_id` 豁免）。理由：




- 所有写入经过 fix_guard 的不变式不能破
- 自动 commit + `codeindex sync` 的流程复用
- patch 进 trace_store，`source='rule_codemod'`，成本归因能算




---




## 顺带解决：`static_scan_post_l0`




你说"协议要求另写扫描器，扫描器还没写"。




**它就是 `rule_codemod` 的同一套引擎，只是 mode 不同。**




```
rule_codemod(mode="plan")  → 输出建议的替换点
rule_codemod(mode="apply") → 落盘
rule_codemod(mode="scan")  → 只输出 warning，不生成 patch   ← 这就是 static_scan_post_l0
```




因为 `static_scan_post_l0` 类规则（`extents → size`：改完不报错但逻辑已坏，因为 `extents` 是半长、`size` 是全长，数值要 ×2）的特点是：**符号定位是确定的，但正确的修法需要判断**（要不要乘 2 取决于上下文）。




所以：




- 用同一个 AST 定位引擎找到所有 `extents` 出现点
- **不自动改**，输出 warning 交给 LLM 或人工
- 同时进 `scene_checks` / 独立的 `semantic_warnings` 表，作为"假修复"的一个可量化类别




**这几乎零额外工程量**（共用定位引擎 + 共用 rules.db），而且它是"编译通过但语义已坏"在迁移域**最硬的实证例子**——非常适合写进论文当 motivating example。




需要注意的是：`static_scan_post_l0` 的规则在你当前协议里对 `retrieve` **不可见**（`detection_method` 白名单只含 `agent_retrieval` / `agent_retrieval_or_escalate`）。所以 `rule_codemod` 需要**直接读 rules.db**，而不是通过 `retrieve` 拿规则。这是一个实现细节但很重要：**codemod 是 rules.db 的第二个消费者，权限比 Agent 大**。




---




# 七、汇总：落地优先级




|顺序|组件|工程量|解锁什么|不做的后果|
|---|---|---|---|---|
|1|**`read` + `grep`**|小|LLM 能看见场景文件；`edit` 的锚点来源|edit 必然失败|
|2|**`edit`（锚定 + git 事务）**|**中大（核心）**|写通道|没有闭环|
|3|**fix_guard 判据 1 + 2**|小（复用 verify line + tree-sitter）|**假修复率这个指标**|论文最大卖点没有|
|4|**`trace_store`**|小（纯 SQLite）|**全部四个指标**|实验部分写不出来|
|5|`intake`（converter + 4MB precheck + baseline commit）|中|"converter 吃掉多少 / 跳过什么"|缺 baseline，残差率没分母|
|6|**`rule_codemod`（AST 定位 + `.tscn`）**|中|成本论点 + 场景一致性|成本打不赢 baseline|
|7|`scene_check` Level 1（静态）|小|"`.tscn` 是否损坏"|CLEAN 是假的|
|8|codeindex / retrieve 的 MCP adapter|小（纯包装）|LLM 能用（且不需要 bash）|只能给 bash，回到第一节的问题|
|9|fix_guard 判据 3/4/5|小|覆盖率提升|guard 召回率偏低|
|10|`scene_check` Level 2（smoke）|中|加载正确性|静态检查已覆盖大部分|




**3 和 4 是投入产出比最高的两项**：加起来可能两三天，但它们是"假修复率"和"残差清除率"这两个数字存在的前提。而这两个数字是你区别于"又一个 coding agent"的全部。




---




**一句话收尾**：你的 verify 已经把"错误信号"做到了很干净——这是稀缺资产，而且它恰好是 fix_guard 判据 1 能成立的唯一前提。现在缺的不是更多工具，而是**把这个干净信号变成对写操作的约束**（`edit` + guard），以及**把过程记下来**（trace_store）。至于 bash——一旦给了它，上面所有约束都只是建议。




---




要不要我接着写：




- **A. `edit` 的完整实现**（锚定算法 + 三级降级 + git 事务 + 错误返回格式，约 250 行，可直接跑）
- **B. fix_guard 五条判据的实现**（含爆炸半径的豁免逻辑和 tree-sitter 符号抽取）
- **C. `rule_codemod` 的 AST 定位 + `.tscn` 替换 + 冲突检测**




建议 **A → B → C**，因为 A 是写通道的前置，B 挂在 A 的第 5 步上。

这是我还缺少的其他工具链的汇总。请你综合我们上面所有的讨论，总结一张pendings列表，这个列表中需要总结出全部的有待实现的工具和features。按照你建议的实现的先后顺序排列（前面的不得依赖后面的）。

请你再次调研一下converter真实遗留下来的问题，根据我的应用场景选取优先级最高的需要实现的features，刚才我们讨论的全部内容有些庞大。请你将非必要的内容删去。留下roi最高的实现。（能现成零成本利用已有设施的除外）。请你总结成一张清晰的表，语言尽可能简洁，将待实现的功能、架构组织（放在什么地方，哪一层），函数签名的初步设计、暴露方式（工作流的环节还是llm调用的工具）等等。
请你开始总结吧

一、先做证据核对：converter 真实遗留什么
官方文档（4.x upgrading_to_godot_4）的原话，按对你的影响排序：

#	官方原文（要点）	遗留物形态	谁能修
E1	"not all API renames can be performed automatically. The list below contains all renames that must be performed manually using the script editor" —— 涵盖 method / property / signal / constant	编译错误，成百上千条，但名单是官方给的、有限、可机器读	⭐ 规则表 + codemod（零 LLM 成本）
E2	"Scripts will likely contain various errors as well (possibly hundreds in large projects) ... a large part of the upgrade process remains manual"	大量编译错误	verify + LLM
E3	被移除/替换的节点："The setup must be done from scratch again, as the project converter doesn't support updating existing setups"	⭐ 场景层损坏，且 converter 明确声明不管	scene_check
E4	"GDScript setter and getter syntax was changed, but it's only partially converted. In most cases, manual changes are required"	编译错误 / 静默失效	LLM
E5	4MB / 100k 行 → "it will not be upgraded"（静默跳过）	整文件未转换	precheck + codemod
E6	StringName："sometimes you may have to replace "example" with &"example""	少量，多为 warning	低优先级
E7	shader："some changes to shaders that aren't covered by the upgrade tool"	shader 编译错误	你的 V3 已覆盖检测
E8	时间差：converter 是 3.x→4.0，你的 target 是 4.7.1	4.0→4.7 之间的 API 变动完全未覆盖	⭐ 你的 4.7.1 rules.db
1.1 由此产生的两处优先级修正（推翻我上一轮的排序）
修正 A：E1 是绝对第一，优先级高于 fix_guard 之外的一切功能性组件。
它是唯一一类"数量最大 + 官方给了完整名单 + 完全机械 + 可零 LLM 成本消化"的遗留债。你的 rules.db 加 codemod 直接吃掉它，这既是残差清除率的主力，也是"每文件成本"论点的唯一机制解释。我上一轮把 rule_codemod 排在第 6 位，太低了。

修正 B：I7（属性静默丢弃）要从"第一优先"降到 P2。 上一轮我基于"@export 改名导致 .tscn 属性静默丢弃"把它排第一。这个危害判断没错，但ROI 判断错了：

I7（属性存在性）	I2′（.tscn 里的过时类型名）
依赖	需要 ClassDB dump（新写 GDScript + 继承树 + 属性集 + 白名单豁免）	只需 rules.db 的 old_symbol 列表（已有）
触发条件	LLM 恰好改了 @export 变量名（推测）	⭐ E3 官方承认 converter 不更新既有 setup（文档证据）
工程量	大	~50 行
同等危害下，成本差一个数量级，且证据强度相反。 所以场景层第一条规则是 .tscn 中的未迁移类型名，不是 I7。

二、Pendings 总表（按实现顺序，前不依赖后）
图例：暴露方式 T=LLM 工具 / W=工作流固定环节（LLM 不可见不可跳过） / L=内部库

P0 — 没有它们，闭环不成立 / 指标算不出来
#	功能	位置 / 层	签名	暴露	量	解锁
1	read	新 workspace MCP	read(path, start=1, limit=400) → {lines[], total, truncated}，带绝对行号	T	小	edit 的锚点来源
2	grep（含 glob）	同上	grep(pattern=None, glob=None, path=None, max=100, context=0)；pattern=None 退化为列文件	T	小	唯一检索入口，替代 bash
3	edit（锚定 + git 事务）	同上	edit(kind, file, hunks[{context_before,remove,add,context_after}], content?, to_commit?, declared_scope?, rule_id?, justification?) —— 无任何行号字段	T	中大	唯一写通道
4	trace_store	宿主 L0，SQLite	record_round/record_patch/record_retrieval/...	L（无工具）	小	⭐ 四个指标的唯一数据源
5	gd_symbols（内存 tree-sitter 抽符号）	共享库 L	symbols(text) → {(kind,name)}；has_error(text) → bool	L	小	guard C2 + edit 第 8 步
6	fix_guard C1+C2+C4c	挂在 edit 落盘前	guard(udiff, old, new, root_causes, declared_scope, rule_id) → {verdict, violations[]}	W（LLM 只见 violations）	小	⭐ 假修复率
7	intake	宿主 L0	intake(repo, commit) → {converted, skipped_oversize[], baseline_commit, baseline_root_cause_count}	W	中	残差清除率的分母
C1/C2/C4c 三条的选择理由：C1 复用 verify 已有的 res_path+line（零新知识）；C2 复用 #5；C4c（注释化检测）是十行字符串比较，抓迁移场景第一高频的假修复形态。C3/C5 推到 P2。

P1 — 论文核心论点的载体
#	功能	位置	签名	暴露	量	解锁
8	⭐ rule_codemod（AST 定位 + 文本替换，不改写 AST）	宿主 L0，直读 rules.db	rule_codemod(mode="plan"|"apply"|"scan", rule_ids=None, files=None) → {plan[], conflicts[], skipped[]}。apply 必须走 edit（带 rule_id）	T + W：首轮 W 批量跑，循环内 retrieve 命中 A 层机械规则时 LLM 可调	中	⭐ E1+E5+E8；成本论点
9	tscn_parse	共享库 L	parse(text) → {ext_res[], sub_res[], nodes[], connections[]}	L	小	8/10/11 的共同前提
10	codemod 的 .tscn 类型字段替换	并入 #8	只改 [node type=] / [ext_resource type=] / [sub_resource type=] / [gd_resource type=] 的值	W	小	⭐ 跨 .gd+.tscn 原子一致（指标之一）
11	scene_check L1（三条规则）	codeindex server（数据在哪计算在哪）	scene_check(scope="changed"|"all"|[paths], include_pre_existing=false) → {regression[], pre_existing_count, fixed[], coverage}	T（主循环）+ W（收尾门固定跑 scope="all"）	小	⭐ E3；让 CLEAN 变成真的
↳ 规则：① unmigrated_type（查 rules.db old_symbol，零新知识）② dangling_path（ext_resource 目标不存在）③ unresolved_ext_id					
12	edit_journal + baseline delta	宿主 L0（journal 与 edit 同事务）；signature 不含行号	changed_files(since) → [paths]；三级降级：journal → mtime/hash → 全量	L	小	scope="changed"；regression ≠ pre_existing
13	codeindex scene 旁路（同库异表）	codeindex server	新表 scene_files/scene_nodes/scene_res/scene_refs + 索引 idx_refs_target；find-symbol 返回追加 scene_usages[]，edges 不动	不加新工具，从已有返回漏出	中	LLM 改符号前就知道场景在用它
14	codeindex / retrieve 的 MCP adapter	各 server	纯包装	T	小	让 LLM 用得上（否则只能给 bash）
P2 — 有余力再做
#	功能	签名 / 要点	暴露	量
15	guard C3（净删除 removed-added>10 且 added<0.3×removed）+ C4a/b（pass/TODO 正则）	先 warn 观察期，收集分布后再 block	W	小
16	guard C5（.gd↔.tscn 改名一致性）	grep 旧名于 *.tscn；warn	W	小
17	scene_outline	scene_outline(path) → 紧凑节点树	T	小
18	scene_check 扩展：broken_connection（连接 method 查 codeindex）、orphan_uid	复用 #13	T	小
19	load sweep（非 flag，是 --headless -s + 自写 MainLoop，只 ResourceLoader.load()，不 instantiate()）	必带 ###BEGIN/###END 哨兵 + SWEEP_RESUME_AT 崩溃续跑 + 必在 --import 后	W（收尾一次）	中
20	I7 属性存在性 + ClassDB dump	需继承树 + 属性集 + 内置属性白名单	T	大
21	retrieve 有效性归因（led_to_patch_id）	trace_store 字段已留	L	小
三、明确砍掉（不做）
砍掉	理由
bash / bash_ro	白名单工程量大于直接写 3 个结构化工具，能力还更弱；且一次 sed -i 就让 fix_guard 和"假修复率"全部作废
单独的 glob 工具	rg --files -g 已覆盖，只增加路由歧义
单独的 scene_refs 工具	已被 find-symbol 的 scene_usages 吸收；多一个可选工具 = 多一个 LLM 想不起来调的地方
I5b（自由文本 grep 消失符号）	update/size/state 误报率过高；I5a 与 #11/#13 高度重叠
把 scene_check 塞进 verify	会污染 signature_set → 震荡/无进展判定失真；且你明确不改 verify
聚合 MCP proxy	多一跳 + 两 server 生命周期耦合 + 错误归因模糊。改用：orchestrator 在 verify 返回文本尾部追加"场景状态陈旧"提示，零架构改动、效果等同
git apply --reject / --3way	--reject 破坏原子性；--3way 往 .gd 写 <<<<<<< = 语法垃圾
git stash / git worktree	状态机复杂；worktree 会让"LLM 改的"和"verify 看的"分叉
--quit-after	你实测崩溃是必然的（它跑 _ready，迁移中途必挂），已正确禁用，不要回头
scene_check 作为编辑 gate	修场景 regression 常需先改更多文件，阻塞编辑会死锁。只 gate "任务完成"，永不 gate "文件写入"
四、两处上一轮的具体错误，顺手修正
上一轮我说的	正确的
git clean -fd -e .godot -e .import -e .codeindex	-e 多余。git clean 不带 -x 时本就跳过 gitignore 的文件。既然 .godot/ .import/ *.uid .codeindex/ 都已 gitignore，用 git clean -fd（绝不加 -x） 即可。更简单也更安全
baseline commit 必须拍在 *.uid wipe 之后	*.uid 和 import 产物都不进 git → 这个坑自动消失，baseline commit 位置无约束
五、三个里程碑
M	包含	产出
M1 闭环（#1–7）	read/grep/edit + guard C1C2C4c + trace_store + intake	Agent 能改代码、改动受约束、过程被记录。"假修复率"可以开始出数
M2 论点（#8–12）	rule_codemod（含 .tscn）+ scene_check L1 + delta	⭐ 吃掉 E1/E5/E8（成本论点）+ 堵住 E3（CLEAN 不再是假的）。四个指标全部可算
M3 打磨（#13–21）	scene 旁路 / 剩余 guard / load sweep / I7	召回率与覆盖率提升
收尾一句
证据把结论收得比上一轮更紧：converter 遗留债的主体是官方已列成名单的机械改名（E1/E5/E8）——这是 rule_codemod 的地盘，零 LLM 成本；其次是官方明确声明"不更新既有 setup"的场景层（E3）——这是 scene_check 的地盘，且第一条规则只需复用 rules.db。

所以顺序是：先建可信写通道（edit+guard）与记账（trace_store）→ 再用 codemod 吃掉机械大头 → 再用 scene_check 堵住 CLEAN 的谎言。 其余（load sweep、I7、ClassDB dump、bash）在这三步交付前都不值得投入。

要不要我下一步直接写 #3 edit 的完整实现（锚定三级降级 + 11 步流水线 + git 事务 + 结构化错误返回）？它是 M1 里唯一"中大"的一项，也是 #6 guard 的挂载点。