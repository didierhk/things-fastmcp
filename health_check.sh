#!/bin/bash
# Health check for things-ca MCP server.
# Verifies the venv interpreter can import all critical dependencies.
# Exit 0 = healthy, exit 1 = broken.

PYTHON="/Users/didierh/projects/things-ca/.venv/bin/python3"

if [[ ! -x "$PYTHON" ]]; then
  echo "FAIL: venv python not found at $PYTHON" >&2
  exit 1
fi

$PYTHON - <<'EOF'
import sys
try:
    import pydantic
    import mcp
    import things
    from importlib.metadata import version
    print(f"OK: pydantic={pydantic.__version__}, mcp={version('mcp')}, things={things.__version__}")
except ImportError as e:
    print(f"FAIL: {e}", file=sys.stderr)
    sys.exit(1)
EOF
