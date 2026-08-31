"""从 ``artifacts/rules.db`` 机械生成评测集 E1/E2/E3。

本文件负责：反向映射 / 文档回指 / 退化线索，写出评测用例文件。

禁止：修改 retriever 内部（SQL、RRF、YAML 默认值）、读取 ``rag/test/``。
调用方：维护者命令行。
被调用方：只读 ``rules.db``。

对应文档：``rag/retriever/docs/eval.md``、``rag/eval/README.md``。
"""

from __future__ import annotations


def main(argv: list[str] | None = None) -> int:
    """CLI 入口。实现轮解析输出路径、读 rules.db、写 jsonl/yaml。

    Args:
        argv: 默认 ``sys.argv[1:]``。

    Returns:
        进程退出码。

    Raises:
        NotImplementedError: 本轮不生成评测集。
    """
    raise NotImplementedError("见 rag/retriever/docs/eval.md")


if __name__ == "__main__":
    raise SystemExit(main())
