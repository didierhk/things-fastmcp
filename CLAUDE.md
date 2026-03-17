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

## Testing

```bash
make test       # runs pytest tests/
make preflight  # quick import + dependency check
./health_check.sh   # standalone import verification (exit 0 = healthy)
```

## Files NOT to modify without care

- `utils.py` reliability classes — shared by url_scheme and fast_server
- `url_scheme.py` — Things URL spec compliance, encoding is finicky
- `applescript_bridge.py` — tested AppleScript syntax; wrong syntax causes error -2741

---

## Maintenance Tasks

### PENDING: Migrate venv to Python 3.13

**Why:** Currently running Python 3.14.2 (pre-release). Zero 3.14-specific syntax in codebase — all files parse cleanly under 3.13. Pre-release Python means ecosystem wheels publish late, increasing breakage risk (root cause of Mar 2026 outage).

**Steps (low-risk, ~5 min):**
```bash
cd /Users/didierh/projects/things-ca

# 1. Destroy old venv
rm -rf .venv

# 2. Recreate with 3.13 (Homebrew has python3.13)
python3.13 -m venv .venv

# 3. Restore exact pinned deps
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install -e .

# 4. Verify
make preflight   # must print "Preflight checks passed"
make test        # must pass 31 tests

# 5. No MCP config change needed — path is still .venv/bin/python3
# 6. Restart Claude Desktop to pick up new venv
```

**Rollback:** If anything fails, `rm -rf .venv && python3.14 -m venv .venv && pip install -r requirements.txt`

---

### Routine: Updating dependencies

When you need to update a dep (e.g., `mcp` publishes a new version):

```bash
# 1. Install the new version
.venv/bin/pip install "mcp~=X.Y.0"

# 2. Verify nothing broke
make preflight && make test

# 3. Lock the new state
make freeze    # updates requirements.txt
git add requirements.txt pyproject.toml && git commit -m "chore: update mcp to X.Y.0"
```

**Never** update a dep without running `make preflight && make test` first.

---

### Routine: After any system Python upgrade or pyenv change

The venv is self-contained — system Python changes don't affect it.
But if you recreate the venv (e.g., after wiping `.venv`):

```bash
python3.13 -m venv .venv              # always use 3.13 (or current stable)
.venv/bin/pip install -r requirements.txt  # exact pinned state
.venv/bin/pip install -e .            # install project itself
make preflight                         # confirm healthy
```

---

### Diagnosing a broken MCP server

If the Things MCP server stops working in Claude Desktop:

```bash
# Step 1: Run health check
./health_check.sh
# Exit 0 = deps OK, Things running. Problem is elsewhere.
# Exit 1 = deps broken. See error message.

# Step 2: Verify MCP config python path
python3 -c "
import json, os
cfg = json.load(open(os.path.expanduser(
  '~/Library/Application Support/Claude/claude_desktop_config.json')))
print(cfg['mcpServers']['things']['command'])
"
# Must be: /Users/didierh/projects/things-ca/.venv/bin/python3

# Step 3: Test server startup directly
timeout 5 /Users/didierh/projects/things-ca/.venv/bin/python3 \
  /Users/didierh/projects/things-ca/things_fast_server.py 2>&1 | head -10
# Must show "Preflight checks passed" and "Things app is running"

# Step 4: If pydantic error, restore from lock file
cd /Users/didierh/projects/things-ca
pip install -r requirements.txt
```
