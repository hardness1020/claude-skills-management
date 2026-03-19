"""Unit tests for scripts/db.py."""

import sqlite3
import pytest

from scripts import db


@pytest.fixture
def conn(tmp_path):
    """Provide an initialized in-memory SQLite connection."""
    connection = db.get_connection(str(tmp_path / "test.db"))
    db.init_schema(connection)
    yield connection
    connection.close()


# --- get_connection ---

class TestGetConnection:
    @pytest.mark.unit
    def test_returns_sqlite_connection(self, tmp_path):
        result = db.get_connection(str(tmp_path / "test.db"))
        assert isinstance(result, sqlite3.Connection)
        result.close()

    @pytest.mark.unit
    def test_wal_mode_enabled(self, tmp_path):
        connection = db.get_connection(str(tmp_path / "test.db"))
        mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode == "wal"
        connection.close()

    @pytest.mark.unit
    def test_default_path_uses_env(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(tmp_path))
        connection = db.get_connection()
        assert isinstance(connection, sqlite3.Connection)
        connection.close()


# --- init_schema ---

class TestInitSchema:
    @pytest.mark.unit
    def test_creates_all_tables(self, conn):
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        table_names = {row[0] for row in tables}
        expected = {
            "skills", "skill_files", "skill_invocations",
            "file_accesses", "skill_lifecycle", "inventory_snapshots",
        }
        assert expected.issubset(table_names)

    @pytest.mark.unit
    def test_idempotent(self, conn):
        db.init_schema(conn)
        db.init_schema(conn)
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        assert len(tables) >= 6


# --- insert_skill_invocation ---

class TestInsertSkillInvocation:
    @pytest.mark.unit
    def test_inserts_row(self, conn):
        event = {
            "timestamp": "2026-03-18T10:00:00Z",
            "session_id": "sess-1",
            "skill_name": "commit",
            "invocation_id": "toolu_abc123",
            "source": "folder",
            "scope": "project",
            "project_dir": "/tmp/project",
            "args": "",
        }
        db.insert_skill_invocation(conn, event)
        row = conn.execute("SELECT * FROM skill_invocations").fetchone()
        assert row is not None

    @pytest.mark.unit
    def test_duplicate_invocation_id_rejected(self, conn):
        event = {
            "timestamp": "2026-03-18T10:00:00Z",
            "session_id": "sess-1",
            "skill_name": "commit",
            "invocation_id": "toolu_dup",
            "source": "folder",
            "scope": "project",
            "project_dir": "/tmp/project",
            "args": "",
        }
        db.insert_skill_invocation(conn, event)
        with pytest.raises(sqlite3.IntegrityError):
            db.insert_skill_invocation(conn, event)


# --- insert_file_access ---

class TestInsertFileAccess:
    @pytest.mark.unit
    def test_inserts_row(self, conn):
        event = {
            "timestamp": "2026-03-18T10:00:00Z",
            "session_id": "sess-1",
            "skill_name": "commit",
            "file_path": "/home/.claude/skills/commit/references/guide.md",
            "relative_path": "references/guide.md",
            "file_type": "reference",
            "hierarchy": "content",
            "project_dir": "/tmp/project",
        }
        db.insert_file_access(conn, event)
        row = conn.execute("SELECT * FROM file_accesses").fetchone()
        assert row is not None


# --- insert_lifecycle_event ---

class TestInsertLifecycleEvent:
    @pytest.mark.unit
    def test_inserts_skill_added(self, conn):
        event = {
            "timestamp": "2026-03-18T10:00:00Z",
            "event_type": "skill_added",
            "skill_name": "commit",
            "source": "folder",
            "scope": "user",
            "skill_path": "/home/.claude/skills/commit",
        }
        db.insert_lifecycle_event(conn, event)
        row = conn.execute("SELECT * FROM skill_lifecycle").fetchone()
        assert row is not None

    @pytest.mark.unit
    def test_inserts_skill_removed(self, conn):
        event = {
            "timestamp": "2026-03-18T10:00:00Z",
            "event_type": "skill_removed",
            "skill_name": "commit",
            "source": "folder",
            "scope": "user",
            "skill_path": "/home/.claude/skills/commit",
        }
        db.insert_lifecycle_event(conn, event)
        rows = conn.execute("SELECT * FROM skill_lifecycle").fetchall()
        assert len(rows) == 1


# --- upsert_skill ---

class TestUpsertSkill:
    @pytest.mark.unit
    def test_inserts_new_skill(self, conn):
        skill_id = db.upsert_skill(conn, {
            "name": "commit",
            "source": "folder",
            "scope": "user",
            "path": "/home/.claude/skills/commit",
            "total_nested_files": 3,
        })
        assert isinstance(skill_id, int)
        assert skill_id > 0

    @pytest.mark.unit
    def test_updates_existing_skill(self, conn):
        info = {
            "name": "commit",
            "source": "folder",
            "scope": "user",
            "path": "/home/.claude/skills/commit",
            "total_nested_files": 3,
        }
        id1 = db.upsert_skill(conn, info)
        info["total_nested_files"] = 5
        id2 = db.upsert_skill(conn, info)
        assert id1 == id2
        row = conn.execute(
            "SELECT total_nested_files FROM skills WHERE id = ?", (id1,)
        ).fetchone()
        assert row[0] == 5


# --- mark_skill_removed ---

class TestMarkSkillRemoved:
    @pytest.mark.unit
    def test_sets_removed_status(self, conn):
        db.upsert_skill(conn, {
            "name": "old-skill",
            "source": "folder",
            "scope": "user",
            "path": "/home/.claude/skills/old-skill",
            "total_nested_files": 1,
        })
        db.mark_skill_removed(conn, "old-skill", "folder", "user", "2026-03-18T12:00:00Z")
        row = conn.execute(
            "SELECT status, removed_at FROM skills WHERE name = 'old-skill'"
        ).fetchone()
        assert row[0] == "removed"
        assert row[1] == "2026-03-18T12:00:00Z"


# --- upsert_skill_file ---

class TestUpsertSkillFile:
    @pytest.mark.unit
    def test_inserts_new_file(self, conn):
        skill_id = db.upsert_skill(conn, {
            "name": "my-skill",
            "source": "folder",
            "scope": "user",
            "path": "/home/.claude/skills/my-skill",
            "total_nested_files": 1,
        })
        db.upsert_skill_file(
            conn, skill_id, "references/guide.md",
            "reference", "content", "2026-03-18T10:00:00Z"
        )
        files = db.get_skill_files(conn, skill_id)
        assert len(files) == 1
        assert files[0]["relative_path"] == "references/guide.md"
        assert files[0]["first_seen_at"] == "2026-03-18T10:00:00Z"


# --- mark_skill_file_removed ---

class TestMarkSkillFileRemoved:
    @pytest.mark.unit
    def test_sets_removed_at(self, conn):
        skill_id = db.upsert_skill(conn, {
            "name": "my-skill",
            "source": "folder",
            "scope": "user",
            "path": "/home/.claude/skills/my-skill",
            "total_nested_files": 1,
        })
        db.upsert_skill_file(
            conn, skill_id, "scripts/old.py",
            "script", "script", "2026-03-01T00:00:00Z"
        )
        db.mark_skill_file_removed(conn, skill_id, "scripts/old.py", "2026-03-18T00:00:00Z")
        files = db.get_skill_files(conn, skill_id)
        assert files[0]["removed_at"] == "2026-03-18T00:00:00Z"


# --- get_skill_files ---

class TestGetSkillFiles:
    @pytest.mark.unit
    def test_returns_all_files(self, conn):
        skill_id = db.upsert_skill(conn, {
            "name": "my-skill",
            "source": "folder",
            "scope": "user",
            "path": "/home/.claude/skills/my-skill",
            "total_nested_files": 2,
        })
        db.upsert_skill_file(conn, skill_id, "SKILL.md", "markdown", "content", "2026-03-01T00:00:00Z")
        db.upsert_skill_file(conn, skill_id, "scripts/run.py", "script", "script", "2026-03-10T00:00:00Z")
        files = db.get_skill_files(conn, skill_id)
        assert len(files) == 2
        paths = {f["relative_path"] for f in files}
        assert paths == {"SKILL.md", "scripts/run.py"}

    @pytest.mark.unit
    def test_includes_removed_files(self, conn):
        skill_id = db.upsert_skill(conn, {
            "name": "my-skill",
            "source": "folder",
            "scope": "user",
            "path": "/home/.claude/skills/my-skill",
            "total_nested_files": 1,
        })
        db.upsert_skill_file(conn, skill_id, "old.md", "markdown", "content", "2026-03-01T00:00:00Z")
        db.mark_skill_file_removed(conn, skill_id, "old.md", "2026-03-15T00:00:00Z")
        files = db.get_skill_files(conn, skill_id)
        assert len(files) == 1
        assert files[0]["removed_at"] == "2026-03-15T00:00:00Z"


# --- save_snapshot / get_latest_snapshot ---

class TestSnapshots:
    @pytest.mark.unit
    def test_save_and_retrieve(self, conn):
        snapshot = [
            {"name": "skill-a", "source": "folder", "scope": "user", "path": "/a"},
            {"name": "skill-b", "source": "plugin", "scope": "project", "path": "/b"},
        ]
        db.save_snapshot(conn, "2026-03-18T10:00:00Z", snapshot)
        result = db.get_latest_snapshot(conn)
        assert result is not None
        assert len(result) == 2

    @pytest.mark.unit
    def test_returns_none_when_empty(self, conn):
        result = db.get_latest_snapshot(conn)
        assert result is None

    @pytest.mark.unit
    def test_prunes_old_snapshots(self, conn):
        for i in range(105):
            db.save_snapshot(conn, f"2026-01-01T{i:04d}:00Z", [{"name": f"s{i}", "source": "folder", "scope": "user", "path": f"/{i}"}])
        count = conn.execute("SELECT COUNT(*) FROM inventory_snapshots").fetchone()[0]
        assert count <= 100

    @pytest.mark.unit
    def test_wal_mode_on_connection(self, conn):
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode == "wal"
