#!/usr/bin/env bash
# =============================================================================
# Codex turn 通知转发器
# =============================================================================
# 由 ~/.codex/config.toml 的 notify 调用，参数 $1 = 事件类型（turn-ended 等）。
# Codex 的 notify 只能配一个目标，所以这里做两件事：
#   1. 链式调用原有 notify 程序（安装器会把原目标记到
#      $PETGEN_DATA_DIR/codex-notify-original，没有则跳过）；
#   2. 额外往桌宠收件箱写一条事件。
# 本脚本永不以非零退出，避免影响 Codex 自身的通知链。
# =============================================================================
set -u
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

ORIG_FILE="${PETGEN_DATA_DIR:-$HOME/.petgen}/codex-notify-original"
ORIG=""
if [ -f "$ORIG_FILE" ]; then
  ORIG="$(head -n1 "$ORIG_FILE" 2>/dev/null || true)"
fi
if [ -n "$ORIG" ] && [ -x "$ORIG" ]; then
  "$ORIG" "$@" 2>/dev/null || true
fi

case "${1:-turn-ended}" in
  turn-ended|completed) "$SCRIPT_DIR/codex-hook.sh" completed "Codex 任务完成" 2>/dev/null || true ;;
  *)                    "$SCRIPT_DIR/codex-hook.sh" responding "Codex 进行中" 2>/dev/null || true ;;
esac
exit 0
