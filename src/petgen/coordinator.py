from __future__ import annotations

import sys
import uuid
from pathlib import Path

from PySide6.QtCore import QObject, QThread, QTimer, Signal
from PySide6.QtWidgets import QApplication, QInputDialog

from petgen.animation import frame_interval_ms
from petgen.bubble import BubbleWindow
from petgen.datadir import data_dir
from petgen.eventbus import EventBus, expression_for_kind
from petgen.library import PetLibrary
from petgen.library_dialog import LibraryDialog
from petgen.personalities import get_personality
from petgen.pet_manifest import FrameAtlas, load_manifest
from petgen.settings_dialog import SettingsDialog
from petgen.store import AiEventStore, PetRegistry, SettingsStore
from petgen.tray import TrayController


def _config_overrides(settings: SettingsStore) -> dict:
    return {
        "api_key": settings.get("ai.api_key") or None,
        "base_url": settings.get("ai.base_url") or None,
        "model": settings.get("ai.image_model") or None,
    }


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
    import sys

    if sys.platform != "darwin":
        return
    try:
        from PySide6.QtGui import QGuiApplication

        if QGuiApplication.platformName() == "offscreen":
            return  # headless self-check: no real Dock to hide, skip AppKit

        import ctypes
        import ctypes.util

        lib = ctypes.cdll.LoadLibrary(ctypes.util.find_library("objc") or "/usr/lib/libobjc.A.dylib")
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


class GenerationWorker(QThread):
    progress = Signal(str)
    finished_ok = Signal(str)
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
            from petgen.openai_image import ImageGenerationError, ImageRequestConfig, OpenAIImageClient
            from petgen.prompt import build_pet_prompt
            from petgen.spritesheet import build_pet_assets

            self.progress.emit("正在生成形象…")
            config = ImageRequestConfig.from_env(**self._config_overrides)
            prompt = build_pet_prompt(self._description)
            refs = [Path(p) for p in self._image_paths if p]
            image_bytes = OpenAIImageClient(config).generate(prompt, refs)
            self._work_dir.mkdir(parents=True, exist_ok=True)
            source_path = self._work_dir / "source.png"
            source_path.write_bytes(image_bytes)

            self.progress.emit("正在合成精灵图…")
            paths = build_pet_assets(
                source_path,
                self._work_dir,
                pet_id=self._pet_id,
                description=self._description,
                model=config.model,
                prompt=prompt,
            )
            self.progress.emit("正在登记到宠物库…")
            record = self._library.register_build(
                paths,
                pet_id=self._pet_id,
                model=config.model,
                prompt=prompt,
                description=self._description,
            )
            self.finished_ok.emit(record.id)
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
        QApplication.instance() or QApplication(self._argv or ["petgen-app"])
        _set_macos_accessory_policy()
        self._scale_override = scale
        self._passthrough = passthrough
        self._quiet = False
        self._worker: GenerationWorker | None = None

        self.settings = SettingsStore()
        self.registry = PetRegistry()
        self.library = PetLibrary(self.registry)
        self.event_store = AiEventStore()
        self.bus = EventBus()
        self.tray = TrayController()
        self.bubble = BubbleWindow()

        from petgen.speak import VoicePackService

        self.voice = VoicePackService(enabled=bool(self.settings.get("pet.sound_enabled", True)))
        saved_pack = self.settings.get("pet.voice_pack")
        if saved_pack:
            self.voice.set_pack(saved_pack)

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

    # --- lifecycle ----------------------------------------------------------

    def bootstrap(self) -> None:
        self._wire_tray()
        self.bus.event_received.connect(self._on_event)
        self.bus.warnings.connect(lambda msgs: [print(f"petgen: {m}", file=sys.stderr) for m in msgs])
        if self.tray.is_available():
            self.tray.set_characters(self.library.list_pets(), self._selected_id())
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
        return app.exec()

    # --- wiring -------------------------------------------------------------

    def _wire_tray(self) -> None:
        t = self.tray
        t.show_pet_requested.connect(self._toggle_pet_visible)
        t.library_requested.connect(self._open_library)
        t.settings_requested.connect(self._open_settings)
        t.about_requested.connect(self._open_settings)
        t.character_selected.connect(self._select_pet)
        t.quiet_toggled.connect(self._set_quiet)
        t.quick_capture_requested.connect(self._open_quick_capture)
        t.reminder_list_requested.connect(self._open_reminder_list)
        t.pomodoro_requested.connect(self._open_pomodoro)
        t.quit_requested.connect(self._quit)

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
            return
        manifest = load_manifest(record.manifest_path)
        atlas = FrameAtlas.load(manifest.sprite_path, manifest.frame)
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
        window.show()

    def _toggle_pet_visible(self) -> None:
        if self.pet_window is None:
            self._open_library()
            return
        if self.pet_window.isVisible():
            self.pet_window.hide()
            self.tray.set_pet_visible(False)
        else:
            self.pet_window.show()
            self.tray.set_pet_visible(True)

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
        # voice packs map ai_* / task_completed -> their alert/happy/busy/error sounds+lines
        self.voice.react(expression_for_kind(event.kind))

    def _on_pet_clicked(self) -> None:
        if self._quiet:
            return
        if self.pet_window is not None:
            self.pet_window.set_expression("attentive")
        # keep the bubble text in sync with what the voice pack speaks (its "tap" line)
        pack_line = self.voice.pack.line_for("tap")
        if pack_line:
            line = pack_line
        else:
            personality = get_personality(self.settings.get("pet.personality"))
            import random

            line = random.choice(personality.click_lines)
        self.bubble.show_message(line)
        if self.pet_window is not None:
            self.bubble.anchor_to(self.pet_window.frameGeometry())
        self.voice.react("tap")

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
        self._refresh_library()
        self.library_dialog.show()
        self.library_dialog.raise_()

    def _refresh_library(self) -> None:
        if self.library_dialog is not None:
            self.library_dialog.refresh(self.library.list_pets(), self._selected_id())
            scale = float(self.settings.get("pet.scale", 1.5))
            self.library_dialog.set_scale_value(scale)

    def _on_library_scale_changed(self, scale: float) -> None:
        self.settings.set("pet.scale", float(scale))
        if self.pet_window is not None:
            self.pet_window.set_scale(float(scale))

    def _select_pet(self, pet_id: str) -> None:
        self.library.select(self.settings, pet_id)
        self._reload_pet()
        self.tray.set_characters(self.library.list_pets(), pet_id)
        self._refresh_library()

    def _delete_pet(self, pet_id: str) -> None:
        self.library.delete_pet(pet_id)
        if self._selected_id() == pet_id:
            self.settings.set("pet.selected_id", None)
        self._reload_pet()
        self.tray.set_characters(self.library.list_pets(), self._selected_id())
        self._refresh_library()

    def _rename_pet(self, pet_id: str, new_name: str) -> None:
        if not self.library.rename(pet_id, new_name):
            return
        self._reload_pet()
        self.tray.set_characters(self.library.list_pets(), self._selected_id())
        self._refresh_library()

    def _import_dir(self, directory: str) -> None:
        try:
            record = self.library.import_existing_dir(Path(directory))
        except Exception as exc:
            self.bubble.show_message(f"导入失败：{exc}")
            return
        self._select_pet(record.id)
        self.bubble.show_message(f"已导入「{record.display_name}」")

    def _create_pet(self, description: str, image_paths: list) -> None:
        if not description.strip():
            self.bubble.show_message("描述不能为空")
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
        if self.library_dialog is not None:
            self.library_dialog.set_progress("正在生成形象…")
        self._worker.start()

    def _on_gen_progress(self, text: str) -> None:
        if self.library_dialog is not None:
            self.library_dialog.set_progress(text)
        self.bubble.show_message(text, timeout_ms=4000)

    def _on_gen_done(self, pet_id: str) -> None:
        if self.library_dialog is not None:
            self.library_dialog.set_progress("")
        record = self.library.get(pet_id)
        self._select_pet(pet_id)
        if self.pet_window is not None:
            self.pet_window.set_expression("happy")
            self.pet_window.celebrate()
        name = record.display_name if record else "新伙伴"
        self.bubble.show_message(f"新伙伴「{name}」来啦！")

    def _on_gen_failed(self, message: str) -> None:
        if self.library_dialog is not None:
            self.library_dialog.set_progress("")
        if self.pet_window is not None:
            self.pet_window.set_expression("error")
        self.bubble.show_message(f"生成失败：{message}")

    def _open_settings(self) -> None:
        if self.settings_dialog is None:
            self.settings_dialog = SettingsDialog(self.settings)
            self.settings_dialog.applied.connect(self._apply_settings)
        self.settings_dialog.load_values()
        self.settings_dialog.show()
        self.settings_dialog.raise_()

    def _apply_settings(self) -> None:
        # scale lives in the fixed-size window, so any settings save rebuilds the pet
        self._reload_pet()
        self.tray.set_characters(self.library.list_pets(), self._selected_id())
        self.voice.set_pack(self.settings.get("pet.voice_pack") or self.voice.pack.id)
        sound_on = bool(self.settings.get("pet.sound_enabled", True)) and not self._quiet
        self.voice.set_enabled(sound_on)

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

        self.quick_capture_dialog = QuickCaptureDialog(parser=parse_reminder_text)
        self.quick_capture_dialog.quick_created.connect(self._create_reminder)
        self.quick_capture_dialog.show()
        self.quick_capture_dialog.raise_()

    def _create_reminder(self, data: dict) -> None:
        try:
            reminder = self.reminder_scheduler.create(
                data["title"],
                data["trigger_at"],
                recurrence=data.get("recurrence", "none"),
                custom_weekdays=data.get("custom_weekdays") or [],
            )
        except Exception as exc:
            self.bubble.show_message(f"新建提醒失败：{exc}")
            return
        self._refresh_reminder_list()
        if not self._quiet:
            self.bubble.show_message(f"已设置提醒：{reminder.title}")

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
        self.reminder_list_dialog.show()
        self.reminder_list_dialog.raise_()

    def _refresh_reminder_list(self) -> None:
        if self.reminder_list_dialog is not None:
            self.reminder_list_dialog.refresh(self.reminder_store.list_active())

    def _open_reminder_editor(self, reminder=None) -> None:
        from petgen.reminder_editor import ReminderEditorDialog

        self.reminder_editor_dialog = ReminderEditorDialog(reminder)
        self.reminder_editor_dialog.reminder_saved.connect(self._save_reminder)
        self.reminder_editor_dialog.show()
        self.reminder_editor_dialog.raise_()

    def _save_reminder(self, data: dict) -> None:
        from petgen.reminder import Reminder

        try:
            if data.get("id"):
                existing = self.reminder_store.get(data["id"])
                if existing is not None:
                    existing.title = data["title"]
                    existing.trigger_at = data["trigger_at"]
                    existing.recurrence = data.get("recurrence", "none")
                    existing.custom_weekdays = data.get("custom_weekdays") or []
                    self.reminder_store.upsert(existing)
                    self.reminder_store.clear_handled(existing.id)
                    self.reminder_scheduler.reminders_changed.emit()
                else:
                    self._create_reminder(data)
            else:
                self._create_reminder(data)
        except Exception as exc:
            self.bubble.show_message(f"保存提醒失败：{exc}")
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
            self.bubble.show_message("已稍后提醒 ⏰")

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
            ("完成", lambda rid=reminder.id: self._complete_reminder(rid)),
            ("稍后", lambda rid=reminder.id: self._snooze_reminder(rid)),
        ]
        self.bubble.show_message(
            f"⏰ 提醒：{reminder.title}", actions=actions, timeout_ms=0
        )
        if self.pet_window is not None:
            self.bubble.anchor_to(self.pet_window.frameGeometry())

    def _open_pomodoro(self) -> None:
        from petgen.pomodoro import PomodoroWindow

        self.pomodoro_window = PomodoroWindow(self.pomodoro)
        self.pomodoro_window.show()
        self.pomodoro_window.raise_()

    def _on_pomodoro_finished(self, phase: str) -> None:
        from petgen.pomodoro import BREAK

        if self._quiet:
            return
        if self.pet_window is not None:
            self.pet_window.set_expression("happy")
            self.pet_window.celebrate()
        self.voice.react("happy")
        msg = "🍅 专注完成，休息一下吧！" if phase != BREAK else "☕ 休息结束，继续加油！"
        self.bubble.show_message(msg)
        if self.pet_window is not None:
            self.bubble.anchor_to(self.pet_window.frameGeometry())

    def _quit(self) -> None:
        self.bus.stop()
        self._due_timer.stop()
        if self.pet_window is not None:
            self.pet_window.close()
        self.bubble.hide_now()
        QApplication.quit()
