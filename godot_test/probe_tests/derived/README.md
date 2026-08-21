# derived

Manual gate 的可重放产物。每个状态一个目录：

```text
derived/<fixture>@<state>/
├── patch.diff
└── provenance.yaml    Godot 版本 + build hash + 生成时间 + 人工确认记录
```

Runner 应用前校验 build hash；不一致则退回 GUI。若 GUI 写入二进制或不可移植内容，永久退回 manual gate。

占位目录见 NP-ADDON@plugin-enabled/ 与 NP-RESOURCE@uid-baseline/。真正的 patch 要等对应实验跑过 GUI 之后才能生成。
