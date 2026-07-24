#!/usr/bin/env bash
# =============================================================================
# Claude Code → petgen 桌宠集成钩子
# =============================================================================
# 用法:
#   claude-code-hook.sh thinking|responding|waiting|error|idle|completed [TITLE] [DETAIL]
# 往 $PETGEN_DATA_DIR（默认 ~/.petgen）/task-events.jsonl 追加一条事件，
# 桌宠约 2 秒内回应（thinking→busy、responding→attentive、completed→happy、error→error）。
#
# 通常不用直接调用——运行 ./scripts/hooks/install-hooks.sh 会自动把它
# 以 Stop / SubagentStop hooks 接进 ~/.claude/settings.json。
# =============================================================================
set -euo pipefail

KIND="${1:-completed}"
TITLE="${2:-}"
DETAIL="${3-}"
SOURCE="claude_code"

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
    ai_thinking)    TITLE="Claude 正在思考..." ;;
    ai_responding)  TITLE="Claude 正在回复" ;;
    ai_waiting)     TITLE="等待输入" ;;
    ai_error)       TITLE="Claude 遇到了错误" ;;
    ai_idle)        TITLE="Claude 空闲中" ;;
    task_completed) TITLE="Claude 任务完成" ;;
    *)              TITLE="Claude Code 事件" ;;
  esac
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$SCRIPT_DIR/../petgen-event.sh" "$EVENT_KIND" "$TITLE" "$DETAIL" "$SOURCE"
