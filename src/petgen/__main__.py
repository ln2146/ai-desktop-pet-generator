"""Enable ``python -m petgen`` (fallback hook entry when ``petgen`` is off PATH)."""
from petgen.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
