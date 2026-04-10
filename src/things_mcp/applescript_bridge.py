#!/usr/bin/env python3
import subprocess
import logging
import sqlite3
import glob
import os
from typing import Optional, List, Union

logger = logging.getLogger(__name__)


def _get_things_auth_token() -> Optional[str]:
    """Read the URL scheme auth token from Things3's database.

    Required for things:///update operations. Returns None if unavailable.
    """
    pattern = os.path.expanduser(
        "~/Library/Group Containers/JLMPQHK86H.com.culturedcode.ThingsMac/*/Things Database.thingsdatabase/main.sqlite"
    )
    db_paths = glob.glob(pattern)
    if not db_paths:
        logger.warning("Things3 database not found")
        return None
    try:
        conn = sqlite3.connect(db_paths[0])
        row = conn.execute("SELECT uriSchemeAuthenticationToken FROM TMSettings").fetchone()
        conn.close()
        if row and row[0]:
            return row[0]
    except Exception as e:
        logger.warning(f"Failed to read Things auth token: {e}")
    return None


def _sanitize_tags(tags: List[str]) -> List[str]:
    """Validate and sanitize tag names before passing to AppleScript.

    Rejects empty strings and strips commas (the `set tag names` delimiter).
    Logs warnings for any tags that are modified or dropped.
    """
    clean = []
    for tag in tags:
        tag = tag.strip()
        if not tag:
            logger.warning("Empty tag name dropped")
            continue
        if ',' in tag:
            logger.warning(f"Tag '{tag}' contains commas — commas stripped (Things3 uses comma as delimiter)")
            tag = tag.replace(',', '')
            if not tag:
                continue
        clean.append(tag)
    return clean


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

def _append_checklist_via_url_scheme(todo_id: str, items: List[str]) -> bool:
    """Append checklist items to an existing todo via Things URL scheme.

    Things3's AppleScript dictionary has no checklist item class, so this is the
    only way to add them programmatically. Requires auth-token from the database.
    """
    import urllib.parse

    auth_token = _get_things_auth_token()
    if not auth_token:
        logger.error("Cannot set checklist items: Things auth token not found")
        return False

    items_text = '\n'.join(items)
    encoded_items = urllib.parse.quote(items_text, safe='')
    url = f"things:///update?auth-token={auth_token}&id={todo_id}&append-checklist-items={encoded_items}"
    run_applescript(f'tell application "Things3" to open location "{url}"')
    logger.info(f"Appended {len(items)} checklist items to {todo_id} via URL scheme")
    return True


def add_todo_direct(title: str, notes: Optional[str] = None, when: Optional[str] = None,
                   deadline: Optional[str] = None, tags: Optional[List[str]] = None,
                   checklist_items: Optional[List[str]] = None,
                   list_title: Optional[str] = None,
                   heading: Optional[str] = None) -> Union[str, bool]:
    """Add a todo to Things using AppleScript.

    Checklist items (not supported by AppleScript) are appended via URL scheme
    after creation.

    Args:
        title: Title of the todo
        notes: Notes for the todo
        when: When to schedule the todo (today, tomorrow, evening, anytime, someday)
        deadline: Deadline in YYYY-MM-DD format
        tags: Tags to apply to the todo
        checklist_items: List of checklist item titles
        list_title: Name of project/area to add to
        heading: Name of heading within project to add under

    Returns:
        ID of the created todo if successful, False otherwise
    """
    import re

    # Build the AppleScript command — two-phase approach:
    # Phase 1 (unprotected): create todo + capture ID — if this fails, osascript
    #   exits with error and run_applescript returns False.
    # Phase 2 (each in try/end try): set schedule, deadline, tags, project —
    #   failures are logged but the ID is still returned.
    script_parts = ['tell application "Things3"']

    # Phase 1: Create the todo and capture its ID
    properties = []
    properties.append(f'name:"{escape_applescript_string(title)}"')

    if notes:
        properties.append(f'notes:"{escape_applescript_string(notes)}"')

    script_parts.append(f'    set newTodo to make new to do with properties {{{", ".join(properties)}}}')
    script_parts.append('    set todoId to id of newTodo')

    # Phase 2: Post-creation properties (best-effort)

    # Scheduling — wrapped in try so date failures don't lose the ID
    if when:
        when_lines = []
        if when == 'today':
            when_lines.append('move newTodo to list "Today"')
        elif when == 'tomorrow':
            when_lines.append('set activation date of newTodo to ((current date) + (1 * days))')
            when_lines.append('move newTodo to list "Upcoming"')
        elif when == 'evening':
            when_lines.append('move newTodo to list "Evening"')
        elif when == 'anytime':
            pass  # Default for new todos
        elif when == 'someday':
            when_lines.append('move newTodo to list "Someday"')
        elif re.match(r'^\d{4}-\d{2}-\d{2}$', when):
            year, month, day = when.split('-')
            # Set day to 1 first to avoid intermediate invalid dates
            # (e.g., current=Jan 31, set month=Feb → Feb 31 wraps to Mar 3)
            when_lines.extend([
                'set newDate to current date',
                'set day of newDate to 1',
                f'set year of newDate to {year}',
                f'set month of newDate to {int(month)}',
                f'set day of newDate to {int(day)}',
                'set hours of newDate to 0',
                'set minutes of newDate to 0',
                'set seconds of newDate to 0',
                'set activation date of newTodo to newDate',
                'move newTodo to list "Upcoming"',
            ])
        else:
            logger.warning(f"Schedule format '{when}' not supported, ignoring")

        if when_lines:
            script_parts.append('    try')
            for line in when_lines:
                script_parts.append(f'        {line}')
            script_parts.append('    end try')

    # Deadline (component-based for locale safety)
    if deadline:
        if re.match(r'^\d{4}-\d{2}-\d{2}$', deadline):
            y, m, d = deadline.split('-')
            script_parts.append('    try')
            script_parts.append('        set deadlineDate to current date')
            script_parts.append('        set day of deadlineDate to 1')
            script_parts.append(f'        set year of deadlineDate to {y}')
            script_parts.append(f'        set month of deadlineDate to {int(m)}')
            script_parts.append(f'        set day of deadlineDate to {int(d)}')
            script_parts.append('        set hours of deadlineDate to 0')
            script_parts.append('        set minutes of deadlineDate to 0')
            script_parts.append('        set seconds of deadlineDate to 0')
            script_parts.append('        set due date of newTodo to deadlineDate')
            script_parts.append('    end try')
        else:
            logger.warning(f"Invalid deadline format: {deadline}. Expected YYYY-MM-DD")

    # Tags
    if tags and len(tags) > 0:
        tags = _sanitize_tags(tags)
    if tags:
        escaped_tags = ','.join(escape_applescript_string(t) for t in tags)
        script_parts.append('    try')
        script_parts.append(f'        set tag names of newTodo to "{escaped_tags}"')
        script_parts.append('    end try')

    # Project/area assignment (already has its own try/on error)
    if list_title:
        script_parts.append('    try')
        script_parts.append(f'        set project_name to "{escape_applescript_string(list_title)}"')
        script_parts.append('        set target_project to first project whose name is project_name')
        script_parts.append('        set project of newTodo to target_project')
        if heading:
            script_parts.append('        try')
            script_parts.append(f'            set target_heading to first to do of target_project whose name is "{escape_applescript_string(heading)}" and status is open')
            script_parts.append('            move newTodo to before target_heading')
            script_parts.append('        end try')
        script_parts.append('    on error')
        script_parts.append('        try')
        script_parts.append(f'            set target_area to first area whose name is "{escape_applescript_string(list_title)}"')
        script_parts.append('            set area of newTodo to target_area')
        script_parts.append('        end try')
        script_parts.append('    end try')
    elif heading:
        logger.warning(f"Heading '{heading}' specified without list_title — heading requires a project context")

    script_parts.append('    return todoId')
    script_parts.append('end tell')

    # Execute the script
    script = '\n'.join(script_parts)
    logger.info(f"Executing AppleScript for add_todo_direct: \n{script}")
    
    result = run_applescript(script)
    if result and result != "false":
        logger.info(f"Successfully created todo with ID: {result}")
        if checklist_items:
            _append_checklist_via_url_scheme(result, checklist_items)
        return result
    else:
        logger.error("Failed to create todo")
        return False

def add_project_direct(title: str, notes: Optional[str] = None, when: Optional[str] = None,
                       deadline: Optional[str] = None, tags: Optional[List[str]] = None,
                       area_title: Optional[str] = None, area_id: Optional[str] = None,
                       todos: Optional[List[str]] = None) -> Union[str, bool]:
    """Create a project in Things directly using AppleScript.

    Args:
        title: Title of the project
        notes: Notes for the project
        when: When to schedule (today, tomorrow, evening, anytime, someday)
        deadline: Deadline in YYYY-MM-DD format
        tags: Tags to apply
        area_title: Name of area to add to
        area_id: UUID of area to add to (takes precedence over area_title)
        todos: Initial todo titles to create in the project

    Returns:
        ID of the created project if successful, False otherwise
    """
    import re

    # Two-phase: create + capture ID first, then best-effort properties
    script_parts = ['tell application "Things3"']

    # Phase 1: Create project and capture ID
    properties = [f'name:"{escape_applescript_string(title)}"']
    if notes:
        properties.append(f'notes:"{escape_applescript_string(notes)}"')

    script_parts.append(f'    set newProject to make new project with properties {{{", ".join(properties)}}}')
    script_parts.append('    set projectId to id of newProject')

    # Phase 2: Post-creation properties (best-effort)

    if when:
        when_lines = []
        if when == 'today':
            when_lines.append('move newProject to list "Today"')
        elif when == 'tomorrow':
            when_lines.append('set activation date of newProject to ((current date) + (1 * days))')
            when_lines.append('move newProject to list "Upcoming"')
        elif when == 'evening':
            when_lines.append('move newProject to list "Evening"')
        elif when == 'anytime':
            pass
        elif when == 'someday':
            when_lines.append('move newProject to list "Someday"')
        elif re.match(r'^\d{4}-\d{2}-\d{2}$', when):
            year, month, day = when.split('-')
            when_lines.extend([
                'set newDate to current date',
                'set day of newDate to 1',
                f'set year of newDate to {year}',
                f'set month of newDate to {int(month)}',
                f'set day of newDate to {int(day)}',
                'set hours of newDate to 0',
                'set minutes of newDate to 0',
                'set seconds of newDate to 0',
                'set activation date of newProject to newDate',
                'move newProject to list "Upcoming"',
            ])
        else:
            logger.warning(f"Schedule format '{when}' not supported for project, ignoring")

        if when_lines:
            script_parts.append('    try')
            for line in when_lines:
                script_parts.append(f'        {line}')
            script_parts.append('    end try')

    if deadline:
        if re.match(r'^\d{4}-\d{2}-\d{2}$', deadline):
            y, m, d = deadline.split('-')
            script_parts.append('    try')
            script_parts.append('        set deadlineDate to current date')
            script_parts.append('        set day of deadlineDate to 1')
            script_parts.append(f'        set year of deadlineDate to {y}')
            script_parts.append(f'        set month of deadlineDate to {int(m)}')
            script_parts.append(f'        set day of deadlineDate to {int(d)}')
            script_parts.append('        set hours of deadlineDate to 0')
            script_parts.append('        set minutes of deadlineDate to 0')
            script_parts.append('        set seconds of deadlineDate to 0')
            script_parts.append('        set due date of newProject to deadlineDate')
            script_parts.append('    end try')
        else:
            logger.warning(f"Invalid deadline format: {deadline}. Expected YYYY-MM-DD")

    if tags:
        tags = _sanitize_tags(tags)
    if tags:
        escaped_tags = ','.join(escape_applescript_string(t) for t in tags)
        script_parts.append('    try')
        script_parts.append(f'        set tag names of newProject to "{escaped_tags}"')
        script_parts.append('    end try')

    if area_id:
        escaped_id = escape_applescript_string(area_id)
        script_parts.append('    try')
        script_parts.append(f'        set target_area to first area whose id is "{escaped_id}"')
        script_parts.append('        set area of newProject to target_area')
        script_parts.append('    end try')
    elif area_title:
        script_parts.append('    try')
        script_parts.append(f'        set target_area to first area whose name is "{escape_applescript_string(area_title)}"')
        script_parts.append('        set area of newProject to target_area')
        script_parts.append('    end try')

    if todos:
        script_parts.append('    try')
        script_parts.append('        tell newProject')
        for todo_title in todos:
            script_parts.append(f'            make new to do with properties {{name:"{escape_applescript_string(todo_title)}"}}')
        script_parts.append('        end tell')
        script_parts.append('    end try')

    script_parts.append('    return projectId')
    script_parts.append('end tell')

    script = '\n'.join(script_parts)
    logger.info(f"Executing AppleScript for add_project_direct: \n{script}")

    result = run_applescript(script)
    if result and result != "false":
        logger.info(f"Successfully created project with ID: {result}")
        return result
    else:
        logger.error("Failed to create project")
        return False


def update_project_direct(project_id: str, title: Optional[str] = None, notes: Optional[str] = None,
                          when: Optional[str] = None, deadline: Optional[str] = None,
                          tags: Optional[List[str]] = None,
                          completed: Optional[bool] = None, canceled: Optional[bool] = None) -> bool:
    """Update a project directly using AppleScript.

    Args:
        project_id: The ID of the project to update
        title: New title
        notes: New notes
        when: New schedule (today, tomorrow, evening, anytime, someday, or YYYY-MM-DD)
        deadline: New deadline (YYYY-MM-DD)
        tags: New tags (replaces existing)
        completed: Mark as completed
        canceled: Mark as canceled

    Returns:
        True if successful, False otherwise
    """
    import re

    script_parts = ['tell application "Things3"']
    script_parts.append('try')
    script_parts.append(f'    set theProject to project id "{escape_applescript_string(project_id)}"')

    if title:
        script_parts.append(f'    set name of theProject to "{escape_applescript_string(title)}"')

    if notes:
        script_parts.append(f'    set notes of theProject to "{escape_applescript_string(notes)}"')

    if when:
        is_date_format = re.match(r'^\d{4}-\d{2}-\d{2}$', when)
        if when == 'today':
            script_parts.append('    move theProject to list "Today"')
        elif when == 'tomorrow':
            script_parts.append('    set activation date of theProject to ((current date) + (1 * days))')
            script_parts.append('    move theProject to list "Upcoming"')
        elif when == 'evening':
            script_parts.append('    move theProject to list "Evening"')
        elif when == 'anytime':
            script_parts.append('    move theProject to list "Anytime"')
        elif when == 'someday':
            script_parts.append('    move theProject to list "Someday"')
        elif is_date_format:
            year, month, day = when.split('-')
            script_parts.append('    set newDate to current date')
            script_parts.append('    set day of newDate to 1')
            script_parts.append(f'    set year of newDate to {year}')
            script_parts.append(f'    set month of newDate to {int(month)}')
            script_parts.append(f'    set day of newDate to {int(day)}')
            script_parts.append('    set hours of newDate to 0')
            script_parts.append('    set minutes of newDate to 0')
            script_parts.append('    set seconds of newDate to 0')
            script_parts.append('    set activation date of theProject to newDate')
            script_parts.append('    move theProject to list "Upcoming"')
        else:
            logger.warning(f"Schedule format '{when}' not supported for project update")

    if deadline:
        if re.match(r'^\d{4}-\d{2}-\d{2}$', deadline):
            y, m, d = deadline.split('-')
            script_parts.append('    set deadlineDate to current date')
            script_parts.append('    set day of deadlineDate to 1')
            script_parts.append(f'    set year of deadlineDate to {y}')
            script_parts.append(f'    set month of deadlineDate to {int(m)}')
            script_parts.append(f'    set day of deadlineDate to {int(d)}')
            script_parts.append('    set hours of deadlineDate to 0')
            script_parts.append('    set minutes of deadlineDate to 0')
            script_parts.append('    set seconds of deadlineDate to 0')
            script_parts.append('    set due date of theProject to deadlineDate')
        else:
            logger.warning(f"Invalid deadline format: {deadline}. Expected YYYY-MM-DD")

    if tags is not None:
        if isinstance(tags, str):
            tags = [tags]
        tags = _sanitize_tags(tags)
        if tags:
            escaped_tags = ','.join(escape_applescript_string(t) for t in tags)
            script_parts.append(f'    set tag names of theProject to "{escaped_tags}"')
        else:
            script_parts.append('    set tag names of theProject to ""')

    if completed is not None:
        if completed:
            script_parts.append('    set status of theProject to completed')
        else:
            script_parts.append('    set status of theProject to open')

    if canceled is not None:
        if canceled:
            script_parts.append('    set status of theProject to canceled')
        else:
            script_parts.append('    set status of theProject to open')

    script_parts.append('    return true')
    script_parts.append('on error errMsg')
    script_parts.append('    log "Error updating project: " & errMsg')
    script_parts.append('    return false')
    script_parts.append('end try')
    script_parts.append('end tell')

    script = '\n'.join(script_parts)
    logger.info(f"Executing AppleScript for update_project_direct: \n{script}")

    result = run_applescript(script)
    if result == "true":
        logger.info(f"Successfully updated project with ID: {project_id}")
        return True
    else:
        logger.error(f"AppleScript update_project_direct failed: {result}")
        return False


def escape_applescript_string(text: str) -> str:
    """Escape special characters in an AppleScript string.

    Handles: double quotes (AppleScript-style doubling), backslashes,
    and newlines/carriage returns (replaced with spaces to avoid splitting
    the generated AppleScript across lines).

    Args:
        text: The string to escape

    Returns:
        The escaped string
    """
    if not text:
        return ""

    # Order matters: backslashes first, then quotes, then newlines
    text = text.replace('\\', '\\\\')
    text = text.replace('"', '\\"')
    text = text.replace('\n', ' ')
    text = text.replace('\r', ' ')
    return text

def update_todo_direct(todo_id: str, title: Optional[str] = None, notes: Optional[str] = None,
                     when: Optional[str] = None, deadline: Optional[str] = None,
                     tags: Optional[Union[List[str], str]] = None, add_tags: Optional[Union[List[str], str]] = None,
                     checklist_items: Optional[List[str]] = None, completed: Optional[bool] = None,
                     canceled: Optional[bool] = None) -> bool:
    """Update a todo directly using AppleScript.

    This bypasses URL schemes entirely to avoid authentication issues.

    Args:
        todo_id: The ID of the todo to update
        title: New title for the todo
        notes: New notes for the todo
        when: New schedule for the todo (today, tomorrow, evening, anytime, someday, or YYYY-MM-DD)
        deadline: New deadline for the todo (YYYY-MM-DD)
        tags: New tags for the todo (replaces existing tags)
        add_tags: Tags to add to the todo (preserves existing tags)
        checklist_items: Checklist items to set for the todo (replaces existing items)
        completed: Mark as completed
        canceled: Mark as canceled
    
    Returns:
        True if successful, False otherwise
    """
    import re
    
    # Build the AppleScript command to find and update the todo
    script_parts = ['tell application "Things3"']
    script_parts.append('try')
    script_parts.append(f'    set theTodo to to do id "{escape_applescript_string(todo_id)}"')
    
    # Update properties one at a time
    if title:
        script_parts.append(f'    set name of theTodo to "{escape_applescript_string(title)}"')
    
    if notes:
        script_parts.append(f'    set notes of theTodo to "{escape_applescript_string(notes)}"')
    
    # Handle date-related properties
    if when:
        # Check if when is a date in YYYY-MM-DD format
        is_date_format = re.match(r'^\d{4}-\d{2}-\d{2}$', when)
        
        # Simple mapping of common 'when' values to AppleScript commands
        if when == 'today':
            script_parts.append('    move theTodo to list "Today"')
        elif when == 'tomorrow':
            script_parts.append('    set activation date of theTodo to ((current date) + (1 * days))')
            script_parts.append('    move theTodo to list "Upcoming"')
        elif when == 'evening':
            script_parts.append('    move theTodo to list "Evening"')
        elif when == 'anytime':
            script_parts.append('    move theTodo to list "Anytime"')
        elif when == 'someday':
            script_parts.append('    move theTodo to list "Someday"')
        elif is_date_format:
            # Handle YYYY-MM-DD format dates (component-based for locale safety)
            # Set day to 1 first to avoid intermediate invalid dates
            year, month, day = when.split('-')
            script_parts.append('    set newDate to current date')
            script_parts.append('    set day of newDate to 1')
            script_parts.append(f'    set year of newDate to {year}')
            script_parts.append(f'    set month of newDate to {int(month)}')
            script_parts.append(f'    set day of newDate to {int(day)}')
            script_parts.append('    set hours of newDate to 0')
            script_parts.append('    set minutes of newDate to 0')
            script_parts.append('    set seconds of newDate to 0')
            script_parts.append('    set activation date of theTodo to newDate')
            script_parts.append('    move theTodo to list "Upcoming"')
        else:
            # For other formats, just log a warning and don't try to set it
            logger.warning(f"Schedule format '{when}' not directly supported in this simplified version")
    
    if deadline:
        # Check if deadline is in YYYY-MM-DD format
        if re.match(r'^\d{4}-\d{2}-\d{2}$', deadline):
            y, m, d = deadline.split('-')
            script_parts.append('    set deadlineDate to current date')
            script_parts.append('    set day of deadlineDate to 1')
            script_parts.append(f'    set year of deadlineDate to {y}')
            script_parts.append(f'    set month of deadlineDate to {int(m)}')
            script_parts.append(f'    set day of deadlineDate to {int(d)}')
            script_parts.append('    set hours of deadlineDate to 0')
            script_parts.append('    set minutes of deadlineDate to 0')
            script_parts.append('    set seconds of deadlineDate to 0')
            script_parts.append('    set due date of theTodo to deadlineDate')
        else:
            logger.warning(f"Invalid deadline format: {deadline}. Expected YYYY-MM-DD")
    
    # Handle tags — use `set tag names` (atomic, reliable; `make new tag` silently fails)
    if tags is not None:
        # Convert string tags to list if needed
        if isinstance(tags, str):
            tags = [tags]
        tags = _sanitize_tags(tags)

        if tags:
            escaped_tags = ','.join(escape_applescript_string(t) for t in tags)
            script_parts.append(f'    set tag names of theTodo to "{escaped_tags}"')
        else:
            # Clear all tags if empty list provided
            script_parts.append('    set tag names of theTodo to ""')

    # Handle adding tags without replacing existing ones
    if add_tags is not None:
        # Convert string to list if needed
        if isinstance(add_tags, str):
            add_tags = [add_tags]
        add_tags = _sanitize_tags(add_tags)

        # Get current tags, merge with new ones, set atomically.
        # Split by comma into a list for exact tag-level matching
        # (string `contains` would match substrings: "P0" in "P0-urgent").
        script_parts.append('    set currentTagNames to tag names of theTodo')
        script_parts.append('    set AppleScript\'s text item delimiters to ","')
        script_parts.append('    set tagList to text items of currentTagNames')
        script_parts.append('    set AppleScript\'s text item delimiters to ""')
        for tag in add_tags:
            tag_name = escape_applescript_string(tag)
            script_parts.append(f'    if tagList does not contain "{tag_name}" then')
            script_parts.append(f'        if currentTagNames is "" then')
            script_parts.append(f'            set currentTagNames to "{tag_name}"')
            script_parts.append(f'        else')
            script_parts.append(f'            set currentTagNames to currentTagNames & ",{tag_name}"')
            script_parts.append(f'        end if')
            script_parts.append(f'        set end of tagList to "{tag_name}"')
            script_parts.append(f'    end if')
        script_parts.append('    set tag names of theTodo to currentTagNames')
            
    # Normalize checklist_items for post-AppleScript URL scheme call
    if checklist_items is not None and isinstance(checklist_items, str):
        checklist_items = checklist_items.split('\n')
    
    # Handle completion status - use completion date approach
    if completed is not None:
        if completed:
            script_parts.append('    set status of theTodo to completed')
        else:
            script_parts.append('    set status of theTodo to open')
    
    # Handle canceled status
    if canceled is not None:
        if canceled:
            script_parts.append('    set status of theTodo to canceled')
        else:
            script_parts.append('    set status of theTodo to open')
    
    # Return true on success
    script_parts.append('    return true')
    script_parts.append('on error errMsg')
    script_parts.append('    log "Error updating todo: " & errMsg')
    script_parts.append('    return false')
    script_parts.append('end try')
    script_parts.append('end tell')
    
    # Execute the script
    script = '\n'.join(script_parts)
    logger.info(f"Executing AppleScript for update_todo_direct: \n{script}")
    
    result = run_applescript(script)
    
    if result == "true":
        logger.info(f"Successfully updated todo with ID: {todo_id}")
        if checklist_items:
            _append_checklist_via_url_scheme(todo_id, checklist_items)
        return True
    else:
        logger.error(f"AppleScript update_todo_direct failed: {result}")
        return False