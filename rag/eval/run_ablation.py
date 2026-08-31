"""两阶段离线消融：先扫 B 层通道，再扫 recall_k × rerank_k。

本文件负责：读 eval 集、对 ``RetrieverConfig`` 做拷贝后调用 ``retrieve``、写 markdown 表。

禁止：给 ``RetrievalQuery`` 加字段、复制一份 RRF、改 SQL 模板、把
``retrieval_mode=exact_only`` 当成「纯关键词」。纯关键词是 ``tier_b.channels=bm25``。

调用方：维护者命令行（``--phase a`` / ``--phase b``）。
被调用方：``rag.retriever.retrieve``、``config.load_config``。

对应文档：``rag/retriever/docs/eval.md``、``rag/retriever/docs/config.md``。
"""

from __future__ import annotations


def main(argv: list[str] | None = None) -> int:
    """CLI 入口。

    阶段 A：锁死 YAML 默认 k/权重/identity/阈值关闭，只扫
    ``channels ∈ {bm25, vector, hybrid}``，报 Recall@5。

    阶段 B：固定通道，矩阵 ``recall_k ∈ {5,10,20}`` × ``rerank_k ∈ {1,3,5}``。

    Args:
        argv: 默认 ``sys.argv[1:]``。应支持 ``--phase a|b`` 以及配置路径。

    Returns:
        进程退出码。

    Raises:
        NotImplementedError: 本轮不跑实验。
    """
    raise NotImplementedError("本轮实验入口是 eval/run_eval.py，见 rag/eval/README.md")


if __name__ == "__main__":
    raise SystemExit(main())
