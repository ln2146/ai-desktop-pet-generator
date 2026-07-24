# AI 工具接入

`petgen app` 内置事件总线。任何外部进程往 `~/.petgen/task-events.jsonl` 追加一行 JSON，桌宠约 2 秒内会按事件类型切换表情并弹出气泡。

## GUI 接入

启动 App 后打开：

```text
设置 → 🔌 工具接入
```

支持三类工具：

- Claude Code：追加 `Stop` / `SubagentStop` hooks。
- Codex：把 `~/.codex/config.toml` 的 top-level `notify` 指向 `petgen codex-notify`，并链式保留原 notify。
- Antigravity：写入 `~/.gemini/config/hooks.json` 的独立键 `petgen-notify`。该渠道的实际触发仍建议真机验证。

配置写入以追加/共存为原则，不碰其他桌宠或用户已有 hook。改动前会自动创建 `*.bak.<时间戳>` 备份。

## CLI 接入

```bash
petgen tools status all
petgen tools connect all
petgen tools disconnect all
```

也可以只操作单个工具：

```bash
petgen tools status claude
petgen tools connect codex
petgen tools disconnect antigravity
```

四种状态含义：

- `connected`：已接通。
- `stale`：检测到 petgen 配置，但命令路径已失效，通常是 venv 迁移后需要重连。
- `not_connected`：检测到工具，但尚未接通。
- `not_detected`：未检测到对应工具配置目录。

## 事件协议

事件文件默认位于：

```text
~/.petgen/task-events.jsonl
```

每行一条 JSON：

```json
{
  "id": "unique-event-id",
  "kind": "task_completed",
  "title": "Codex 任务完成",
  "detail": null,
  "source": "codex",
  "createdAt": "2026-07-24T12:00:00Z"
}
```

常用 `kind`：

- `ai_thinking` → busy
- `ai_responding` → attentive
- `ai_waiting` / `ai_idle` → idle
- `task_completed` → happy
- `ai_error` → error
- `custom` → happy

手写事件：

```bash
petgen event task_completed "完成一轮" "" manual
```

hook 目标命令必须永远返回 0，避免阻塞 Claude Code、Codex 等宿主工具。因此 `petgen event` 和 `petgen codex-notify` 会把写入失败打印为 warning，而不是以非零退出。

## 旧 bash hook 迁移

早期 `scripts/hooks/install-hooks.sh` 会把仓库绝对路径写进配置。新版 GUI/CLI 接线改为调用 `petgen` 可执行文件本身，随 pip 升级更稳。

如果旧配置仍然存在，可能出现双份事件。迁移建议：

- Claude Code：删除 `~/.claude/settings.json` 中 command 含 `ai-desktop-pet-generator/scripts/hooks/` 的 hook 组。
- Codex：把 `notify` 还原为安装前的值，原值可能记录在 `~/.petgen/codex-notify-original`。
- Antigravity：GUI/CLI 接通会覆盖同名 `petgen-notify` 键，通常无需额外处理。

注意：工具接线固定写默认 `~/.petgen` 事件文件，不跟随 App 的 `--data-dir`。接线仅支持 macOS / Linux，Windows 上会拒绝连接。
