"""Shared pytest fixtures.

i18n note: the app's source language is Chinese, and ``tr()`` returns the source
text verbatim when no translator is loaded. Several existing tests assert on
specific Chinese UI strings (tray menu labels, dialog titles, bubble text). The
translator is installed on the (session-scoped) QApplication by AppCoordinator,
which resolves the OS locale at runtime — on a non-Chinese CI/OS locale that
swaps the UI to English and breaks those assertions.

This autouse fixture forces the source language (zh) before every GUI test so
those assertions are deterministic regardless of the host locale. It is a
no-op when PySide6 is not installed (pure-logic tests import-skip Qt).
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _force_source_language(monkeypatch):
    """Force the source language (Chinese) for every test.

    Two things must hold for tests that assert on Chinese UI strings:
    1. resolve_language() must return zh_CN regardless of the host locale (CI may
       run on en-US, where the app would otherwise auto-select English).
    2. Any QTranslator already installed on the session-scoped QApplication
       (left over from a prior AppCoordinator test) must be removed so widgets
       built in this test see the source strings.

    Both are handled here; a no-op when PySide6 / QApplication are absent.
    """
    try:
        from petgen import i18n

        # 1. Pin locale resolution to the source language.
        monkeypatch.setattr(i18n, "resolve_language", lambda _pref=None: "zh_CN")

        # 2. Clear any translator already on the app.
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        if app is not None:
            i18n.install_translator(app, "zh_CN")
    except Exception:
        # No QApplication yet or PySide6 absent — nothing to reset.
        pass
    yield
