"""Fail fast if the interpreter is not a supported FloodGuard environment."""

import sys

MIN_VERSION = (3, 11)


def main() -> int:
    if sys.version_info < MIN_VERSION:
        print(f"Python {sys.version.split()[0]} found; >= 3.11 required.", file=sys.stderr)
        return 1
    if sys.prefix == sys.base_prefix:
        print("Not running inside a virtual environment (.venv).", file=sys.stderr)
        return 1
    print(f"OK: Python {sys.version.split()[0]} in {sys.prefix}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
