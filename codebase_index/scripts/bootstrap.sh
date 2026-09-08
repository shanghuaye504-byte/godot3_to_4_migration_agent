#!/usr/bin/env bash
# 一键安装两个子系统的开发依赖（index/ 与 godot_mcp/ 均为 Python + uv）。
set -euo pipefail

cd "$(dirname "$0")/.."

echo "==> installing Layer 2 (index/) deps"
uv sync --directory index --all-groups

echo "==> installing Layer 3 (godot_mcp/) deps"
uv sync --directory godot_mcp --all-groups

echo "==> done. 记得 cp config.example.yaml config.yaml 并按需修改。"
