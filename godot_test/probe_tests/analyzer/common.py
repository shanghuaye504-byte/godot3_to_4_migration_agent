"""analyzer 共享：行解析与两级 signature 计算。

这是计算 local_signature / noise_signature 的唯一实现点。
实验脚本不参与计算；各 analyzer 脚本从本模块取解析与签名，不各自再写一份。

规格以 README §0.4 为准，实现时不可合并这两步：
  1. 用 noise_signature 做 BG 减法（粗筛引擎噪声）
  2. 用 local_signature + annotations/ 埋点表把 Δ 归入 REAL / CLEAN 桶

local_signature  = sha1(kind | res_path | symbol | normalized_msg)
    保留 res:// 相对路径与符号名；抹掉行号、绝对路径、内存地址、耗时数值
    用途：项目内身份 —— 重复比较、级联去重、Agent 震荡检测

noise_signature  = sha1(kind | msg_template)
    路径、符号名、数值全部占位符化，只留消息模板
    用途：唯一用途是 BG 减法

字段抹除规格由 N09 纵向 + 横向共同裁定，由人写进 reports/README.md，
本模块按已确认规格计算，不自行宣布 CONFIRMED / BG-DRIFT。

禁止：import 实验脚本；修改 artifacts/；写死某个 fixture 名。
本文件只记录契约，不含实现。
"""
