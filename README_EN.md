# AI Desktop Pet Generator

<p align="center">
  <a href="README.md">Chinese</a> · <a href="README_EN.md"><b>English</b></a>
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green.svg" alt="MIT License"></a>
  <img src="https://img.shields.io/badge/python-%3E%3D3.10-blue.svg" alt="Python >= 3.10">
  <img src="https://img.shields.io/badge/pytest%20%2B%20ruff-passing-brightgreen.svg" alt="pytest + ruff">
  <img src="https://img.shields.io/badge/macOS%20%7C%20Linux%20%7C%20Windows-supported-lightgrey.svg" alt="macOS / Linux / Windows">
</p>

Turn a sentence, or a reference image, into a polished desktop pet that lives in your tray and on your desktop.

The project covers the full pipeline: AI image generation, local green-screen keying, frame slicing, standard `8 x 9` spritesheet packaging, and a tray-resident desktop app. It can also connect to Claude Code, Codex, and Antigravity so AI coding events become pet expressions, bubbles, and sound feedback.

<p align="center">
  <table align="center">
    <tr>
      <td align="center"><img src="docs/images/hero.png" alt="Grey-white cat hero" width="340"></td>
      <td align="center"><img src="docs/images/idle.gif" alt="Grey-white cat idle animation" width="180"></td>
    </tr>
    <tr>
      <td align="center"><sub><b>Grey-white cat</b>: generated from a sentence or reference image</sub></td>
      <td align="center"><sub>idle breathing animation</sub></td>
    </tr>
  </table>
</p>

## Featured Pets

Each pet is generated from one sentence, shares a consistent style, and can be used directly in the desktop app.

<p align="center">
  <table align="center">
    <tr>
      <td align="center"><img src="docs/images/pet-cat.png" alt="Grey-white cat" width="120"></td>
      <td align="center"><img src="docs/images/pet-redpanda.png" alt="Panda buddy" width="120"></td>
      <td align="center"><img src="docs/images/pet-fox.png" alt="Arctic fox" width="120"></td>
      <td align="center"><img src="docs/images/pet-gingercat.png" alt="Ginger kitten" width="120"></td>
      <td align="center"><img src="docs/images/pet-dragon.png" alt="Mint baby dragon" width="120"></td>
      <td align="center"><img src="docs/images/pet-corgi.png" alt="Corgi pup" width="120"></td>
    </tr>
    <tr>
      <td align="center"><sub><b>Grey-white Cat</b></sub></td>
      <td align="center"><sub><b>Panda Buddy</b></sub></td>
      <td align="center"><sub><b>Arctic Fox</b></sub></td>
      <td align="center"><sub><b>Ginger Kitten</b></sub></td>
      <td align="center"><sub><b>Mint Baby Dragon</b></sub></td>
      <td align="center"><sub><b>Corgi Pup</b></sub></td>
    </tr>
  </table>
</p>

## Features

| Feature | Description |
|---------|-------------|
| Text or reference-image pet generation | Generate a pet from a short prompt, or keep colors, silhouette, and signature accessories from a reference image |
| Local post-processing | Green-screen keying, connected-component frame slicing, normalization, and standard spritesheet packaging |
| Tray-resident desktop app | System tray, floating pet, pet center, settings, speech bubbles, and celebration effects |
| AI coding integration | Connect to Claude Code, Codex, and Antigravity so the pet reacts when AI coding tasks complete |
| Voice, reminders, and pomodoro | TTS speech, synthesized sound effects, natural-language reminders, and a 25/5 focus timer |

## Quick Start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[desktop]"

cp .env.example .env
# Then fill OPENAI_API_KEY in .env
```

Generate a pet:

```bash
petgen generate \
  --prompt "a chubby capybara programmer wearing tiny headphones, gentle and smart" \
  --name "Capybara Coder" \
  --output outputs/capybara-coder
```

Launch the desktop app:

```bash
petgen app
```

## Configuration

The project automatically loads `.env` from the current directory. The default provider is OpenAI:

```bash
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_IMAGE_MODEL=gpt-image-2
OPENAI_TEXT_MODEL=gpt-4o-mini
```

OpenAI-compatible providers are also supported:

```bash
OPENAI_BASE_URL=https://your-compatible-endpoint/v1
OPENAI_API_KEY=your-provider-key
OPENAI_IMAGE_MODEL=gpt-image-2
OPENAI_TEXT_MODEL=your-chat-model
```

## Common Commands

Generate from text:

```bash
petgen generate \
  --prompt "a chubby capybara programmer wearing tiny headphones, gentle and smart" \
  --name "Capybara Coder" \
  --output outputs/capybara-coder
```

Generate from a reference image:

```bash
petgen generate \
  --image /path/to/reference.png \
  --prompt "keep the colors and signature accessories, then turn it into a cute desktop pet" \
  --output outputs/from-reference
```

Build assets from an existing source sheet:

```bash
petgen build --source /path/to/source.png --name "Local Pet" --output outputs/local-pet
```

Run one existing pet directly:

```bash
petgen desktop outputs/capybara-coder --scale 1.5
```

## Generation Output

The output directory contains:

- `source.png`: raw model output, written by `generate` only.
- `sprite.png`: standard `8 x 9` pet spritesheet with transparency.
- `pet.json`: animation manifest and generation metadata.
- `preview.png`: first-frame preview.

<p align="center">
  <img src="docs/images/spritesheet.png" alt="Standard 8x9 pet spritesheet" width="430">
  <br><sub>Packed <code>8 x 9</code> spritesheet</sub>
</p>

## Desktop App

```bash
petgen app
```

`petgen app` starts the tray icon, floating pet, pet center, settings panel, and AI event bus. Runtime data is stored in `~/.petgen/` by default, and can be changed with `$PETGEN_DATA_DIR` or `--data-dir`.

Common entry points:

- Pet center: browse, select, preview, rename, delete, import, or create pets.
- Settings center: configure API credentials, models, animation, sound, voice packs, interaction styles, and tool integrations.
- Quick reminders: supports natural-language entries such as "tomorrow 3pm meeting" or "in 1 hour take medicine".
- Pomodoro timer: includes a 25/5 focus timer with pet reminders.

## AI Tool Integration

The pet can read AI coding events and switch expressions accordingly. In the app:

```text
petgen app -> Settings Center -> Tool Integration
```

Equivalent CLI commands:

```bash
petgen tools status all
petgen tools connect all
petgen tools disconnect all
petgen event KIND TITLE [DETAIL] [SOURCE]
```

See [docs/integrations.md](docs/integrations.md) for hook details, migration notes, and the manual event protocol.

## Source Image Spec

For stable local slicing, generated source images should follow these constraints:

- One image with a pure `#00FF00` green-screen background.
- Three action rows: row 1 has 6 idle frames, row 2 has 4 attentive frames, row 3 has 5 happy frames.
- Each frame should show the full body, centered, with visible green gaps between frames.
- The character body should not be mostly green, because same-color foreground and background cannot be separated reliably with color keying alone.

## Development

```bash
pip install -e ".[dev,desktop]"
pytest
ruff check .
python -m pip wheel . --no-deps -w /tmp/petgen-wheel
```

## Documentation

- [Development Guide](docs/development.md): setup, tests, linting, wheel builds, and release checks.
- [Tool Integrations](docs/integrations.md): Claude Code, Codex, and Antigravity integration notes.
- [Architecture](docs/architecture.md): generation pipeline, runtime components, storage, and error boundaries.
- [Troubleshooting](docs/troubleshooting.md): API, PySide6, sound, reminders, and slicing issues.

## Tech Stack

`Python >= 3.10` · `PySide6` · `Pillow` · `numpy` · `requests` · `edge-tts` · `pytest` · `ruff`

## Contributing

Issues and pull requests are welcome. Before submitting changes, run:

```bash
pytest
ruff check .
```

## License

[MIT](LICENSE)
