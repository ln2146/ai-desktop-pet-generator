from __future__ import annotations

import json
import shlex
import stat
import sys
from pathlib import Path

import pytest

from petgen import integrations
from petgen.integrations import (
    IntegrationsError,
    ToolStatus,
    _find_top_level_notify,
    _parse_toml_array_fallback,
    _parse_toml_string_array,
    _toml_quote,
)


@pytest.fixture(autouse=True)
def _deterministic_antigravity_detection(monkeypatch: pytest.MonkeyPatch):
    # Default detection paths include absolute macOS locations that may really
    # exist on the test machine (e.g. /Applications/Antigravity.app).
    monkeypatch.setattr(integrations, "ANTIGRAVITY_DETECT_PATHS", ("~/.gemini",))


@pytest.fixture()
def fake_petgen_exe(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """A fake but existing petgen executable that petgen_argv() resolves to."""
    exe = tmp_path / "bin" / "petgen"
    exe.parent.mkdir(parents=True)
    exe.write_text("#!/bin/sh\n", encoding="utf-8")
    exe.chmod(0o755)
    monkeypatch.setattr(
        integrations.shutil, "which", lambda name: str(exe) if name == "petgen" else None
    )
    return exe


def _make_home(tmp_path: Path, *, claude: bool = True, codex: bool = True, gemini: bool = True) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    if claude:
        (home / ".claude").mkdir()
    if codex:
        (home / ".codex").mkdir()
    if gemini:
        (home / ".gemini").mkdir()
    return home


# --- petgen_argv ---------------------------------------------------------------


def test_petgen_argv_prefers_which(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    exe = tmp_path / "petgen"
    exe.write_text("x", encoding="utf-8")
    monkeypatch.setattr(integrations.shutil, "which", lambda name: str(exe))
    assert integrations.petgen_argv() == [str(exe)]


def test_petgen_argv_falls_back_to_module(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(integrations.shutil, "which", lambda name: None)
    assert integrations.petgen_argv() == [sys.executable, "-m", "petgen"]


# --- Claude Code ----------------------------------------------------------------


def test_claude_connect_creates_hooks_and_backs_up(
    fake_petgen_exe: Path, tmp_path: Path
) -> None:
    home = _make_home(tmp_path)
    settings = home / ".claude" / "settings.json"
    settings.write_text(json.dumps({"theme": "dark"}), encoding="utf-8")

    state = integrations.connect("claude", home=home)
    assert state.status == ToolStatus.CONNECTED

    data = json.loads(settings.read_text(encoding="utf-8"))
    assert data["theme"] == "dark"  # pre-existing content preserved
    titles = {"Stop": "Claude 任务完成", "SubagentStop": "Claude 子任务完成"}
    for event, title in titles.items():
        groups = data["hooks"][event]
        assert len(groups) == 1
        parts = shlex.split(groups[0]["hooks"][0]["command"])
        assert parts[0] == str(fake_petgen_exe)
        assert parts[1:4] == ["event", "task_completed", title]
        assert parts[4] == "" and parts[5] == "claude_code"
    assert list(settings.parent.glob("settings.json.bak.*"))


def test_claude_connect_idempotent(fake_petgen_exe: Path, tmp_path: Path) -> None:
    home = _make_home(tmp_path)
    settings = home / ".claude" / "settings.json"
    integrations.connect("claude", home=home)
    backups_after_first = list(settings.parent.glob("settings.json.bak.*"))
    integrations.connect("claude", home=home)

    data = json.loads(settings.read_text(encoding="utf-8"))
    assert len(data["hooks"]["Stop"]) == 1
    assert len(data["hooks"]["SubagentStop"]) == 1
    assert list(settings.parent.glob("settings.json.bak.*")) == backups_after_first  # no extra backup


def test_claude_coexists_with_other_pets(fake_petgen_exe: Path, tmp_path: Path) -> None:
    home = _make_home(tmp_path)
    settings = home / ".claude" / "settings.json"
    other_group = {
        "hooks": [
            {
                "type": "command",
                "command": '/x/ai-pet-reminder/scripts/hooks/claude-code-hook.sh completed "Claude 任务完成"',
            }
        ]
    }
    legacy_group = {
        "hooks": [
            {
                "type": "command",
                "command": '/x/ai-desktop-pet-generator/scripts/hooks/claude-code-hook.sh completed "Claude 任务完成"',
            }
        ]
    }
    settings.write_text(
        json.dumps({"hooks": {"Stop": [other_group, legacy_group]}}, ensure_ascii=False),
        encoding="utf-8",
    )

    integrations.connect("claude", home=home)
    data = json.loads(settings.read_text(encoding="utf-8"))
    assert len(data["hooks"]["Stop"]) == 3  # both foreign groups kept + ours appended

    integrations.disconnect("claude", home=home)
    data = json.loads(settings.read_text(encoding="utf-8"))
    assert data["hooks"]["Stop"] == [other_group, legacy_group]  # only ours removed


def test_claude_disconnect_removes_empty_keys(fake_petgen_exe: Path, tmp_path: Path) -> None:
    home = _make_home(tmp_path)
    settings = home / ".claude" / "settings.json"
    integrations.connect("claude", home=home)
    integrations.disconnect("claude", home=home)
    data = json.loads(settings.read_text(encoding="utf-8"))
    assert data == {}


def test_claude_corrupted_settings_refused(fake_petgen_exe: Path, tmp_path: Path) -> None:
    home = _make_home(tmp_path)
    settings = home / ".claude" / "settings.json"
    settings.write_text("{not json", encoding="utf-8")
    with pytest.raises(IntegrationsError):
        integrations.connect("claude", home=home)
    assert settings.read_text(encoding="utf-8") == "{not json"  # untouched


def test_claude_status_corrupted_reports_not_connected(tmp_path: Path) -> None:
    home = _make_home(tmp_path)
    (home / ".claude" / "settings.json").write_text("{not json", encoding="utf-8")
    state = integrations.status("claude", home=home)
    assert state.status == ToolStatus.NOT_CONNECTED
    assert "损坏" in state.detail


def test_claude_stale_then_reconnect(fake_petgen_exe: Path, tmp_path: Path) -> None:
    home = _make_home(tmp_path)
    settings = home / ".claude" / "settings.json"
    stale = '/nonexistent/petgen event task_completed "Claude 任务完成" "" claude_code'
    settings.write_text(
        json.dumps(
            {
                "hooks": {
                    "Stop": [{"hooks": [{"type": "command", "command": stale}]}],
                    "SubagentStop": [{"hooks": [{"type": "command", "command": stale}]}],
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    assert integrations.status("claude", home=home).status == ToolStatus.STALE

    state = integrations.connect("claude", home=home)
    assert state.status == ToolStatus.CONNECTED
    data = json.loads(settings.read_text(encoding="utf-8"))
    assert len(data["hooks"]["Stop"]) == 1  # stale group replaced, not duplicated
    command = data["hooks"]["Stop"][0]["hooks"][0]["command"]
    assert shlex.split(command)[0] == str(fake_petgen_exe)


def test_claude_not_detected(tmp_path: Path) -> None:
    home = _make_home(tmp_path, claude=False)
    assert integrations.status("claude", home=home).status == ToolStatus.NOT_DETECTED
    with pytest.raises(IntegrationsError):
        integrations.connect("claude", home=home)


# --- Codex -----------------------------------------------------------------------


def test_codex_connect_replaces_notify_and_writes_sidecar(
    fake_petgen_exe: Path, tmp_path: Path
) -> None:
    home = _make_home(tmp_path)
    config = home / ".codex" / "config.toml"
    original = 'model = "o4-mini"\nnotify = ["/usr/local/bin/other-notify", "turn-ended"]\n'
    config.write_text(original, encoding="utf-8")

    state = integrations.connect("codex", home=home)
    assert state.status == ToolStatus.CONNECTED

    lines = config.read_text(encoding="utf-8").splitlines()
    assert lines[0] == 'model = "o4-mini"'
    assert _parse_toml_string_array(lines[1]) == [str(fake_petgen_exe), "codex-notify"]
    assert stat.S_IMODE(config.stat().st_mode) == 0o600
    assert list(config.parent.glob("config.toml.bak.*"))

    sidecar = json.loads((home / ".petgen" / "codex-notify-original").read_text(encoding="utf-8"))
    assert sidecar["format"] == 1
    assert sidecar["argv"] == ["/usr/local/bin/other-notify", "turn-ended"]
    assert sidecar["original_line"] == 'notify = ["/usr/local/bin/other-notify", "turn-ended"]'


def test_codex_connect_appends_when_no_notify(fake_petgen_exe: Path, tmp_path: Path) -> None:
    home = _make_home(tmp_path)
    config = home / ".codex" / "config.toml"
    config.write_text('model = "x"', encoding="utf-8")  # no trailing newline

    integrations.connect("codex", home=home)
    lines = config.read_text(encoding="utf-8").splitlines()
    assert lines[0] == 'model = "x"'
    assert lines[-1].startswith("notify = [")

    # fresh append had no prior notify, so no sidecar is written
    assert not (home / ".petgen" / "codex-notify-original").exists()


def test_codex_connect_idempotent(fake_petgen_exe: Path, tmp_path: Path) -> None:
    home = _make_home(tmp_path)
    config = home / ".codex" / "config.toml"
    config.write_text('notify = ["/x/other"]\n', encoding="utf-8")
    integrations.connect("codex", home=home)
    after_first = config.read_text(encoding="utf-8")
    integrations.connect("codex", home=home)
    assert config.read_text(encoding="utf-8") == after_first
    assert after_first.count("notify =") == 1


def test_codex_notify_inside_table_untouched(fake_petgen_exe: Path, tmp_path: Path) -> None:
    home = _make_home(tmp_path)
    config = home / ".codex" / "config.toml"
    config.write_text('[history]\nnotify = ["/x/inner"]\n', encoding="utf-8")

    integrations.connect("codex", home=home)
    lines = config.read_text(encoding="utf-8").splitlines()
    # ours is inserted before the first [table] header so it stays top-level
    assert lines[0].startswith("notify = [") and "codex-notify" in lines[0]
    assert lines[1] == "[history]"
    assert lines[2] == 'notify = ["/x/inner"]'  # table member untouched

    integrations.disconnect("codex", home=home)
    assert config.read_text(encoding="utf-8") == '[history]\nnotify = ["/x/inner"]\n'


def test_codex_disconnect_restores_original_line(fake_petgen_exe: Path, tmp_path: Path) -> None:
    home = _make_home(tmp_path)
    config = home / ".codex" / "config.toml"
    original = 'notify = ["/usr/local/bin/other-notify", "turn-ended"]\n'
    config.write_text(original, encoding="utf-8")

    integrations.connect("codex", home=home)
    state = integrations.disconnect("codex", home=home)
    assert state.status == ToolStatus.NOT_CONNECTED
    assert config.read_text(encoding="utf-8") == original
    assert not (home / ".petgen" / "codex-notify-original").exists()


def test_codex_disconnect_without_sidecar_deletes_line(
    fake_petgen_exe: Path, tmp_path: Path
) -> None:
    home = _make_home(tmp_path)
    config = home / ".codex" / "config.toml"
    config.write_text('model = "x"\n', encoding="utf-8")
    integrations.connect("codex", home=home)  # fresh append → no sidecar exists

    integrations.disconnect("codex", home=home)
    assert config.read_text(encoding="utf-8") == 'model = "x"\n'


def test_codex_disconnect_foreign_notify_untouched(fake_petgen_exe: Path, tmp_path: Path) -> None:
    home = _make_home(tmp_path)
    config = home / ".codex" / "config.toml"
    config.write_text('notify = ["/usr/local/bin/other"]\n', encoding="utf-8")
    state = integrations.disconnect("codex", home=home)
    assert state.status == ToolStatus.NOT_CONNECTED
    assert config.read_text(encoding="utf-8") == 'notify = ["/usr/local/bin/other"]\n'


def test_codex_stale_status_when_entry_gone(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = _make_home(tmp_path)
    config = home / ".codex" / "config.toml"
    config.write_text('notify = ["/nonexistent/petgen", "codex-notify"]\n', encoding="utf-8")
    assert integrations.status("codex", home=home).status == ToolStatus.STALE


def test_codex_not_detected(tmp_path: Path) -> None:
    home = _make_home(tmp_path, codex=False)
    assert integrations.status("codex", home=home).status == ToolStatus.NOT_DETECTED
    with pytest.raises(IntegrationsError):
        integrations.connect("codex", home=home)


def test_codex_sidecar_legacy_single_line(tmp_path: Path) -> None:
    home = _make_home(tmp_path)
    (home / ".petgen").mkdir()
    (home / ".petgen" / "codex-notify-original").write_text("/usr/local/bin/old-wrapper\n", encoding="utf-8")
    argv, original_line = integrations.read_codex_sidecar(home=home)
    assert argv == ["/usr/local/bin/old-wrapper"]
    assert original_line is None


def test_chain_calls_original_with_passthrough(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = _make_home(tmp_path)
    (home / ".petgen").mkdir()
    prog = tmp_path / "orig-notify"
    prog.write_text("#!/bin/sh\n", encoding="utf-8")
    prog.chmod(0o755)
    (home / ".petgen" / "codex-notify-original").write_text(
        json.dumps({"format": 1, "argv": [str(prog)], "original_line": None}),
        encoding="utf-8",
    )
    recorded: list[list[str]] = []
    monkeypatch.setattr(integrations.subprocess, "run", lambda argv, **kwargs: recorded.append(list(argv)))
    integrations.chain_original_notify(['{"type": "agent-turn-complete"}'], home=home)
    assert recorded == [[str(prog), '{"type": "agent-turn-complete"}']]


def test_chain_skips_self_reference(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = _make_home(tmp_path)
    (home / ".petgen").mkdir()
    exe = tmp_path / "petgen"
    exe.write_text("#!/bin/sh\n", encoding="utf-8")
    exe.chmod(0o755)
    (home / ".petgen" / "codex-notify-original").write_text(
        json.dumps({"format": 1, "argv": [str(exe), "codex-notify"], "original_line": None}),
        encoding="utf-8",
    )
    called: list[object] = []
    monkeypatch.setattr(integrations.subprocess, "run", lambda *args, **kwargs: called.append(args))
    integrations.chain_original_notify(["turn-ended"], home=home)
    assert called == []


def test_chain_skips_bash_wrapper_reading_sidecar(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # The legacy bash wrapper reads our sidecar file — chaining it would loop
    # forever, so any target whose body references the sidecar is skipped.
    home = _make_home(tmp_path)
    (home / ".petgen").mkdir()
    wrapper = tmp_path / "codex-notify-wrapper.sh"
    wrapper.write_text(
        '#!/bin/sh\nORIG_FILE="${PETGEN_DATA_DIR:-$HOME/.petgen}/codex-notify-original"\n',
        encoding="utf-8",
    )
    wrapper.chmod(0o755)
    (home / ".petgen" / "codex-notify-original").write_text(
        json.dumps({"format": 1, "argv": [str(wrapper), "turn-ended"], "original_line": None}),
        encoding="utf-8",
    )
    called: list[object] = []
    monkeypatch.setattr(integrations.subprocess, "run", lambda *args, **kwargs: called.append(args))
    integrations.chain_original_notify([], home=home)
    assert called == []


def test_chain_allows_foreign_wrapper_with_similar_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Another pet's wrapper may also be named codex-notify-wrapper.sh; as long
    # as it does not read our sidecar it is a legitimate chain target.
    home = _make_home(tmp_path)
    (home / ".petgen").mkdir()
    wrapper = tmp_path / "codex-notify-wrapper.sh"
    wrapper.write_text("#!/bin/sh\n/usr/bin/some-original-notify \"$@\"\n", encoding="utf-8")
    wrapper.chmod(0o755)
    (home / ".petgen" / "codex-notify-original").write_text(
        json.dumps({"format": 1, "argv": [str(wrapper), "turn-ended"], "original_line": None}),
        encoding="utf-8",
    )
    called: list[list[str]] = []
    monkeypatch.setattr(integrations.subprocess, "run", lambda argv, **kwargs: called.append(list(argv)))
    integrations.chain_original_notify([], home=home)
    assert called == [[str(wrapper), "turn-ended"]]


# --- Antigravity -------------------------------------------------------------------


def test_antigravity_connect_preserves_other_keys(fake_petgen_exe: Path, tmp_path: Path) -> None:
    home = _make_home(tmp_path)
    hooks = home / ".gemini" / "config" / "hooks.json"
    hooks.parent.mkdir(parents=True)
    hooks.write_text(json.dumps({"ai-pet-notify": {"Stop": []}}), encoding="utf-8")

    state = integrations.connect("antigravity", home=home)
    assert state.status == ToolStatus.CONNECTED
    data = json.loads(hooks.read_text(encoding="utf-8"))
    assert data["ai-pet-notify"] == {"Stop": []}
    parts = shlex.split(data["petgen-notify"]["Stop"][0]["hooks"][0]["command"])
    assert parts[1:3] == ["event", "task_completed"]
    assert parts[-1] == "antigravity"

    # idempotent
    integrations.connect("antigravity", home=home)
    data = json.loads(hooks.read_text(encoding="utf-8"))
    assert len(data["petgen-notify"]["Stop"]) == 1


def test_antigravity_disconnect_only_own_key(fake_petgen_exe: Path, tmp_path: Path) -> None:
    home = _make_home(tmp_path)
    hooks = home / ".gemini" / "config" / "hooks.json"
    hooks.parent.mkdir(parents=True)
    hooks.write_text(json.dumps({"ai-pet-notify": {"Stop": []}}), encoding="utf-8")
    integrations.connect("antigravity", home=home)

    integrations.disconnect("antigravity", home=home)
    data = json.loads(hooks.read_text(encoding="utf-8"))
    assert data == {"ai-pet-notify": {"Stop": []}}


def test_antigravity_fresh_connect_creates_file(fake_petgen_exe: Path, tmp_path: Path) -> None:
    home = _make_home(tmp_path)  # .gemini exists, config/ does not
    state = integrations.connect("antigravity", home=home)
    assert state.status == ToolStatus.CONNECTED
    assert (home / ".gemini" / "config" / "hooks.json").exists()


def test_antigravity_disconnect_missing_file_noop(tmp_path: Path) -> None:
    home = _make_home(tmp_path)
    state = integrations.disconnect("antigravity", home=home)
    assert state.status == ToolStatus.NOT_CONNECTED


def test_antigravity_corrupted_refused(fake_petgen_exe: Path, tmp_path: Path) -> None:
    home = _make_home(tmp_path)
    hooks = home / ".gemini" / "config" / "hooks.json"
    hooks.parent.mkdir(parents=True)
    hooks.write_text("[1,2", encoding="utf-8")
    with pytest.raises(IntegrationsError):
        integrations.connect("antigravity", home=home)
    assert hooks.read_text(encoding="utf-8") == "[1,2"


def test_antigravity_not_detected(fake_petgen_exe: Path, tmp_path: Path) -> None:
    home = _make_home(tmp_path, gemini=False)
    assert integrations.status("antigravity", home=home).status == ToolStatus.NOT_DETECTED
    with pytest.raises(IntegrationsError):
        integrations.connect("antigravity", home=home)


def test_antigravity_legacy_entry_upgraded_by_connect(
    fake_petgen_exe: Path, tmp_path: Path
) -> None:
    # bash-era wiring occupies our petgen-notify key with a non-petgen command:
    # status must not call it connected, and connect must upgrade it in place.
    home = _make_home(tmp_path)
    hooks = home / ".gemini" / "config" / "hooks.json"
    hooks.parent.mkdir(parents=True)
    legacy_script = tmp_path / "antigravity-hook.sh"
    legacy_script.write_text("#!/bin/sh\n", encoding="utf-8")
    legacy_script.chmod(0o755)
    hooks.write_text(
        json.dumps(
            {
                "petgen-notify": {
                    "Stop": [
                        {
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": f"{legacy_script} completed 'Antigravity 任务完成'",
                                }
                            ]
                        }
                    ]
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    assert integrations.status("antigravity", home=home).status == ToolStatus.NOT_CONNECTED

    state = integrations.connect("antigravity", home=home)
    assert state.status == ToolStatus.CONNECTED
    data = json.loads(hooks.read_text(encoding="utf-8"))
    parts = shlex.split(data["petgen-notify"]["Stop"][0]["hooks"][0]["command"])
    assert parts[0] == str(fake_petgen_exe) and parts[-1] == "antigravity"


# --- TOML helpers -------------------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    [
        "/usr/local/bin/petgen",
        "/path with space/petgen",
        'quote"and\\slash',
        "中文路径",
        "tab\there\nnewline",
    ],
)
def test_toml_quote_roundtrip(value: str) -> None:
    line = f"notify = [{_toml_quote(value)}, \"codex-notify\"]"
    assert _parse_toml_string_array(line) == [value, "codex-notify"]
    assert _parse_toml_array_fallback(line) == [value, "codex-notify"]


def test_toml_fallback_escapes_and_rejects() -> None:
    assert _parse_toml_array_fallback(r'notify = ["quo\"te", "back\\slash", "uni中"]') == [
        'quo"te',
        "back\\slash",
        "uni中",
    ]
    assert _parse_toml_array_fallback("notify = 1") is None
    assert _parse_toml_array_fallback("notify = [1, 2]") is None  # non-string items
    assert _parse_toml_array_fallback(r'notify = ["中"]') == ["中"]  # \uXXXX escape


def test_find_top_level_notify_tracks_sections() -> None:
    # keys after a [table] header belong to that table until the next header
    assert _find_top_level_notify(['notify = ["top"]\n', "[a]\n", 'notify = ["inner"]\n']) == 0
    assert _find_top_level_notify(["[a]\n", 'notify = ["inner"]\n', "\n"]) is None
    assert _find_top_level_notify(["# comment\n", 'notify = ["top"]\n']) == 1


# --- facade --------------------------------------------------------------------------


def test_facade_unknown_tool(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        integrations.status("gemini", home=tmp_path)
    with pytest.raises(ValueError):
        integrations.connect("gemini", home=tmp_path)


def test_connect_refuses_windows(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    home = _make_home(tmp_path)
    monkeypatch.setattr(integrations.sys, "platform", "win32")
    with pytest.raises(IntegrationsError):
        integrations.connect("claude", home=home)
    with pytest.raises(IntegrationsError):
        integrations.disconnect("claude", home=home)
