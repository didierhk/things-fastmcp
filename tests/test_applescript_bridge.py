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

    def test_returns_false_when_applescript_returns_false_string(self):
        """AppleScript 'on error' returns boolean false, which osascript outputs as string 'false'."""
        with patch('src.things_mcp.applescript_bridge.run_applescript', return_value="false"):
            result = add_todo_direct(title="Test Todo")
            assert result is False

    def test_two_phase_no_outer_try_on_error(self):
        """Two-phase approach: creation is unprotected, post-creation uses try blocks."""
        captured, capture = _capture_script()
        with patch('src.things_mcp.applescript_bridge.run_applescript', side_effect=capture):
            add_todo_direct(title="Test", when="today", tags=["T1"])
        script = captured[0]
        # Should NOT have an outer on error that returns false
        assert 'return false' not in script
        # Should capture ID right after creation
        assert 'set todoId to id of newTodo' in script
        assert 'return todoId' in script
        # Post-creation operations wrapped in individual try blocks
        lines = script.split('\n')
        try_count = sum(1 for l in lines if l.strip() == 'try')
        assert try_count >= 2  # scheduling + tags at minimum

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

    def test_when_date_sets_day_to_1_first(self):
        """Date components must set day=1 before month to avoid invalid intermediate dates."""
        captured, capture = _capture_script()
        with patch('src.things_mcp.applescript_bridge.run_applescript', side_effect=capture):
            add_todo_direct(title="Test", when="2026-02-15")
        script = captured[0]
        # day=1 must come before month setting
        day1_pos = script.index('set day of newDate to 1')
        month_pos = script.index('set month of newDate to 2')
        day_pos = script.index('set day of newDate to 15')
        assert day1_pos < month_pos < day_pos

    def test_checklist_items_appended_via_url_scheme(self):
        """Checklist items are appended via URL scheme after AppleScript creation."""
        calls = []
        def mock_applescript(script, **kwargs):
            calls.append(script)
            if 'make new to do' in script:
                return "FAKE-ID-123"
            return ""
        with patch('src.things_mcp.applescript_bridge.run_applescript', side_effect=mock_applescript):
            with patch('src.things_mcp.applescript_bridge._get_things_auth_token', return_value="FAKE-TOKEN"):
                result = add_todo_direct(title="Test", checklist_items=["Step 1", "Step 2"])
        assert result == "FAKE-ID-123"
        # First call: AppleScript creates the todo
        assert 'make new to do' in calls[0]
        assert 'check list item' not in calls[0]
        # Second call: URL scheme appends checklist items with auth token
        assert 'open location' in calls[1]
        assert 'append-checklist-items' in calls[1]
        assert 'auth-token=FAKE-TOKEN' in calls[1]
        assert 'Step%201' in calls[1]

    def test_tags_uses_set_tag_names(self):
        captured, capture = _capture_script()
        with patch('src.things_mcp.applescript_bridge.run_applescript', side_effect=capture):
            add_todo_direct(title="Test", tags=["KYNALITH", "P0"])
        assert 'set tag names of newTodo to "KYNALITH,P0"' in captured[0]

    def test_all_params_with_checklist(self):
        """All params including checklist: AppleScript handles properties, URL scheme handles checklist."""
        calls = []
        def mock_applescript(script, **kwargs):
            calls.append(script)
            if 'make new to do' in script:
                return "FAKE-ID-123"
            return ""
        with patch('src.things_mcp.applescript_bridge.run_applescript', side_effect=mock_applescript):
            with patch('src.things_mcp.applescript_bridge._get_things_auth_token', return_value="FAKE-TOKEN"):
                result = add_todo_direct(
                    title="Full test",
                    notes="Some notes",
                    when="today",
                    tags=["TAG1", "TAG2"],
                    checklist_items=["Item A", "Item B"],
                    list_title="My Project",
                )
        assert result == "FAKE-ID-123"
        # AppleScript handles all properties
        assert 'make new to do with properties' in calls[0]
        assert 'move newTodo to list "Today"' in calls[0]
        assert 'set tag names' in calls[0]
        assert 'set project_name to "My Project"' in calls[0]
        # URL scheme only handles checklist items
        assert 'append-checklist-items' in calls[1]

    def test_all_params_without_checklist_uses_applescript(self):
        """Without checklist_items, creation uses AppleScript."""
        captured, capture = _capture_script()
        with patch('src.things_mcp.applescript_bridge.run_applescript', side_effect=capture):
            add_todo_direct(
                title="Full test",
                notes="Some notes",
                when="today",
                tags=["TAG1", "TAG2"],
                list_title="My Project",
            )
        script = captured[0]
        assert 'make new to do with properties' in script
        assert 'move newTodo to list "Today"' in script
        assert 'set tag names of newTodo to "TAG1,TAG2"' in script
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

    def test_checklist_items_uses_url_scheme_with_auth(self):
        """Checklist items in update use URL scheme with auth token."""
        calls = []
        def mock_applescript(script, **kwargs):
            calls.append(script)
            if 'set theTodo' in script:
                return "true"
            return ""
        with patch('src.things_mcp.applescript_bridge.run_applescript', side_effect=mock_applescript):
            with patch('src.things_mcp.applescript_bridge._get_things_auth_token', return_value="FAKE-TOKEN"):
                update_todo_direct(todo_id="test-uuid", checklist_items=["Step 1"])
        assert 'check list item' not in calls[0]
        assert len(calls) == 2
        assert 'open location' in calls[1]
        assert 'checklist-items' in calls[1]
        assert 'auth-token=FAKE-TOKEN' in calls[1]

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

    def test_returns_false_when_applescript_returns_false_string(self):
        with patch('src.things_mcp.applescript_bridge.run_applescript', return_value="false"):
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

    def test_two_phase_captures_id_before_post_creation(self):
        """Two-phase: creation captures ID, post-creation wrapped in try blocks."""
        captured, capture = _capture_script()
        with patch('src.things_mcp.applescript_bridge.run_applescript', side_effect=capture):
            add_project_direct(title="Test", when="today", tags=["T1"])
        script = captured[0]
        assert 'set projectId to id of newProject' in script
        assert 'return projectId' in script
        assert 'return false' not in script
        # Post-creation ops should have try blocks
        assert 'try' in script

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
