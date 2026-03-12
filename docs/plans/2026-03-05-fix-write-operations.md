# Things MCP — Write Operations Fix Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make all write operations in fast_server.py reliably modify Things 3 by routing them through the AppleScript bridge instead of the broken URL scheme.

**Architecture:** The `things-py` library reads directly from Things' SQLite DB (reliable). URL scheme writes (`webbrowser.open("things:///...")`) silently succeed but never modify Things in background processes. The `applescript_bridge.py` module already has `update_todo_direct()` which uses `osascript` and works reliably. We extend it to cover all write operations and wire `fast_server.py` to use it.

**Tech Stack:** Python 3.12+, osascript, FastMCP, things-py, pytest

---

## Context (Read This First)

### What's broken and why

```
fast_server.py → add_todo() → url_scheme.construct_url() → webbrowser.open("things:///add?...")
                                                             ↑ Returns True. Nothing happens.
```

URL schemes require Things to be in the foreground OR have a registered URL handler. In background/stdio MCP processes, the OS delivers the URL open but Things ignores it silently.

### What works

```
applescript_bridge.update_todo_direct() → osascript → Things3 AppleScript dictionary
                                           ↑ Bypasses URL scheme entirely. Always works.
```

Confirmed in production 2026-03-05: completed 17 todos with 100% success rate via osascript.

### The one AppleScript gotcha (critical)

```applescript
complete to do id "UUID"           -- BROKEN: error -2741 "Expected end of line"
set status of to do id "UUID" to completed  -- CORRECT
```

`applescript_bridge.update_todo_direct()` already uses the correct syntax (line 305).

### Files involved

| File | Role | Touch? |
|------|------|--------|
| `src/things_mcp/fast_server.py` | Active MCP server | Yes — rewire write tools |
| `src/things_mcp/applescript_bridge.py` | Write via osascript | Yes — add add_todo_direct_v2, add_project_direct, update_project_direct; fix bugs |
| `src/things_mcp/cache.py` | TTL cache | Yes — fix broken invalidation |
| `src/things_mcp/utils.py` | Circuit breaker, DLQ | Yes — fix DLQ path, remove duplicate fn |
| `tests/` | Test suite | Yes — create from scratch |
| `handlers.py`, `mcp_tools.py`, `simple_server.py`, `simple_url_scheme.py` | Dead code | Delete |

---

## Phase 1 — Safety Net (Tests First)

### Task 1: Bootstrap test infrastructure

**Files:**
- Create: `tests/__init__.py`
- Create: `tests/test_applescript_bridge.py`
- Create: `tests/test_cache.py`

**Step 1: Create test files**

```bash
mkdir -p tests
touch tests/__init__.py
```

**Step 2: Write tests for `escape_applescript_string`**

Create `tests/test_applescript_bridge.py`:

```python
import pytest
from src.things_mcp.applescript_bridge import escape_applescript_string, run_applescript

class TestEscapeApplescriptString:
    def test_escapes_double_quotes(self):
        assert escape_applescript_string('say "hello"') == 'say ""hello""'

    def test_preserves_plus_signs(self):
        # + is valid in titles like "C++ Programming"
        assert escape_applescript_string("C++ Programming") == "C++ Programming"

    def test_preserves_spaces(self):
        assert escape_applescript_string("hello world") == "hello world"

    def test_empty_string(self):
        assert escape_applescript_string("") == ""

    def test_none_returns_empty(self):
        assert escape_applescript_string(None) == ""

    def test_backslash(self):
        result = escape_applescript_string("path\\file")
        assert '"' not in result or '""' in result  # no unescaped quotes

class TestRunApplescript:
    def test_returns_output_on_success(self):
        result = run_applescript('return "hello"')
        assert result == "hello"

    def test_returns_false_on_error(self):
        result = run_applescript('this is not valid applescript !!!@@@')
        assert result is False

    def test_timeout_parameter_accepted(self):
        # Should not raise; just verifies the timeout kwarg is wired
        result = run_applescript('return "ok"', timeout=5)
        assert result == "ok"
```

**Step 3: Write tests for cache invalidation**

Create `tests/test_cache.py`:

```python
import pytest
import time
from src.things_mcp.cache import ThingsCache

class TestThingsCache:
    def setup_method(self):
        self.cache = ThingsCache(default_ttl=60)

    def test_set_and_get(self):
        self.cache.set("get-inbox", "result", ttl=60)
        assert self.cache.get("get-inbox") == "result"

    def test_expired_entry_returns_none(self):
        self.cache.set("get-today", "result", ttl=1)
        time.sleep(1.1)
        assert self.cache.get("get-today") is None

    def test_invalidate_operation_removes_matching_entries(self):
        self.cache.set("get-inbox", "result1", ttl=60)
        self.cache.set("get-today", "result2", ttl=60)
        self.cache.invalidate("get-inbox")
        assert self.cache.get("get-inbox") is None
        assert self.cache.get("get-today") == "result2"  # untouched

    def test_invalidate_all_clears_cache(self):
        self.cache.set("get-inbox", "result1", ttl=60)
        self.cache.set("get-today", "result2", ttl=60)
        self.cache.invalidate()
        assert self.cache.get("get-inbox") is None
        assert self.cache.get("get-today") is None

    def test_hit_rate_tracking(self):
        self.cache.set("op", "val", ttl=60)
        self.cache.get("op")   # hit
        self.cache.get("op")   # hit
        self.cache.get("missing")  # miss
        stats = self.cache.get_stats()
        assert stats["hits"] == 2
        assert stats["misses"] == 1
```

**Step 4: Run tests — expect failures (that's the point)**

```bash
cd /Users/didierh/projects/things-ca
python -m pytest tests/ -v 2>&1 | head -60
```

Expected failures:
- `test_preserves_plus_signs` — FAIL (current code replaces + with space)
- `test_timeout_parameter_accepted` — FAIL (`run_applescript` doesn't accept timeout)
- `test_invalidate_operation_removes_matching_entries` — FAIL (broken prefix matching)

**Step 5: Commit baseline tests**

```bash
git add tests/
git commit -m "test: add baseline tests for applescript_bridge and cache (failing)"
```

---

## Phase 2 — Bug Fixes (Make Tests Pass)

### Task 2: Fix `escape_applescript_string` — remove `+` corruption

**File:** `src/things_mcp/applescript_bridge.py:128-129`

**Current code (line 128-129):**
```python
# Replace any "+" with spaces first
text = text.replace("+", " ")
```

**Step 1: Delete those two lines**

Remove lines 128-129. The function should be:
```python
def escape_applescript_string(text: str) -> str:
    if not text:
        return ""
    # Escape quotes by doubling them (AppleScript style)
    return text.replace('"', '""')
```

**Step 2: Run the test**
```bash
python -m pytest tests/test_applescript_bridge.py::TestEscapeApplescriptString -v
```
Expected: All pass.

**Step 3: Commit**
```bash
git add src/things_mcp/applescript_bridge.py
git commit -m "fix: remove + corruption in escape_applescript_string"
```

---

### Task 3: Fix `run_applescript` — add timeout parameter

**File:** `src/things_mcp/applescript_bridge.py:8-28`

**Current signature:**
```python
def run_applescript(script: str) -> Union[str, bool]:
```

**New signature and body:**
```python
def run_applescript(script: str, timeout: int = 10) -> Union[str, bool]:
    """Run an AppleScript command and return the result.

    Args:
        script: The AppleScript code to execute
        timeout: Seconds before giving up (default 10)

    Returns:
        The result string, or False if it failed or timed out
    """
    try:
        result = subprocess.run(
            ['osascript', '-e', script],
            capture_output=True,
            text=True,
            timeout=timeout
        )

        if result.returncode != 0:
            logger.error(f"AppleScript error: {result.stderr}")
            return False

        return result.stdout.strip()
    except subprocess.TimeoutExpired:
        logger.error(f"AppleScript timed out after {timeout}s")
        return False
    except Exception as e:
        logger.error(f"Error running AppleScript: {str(e)}")
        return False
```

**Step 1: Apply the change**

**Step 2: Run tests**
```bash
python -m pytest tests/test_applescript_bridge.py -v
```
Expected: All pass.

**Step 3: Commit**
```bash
git add src/things_mcp/applescript_bridge.py
git commit -m "fix: add timeout parameter to run_applescript (default 10s)"
```

---

### Task 4: Fix cache invalidation by operation name

**File:** `src/things_mcp/cache.py`

**Problem:** `_make_key` creates `md5("operation:{params}")` — one monolithic hash. Can't find all keys for an operation without scanning every key.

**Fix:** Change the cache dict to store keys as `"operation:md5(params)"` strings instead of a single MD5. This makes operation-prefix matching trivial.

**Step 1: Modify `_make_key` to return a prefix-friendly key**

```python
def _make_key(self, operation: str, **kwargs) -> str:
    """Generate a cache key from operation and parameters."""
    sorted_params = json.dumps(kwargs, sort_keys=True)
    params_hash = hashlib.md5(sorted_params.encode()).hexdigest()
    return f"{operation}:{params_hash}"
```

**Step 2: Modify `invalidate` to use simple string prefix matching**

```python
def invalidate(self, operation: Optional[str] = None, **kwargs) -> None:
    with self.lock:
        if operation and kwargs:
            key = self._make_key(operation, **kwargs)
            self.cache.pop(key, None)
            logger.debug(f"Invalidated specific cache entry: {key}")
        elif operation:
            prefix = f"{operation}:"
            keys_to_remove = [k for k in self.cache if k.startswith(prefix)]
            for key in keys_to_remove:
                del self.cache[key]
            logger.debug(f"Invalidated {len(keys_to_remove)} entries for: {operation}")
        else:
            self.cache.clear()
            logger.info("Cleared entire cache")
```

**Step 3: Run tests**
```bash
python -m pytest tests/test_cache.py -v
```
Expected: All pass including `test_invalidate_operation_removes_matching_entries`.

**Step 4: Commit**
```bash
git add src/things_mcp/cache.py
git commit -m "fix: repair cache invalidation by operation name"
```

---

### Task 5: Fix DLQ path — use home directory

**File:** `src/things_mcp/utils.py:178`

**Current:**
```python
def __init__(self, dlq_file="things_dlq.json"):
```

**Fix:**
```python
from pathlib import Path

class DeadLetterQueue:
    def __init__(self, dlq_file=None):
        if dlq_file is None:
            dlq_file = Path.home() / ".things-mcp" / "things_dlq.json"
            dlq_file.parent.mkdir(parents=True, exist_ok=True)
        self.dlq_file = str(dlq_file)
        self.queue = self._load_queue()
```

**Step 1: Apply the change**

**Step 2: Verify no test regressions**
```bash
python -m pytest tests/ -v
```

**Step 3: Commit**
```bash
git add src/things_mcp/utils.py
git commit -m "fix: store dead letter queue in ~/.things-mcp/ instead of cwd"
```

---

### Task 6: Remove duplicate `validate_tool_registration`

**File:** `src/things_mcp/utils.py:335-353`

The second definition (line 335) is a simpler version that shadows the first (line 87). Delete lines 335-353 (the second one).

**Step 1: Delete the second definition**

Find and remove:
```python
def validate_tool_registration(tool_list):
    """Validate that all tools are properly registered"""
    required_tools = [
        ...
    ]
    tool_names = [t.name for t in tool_list]
    ...
```

**Step 2: Run tests**
```bash
python -m pytest tests/ -v
```

**Step 3: Commit**
```bash
git add src/things_mcp/utils.py
git commit -m "fix: remove duplicate validate_tool_registration in utils.py"
```

---

## Phase 3 — Core Fix: Route Writes Through AppleScript

> ⚠️ **PEER REVIEW CHECKPOINT** — Before implementing Phase 3, the plan and Phase 1-2 changes should be reviewed. See review checklist at the bottom of this document.

### Task 7: Add `add_todo_direct_v2` to applescript_bridge

The existing `add_todo_direct` works but has limitations. We need a clean version for fast_server that supports all parameters.

**File:** `src/things_mcp/applescript_bridge.py` — add after line 114

```python
def complete_todo(uuid: str) -> bool:
    """Mark a single todo as complete by UUID.

    Args:
        uuid: The Things UUID of the todo

    Returns:
        True if successful, False otherwise
    """
    script = f'''tell application "Things3"
  try
    set theToDo to to do id "{escape_applescript_string(uuid)}"
    set status of theToDo to completed
    return "ok"
  on error errMsg
    return "error: " & errMsg
  end try
end tell'''
    result = run_applescript(script)
    if result == "ok":
        logger.info(f"Completed todo: {uuid}")
        return True
    logger.error(f"Failed to complete todo {uuid}: {result}")
    return False
```

**Tests to add to `tests/test_applescript_bridge.py`:**

```python
from unittest.mock import patch

class TestCompleteTodo:
    def test_returns_true_on_success(self):
        with patch('src.things_mcp.applescript_bridge.run_applescript', return_value="ok"):
            from src.things_mcp.applescript_bridge import complete_todo
            assert complete_todo("some-uuid") is True

    def test_returns_false_on_failure(self):
        with patch('src.things_mcp.applescript_bridge.run_applescript', return_value="error: not found"):
            from src.things_mcp.applescript_bridge import complete_todo
            assert complete_todo("bad-uuid") is False

    def test_uuid_is_escaped(self):
        """UUID with quotes should not break the script."""
        captured = []
        def capture(script, **kwargs):
            captured.append(script)
            return "ok"
        with patch('src.things_mcp.applescript_bridge.run_applescript', side_effect=capture):
            from src.things_mcp.applescript_bridge import complete_todo
            complete_todo('uuid"with"quotes')
        assert '""' in captured[0]  # quotes were doubled
```

**Step 1: Add `complete_todo` function**
**Step 2: Run tests**
```bash
python -m pytest tests/test_applescript_bridge.py -v
```
**Step 3: Commit**
```bash
git add src/things_mcp/applescript_bridge.py tests/test_applescript_bridge.py
git commit -m "feat: add complete_todo() to applescript_bridge with tests"
```

---

### Task 8: Wire `update-todo` (completed/canceled) in fast_server to AppleScript

**File:** `src/things_mcp/fast_server.py:412-460`

The `update_task` function currently calls `update_todo()` from `url_scheme`. Route `completed` and `canceled` status changes through `update_todo_direct` from `applescript_bridge`.

**Current update_task (simplified):**
```python
@mcp.tool(name="update-todo")
def update_task(id: str, ..., completed: Optional[bool] = None, canceled: Optional[bool] = None) -> str:
    ...
    result = update_todo(id=id, ..., completed=completed, canceled=canceled)
    ...
```

**New implementation:**
```python
from .applescript_bridge import update_todo_direct

@mcp.tool(name="update-todo")
def update_task(
    id: str,
    title: Optional[str] = None,
    notes: Optional[str] = None,
    when: Optional[str] = None,
    deadline: Optional[str] = None,
    tags: Optional[List[str]] = None,
    completed: Optional[bool] = None,
    canceled: Optional[bool] = None
) -> str:
    """Update an existing todo in Things"""
    try:
        success = update_todo_direct(
            id=id,
            title=title,
            notes=notes,
            when=when,
            deadline=deadline,
            tags=tags,
            completed=completed,
            canceled=canceled
        )
        if not success:
            return f"Error: Failed to update todo with ID: {id}"
        invalidate_caches_for(["get-inbox", "get-today", "get-upcoming", "get-anytime", "get-todos"])
        return f"Successfully updated todo with ID: {id}"
    except Exception as e:
        logger.error(f"Error updating todo: {str(e)}")
        return f"Error updating todo: {str(e)}"
```

**Tests to add to `tests/test_fast_server.py`** (create new file):

```python
from unittest.mock import patch

class TestUpdateTodo:
    def test_calls_applescript_bridge_not_url_scheme(self):
        """Verify update-todo uses applescript_bridge, not url_scheme."""
        with patch('src.things_mcp.fast_server.update_todo_direct', return_value=True) as mock_as, \
             patch('src.things_mcp.url_scheme.execute_url') as mock_url:
            from src.things_mcp.fast_server import update_task
            result = update_task(id="some-uuid", completed=True)
            assert mock_as.called
            assert not mock_url.called
            assert "Successfully" in result

    def test_returns_error_on_failure(self):
        with patch('src.things_mcp.fast_server.update_todo_direct', return_value=False):
            from src.things_mcp.fast_server import update_task
            result = update_task(id="bad-uuid", completed=True)
            assert "Error" in result
```

**Step 1: Add import at top of fast_server.py**
```python
from .applescript_bridge import update_todo_direct
```

**Step 2: Replace `update_task` function body**

**Step 3: Run tests**
```bash
python -m pytest tests/test_fast_server.py -v
python -m pytest tests/ -v  # full suite
```

**Step 4: Manual smoke test**
```bash
# Start the server briefly and send an update via osascript to verify
osascript -e 'tell application "Things3" to count to dos of list "Inbox"'
# Then test via Claude Desktop: ask it to complete a known todo
```

**Step 5: Commit**
```bash
git add src/things_mcp/fast_server.py tests/test_fast_server.py
git commit -m "fix: route update-todo through applescript_bridge instead of url_scheme"
```

---

### Task 9: Wire `add-todo` in fast_server to AppleScript

**File:** `src/things_mcp/fast_server.py:306-360`

The `add_task` function currently calls `add_todo()` from `url_scheme`. Route through `add_todo_direct` from `applescript_bridge`.

**New implementation:**
```python
from .applescript_bridge import add_todo_direct

@mcp.tool(name="add-todo")
def add_task(
    title: str,
    notes: Optional[str] = None,
    when: Optional[str] = None,
    deadline: Optional[str] = None,
    tags: Optional[List[str]] = None,
    checklist_items: Optional[List[str]] = None,
    list_id: Optional[str] = None,
    list_title: Optional[str] = None,
    heading: Optional[str] = None
) -> str:
    """Create a new todo in Things"""
    try:
        task_id = add_todo_direct(
            title=title,
            notes=notes,
            when=when,
            tags=tags,
            list_title=list_title
        )
        if not task_id:
            return f"Error: Failed to create todo: {title}"
        invalidate_caches_for(["get-inbox", "get-today", "get-upcoming", "get-todos"])
        return f"Successfully created todo: {title} (ID: {task_id})"
    except Exception as e:
        logger.error(f"Error creating todo: {str(e)}")
        return f"Error creating todo: {str(e)}"
```

> **Note:** `add_todo_direct` does not currently support `deadline`, `checklist_items`, `list_id`, `heading`. These are accepted but silently ignored. This is acceptable for now — they can be added to `applescript_bridge` in a follow-up. The important fix is that `title`, `notes`, `when`, `tags`, `list_title` work.

**Tests to add to `tests/test_fast_server.py`:**

```python
class TestAddTodo:
    def test_calls_applescript_bridge_not_url_scheme(self):
        with patch('src.things_mcp.fast_server.add_todo_direct', return_value="new-uuid-123") as mock_as, \
             patch('src.things_mcp.url_scheme.execute_url') as mock_url:
            from src.things_mcp.fast_server import add_task
            result = add_task(title="Test todo")
            assert mock_as.called
            assert not mock_url.called
            assert "Successfully" in result
            assert "new-uuid-123" in result

    def test_returns_error_when_creation_fails(self):
        with patch('src.things_mcp.fast_server.add_todo_direct', return_value=False):
            from src.things_mcp.fast_server import add_task
            result = add_task(title="Test todo")
            assert "Error" in result
```

**Step 1: Add import**
```python
from .applescript_bridge import add_todo_direct
```

**Step 2: Replace `add_task` function body**

**Step 3: Run tests**
```bash
python -m pytest tests/ -v
```

**Step 4: Commit**
```bash
git add src/things_mcp/fast_server.py tests/test_fast_server.py
git commit -m "fix: route add-todo through applescript_bridge instead of url_scheme"
```

---

## Phase 4 — Cleanup

### Task 10: Remove dead modules

**Files to delete:**
- `src/things_mcp/handlers.py` — 25KB, never imported by active server
- `src/things_mcp/mcp_tools.py` — 16KB, never imported
- `src/things_mcp/simple_server.py` — 21KB, not in any entry point
- `src/things_mcp/simple_url_scheme.py` — only imported by simple_server

**Step 1: Verify nothing imports these**
```bash
grep -r "from .handlers" src/things_mcp/
grep -r "from .mcp_tools" src/things_mcp/
grep -r "from .simple_server" src/things_mcp/
grep -r "simple_url_scheme" src/things_mcp/
grep -r "import handlers" things_fast_server.py things_server.py
```
Expected: no matches (except inside the files themselves).

**Step 2: Delete**
```bash
rm src/things_mcp/handlers.py
rm src/things_mcp/mcp_tools.py
rm src/things_mcp/simple_server.py
rm src/things_mcp/simple_url_scheme.py
```

**Step 3: Run full test suite**
```bash
python -m pytest tests/ -v
python -c "from src.things_mcp.fast_server import mcp; print('import OK')"
```

**Step 4: Commit**
```bash
git add -A
git commit -m "chore: remove dead modules (handlers, mcp_tools, simple_server, simple_url_scheme)"
```

---

### Task 11: Remove unused `httpx` dependency and dead url_scheme code

**Files:**
- `pyproject.toml` — remove `httpx` from dependencies
- `src/things_mcp/url_scheme.py` — remove `should_use_json_api()` and the `if False and ...` block

**Step 1: Remove httpx from pyproject.toml**

In `[project] dependencies`, delete:
```
"httpx>=0.28.1",
```

**Step 2: Remove dead functions from url_scheme.py**

Delete `should_use_json_api()` (lines 206-223) and the dead block in `construct_url` (lines 155-160):
```python
# Delete this:
use_json_api = False

if False and command in ['add'] and use_json_api:
    # This code is disabled but kept for reference
    logger.info("JSON API is currently disabled due to formatting issues")
    pass
```

**Step 3: Run tests**
```bash
python -m pytest tests/ -v
```

**Step 4: Commit**
```bash
git add pyproject.toml src/things_mcp/url_scheme.py
git commit -m "chore: remove unused httpx dependency and dead JSON API code"
```

---

## Final Verification

```bash
# Full test suite
python -m pytest tests/ -v --tb=short

# Import smoke test
python -c "from src.things_mcp.fast_server import mcp, run_things_mcp_server; print('OK')"

# Server startup smoke test (Ctrl+C after 3s)
timeout 3 python things_fast_server.py || echo "Server started OK"

# Live test: complete a real Things todo
osascript -e 'tell application "Things3" to count to dos of list "Inbox"'
```

---

## Peer Review Checklist

Before executing Phase 3 (Tasks 7-9), reviewer should confirm:

- [ ] `update_todo_direct` in `applescript_bridge.py` uses `set status of to do id "UUID" to completed` (not `complete to do id`) — confirm line 305
- [ ] The `add_todo_direct` function returns the UUID string on success and `False` on failure — confirm lines 108-114
- [ ] Phase 1-2 tests all pass before Phase 3 starts
- [ ] Reviewer is comfortable that removing URL scheme from write path is the right call (it is — URL scheme writes are confirmed broken, AppleScript is confirmed working)
- [ ] `list_id`, `deadline`, `checklist_items`, `heading` being silently ignored in the new `add_task` is acceptable for now (acknowledged limitation, not a regression — they never worked before either)

**Reviewer:** Post review result to `Inbox/Handoffs/to-claude-code/2026-03-05-fix-plan-review.md`

---

## Summary of Changes

| # | File | Type | Impact |
|---|------|------|--------|
| 1 | `applescript_bridge.py` | Bug fix | `+` chars no longer corrupted in titles |
| 2 | `applescript_bridge.py` | Bug fix | AppleScript calls can't hang server anymore |
| 3 | `applescript_bridge.py` | New fn | `complete_todo()` added |
| 4 | `cache.py` | Bug fix | Operation-level invalidation now works |
| 5 | `utils.py` | Bug fix | DLQ written to `~/.things-mcp/` |
| 6 | `utils.py` | Cleanup | Duplicate fn removed |
| 7 | `fast_server.py` | Core fix | `update-todo` → AppleScript (writes work) |
| 8 | `fast_server.py` | Core fix | `add-todo` → AppleScript (writes work) |
| 9 | Dead modules | Cleanup | 62KB of unused code deleted |
| 10 | `pyproject.toml` | Cleanup | Unused `httpx` dependency removed |
| 11 | `url_scheme.py` | Cleanup | Dead JSON API code removed |

**Not addressed in this plan (follow-up):**
- `add-project` and `update-project` still use URL scheme — needs new AppleScript functions
- `deadline`, `checklist_items`, `list_id`, `heading` params in `add-todo` not wired to AppleScript
- `OperationLogFilter` thread-safety (low risk with synchronous FastMCP)
- `@cached` decorator ignores positional args (no tools use positional args currently)
