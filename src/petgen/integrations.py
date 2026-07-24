"""One-click wiring between petgen and AI coding tools (Claude Code / Codex / Antigravity).

Pure Python, Qt-free, and fully path-injectable: every public function takes an
optional ``home`` argument (defaulting to ``Path.home()``) so tests can point it
at a tmp directory instead of monkeypatching the real home.

Design contracts (see docs + scripts/hooks/install-hooks.sh for the bash-era
equivalent this supersedes for pip-installed users):

* Hook commands reference the ``petgen`` executable itself (``petgen event ...``),
  resolved via ``shutil.which`` with a ``sys.executable -m petgen`` fallback, so
  wiring keeps working after pip upgrades and does not depend on repo paths.
* Wiring is additive/coexistent: Claude hooks are appended (never replaced),
  Antigravity uses its own top-level ``petgen-notify`` key, and our own entries
  are identified by a command containing both ``petgen`` and the source token —
  other pets' hooks (e.g. ai-pet-reminder) are never touched.
* Every mutating operation backs the target file up to ``*.bak.<timestamp>``
  first and writes atomically (tmp + ``os.replace``, original mode preserved;
  Codex config forced to 0600). Corrupted JSON is refused, never overwritten.
"""
from __future__ import annotations

import enum
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

TOOLS = ("claude", "codex", "antigravity")

TOOL_LABELS = {
    "claude": "Claude Code",
    "codex": "Codex",
    "antigravity": "Antigravity",
}

TOOL_SOURCES = {
    "claude": "claude_code",
    "codex": "codex",
    "antigravity": "antigravity",
}

TOOL_TITLES = {
    "claude": "Claude 任务完成",
    "claude_subagent": "Claude 子任务完成",
    "codex": "Codex 任务完成",
    "antigravity": "Antigravity 任务完成",
}

#: Existence of any of these marks Antigravity as installed. Entries starting
#: with "~" resolve against the injected home; absolute paths are used as-is.
#: Kept as a module constant so tests can swap it deterministically.
ANTIGRAVITY_DETECT_PATHS = (
    "~/.gemini",
    "~/Library/Application Support/Antigravity",
    "/Applications/Antigravity.app",
)

SIDECAR_NAME = "codex-notify-original"

_CLAUDE_HOOK_EVENTS = ("Stop", "SubagentStop")


class ToolStatus(str, enum.Enum):
    CONNECTED = "connected"
    STALE = "stale"  # marker present but the petgen entry point no longer exists
    NOT_CONNECTED = "not_connected"
    NOT_DETECTED = "not_detected"


@dataclass(frozen=True)
class ToolState:
    tool: str
    status: ToolStatus
    detail: str = ""


class IntegrationsError(RuntimeError):
    """Raised when wiring cannot proceed (tool missing, corrupted config, ...)."""


# --- event inbox writer (the payload every hook command emits) ----------------


def append_event(
    kind: str,
    title: str,
    detail: str | None = None,
    source: str | None = None,
) -> dict:
    """Append one task event to the pet inbox; 1:1 with scripts/petgen-event.sh.

    Empty ``detail``/``source`` degrade to JSON null; the inbox follows
    ``$PETGEN_DATA_DIR`` (default ``~/.petgen``) exactly like the shell script.
    """
    from petgen.datadir import event_inbox_path

    event = {
        "id": str(uuid.uuid4()),
        "kind": kind,
        "title": title,
        "detail": detail or None,
        "source": source or None,
        "createdAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    inbox = event_inbox_path()
    inbox.parent.mkdir(parents=True, exist_ok=True)
    with inbox.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")
    return event


# --- generic helpers ---------------------------------------------------------


def _home(home: Path | None) -> Path:
    return Path(home) if home is not None else Path.home()


def _require_posix() -> None:
    if sys.platform == "win32":
        raise IntegrationsError("工具接线暂不支持 Windows（钩子 shell 语义不兼容）")


def petgen_argv() -> list[str]:
    """Absolute argv prefix that invokes this petgen install."""
    found = shutil.which("petgen")
    if found:
        return [found]
    return [sys.executable, "-m", "petgen"]


def _hook_command(source: str, title: str) -> str:
    argv = [*petgen_argv(), "event", "task_completed", title, "", source]
    return shlex.join(argv)


def _is_petgen_command(command: str, source: str) -> bool:
    """Marker test: our entries contain both 'petgen' and the source token.

    Other pets' hooks (e.g. ai-pet-reminder's '...claude-code-hook.sh ...')
    contain neither the substring 'petgen' nor 'claude_code', so they never match.
    """
    return "petgen" in command and source in command


def _command_entry_exists(command: str) -> bool:
    try:
        parts = shlex.split(command)
    except ValueError:
        return False
    return bool(parts) and Path(parts[0]).exists()


def _backup(path: Path) -> Path | None:
    """Copy ``path`` to ``<name>.bak.<timestamp>``; None when nothing to back up."""
    if not path.exists():
        return None
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    candidate = path.with_name(f"{path.name}.bak.{stamp}")
    n = 1
    while candidate.exists():
        candidate = path.with_name(f"{path.name}.bak.{stamp}-{n}")
        n += 1
    candidate.write_bytes(path.read_bytes())
    return candidate


def _atomic_write(path: Path, text: str, *, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp")
    tmp.write_text(text, encoding="utf-8")
    if mode is not None:
        os.chmod(tmp, mode)
    elif path.exists():
        try:
            os.chmod(tmp, path.stat().st_mode & 0o7777)
        except OSError:
            pass
    os.replace(tmp, path)


def _read_json_dict(path: Path) -> dict:
    """Load a JSON object; raise IntegrationsError (with backup hint) when unusable."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise IntegrationsError(f"{path} 已损坏（{exc}）；请手动修复或用 *.bak.* 备份还原后再试") from exc
    if not isinstance(data, dict):
        raise IntegrationsError(f"{path} 不是 JSON 对象；请手动修复或用 *.bak.* 备份还原后再试")
    return data


# --- config file locations ---------------------------------------------------


def claude_settings_path(home: Path | None = None) -> Path:
    return _home(home) / ".claude" / "settings.json"


def codex_config_path(home: Path | None = None) -> Path:
    return _home(home) / ".codex" / "config.toml"


def antigravity_hooks_path(home: Path | None = None) -> Path:
    return _home(home) / ".gemini" / "config" / "hooks.json"


def codex_sidecar_path(home: Path | None = None) -> Path:
    """Where the pre-wiring Codex notify is remembered (default ~/.petgen/...)."""
    return _home(home) / ".petgen" / SIDECAR_NAME


def _detect_antigravity(home: Path) -> bool:
    for raw in ANTIGRAVITY_DETECT_PATHS:
        path = Path(raw)
        if raw.startswith("~"):
            path = home / raw[2:].lstrip("/")
        if path.exists():
            return True
    return False


# --- TOML helpers (config.toml is edited at line level; no writer dependency) --


def _toml_quote(value: str) -> str:
    out = ['"']
    for ch in value:
        if ch == "\\":
            out.append("\\\\")
        elif ch == '"':
            out.append('\\"')
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\t":
            out.append("\\t")
        elif ch == "\r":
            out.append("\\r")
        elif ch == "\b":
            out.append("\\b")
        elif ch == "\f":
            out.append("\\f")
        elif ord(ch) < 0x20:
            out.append("\\u%04X" % ord(ch))
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


def _parse_toml_string_array(line: str) -> list[str] | None:
    """Parse ``notify = ["a", "b"]`` into ["a", "b"]; None when not a string array."""
    stripped = line.strip()
    try:  # 3.11+ has tomllib; a single `key = [...]` line is a valid TOML document
        import tomllib

        value = tomllib.loads(stripped).get("notify")
    except ImportError:
        return _parse_toml_array_fallback(stripped)
    except Exception:
        return None
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return list(value)
    return None


def _parse_toml_array_fallback(line: str) -> list[str] | None:
    """3.10-compatible mini parser for `notify = ["...", "..."]` (string items only)."""
    match = re.match(r'\s*notify\s*=\s*\[(.*)\]\s*(?:#.*)?$', line)
    if not match:
        return None
    body = match.group(1)
    escapes = {'"': '"', "\\": "\\", "n": "\n", "t": "\t", "r": "\r", "b": "\b", "f": "\f"}
    items: list[str] = []
    i, n = 0, len(body)
    while i < n:
        while i < n and body[i] in " \t\r\n,":
            i += 1
        if i >= n:
            break
        if body[i] != '"':
            return None
        i += 1
        buf: list[str] = []
        closed = False
        while i < n:
            ch = body[i]
            if ch == "\\" and i + 1 < n:
                nxt = body[i + 1]
                if nxt == "u" and i + 6 <= n:
                    try:
                        buf.append(chr(int(body[i + 2 : i + 6], 16)))
                    except ValueError:
                        return None
                    i += 6
                    continue
                if nxt not in escapes:
                    return None
                buf.append(escapes[nxt])
                i += 2
                continue
            if ch == '"':
                closed = True
                break
            buf.append(ch)
            i += 1
        if not closed:
            return None
        items.append("".join(buf))
        i += 1
    return items


def _find_top_level_notify(lines: list[str]) -> int | None:
    """Index of a top-level `notify = [...]` line; table sections are skipped."""
    section: str | None = None
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("["):
            section = stripped
            continue
        if section is None and re.match(r"\s*notify\s*=\s*\[", line):
            return index
    return None


def _first_section_index(lines: list[str]) -> int | None:
    """Index of the first `[table]` header; a new top-level key must go before it."""
    for index, line in enumerate(lines):
        if line.strip().startswith("["):
            return index
    return None


# --- Codex sidecar (remember the pre-wiring notify for chaining & restore) ----


def read_codex_sidecar(home: Path | None = None) -> tuple[list[str] | None, str | None]:
    """Return (argv, original_line); legacy bash-era single-line files still work."""
    path = codex_sidecar_path(home)
    if not path.exists():
        return None, None
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return None, None
    try:
        data = json.loads(text)
    except ValueError:
        first = text.splitlines()[0].strip()
        return ([first] if first else None), None
    if isinstance(data, dict) and data.get("format") == 1:
        argv = data.get("argv")
        original = data.get("original_line")
        return (
            list(argv) if isinstance(argv, list) and argv else None,
            original if isinstance(original, str) else None,
        )
    return None, None


def _write_sidecar(home: Path, argv: list[str] | None, original_line: str | None) -> None:
    path = codex_sidecar_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"format": 1, "argv": argv, "original_line": original_line}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _reads_our_sidecar(path: Path) -> bool:
    """True when the candidate notify target reads our sidecar (would recurse)."""
    try:
        head = path.read_bytes()[:4096]
    except OSError:
        return False
    return b"codex-notify-original" in head


def _drop_sidecar(home: Path) -> None:
    path = codex_sidecar_path(home)
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def chain_original_notify(passthrough_args: list[str], *, home: Path | None = None) -> None:
    """Best-effort invoke the pre-wiring Codex notify; never raises."""
    argv, _ = read_codex_sidecar(home)
    if not argv:
        return
    head = Path(argv[0])
    if "petgen" in head.name or "codex-notify" in argv:
        return  # recursion guard: never chain back into ourselves
    if _reads_our_sidecar(head):
        return  # recursion guard: a script reading our sidecar would loop forever
    if not head.exists():
        return
    try:
        subprocess.run(
            [*argv, *passthrough_args],
            timeout=10,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.SubprocessError):
        pass


# --- Claude Code --------------------------------------------------------------


def _claude_petgen_groups(data: dict) -> list[str]:
    """Commands of our own hook groups currently present in settings.json."""
    found: list[str] = []
    hooks = data.get("hooks")
    if not isinstance(hooks, dict):
        return found
    for event in _CLAUDE_HOOK_EVENTS:
        groups = hooks.get(event)
        if not isinstance(groups, list):
            continue
        for group in groups:
            if not isinstance(group, dict):
                continue
            for hook in group.get("hooks") or []:
                command = hook.get("command") if isinstance(hook, dict) else None
                if isinstance(command, str) and _is_petgen_command(command, TOOL_SOURCES["claude"]):
                    found.append(command)
    return found


def _claude_status(home: Path) -> ToolState:
    if not (home / ".claude").is_dir():
        return ToolState("claude", ToolStatus.NOT_DETECTED, "未检测到 ~/.claude")
    settings = claude_settings_path(home)
    if not settings.exists():
        return ToolState("claude", ToolStatus.NOT_CONNECTED)
    try:
        data = _read_json_dict(settings)
    except IntegrationsError as exc:
        return ToolState("claude", ToolStatus.NOT_CONNECTED, str(exc))
    commands = _claude_petgen_groups(data)
    if not commands:
        return ToolState("claude", ToolStatus.NOT_CONNECTED)
    if all(_command_entry_exists(command) for command in commands):
        entry = shlex.split(commands[0])[0]
        return ToolState("claude", ToolStatus.CONNECTED, f"接通于 {entry}")
    return ToolState("claude", ToolStatus.STALE, "接线命令已失效（petgen 迁移过？），请重连")


def _claude_connect(home: Path) -> ToolState:
    if not (home / ".claude").is_dir():
        raise IntegrationsError("未检测到 Claude Code（~/.claude 不存在）")
    current = _claude_status(home)
    if current.status == ToolStatus.CONNECTED:
        return current
    settings = claude_settings_path(home)
    data = _read_json_dict(settings) if settings.exists() else {}
    _backup(settings)
    hooks = data.setdefault("hooks", {})
    titles = {"Stop": TOOL_TITLES["claude"], "SubagentStop": TOOL_TITLES["claude_subagent"]}
    for event in _CLAUDE_HOOK_EVENTS:
        groups = hooks.get(event)
        kept = [
            group
            for group in (groups if isinstance(groups, list) else [])
            if not (
                isinstance(group, dict)
                and any(
                    isinstance(hook, dict)
                    and _is_petgen_command(str(hook.get("command", "")), TOOL_SOURCES["claude"])
                    for hook in (group.get("hooks") or [])
                )
            )
        ]
        kept.append(
            {
                "hooks": [
                    {
                        "type": "command",
                        "command": _hook_command(TOOL_SOURCES["claude"], titles[event]),
                    }
                ]
            }
        )
        hooks[event] = kept
    _atomic_write(settings, json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    entry = petgen_argv()[0]
    return ToolState("claude", ToolStatus.CONNECTED, f"接通于 {entry}")


def _claude_disconnect(home: Path) -> ToolState:
    settings = claude_settings_path(home)
    if not settings.exists():
        return ToolState("claude", ToolStatus.NOT_CONNECTED)
    data = _read_json_dict(settings)
    if not _claude_petgen_groups(data):
        return ToolState("claude", ToolStatus.NOT_CONNECTED)
    _backup(settings)
    hooks = data.get("hooks", {})
    for event in _CLAUDE_HOOK_EVENTS:
        groups = hooks.get(event)
        if not isinstance(groups, list):
            continue
        kept = [
            group
            for group in groups
            if not (
                isinstance(group, dict)
                and any(
                    isinstance(hook, dict)
                    and _is_petgen_command(str(hook.get("command", "")), TOOL_SOURCES["claude"])
                    for hook in (group.get("hooks") or [])
                )
            )
        ]
        if kept:
            hooks[event] = kept
        else:
            hooks.pop(event, None)
    if not hooks:
        data.pop("hooks", None)
    _atomic_write(settings, json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    return ToolState("claude", ToolStatus.NOT_CONNECTED)


# --- Codex --------------------------------------------------------------------


def _codex_status(home: Path) -> ToolState:
    if not (home / ".codex").is_dir():
        return ToolState("codex", ToolStatus.NOT_DETECTED, "未检测到 ~/.codex")
    config = codex_config_path(home)
    if not config.exists():
        return ToolState("codex", ToolStatus.NOT_CONNECTED)
    lines = config.read_text(encoding="utf-8").splitlines(keepends=True)
    index = _find_top_level_notify(lines)
    if index is None:
        return ToolState("codex", ToolStatus.NOT_CONNECTED)
    line = lines[index]
    if not _is_petgen_command(line, TOOL_SOURCES["codex"]):
        return ToolState("codex", ToolStatus.NOT_CONNECTED, "notify 指向其他程序")
    parsed = _parse_toml_string_array(line)
    if parsed and Path(parsed[0]).exists():
        return ToolState("codex", ToolStatus.CONNECTED, f"接通于 {parsed[0]}")
    return ToolState("codex", ToolStatus.STALE, "接线命令已失效（petgen 迁移过？），请重连")


def _codex_connect(home: Path) -> ToolState:
    if not (home / ".codex").is_dir():
        raise IntegrationsError("未检测到 Codex（~/.codex 不存在）")
    current = _codex_status(home)
    if current.status == ToolStatus.CONNECTED:
        return current
    config = codex_config_path(home)
    text = config.read_text(encoding="utf-8") if config.exists() else ""
    lines = text.splitlines(keepends=True)
    new_line = "notify = [%s]\n" % ", ".join(
        _toml_quote(part) for part in [*petgen_argv(), "codex-notify"]
    )
    index = _find_top_level_notify(lines)
    _backup(config)
    if index is not None:
        existing = lines[index]
        if not _is_petgen_command(existing, TOOL_SOURCES["codex"]):
            # foreign notify: remember it verbatim for chaining + later restore
            _write_sidecar(home, _parse_toml_string_array(existing), existing.rstrip("\n"))
        # else: stale petgen line — sidecar already holds the true original
        lines[index] = new_line
    else:
        # No top-level notify yet. Insert before the first [table] header so the
        # key really stays top-level; append at the end when there are no tables.
        insert_at = _first_section_index(lines)
        if insert_at is None:
            if lines and not lines[-1].endswith("\n"):
                lines[-1] += "\n"
            lines.append(new_line)
        else:
            if insert_at > 0 and not lines[insert_at - 1].endswith("\n"):
                lines[insert_at - 1] += "\n"
            lines.insert(insert_at, new_line)
    _atomic_write(config, "".join(lines), mode=0o600)
    entry = petgen_argv()[0]
    return ToolState("codex", ToolStatus.CONNECTED, f"接通于 {entry}")


def _codex_disconnect(home: Path) -> ToolState:
    config = codex_config_path(home)
    if not config.exists():
        return ToolState("codex", ToolStatus.NOT_CONNECTED)
    lines = config.read_text(encoding="utf-8").splitlines(keepends=True)
    index = _find_top_level_notify(lines)
    if index is None or not _is_petgen_command(lines[index], TOOL_SOURCES["codex"]):
        return ToolState("codex", ToolStatus.NOT_CONNECTED)
    _backup(config)
    _, original_line = read_codex_sidecar(home)
    if original_line is not None:
        lines[index] = original_line + "\n"
    else:
        del lines[index]
    _atomic_write(config, "".join(lines), mode=0o600)
    _drop_sidecar(home)
    return ToolState("codex", ToolStatus.NOT_CONNECTED)


# --- Antigravity --------------------------------------------------------------


def _first_antigravity_command(entry: object) -> str | None:
    if not isinstance(entry, dict):
        return None
    stops = entry.get("Stop")
    if not isinstance(stops, list):
        return None
    for group in stops:
        if not isinstance(group, dict):
            continue
        for hook in group.get("hooks") or []:
            command = hook.get("command") if isinstance(hook, dict) else None
            if isinstance(command, str):
                return command
    return None


def _antigravity_status(home: Path) -> ToolState:
    if not _detect_antigravity(home):
        return ToolState("antigravity", ToolStatus.NOT_DETECTED, "未检测到 Antigravity")
    hooks_path = antigravity_hooks_path(home)
    if not hooks_path.exists():
        return ToolState("antigravity", ToolStatus.NOT_CONNECTED)
    try:
        data = _read_json_dict(hooks_path)
    except IntegrationsError as exc:
        return ToolState("antigravity", ToolStatus.NOT_CONNECTED, str(exc))
    entry = data.get("petgen-notify")
    if entry is None:
        return ToolState("antigravity", ToolStatus.NOT_CONNECTED)
    command = _first_antigravity_command(entry)
    # Ownership marker (same rule as Claude/Codex): the command must reference
    # petgen. Legacy bash-era entries under this key lack the marker, report
    # not_connected, and get upgraded in place by the next connect.
    if not command or not _is_petgen_command(command, TOOL_SOURCES["antigravity"]):
        return ToolState("antigravity", ToolStatus.NOT_CONNECTED, "petgen-notify 键由旧版配置占用，接通时自动升级")
    if _command_entry_exists(command):
        return ToolState("antigravity", ToolStatus.CONNECTED, "真机触发待验证")
    return ToolState("antigravity", ToolStatus.STALE, "接线命令已失效（petgen 迁移过？），请重连")


def _antigravity_connect(home: Path) -> ToolState:
    if not _detect_antigravity(home):
        raise IntegrationsError("未检测到 Antigravity（~/.gemini 等路径不存在）")
    current = _antigravity_status(home)
    if current.status == ToolStatus.CONNECTED:
        return current
    hooks_path = antigravity_hooks_path(home)
    data = _read_json_dict(hooks_path) if hooks_path.exists() else {}
    _backup(hooks_path)
    data["petgen-notify"] = {
        "Stop": [
            {
                "hooks": [
                    {
                        "type": "command",
                        "command": _hook_command(TOOL_SOURCES["antigravity"], TOOL_TITLES["antigravity"]),
                    }
                ]
            }
        ]
    }
    _atomic_write(hooks_path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    entry = petgen_argv()[0]
    return ToolState("antigravity", ToolStatus.CONNECTED, f"接通于 {entry}（真机触发待验证）")


def _antigravity_disconnect(home: Path) -> ToolState:
    hooks_path = antigravity_hooks_path(home)
    if not hooks_path.exists():
        return ToolState("antigravity", ToolStatus.NOT_CONNECTED)
    data = _read_json_dict(hooks_path)
    if "petgen-notify" not in data:
        return ToolState("antigravity", ToolStatus.NOT_CONNECTED)
    _backup(hooks_path)
    del data["petgen-notify"]
    _atomic_write(hooks_path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    return ToolState("antigravity", ToolStatus.NOT_CONNECTED)


# --- public facade -------------------------------------------------------------

_STATUS_FN = {"claude": _claude_status, "codex": _codex_status, "antigravity": _antigravity_status}
_CONNECT_FN = {"claude": _claude_connect, "codex": _codex_connect, "antigravity": _antigravity_connect}
_DISCONNECT_FN = {"claude": _claude_disconnect, "codex": _codex_disconnect, "antigravity": _antigravity_disconnect}


def status(tool: str, home: Path | None = None) -> ToolState:
    if tool not in TOOLS:
        raise ValueError(f"unknown tool: {tool!r} (expected one of {TOOLS})")
    return _STATUS_FN[tool](_home(home))


def connect(tool: str, home: Path | None = None) -> ToolState:
    if tool not in TOOLS:
        raise ValueError(f"unknown tool: {tool!r} (expected one of {TOOLS})")
    _require_posix()
    return _CONNECT_FN[tool](_home(home))


def disconnect(tool: str, home: Path | None = None) -> ToolState:
    if tool not in TOOLS:
        raise ValueError(f"unknown tool: {tool!r} (expected one of {TOOLS})")
    _require_posix()
    return _DISCONNECT_FN[tool](_home(home))
