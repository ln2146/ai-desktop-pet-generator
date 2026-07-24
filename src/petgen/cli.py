from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path

from petgen.envfile import load_env_file
from petgen.openai_image import (
    ImageGenerationError,
    ImageRequestConfig,
    OpenAIImageClient,
)
from petgen.openai_text import (
    OpenAITextClient,
    TextGenerationError,
    TextRequestConfig,
    should_enrich,
)
from petgen.prompt import build_pet_prompt
from petgen.spritesheet import SpriteBuildError, build_pet_assets

DEFAULT_IMAGE_ONLY_DESCRIPTION = "把参考图中的形象原样转成可爱桌面宠物，保留原本的颜色、轮廓、标志性配饰和性格特征"

#: Subcommands used as hook targets — they must never exit non-zero for usage
#: errors, because Claude Code interprets exit code 2 from a Stop hook as
#: "block the stop". Usage problems therefore degrade to a silent success.
_HOOK_COMMANDS = ("event", "codex-notify")


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    effective = sys.argv[1:] if argv is None else argv
    try:
        args = parser.parse_args(argv)
    except SystemExit:
        if effective and effective[0] in _HOOK_COMMANDS:
            return 0
        raise
    try:
        if args.command == "generate":
            return _run_generate(args)
        if args.command == "build":
            return _run_build(args)
        if args.command in ("desktop", "run"):
            return _run_desktop(args)
        if args.command == "app":
            return _run_app(args)
        if args.command == "event":
            return _run_event(args)
        if args.command == "codex-notify":
            return _run_codex_notify(args)
        if args.command == "tools":
            return _run_tools(args)
    except (ImageGenerationError, TextGenerationError, SpriteBuildError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    parser.print_help()
    return 2


def _run_generate(args: argparse.Namespace) -> int:
    load_env_file(Path(args.env_file).expanduser().resolve() if args.env_file else None)
    description = _resolve_description(args.prompt, args.prompt_file, reference_images=args.image)
    effective_description = _maybe_enrich_description(
        description,
        args.enrich,
        api_key=args.api_key,
        base_url=args.base_url,
        text_model=args.text_model,
    )
    prompt = build_pet_prompt(effective_description)
    output_dir = Path(args.output).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    source_path = output_dir / "source.png"

    config = ImageRequestConfig.from_env(
        api_key=args.api_key,
        base_url=args.base_url,
        model=args.model,
        size=args.size,
        quality=args.quality,
    )
    client = OpenAIImageClient(config)
    reference_images = [Path(path).expanduser().resolve() for path in args.image]
    image_bytes = client.generate(prompt, reference_images)
    source_path.write_bytes(image_bytes)

    pet_id = args.pet_id or f"pet-{uuid.uuid4().hex[:12]}"
    paths = build_pet_assets(
        source_path,
        output_dir,
        pet_id=pet_id,
        display_name=args.name,
        description=description,
        model=config.model,
        prompt=prompt,
        enriched_description=effective_description if effective_description != description else None,
    )
    if not getattr(args, "no_register", False):
        _register_generated_pet(
            paths,
            pet_id=pet_id,
            model=config.model,
            prompt=prompt,
            description=description,
        )
    _print_result(paths)
    return 0


def _register_generated_pet(
    paths: dict[str, Path],
    *,
    pet_id: str,
    model: str,
    prompt: str,
    description: str,
) -> None:
    """Copy the generated pet into the managed library; never fail the generation."""
    import sqlite3

    try:
        from petgen.library import PetLibrary
        from petgen.store import PetRegistry

        PetLibrary(PetRegistry()).register_build(
            paths, pet_id=pet_id, model=model, prompt=prompt, description=description
        )
    except (sqlite3.Error, OSError, ValueError) as exc:
        print(f"warning: failed to register pet in library ({exc})", file=sys.stderr)


def _run_build(args: argparse.Namespace) -> int:
    source_path = Path(args.source).expanduser().resolve()
    output_dir = Path(args.output).expanduser().resolve()
    description = _resolve_description(args.prompt, args.prompt_file, reference_images=[])
    prompt = build_pet_prompt(description)
    paths = build_pet_assets(
        source_path,
        output_dir,
        pet_id=args.pet_id or f"pet-{uuid.uuid4().hex[:12]}",
        display_name=args.name,
        description=description,
        model=args.model,
        prompt=prompt,
    )
    _print_result(paths)
    return 0


def _resolve_description(
    prompt: str | None,
    prompt_file: str | None,
    *,
    reference_images: list[str],
) -> str:
    if prompt:
        return prompt
    if prompt_file:
        return Path(prompt_file).expanduser().read_text(encoding="utf-8")
    if reference_images:
        return DEFAULT_IMAGE_ONLY_DESCRIPTION
    raise ValueError("provide --prompt or --prompt-file, or pass at least one --image")


def _maybe_enrich_description(
    description: str,
    flag: bool | None,
    *,
    api_key: str | None,
    base_url: str | None,
    text_model: str | None,
) -> str:
    if not should_enrich(description, flag):
        return description
    try:
        config = TextRequestConfig.from_env(api_key=api_key, base_url=base_url, model=text_model)
        return OpenAITextClient(config).enrich(description)
    except (TextGenerationError, OSError) as exc:
        print(
            f"warning: description enrichment failed ({exc}); using the original description",
            file=sys.stderr,
        )
        return description


def _print_result(paths: dict[str, Path]) -> None:
    print("done")
    for key in ["sprite", "manifest", "preview"]:
        print(f"{key}: {paths[key]}")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="petgen",
        description="Generate desktop-pet spritesheets from text and optional reference images.",
    )
    sub = parser.add_subparsers(dest="command")

    generate = sub.add_parser("generate", help="call the image API, then build desktop-pet assets")
    _add_common_args(generate)
    generate.add_argument("--image", action="append", default=[], help="optional reference image; repeatable")
    generate.add_argument("--api-key", default=None, help="defaults to OPENAI_API_KEY")
    generate.add_argument("--base-url", default=None, help="defaults to OPENAI_BASE_URL or OpenAI")
    generate.add_argument("--model", default=None, help="defaults to OPENAI_IMAGE_MODEL or gpt-image-2")
    generate.add_argument("--size", default=None, help="defaults to OPENAI_IMAGE_SIZE or 1536x1024")
    generate.add_argument("--quality", default=None, help="defaults to OPENAI_IMAGE_QUALITY or high")
    generate.add_argument("--env-file", default=None, help="load variables from this .env file")
    generate.add_argument(
        "--enrich",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="enrich short descriptions via a text model; --no-enrich disables; default: auto when < 30 chars",
    )
    generate.add_argument("--text-model", default=None, help="defaults to OPENAI_TEXT_MODEL or gpt-4o-mini")
    generate.add_argument(
        "--no-register",
        action="store_true",
        help="do not copy/register the generated pet into the managed library",
    )

    build = sub.add_parser("build", help="build desktop-pet assets from an existing generated source image")
    _add_common_args(build)
    build.add_argument("--source", required=True, help="existing 3-row green-screen source sheet")
    build.add_argument("--model", default="local-source", help="model name recorded in pet.json")

    desktop = sub.add_parser(
        "desktop",
        aliases=["run"],
        help="run a generated pet as a floating, click-through desktop window",
    )
    desktop.add_argument("path", help="pet output directory (with pet.json) or path to pet.json")
    desktop.add_argument("--scale", type=float, default=1.0, help="multiply frame size for visibility (default 1.0)")
    desktop.add_argument(
        "--no-passthrough",
        action="store_true",
        help="disable transparent-area click-through if setMask misbehaves on your platform",
    )

    app = sub.add_parser(
        "app",
        help="run the resident desktop-pet app (tray + library + settings + event bus)",
    )
    app.add_argument("--scale", type=float, default=None, help="override pet scale for this run")
    app.add_argument(
        "--no-passthrough",
        action="store_true",
        help="disable transparent-area click-through if setMask misbehaves on your platform",
    )
    app.add_argument("--data-dir", default=None, help="override the data directory (also $PETGEN_DATA_DIR)")

    event = sub.add_parser(
        "event",
        help="append one task event to the pet inbox (hook target for AI tools)",
    )
    event.add_argument("kind", help="e.g. ai_thinking | ai_responding | task_completed | ai_error | custom")
    event.add_argument("title", help="short message shown in the pet bubble")
    event.add_argument("detail", nargs="?", default=None, help="optional extra detail")
    event.add_argument("source", nargs="?", default="manual", help="event source, e.g. claude_code | codex")

    codex_notify = sub.add_parser(
        "codex-notify",
        help="Codex notify target: chain the previous notify, then emit a pet event",
    )
    codex_notify.add_argument("notify_args", nargs="*", default=[], help="arguments Codex passes (ignored here)")

    tools = sub.add_parser("tools", help="inspect / wire / unwire AI tool notification hooks")
    tools_sub = tools.add_subparsers(dest="tools_action")
    for action in ("status", "connect", "disconnect"):
        action_parser = tools_sub.add_parser(action, help=f"{action} the notification hook")
        action_parser.add_argument("tool", choices=["claude", "codex", "antigravity", "all"])

    return parser


def _run_desktop(args: argparse.Namespace) -> int:
    try:
        from petgen.desktop_window import run
    except ImportError:
        print(
            'error: desktop runtime needs PySide6; install with: pip install -e ".[desktop]"',
            file=sys.stderr,
        )
        return 1
    return run(args.path, scale=args.scale, passthrough=not args.no_passthrough)


def _run_app(args: argparse.Namespace) -> int:
    if args.data_dir:
        import os

        os.environ["PETGEN_DATA_DIR"] = str(Path(args.data_dir).expanduser().resolve())
    try:
        from petgen.coordinator import AppCoordinator
    except ImportError:
        print(
            'error: desktop runtime needs PySide6; install with: pip install -e ".[desktop]"',
            file=sys.stderr,
        )
        return 1
    coordinator = AppCoordinator(
        scale=args.scale, passthrough=not args.no_passthrough
    )
    return coordinator.run()


def _run_event(args: argparse.Namespace) -> int:
    from petgen.integrations import append_event

    try:
        append_event(args.kind, args.title, args.detail, args.source)
    except Exception as exc:  # noqa: BLE001 — hook target: never fail the calling AI tool
        print(f"warning: failed to append task event: {exc}", file=sys.stderr)
    return 0


def _run_codex_notify(args: argparse.Namespace) -> int:
    """Codex `notify` target: chain the previous notify, then emit a pet event.

    Codex passes the notify array elements as argv and appends one JSON payload
    argument ({"type": "agent-turn-complete", ...}); older configs may instead
    carry a literal type string — both shapes are tolerated.
    """
    from petgen import integrations

    extra = list(args.notify_args)
    event_type: object = None
    for arg in extra:
        try:
            payload = json.loads(arg)
        except ValueError:
            continue
        if isinstance(payload, dict):
            event_type = payload.get("type")
            break
    if event_type is None:
        for arg in extra:  # legacy fallback: first non-JSON arg is the type string
            try:
                json.loads(arg)
            except ValueError:
                event_type = arg
                break
    done_types = (None, "", "agent-turn-complete", "turn-ended", "completed")
    kind = "task_completed" if event_type in done_types else "ai_responding"
    title = "Codex 任务完成" if kind == "task_completed" else "Codex 进行中"

    try:
        integrations.chain_original_notify(extra)
    except Exception as exc:  # best-effort chaining must never break the hook
        print(f"warning: notify chain failed: {exc}", file=sys.stderr)
    try:
        integrations.append_event(kind, title, None, "codex")
    except Exception as exc:  # noqa: BLE001 — hook target: never fail the calling tool
        print(f"warning: failed to append task event: {exc}", file=sys.stderr)
    return 0


def _run_tools(args: argparse.Namespace) -> int:
    from petgen import integrations

    if not getattr(args, "tools_action", None):
        print("usage: petgen tools {status|connect|disconnect} {claude|codex|antigravity|all}", file=sys.stderr)
        return 2
    tools = integrations.TOOLS if args.tool == "all" else (args.tool,)
    exit_code = 0
    for tool in tools:
        try:
            if args.tools_action == "status":
                state = integrations.status(tool)
            elif args.tools_action == "connect":
                state = integrations.connect(tool)
            else:
                state = integrations.disconnect(tool)
        except integrations.IntegrationsError as exc:
            print(f"{integrations.TOOL_LABELS[tool]}: error: {exc}", file=sys.stderr)
            exit_code = 1
            continue
        line = f"{integrations.TOOL_LABELS[tool]}: {state.status.value}"
        if state.detail:
            line += f" ({state.detail})"
        print(line)
    return exit_code


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--prompt", default=None, help="pet description")
    parser.add_argument("--prompt-file", default=None, help="read pet description from a text file")
    parser.add_argument("--output", default="outputs/pet", help="output directory")
    parser.add_argument("--name", default="自定义桌宠", help="display name written to pet.json")
    parser.add_argument("--pet-id", default=None, help="stable pet id; defaults to a generated id")


if __name__ == "__main__":
    raise SystemExit(main())
