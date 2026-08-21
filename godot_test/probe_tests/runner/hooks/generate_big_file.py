"""generate_big_file：按 YAML 的目标字节数/行数/最大单行长度生成 big.gd 与 longline.gd。

必须按固定间隔插入可转换模式（如 OS.get_ticks_msec()、.instance()），
否则无法区分“文件未被改”与“converter 跳过”。当前为骨架。
"""
