from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from petgen.spritesheet import DEFAULT_ANIMATIONS


class ManifestError(ValueError):
    """Raised for a missing or invalid pet manifest / sprite sheet."""


@dataclass(frozen=True)
class FrameSpec:
    width: int
    height: int
    columns: int
    rows: int

    @property
    def frame_count(self) -> int:
        return self.columns * self.rows


@dataclass(frozen=True)
class AnimationSpec:
    frames: tuple[int, ...]
    fps: float
    loop: bool
    fallback: str


@dataclass(frozen=True)
class PetManifest:
    id: str
    display_name: str
    description: str
    sprite_path: Path
    frame: FrameSpec
    animations: dict[str, AnimationSpec]
    manifest_dir: Path

    def initial_animation(self) -> str:
        if not self.animations:
            raise ManifestError("manifest defines no animations")
        if "idle" in self.animations:
            return "idle"
        return next(iter(self.animations))


def load_manifest(path: str | Path) -> PetManifest:
    """Load a pet manifest from a directory (containing ``pet.json``) or a file."""
    base = Path(path).expanduser().resolve()
    if base.is_dir():
        manifest_path = base / "pet.json"
        manifest_dir = base
    elif base.is_file():
        manifest_path = base
        manifest_dir = base.parent
    else:
        raise ManifestError(f"no pet manifest at {path}")

    if not manifest_path.is_file():
        raise ManifestError(f"{manifest_path} not found")

    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ManifestError(f"failed to read {manifest_path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise ManifestError(f"{manifest_path} is not a JSON object")

    for key in ("spritesheetPath", "frame"):
        if key not in raw:
            raise ManifestError(f"pet.json missing required key '{key}'")

    frame = _coerce_frame(raw["frame"])

    sprite_path = (manifest_dir / str(raw["spritesheetPath"])).resolve()
    if not sprite_path.is_file():
        raise ManifestError(f"sprite sheet not found: {sprite_path}")

    animations = _coerce_animations(raw.get("animations"), frame)

    return PetManifest(
        id=str(raw.get("id", "")),
        display_name=str(raw.get("displayName", "")),
        description=str(raw.get("description", "")),
        sprite_path=sprite_path,
        frame=frame,
        animations=animations,
        manifest_dir=manifest_dir,
    )


def _coerce_frame(raw: object) -> FrameSpec:
    if not isinstance(raw, dict):
        raise ManifestError("pet.json 'frame' must be an object")
    try:
        return FrameSpec(
            width=int(raw["width"]),
            height=int(raw["height"]),
            columns=int(raw["columns"]),
            rows=int(raw["rows"]),
        )
    except KeyError as exc:
        raise ManifestError(f"pet.json 'frame' missing sub-key {exc.args[0]!r}") from exc
    except (TypeError, ValueError) as exc:
        raise ManifestError(f"pet.json 'frame' has invalid numbers: {exc}") from exc


def _coerce_animations(
    raw: object, frame: FrameSpec
) -> dict[str, AnimationSpec]:
    source = raw if isinstance(raw, dict) and raw else DEFAULT_ANIMATIONS
    animations: dict[str, AnimationSpec] = {}
    for name, entry in source.items():
        if not isinstance(entry, dict):
            raise ManifestError(f"animation '{name}' must be an object")
        try:
            frames = tuple(int(index) for index in entry["frames"])
        except KeyError as exc:
            raise ManifestError(f"animation '{name}' missing 'frames'") from exc
        except (TypeError, ValueError) as exc:
            raise ManifestError(f"animation '{name}' has invalid frame indices: {exc}") from exc
        for index in frames:
            if index < 0 or index >= frame.frame_count:
                raise ManifestError(
                    f"animation '{name}' references out-of-range frame {index}"
                )
        animations[name] = AnimationSpec(
            frames=frames,
            fps=float(entry.get("fps", 1.0)),
            loop=bool(entry.get("loop", True)),
            fallback=str(entry.get("fallback", "idle")),
        )
    return animations


class FrameAtlas:
    """Crops individual RGBA frames out of a generated spritesheet atlas."""

    def __init__(self, image: Image.Image, spec: FrameSpec) -> None:
        self._image = image.convert("RGBA")
        self._spec = spec

    @classmethod
    def load(cls, sprite_path: Path, spec: FrameSpec) -> "FrameAtlas":
        image = Image.open(sprite_path)
        expected = (spec.width * spec.columns, spec.height * spec.rows)
        if image.size != expected:
            raise ManifestError(
                f"sprite is {image.width}x{image.height}, expected {expected[0]}x{expected[1]}"
            )
        return cls(image, spec)

    @property
    def count(self) -> int:
        return self._spec.frame_count

    def crop(self, global_index: int) -> Image.Image:
        spec = self._spec
        if global_index < 0 or global_index >= spec.frame_count:
            raise ManifestError(f"frame index {global_index} out of range")
        row = global_index // spec.columns
        col = global_index % spec.columns
        box = (
            col * spec.width,
            row * spec.height,
            (col + 1) * spec.width,
            (row + 1) * spec.height,
        )
        return self._image.crop(box)
