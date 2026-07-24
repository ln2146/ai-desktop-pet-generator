from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QTabWidget  # noqa: E402

from petgen import integrations  # noqa: E402
from petgen.settings_dialog import SettingsDialog  # noqa: E402
from petgen.store import SettingsStore  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication(["test-settings-tools-tab"])


class _FakeWiring:
    """In-memory stand-in for the integrations module functions."""

    def __init__(self, initial: dict[str, integrations.ToolState]) -> None:
        self.states = dict(initial)
        self.connect_calls: list[str] = []
        self.disconnect_calls: list[str] = []

    def status(self, tool: str, home=None) -> integrations.ToolState:
        return self.states[tool]

    def connect(self, tool: str, home=None) -> integrations.ToolState:
        self.connect_calls.append(tool)
        self.states[tool] = integrations.ToolState(tool, integrations.ToolStatus.CONNECTED, "ok")
        return self.states[tool]

    def disconnect(self, tool: str, home=None) -> integrations.ToolState:
        self.disconnect_calls.append(tool)
        self.states[tool] = integrations.ToolState(tool, integrations.ToolStatus.NOT_CONNECTED)
        return self.states[tool]


def _install(monkeypatch: pytest.MonkeyPatch, fake: _FakeWiring) -> None:
    monkeypatch.setattr(integrations, "status", fake.status)
    monkeypatch.setattr(integrations, "connect", fake.connect)
    monkeypatch.setattr(integrations, "disconnect", fake.disconnect)


def _all(status: integrations.ToolStatus) -> dict[str, integrations.ToolState]:
    return {tool: integrations.ToolState(tool, status) for tool in integrations.TOOLS}


def _make_dialog(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SettingsDialog:
    monkeypatch.setenv("PETGEN_DATA_DIR", str(tmp_path / "data"))
    return SettingsDialog(SettingsStore(tmp_path / "db.sqlite"))


def test_tools_tab_exists_with_four_tabs(qapp, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _install(monkeypatch, _FakeWiring(_all(integrations.ToolStatus.NOT_CONNECTED)))
    dlg = _make_dialog(tmp_path, monkeypatch)
    tabs = dlg.findChild(QTabWidget)
    assert tabs is not None
    assert tabs.count() == 4
    assert any("工具接入" in tabs.tabText(i) for i in range(tabs.count()))


def test_rows_reflect_all_four_states(qapp, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeWiring(
        {
            "claude": integrations.ToolState("claude", integrations.ToolStatus.CONNECTED, "接通于 /x"),
            "codex": integrations.ToolState("codex", integrations.ToolStatus.NOT_CONNECTED),
            "antigravity": integrations.ToolState("antigravity", integrations.ToolStatus.NOT_DETECTED, "未检测到"),
        }
    )
    fake.states["claude"] = integrations.ToolState("claude", integrations.ToolStatus.CONNECTED)
    _install(monkeypatch, fake)
    # fourth state via stale on a fresh fake row: emulate by patching one tool
    fake.states["codex"] = integrations.ToolState("codex", integrations.ToolStatus.STALE, "需重连")
    dlg = _make_dialog(tmp_path, monkeypatch)

    claude_chip, claude_toggle = dlg._tool_rows["claude"]  # noqa: SLF001
    codex_chip, codex_toggle = dlg._tool_rows["codex"]  # noqa: SLF001
    ag_chip, ag_toggle = dlg._tool_rows["antigravity"]  # noqa: SLF001

    # connected -> checked + enabled
    assert claude_chip.text() == "✅ 已接通"
    assert claude_toggle.isChecked() and claude_toggle.isEnabled()

    # stale -> unchecked but enabled; the chip text carries the 4th-state detail
    assert codex_chip.text() == "⚠️ 需重连"
    assert not codex_toggle.isChecked() and codex_toggle.isEnabled()

    # not detected -> unchecked + disabled
    assert ag_chip.text() == "未检测到"
    assert not ag_toggle.isChecked() and not ag_toggle.isEnabled()


def test_toggle_connects_then_disconnects(qapp, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeWiring(_all(integrations.ToolStatus.NOT_CONNECTED))
    _install(monkeypatch, fake)
    dlg = _make_dialog(tmp_path, monkeypatch)
    chip, toggle = dlg._tool_rows["codex"]  # noqa: SLF001

    toggle.click()
    assert fake.connect_calls == ["codex"]
    assert chip.text() == "✅ 已接通"
    assert toggle.isChecked()

    toggle.click()
    assert fake.disconnect_calls == ["codex"]
    assert chip.text() == "○ 未接通"
    assert not toggle.isChecked()


def test_connect_all_connects_each_tool(qapp, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeWiring(_all(integrations.ToolStatus.NOT_CONNECTED))
    _install(monkeypatch, fake)
    dlg = _make_dialog(tmp_path, monkeypatch)

    dlg._connect_all_tools()  # noqa: SLF001
    assert sorted(fake.connect_calls) == ["antigravity", "claude", "codex"]

    fake.connect_calls.clear()
    dlg._connect_all_tools()  # noqa: SLF001 - all connected now → no new calls
    assert fake.connect_calls == []


def test_connect_error_shows_warning(qapp, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeWiring(_all(integrations.ToolStatus.NOT_CONNECTED))
    _install(monkeypatch, fake)

    def bad_connect(tool, home=None):
        raise integrations.IntegrationsError("boom")

    monkeypatch.setattr(integrations, "connect", bad_connect)
    warnings: list[tuple[str, str]] = []
    import petgen.settings_dialog as sd

    monkeypatch.setattr(
        sd.QMessageBox, "warning", lambda parent, title, text: warnings.append((title, text))
    )
    dlg = _make_dialog(tmp_path, monkeypatch)
    _chip, btn = dlg._tool_rows["claude"]  # noqa: SLF001
    btn.click()
    assert warnings and "boom" in warnings[0][1]


def test_status_failure_does_not_break_dialog(qapp, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(tool, home=None):
        raise RuntimeError("probe failed")

    monkeypatch.setattr(integrations, "status", broken)
    dlg = _make_dialog(tmp_path, monkeypatch)  # must construct fine
    dlg.load_values()  # must not raise either
    chip, btn = dlg._tool_rows["claude"]  # noqa: SLF001
    assert chip.text() == "状态未知"
    assert not btn.isEnabled()
