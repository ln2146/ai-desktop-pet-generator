#!/usr/bin/env bash
# =============================================================================
# Codex CLI → petgen 桌宠集成钩子
# =============================================================================
# 用法:
#   codex-hook.sh thinking|responding|waiting|error|idle|completed [TITLE] [DETAIL]
# 往 $PETGEN_DATA_DIR（默认 ~/.petgen）/task-events.jsonl 追加一条事件。
#
# 通常不用直接调用——运行 ./scripts/hooks/install-hooks.sh 会把
# codex-notify-wrapper.sh 接进 ~/.codex/config.toml 的 notify，由它在
# 每个 turn 结束时转发事件（并链式保留你原有的 notify 程序）。
# =============================================================================
set -euo pipefail

KIND="${1:-completed}"
TITLE="${2:-}"
DETAIL="${3-}"
SOURCE="codex"

case "$KIND" in
  thinking)   EVENT_KIND="ai_thinking" ;;
  responding) EVENT_KIND="ai_responding" ;;
  waiting)    EVENT_KIND="ai_waiting" ;;
  error)      EVENT_KIND="ai_error" ;;
  idle)       EVENT_KIND="ai_idle" ;;
  completed)  EVENT_KIND="task_completed" ;;
  *)          EVENT_KIND="custom" ;;
esac

if [ -z "$TITLE" ]; then
  case "$EVENT_KIND" in
    ai_thinking)    TITLE="Codex 正在思考..." ;;
    ai_responding)  TITLE="Codex 正在回复" ;;
    ai_waiting)     TITLE="等待输入" ;;
    ai_error)       TITLE="Codex 遇到了错误" ;;
    ai_idle)        TITLE="Codex 空闲中" ;;
    task_completed) TITLE="Codex 任务完成" ;;
    *)              TITLE="Codex 事件" ;;
  esac
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$SCRIPT_DIR/../petgen-event.sh" "$EVENT_KIND" "$TITLE" "$DETAIL" "$SOURCE"
