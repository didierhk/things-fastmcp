# Changelog

All notable changes to Things 3 Enhanced MCP will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.0] - 2026-03-11

### Fixed
- **All write operations now work reliably** — rerouted `add-todo`, `update-todo`, `add-project`, `update-project` from broken URL scheme to AppleScript bridge (`osascript`). URL scheme writes silently succeeded but never modified Things in background/stdio processes.
- `escape_applescript_string` no longer corrupts `+` characters (e.g., "C++ Programming" was becoming "C   Programming")
- `run_applescript` now has a `timeout` parameter (default 10s) — prevents hung Things from blocking the MCP server indefinitely
- Cache invalidation by operation name now works — keys use `"operation:hash"` prefix format instead of opaque MD5
- Dead letter queue writes to `~/.things-mcp/things_dlq.json` instead of current working directory
- Removed duplicate `validate_tool_registration` function in utils.py

### Added
- `add_project_direct()` — create projects via AppleScript
- `update_project_direct()` — update projects via AppleScript
- Test suite: 31 automated tests covering applescript_bridge, cache, and all fast_server write tools

### Removed
- `handlers.py` (25KB) — dead code, never imported by active server
- `mcp_tools.py` (16KB) — dead code, old-style tool schemas
- `simple_server.py` (21KB) — dead code, unused duplicate server
- `simple_url_scheme.py` (~8KB) — dead code, only used by simple_server
- `httpx` dependency — not imported anywhere in source
- Dead JSON API code in `url_scheme.py`

### Changed
- `fast_server.py` no longer imports `add_todo`, `update_todo`, `add_project`, `update_project` from `url_scheme`
- `.gitignore` updated to allow test files in `tests/` directory

## [1.0.0] - 2025-05-30

### Added
- 🚀 **FastMCP Implementation**: Complete rewrite using FastMCP pattern for better maintainability
- 🔄 **Reliability Features**:
  - Circuit breaker pattern to prevent cascading failures
  - Exponential backoff retry logic for transient failures
  - Dead letter queue for failed operations
- ⚡ **Performance Optimizations**:
  - Intelligent caching system with TTL management
  - Rate limiting to prevent overwhelming Things app
  - Automatic cache invalidation on data modifications
- 🍎 **AppleScript Bridge**: Fallback mechanism when URL schemes fail
- 📊 **Enhanced Monitoring**:
  - Structured JSON logging
  - Performance metrics and statistics
  - Comprehensive error tracking
  - Debug-friendly output
- 🛡️ **Error Handling**: Comprehensive exception management and recovery
- 📦 **Smithery Support**: Full configuration for Smithery registry deployment
- 📝 **Documentation**: Enhanced README with detailed setup and troubleshooting guides

### Changed
- Rebranded to "Things 3 Enhanced MCP" for clear differentiation
- Updated package name to `things3-enhanced-mcp`
- Improved configuration token handling
- Enhanced URL scheme operations with better error recovery

### Fixed
- Token configuration import issues
- URL scheme reliability problems
- Various edge cases in task/project operations

### Attribution
Based on the original [things-mcp](https://github.com/hald/things-mcp) by Harald Lindstrøm

[1.0.0]: https://github.com/excelsier/things-fastmcp/releases/tag/v1.0.0 