#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""PreToolUse hook entry point.

Reads JSON from stdin, logs skill invocations and nested file accesses,
writes allow response to stdout. Never blocks Claude Code.
"""

import json
import os
import sys
from datetime import datetime, timezone

# Ensure project root is in sys.path for imports
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from scripts import db
from scripts import skill_discovery

_ALLOW_RESPONSE = json.dumps({
    "hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "allow",
    }
})


def main() -> None:
    """PreToolUse hook entry point."""
    try:
        raw = sys.stdin.read()
        data = json.loads(raw)
    except Exception:
        print(_ALLOW_RESPONSE)
        return

    try:
        tool_name = data.get("tool_name", "")
        tool_input = data.get("tool_input", {})

        conn = db.get_connection()
        db.init_schema(conn)

        if tool_name == "Skill":
            _handle_skill_invocation(conn, data, tool_input)
        elif tool_name == "Read":
            _handle_file_read(conn, data, tool_input)

        conn.close()
    except Exception as e:
        print(str(e), file=sys.stderr)

    print(_ALLOW_RESPONSE)


def _handle_skill_invocation(conn, data, tool_input):
    """Log a skill invocation event."""
    db.insert_skill_invocation(conn, {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "session_id": data.get("session_id", ""),
        "skill_name": tool_input.get("skill", ""),
        "invocation_id": data.get("tool_use_id", ""),
        "source": "",
        "scope": "",
        "project_dir": data.get("cwd", ""),
        "args": tool_input.get("args", ""),
    })


def _handle_file_read(conn, data, tool_input):
    """Log a nested file access if the file is inside a skill directory."""
    file_path = tool_input.get("file_path", "")
    if not file_path:
        return

    all_skills = skill_discovery.discover_all(project_dir=data.get("cwd", ""))
    skill_paths = {s["path"]: s for s in all_skills}

    result = skill_discovery.resolve_skill_for_path(file_path, skill_paths=skill_paths)
    if result is None:
        return

    db.insert_file_access(conn, {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "session_id": data.get("session_id", ""),
        "skill_name": result["skill_name"],
        "file_path": file_path,
        "relative_path": result["relative_path"],
        "file_type": result["file_type"],
        "hierarchy": result["hierarchy"],
        "project_dir": data.get("cwd", ""),
    })


if __name__ == "__main__":
    main()
