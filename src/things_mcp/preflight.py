"""Startup health checks — fail loud, not silent.

This module would have caught the Mar 16 2026 outage where pydantic-core
drifted to an incompatible version in the shared global Python environment.
Now wired as the first call in things_fast_server.py before the server starts.
"""
import sys
import subprocess


def check() -> None:
    """Run before server starts. Raises SystemExit on failure."""
    errors = []
    warnings = []

    # 1. Pydantic core version compatibility — catches the exact Mar 16 failure mode
    try:
        import pydantic
        import pydantic_core  # noqa: F401
        pydantic.version._ensure_pydantic_core_version()
    except Exception as e:
        errors.append(f"Pydantic version mismatch: {e}")

    # 2. things.py library
    try:
        import things  # noqa: F401
    except ImportError as e:
        errors.append(f"things.py not installed: {e}")

    # 3. MCP SDK
    try:
        import mcp  # noqa: F401
    except ImportError as e:
        errors.append(f"MCP SDK not installed: {e}")

    # 4. Things app reachable (macOS only) — warn, don't block startup
    things_running = False
    try:
        result = subprocess.run(
            ["osascript", "-e", 'tell application "System Events" to (name of processes) contains "Things3"'],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        things_running = result.stdout.strip().lower() == "true"
        if not things_running:
            warnings.append("Things 3 app is not running (will attempt launch when needed)")
    except Exception as e:
        warnings.append(f"Cannot check Things app status: {e}")

    if errors:
        print("PREFLIGHT CHECK FAILED:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        sys.exit(1)

    for warn in warnings:
        print(f"  ⚠ {warn}", file=sys.stderr)

    print("Preflight checks passed", file=sys.stderr)
