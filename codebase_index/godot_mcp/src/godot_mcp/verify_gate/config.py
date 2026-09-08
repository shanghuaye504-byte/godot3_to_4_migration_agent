"""`RetryGateConfig` —— 方案文档 §4.1 的 YAML 对应的 dataclass。

```yaml
retry_gate:
  no_progress_window: 3        # 连续 N 轮签名集合完全不变 → NO_PROGRESS_WARN
  oscillation_window: 3        # 见下方"语义限制"，当前不是可调窗口大小
  file_stuck_threshold: 3      # 同一文件被 patch 的次数超过这个值、且相关签名不变 → FILE_STUCK_WARN
  infra_failure_streak_limit: 3   # 连续基础设施失败次数 → CIRCUIT_OPEN
  rounds_limit: 40             # 单会话最大轮次（硬顶）
  cost_limit_usd: 5.0          # 单会话最大花费（硬顶，具体数值按模型定价调整）
```

**待验证标记**：`no_progress_window`/`oscillation_window`/`file_stuck_threshold` 这三个
数字目前没有专门的消融实验支撑，是从通用 Agent 工程经验里取的经验值，不要当成"已验证"
写死在别处。

**`oscillation_window` 的语义限制**：当前实现只识别长度恰为 3 的最小 A→B→A 震荡，把
这个数字改成 5 并不会让算法检测更长周期的震荡（比如 A→B→C→A 的 4 轮循环）。应理解为
"是否识别 A→B→A"这一固定行为的开关，不是可调窗口；要支持更长周期需要另外扩展
`algorithm.py`，不是改这个配置数字就够。
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from pathlib import Path

import yaml


@dataclass(frozen=True)
class RetryGateConfig:
    no_progress_window: int = 3
    oscillation_window: int = 3
    file_stuck_threshold: int = 3
    infra_failure_streak_limit: int = 3
    rounds_limit: int = 40
    cost_limit_usd: float = 5.0


_KNOWN_FIELDS = frozenset(f.name for f in fields(RetryGateConfig))


def load_retry_gate_config(path: Path | None = None) -> RetryGateConfig:
    """从 YAML 读 `retry_gate:` 段，缺省或未传 path 时返回 dataclass 默认值。

    未知字段直接报 ValueError，防止把 `no_progress_widow` 这类拼写错误默默忽略。
    既接受带 `retry_gate:` 外壳的完整 yaml，也接受扁平的字段映射。
    """
    if path is None:
        return RetryGateConfig()

    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"retry_gate config must be a mapping: {path}")

    data = raw.get("retry_gate", raw)
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ValueError(f"retry_gate must be a mapping: {path}")

    unknown = set(data) - _KNOWN_FIELDS
    if unknown:
        raise ValueError(f"unknown retry_gate fields: {sorted(unknown)}")

    kwargs: dict[str, object] = {}
    for key, value in data.items():
        if key == "cost_limit_usd":
            kwargs[key] = float(value)
        else:
            kwargs[key] = int(value)
    return RetryGateConfig(**kwargs)  # type: ignore[arg-type]
