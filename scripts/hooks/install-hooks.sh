#!/usr/bin/env bash
# =============================================================================
# petgen — 一键接通 Claude Code / Codex / Antigravity 的桌宠钩子（幂等）
# =============================================================================
# 以「追加/共存」方式接线：不会覆盖你已有的钩子配置（例如 ai-pet-reminder
# 等其他桌宠的接入），三处配置文件改动前自动备份为 *.bak.<时间戳>。
# 运行: ./scripts/hooks/install-hooks.sh
# 撤销: 用对应的 *.bak.* 备份恢复即可。
# =============================================================================
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HOOKS_DIR="$ROOT_DIR/scripts/hooks"
TS="$(date +%Y%m%d-%H%M%S)"
DATA_DIR="${PETGEN_DATA_DIR:-$HOME/.petgen}"
G=$'\033[0;32m'; Y=$'\033[0;33m'; N=$'\033[0m'
ok()   { echo -e "${G}✅ $*${N}"; }
warn() { echo -e "${Y}⚠️  $*${N}"; }

chmod +x "$HOOKS_DIR"/*.sh 2>/dev/null || true
mkdir -p "$DATA_DIR"
ok "钩子脚本已设可执行权限；数据目录 $DATA_DIR 就绪"
echo ""

# ===================== Claude Code =====================
echo "📎 Claude Code"
CS="$HOME/.claude/settings.json"
CLAUDE_HOOK="$HOOKS_DIR/claude-code-hook.sh"
if [ -f "$CS" ]; then
  if grep -qF "$CLAUDE_HOOK" "$CS" 2>/dev/null; then
    ok "已接通，跳过（幂等）"
  else
    cp "$CS" "$CS.bak.$TS"
    python3 - "$CLAUDE_HOOK" <<'PY'
import json, os, sys
hook = sys.argv[1]
p = os.path.expanduser('~/.claude/settings.json')
d = json.load(open(p, encoding='utf-8'))
hooks = d.setdefault('hooks', {})
# 追加（而非覆盖）钩子组，保留任何已有配置
hooks.setdefault('Stop', []).append(
    {"hooks": [{"type": "command", "command": hook + ' completed "Claude 任务完成"'}]})
hooks.setdefault('SubagentStop', []).append(
    {"hooks": [{"type": "command", "command": hook + ' completed "Claude 子任务完成"'}]})
json.dump(d, open(p, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
PY
    ok "已追加 Stop / SubagentStop hooks（保留原有钩子；备份 $CS.bak.${TS}）"
  fi
else warn "未找到 ~/.claude/settings.json，跳过"; fi
echo ""

# ===================== Codex =====================
echo "📎 Codex"
CT="$HOME/.codex/config.toml"
WRAP="$HOOKS_DIR/codex-notify-wrapper.sh"
if [ -f "$CT" ]; then
  if grep -qF "$WRAP" "$CT" 2>/dev/null; then
    ok "notify 已指向转发器，跳过（幂等）"
  else
    cp "$CT" "$CT.bak.$TS"
    python3 - "$WRAP" "$DATA_DIR" <<'PY'
import os, re, sys
wrap, data_dir = sys.argv[1], sys.argv[2]
p = os.path.expanduser('~/.codex/config.toml')
lines = open(p, encoding='utf-8').read().splitlines(keepends=True)
# notify 只能配一个目标：把原有 notify 程序记下来，供转发器链式调用
for l in lines:
    m = re.match(r'\s*notify\s*=\s*\[\s*"([^"]+)"', l)
    if m and m.group(1) != wrap:
        with open(os.path.join(data_dir, 'codex-notify-original'), 'w', encoding='utf-8') as f:
            f.write(m.group(1) + '\n')
        break
new = 'notify = ["%s", "turn-ended"]\n' % wrap
out, rep = [], False
for l in lines:
    if re.match(r'\s*notify\s*=', l):
        out.append(new); rep = True
    else:
        out.append(l)
if not rep:
    out.append('\n' + new)
open(p, 'w', encoding='utf-8').write(''.join(out))
PY
    chmod 600 "$CT"
    ok "notify 已指向转发器（原有 notify 链式保留：$DATA_DIR/codex-notify-original；备份 $CT.bak.${TS}）"
  fi
else warn "未找到 ~/.codex/config.toml，跳过"; fi
echo ""

# ===================== 反重力 Antigravity =====================
echo "📎 反重力 Antigravity"
AH="$HOME/.gemini/config/hooks.json"
AG_HOOK="$HOOKS_DIR/antigravity-hook.sh"
if [ -d "$HOME/.gemini" ] || [ -d "$HOME/Library/Application Support/Antigravity" ] || [ -d "/Applications/Antigravity.app" ]; then
  mkdir -p "$HOME/.gemini/config"
  if [ -f "$AH" ] && grep -qF "$AG_HOOK" "$AH" 2>/dev/null; then
    ok "已接通，跳过（幂等）"
  else
    [ -f "$AH" ] && cp "$AH" "$AH.bak.$TS"
    python3 - "$AG_HOOK" <<'PY'
import json, os, sys
hook = sys.argv[1]
p = os.path.expanduser('~/.gemini/config/hooks.json')
d = {}
if os.path.exists(p):
    try:
        d = json.load(open(p, encoding='utf-8'))
    except ValueError:
        d = {}
# 独立键 petgen-notify，与其他桌宠（如 ai-pet-notify）共存
d['petgen-notify'] = {"Stop": [{"hooks": [{"type": "command",
    "command": hook + " completed 'Antigravity 任务完成'"}]}]}
json.dump(d, open(p, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
PY
    ok "已写入 ~/.gemini/config/hooks.json（键 petgen-notify；配完请在 Antigravity 跑个任务确认触发）"
  fi
else warn "未检测到 Antigravity（~/.gemini），跳过"; fi
echo ""
ok "完成。已接通: Claude Code / Codex / 反重力 Antigravity。"
ok "验证: 在各工具里跑一轮任务，事件应出现在 $DATA_DIR/task-events.jsonl，桌宠约 2 秒内反应。"
