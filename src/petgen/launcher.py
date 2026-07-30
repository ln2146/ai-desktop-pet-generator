"""Bare entry point for the bundled desktop app (no argparse).

The CLI's ``petgen app`` subcommand is the normal launch path, but double-
clicking a ``.app`` bundle passes no arguments — ``petgen.cli.main()`` would
then just print argparse help and exit. This launcher goes straight to the
resident pet app, which is what a bundled app should do.

It also calls ``multiprocessing.freeze_support()`` defensively: the app does
not use multiprocessing today, but frozen PyInstaller apps must call it before
anything else if they ever spawn subprocesses of themselves, so it is harmless
to keep here as a forward-looking safety net.
"""
from __future__ import annotations

import sys


def main() -> int:
    # PyInstaller frozen apps that ever fork need this before other imports.
    try:
        import multiprocessing

        multiprocessing.freeze_support()
    except Exception:  # noqa: BLE001 - never block startup on this
        pass

    # When frozen, the real app argv starts at sys.argv[0] (the executable).
    # When run from source for testing, mimic the CLI's app argv.
    argv = list(sys.argv[1:]) if not getattr(sys, "frozen", False) else []
    from petgen.coordinator import AppCoordinator

    return AppCoordinator(argv=argv).run()


if __name__ == "__main__":
    raise SystemExit(main())
