# Things 3 Enhanced MCP — Codebase Analysis

**Reviewed:** 2026-03-11 (updated from 2026-03-05 baseline)
**Project:** things3-enhanced-mcp v1.1.0
**Reviewer:** Claude Code
**Previous review:** 2026-03-05 (pre-fix baseline, score 5.5/10)

---

## Health Score: 7.5/10 (was 5.5/10)

| Dimension | Before | After | Delta | Notes |
|-----------|--------|-------|-------|-------|
| Architecture | 6/10 | 8/10 | +2 | Dead code removed, single write path |
| Code Quality | 5/10 | 7/10 | +2 | Duplicate functions removed, bugs fixed |
| Reliability | 4/10 | 8/10 | +4 | All write operations work reliably |
| Security | 6/10 | 7/10 | +1 | Injection-vulnerable handlers.py deleted |
| Documentation | 7/10 | 8/10 | +1 | SSOT updated, docs match reality |
| Testing | 1/10 | 6/10 | +5 | 31 automated tests (was 0) |

---

## Project Structure (current)

```
things-ca/
├── things_fast_server.py        # Entry point — imports fast_server.py
├── things_server.py             # Legacy entry point (unused, candidate for deletion)
├── configure_token.py           # Token setup CLI utility
├── src/things_mcp/
│   ├── fast_server.py           # ACTIVE: FastMCP server — all reads + writes work
│   ├── applescript_bridge.py    # Write operations via osascript (primary write path)
│   ├── url_scheme.py            # URL scheme builder (reads only — show, search)
│   ├── tag_handler.py           # AppleScript-based tag creation
│   ├── cache.py                 # Thread-safe TTL cache with prefix-key invalidation
│   ├── config.py                # Auth token + settings (~/.things-mcp/config.json)
│   ├── utils.py                 # Circuit breaker, DLQ, rate limiter, app state
│   ├── logging_config.py        # Structured logging with rotation
│   ├── formatters.py            # Output formatters for todos/projects/areas/tags
│   ├── things_server.py         # Legacy server module (unused)
│   └── __init__.py
├── tests/
│   ├── __init__.py
│   ├── test_applescript_bridge.py  # 18 tests: escape, run, add/update project
│   ├── test_cache.py               # 5 tests: TTL, invalidation, hit rate
│   └── test_fast_server.py         # 8 tests: all 4 write tools use bridge
├── docs/
│   └── plans/
│       └── 2026-03-05-fix-write-operations.md  # Original fix plan (executed)
├── pyproject.toml
└── uv.lock
```

**Active code path:**
- **Reads:** `fast_server.py` → `things-py` (SQLite) — reliable
- **Writes:** `fast_server.py` → `applescript_bridge.py` → `osascript` — reliable
- **UI navigation:** `fast_server.py` → `url_scheme.py` → `show()` — works (foreground only)

**Deleted since baseline:** `handlers.py` (25KB), `mcp_tools.py` (16KB), `simple_server.py` (21KB), `simple_url_scheme.py` (~8KB) — 62KB of dead code removed.

---

## Write Operations — Architecture

### Data flow (after fix)

```
Claude Desktop / MCP Client
    │
    ▼
fast_server.py (FastMCP tool handlers)
    │
    ├── add-todo      → add_todo_direct()      → osascript → Things 3
    ├── update-todo   → update_todo_direct()    → osascript → Things 3
    ├── add-project   → add_project_direct()    → osascript → Things 3
    └── update-project→ update_project_direct() → osascript → Things 3
```

### Why URL scheme was broken

URL schemes (`things:///add?...`) require Things to be in the foreground OR have a registered URL handler. In background/stdio MCP processes, `webbrowser.open()` returns `True` but Things never processes the command. This is a macOS architectural limitation, not a configuration issue.

### Why AppleScript works

`osascript` sends Apple Events directly to the Things process via the Mach port. This works regardless of app focus state, background processes, or stdio context. Confirmed in production: 17 todos completed with 100% success rate on 2026-03-05.

### Critical AppleScript syntax

```applescript
-- CORRECT: set property approach
set status of to do id "UUID" to completed

-- BROKEN: verb approach (error -2741 "Expected end of line")
complete to do id "UUID"
```

---

## Bugs Fixed (2026-03-05 → 2026-03-11)

| # | Bug | File | Severity | Commit |
|---|-----|------|----------|--------|
| 1 | Write operations silently fail via URL scheme | `fast_server.py` | Critical | `fbb7b7b`, `f1074ff` |
| 2 | `escape_applescript_string` corrupts `+` chars | `applescript_bridge.py:128` | Medium | `e7c79b2` |
| 3 | `run_applescript` has no timeout | `applescript_bridge.py:18` | Medium | `e7c79b2` |
| 4 | Cache invalidation by operation name is a no-op | `cache.py:103-109` | High | `e7c79b2` |
| 5 | DLQ writes to cwd instead of `~/.things-mcp/` | `utils.py:178` | Low | `e7c79b2` |
| 6 | Duplicate `validate_tool_registration` in utils | `utils.py:87,335` | Low | `e7c79b2` |
| 7 | AppleScript injection risk in handlers.py | `handlers.py:445` | Medium | `b3f5869` (deleted) |

---

## Known Issues (remaining)

### Low priority — not regressions

| # | Issue | File | Impact | Notes |
|---|-------|------|--------|-------|
| 1 | `add-todo` ignores `deadline`, `checklist_items`, `list_id`, `heading` | `fast_server.py` | Low | Accepted by function signature but not wired to AppleScript. Never worked before either. |
| 2 | `add-project` ignores `area_id` | `fast_server.py` | Low | Only `area_title` (name-based lookup) works. Same as before. |
| 3 | `datetime.utcnow()` deprecation warning | `logging_config.py:23` | Cosmetic | 24 warnings per test run. Fix: `datetime.now(datetime.UTC)`. |
| 4 | `url_scheme.py` still contains unused `add_todo`, `update_todo` etc. | `url_scheme.py` | Cosmetic | No longer imported by `fast_server.py`. Could be cleaned up. |
| 5 | `things_server.py` (both root + src/) are unused | multiple | Cosmetic | Legacy entry points. |
| 6 | `@cached` decorator ignores positional args | `cache.py:172` | Low | All tools use kwargs, so no current impact. |
| 7 | `OperationLogFilter` not thread-safe | `logging_config.py:48` | Low | FastMCP is synchronous, so no current impact. |

---

## Module Quality Summary (current)

| Module | Quality | Role | Notes |
|--------|---------|------|-------|
| `fast_server.py` | Good | MCP server | All reads + writes work. Clean tool handlers. |
| `applescript_bridge.py` | Good | Write operations | 6 functions: add/update for todos + projects, escape, run |
| `formatters.py` | Good | Output formatting | Clean, minimal, does one thing well |
| `cache.py` | Good | TTL cache | Prefix-key invalidation works correctly now |
| `config.py` | Good | Configuration | Clean singleton, env var override, correct paths |
| `utils.py` | Good | Infrastructure | Circuit breaker, DLQ (correct path), rate limiter |
| `logging_config.py` | Good | Logging | Structured JSON, rotation. Minor: utcnow deprecation |
| `tag_handler.py` | Good | Tag creation | Has timeout, decent escaping |
| `url_scheme.py` | Fair | URL builder | Only used for `show()` and `search()` now. Has dead code. |

---

## Test Coverage

| Test file | Tests | What's covered |
|-----------|-------|---------------|
| `test_applescript_bridge.py` | 18 | `escape_applescript_string` (6), `run_applescript` (3), `add_project_direct` (5), `update_project_direct` (4) |
| `test_cache.py` | 5 | set/get, TTL expiry, operation invalidation, full clear, hit rate |
| `test_fast_server.py` | 8 | All 4 write tools route through bridge (success + failure cases) |
| **Total** | **31** | All pass, 1.8s runtime |

### Not yet tested

- Read operations (`get-inbox`, `get-today`, etc.) — these use `things-py` directly and are stable
- `add_todo_direct` and `update_todo_direct` unit tests (bridge functions for todos)
- Integration tests against live Things 3
- `show-item` and `search` operations

---

## Commit History (post-baseline)

| Commit | Date | Type | Description |
|--------|------|------|-------------|
| `e7c79b2` | 2026-03-06 | fix | Phase 1-2: Tests + bug fixes (escape, timeout, cache, DLQ, dup function) |
| `fbb7b7b` | 2026-03-06 | fix | Route add-todo/update-todo through AppleScript bridge |
| `b3f5869` | 2026-03-06 | chore | Remove dead modules + httpx dependency (62KB deleted) |
| `f1074ff` | 2026-03-08 | fix | Route add-project/update-project through AppleScript bridge |

---

## Peer Review Checklist

For auditing the current state of the codebase:

- [ ] All 4 write operations in `fast_server.py` import from `applescript_bridge`, not `url_scheme`
- [ ] `fast_server.py` has no remaining imports of `add_todo`, `update_todo`, `add_project`, `update_project` from `url_scheme`
- [ ] `applescript_bridge.py` uses `set status of ... to completed` (not `complete to do id`)
- [ ] `run_applescript()` has `timeout` parameter (default 10s)
- [ ] `escape_applescript_string()` does NOT replace `+` with space
- [ ] `cache.py` `_make_key()` returns `"operation:md5(params)"` format (prefix-friendly)
- [ ] `cache.py` `invalidate(operation)` uses `startswith(prefix)` matching
- [ ] `utils.py` `DeadLetterQueue` defaults to `~/.things-mcp/things_dlq.json`
- [ ] `utils.py` has only ONE `validate_tool_registration` function
- [ ] Dead modules (`handlers.py`, `mcp_tools.py`, `simple_server.py`, `simple_url_scheme.py`) are gone
- [ ] `pyproject.toml` does NOT list `httpx` as dependency
- [ ] `tests/` has 31 passing tests (`python -m pytest tests/ -v`)

### Verification commands

```bash
# All tests pass
python -m pytest tests/ -v --tb=short

# Import smoke test
python -c "from src.things_mcp.fast_server import mcp, run_things_mcp_server; print('OK')"

# No URL scheme write imports in fast_server
grep -E "from .url_scheme import.*(add_todo|update_todo|add_project|update_project)" src/things_mcp/fast_server.py
# Expected: no output

# Dead modules gone
ls src/things_mcp/handlers.py src/things_mcp/mcp_tools.py src/things_mcp/simple_server.py src/things_mcp/simple_url_scheme.py 2>&1
# Expected: No such file or directory (4x)
```

---

## References

- Original project: https://github.com/hald/things-mcp
- Enhanced fork: https://github.com/excelsier/things-fastmcp
- Things URL scheme docs: https://culturedcode.com/things/help/url-scheme/
- Things AppleScript dictionary: Open Script Editor → File → Open Dictionary → Things3
- MCP docs: https://modelcontextprotocol.io/
- Fix plan: `docs/plans/2026-03-05-fix-write-operations.md`
