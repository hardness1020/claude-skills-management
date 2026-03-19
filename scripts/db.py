"""Database module for skills analytics.

Provides SQLite connection management, schema initialization,
and CRUD operations for skill invocations, file accesses,
lifecycle events, and inventory snapshots.
"""

import json
import os
import sqlite3

_SCHEMA = """
CREATE TABLE IF NOT EXISTS skills (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    source TEXT NOT NULL CHECK (source IN ('folder', 'plugin')),
    scope TEXT NOT NULL CHECK (scope IN ('user', 'project', 'local')),
    path TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'removed')),
    first_seen_at TEXT NOT NULL,
    removed_at TEXT,
    total_nested_files INTEGER DEFAULT 0,
    UNIQUE(name, source, scope)
);
CREATE INDEX IF NOT EXISTS idx_skills_name ON skills(name);
CREATE INDEX IF NOT EXISTS idx_skills_status ON skills(status);

CREATE TABLE IF NOT EXISTS skill_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    skill_id INTEGER NOT NULL REFERENCES skills(id),
    relative_path TEXT NOT NULL,
    file_type TEXT NOT NULL CHECK (file_type IN ('markdown', 'script', 'asset', 'reference', 'config')),
    hierarchy TEXT NOT NULL CHECK (hierarchy IN ('content', 'script')),
    first_seen_at TEXT NOT NULL,
    removed_at TEXT,
    UNIQUE(skill_id, relative_path)
);
CREATE INDEX IF NOT EXISTS idx_skill_files_skill ON skill_files(skill_id);

CREATE TABLE IF NOT EXISTS skill_invocations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    session_id TEXT NOT NULL,
    skill_name TEXT NOT NULL,
    invocation_id TEXT NOT NULL UNIQUE,
    source TEXT NOT NULL,
    scope TEXT NOT NULL,
    project_dir TEXT,
    args TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_invocations_timestamp ON skill_invocations(timestamp);
CREATE INDEX IF NOT EXISTS idx_invocations_skill ON skill_invocations(skill_name);
CREATE INDEX IF NOT EXISTS idx_invocations_session ON skill_invocations(session_id);

CREATE TABLE IF NOT EXISTS file_accesses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    session_id TEXT NOT NULL,
    skill_name TEXT NOT NULL,
    file_path TEXT NOT NULL,
    relative_path TEXT NOT NULL,
    file_type TEXT NOT NULL,
    hierarchy TEXT NOT NULL,
    project_dir TEXT
);
CREATE INDEX IF NOT EXISTS idx_accesses_timestamp ON file_accesses(timestamp);
CREATE INDEX IF NOT EXISTS idx_accesses_skill ON file_accesses(skill_name);

CREATE TABLE IF NOT EXISTS skill_lifecycle (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    event_type TEXT NOT NULL CHECK (event_type IN ('skill_added', 'skill_removed')),
    skill_name TEXT NOT NULL,
    source TEXT NOT NULL,
    scope TEXT NOT NULL,
    skill_path TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_lifecycle_timestamp ON skill_lifecycle(timestamp);
CREATE INDEX IF NOT EXISTS idx_lifecycle_skill ON skill_lifecycle(skill_name);

CREATE TABLE IF NOT EXISTS inventory_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    snapshot_json TEXT NOT NULL
);
"""


def get_connection(db_path: str = None) -> sqlite3.Connection:
    """Get a SQLite connection with WAL mode enabled."""
    if db_path is None:
        plugin_data = os.environ.get(
            "CLAUDE_PLUGIN_DATA",
            os.path.expanduser("~/.skills-analytics"),
        )
        os.makedirs(plugin_data, exist_ok=True)
        db_path = os.path.join(plugin_data, "skills_analytics.db")
    conn = sqlite3.connect(db_path, timeout=5)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    """Create all tables and indexes if they don't exist."""
    conn.executescript(_SCHEMA)
    conn.commit()


def insert_skill_invocation(conn: sqlite3.Connection, event: dict) -> None:
    """Insert a skill_invoked event into skill_invocations table."""
    conn.execute(
        """INSERT INTO skill_invocations
           (timestamp, session_id, skill_name, invocation_id, source, scope, project_dir, args)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            event["timestamp"], event["session_id"], event["skill_name"],
            event["invocation_id"], event["source"], event["scope"],
            event.get("project_dir", ""), event.get("args", ""),
        ),
    )
    conn.commit()


def insert_file_access(conn: sqlite3.Connection, event: dict) -> None:
    """Insert a nested_file_accessed event into file_accesses table."""
    conn.execute(
        """INSERT INTO file_accesses
           (timestamp, session_id, skill_name, file_path, relative_path, file_type, hierarchy, project_dir)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            event["timestamp"], event["session_id"], event["skill_name"],
            event["file_path"], event["relative_path"], event["file_type"],
            event["hierarchy"], event.get("project_dir", ""),
        ),
    )
    conn.commit()


def insert_lifecycle_event(conn: sqlite3.Connection, event: dict) -> None:
    """Insert a skill_added or skill_removed event."""
    conn.execute(
        """INSERT INTO skill_lifecycle
           (timestamp, event_type, skill_name, source, scope, skill_path)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            event["timestamp"], event["event_type"], event["skill_name"],
            event["source"], event["scope"], event["skill_path"],
        ),
    )
    conn.commit()


def upsert_skill(conn: sqlite3.Connection, skill_info: dict) -> int:
    """Insert or update a skill in the skills registry, return skill ID."""
    from datetime import datetime, timezone

    row = conn.execute(
        "SELECT id FROM skills WHERE name = ? AND source = ? AND scope = ?",
        (skill_info["name"], skill_info["source"], skill_info["scope"]),
    ).fetchone()

    if row:
        conn.execute(
            """UPDATE skills SET path = ?, total_nested_files = ?, status = 'active', removed_at = NULL
               WHERE id = ?""",
            (skill_info["path"], skill_info.get("total_nested_files", 0), row[0]),
        )
        conn.commit()
        return row[0]

    conn.execute(
        """INSERT INTO skills (name, source, scope, path, status, first_seen_at, total_nested_files)
           VALUES (?, ?, ?, ?, 'active', ?, ?)""",
        (
            skill_info["name"], skill_info["source"], skill_info["scope"],
            skill_info["path"],
            datetime.now(timezone.utc).isoformat(),
            skill_info.get("total_nested_files", 0),
        ),
    )
    conn.commit()
    return conn.execute(
        "SELECT id FROM skills WHERE name = ? AND source = ? AND scope = ?",
        (skill_info["name"], skill_info["source"], skill_info["scope"]),
    ).fetchone()[0]


def mark_skill_removed(
    conn: sqlite3.Connection,
    skill_name: str,
    source: str,
    scope: str,
    removed_at: str,
) -> None:
    """Set a skill's status to 'removed' with timestamp."""
    conn.execute(
        "UPDATE skills SET status = 'removed', removed_at = ? WHERE name = ? AND source = ? AND scope = ?",
        (removed_at, skill_name, source, scope),
    )
    conn.commit()


def upsert_skill_file(
    conn: sqlite3.Connection,
    skill_id: int,
    relative_path: str,
    file_type: str,
    hierarchy: str,
    first_seen_at: str,
) -> None:
    """Insert a nested file record or update if it already exists."""
    row = conn.execute(
        "SELECT id FROM skill_files WHERE skill_id = ? AND relative_path = ?",
        (skill_id, relative_path),
    ).fetchone()

    if row:
        conn.execute(
            "UPDATE skill_files SET file_type = ?, hierarchy = ?, removed_at = NULL WHERE id = ?",
            (file_type, hierarchy, row[0]),
        )
    else:
        conn.execute(
            """INSERT INTO skill_files (skill_id, relative_path, file_type, hierarchy, first_seen_at)
               VALUES (?, ?, ?, ?, ?)""",
            (skill_id, relative_path, file_type, hierarchy, first_seen_at),
        )
    conn.commit()


def mark_skill_file_removed(
    conn: sqlite3.Connection,
    skill_id: int,
    relative_path: str,
    removed_at: str,
) -> None:
    """Mark a nested file as removed with timestamp."""
    conn.execute(
        "UPDATE skill_files SET removed_at = ? WHERE skill_id = ? AND relative_path = ?",
        (removed_at, skill_id, relative_path),
    )
    conn.commit()


def get_skill_files(conn: sqlite3.Connection, skill_id: int) -> list[dict]:
    """Get all nested files for a skill (including removed ones)."""
    rows = conn.execute(
        "SELECT relative_path, file_type, hierarchy, first_seen_at, removed_at FROM skill_files WHERE skill_id = ?",
        (skill_id,),
    ).fetchall()
    return [
        {
            "relative_path": r[0],
            "file_type": r[1],
            "hierarchy": r[2],
            "first_seen_at": r[3],
            "removed_at": r[4],
        }
        for r in rows
    ]


def save_snapshot(
    conn: sqlite3.Connection, timestamp: str, snapshot: list[dict]
) -> None:
    """Save an inventory snapshot and prune old snapshots (keep latest 100)."""
    conn.execute(
        "INSERT INTO inventory_snapshots (timestamp, snapshot_json) VALUES (?, ?)",
        (timestamp, json.dumps(snapshot)),
    )
    conn.execute(
        """DELETE FROM inventory_snapshots WHERE id NOT IN (
            SELECT id FROM inventory_snapshots ORDER BY id DESC LIMIT 100
        )"""
    )
    conn.commit()


def get_latest_snapshot(conn: sqlite3.Connection) -> list[dict] | None:
    """Retrieve the most recent inventory snapshot."""
    row = conn.execute(
        "SELECT snapshot_json FROM inventory_snapshots ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if row is None:
        return None
    return json.loads(row[0])
