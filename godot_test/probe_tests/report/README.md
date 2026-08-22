# report/

Analyzer 规程化中间结果，按实验分目录：

```text
report/<phase>/<N>/
```

例如 `report/phase1/N09/`。由事后进程写入：

```text
python Analyzer.py --path artifacts/<run-id>/<N>/
```

本目录不是：

- `artifacts/`（那是 kernel 原始测量）
- `runner/report/`（那是通用脚本）
- `reports/README.md`（那是人写实验报告）
