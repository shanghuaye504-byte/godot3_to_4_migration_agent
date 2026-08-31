# 本轮评测上下文

粗召回锁定 20+20、bm25:vector = 0.3:0.7。

对照：identity vs minilm_l6（已锁定：生产保持 identity）。
A 层 Recall@5=0.883 / @8=0.923 / @15=0.993（不采纳 @4）。B 层 rerank_k ∈ {2,3,5}。Prec_GT 分母是 |GT|。

生产 YAML 先别改。
