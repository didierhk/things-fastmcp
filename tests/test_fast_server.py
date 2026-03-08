from unittest.mock import patch, MagicMock


class TestUpdateTodo:
    def test_calls_applescript_bridge_not_url_scheme(self):
        with patch('src.things_mcp.fast_server.update_todo_direct', return_value=True) as mock_as, \
             patch('src.things_mcp.fast_server.invalidate_caches_for'):
            from src.things_mcp.fast_server import update_task
            result = update_task(id="some-uuid", completed=True)
            assert mock_as.called
            assert "Successfully" in result

    def test_returns_error_on_failure(self):
        with patch('src.things_mcp.fast_server.update_todo_direct', return_value=False), \
             patch('src.things_mcp.fast_server.invalidate_caches_for'):
            from src.things_mcp.fast_server import update_task
            result = update_task(id="bad-uuid", completed=True)
            assert "Error" in result


class TestAddTodo:
    def test_calls_applescript_bridge_not_url_scheme(self):
        with patch('src.things_mcp.fast_server.add_todo_direct', return_value="new-uuid-123") as mock_as, \
             patch('src.things_mcp.fast_server.invalidate_caches_for'):
            from src.things_mcp.fast_server import add_task
            result = add_task(title="Test todo")
            assert mock_as.called
            assert "Successfully" in result
            assert "new-uuid-123" in result

    def test_returns_error_when_creation_fails(self):
        with patch('src.things_mcp.fast_server.add_todo_direct', return_value=False), \
             patch('src.things_mcp.fast_server.invalidate_caches_for'):
            from src.things_mcp.fast_server import add_task
            result = add_task(title="Test todo")
            assert "Error" in result


class TestAddProject:
    def test_calls_applescript_bridge(self):
        with patch('src.things_mcp.fast_server.add_project_direct', return_value="proj-uuid") as mock_as, \
             patch('src.things_mcp.fast_server.invalidate_caches_for'):
            from src.things_mcp.fast_server import add_new_project
            result = add_new_project(title="Test Project")
            assert mock_as.called
            assert "Successfully" in result
            assert "proj-uuid" in result

    def test_returns_error_on_failure(self):
        with patch('src.things_mcp.fast_server.add_project_direct', return_value=False), \
             patch('src.things_mcp.fast_server.invalidate_caches_for'):
            from src.things_mcp.fast_server import add_new_project
            result = add_new_project(title="Test Project")
            assert "Error" in result


class TestUpdateProject:
    def test_calls_applescript_bridge(self):
        with patch('src.things_mcp.fast_server.update_project_direct', return_value=True) as mock_as, \
             patch('src.things_mcp.fast_server.invalidate_caches_for'):
            from src.things_mcp.fast_server import update_existing_project
            result = update_existing_project(id="proj-uuid", completed=True)
            assert mock_as.called
            assert "Successfully" in result

    def test_returns_error_on_failure(self):
        with patch('src.things_mcp.fast_server.update_project_direct', return_value=False), \
             patch('src.things_mcp.fast_server.invalidate_caches_for'):
            from src.things_mcp.fast_server import update_existing_project
            result = update_existing_project(id="proj-uuid", completed=True)
            assert "Error" in result
