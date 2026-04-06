import logging
import things

logger = logging.getLogger(__name__)

# In-memory lookup caches for project/area names.
# Populated lazily on first miss, cleared by invalidate_name_caches().
# Eliminates N+1 queries: without this, every todo with a project/area
# ref triggers a things.get() call (~0.8ms each, 128 extra queries for
# a 268-todo vault).
_project_names: dict[str, str] = {}
_area_names: dict[str, str] = {}


def _get_project_name(uuid: str) -> str:
    """Resolve project UUID to title, caching the result."""
    if uuid not in _project_names:
        try:
            project = things.get(uuid)
            _project_names[uuid] = project['title'] if project else ''
        except Exception:
            _project_names[uuid] = ''
    return _project_names[uuid]


def _get_area_name(uuid: str) -> str:
    """Resolve area UUID to title, caching the result."""
    if uuid not in _area_names:
        try:
            area = things.get(uuid)
            _area_names[uuid] = area['title'] if area else ''
        except Exception:
            _area_names[uuid] = ''
    return _area_names[uuid]


def invalidate_name_caches() -> None:
    """Clear project/area name caches (call after writes)."""
    _project_names.clear()
    _area_names.clear()


def format_todo(todo: dict) -> str:
    """Helper function to format a single todo into a readable string."""
    logger.debug(f"Formatting todo: {todo}")
    todo_text = f"Title: {todo['title']}"

    # Add UUID for reference
    todo_text += f"\nUUID: {todo['uuid']}"

    # Add type
    todo_text += f"\nType: {todo['type']}"

    # Add status if present
    if todo.get('status'):
        todo_text += f"\nStatus: {todo['status']}"

    # Add start/list location
    if todo.get('start'):
        todo_text += f"\nList: {todo['start']}"

    # Add dates
    if todo.get('start_date'):
        todo_text += f"\nStart Date: {todo['start_date']}"
    if todo.get('deadline'):
        todo_text += f"\nDeadline: {todo['deadline']}"
    if todo.get('stop_date'):  # Completion date
        todo_text += f"\nCompleted: {todo['stop_date']}"

    # Add notes if present
    if todo.get('notes'):
        todo_text += f"\nNotes: {todo['notes']}"

    # Add project info if present (cached lookup)
    if todo.get('project'):
        name = _get_project_name(todo['project'])
        if name:
            todo_text += f"\nProject: {name}"

    # Add area info if present (cached lookup)
    if todo.get('area'):
        name = _get_area_name(todo['area'])
        if name:
            todo_text += f"\nArea: {name}"

    # Add tags if present
    if todo.get('tags'):
        todo_text += f"\nTags: {', '.join(todo['tags'])}"

    # Add checklist if present and contains items
    if isinstance(todo.get('checklist'), list):
        todo_text += "\nChecklist:"
        for item in todo['checklist']:
            status = "✓" if item['status'] == 'completed' else "□"
            todo_text += f"\n  {status} {item['title']}"

    return todo_text

def format_project(project: dict, include_items: bool = False) -> str:
    """Helper function to format a single project."""
    project_text = f"Title: {project['title']}\nUUID: {project['uuid']}"
    
    if project.get('area'):
        try:
            area = things.get(project['area'])
            if area:
                project_text += f"\nArea: {area['title']}"
        except Exception:
            pass
            
    if project.get('notes'):
        project_text += f"\nNotes: {project['notes']}"
        
    if include_items:
        todos = things.todos(project=project['uuid'])
        if todos:
            project_text += "\n\nTasks:"
            for todo in todos:
                project_text += f"\n- {todo['title']}"
    
    return project_text

def format_area(area: dict, include_items: bool = False) -> str:
    """Helper function to format a single area."""
    area_text = f"Title: {area['title']}\nUUID: {area['uuid']}"
    
    if area.get('notes'):
        area_text += f"\nNotes: {area['notes']}"
        
    if include_items:
        projects = things.projects(area=area['uuid'])
        if projects:
            area_text += "\n\nProjects:"
            for project in projects:
                area_text += f"\n- {project['title']}"
                
        todos = things.todos(area=area['uuid'])
        if todos:
            area_text += "\n\nTasks:"
            for todo in todos:
                area_text += f"\n- {todo['title']}"
    
    return area_text

def format_tag(tag: dict, include_items: bool = False) -> str:
    """Helper function to format a single tag."""
    tag_text = f"Title: {tag['title']}\nUUID: {tag['uuid']}"
    
    if tag.get('shortcut'):
        tag_text += f"\nShortcut: {tag['shortcut']}"
        
    if include_items:
        todos = things.todos(tag=tag['title'])
        if todos:
            tag_text += "\n\nTagged Items:"
            for todo in todos:
                tag_text += f"\n- {todo['title']}"
    
    return tag_text