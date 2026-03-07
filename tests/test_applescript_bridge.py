import pytest
from unittest.mock import patch
from src.things_mcp.applescript_bridge import escape_applescript_string, run_applescript


class TestEscapeApplescriptString:
    def test_escapes_double_quotes(self):
        assert escape_applescript_string('say "hello"') == 'say ""hello""'

    def test_preserves_plus_signs(self):
        assert escape_applescript_string("C++ Programming") == "C++ Programming"

    def test_preserves_spaces(self):
        assert escape_applescript_string("hello world") == "hello world"

    def test_empty_string(self):
        assert escape_applescript_string("") == ""

    def test_none_returns_empty(self):
        assert escape_applescript_string(None) == ""

    def test_backslash(self):
        assert escape_applescript_string("path\\file") == "path\\file"


class TestRunApplescript:
    def test_returns_output_on_success(self):
        result = run_applescript('return "hello"')
        assert result == "hello"

    def test_returns_false_on_error(self):
        result = run_applescript('this is not valid applescript !!!@@@')
        assert result is False

    def test_timeout_parameter_accepted(self):
        result = run_applescript('return "ok"', timeout=5)
        assert result == "ok"
