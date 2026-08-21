"""通用 Hook 注册表。

特殊行为进 hook，不为每个 N 写主程序。步骤结束必须撤销自己写入的文件，
除非该步骤的目的就是留下变更（converter、config_version 降级）。当前为骨架。
"""
