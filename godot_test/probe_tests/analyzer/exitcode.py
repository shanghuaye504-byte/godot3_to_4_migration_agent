"""analyzer/exitcode.py —— rc / signal / timeout 交叉表，含存活性观测。

用法：
    python analyzer/exitcode.py artifacts/<run-id>/N08/ [--out reports/<run-id>/N08/exitcode/]

服务：N08
输入：已落盘的 N08 目录（各 group 的 process-status.json：rc / signal / timed_out / wall_time）
输出：reports/<run-id>/N08/exitcode/

交叉表格子（缺一格不算完成）：
    干净 CleanControl          期望 rc=0
    单文件真错 NP-SYNTAX V2    期望 rc≠0
    项目级真错 NP-SYNTAX V1    期望 rc≠0
    纯假阳性 NP-AUTOLOAD V2    期望 rc=0（「有真错误=否」由 N01 确认后回填，本脚本不预判）
    被 timeout kill 的 V8 步   期望 124/137

另外提取：
    B9：有坏脚本的项目上 V5 是否仍启动成功且 rc=0
    V8 存活性：wall time ≥ timeout，或 rc=134/139，或 stderr 含
               handle_crash: Program crashed with signal 11

本脚本填表，不宣布 exit_code 可否当 success、不写 CONFIRMED。
--debug 禁入正式 verifier 的裁决由人写进 reports/README.md。

禁止：import 实验脚本；修改 artifacts/；写死 fixture 名。
本文件只记录契约，不含实现。
"""
