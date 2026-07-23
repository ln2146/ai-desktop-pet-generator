from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from petgen.bubble import BubbleWindow  # noqa: E402


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
