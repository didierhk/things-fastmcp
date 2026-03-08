import pytest
from unittest.mock import patch
from src.things_mcp.applescript_bridge import (
    escape_applescript_string, run_applescript,
    add_project_direct, update_project_direct
)


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


class TestAddProjectDirect:
    def test_returns_id_on_success(self):
        with patch('src.things_mcp.applescript_bridge.run_applescript', return_value="project-uuid-123"):
            result = add_project_direct(title="Test Project")
            assert result == "project-uuid-123"

    def test_returns_false_on_failure(self):
        with patch('src.things_mcp.applescript_bridge.run_applescript', return_value=False):
            result = add_project_direct(title="Test Project")
            assert result is False

    def test_includes_notes_in_script(self):
        captured = []
        def capture(script, **kwargs):
            captured.append(script)
            return "uuid"
        with patch('src.things_mcp.applescript_bridge.run_applescript', side_effect=capture):
            add_project_direct(title="Proj", notes="Some notes")
        assert 'notes:"Some notes"' in captured[0]

    def test_creates_todos_in_project(self):
        captured = []
        def capture(script, **kwargs):
            captured.append(script)
            return "uuid"
        with patch('src.things_mcp.applescript_bridge.run_applescript', side_effect=capture):
            add_project_direct(title="Proj", todos=["Task 1", "Task 2"])
        assert 'make new to do' in captured[0]
        assert 'Task 1' in captured[0]
        assert 'Task 2' in captured[0]

    def test_assigns_to_area(self):
        captured = []
        def capture(script, **kwargs):
            captured.append(script)
            return "uuid"
        with patch('src.things_mcp.applescript_bridge.run_applescript', side_effect=capture):
            add_project_direct(title="Proj", area_title="Work")
        assert 'area' in captured[0].lower()
        assert 'Work' in captured[0]


class TestUpdateProjectDirect:
    def test_returns_true_on_success(self):
        with patch('src.things_mcp.applescript_bridge.run_applescript', return_value="true"):
            result = update_project_direct(id="proj-uuid", title="New Title")
            assert result is True

    def test_returns_false_on_failure(self):
        with patch('src.things_mcp.applescript_bridge.run_applescript', return_value="false"):
            result = update_project_direct(id="proj-uuid", completed=True)
            assert result is False

    def test_uses_project_class_not_todo(self):
        captured = []
        def capture(script, **kwargs):
            captured.append(script)
            return "true"
        with patch('src.things_mcp.applescript_bridge.run_applescript', side_effect=capture):
            update_project_direct(id="proj-uuid", title="Updated")
        assert 'project id' in captured[0]
        assert 'to do id' not in captured[0]

    def test_completion_sets_status(self):
        captured = []
        def capture(script, **kwargs):
            captured.append(script)
            return "true"
        with patch('src.things_mcp.applescript_bridge.run_applescript', side_effect=capture):
            update_project_direct(id="proj-uuid", completed=True)
        assert 'set status of theProject to completed' in captured[0]
