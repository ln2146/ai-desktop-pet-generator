from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def compact_text(value: object, *, limit: int = 80) -> str:
    text = str(value or "")
    text = re.sub(r"\s+", " ", text).strip(" -:\t\r\n")
    text = _strip_inline_markdown(text)
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def format_duration(ms: object) -> str:
    if not isinstance(ms, (int, float)) or ms < 0:
        return ""
    seconds = int(round(float(ms) / 1000))
    if seconds < 60:
        return f"耗时 {seconds} 秒"
    minutes, rest = divmod(seconds, 60)
    if minutes < 60:
        return f"耗时 {minutes} 分 {rest} 秒" if rest else f"耗时 {minutes} 分"
    hours, minutes = divmod(minutes, 60)
    return f"耗时 {hours} 小时 {minutes} 分" if minutes else f"耗时 {hours} 小时"


def summarize_agent_message(text: object, *, limit: int = 84) -> str:
    if not isinstance(text, str):
        return ""
    lines = [line.strip(" -•\t") for line in text.splitlines()]
    lines = [line for line in lines if line]
    if not lines:
        return ""
    preferred = _prefer_human_line(lines)
    return compact_text(preferred, limit=limit)


def codex_event_from_notify_args(
    args: list[str], *, home: Path | None = None
) -> tuple[str, str, str | None]:
    payload = _first_payload(args)
    event_type = _event_type(args, payload)
    done_types = {None, "", "agent-turn-complete", "turn-ended", "completed", "task_complete"}
    kind = "task_completed" if event_type in done_types else "ai_responding"
    if kind != "task_completed":
        title = _codex_in_progress_title(event_type)
        return kind, title, None

    completion = (
        payload
        if _payload_get(payload, "last_agent_message", "message", "summary")
        else _latest_codex_completion(home)
    )
    final = summarize_agent_message(
        _payload_get(completion, "last_agent_message", "message", "summary")
    )
    project = _project_name(_payload_get(completion, "cwd", "workspace"))
    subject = f"已完成：{final}" if final else "回合完成，可以查看最新回复"
    title = f"{project} {subject}" if project else subject
    detail = _detail_from_parts(
        format_duration(_payload_get(completion, "duration_ms")),
    )
    return kind, title, detail


def claude_event_from_hook_input(
    payload: dict[str, Any] | None,
    *,
    event_name: str,
    fallback_title: str,
) -> tuple[str, str, str | None]:
    payload = payload or {}
    event = str(
        _payload_get(payload, "hook_event_name", "event_name", "event", "type") or event_name
    )
    kind = "task_completed" if event in {"Stop", "SubagentStop", "completed"} else "custom"
    if kind != "task_completed":
        return kind, fallback_title, None

    transcript_path = _payload_get(payload, "transcript_path", "transcriptPath")
    transcript = _read_claude_transcript(Path(str(transcript_path))) if transcript_path else {}
    user_task = summarize_agent_message(transcript.get("last_user"), limit=70)
    final = summarize_agent_message(transcript.get("last_assistant"), limit=82)
    label = "子任务完成" if event == "SubagentStop" else "已完成"
    project = _project_name(_payload_get(payload, "cwd", "workspace", "workspacePaths"))
    subject = (
        f"{label}：{final}" if final else (f"{label}：{user_task}" if user_task else fallback_title)
    )
    title = f"{project} {subject}" if project else subject
    detail = _detail_from_parts(
        f"任务：{user_task}" if user_task and final else "",
        format_duration(
            _payload_get(payload, "duration_ms", "elapsed_ms", "durationMs", "elapsedMs")
        ),
    )
    return kind, title, detail


def antigravity_event_from_hook_input(
    payload: dict[str, Any] | None,
    *,
    event_name: str,
    fallback_title: str,
) -> tuple[str, str, str | None]:
    payload = payload or {}
    event = str(
        _payload_get(payload, "hook_event_name", "event_name", "event", "type") or event_name
    )
    kind = (
        "task_completed"
        if event in {"Stop", "completed", "task_completed", "task_complete"}
        else "custom"
    )
    if kind != "task_completed":
        return kind, fallback_title, None

    transcript = (
        _read_antigravity_transcript(Path(str(payload["transcriptPath"])))
        if payload.get("transcriptPath")
        else {}
    )
    raw_final = _payload_get(
        payload,
        "last_agent_message",
        "summary",
        "message",
        "result",
        "response",
        "text",
    )
    final = summarize_agent_message(raw_final or transcript.get("last_assistant"))
    user_task = summarize_agent_message(transcript.get("last_user"), limit=70)
    project = _project_name(
        _payload_get(
            payload,
            "workspacePaths",
            "cwd",
            "workspace",
            "workspace_path",
            "project_path",
            "project",
        )
    )
    subject = (
        f"已完成：{final}" if final else (f"已完成：{user_task}" if user_task else fallback_title)
    )
    title = f"{project} {subject}" if project else subject
    detail = _detail_from_parts(
        format_duration(
            _payload_get(payload, "duration_ms", "elapsed_ms", "durationMs", "elapsedMs")
        ),
        _antigravity_stop_detail(payload),
    )
    return kind, title, detail


def _first_payload(args: list[str]) -> dict[str, Any]:
    for arg in args:
        try:
            raw = json.loads(arg)
        except ValueError:
            continue
        if isinstance(raw, dict):
            nested = raw.get("payload")
            return nested if isinstance(nested, dict) else raw
    return {}


def _event_type(args: list[str], payload: dict[str, Any]) -> object:
    if "type" in payload:
        return payload.get("type")
    for arg in args:
        try:
            json.loads(arg)
        except ValueError:
            return arg
    return None


def _payload_get(payload: dict[str, Any], *keys: str) -> object:
    for key in keys:
        value = payload.get(key)
        if value not in (None, ""):
            return value
    return None


def _codex_in_progress_title(event_type: object) -> str:
    if event_type:
        return f"需要处理：{compact_text(event_type, limit=36)}"
    return "仍在处理中"


def _prefer_human_line(lines: list[str]) -> str:
    for prefix in ("summary=", "qa_note=", "result=", "changed=", "done=", "完成", "已"):
        for line in lines:
            if line.startswith(prefix):
                return line.split("=", 1)[1] if "=" in line else line
    return lines[0]


def _strip_inline_markdown(text: str) -> str:
    text = re.sub(r"(\*\*|__)(.*?)\1", r"\2", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    return text


def _detail_from_parts(*parts: str) -> str | None:
    text = "；".join(part for part in parts if part)
    return text or None


def _project_name(value: object) -> str:
    if not value:
        return ""
    if isinstance(value, list):
        value = next((item for item in value if item), "")
    name = Path(str(value)).name
    return name or ""


def _antigravity_stop_detail(payload: dict[str, Any]) -> str:
    reason = compact_text(
        _payload_get(payload, "terminationReason", "termination_reason"), limit=36
    )
    error = compact_text(_payload_get(payload, "error"), limit=70)
    parts: list[str] = []
    if reason and reason != "model_stop":
        parts.append(f"停止原因：{reason}")
    if error:
        parts.append(f"错误：{error}")
    return "；".join(parts)


def _read_antigravity_transcript(path: Path) -> dict[str, str]:
    try:
        with path.open("rb") as handle:
            handle.seek(0, 2)
            size = handle.tell()
            handle.seek(max(0, size - 1024 * 1024))
            raw_lines = handle.read().decode("utf-8", errors="replace").splitlines()
    except OSError:
        return {}

    last_user = ""
    assistant_replies: list[str] = []
    for line in raw_lines[-500:]:
        try:
            item = json.loads(line)
        except ValueError:
            continue
        if not isinstance(item, dict):
            continue
        text = str(item.get("content") or "")
        if not text:
            continue
        source = item.get("source")
        item_type = item.get("type")
        if source == "USER_EXPLICIT" and item_type == "USER_INPUT":
            last_user = _antigravity_user_request(text)
        elif source == "MODEL" and item_type == "PLANNER_RESPONSE":
            assistant_replies.append(text)
    return {"last_user": last_user, "last_assistant": _best_agent_reply(assistant_replies)}


def _antigravity_user_request(text: str) -> str:
    match = re.search(r"<USER_REQUEST>\s*(.*?)\s*</USER_REQUEST>", text, flags=re.S)
    return match.group(1).strip() if match else text.strip()


def _best_agent_reply(replies: list[str]) -> str:
    for reply in reversed(replies):
        if not _is_low_signal_agent_reply(reply):
            return reply
    return replies[-1] if replies else ""


def _is_low_signal_agent_reply(text: str) -> bool:
    compact = compact_text(text, limit=160)
    if not compact:
        return True
    low_signal_markers = (
        "随时告诉我",
        "如果您后续",
        "后续在使用中",
        "后台正常运行中",
        "平稳运行中",
    )
    return any(marker in compact for marker in low_signal_markers)


def _read_claude_transcript(path: Path) -> dict[str, str]:
    try:
        with path.open("rb") as handle:
            handle.seek(0, 2)
            size = handle.tell()
            handle.seek(max(0, size - 1024 * 1024))
            raw_lines = handle.read().decode("utf-8", errors="replace").splitlines()
    except OSError:
        return {}

    last_user = ""
    assistant_replies: list[str] = []
    for line in raw_lines[-300:]:
        try:
            item = json.loads(line)
        except ValueError:
            continue
        role = ((item.get("message") or {}) if isinstance(item.get("message"), dict) else {}).get(
            "role"
        )
        text = _message_text(item)
        if not text:
            continue
        if role == "user" and item.get("isSidechain") is not True:
            last_user = text
        elif role == "assistant":
            assistant_replies.append(text)
    return {"last_user": last_user, "last_assistant": _best_agent_reply(assistant_replies)}


def _latest_codex_completion(home: Path | None = None) -> dict[str, Any]:
    sessions = (home or Path.home()) / ".codex" / "sessions"
    if not sessions.is_dir():
        return {}
    candidates: list[tuple[float, Path]] = []
    try:
        for path in sessions.glob("**/*.jsonl"):
            try:
                candidates.append((path.stat().st_mtime, path))
            except OSError:
                continue
    except OSError:
        return {}
    for _mtime, path in sorted(candidates, reverse=True)[:8]:
        completion = _codex_completion_from_file(path)
        if completion:
            return completion
    return {}


def _codex_completion_from_file(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as handle:
            handle.seek(0, 2)
            size = handle.tell()
            handle.seek(0)
            head = handle.read(min(size, 256 * 1024))
            handle.seek(max(0, size - 1024 * 1024))
            tail = handle.read()
            lines = (head + b"\n" + tail).decode("utf-8", errors="replace").splitlines()
    except OSError:
        return {}
    cwd = ""
    for line in lines:
        try:
            item = json.loads(line)
        except ValueError:
            continue
        if not isinstance(item, dict):
            continue
        payload = item.get("payload")
        cwd_value = item.get("cwd")
        if not cwd_value and isinstance(payload, dict):
            cwd_value = payload.get("cwd")
        if isinstance(cwd_value, str) and cwd_value:
            cwd = cwd_value
    for line in reversed(lines[-600:]):
        try:
            item = json.loads(line)
        except ValueError:
            continue
        if not isinstance(item, dict):
            continue
        payload = item.get("payload")
        if isinstance(payload, dict) and payload.get("type") == "task_complete":
            if cwd and "cwd" not in payload:
                payload = {**payload, "cwd": cwd}
            return payload
    return {}


def _message_text(item: dict[str, Any]) -> str:
    message = item.get("message")
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    chunks: list[str] = []
    for part in content:
        if (
            isinstance(part, dict)
            and part.get("type") == "text"
            and isinstance(part.get("text"), str)
        ):
            chunks.append(part["text"])
    return "\n".join(chunks)
