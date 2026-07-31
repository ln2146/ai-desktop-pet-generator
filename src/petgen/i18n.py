"""Qt translation loading and language resolution for the PetGen GUI.

The source language of every ``tr()``/``translate()`` string in the codebase is
**Chinese** (simplified). When no translator is loaded for the resolved language,
Qt returns the source string verbatim — so the app is Chinese by default, and a
loaded ``app_en.qm`` swaps it to English. This keeps tests green: they run with
no translator installed and see the original Chinese literals.

Language resolution:
* ``"auto"`` (default) inspects ``QLocale.system()`` — any Chinese locale maps
  to ``zh_CN``, everything else falls back to ``en``.
* an explicit value (``"zh_CN"`` / ``"en"``) is used as-is.

Translation files live under ``petgen/resources/i18n`` (``app_<lang>.qm``), so
they are bundled by PyInstaller via the same ``datas`` entry that ships the rest
of ``resources/``.
"""
from __future__ import annotations

import logging
from pathlib import Path

_I18N_DIR = Path(__file__).resolve().parent / "resources" / "i18n"
log = logging.getLogger(__name__)

#: Supported language ids in display order. The display labels are themselves
#: translated via ``QCoreApplication.translate`` so the picker follows the
#: active language; the special ``"auto"`` entry means "follow the OS".
LANGUAGES: tuple[tuple[str, str], ...] = (
    ("auto", "Follow system / 跟随系统"),
    ("zh_CN", "简体中文"),
    ("en", "English"),
)


def available_locales() -> tuple[tuple[str, str], ...]:
    """Return ``(id, label)`` pairs for the settings language picker."""
    return LANGUAGES


def resolve_language(pref: str | None) -> str:
    """Map a stored preference to a concrete language id we ship a .qm for.

    ``"auto"``/``""``/``None`` -> system locale guess (zh* -> zh_CN else en);
    an unknown value degrades to ``en`` rather than leaving the UI untranslated
    mid-flight (the source is Chinese, so a missing en file still falls back to
    Chinese via Qt's no-translator behavior).
    """
    pref = (pref or "").strip()
    if pref and pref != "auto":
        return pref if pref in ("zh_CN", "en") else "en"
    try:
        from PySide6.QtCore import QLocale

        system = QLocale.system()
        # bcp47Name() yields e.g. "zh-CN", "zh-Hans-CN", "en-US".
        if system.bcp47Name().lower().startswith("zh"):
            return "zh_CN"
    except Exception:  # pragma: no cover - QLocale unavailable in headless tests
        pass
    return "en"


def install_translator(app, language: str) -> bool:
    """Install the Qt translator for ``language`` onto ``app``.

    Chinese (the source language) needs no translator: ``tr()`` returns the
    source text directly, so we skip loading (and skip a spurious "failed to
    load" log). For every other language we look for
    ``resources/i18n/app_<lang>.qm`` next to this module.

    Returns True if a translator was installed (or no translator was needed for
    the source language), False if the requested .qm could not be loaded.
    """
    # Keep a handle on the translator so it isn't garbage-collected (Qt keeps a
    # weak-ish relationship; the Python ref must persist for the app lifetime).
    global _active_translator
    global _active_language
    if _active_translator is not None:
        try:
            app.removeTranslator(_active_translator)
        except Exception:  # pragma: no cover - defensive
            pass
        _active_translator = None

    # Source language: nothing to translate, strings render as-is.
    if language in ("", "zh_CN"):
        _active_language = "zh_CN"
        return True

    from PySide6.QtCore import QTranslator

    qm = _I18N_DIR / f"app_{language}.qm"
    translator = QTranslator()
    if translator.load(str(qm)):
        app.installTranslator(translator)
        _active_translator = translator
        _active_language = language
        return True
    # .qm missing or unreadable: leave the app on the source language rather
    # than crashing startup, but do not fail silently; a selected language that
    # cannot load is user-visible and should be diagnosable.
    _active_language = "zh_CN"
    log.warning("failed to load translation file for language %s: %s", language, qm)
    return False


def current_language() -> str:
    """Return the currently active concrete UI language."""
    return _active_language


def _label(source: str, *, en: str) -> str:
    if _active_language == "en":
        return en
    return source


def interaction_style_label(style_id: str, fallback: str) -> str:
    """Localized display label for built-in interaction styles."""
    labels = {
        "moe-pet": ("萌宠风", "Soft Pet"),
        "moe-girl": ("萌妹风", "Cheerful Girl"),
        "elegant-senior": ("御姐风", "Elegant Senior"),
        "butler": ("管家风", "Butler"),
        "sunny-boy": ("清爽男声", "Sunny Boy"),
        "steady-senior": ("沉稳男声", "Steady Senior"),
        "tsundere": ("傲娇风", "Tsundere"),
    }
    zh, en = labels.get(style_id, (fallback, fallback))
    return _label(zh, en=en)


def recurrence_label(recurrence: str) -> str:
    """Localized label for persisted recurrence keys."""
    labels = {
        "none": ("不重复", "No repeat"),
        "daily": ("每天", "Daily"),
        "weekdays": ("工作日", "Weekdays"),
        "weekdays_full": ("工作日 (周一至周五)", "Weekdays (Mon-Fri)"),
        "weekly": ("每周", "Weekly"),
        "monthly": ("每月", "Monthly"),
        "custom_weekly": ("自定义", "Custom"),
    }
    zh, en = labels.get(recurrence, (recurrence, recurrence))
    return _label(zh, en=en)


def weekday_short_label(weekday: int) -> str:
    """Localized short weekday label, where 0 is Monday."""
    labels = (
        ("一", "Mon"),
        ("二", "Tue"),
        ("三", "Wed"),
        ("四", "Thu"),
        ("五", "Fri"),
        ("六", "Sat"),
        ("日", "Sun"),
    )
    try:
        zh, en = labels[int(weekday)]
    except (TypeError, ValueError, IndexError):
        return str(weekday)
    return _label(zh, en=en)


def tool_status_label(source: str) -> str:
    """Localized label for tool connection status chips."""
    labels = {
        "✅ 已接通": "✅ Connected",
        "⚠️ 需重连": "⚠️ Reconnect",
        "○ 未接通": "○ Not connected",
        "未检测到": "Not detected",
    }
    return _label(source, en=labels.get(source, source))


_active_translator = None
_active_language = "zh_CN"
