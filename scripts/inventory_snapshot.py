#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""UserPromptSubmit hook entry point.

Snapshots skill inventory on each conversation start, diffs against
the previous snapshot, and logs skill_added/skill_removed lifecycle
events. Also diffs nested files per skill.
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


def main() -> None:
    """UserPromptSubmit hook entry point."""
    try:
        raw = sys.stdin.read()
        data = json.loads(raw)
    except Exception:
        print("{}")
        return

    try:
        cwd = data.get("cwd", "")
        now = datetime.now(timezone.utc).isoformat()

        conn = db.get_connection()
        db.init_schema(conn)

        # Discover current skills
        current_skills = skill_discovery.discover_all(project_dir=cwd)

        # Build current snapshot for comparison
        current_set = {
            (s["name"], s["source"], s["scope"]): s for s in current_skills
        }
        current_snapshot = [
            {"name": s["name"], "source": s["source"], "scope": s["scope"], "path": s["path"]}
            for s in current_skills
        ]

        # Load previous snapshot
        prev_snapshot = db.get_latest_snapshot(conn)
        if prev_snapshot is None:
            prev_set = {}
        else:
            prev_set = {
                (s["name"], s["source"], s["scope"]): s for s in prev_snapshot
            }

        # Diff skills: detect added and removed
        prev_keys = set(prev_set.keys())
        current_keys = set(current_set.keys())

        for key in current_keys - prev_keys:
            skill = current_set[key]
            db.insert_lifecycle_event(conn, {
                "timestamp": now,
                "event_type": "skill_added",
                "skill_name": skill["name"],
                "source": skill["source"],
                "scope": skill["scope"],
                "skill_path": skill["path"],
            })

        for key in prev_keys - current_keys:
            skill = prev_set[key]
            db.insert_lifecycle_event(conn, {
                "timestamp": now,
                "event_type": "skill_removed",
                "skill_name": skill["name"],
                "source": skill["source"],
                "scope": skill["scope"],
                "skill_path": skill["path"],
            })
            db.mark_skill_removed(conn, skill["name"], skill["source"], skill["scope"], now)

        # Upsert skills and diff nested files
        for key, skill in current_set.items():
            skill_id = db.upsert_skill(conn, {
                "name": skill["name"],
                "source": skill["source"],
                "scope": skill["scope"],
                "path": skill["path"],
                "total_nested_files": len(skill.get("nested_files", [])),
            })

            # Diff nested files
            existing_files = db.get_skill_files(conn, skill_id)
            existing_paths = {
                f["relative_path"]: f for f in existing_files
                if f["removed_at"] is None
            }
            current_nested = set(skill.get("nested_files", []))

            # New files
            for rel_path in current_nested - set(existing_paths.keys()):
                ft = skill.get("file_types", {}).get(rel_path, "asset")
                hier = skill.get("hierarchies", {}).get(rel_path, "content")
                db.upsert_skill_file(conn, skill_id, rel_path, ft, hier, now)

            # Removed files
            for rel_path in set(existing_paths.keys()) - current_nested:
                db.mark_skill_file_removed(conn, skill_id, rel_path, now)

        # Save snapshot
        db.save_snapshot(conn, now, current_snapshot)

        conn.close()
    except Exception as e:
        print(str(e), file=sys.stderr)

    print("{}")


if __name__ == "__main__":
    main()
