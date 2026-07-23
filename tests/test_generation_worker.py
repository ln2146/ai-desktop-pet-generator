from __future__ import annotations

import os
import sqlite3
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

pytest.importorskip("PySide6")

from PySide6.QtCore import QThread  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication(["test-gen-worker"])


def _make_source(path: Path) -> None:
    """A tiny but valid 3-row (6/4/5) action sheet on a green screen."""
    from PIL import Image, ImageDraw

    width, height = 960, 600
    image = Image.new("RGBA", (width, height), (0, 255, 0, 255))
    draw = ImageDraw.Draw(image)
    row_tops = [35, 220, 405]
    colors = [(236, 66, 74, 255), (58, 118, 234, 255), (238, 158, 48, 255)]
    for row_index, count in enumerate((6, 4, 5)):
        cell_width = width / count
        top = row_tops[row_index]
        for col in range(count):
            cx = int(cell_width * (col + 0.5))
            draw.ellipse((cx - 34, top + 56, cx + 34, top + 134), fill=colors[row_index])
            draw.ellipse((cx - 24, top + 20, cx + 24, top + 62), fill=colors[row_index])
    image.save(path)


class _FakeConfig:
    model = "fake-model"

    @classmethod
    def from_env(cls, **_overrides):
        return cls()


class _FakeClient:
    def __init__(self, config):
        self._config = config

    def generate(self, prompt, refs):
        return b"\x89PNG\r\n\x1a\n"  # unused: run() writes it then build reads source.png


def _install_stubs(monkeypatch, source_bytes: bytes) -> None:
    """Make the worker's lazy imports produce a real source.png without network."""
    import petgen.openai_image as oi
    import petgen.prompt as pr

    class _Client:
        def __init__(self, config):
            self._config = config

        def generate(self, prompt, refs):
            return source_bytes

    monkeypatch.setattr(oi, "OpenAIImageClient", _Client)
    monkeypatch.setattr(oi, "ImageRequestConfig", _FakeConfig)
    monkeypatch.setattr(pr, "build_pet_prompt", lambda desc: f"prompt:{desc}")


def test_register_from_worker_thread_raises(qapp, tmp_path: Path) -> None:
    """Regression guard: a sqlite3 connection is thread-affine by default.

    The old worker registered the pet from inside the QThread, using the
    main-thread registry connection -> ProgrammingError. This test proves that
    failure mode exists, so the design (register on the main thread) is
    justified. If sqlite ever becomes thread-shareable here, this will fail and
    prompt a rethink.
    """
    from petgen.store import PetRecord, PetRegistry

    registry = PetRegistry(tmp_path / "petgen.sqlite")
    record = PetRecord(
        id="pet-x",
        display_name="x",
        dir_path="/tmp/x",
        sprite_path="/tmp/x/sprite.png",
        manifest_path="/tmp/x/pet.json",
        preview_path=None,
        model="m",
        prompt="p",
        description="d",
        created_at="t",
        updated_at="t",
    )

    error: list[BaseException] = []

    class _Thread(QThread):
        def run(self):
            try:
                registry.register(record)
            except BaseException as exc:  # noqa: BLE001 - capture the thread error
                error.append(exc)

    thread = _Thread()
    thread.start()
    thread.wait(5000)
    assert error, "expected cross-thread register to raise, but it succeeded"
    assert isinstance(error[0], sqlite3.ProgrammingError)


def test_generation_worker_emits_paths_without_touching_db(
    qapp, tmp_path: Path, monkeypatch
) -> None:
    """The worker must build assets and emit paths, never register (no DB)."""
    from petgen.coordinator import GenerationWorker
    from petgen.library import PetLibrary
    from petgen.store import PetRegistry

    source = tmp_path / "src.png"
    _make_source(source)
    _install_stubs(monkeypatch, source.read_bytes())

    registry = PetRegistry(tmp_path / "petgen.sqlite")
    library = PetLibrary(registry, root=tmp_path / "pets")
    work_dir = tmp_path / "work"

    worker = GenerationWorker(
        description="一只猫",
        image_paths=[],
        pet_id="pet-worker",
        work_dir=work_dir,
        config_overrides={},
        library=library,
    )

    result: list[object] = []
    worker.finished_ok.connect(result.append)
    worker.start()
    assert worker.wait(15000), "worker did not finish in time"
    # Cross-thread signal delivery is queued; pump the main loop to dispatch it.
    QApplication.processEvents()

    assert len(result) == 1
    built = result[0]
    assert built.pet_id == "pet-worker"
    assert built.model == "fake-model"
    assert Path(built.paths["manifest"]).exists()
    # Crucially: the worker must NOT have registered (that is the main thread's
    # job now); the registry stays empty until _on_gen_done runs.
    assert registry.count() == 0


def test_on_gen_done_registers_on_main_thread(
    qapp, tmp_path: Path, monkeypatch
) -> None:
    """End-to-end: worker emits -> coordinator registers on the main thread."""
    from petgen.coordinator import AppCoordinator

    monkeypatch.setenv("PETGEN_DATA_DIR", str(tmp_path))
    source = tmp_path / "src.png"
    _make_source(source)

    import petgen.spritesheet as ss

    real_build = ss.build_pet_assets

    def _fake_build(source_image_path, output_dir, **kwargs):
        return real_build(source, output_dir, **kwargs)

    monkeypatch.setattr(ss, "build_pet_assets", _fake_build)
    import petgen.openai_image as oi
    import petgen.prompt as pr

    class _Client:
        def __init__(self, config):
            pass

        def generate(self, prompt, refs):
            return source.read_bytes()

    monkeypatch.setattr(oi, "OpenAIImageClient", _Client)
    monkeypatch.setattr(oi, "ImageRequestConfig", _FakeConfig)
    monkeypatch.setattr(pr, "build_pet_prompt", lambda desc: f"prompt:{desc}")

    coord = AppCoordinator()
    try:
        coord._create_pet("一只猫", [])
        assert coord._worker is not None
        assert coord._worker.wait(15000), "worker did not finish"
        # Process the queued finished_ok signal so _on_gen_done runs on main thread.
        QApplication.processEvents()
        QApplication.processEvents()
        assert coord.registry.count() == 1
        record = coord.registry.list_pets()[0]
        assert record.description == "一只猫"
        assert Path(record.sprite_path).exists()
    finally:
        coord.bus.stop()
