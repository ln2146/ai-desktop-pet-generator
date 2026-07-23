#!/usr/bin/env bash
# Append one AI/agent task event to the petgen event inbox so the floating pet
# reacts (thinking->busy, responding->attentive, completed->happy, error->error).
#
# Usage:  petgen-event.sh KIND TITLE [DETAIL] [SOURCE]
#   KIND   ai_thinking | ai_responding | ai_waiting | ai_idle | ai_error |
#          task_completed | custom
#   SOURCE claude_code | codex | copilot | glm | manual | ... (any string ok)
#
# The inbox path MUST match petgen.datadir.data_dir(): $PETGEN_DATA_DIR else ~/.petgen
#
# Example Claude Code settings.json hooks (wire the pet to your coding agent):
#   "hooks": {
#     "PreToolUse":  [{"hooks":[{"type":"command","command":"/abs/path/petgen-event.sh ai_thinking \"Claude Code 思考中\" \"\" claude_code"}]}],
#     "PostToolUse": [{"hooks":[{"type":"command","command":"/abs/path/petgen-event.sh ai_responding \"Claude Code 回复中\" \"\" claude_code"}]}],
#     "Stop":        [{"hooks":[{"type":"command","command":"/abs/path/petgen-event.sh task_completed \"Claude Code 完成了一轮任务\" \"\" claude_code"}]}]
#   }
set -euo pipefail
KIND="${1:?usage: $0 KIND TITLE [DETAIL] [SOURCE]}"
TITLE="${2:?missing TITLE}"
DETAIL="${3-}"
SOURCE="${4:-manual}"
DATA_DIR="${PETGEN_DATA_DIR:-$HOME/.petgen}"
mkdir -p "$DATA_DIR"
touch "$DATA_DIR/task-events.jsonl"
python3 - "$KIND" "$TITLE" "$DETAIL" "$SOURCE" >> "$DATA_DIR/task-events.jsonl" <<'PY'
import json
import sys
import uuid
from datetime import datetime, timezone

kind, title, detail, source = sys.argv[1:5]
print(
    json.dumps(
        {
            "id": str(uuid.uuid4()),
            "kind": kind,
            "title": title,
            "detail": detail or None,
            "source": source or None,
            "createdAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        },
        ensure_ascii=False,
    )
)
PY
