from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from petgen.cli import (
    DEFAULT_IMAGE_ONLY_DESCRIPTION,
    _build_parser,
    _maybe_enrich_description,
    _register_generated_pet,
    _resolve_description,
    _run_codex_notify,
    _run_event,
    main,
)
from petgen.eventbus import parse_event_line
from petgen.openai_text import TextGenerationError


def test_resolve_description_prefers_prompt(tmp_path: Path) -> None:
    prompt_file = tmp_path / "prompt.txt"
    prompt_file.write_text("file text", encoding="utf-8")

    result = _resolve_description(
        "direct prompt", str(prompt_file), reference_images=["ref.png"]
    )

    assert result == "direct prompt"


def test_resolve_description_reads_prompt_file(tmp_path: Path) -> None:
    prompt_file = tmp_path / "prompt.txt"
    prompt_file.write_text("file text", encoding="utf-8")

    result = _resolve_description(None, str(prompt_file), reference_images=[])

    assert result == "file text"


def test_resolve_description_falls_back_to_default_for_images_only() -> None:
    result = _resolve_description(None, None, reference_images=["ref.png"])

    assert result is DEFAULT_IMAGE_ONLY_DESCRIPTION


def test_resolve_description_requires_prompt_or_image() -> None:
    try:
        _resolve_description(None, None, reference_images=[])
    except ValueError as exc:
        message = str(exc)
        assert "--prompt" in message
        assert "--image" in message
    else:
        raise AssertionError("expected ValueError")


def test_parser_enrich_flag_is_tri_state() -> None:
    parser = _build_parser()

    on = parser.parse_args(["generate", "--enrich", "--prompt", "p"])
    off = parser.parse_args(["generate", "--no-enrich", "--prompt", "p"])
    auto = parser.parse_args(["generate", "--prompt", "p"])

    assert on.enrich is True
    assert off.enrich is False
    assert auto.enrich is None


def test_parser_text_model_flag() -> None:
    parser = _build_parser()
    args = parser.parse_args(["generate", "--prompt", "p", "--text-model", "custom-model"])
    assert args.text_model == "custom-model"


class _RaisingTextClient:
    def __init__(self, config) -> None:
        raise TextGenerationError("boom")


class _ReturningTextClient:
    def __init__(self, config) -> None:
        pass

    def enrich(self, description: str) -> str:
        return "enriched"


def test_enrichment_failure_falls_back_to_original(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("petgen.cli.OpenAITextClient", _RaisingTextClient)

    result = _maybe_enrich_description(
        "一只猫", None, api_key="test", base_url=None, text_model=None
    )

    assert result == "一只猫"
    stderr = capsys.readouterr().err
    assert "warning: description enrichment failed" in stderr
    assert "boom" in stderr


def test_enrichment_skipped_when_flag_false(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("petgen.cli.OpenAITextClient", _RaisingTextClient)

    result = _maybe_enrich_description(
        "一只猫", False, api_key=None, base_url=None, text_model=None
    )

    assert result == "一只猫"


def test_enrichment_runs_when_flag_true(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("petgen.cli.OpenAITextClient", _ReturningTextClient)

    result = _maybe_enrich_description(
        "一只详细描述了很多外观性格细节的长长长猫",
        True,
        api_key="test",
        base_url=None,
        text_model=None,
    )

    assert result == "enriched"


def test_enrichment_auto_triggers_for_short_description(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("petgen.cli.OpenAITextClient", _ReturningTextClient)

    result = _maybe_enrich_description(
        "一只猫", None, api_key="test", base_url=None, text_model=None
    )

    assert result == "enriched"


def test_parser_no_register_flag() -> None:
    parser = _build_parser()
    assert parser.parse_args(["generate", "--prompt", "p"]).no_register is False
    assert parser.parse_args(["generate", "--prompt", "p", "--no-register"]).no_register is True


def test_register_generated_pet_copies_into_library(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PETGEN_DATA_DIR", str(tmp_path / "data"))
    from petgen.spritesheet import build_pet_assets
    from petgen.store import PetRegistry

    out = tmp_path / "out"
    out.mkdir()
    sprite = _make_source_sheet()
    sprite.save(out / "source.png")
    paths = build_pet_assets(
        out / "source.png",
        out,
        pet_id="pet-reg",
        display_name="登记测试",
        description="d",
        model="m",
        prompt="p",
    )

    _register_generated_pet(paths, pet_id="pet-reg", model="m", prompt="p", description="d")

    assert PetRegistry().count() == 1
    assert PetRegistry().get("pet-reg") is not None


def test_register_generated_pet_failure_only_warns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import sqlite3

    def boom(*a, **k):
        raise sqlite3.OperationalError("disk full")

    monkeypatch.setattr("petgen.store.PetRegistry.register", boom)

    _register_generated_pet(
        {"sprite": tmp_path, "manifest": tmp_path, "preview": tmp_path},
        pet_id="x",
        model="m",
        prompt="p",
        description="d",
    )

    assert "warning: failed to register pet in library" in capsys.readouterr().err


def _make_source_sheet():
    from PIL import Image, ImageDraw

    width, height = 960, 600
    image = Image.new("RGBA", (width, height), (0, 255, 0, 255))
    draw = ImageDraw.Draw(image)
    for row_index, count in enumerate((6, 4, 5)):
        top = [35, 220, 405][row_index]
        cell_width = width / count
        for col in range(count):
            cx = int(cell_width * (col + 0.5))
            draw.ellipse((cx - 30, top + 30, cx + 30, top + 120), fill=(200, 20, 20, 255))
    return image


# --- event / codex-notify / tools subcommands ---------------------------------


def test_parser_event_defaults() -> None:
    args = _build_parser().parse_args(["event", "task_completed", "完成啦"])
    assert args.command == "event"
    assert args.kind == "task_completed"
    assert args.title == "完成啦"
    assert args.detail is None
    assert args.source == "manual"


def test_run_event_appends_parseable_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PETGEN_DATA_DIR", str(tmp_path))
    args = _build_parser().parse_args(["event", "task_completed", "完成啦", "一些细节", "claude_code"])
    assert _run_event(args) == 0

    lines = (tmp_path / "task-events.jsonl").read_text(encoding="utf-8").splitlines()
    event = parse_event_line(lines[-1])
    assert event is not None
    assert event.kind == "task_completed"
    assert event.title == "完成啦"
    assert event.detail == "一些细节"
    assert event.source == "claude_code"
    assert "完成啦" in lines[-1]  # ensure_ascii=False keeps Chinese verbatim


def test_run_event_empty_detail_becomes_null(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PETGEN_DATA_DIR", str(tmp_path))
    args = _build_parser().parse_args(["event", "task_completed", "x", ""])
    _run_event(args)
    event = parse_event_line((tmp_path / "task-events.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert event is not None and event.detail is None


def test_run_event_write_failure_returns_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    blocker = tmp_path / "blocker"
    blocker.write_text("x", encoding="utf-8")
    monkeypatch.setenv("PETGEN_DATA_DIR", str(blocker / "sub"))  # mkdir under a file fails
    args = _build_parser().parse_args(["event", "task_completed", "x"])
    assert _run_event(args) == 0
    assert "warning" in capsys.readouterr().err


def test_main_event_missing_args_returns_zero_not_exit2() -> None:
    # Claude Code treats exit code 2 from a Stop hook as "block the stop".
    assert main(["event"]) == 0


def _last_event(tmp_path: Path):
    return parse_event_line((tmp_path / "task-events.jsonl").read_text(encoding="utf-8").splitlines()[-1])


def test_run_codex_notify_json_arg(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PETGEN_DATA_DIR", str(tmp_path))
    chained: list[list[str]] = []
    monkeypatch.setattr(
        "petgen.integrations.chain_original_notify", lambda args, **kw: chained.append(list(args))
    )
    payload = '{"type": "agent-turn-complete"}'
    args = _build_parser().parse_args(["codex-notify", payload])
    assert _run_codex_notify(args) == 0
    event = _last_event(tmp_path)
    assert event is not None
    assert event.kind == "task_completed"
    assert event.source == "codex"
    assert chained == [[payload]]  # Codex args passed through to the original notify


def test_run_codex_notify_legacy_string(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PETGEN_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("petgen.integrations.chain_original_notify", lambda *a, **k: None)
    args = _build_parser().parse_args(["codex-notify", "turn-ended"])
    _run_codex_notify(args)
    assert _last_event(tmp_path).kind == "task_completed"


def test_run_codex_notify_unknown_type_maps_responding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PETGEN_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("petgen.integrations.chain_original_notify", lambda *a, **k: None)
    args = _build_parser().parse_args(["codex-notify", '{"type": "permission-request"}'])
    _run_codex_notify(args)
    event = _last_event(tmp_path)
    assert event.kind == "ai_responding"
    assert event.title == "Codex 进行中"


def test_tools_status_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    (home / ".codex").mkdir()
    monkeypatch.setattr("petgen.integrations._home", lambda value: home)
    monkeypatch.setattr("petgen.integrations.ANTIGRAVITY_DETECT_PATHS", ("~/.gemini",))
    assert main(["tools", "status", "all"]) == 0
    out = capsys.readouterr().out
    assert "Claude Code: not_connected" in out
    assert "Codex: not_connected" in out
    assert "Antigravity: not_detected" in out


def test_module_entry_event_end_to_end(tmp_path: Path) -> None:
    src_dir = Path(__file__).resolve().parents[1] / "src"
    env = {**os.environ, "PYTHONPATH": str(src_dir), "PETGEN_DATA_DIR": str(tmp_path)}
    result = subprocess.run(
        [sys.executable, "-m", "petgen", "event", "ai_thinking", "思考中"],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    event = _last_event(tmp_path)
    assert event is not None and event.kind == "ai_thinking" and event.title == "思考中"
