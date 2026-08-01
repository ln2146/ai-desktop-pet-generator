from __future__ import annotations

import sys
import uuid
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, QThread, QTimer, Signal
from PySide6.QtWidgets import QApplication

from petgen.bubble import BubbleWindow
from petgen.datadir import data_dir
from petgen.eventbus import EventBus, expression_for_kind
from petgen.interaction_style import normalize_style_id
from petgen.library import PetLibrary
from petgen.library_dialog import LibraryDialog
from petgen.pet_manifest import FrameAtlas, load_manifest
from petgen.settings_dialog import SettingsDialog
from petgen.store import AiEventStore, PetRegistry, SettingsStore
from petgen.tray import TrayController
from petgen.usage_tracker import SNAPSHOT_KEY, UsageTracker


def _config_overrides(settings: SettingsStore) -> dict:
    return {
        "api_key": settings.get("ai.api_key") or None,
        "base_url": settings.get("ai.base_url") or None,
        "model": settings.get("ai.image_model") or None,
    }


class BuildResult:
    """Cross-thread payload handed from the generation QThread to the main thread.

    Wrapped in a plain object (not a dict) because PySide6's ``Signal(object)``
    tries to copy-convert built-in containers to C++ types and drops them; a
    custom Python instance is passed through untouched.
    """

    __slots__ = ("pet_id", "paths", "model", "prompt", "description")

    def __init__(
        self,
        pet_id: str,
        paths: dict[str, str],
        model: str,
        prompt: str,
        description: str,
    ) -> None:
        self.pet_id = pet_id
        self.paths = paths
        self.model = model
        self.prompt = prompt
        self.description = description


def _set_macos_accessory_policy() -> None:
    """Drop the interpreter's Dock icon on macOS by becoming a UI accessory.

    Run as a bare ``python`` process, macOS registers the GUI under the
    interpreter's own app (the rocket icon) and shows it in the Dock. Switching
    the activation policy to *accessory* keeps the tray icon and every floating
    window/dialog interactive while removing the Dock entry and the app menu.

    No-op off-platform, in the offscreen self-check platform, and if the Cocoa
    call is unavailable for any reason — this is purely cosmetic and must never
    break startup.
    """
    if sys.platform != "darwin":
        return
    try:
        from PySide6.QtGui import QGuiApplication

        if QGuiApplication.platformName() == "offscreen":
            return  # headless self-check: no real Dock to hide, skip AppKit

        import ctypes
        import ctypes.util

        lib = ctypes.cdll.LoadLibrary(
            ctypes.util.find_library("objc") or "/usr/lib/libobjc.A.dylib"
        )
        lib.objc_getClass.restype = ctypes.c_void_p
        lib.objc_getClass.argtypes = [ctypes.c_char_p]
        lib.sel_registerName.restype = ctypes.c_void_p
        lib.sel_registerName.argtypes = [ctypes.c_char_p]
        send = lib.objc_msgSend
        send.restype = ctypes.c_void_p
        send.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        nsapp = send(
            lib.objc_getClass(b"NSApplication"),
            lib.sel_registerName(b"sharedApplication"),
        )
        if not nsapp:
            return
        send.restype = ctypes.c_bool
        send.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_long]
        send(nsapp, lib.sel_registerName(b"setActivationPolicy:"), 1)  # Accessory
    except Exception:  # noqa: BLE001 - cosmetic only
        pass


def _activate_macos_app() -> None:
    """Force the current process to the foreground on macOS.

    Under the Accessory activation policy, ``QWindow.activateWindow()`` is a
    polite request that macOS routinely ignores when another app holds the
    focus — so the dialog window is created but stays buried behind the front
    app, and only a sliver of it (e.g. an inner config row) peeks out. That is
    the root cause of "clicking the tray sometimes shows a tiny window."

    ``activateIgnoringOtherApps:YES`` alone is not enough when the app already
    has visible but non-focus-accepting windows (the pet/bubble): the window
    server keeps treating the app as a background accessory and refuses the
    activation. The reliable fix is to **briefly flip the activation policy to
    Regular** — this re-arms the app as a normal foreground app, forces a fresh
    activation, then restores Accessory so the Dock icon stays hidden
    afterwards. This is the same mechanism Qt's own window-raising uses. No-op
    off-platform and in the offscreen self-check platform.
    """
    if sys.platform != "darwin":
        return
    try:
        from PySide6.QtGui import QGuiApplication

        if QGuiApplication.platformName() == "offscreen":
            return
        import ctypes
        import ctypes.util

        lib = ctypes.cdll.LoadLibrary(
            ctypes.util.find_library("objc") or "/usr/lib/libobjc.A.dylib"
        )
        lib.objc_getClass.restype = ctypes.c_void_p
        lib.objc_getClass.argtypes = [ctypes.c_char_p]
        lib.sel_registerName.restype = ctypes.c_void_p
        lib.sel_registerName.argtypes = [ctypes.c_char_p]
        send = lib.objc_msgSend
        send.restype = ctypes.c_void_p
        send.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        nsapp = send(
            lib.objc_getClass(b"NSApplication"),
            lib.sel_registerName(b"sharedApplication"),
        )
        if not nsapp:
            return

        # Flip activation policy Regular (0) -> activate -> back to Accessory (1).
        # The brief Regular interval is what actually lets the window server
        # promote us to the foreground; staying Regular would re-add the Dock icon.
        send.restype = ctypes.c_bool
        send.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_long]
        set_policy = lib.sel_registerName(b"setActivationPolicy:")
        send(nsapp, set_policy, 0)  # NSApplicationActivationPolicyRegular

        send.restype = None
        send.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_bool]
        send(nsapp, lib.sel_registerName(b"activateIgnoringOtherApps:"), True)

        # Restore Accessory immediately — the activation above has already taken
        # effect synchronously within this call.
        send(nsapp, set_policy, 1)  # NSApplicationActivationPolicyAccessory
    except Exception:  # noqa: BLE001 - bringing to front must never crash the app
        pass


def _bring_to_front(widget) -> None:
    """Show + raise + activate a top-level widget so it actually appears on top.

    Under the macOS Accessory activation policy (and in several offscreen / WM
    configurations on Linux), ``show()`` + ``raise_()`` alone are NOT enough to
    bring a window to the front — the app lacks foreground standing, so the
    window is created but stays buried behind other apps' windows. On macOS we
    additionally force the app itself into the foreground via Cocoa
    (``activateIgnoringOtherApps``); ``activateWindow()`` alone is a polite
    request that macOS ignores when another app holds focus, which is why a
    dialog sometimes appears as just a sliver peeking out from under the front
    app.

    A second ``activateWindow`` is re-issued off the next event-loop tick. Tray
    dialogs are opened via ``QTimer.singleShot(0, ...)`` to dodge the native
    status-menu teardown; by the time that callback runs macOS has often handed
    focus back to the previously front app (the pet/bubble windows are
    ``WindowDoesNotAcceptFocus`` and cannot hold it), so a single
    ``activateWindow`` at callback time loses the race. Re-arming it one tick
    later wins the focus back after the menu is fully gone.
    """
    _activate_macos_app()
    widget.show()
    widget.raise_()
    widget.activateWindow()
    # Re-assert activation after the menu has fully torn down.
    QTimer.singleShot(0, widget.activateWindow)


class GenerationWorker(QThread):
    progress = Signal(str)
    finished_ok = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        *,
        description: str,
        image_paths: list[str],
        pet_id: str,
        work_dir: Path,
        config_overrides: dict,
        library: PetLibrary,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._description = description
        self._image_paths = image_paths
        self._pet_id = pet_id
        self._work_dir = work_dir
        self._config_overrides = config_overrides
        self._library = library

    def run(self) -> None:  # noqa: D401 - QThread entry
        try:
            from petgen.openai_image import ImageRequestConfig, OpenAIImageClient
            from petgen.prompt import build_pet_prompt
            from petgen.spritesheet import build_pet_assets

            self.progress.emit(self.tr("正在生成形象…"))
            config = ImageRequestConfig.from_env(**self._config_overrides)
            prompt = build_pet_prompt(self._description)
            refs = [Path(p) for p in self._image_paths if p]
            image_bytes = OpenAIImageClient(config).generate(prompt, refs)
            self._work_dir.mkdir(parents=True, exist_ok=True)
            source_path = self._work_dir / "source.png"
            source_path.write_bytes(image_bytes)

            self.progress.emit(self.tr("正在合成精灵图…"))
            paths = build_pet_assets(
                source_path,
                self._work_dir,
                pet_id=self._pet_id,
                description=self._description,
                model=config.model,
                prompt=prompt,
            )
            # Registration touches SQLite, whose connection lives on the main
            # thread; doing it here (a QThread) raises ProgrammingError
            # ("SQLite objects created in a thread can only be used in that same
            # thread"). Emit the built paths and let the main thread register.
            self.progress.emit(self.tr("正在登记到宠物库…"))
            self.finished_ok.emit(
                BuildResult(
                    pet_id=self._pet_id,
                    paths={key: str(value) for key, value in paths.items()},
                    model=config.model,
                    prompt=prompt,
                    description=self._description,
                )
            )
        except Exception as exc:  # surface any failure to the UI thread
            self.failed.emit(str(exc))


class AppCoordinator(QObject):
    def __init__(
        self,
        argv: list[str] | None = None,
        *,
        scale: float | None = None,
        passthrough: bool = True,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._argv = argv or []
        # A QApplication MUST exist before any QSystemTrayIcon call (isSystemTrayAvailable
        # segfaults without one), and the tray is built below, so create it up front.
        app = QApplication.instance() or QApplication(self._argv or ["petgen-app"])
        _set_macos_accessory_policy()
        self.settings = SettingsStore()
        # Install the Qt translator before any widget/dialog is created so every
        # tr() call resolves in the right language from the start. Source
        # language is Chinese; an app_en.qm swaps it to English. Settings must
        # exist first so we can read the stored language preference.
        from petgen import i18n

        i18n.install_translator(
            app, i18n.resolve_language(self.settings.get("ui.language", "auto"))
        )
        self._scale_override = scale
        self._passthrough = passthrough
        self._quiet = False
        self._pet_visible_requested = True
        self._worker: GenerationWorker | None = None

        self.registry = PetRegistry()
        self.library = PetLibrary(self.registry)
        self.event_store = AiEventStore()
        self.bus = EventBus()
        self.tray = TrayController()
        self.bubble = BubbleWindow()

        from petgen.speak import VoicePackService

        self.voice = VoicePackService(
            enabled=bool(self.settings.get("pet.sound_enabled", True)),
        )
        style_id = self._current_interaction_style_id()
        if self.settings.get("pet.interaction_style") != style_id:
            self.settings.set("pet.interaction_style", style_id)
        self.voice.set_style(style_id)

        self.pet_window = None
        self.library_dialog: LibraryDialog | None = None
        self.settings_dialog: SettingsDialog | None = None

        # reminders + pomodoro
        from petgen.pomodoro import PomodoroService
        from petgen.reminder_scheduler import ReminderScheduler
        from petgen.store import ReminderStore

        self.reminder_store = ReminderStore()
        self.reminder_scheduler = ReminderScheduler(self.reminder_store)
        self.reminder_scheduler.reminder_due.connect(self._on_reminder_due)
        self.pomodoro = PomodoroService()
        self.pomodoro.finished.connect(self._on_pomodoro_finished)
        self._due_timer = QTimer(self)
        self._due_timer.setInterval(20000)
        self._due_timer.timeout.connect(self.reminder_scheduler.check_due)
        self.reminder_list_dialog = None
        self.reminder_editor_dialog = None
        self.quick_capture_dialog = None
        self.pomodoro_window = None

        # usage tracking + rest nudges
        self.usage_tracker = UsageTracker(
            enabled=bool(self.settings.get("pet.usage_reminder_enabled", True)),
            work_threshold_seconds=max(1, int(self.settings.get("pet.usage_work_threshold", 45))) * 60,
        )
        self.usage_tracker.load_snapshot(self.settings.get(SNAPSHOT_KEY))
        self.usage_tracker.rest_reminder.connect(self._on_rest_reminder)
        self.usage_panel_dialog = None
        self._usage_timer = QTimer(self)
        self._usage_timer.setInterval(20000)
        self._usage_timer.timeout.connect(self._on_usage_tick)
        self._usage_last_tick_at: datetime | None = None
        self._usage_last_save_at: datetime | None = None
        self._usage_idle_warning_shown = False

    # --- lifecycle ----------------------------------------------------------

    def bootstrap(self) -> None:
        self._wire_tray()
        self.bus.event_received.connect(self._on_event)
        self.bus.warnings.connect(
            lambda msgs: [print(f"petgen: {m}", file=sys.stderr) for m in msgs]
        )
        if self.tray.is_available():
            self.tray.show()

    def run(self) -> int:
        from petgen.theme import apply_theme

        app = QApplication.instance() or QApplication(self._argv or ["petgen-app"])
        app.setQuitOnLastWindowClosed(False)
        apply_theme(app)
        app.setApplicationName("PetGen")
        self.bootstrap()
        self._reload_pet()
        self.bus.start()
        self._due_timer.start()
        self.reminder_scheduler.check_due()  # surface anything already overdue at startup
        self._start_usage_tracking()
        return app.exec()

    # --- wiring -------------------------------------------------------------

    def _wire_tray(self) -> None:
        t = self.tray
        t.show_pet_requested.connect(self._set_pet_visible)
        t.library_requested.connect(lambda: self._defer_ui_open(self._open_library))
        t.settings_requested.connect(lambda: self._defer_ui_open(self._open_settings))
        t.about_requested.connect(lambda: self._defer_ui_open(self._open_settings))
        t.quiet_toggled.connect(self._set_quiet)
        t.quick_capture_requested.connect(lambda: self._defer_ui_open(self._open_quick_capture))
        t.reminder_list_requested.connect(lambda: self._defer_ui_open(self._open_reminder_list))
        t.pomodoro_requested.connect(lambda: self._defer_ui_open(self._open_pomodoro))
        t.usage_requested.connect(lambda: self._defer_ui_open(self._open_usage_panel))
        t.quit_requested.connect(self._quit)

    @staticmethod
    def _defer_ui_open(callback) -> None:
        """Open tray-launched dialogs on the next event-loop tick.

        Native tray menus can still be tearing down when the QAction fires.
        Deferring avoids cases where a dialog is technically shown but never
        surfaces on macOS / some Linux shells because the menu kept focus for
        the rest of the callback turn.
        """
        QTimer.singleShot(0, callback)

    def _selected_id(self) -> str | None:
        return self.settings.get("pet.selected_id")

    # --- pet window ---------------------------------------------------------

    def _reload_pet(self) -> None:
        from petgen.desktop_window import PetWindow

        record = self.library.resolve_selected(self.settings)
        if self.pet_window is not None:
            self.pet_window.close()
            self.pet_window = None
        if record is None:
            self.tray.set_pet_visible(False)
            return
        try:
            manifest = load_manifest(record.manifest_path)
            atlas = FrameAtlas.load(manifest.sprite_path, manifest.frame)
        except Exception as exc:  # corrupt / missing assets must not crash startup
            print(
                f"petgen: failed to load pet {record.id!r} ({exc}); clearing selection",
                file=sys.stderr,
            )
            self.settings.set("pet.selected_id", None)
            self.tray.set_pet_visible(False)
            if self.bubble is not None:
                try:
                    self.bubble.show_message(self.tr("宠物素材损坏，已跳过：{0}").format(str(exc)))
                except Exception:  # noqa: BLE001 - bubble is best-effort at startup
                    pass
            return
        scale = self._scale_override or float(self.settings.get("pet.scale", 1.5))
        window = PetWindow(
            manifest,
            atlas,
            scale=scale,
            passthrough=self._passthrough,
            overlays=True,
            motion=bool(self.settings.get("pet.motion_enabled", True)),
        )
        window.pet_clicked.connect(self._on_pet_clicked)
        window.pet_context_menu_requested.connect(lambda pos: self.tray.menu().exec(pos))
        window.pet_moved.connect(self.bubble.anchor_to)
        window.scale_changed.connect(lambda s: self.settings.set("pet.scale", float(s)))
        self.pet_window = window
        self.tray.set_icon_from_preview(record.preview_path)
        if self._pet_visible_requested:
            window.show()
        self.tray.set_pet_visible(self._pet_visible_requested)

    def _set_pet_visible(self, visible: bool) -> None:
        self._pet_visible_requested = bool(visible)
        if self.pet_window is None:
            self.tray.set_pet_visible(False)
            if visible:
                self._open_library()
            return
        if visible:
            self.pet_window.show()
            self.tray.set_pet_visible(True)
        else:
            self.pet_window.hide()
            self.tray.set_pet_visible(False)

    # --- events / interaction ----------------------------------------------

    def _on_event(self, event) -> None:
        self.event_store.append(
            {
                "id": event.id,
                "kind": event.kind,
                "title": event.title,
                "detail": event.detail,
                "source": event.source,
                "created_at": event.created_at,
            }
        )
        if self._quiet:
            return
        if self.pet_window is not None:
            self.pet_window.set_expression(expression_for_kind(event.kind))
            if event.kind == "task_completed":
                self.pet_window.celebrate()
        self.bubble.show_message(event.display_message())
        if self.pet_window is not None:
            self.bubble.anchor_to(self.pet_window.frameGeometry())
        # interaction styles map ai_* / task_completed -> their alert/happy/busy/error sounds+lines
        self.voice.react(expression_for_kind(event.kind))

    def _on_pet_clicked(self) -> None:
        if self._quiet:
            return
        if self.pet_window is not None:
            self.pet_window.set_expression("attentive")
        # keep the bubble text in sync with what the interaction style speaks.
        from petgen import i18n

        language = i18n.current_language()
        fallback = "I'm here." if language == "en" else self.tr("我在。")
        line = self.voice.pack.line_for("tap", language) or fallback
        self.bubble.show_message(line)
        if self.pet_window is not None:
            self.bubble.anchor_to(self.pet_window.frameGeometry())
        self.voice.react("tap", line)

    # --- dialogs ------------------------------------------------------------

    def _open_library(self) -> None:
        if self.library_dialog is None:
            self.library_dialog = LibraryDialog()
            self.library_dialog.pet_selected.connect(self._select_pet)
            self.library_dialog.delete_requested.connect(self._delete_pet)
            self.library_dialog.rename_requested.connect(self._rename_pet)
            self.library_dialog.import_requested.connect(self._import_dir)
            self.library_dialog.create_requested.connect(self._create_pet)
            self.library_dialog.refresh_requested.connect(self._refresh_library)
            self.library_dialog.scale_changed.connect(self._on_library_scale_changed)
            self.library_dialog.interaction_style_changed.connect(
                self._on_library_interaction_style_changed
            )
            self.library_dialog.preview_style_requested.connect(self._preview_interaction_style)
            # The dialog is a top-level Qt.Window. If we keep the Python reference
            # after the user closes it, the underlying QWidget is only hidden, not
            # destroyed — a "zombie" window lingers in the window manager and, under
            # the macOS Accessory policy, resurfaces later as a collapsed/abnormal
            # sliver. Drop the reference on close so the next open rebuilds a fresh,
            # correctly-sized dialog (same pattern as reminder_editor_dialog).
            self.library_dialog.finished.connect(self._discard_library_dialog)
        self._refresh_library()
        _bring_to_front(self.library_dialog)

    def _discard_library_dialog(self) -> None:
        """Drop the library dialog reference when it closes so it is GC'd.

        ``QDialog.finished`` fires for both accept and reject (the red close
        button, Esc, etc.), so this single hook covers every close path.
        """
        if self.library_dialog is not None:
            dlg = self.library_dialog
            self.library_dialog = None
            dlg.deleteLater()

    def _refresh_library(self) -> None:
        if self.library_dialog is not None:
            self.library_dialog.refresh(self.library.list_pets(), self._selected_id())
            scale = float(self.settings.get("pet.scale", 1.5))
            self.library_dialog.set_scale_value(scale)
            self.library_dialog.set_interaction_style_value(self._current_interaction_style_id())

    def _on_library_scale_changed(self, scale: float) -> None:
        self.settings.set("pet.scale", float(scale))
        if self.pet_window is not None:
            self.pet_window.set_scale(float(scale))

    def _current_interaction_style_id(self) -> str:
        saved = self.settings.get("pet.interaction_style")
        if saved:
            return normalize_style_id(saved)
        legacy_pack = self.settings.get("pet.voice_pack")
        if legacy_pack:
            return normalize_style_id(legacy_pack)
        return normalize_style_id(self.settings.get("pet.personality"))

    def _on_library_interaction_style_changed(self, style_id: str) -> None:
        style_id = normalize_style_id(style_id)
        if style_id not in self.voice.styles:
            self.bubble.show_message(self.tr("未知互动风格：{0}").format(style_id))
            return
        self.settings.set("pet.interaction_style", style_id)
        self.voice.set_style(style_id)

    def _preview_interaction_style(self) -> None:
        try:
            from petgen.speak import VoicePackService

            style_id = self._current_interaction_style_id()
            style = self.voice.styles.get(style_id)
            if style is None:
                self.bubble.show_message(self.tr("未知互动风格：{0}").format(style_id))
                return
            svc = getattr(self, "_preview_voice_svc", None)
            if svc is None:
                svc = VoicePackService(
                    style,
                    enabled=True,
                )
                self._preview_voice_svc = svc
            else:
                svc.set_style(style.id)
            svc.set_enabled(True)
            svc.preview()
        except Exception as exc:  # noqa: BLE001 - keep the UI alive and surface the failure
            self.bubble.show_message(self.tr("试听失败：{0}").format(str(exc)))

    def _select_pet(self, pet_id: str) -> None:
        self.library.select(self.settings, pet_id)
        self._reload_pet()
        self._refresh_library()

    def _delete_pet(self, pet_id: str) -> None:
        self.library.delete_pet(pet_id)
        if self._selected_id() == pet_id:
            self.settings.set("pet.selected_id", None)
        self._reload_pet()
        self._refresh_library()

    def _rename_pet(self, pet_id: str, new_name: str) -> None:
        if not self.library.rename(pet_id, new_name):
            return
        self._reload_pet()
        self._refresh_library()

    def _import_dir(self, directory: str) -> None:
        try:
            record = self.library.import_existing_dir(Path(directory))
        except Exception as exc:
            self.bubble.show_message(self.tr("导入失败：{0}").format(str(exc)))
            return
        self._select_pet(record.id)
        self.bubble.show_message(self.tr("已导入「{0}」").format(record.display_name))

    def _create_pet(self, description: str, image_paths: list) -> None:
        if not description.strip():
            self.bubble.show_message(self.tr("描述不能为空"))
            return
        # A previous generation is still running: reassigning self._worker would
        # drop the last Python reference to a live QThread and abort the process
        # ("QThread: Destroyed while thread is still running"). Ignore the new
        # request and tell the user instead of racing the prior worker.
        if self._worker is not None and self._worker.isRunning():
            self.bubble.show_message(self.tr("上一次生成还在进行中，请稍候…"))
            return
        pet_id = f"pet-{uuid.uuid4().hex[:12]}"
        work_dir = data_dir() / "workspace" / pet_id
        self._worker = GenerationWorker(
            description=description.strip(),
            image_paths=list(image_paths or []),
            pet_id=pet_id,
            work_dir=work_dir,
            config_overrides=_config_overrides(self.settings),
            library=self.library,
        )
        self._worker.progress.connect(self._on_gen_progress)
        self._worker.finished_ok.connect(self._on_gen_done)
        self._worker.failed.connect(self._on_gen_failed)
        # Keep the QThread alive until it finishes: dropping the last Python
        # reference while it runs aborts the process ("QThread: Destroyed while
        # thread is still running"). deleteLater reclaims it once done.
        self._worker.finished.connect(self._worker.deleteLater)
        if self.library_dialog is not None:
            self.library_dialog.set_progress(self.tr("正在生成形象…"))
        self._worker.start()

    def _on_gen_progress(self, text: str) -> None:
        if self.library_dialog is not None:
            self.library_dialog.set_progress(text)
        self.bubble.show_message(text, timeout_ms=4000)

    def _on_gen_done(self, result: BuildResult) -> None:
        if self.library_dialog is not None:
            self.library_dialog.set_progress("")
        # Registration runs here on the main thread (the worker only produced
        # files) so the SQLite connection is never used cross-thread.
        paths = {key: Path(value) for key, value in result.paths.items()}
        try:
            record = self.library.register_build(
                paths,
                pet_id=result.pet_id,
                model=result.model,
                prompt=result.prompt,
                description=result.description,
            )
        except Exception as exc:
            self.bubble.show_message(self.tr("登记失败：{0}").format(str(exc)))
            return
        self._select_pet(record.id)
        if self.pet_window is not None:
            self.pet_window.set_expression("happy")
            self.pet_window.celebrate()
        self.bubble.show_message(self.tr("新伙伴「{0}」来啦！").format(record.display_name))

    def _on_gen_failed(self, message: str) -> None:
        if self.library_dialog is not None:
            self.library_dialog.set_progress("")
        if self.pet_window is not None:
            self.pet_window.set_expression("error")
        self.bubble.show_message(self.tr("生成失败：{0}").format(message))

    def _open_settings(self) -> None:
        if self.settings_dialog is None:
            self.settings_dialog = SettingsDialog(self.settings)
            self.settings_dialog.applied.connect(self._apply_settings)
        self.settings_dialog.load_values()
        _bring_to_front(self.settings_dialog)

    def _apply_settings(self) -> None:
        # scale lives in the fixed-size window, so any settings save rebuilds the pet
        self._reload_pet()
        self.voice.set_style(self._current_interaction_style_id())
        sound_on = bool(self.settings.get("pet.sound_enabled", True)) and not self._quiet
        self.voice.set_enabled(sound_on)
        self.usage_tracker.configure(
            enabled=bool(self.settings.get("pet.usage_reminder_enabled", True)),
            work_threshold_seconds=max(1, int(self.settings.get("pet.usage_work_threshold", 45))) * 60,
        )

    def _set_quiet(self, quiet: bool) -> None:
        # Quiet = "do not disturb": the pet STAYS visible but stops reacting
        # (no bubbles / no event-driven expressions / no click replies). Visibility
        # is owned solely by the "显示宠物" toggle, so quiet no longer hides the pet.
        self._quiet = quiet
        self.tray.set_quiet(quiet)
        self.voice.set_enabled(not quiet and bool(self.settings.get("pet.sound_enabled", True)))
        if self.pet_window is not None and not quiet:
            self.pet_window.set_expression("idle")

    # --- reminders + pomodoro ----------------------------------------------

    def _open_quick_capture(self) -> None:
        from petgen.reminder_nl import parse_reminder_text
        from petgen.reminder_quick import QuickCaptureDialog

        # Reuse the existing dialog if it is still alive: previously every open
        # built a fresh QDialog and dropped the reference to the prior one,
        # orphaning it (and its signals) for the rest of the session.
        if self.quick_capture_dialog is None:
            self.quick_capture_dialog = QuickCaptureDialog(parser=parse_reminder_text)
            self.quick_capture_dialog.quick_created.connect(self._create_reminder)
        else:
            # Reset the input so reopening feels like a fresh capture.
            self.quick_capture_dialog.input.clear()
        _bring_to_front(self.quick_capture_dialog)

    def _create_reminder(self, data: dict) -> None:
        try:
            reminder = self.reminder_scheduler.create(
                data["title"],
                data["trigger_at"],
                recurrence=data.get("recurrence", "none"),
                custom_weekdays=data.get("custom_weekdays") or [],
            )
        except Exception as exc:
            self.bubble.show_message(self.tr("新建提醒失败：{0}").format(str(exc)))
            return
        self._refresh_reminder_list()
        if not self._quiet:
            self.bubble.show_message(self.tr("已设置提醒：{0}").format(reminder.title))

    def _open_reminder_list(self) -> None:
        from petgen.reminder_list import ReminderListDialog

        if self.reminder_list_dialog is None:
            self.reminder_list_dialog = ReminderListDialog()
            self.reminder_list_dialog.new_requested.connect(self._open_reminder_editor)
            self.reminder_list_dialog.complete_requested.connect(self._complete_reminder)
            self.reminder_list_dialog.snooze_requested.connect(self._snooze_reminder)
            self.reminder_list_dialog.edit_requested.connect(self._edit_reminder)
            self.reminder_list_dialog.delete_requested.connect(self._delete_reminder)
        self._refresh_reminder_list()
        _bring_to_front(self.reminder_list_dialog)

    def _refresh_reminder_list(self) -> None:
        if self.reminder_list_dialog is not None:
            self.reminder_list_dialog.refresh(self.reminder_store.list_active())

    def _open_reminder_editor(self, reminder=None) -> None:
        from petgen.reminder_editor import ReminderEditorDialog

        # The editor carries per-open state (which reminder is being edited, via
        # _editing_id), so we cannot just raise the old one. But we must not
        # leak it either: close + deleteLater the previous dialog before opening
        # a new one, otherwise each edit accumulates an orphaned QDialog.
        if self.reminder_editor_dialog is not None:
            old = self.reminder_editor_dialog
            self.reminder_editor_dialog = None
            old.close()
            old.deleteLater()
        self.reminder_editor_dialog = ReminderEditorDialog(reminder)
        self.reminder_editor_dialog.reminder_saved.connect(self._save_reminder)
        _bring_to_front(self.reminder_editor_dialog)

    def _save_reminder(self, data: dict) -> None:
        try:
            if data.get("id"):
                updated = self.reminder_scheduler.update(
                    data["id"],
                    title=data["title"],
                    trigger_at=data["trigger_at"],
                    recurrence=data.get("recurrence", "none"),
                    custom_weekdays=data.get("custom_weekdays") or [],
                )
                if updated is None:
                    self._create_reminder(data)  # vanished; recreate instead
            else:
                self._create_reminder(data)
        except Exception as exc:
            self.bubble.show_message(self.tr("保存提醒失败：{0}").format(str(exc)))
            return
        self._refresh_reminder_list()

    def _edit_reminder(self, reminder_id: str) -> None:
        reminder = self.reminder_store.get(reminder_id)
        if reminder is not None:
            self._open_reminder_editor(reminder)

    def _complete_reminder(self, reminder_id: str) -> None:
        self.reminder_scheduler.complete(reminder_id)
        self._refresh_reminder_list()

    def _snooze_reminder(self, reminder_id: str) -> None:
        self.reminder_scheduler.snooze(reminder_id)
        self._refresh_reminder_list()
        if not self._quiet:
            self.bubble.show_message(self.tr("已稍后提醒 ⏰"))

    def _delete_reminder(self, reminder_id: str) -> None:
        self.reminder_scheduler.delete(reminder_id)
        self._refresh_reminder_list()

    def _on_reminder_due(self, reminder) -> None:
        if self._quiet:
            return
        if self.pet_window is not None:
            self.pet_window.set_expression("alert")
        self.voice.react("alert")
        actions = [
            (self.tr("完成啦"), lambda rid=reminder.id: self._complete_reminder(rid)),
            (self.tr("等会儿"), lambda rid=reminder.id: self._snooze_reminder(rid)),
            (self.tr("知道啦"), lambda: None),
        ]
        self.bubble.show_message(
            self.tr("叮咚~ {0} 时间到啦 ✨").format(reminder.title), actions=actions, timeout_ms=0
        )
        if self.pet_window is not None:
            self.bubble.anchor_to(self.pet_window.frameGeometry())

    def _open_pomodoro(self) -> None:
        from petgen.pomodoro import PomodoroWindow

        # Reuse the live window: PomodoroWindow binds to the shared service, and
        # rebuilding it each open orphans the previous QDialog (and re-connects
        # its signals to the service, doubling tick handlers).
        if self.pomodoro_window is None:
            self.pomodoro_window = PomodoroWindow(self.pomodoro)
        _bring_to_front(self.pomodoro_window)

    def _on_pomodoro_finished(self, phase: str) -> None:
        from petgen.pomodoro import BREAK

        if self._quiet:
            return
        if self.pet_window is not None:
            self.pet_window.set_expression("happy")
            self.pet_window.celebrate()
        self.voice.react("happy")
        msg = self.tr("🍅 专注完成，休息一下吧！") if phase != BREAK else self.tr("☕ 休息结束，继续加油！")
        self.bubble.show_message(msg)
        if self.pet_window is not None:
            self.bubble.anchor_to(self.pet_window.frameGeometry())

    # --- usage tracking + rest nudges --------------------------------------

    def _start_usage_tracking(self) -> None:
        self._usage_last_tick_at = datetime.now()
        self._usage_last_save_at = datetime.now()
        self._on_usage_tick()  # prime the state with a single sample
        self._usage_timer.start()

    def _on_usage_tick(self) -> None:
        from petgen.idle_time import get_idle_seconds
        from petgen.reminder import utcnow

        now = datetime.now()
        # Truncate the gap so a long sleep/suspend can't dump an hour into the
        # active count at once. 120s matches the tracker's own tick resolution.
        if self._usage_last_tick_at is None:
            elapsed = 0
        else:
            elapsed = min(int((now - self._usage_last_tick_at).total_seconds()), 120)
        self._usage_last_tick_at = now

        idle_seconds = get_idle_seconds()
        if idle_seconds is None and not self._usage_idle_warning_shown:
            print(
                "petgen: system idle time unavailable; usage stats are estimated from app runtime",
                file=sys.stderr,
            )
            self._usage_idle_warning_shown = True
        self.usage_tracker.tick(idle_seconds, utcnow(), elapsed=elapsed)

        # Persist the day's totals every ~60s (and on rollover/quit), not every
        # tick, to keep the settings table write volume down.
        if self._usage_last_save_at is None or (now - self._usage_last_save_at).total_seconds() >= 60:
            self._save_usage_snapshot(now)

    def _save_usage_snapshot(self, saved_at: datetime | None = None) -> None:
        from petgen.reminder import utcnow

        self.settings.set(SNAPSHOT_KEY, self.usage_tracker.snapshot(utcnow()))
        self._usage_last_save_at = saved_at or datetime.now()

    def _on_rest_reminder(self, info: dict) -> None:
        if self._quiet:
            return
        mins = info.get("active_minutes", 0)
        if self.pet_window is not None:
            self.pet_window.set_expression("alert")
        self.voice.react("alert")
        actions = [
            (self.tr("休息一下"), lambda: self.usage_tracker.take_break()),
            (self.tr("再等 10 分钟"), lambda: self.usage_tracker.snooze(10 * 60)),
            (self.tr("知道啦"), lambda: None),
        ]
        self.bubble.show_message(
            self.tr("你已经连续用电脑 {0} 分钟啦，起来动一动、看看远处吧 🌿").format(str(mins)),
            actions=actions,
            timeout_ms=0,
        )
        if self.pet_window is not None:
            self.bubble.anchor_to(self.pet_window.frameGeometry())

    def _open_usage_panel(self) -> None:
        from petgen.usage_panel import UsagePanelDialog

        if self.usage_panel_dialog is None:
            self.usage_panel_dialog = UsagePanelDialog(
                self.usage_tracker,
                reset_callback=self._save_usage_snapshot,
            )
        self.usage_panel_dialog.refresh()
        _bring_to_front(self.usage_panel_dialog)

    def _quit(self) -> None:
        self.bus.stop()
        self._due_timer.stop()
        self._usage_timer.stop()
        self.settings.set(SNAPSHOT_KEY, self.usage_tracker.snapshot())
        # Let an in-flight generation thread exit cleanly instead of being
        # destroyed mid-run (which aborts the process). It only does local file
        # work + a network call, so it returns promptly; the timeout is a safety
        # net so a stuck network request can't hang shutdown.
        if self._worker is not None and self._worker.isRunning():
            self._worker.quit()
            self._worker.wait(3000)
        if self.pet_window is not None:
            self.pet_window.close()
        self.bubble.hide_now()
        QApplication.quit()
