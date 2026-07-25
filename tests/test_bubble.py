from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from petgen.bubble import BubbleWindow  # noqa: E402


def _click_action_button(bubble: BubbleWindow, label: str) -> None:
    """Find and click the action button the bubble built for ``label``."""
    from PySide6.QtWidgets import QPushButton

    matches = [b for b in bubble.findChildren(QPushButton) if b.text() == label]
    assert matches, f"no action button labelled {label!r} rendered"
    matches[0].click()


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication(["test-bubble"])


def test_bubble_label_is_plain_text(qapp) -> None:
    """Bubble text is forced to PlainText so external titles cannot inject HTML."""
    bubble = BubbleWindow()
    assert bubble._label.textFormat() == Qt.PlainText  # noqa: SLF001


def test_bubble_renders_html_markup_literally(qapp) -> None:
    bubble = BubbleWindow()
    markup = '<b>bold</b> <a href="x">link</a>'
    bubble.show_message(markup)
    # With PlainText the raw markup is shown verbatim, not parsed into rich text.
    assert bubble._label.text() == markup  # noqa: SLF001


def test_bubble_strips_outer_blank_lines(qapp) -> None:
    bubble = BubbleWindow()
    bubble.show_message("\n[Codex] 完成\n\n")
    assert bubble._label.text() == "[Codex] 完成"  # noqa: SLF001
    assert not bubble._button_bar.isVisible()  # noqa: SLF001


def test_bubble_action_failure_is_logged_not_swallowed(qapp, capsys) -> None:
    """A raising action callback must surface on stderr (was silently swallowed).

    The bubble still dismisses (best-effort UI), but the failure is observable
    so reminder complete/snooze bugs do not disappear silently.
    """
    bubble = BubbleWindow()
    dismissed: list[bool] = []
    bubble.dismissed.connect(lambda: dismissed.append(True))

    def boom() -> None:
        raise RuntimeError("kaboom")

    bubble.show_message("提醒", actions=[("完成", boom)])
    _click_action_button(bubble, "完成")
    QApplication.processEvents()

    err = capsys.readouterr().err
    assert "bubble action failed" in err
    assert "kaboom" in err
    assert dismissed == [True]  # bubble still hid as expected
