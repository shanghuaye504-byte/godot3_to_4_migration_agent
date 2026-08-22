stability：repeat 塌陷报告（vertical.json）。

每个 (project, command, cache_state) 一条。
error_lines_set_same / stdout_lines_set_same：各 repeat 行集合是否相同（忽略顺序）；不同为 false。
common_error_order_same：只保留各 repeat 都有的错误行，再比顺序；不同为 false。

escalate:
本文件只报告行集合是否相同、公共错误行顺序是否相同。字段抹除规格仍按 reports/README.md §0.4 由人/模型另写，不由本 analyzer 决定。Fake 产物不得当已确认结论。
