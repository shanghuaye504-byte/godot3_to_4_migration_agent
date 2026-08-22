# derived

Manual gate 的可重放产物。每个状态一个目录：

```text
derived/<fixture>@<state>/
├── patch.diff
└── provenance.yaml    Godot 版本 + build hash + 生成时间 + 人工确认记录
```

`probe.apply_derived` 应用前校验 build hash（对的是当前可执行文件，不是 git commit）；空或不一致则退回 GUI。若 GUI 写入二进制或不可移植内容，永久退回 manual gate。判定细则见 ARCHITECTURE.md §7。

占位目录见 NP-ADDON@plugin-enabled/ 与 NP-RESOURCE@uid-baseline/。真正的 patch 要等对应实验跑过 GUI 之后才能生成。
