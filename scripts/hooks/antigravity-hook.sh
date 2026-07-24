#!/usr/bin/env bash
# =============================================================================
# Antigravity(反重力) IDE → petgen 桌宠集成钩子
# =============================================================================
# 用法:
#   antigravity-hook.sh thinking|responding|error|completed [TITLE] [DETAIL]
# 往 $PETGEN_DATA_DIR（默认 ~/.petgen）/task-events.jsonl 追加一条事件。
#
# 通常不用直接调用——运行 ./scripts/hooks/install-hooks.sh 会把 Stop 钩子
# 写进 ~/.gemini/config/hooks.json（键 petgen-notify）。
# =============================================================================
set -euo pipefail

KIND="${1:-completed}"
TITLE="${2:-}"
DETAIL="${3-}"
SOURCE="antigravity"

case "$KIND" in
  thinking)   EVENT_KIND="ai_thinking" ;;
  responding) EVENT_KIND="ai_responding" ;;
  error)      EVENT_KIND="ai_error" ;;
  *)          EVENT_KIND="task_completed" ;;
esac

if [ -z "$TITLE" ]; then
  case "$EVENT_KIND" in
    ai_thinking)    TITLE="Antigravity 正在思考..." ;;
    ai_responding)  TITLE="Antigravity 正在回复" ;;
    ai_error)       TITLE="Antigravity 遇到了错误" ;;
    task_completed) TITLE="Antigravity 任务完成" ;;
  esac
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$SCRIPT_DIR/../petgen-event.sh" "$EVENT_KIND" "$TITLE" "$DETAIL" "$SOURCE"
