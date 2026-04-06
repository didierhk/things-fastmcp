#!/usr/bin/env python3
import subprocess
import logging
from typing import Optional, List, Dict, Any, Union

logger = logging.getLogger(__name__)

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

def add_todo_direct(title: str, notes: Optional[str] = None, when: Optional[str] = None,
                   deadline: Optional[str] = None, tags: Optional[List[str]] = None,
                   checklist_items: Optional[List[str]] = None,
                   list_title: Optional[str] = None,
                   heading: Optional[str] = None) -> str:
    """Add a todo to Things directly using AppleScript.

    This bypasses URL schemes entirely to avoid encoding issues.

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

    # Build the AppleScript command
    script_parts = ['tell application "Things3"']

    # Create the todo with properties
    properties = []
    properties.append(f'name:"{escape_applescript_string(title)}"')

    if notes:
        properties.append(f'notes:"{escape_applescript_string(notes)}"')

    # Create with properties in the right way
    script_parts.append(f'set newTodo to make new to do with properties {{{", ".join(properties)}}}')

    # Add scheduling
    if when:
        when_mapping = {
            'today': '',  # Default is today, no need to set
            'tomorrow': 'set activation date of newTodo to ((current date) + 1 * days)',
            'evening': '',  # Default is today, no need to set
            'anytime': '',  # Default
            'someday': 'move newTodo to list "Someday"'
        }

        if when in when_mapping:
            if when_mapping[when]:
                script_parts.append(when_mapping[when])
        elif re.match(r'^\d{4}-\d{2}-\d{2}$', when):
            # Handle YYYY-MM-DD format dates (component-based for locale safety)
            year, month, day = when.split('-')
            script_parts.append('set newDate to current date')
            script_parts.append(f'set year of newDate to {year}')
            script_parts.append(f'set month of newDate to {int(month)}')
            script_parts.append(f'set day of newDate to {int(day)}')
            script_parts.append('set hours of newDate to 0')
            script_parts.append('set minutes of newDate to 0')
            script_parts.append('set seconds of newDate to 0')
            script_parts.append('schedule newTodo for newDate')
        else:
            logger.warning(f"Custom date format '{when}' not supported, defaulting to today")

    # Add deadline if provided (component-based for locale safety)
    if deadline and re.match(r'^\d{4}-\d{2}-\d{2}$', deadline):
        y, m, d = deadline.split('-')
        script_parts.append('set deadlineDate to current date')
        script_parts.append(f'set year of deadlineDate to {y}')
        script_parts.append(f'set month of deadlineDate to {int(m)}')
        script_parts.append(f'set day of deadlineDate to {int(d)}')
        script_parts.append('set hours of deadlineDate to 0')
        script_parts.append('set minutes of deadlineDate to 0')
        script_parts.append('set seconds of deadlineDate to 0')
        script_parts.append('set due date of newTodo to deadlineDate')
    elif deadline:
        logger.warning(f"Invalid deadline format: {deadline}. Expected YYYY-MM-DD")

    # Add tags if provided
    if tags and len(tags) > 0:
        escaped_tags = ','.join(escape_applescript_string(t) for t in tags)
        script_parts.append(f'set tag names of newTodo to "{escaped_tags}"')

    # Add checklist items if provided
    if checklist_items:
        for item in checklist_items:
            script_parts.append(f'tell newTodo to make new check list item with properties {{name:"{escape_applescript_string(item)}"}}')

    # Add to a specific project/area if specified
    if list_title:
        script_parts.append(f'set project_name to "{escape_applescript_string(list_title)}"')
        script_parts.append('try')
        script_parts.append('  set target_project to first project whose name is project_name')
        script_parts.append('  set project of newTodo to target_project')
        # Place under heading if specified
        if heading:
            script_parts.append(f'  set heading_name to "{escape_applescript_string(heading)}"')
            script_parts.append('  try')
            script_parts.append('    set target_heading to first to do of target_project whose name is heading_name and status is open')
            script_parts.append('    move newTodo to before target_heading')
            script_parts.append('  on error')
            script_parts.append(f'    -- Heading "{escape_applescript_string(heading)}" not found in project, todo stays at project root')
            script_parts.append('  end try')
        script_parts.append('on error')
        script_parts.append('  -- Project not found, try area')
        script_parts.append('  try')
        script_parts.append('    set target_area to first area whose name is project_name')
        script_parts.append('    set area of newTodo to target_area')
        script_parts.append('  on error')
        script_parts.append('    -- Neither project nor area found, todo will remain in inbox')
        script_parts.append('  end try')
        script_parts.append('end try')
    elif heading:
        logger.warning(f"Heading '{heading}' specified without list_title — heading requires a project context")

    # Get the ID of the created todo
    script_parts.append('return id of newTodo')

    # Close the tell block
    script_parts.append('end tell')
    
    # Execute the script
    script = '\n'.join(script_parts)
    logger.debug(f"Executing AppleScript: {script}")
    
    result = run_applescript(script)
    if result:
        logger.info(f"Successfully created todo with ID: {result}")
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

    script_parts = ['tell application "Things3"']

    properties = [f'name:"{escape_applescript_string(title)}"']
    if notes:
        properties.append(f'notes:"{escape_applescript_string(notes)}"')

    script_parts.append(f'set newProject to make new project with properties {{{", ".join(properties)}}}')

    if when:
        when_mapping = {
            'today': '',
            'tomorrow': 'set activation date of newProject to ((current date) + 1 * days)',
            'evening': '',
            'anytime': '',
            'someday': 'move newProject to list "Someday"'
        }
        if when in when_mapping:
            if when_mapping[when]:
                script_parts.append(when_mapping[when])
        elif re.match(r'^\d{4}-\d{2}-\d{2}$', when):
            year, month, day = when.split('-')
            script_parts.append('set newDate to current date')
            script_parts.append(f'set year of newDate to {year}')
            script_parts.append(f'set month of newDate to {int(month)}')
            script_parts.append(f'set day of newDate to {int(day)}')
            script_parts.append('set hours of newDate to 0')
            script_parts.append('set minutes of newDate to 0')
            script_parts.append('set seconds of newDate to 0')
            script_parts.append('schedule newProject for newDate')
        else:
            logger.warning(f"Custom date format '{when}' not supported for project, defaulting to today")

    if deadline and re.match(r'^\d{4}-\d{2}-\d{2}$', deadline):
        y, m, d = deadline.split('-')
        script_parts.append('set deadlineDate to current date')
        script_parts.append(f'set year of deadlineDate to {y}')
        script_parts.append(f'set month of deadlineDate to {int(m)}')
        script_parts.append(f'set day of deadlineDate to {int(d)}')
        script_parts.append('set hours of deadlineDate to 0')
        script_parts.append('set minutes of deadlineDate to 0')
        script_parts.append('set seconds of deadlineDate to 0')
        script_parts.append('set due date of newProject to deadlineDate')

    if tags:
        escaped_tags = ','.join(escape_applescript_string(t) for t in tags)
        script_parts.append(f'set tag names of newProject to "{escaped_tags}"')

    if area_id:
        # area_id takes precedence over area_title
        escaped_id = escape_applescript_string(area_id)
        script_parts.append('try')
        script_parts.append(f'  set target_area to first area whose id is "{escaped_id}"')
        script_parts.append('  set area of newProject to target_area')
        script_parts.append('on error')
        script_parts.append(f'  -- Area with ID "{escaped_id}" not found')
        script_parts.append('end try')
    elif area_title:
        script_parts.append(f'set area_name to "{escape_applescript_string(area_title)}"')
        script_parts.append('try')
        script_parts.append('  set target_area to first area whose name is area_name')
        script_parts.append('  set area of newProject to target_area')
        script_parts.append('on error')
        script_parts.append('  -- Area not found, project will remain unassigned')
        script_parts.append('end try')

    if todos:
        for todo_title in todos:
            script_parts.append(f'tell newProject to make new to do with properties {{name:"{escape_applescript_string(todo_title)}"}}')

    script_parts.append('return id of newProject')
    script_parts.append('end tell')

    script = '\n'.join(script_parts)
    logger.debug(f"Executing AppleScript: {script}")

    result = run_applescript(script)
    if result:
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
            year, month, day = when.split('-')
            script_parts.append('    set newDate to current date')
            script_parts.append(f'    set year of newDate to {year}')
            script_parts.append(f'    set month of newDate to {int(month)}')
            script_parts.append(f'    set day of newDate to {int(day)}')
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

        # Get current tags, merge with new ones, set atomically
        script_parts.append('    set currentTagNames to tag names of theTodo')
        for tag in add_tags:
            tag_name = escape_applescript_string(tag)
            script_parts.append(f'    if currentTagNames does not contain "{tag_name}" then')
            script_parts.append(f'        if currentTagNames is "" then')
            script_parts.append(f'            set currentTagNames to "{tag_name}"')
            script_parts.append(f'        else')
            script_parts.append(f'            set currentTagNames to currentTagNames & ",{tag_name}"')
            script_parts.append(f'        end if')
            script_parts.append(f'    end if')
        script_parts.append('    set tag names of theTodo to currentTagNames')
            
    # Handle checklist items - simplified approach
    if checklist_items is not None:
        # Convert string to list if needed
        if isinstance(checklist_items, str):
            checklist_items = checklist_items.split('\n')
            
        if checklist_items:
            # Clear existing checklist items then add new ones
            script_parts.append('    set oldItems to check list items of theTodo')
            script_parts.append('    repeat with i from (count of oldItems) to 1 by -1')
            script_parts.append('        delete item i of oldItems')
            script_parts.append('    end repeat')
            for item in checklist_items:
                script_parts.append(f'    tell theTodo to make new check list item with properties {{name:"{escape_applescript_string(item)}"}}')
    
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
        return True
    else:
        logger.error(f"AppleScript update_todo_direct failed: {result}")
        return False