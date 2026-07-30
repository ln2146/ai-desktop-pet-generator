# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the PetGen desktop app (macOS + Windows).

Build:  pyinstaller packaging/petgen.spec   (run from the repo root)
Output:
  macOS:   dist/PetGen.app   (app bundle, then hdiutil -> .dmg)
  Windows: dist/PetGen/      (onedir; zip it for distribution)

Key decisions (see the packaging exploration notes for the why):

* Entry point is petgen.launcher (NOT petgen.cli) — double-clicking a .app/.exe
  bundle passes no argv, so cli.main() would just print argparse help and
  quit. The launcher goes straight to AppCoordinator.run().

* datas ships src/petgen/resources into petgen/resources inside the bundle.
  theme.py and interaction_style.py resolve assets via Path(__file__).parent
  / "resources", which only works if the resources tree keeps its petgen/
  prefix relative to the frozen modules. Missing it = no check.svg icons and
  SFX re-synthesized at runtime (graceful but wasteful).

* hiddenimports cover Qt modules + edge_tts that are imported inside try/except
  blocks, so PyInstaller's static analysis misses them. collect_submodules
  pulls in the whole petgen package (heavy use of deferred in-function imports)
  and aiohttp (edge_tts dependency with C extensions).

Platform split at the end:
* macOS -> BUNDLE into PetGen.app with LSUIElement=true (tray-resident, no
  Dock icon, more reliable than the runtime ctypes policy flip).
* Windows -> onedir COLLECT output (dist/PetGen/). QSystemTrayIcon already
  makes it tray-resident; setQuitOnLastWindowClosed(False) keeps it alive.

No code signing here — see packaging/README for the trust notes.
"""

import sys
from PyInstaller.utils.hooks import collect_submodules

IS_MAC = sys.platform == "darwin"
IS_WIN = sys.platform.startswith("win")

# Resolve everything against the repo root (the spec lives in packaging/).
import os
ROOT = os.path.abspath(os.path.join(SPECPATH, os.pardir))
def _p(*parts):
    return os.path.join(ROOT, *parts)

block_cipher = None

datas = [
    (_p("src", "petgen", "resources"), "petgen/resources"),
]

hiddenimports = [
    "PySide6.QtMultimedia",
    "PySide6.QtTextToSpeech",
    "edge_tts",
] + collect_submodules("petgen") + collect_submodules("aiohttp")


a = Analysis(
    [_p("src", "petgen", "launcher.py")],
    pathex=[_p("src")],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Trim test/dev tooling that has no place in a shipped GUI app.
        "pytest",
        "ruff",
        "tests",
    ],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# Windows-only idle-time helper imports ctypes.windll; on macOS it is dead
# code guarded by sys.platform. No action needed, but note it here.
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="PetGen",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # --windowed: no console/Terminal window
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # EXE-level icon (used on Windows; macOS app icon is set in BUNDLE).
    icon=_p("packaging", "PetGen.ico") if IS_WIN else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="PetGen",
)

if IS_MAC:
    app = BUNDLE(
        coll,
        name="PetGen.app",
        icon=_p("packaging", "PetGen.icns"),  # grey-white cat icon
        bundle_identifier="com.petgen.app",
        info_plist={
            "CFBundleName": "PetGen",
            "CFBundleDisplayName": "PetGen 桌宠",
            "CFBundleShortVersionString": "0.1.0",
            "CFBundleExecutable": "PetGen",
            # Accessory app: no Dock icon, no app menu — this is a tray-resident pet.
            "LSUIElement": True,
            "LSMinimumSystemVersion": "11.0",
            # Retina rendering for crisp spritesheet frames.
            "NSHighResolutionCapable": True,
            "NSPrincipalClass": "NSApplication",
        },
    )
# Windows: the COLLECT above already produced dist/PetGen/ (onedir). The CI
# workflow zips it into an artifact. PetGen.exe inside uses PetGen.ico.
