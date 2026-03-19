"""Integration tests for hook scripts → DB pipeline.

These tests exercise the full path from simulated hook stdin
through to actual SQLite writes, without mocking the DB layer.
"""

import json
import io
import os
import pytest

from scripts import db, log_event, inventory_snapshot, skill_discovery


@pytest.fixture
def test_db(tmp_path):
    """Provide a real SQLite DB for integration tests."""
    db_path = str(tmp_path / "integration_test.db")
    conn = db.get_connection(db_path)
    db.init_schema(conn)
    yield conn, db_path
    conn.close()


@pytest.fixture
def skill_tree(tmp_path):
    """Create a real skill directory tree for discovery."""
    skills_dir = tmp_path / ".claude" / "skills"
    skill_a = skills_dir / "skill-a"
    skill_a.mkdir(parents=True)
    (skill_a / "SKILL.md").write_text("# Skill A")
    refs = skill_a / "references"
    refs.mkdir()
    (refs / "guide.md").write_text("# Guide")
    scripts_dir = skill_a / "scripts"
    scripts_dir.mkdir()
    (scripts_dir / "run.py").write_text("print('ok')")
    return tmp_path


# --- Hook → DB integration ---

class TestLogEventIntegration:
    @pytest.mark.integration
    def test_skill_invocation_writes_to_db(self, tmp_path, monkeypatch):
        db_dir = tmp_path / "plugin_data"
        db_dir.mkdir()
        monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(db_dir))

        stdin_data = json.dumps({
            "session_id": "sess-integ-1",
            "transcript_path": "/tmp/transcript.jsonl",
            "cwd": "/tmp/project",
            "hook_event_name": "PreToolUse",
            "tool_name": "Skill",
            "tool_use_id": "toolu_integ_001",
            "tool_input": {"skill": "my-skill", "args": ""},
        })
        monkeypatch.setattr("sys.stdin", io.StringIO(stdin_data))
        stdout = io.StringIO()
        monkeypatch.setattr("sys.stdout", stdout)

        log_event.main()

        # Verify the event was written to the actual DB
        verify_conn = db.get_connection(str(db_dir / "skills_analytics.db"))
        rows = verify_conn.execute("SELECT skill_name FROM skill_invocations").fetchall()
        verify_conn.close()
        assert len(rows) == 1
        assert rows[0][0] == "my-skill"

        # Verify allow response was written
        output = json.loads(stdout.getvalue())
        assert output["hookSpecificOutput"]["permissionDecision"] == "allow"


class TestInventorySnapshotIntegration:
    @pytest.mark.integration
    def test_first_run_registers_skills(self, skill_tree, tmp_path, monkeypatch):
        db_dir = tmp_path / "plugin_data"
        db_dir.mkdir()
        monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(db_dir))
        monkeypatch.setenv("HOME", str(skill_tree))
        monkeypatch.setattr(os.path, "expanduser", lambda x: str(skill_tree) if x == "~" else x)

        stdin_data = json.dumps({
            "session_id": "sess-integ-2",
            "transcript_path": "/tmp/transcript.jsonl",
            "cwd": str(skill_tree),
            "hook_event_name": "UserPromptSubmit",
            "prompt": "hello",
        })
        monkeypatch.setattr("sys.stdin", io.StringIO(stdin_data))
        stdout = io.StringIO()
        monkeypatch.setattr("sys.stdout", stdout)

        inventory_snapshot.main()

        # Verify skills were registered in DB
        verify_conn = db.get_connection(str(db_dir / "skills_analytics.db"))
        skills = verify_conn.execute("SELECT name, status FROM skills").fetchall()
        verify_conn.close()
        assert len(skills) >= 1
        skill_names = {s[0] for s in skills}
        assert "skill-a" in skill_names

    @pytest.mark.integration
    def test_second_run_detects_removal(self, skill_tree, tmp_path, monkeypatch):
        db_dir = tmp_path / "plugin_data"
        db_dir.mkdir()
        monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(db_dir))
        monkeypatch.setenv("HOME", str(skill_tree))
        monkeypatch.setattr(os.path, "expanduser", lambda x: str(skill_tree) if x == "~" else x)

        # First run
        stdin_data = json.dumps({
            "session_id": "sess-integ-3",
            "cwd": str(skill_tree),
            "hook_event_name": "UserPromptSubmit",
            "prompt": "hello",
        })
        monkeypatch.setattr("sys.stdin", io.StringIO(stdin_data))
        monkeypatch.setattr("sys.stdout", io.StringIO())
        inventory_snapshot.main()

        # Delete the skill
        import shutil
        shutil.rmtree(str(skill_tree / ".claude" / "skills" / "skill-a"))

        # Second run
        stdin_data2 = json.dumps({
            "session_id": "sess-integ-4",
            "cwd": str(skill_tree),
            "hook_event_name": "UserPromptSubmit",
            "prompt": "hello again",
        })
        monkeypatch.setattr("sys.stdin", io.StringIO(stdin_data2))
        monkeypatch.setattr("sys.stdout", io.StringIO())
        inventory_snapshot.main()

        # Verify skill is marked as removed
        verify_conn = db.get_connection(str(db_dir / "skills_analytics.db"))
        row = verify_conn.execute(
            "SELECT status, removed_at FROM skills WHERE name = 'skill-a'"
        ).fetchone()
        verify_conn.close()
        assert row[0] == "removed"
        assert row[1] is not None


# --- Discovery → DB → Analytics integration ---

class TestFullPipelineIntegration:
    @pytest.mark.integration
    def test_discover_snapshot_invoke_analyze(self, skill_tree, tmp_path, monkeypatch):
        """Full pipeline: discover skills → snapshot → invoke → query analytics."""
        db_dir = tmp_path / "plugin_data"
        db_dir.mkdir()
        db_path = str(db_dir / "skills_analytics.db")
        monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(db_dir))
        monkeypatch.setenv("HOME", str(skill_tree))
        monkeypatch.setattr(os.path, "expanduser", lambda x: str(skill_tree) if x == "~" else x)

        # Step 1: Run inventory snapshot
        stdin_data = json.dumps({
            "session_id": "sess-pipe-1",
            "cwd": str(skill_tree),
            "hook_event_name": "UserPromptSubmit",
            "prompt": "hello",
        })
        monkeypatch.setattr("sys.stdin", io.StringIO(stdin_data))
        monkeypatch.setattr("sys.stdout", io.StringIO())
        inventory_snapshot.main()

        # Step 2: Simulate skill invocations
        conn = db.get_connection(db_path)
        for i in range(5):
            db.insert_skill_invocation(conn, {
                "timestamp": f"2026-03-18T{10+i:02d}:00:00Z",
                "session_id": f"sess-pipe-{i}",
                "skill_name": "skill-a",
                "invocation_id": f"toolu_pipe_{i}",
                "source": "folder",
                "scope": "user",
                "project_dir": str(skill_tree),
                "args": "",
            })

        # Step 3: Simulate file accesses
        db.insert_file_access(conn, {
            "timestamp": "2026-03-18T12:00:00Z",
            "session_id": "sess-pipe-1",
            "skill_name": "skill-a",
            "file_path": str(skill_tree / ".claude/skills/skill-a/references/guide.md"),
            "relative_path": "references/guide.md",
            "file_type": "reference",
            "hierarchy": "content",
            "project_dir": str(skill_tree),
        })

        # Step 4: Query analytics
        from dashboard.analytics import analytics

        freq = analytics.frequency_ranking(conn, "2026-03-01T00:00:00Z", "2026-03-31T23:59:59Z")
        assert len(freq) >= 1
        skill_a_freq = [f for f in freq if f["skill_name"] == "skill-a"]
        assert len(skill_a_freq) == 1
        assert skill_a_freq[0]["count"] == 5

        coverage = analytics.structure_coverage(conn, "skill-a", "2026-03-01T00:00:00Z", "2026-03-31T23:59:59Z")
        assert coverage["skill_name"] == "skill-a"
        assert coverage["accessed_files"] >= 1

        trends = analytics.usage_trends(conn, "2026-03-01T00:00:00Z", "2026-03-31T23:59:59Z", "day")
        assert len(trends) >= 1

        conn.close()
