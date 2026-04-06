import pytest
from unittest.mock import patch
from src.things_mcp.applescript_bridge import (
    escape_applescript_string, run_applescript,
    add_todo_direct, update_todo_direct,
    add_project_direct, update_project_direct
)


def _capture_script(return_value="uuid"):
    """Helper: captures the AppleScript string passed to run_applescript."""
    captured = []
    def capture(script, **kwargs):
        captured.append(script)
        return return_value
    return captured, capture


class TestEscapeApplescriptString:
    def test_escapes_double_quotes(self):
        assert escape_applescript_string('say "hello"') == 'say \\"hello\\"'

    def test_preserves_plus_signs(self):
        assert escape_applescript_string("C++ Programming") == "C++ Programming"

    def test_preserves_spaces(self):
        assert escape_applescript_string("hello world") == "hello world"

    def test_empty_string(self):
        assert escape_applescript_string("") == ""

    def test_none_returns_empty(self):
        assert escape_applescript_string(None) == ""

    def test_backslash(self):
        assert escape_applescript_string("path\\file") == "path\\\\file"

    def test_newline_replaced_with_space(self):
        assert escape_applescript_string("line1\nline2") == "line1 line2"

    def test_carriage_return_replaced_with_space(self):
        assert escape_applescript_string("line1\rline2") == "line1 line2"


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


class TestAddTodoDirect:
    """Tests for add_todo_direct — verifies generated AppleScript structure."""

    def test_returns_id_on_success(self):
        with patch('src.things_mcp.applescript_bridge.run_applescript', return_value="todo-uuid-123"):
            result = add_todo_direct(title="Test Todo")
            assert result == "todo-uuid-123"

    def test_returns_false_on_failure(self):
        with patch('src.things_mcp.applescript_bridge.run_applescript', return_value=False):
            result = add_todo_direct(title="Test Todo")
            assert result is False

    def test_wraps_in_try_on_error(self):
        captured, capture = _capture_script()
        with patch('src.things_mcp.applescript_bridge.run_applescript', side_effect=capture):
            add_todo_direct(title="Test")
        assert 'try' in captured[0]
        assert 'on error errMsg' in captured[0]
        assert 'end try' in captured[0]

    def test_when_today_moves_to_today_list(self):
        captured, capture = _capture_script()
        with patch('src.things_mcp.applescript_bridge.run_applescript', side_effect=capture):
            add_todo_direct(title="Test", when="today")
        assert 'move newTodo to list "Today"' in captured[0]

    def test_when_evening_moves_to_evening_list(self):
        captured, capture = _capture_script()
        with patch('src.things_mcp.applescript_bridge.run_applescript', side_effect=capture):
            add_todo_direct(title="Test", when="evening")
        assert 'move newTodo to list "Evening"' in captured[0]

    def test_when_someday_moves_to_someday_list(self):
        captured, capture = _capture_script()
        with patch('src.things_mcp.applescript_bridge.run_applescript', side_effect=capture):
            add_todo_direct(title="Test", when="someday")
        assert 'move newTodo to list "Someday"' in captured[0]

    def test_when_date_uses_activation_date_not_schedule(self):
        captured, capture = _capture_script()
        with patch('src.things_mcp.applescript_bridge.run_applescript', side_effect=capture):
            add_todo_direct(title="Test", when="2026-04-10")
        assert 'set activation date of newTodo to newDate' in captured[0]
        assert 'move newTodo to list "Upcoming"' in captured[0]
        assert 'schedule' not in captured[0]

    def test_checklist_items_uses_tell_block(self):
        captured, capture = _capture_script()
        with patch('src.things_mcp.applescript_bridge.run_applescript', side_effect=capture):
            add_todo_direct(title="Test", checklist_items=["Step 1", "Step 2"])
        # Must use tell block, not tell-to single-line form
        assert 'tell newTodo' in captured[0]
        assert 'end tell' in captured[0]
        assert 'make new check list item at end with properties {name:"Step 1"}' in captured[0]
        assert 'make new check list item at end with properties {name:"Step 2"}' in captured[0]

    def test_tags_uses_set_tag_names(self):
        captured, capture = _capture_script()
        with patch('src.things_mcp.applescript_bridge.run_applescript', side_effect=capture):
            add_todo_direct(title="Test", tags=["KYNALITH", "P0"])
        assert 'set tag names of newTodo to "KYNALITH,P0"' in captured[0]

    def test_all_params_together(self):
        """Integration test: all parameters combined must produce valid structure."""
        captured, capture = _capture_script()
        with patch('src.things_mcp.applescript_bridge.run_applescript', side_effect=capture):
            add_todo_direct(
                title="Full test",
                notes="Some notes",
                when="today",
                tags=["TAG1", "TAG2"],
                checklist_items=["Item A", "Item B"],
                list_title="My Project",
            )
        script = captured[0]
        assert 'make new to do with properties' in script
        assert 'move newTodo to list "Today"' in script
        assert 'set tag names of newTodo to "TAG1,TAG2"' in script
        assert 'tell newTodo' in script
        assert 'make new check list item at end' in script
        assert 'set project_name to "My Project"' in script


class TestUpdateTodoDirect:
    """Tests for update_todo_direct — verifies generated AppleScript structure."""

    def test_returns_true_on_success(self):
        with patch('src.things_mcp.applescript_bridge.run_applescript', return_value="true"):
            result = update_todo_direct(todo_id="test-uuid", title="New Title")
            assert result is True

    def test_returns_false_on_failure(self):
        with patch('src.things_mcp.applescript_bridge.run_applescript', return_value="false"):
            result = update_todo_direct(todo_id="test-uuid", title="New Title")
            assert result is False

    def test_checklist_items_uses_tell_block(self):
        captured, capture = _capture_script(return_value="true")
        with patch('src.things_mcp.applescript_bridge.run_applescript', side_effect=capture):
            update_todo_direct(todo_id="test-uuid", checklist_items=["Step 1"])
        script = captured[0]
        assert 'tell theTodo' in script
        assert 'end tell' in script
        assert 'make new check list item at end with properties {name:"Step 1"}' in script

    def test_add_tags_uses_list_matching_not_substring(self):
        """add_tags must split into a list for exact matching, not substring."""
        captured, capture = _capture_script(return_value="true")
        with patch('src.things_mcp.applescript_bridge.run_applescript', side_effect=capture):
            update_todo_direct(todo_id="test-uuid", add_tags=["KYNALITH"])
        script = captured[0]
        # Must split tags into a list before checking containment
        assert 'text item delimiters' in script
        assert 'text items of currentTagNames' in script
        assert 'tagList does not contain "KYNALITH"' in script

    def test_when_today_moves_to_today_list(self):
        captured, capture = _capture_script(return_value="true")
        with patch('src.things_mcp.applescript_bridge.run_applescript', side_effect=capture):
            update_todo_direct(todo_id="test-uuid", when="today")
        assert 'move theTodo to list "Today"' in captured[0]


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
        captured, capture = _capture_script()
        with patch('src.things_mcp.applescript_bridge.run_applescript', side_effect=capture):
            add_project_direct(title="Proj", notes="Some notes")
        assert 'notes:"Some notes"' in captured[0]

    def test_creates_todos_in_project(self):
        captured, capture = _capture_script()
        with patch('src.things_mcp.applescript_bridge.run_applescript', side_effect=capture):
            add_project_direct(title="Proj", todos=["Task 1", "Task 2"])
        assert 'make new to do' in captured[0]
        assert 'Task 1' in captured[0]
        assert 'Task 2' in captured[0]

    def test_assigns_to_area(self):
        captured, capture = _capture_script()
        with patch('src.things_mcp.applescript_bridge.run_applescript', side_effect=capture):
            add_project_direct(title="Proj", area_title="Work")
        assert 'area' in captured[0].lower()
        assert 'Work' in captured[0]

    def test_wraps_in_try_on_error(self):
        captured, capture = _capture_script()
        with patch('src.things_mcp.applescript_bridge.run_applescript', side_effect=capture):
            add_project_direct(title="Test")
        assert 'try' in captured[0]
        assert 'on error errMsg' in captured[0]

    def test_when_today_moves_to_today_list(self):
        captured, capture = _capture_script()
        with patch('src.things_mcp.applescript_bridge.run_applescript', side_effect=capture):
            add_project_direct(title="Test", when="today")
        assert 'move newProject to list "Today"' in captured[0]

    def test_when_date_uses_activation_date_not_schedule(self):
        captured, capture = _capture_script()
        with patch('src.things_mcp.applescript_bridge.run_applescript', side_effect=capture):
            add_project_direct(title="Test", when="2026-04-10")
        assert 'set activation date of newProject to newDate' in captured[0]
        assert 'schedule' not in captured[0]

    def test_todos_uses_tell_block(self):
        """Todos should use tell block form, not tell-to single-line."""
        captured, capture = _capture_script()
        with patch('src.things_mcp.applescript_bridge.run_applescript', side_effect=capture):
            add_project_direct(title="Test", todos=["Item 1"])
        assert 'tell newProject' in captured[0]


class TestUpdateProjectDirect:
    def test_returns_true_on_success(self):
        with patch('src.things_mcp.applescript_bridge.run_applescript', return_value="true"):
            result = update_project_direct(project_id="proj-uuid", title="New Title")
            assert result is True

    def test_returns_false_on_failure(self):
        with patch('src.things_mcp.applescript_bridge.run_applescript', return_value="false"):
            result = update_project_direct(project_id="proj-uuid", completed=True)
            assert result is False

    def test_uses_project_class_not_todo(self):
        captured, capture = _capture_script(return_value="true")
        with patch('src.things_mcp.applescript_bridge.run_applescript', side_effect=capture):
            update_project_direct(project_id="proj-uuid", title="Updated")
        assert 'project id' in captured[0]
        assert 'to do id' not in captured[0]

    def test_completion_sets_status(self):
        captured, capture = _capture_script(return_value="true")
        with patch('src.things_mcp.applescript_bridge.run_applescript', side_effect=capture):
            update_project_direct(project_id="proj-uuid", completed=True)
        assert 'set status of theProject to completed' in captured[0]
