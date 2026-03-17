# things-ca (Things 3 MCP Server)

## Quick Start

```bash
make setup   # create venv + install deps
make run     # preflight check + start server
make test    # pytest
```

## Architecture

```
things_fast_server.py          ← entry point
  → preflight.check()          ← import + dep + Things app health check
  → run_things_mcp_server()    ← starts FastMCP server

src/things_mcp/
  fast_server.py               ← ALL tool definitions (FastMCP decorators)
  preflight.py                 ← startup health checks (fail loud)
  applescript_bridge.py        ← write ops: add/update todo/project
  url_scheme.py                ← show/search URL construction + execute_url()
  utils.py                     ← CircuitBreaker, RateLimiter, DLQ, reliable_tool
  cache.py                     ← @cached decorator, TTL-based cache
  formatters.py                ← format_todo(), format_project() etc.
  config.py                    ← auth token retrieval
```

**Write path:** `applescript_bridge` → AppleScript → Things (verified: returns UUID)

**Show/Search path:** `url_scheme.execute_url(show(...))` → `webbrowser.open()` → Things

**Reliability:** `@reliable_tool` decorator on all write tools — rate limit + circuit breaker + DLQ

## Key Constraints

- **Python venv only** — always `.venv/bin/python3`, never global pyenv or system Python
- **Things 3 has no real API** — URL scheme + AppleScript only
- **Write ops use AppleScript bridge** — verified via returned UUID, not fire-and-forget
- **MCP config must point to `.venv/bin/python3`**
  - Config: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **After any `pip install`, run `make preflight`** to catch dependency drift before next session

## Dependency Management

```bash
make freeze          # update requirements.txt from current venv
pip install -r requirements.txt   # recreate venv to exact known-good state
```

Key pinned versions (pydantic drift caused 4-day silent outage Mar 2026):
- `pydantic~=2.12.5` + `pydantic_core~=2.41.5`
- `mcp~=1.26.0`
- Full lock: `requirements.txt`

## Python Version Note

Code has zero Python 3.14-specific syntax — all files parse cleanly under 3.13.
**Consider switching to Python 3.13** for broader ecosystem wheel support.
3.14 is pre-release; wheels publish late, increasing breakage risk.

## Testing

```bash
make test       # runs pytest tests/
make preflight  # quick import + dependency check
./health_check.sh   # standalone import verification
```

## Files NOT to modify without care

- `utils.py` reliability classes — shared by url_scheme and fast_server
- `url_scheme.py` — Things URL spec compliance, encoding is finicky
- `applescript_bridge.py` — tested AppleScript syntax; wrong syntax causes error -2741
