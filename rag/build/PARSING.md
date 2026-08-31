# A 层编译：四类源的具体解析方法

这份文档补的是 [build/README.md](README.md) 没写的那一半:那份文档锁的是"协议"(一行长什么样、字段怎么填);这份文档锁的是"怎么把四种长得完全不一样的原始文件,变成那一行"——每个 adapter 用什么库、正则怎么写、库解决不了的地方怎么办。

读者是要动手写 `parse_renames_cpp.py` / `diff_extension_api.py` / `parse_upgrading_docs.py` / `build_tier_a.py` 的人。字段名、`source` 取值、`detection_method` 分流规则一律以 [build/README.md](README.md) 为准,这里不重复,只讲"怎么解析"。

选型总表放在最前面,方便直接抄依赖:

| adapter | 输入 | 用什么解析 | 为什么不用别的 |
|---------|------|-----------|--------------|
| `parse_renames_cpp.py` | `renames_map_3_to_4.cpp` | 纯正则,不引入库 | 格式是 C++ 数组字面量,固定到只有一种形状,上真正的 C++ 解析器(`pycparser`/`libclang`)是过度设计 |
| `diff_extension_api.py` | 两份 `extension_api*.json` | 标准库 `json` | 就是 JSON,不需要额外库 |
| `parse_upgrading_docs.py` | `upgrading_to_godot_4.{1-7}.rst` + `upgrading_to_godot_4.rst` 的 `Updating shaders` 小节 | **docutils**(`docutils.parsers.rst` + `docutils.utils.new_document`) | 表格列宽逐表不同、多字节符号(✔️/❌)对齐、"粗体行是 owner、下一行是内容"这种跨行语义,手写正则切列极易在某一份文件上悄悄错位;docutils 是 Sphinx 本身用来渲染这些文件的库,拿它解析比自己猜表格边界可靠得多 |
| `tier_a_manual/*.yaml` | 人工维护的 YAML | 标准库 `yaml.safe_load`(PyYAML) | 格式已经接近最终行,不需要额外解析逻辑,只需要类型/默认值兜底 |

依赖清单见本文件末尾,已经写进 [`rag/pyproject.toml`](../pyproject.toml) 的 `build` 依赖组,实测可用(见该文件注释)。

---

## 1. `parse_renames_cpp.py`:纯正则,按数组分组扫描

`renames_map_3_to_4.cpp` 的形状全篇统一,只有一种模式:

```cpp
const char *RenamesMap3To4::gdscript_function_renames[][2] = {
	{ "instance", "instantiate" },
	// { "FLAG_MAX", "PARTICLE_FLAG_MAX" }, // CPUParticles2D -- Used in more classes.
	{ "get_positional_shortcut", "get_shortcut" }, // 可选的行尾注释
	...
};
```

算法(单次逐行扫描,不需要真正的语法分析):

1. 用 `re.compile(r'RenamesMap3To4::(\w+)\[\]\[2\]\s*=\s*\{')` 匹配数组开始行,捕获数组名,按 [build/README.md 6.1](README.md) 的表把数组名映射到 `symbol_kind`(例如 `gdscript_function_renames` → `method`)。C# 三个数组(`csharp_*_renames`)命中即跳过整个数组,不产出任何行——不是解析失败,是故意排除(见 6.1)。
2. 数组开始之后,逐行用 `re.compile(r'^\s*(?P<commented>//\s*)?\{\s*"(?P<old>[^"]*)"\s*,\s*"(?P<new>[^"]*)"\s*\}\s*,?\s*(?://\s*(?P<comment>.*))?$')` 匹配条目行。`commented` 组非空 → `source=official_renames_skipped`、`converter_gap=1`、`agent_action=apply_and_warn`(6.1 已定);否则 `source=official_renames`、`agent_action=apply_rename`。
3. 遇到只含 `};` 的行,结束当前数组,回到状态 1 找下一个数组。纯注释行(不匹配条目正则、也不是数组开始/结束)直接跳过,不报错——文件里穿插了大量分类注释(`// Constants`、`// @GlobalScope`),这些是合法内容,不是异常。
4. 行尾 `// ClassA -- Breaks X` 这类说明写入 `payload.cpp_comment`,不解析成 `owner`(6.1 已经说明原因:转换器本身是全局正则,`owner` 允许为空)。

边界情况:

- 同一行内出现多个 `{ "x", "y" }`(目前没见过,但别假设永远不会出现)——正则按 `$` 锚定整行,如果真的出现多元组一行,会匹配失败并计入下面的"未识别行"报告,不会静默丢数据。
- `//` 出现在字符串内容里(例如老符号名恰好包含 `//`)——理论上可能,但 Godot 符号命名规范里不会出现,不特别处理,只在解析报告里留一条"如果未识别行数突然增加,先查这个"的注释。
- **解析报告**:脚本跑完打印"每个数组识别到多少条、跳过多少条(注释掉的)、多少行完全没匹配上任何规则"。未识别行数 > 0 时非零退出——不允许静默漏行,这是 8 个 vault 文件里改动最少、最应该被完全解析对的一个,任何遗漏都值得马上查。

---

## 2. `diff_extension_api.py`:标准库 `json`,按符号做集合差

两份快照都是普通 JSON,`json.load()` 直接拿到 dict,不需要额外库。核心是把 [build/README.md 6.2](README.md) 的"差集粒度是符号,不是整份 JSON"落成代码:

```python
def index_classes(api: dict) -> dict[str, dict]:
    return {c["name"]: c for c in api["classes"]}

def index_members(cls: dict, key: str) -> dict[str, dict]:
    # key in {"methods", "properties", "signals", "enums", "constants"}
    return {m["name"]: m for m in cls.get(key, [])}  # .get 兜底:不是每个类都有 properties/signals
```

对每个类、每个成员类别(`methods`/`properties`/`signals`/`enums`/`constants`),按 6.2 的表分流:

- 只在 4.0 的类/成员 → `change=remove`
- 只在目标版本的 → `change=add`
- 两边都有、`name` 相同但签名不同 → `change=signature`(方法:比较 `arguments` 的 `(name, type)` 序列 + `return_type`)或 `change=type`(属性:比较 `type` 字段)
- 两边都有且完全一致 → 不出行

`builtin_classes`(结构和 `classes` 平行,但字段是 `methods`/`members` 不是 `methods`/`properties`)、`global_enums`、`utility_functions`、`singletons` 各自单独一趟同样的逻辑,不能和 `classes` 共用同一份 index 函数的字段名假设。显式跳过 `builtin_class_sizes`、`builtin_class_member_offsets`、`native_structures`(6.2 已定,ABI 细节修 `.gd` 用不上)。

`hash` 字段不参与比较(6.2:"`hash` 变了但参数列表和返回类型没变,视为没变")——只比较业务字段,不比较这个。

`GH-xxxxx` 编号:这份 JSON 里没有,`payload.github` 留空,只有 rst 那一路才有编号(6.2 已定,两条允许并存)。

---

## 3. `parse_upgrading_docs.py`:docutils 解析 + 规则化的语义抽取

这是四个 adapter 里唯一需要"理解结构"而不是"照抄格式"的一个,拆成四步。

### 3.1 为什么选 docutils,不是手写正则切表格

实际文件里的表格是 RST **simple table**(`====` 做表头/表尾分隔线,列宽由这行 `=` 的分段决定),例如:

```rst
========================================================================================================================  ===================  ====================  ====================  ===========
Change                                                                                                                    GDScript Compatible  C# Binary Compatible  C# Source Compatible  Introduced
========================================================================================================================  ===================  ====================  ====================  ===========
**Basis**
Method ``looking_at`` adds a new ``use_model_front`` optional parameter                                                   |✔️|                 |✔️|                  |✔️|                  `GH-76082`_
========================================================================================================================  ===================  ====================  ====================  ===========
```

`**Basis**` 单独占一行、只有第一列有内容,是"owner 行";下一行 `Method ...` 是"内容行"——两者是不同的表格行(docutils 靠"第一列是否顶格"分行,不是靠空行分段)。手写正则按空格数切列,在 7 份文件、每份列宽都不同、且中间混着宽度不统一的 emoji 字符的情况下,极易在某一张表上悄悄错位而不报错。docutils 本身就是 Sphinx 渲染这些文件用的库,拿它解析可以直接复用官方自己认定的"这张表该怎么切"的逻辑。

### 3.2 预处理:把 `|✔️|` 这类替换引用转成纯文本

文件里的 `|✔️|`、`|❌|`、`|✔️ with compat|` 是 RST **替换引用**(substitution reference),它们的定义(`.. |✔️| replace:: ...`)在 godot-docs 仓库别处的公共文件里,不在我们 vault 里存的这份单文件快照中——如果直接拿这份文件喂给 docutils,会报"Undefined substitution referenced"。

解决方法**不是**去 vault 别的地方找那份定义文件,也**不是**用正则去改表格里的字符(改了会移动字符位置,破坏 simple table 靠字符列宽对齐的解析前提)。而是:在文件最前面(表格外,不影响任何字符位置)按下面的算法自动补上定义:

```python
import re

def inject_substitution_defs(rst_text: str) -> str:
    names = sorted(set(re.findall(r'\|([^|\n]{1,60})\|', rst_text)))
    preamble = "\n".join(f".. |{n}| replace:: {n}" for n in names)
    return preamble + "\n\n" + rst_text
```

即:扫描全文出现过的所有 `|...|` 名字,统一定义成"替换成它自己"(`✔️` 替换成显示文本 `✔️`),再拼到正文前面。这样每张表格里的字符一个不改,只是让 docutils 知道该怎么把这些替换引用还原成文本。

同理,`:ref:`(Sphinx 专有角色,不是 docutils 内置)在解析时会报"Unknown interpreted text role"——这类警告我们不需要处理(不关心跳转目标,只要保留原文文本),用 `settings_overrides={"report_level": 5, "halt_level": 5}` 让 docutils 报告但不中断解析。

### 3.3 用 docutils 建 doctree,按 section 记录 `heading_path`

```python
from docutils.parsers.rst import Parser
from docutils.utils import new_document
from docutils.frontend import OptionParser

def parse_doctree(rst_text: str, source_path: str):
    settings = OptionParser(components=(Parser,)).get_default_values()
    settings.report_level = 5
    settings.halt_level = 5
    document = new_document(source_path, settings)
    Parser().parse(rst_text, document)
    return document
```

拿到 `document` 之后,写一个继承 `docutils.nodes.NodeVisitor` 的访问者,在 `visit_section`/`depart_section` 里维护一个 `heading_path: list[str]` 栈(进入一个 section 就把它的 `title.astext()` 压栈,离开时弹栈)。这个栈同时喂给:表格行(`owner` 之外,`heading_path` 里最深的标题,例如 `Core`/`Rendering`,可以作为交叉校验或者展示上下文)和散文段落(直接就是它要用的 `heading_path`)。

### 3.4 表格 → `MigrationRule` 候选行

对 `nodes.table` 节点:

1. 读表头行(`thead`),把每一列的表头文字记下来(`Change` / `GDScript Compatible` / `C# Binary Compatible` / `C# Source Compatible` / `Introduced`)——按表头文字找列,不是按写死的列序号找,因为不同文件的列可能不是同一个顺序(目前 7 份文件观察到的顺序一致,但按名字找更抗变化)。
2. 遍历 `tbody` 的每个 `row`:用 `entry.astext()` 取每列纯文本。若只有第一列非空、其余列全空 → 这是"owner 行",把第一列文本(`nodes.strong` 包着的粗体文本)记为 `current_owner`,不产出行。否则是"内容行",继续第 3 步。
3. 内容行的第一列(`Change` 列)同时要:
   - 用 `.astext()` 拿完整文本,存进 `snippet`;
   - 单独遍历该列子节点里的 `nodes.literal`(即 `` `xxx` `` 反引号包裹的部分),把这些文本收集进 `match_tokens`——反引号包的通常就是符号名(类名、方法名、参数名),不需要额外猜测哪个词是符号。
4. 用下面第 3.5 节的"变更分类规则"从 `Change` 列文本里推导 `change`/`old_symbol`/`new_symbol`。
5. 其余列(GDScript/C# 兼容性)按表头映射写进 `payload.gdscript_compatible` 等布尔字段;最后一列的 `` `GH-12345`_ `` 用正则 `GH-(\d+)` 抽出编号写进 `payload.github`。
6. `since_version` 按文件名(`upgrading_to_godot_4.3.rst` → `"4.3"`),`source="official_prose"`,`detection_method="agent_retrieval"`(6.3 已定)。

### 3.5 变更分类规则:一份"能覆盖大多数、但不假装能覆盖全部"的正则表

抽样统计了全部 7 份文件里 `Change` 列的实际句式(不是猜的),常见模板和出现频率大致是:

| 句式(已归一化) | 出现量级 | `change` | 怎么抽 `old_symbol`/`new_symbol` |
|---|---|---|---|
| `Method/Property/Signal/Constant/Enum/Type `` `X` `` removed` | 高频 | `remove` | `old_symbol=X`,`new_symbol=None` |
| `... `` `X` `` renamed to `` `Y` ``` | 中频 | `rename` | `old_symbol=X`,`new_symbol=Y` |
| `... `` `X` `` replaced with/replaced by `` `Y` ``` | 中频 | `replace` | `old_symbol=X`,`new_symbol=Y` |
| `... `` `X` `` split into `` `Y` `` and `` `Z` ``` | 低频 | `split` | `old_symbol=X`,`match_tokens += [Y, Z]`,`new_symbol=None`(拆成两个,没有单一新名字) |
| `Method `` `X` `` adds (a new / new / optional) `` `p` `` parameter` | 高频(单一最大类) | `signature` | `old_symbol=new_symbol=X` |
| `... `` `X` `` changes return type from A to B` / `changes ... type from A to B` | 中频 | `type`(或 `signature`,方法用 `signature`,属性用 `type`,按行首关键字 `Method`/`Property` 区分) | `old_symbol=new_symbol=X` |
| `... `` `X` `` moved to base class/enum `` `Y` ``` | 中频 | `move` | `old_symbol=new_symbol=X`,`owner` 更新为 `Y`(记录在 `payload.moved_to`) |
| `... `` `X` `` removes `` `p` `` parameter` | 低频 | `signature` | 同上 |

**诚实的边界**:抽样也发现了一部分完全自由写的整句说明,不套用任何"主语+反引号符号+固定动词"模板,例如:

> When input events should reach SubViewports and their children, ``SubViewportContainer.mouse_filter`` now needs to be ``MOUSE_FILTER_STOP`` or ``MOUSE_FILTER_PASS``. See `GH-79271`_ for details.

这类行**不属于解析 bug**,是文档本身就这么写的。处理方式:正则表按顺序尝试匹配,**任何一条都没匹配上时不丢弃这一行**,仍然产出一条 `MigrationRule`(`change="behavior"`,`old_symbol=None`,`match_tokens` 用该列所有反引号符号填充,`confidence="needs_review"`),同时记进构建报告的"未分类行"列表。这样人工只需要扫一遍报告里的"未分类"条目,决定要不要给某条单独写抽取规则,而不必担心数据被静默漏掉——这个报告本身也是后续要不要扩充正则表的依据。

### 3.6 散文段落 → `vault/tier_b_prose/`

不在表格里的内容(`paragraph`、`.. warning::`/`.. note::`/`.. danger::` 等 admonition 节点的正文)按 `heading_path` 分组收集,每组内多个段落拼成一条,写入 `vault/tier_b_prose/<source_stem>.prose.jsonl`,每行一个对象:

```json
{"heading_path": ["Breaking changes", "Rendering"], "text": "...", "since_version": "4.3", "source_file": "upgrading_to_godot_4.3.rst", "source": "official_prose"}
```

过滤规则:低于阈值(建议 40 字符)的孤立短句(比如纯粹的"见下表"之类过渡句)不单独成块,直接跳过——不是所有非表格文字都值得占一行,这个阈值本身不精确也不需要精确,只是避免产出大量没有实际信息的碎片。

### 3.7 `upgrading_to_godot_4.rst`:只做两件事,不跑通用抽取

按 [build/README.md 第 1 节和 6.4 节](README.md) 已经定的边界:

1. **整篇复制**到 `artifacts/agent_context/upgrading_to_godot_4.rst`(纯文件拷贝,不解析)。
2. 用同一个 docutils 解析结果,定位 `title.astext() == "Updating shaders"` 的 section 子树,**只**对这个子树跑 3.6 节的散文抽取(写入 `vault/tier_b_prose/upgrading_to_godot_4.rst.updating_shaders.prose.jsonl`),**不**对它跑 3.4/3.5 的表格/正则抽取——[build/README.md 6.4](README.md) 里那 4 行结构化数据是人工读过这一小节之后判断出来的语义(比如"`vertex()` 拆成 `start()`+`process()`"根本不是这份文件里的表格行,是散文里的一句话,没有正则能安全归纳出"这是一次函数拆分"这种判断),**不是**代码自动抽取的产物。做法:把这 4 行当成和 `tier_a_manual/*.yaml` 同类的人工维护小文件(建议新增 `vault/tier_a_manual/shader_3to4_carveout.yaml`,`insert`-only,字段结构和 `known_traps.yaml` 一致,`source` 固定写 `official_prose_3to4_shader`),`build_tier_a.py` 按普通 YAML 源读取,和 cpp/json/rst 三路一起合并写库,不需要给 `parse_upgrading_docs.py` 加一条"自动识别 vertex 拆分成两个函数"的特殊正则。
   跑 3.6 散文抽取时,如果一段文字明显是在复述这 4 行手工条目里已经写过的事实(简单启发式:段落文本里同时出现某条目 `match_tokens` 里两个以上关键词),跳过不重复落盘——避免同一件事在 SQL 行和向量库原材料里各存一份还互相打不通。

---

## 4. YAML:`yaml.safe_load` + 默认值兜底

`tier_a_manual/*.yaml` 已经接近最终表结构(见当前 [`semantic_rewrites.yaml`](../vault/tier_a_manual/semantic_rewrites.yaml)),`build_tier_a.py` 里这一路只需要:

1. `yaml.safe_load(path.read_text())` 读出 `known_traps` / `semantic_rewrites` 两个列表(`build_pipeline_notes` 键跳过,不编译,build/README.md 8.3 已定)。
2. 逐条把 YAML 字段映射到 `MigrationRule` 字段:`kind` → `rule_kind`,`trigger.symbol` 同时写入 `old_symbol` 和 `match_tokens[0]`,`action` → `system_action`(`detection_method` 是 `static_scan_post_l0`/`verify_error_filter` 的条目)或 `agent_action`(`detection_method=agent_retrieval*` 的条目),`since_version` 算出对应的 `since_version_code`(调用 `rag.version_codec.version_to_code`,不要在这里重新实现一份换算)。
3. `detection_method` 是 `not_actively_handled`/`preflight_probe_recommended` 的条目,读出来但不追加进要写库的列表(build/README.md 第 1 节:这两类"不入库",只在构建报告里打印一句"跳过 N 条存档条目"确认没有漏读)。

这一路不需要额外的第三方库(`PyYAML` 是唯一依赖),也不需要处理"意外格式"——YAML 是人工维护的,格式错误应该在 `yaml.safe_load` 阶段直接报错退出,不做兼容兜底。

---

## 5. 依赖清单(已写入 `rag/pyproject.toml` 的 `build` 依赖组)

| 包 | 用在哪 | 备注 |
|---|---|---|
| `docutils` | `parse_upgrading_docs.py` | 纯 Python,无需编译工具链 |
| `PyYAML` | YAML 读取(`build_tier_a.py` 内) | 标准选择,`safe_load` 已经足够,不需要 `full_load` |
| `requests` | 未来"定期从官方仓库拉取"刷新 vault 用(build_all.sh 目前还是空的) | 今天没有脚本用到,先占位在依赖组里,免得以后加着急 |
| `GitPython` | 同上,clone/checkout godot-docs 指定 tag 用 | 同上,先占位 |

`retriever/` 需要的 `pydantic`、`lancedb` 不在这个依赖组里——那两个是运行时依赖,写在 `[project.dependencies]`,worker 镜像要带;这里列的四个只在本机 build 时用,worker 镜像不带,和 [rag/README.md](../README.md) 的"重/轻依赖分离"设计对应。

---

## 6. 不在这份文档里回答的问题

- 每个字段具体叫什么、`source` 允许哪些取值、`detection_method` 怎么分流 → [build/README.md](README.md)。
- 解析完的行怎么被检索、A/B 两层怎么融合 → [retriever/docs/](../retriever/docs/README.md)。
- `rag` 包怎么装、`uv` 依赖组怎么分 → [rag/README.md](../README.md)「开发环境」一节 + [`rag/pyproject.toml`](../pyproject.toml)。
