#!/usr/bin/env python3
# 1.0.0
"""
Plan file parser - Extracts tasks from markdown implementation plans.
"""

import re


def parse_plan(content, default_executor="jules"):
    """Parse a markdown plan file into structured tasks.

    Args:
        content: The full markdown content of the plan file.
        default_executor: Default executor for tasks without an explicit one.

    Returns:
        list[dict]: Tasks with keys: number, title, executor, depends, body.
    """
    # Split on ### Task N: Title
    task_pattern = re.compile(r"^### Task (\d+):\s*(.+)$", re.MULTILINE)
    matches = list(task_pattern.finditer(content))

    tasks = []
    for i, match in enumerate(matches):
        number = int(match.group(1))
        title = match.group(2).strip()

        # Extract body: from after the heading to the next heading (or end)
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        body = content[start:end].strip()

        # Parse metadata from body
        executor = _extract_field(body, "executor", default_executor)
        depends = _extract_depends(body, number)

        # Remove metadata lines from body for clean task text
        clean_body = _remove_metadata(body)

        tasks.append({
            "number": number,
            "title": title,
            "executor": executor,
            "depends": depends,
            "body": clean_body,
        })

    return tasks


def _extract_field(body, field_name, default):
    """Extract a metadata field value from task body."""
    pattern = re.compile(rf"^-\s*{field_name}:\s*(.+)$", re.MULTILINE | re.IGNORECASE)
    match = pattern.search(body)
    if match:
        return match.group(1).strip()
    return default


def _extract_depends(body, task_number):
    """Extract dependency list from task body."""
    raw = _extract_field(body, "depends", None)
    if raw is None:
        # Default: depend on previous task (except task 1)
        return [task_number - 1] if task_number > 1 else []
    if raw.lower() == "none":
        return []
    # Parse [1, 2, 3] format
    nums = re.findall(r"\d+", raw)
    return [int(n) for n in nums]


def _remove_metadata(body):
    """Remove metadata lines (- key: value) from the start of the body.

    Keeps Description lines (task description) but removes configuration
    metadata like executor and depends.
    """
    lines = body.split("\n")
    result = []
    in_metadata = True

    # Metadata keys to remove (lowercase for comparison)
    remove_keys = {"executor", "depends"}

    for line in lines:
        if in_metadata and line.startswith("- "):
            # Extract the key (text after "- " and before ":")
            if ":" in line:
                key_part = line[2:].split(":")[0].strip().lower()
                if key_part in remove_keys:
                    continue
        in_metadata = False
        result.append(line)

    return "\n".join(result).strip()
