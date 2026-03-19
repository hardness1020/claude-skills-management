"""Integration tests for plugin packaging (#ft-4).

Tests the full hook → DB pipeline with the log_event.py fix
(skill_paths populated from discover_all), and the settings
SECRET_KEY generation with real filesystem I/O.
"""

import json
import io
import os
import pytest

from scripts import db, log_event, skill_discovery


@pytest.fixture
def skill_tree(tmp_path):
    """Create a real skill directory tree for discovery."""
    skills_dir = tmp_path / ".claude" / "skills"
    skill_a = skills_dir / "test-skill"
    skill_a.mkdir(parents=True)
    (skill_a / "SKILL.md").write_text("# Test Skill")
    refs = skill_a / "references"
    refs.mkdir()
    (refs / "guide.md").write_text("# Guide content")
    return tmp_path


class TestFileReadIntegration:
    """Integration: Read hook → discover_all → resolve → DB write."""

    @pytest.mark.integration
    def test_file_read_inside_skill_writes_to_db(self, skill_tree, tmp_path, monkeypatch):
        """Full path: Read hook input → discover skills → resolve path → insert file_access."""
        db_dir = tmp_path / "plugin_data"
        db_dir.mkdir()
        monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(db_dir))
        monkeypatch.setenv("HOME", str(skill_tree))
        monkeypatch.setattr(os.path, "expanduser", lambda x: str(skill_tree) if x == "~" else x)

        file_path = str(skill_tree / ".claude" / "skills" / "test-skill" / "references" / "guide.md")
        stdin_data = json.dumps({
            "session_id": "sess-integ-read-1",
            "transcript_path": "/tmp/transcript.jsonl",
            "cwd": str(skill_tree),
            "hook_event_name": "PreToolUse",
            "tool_name": "Read",
            "tool_use_id": "toolu_integ_read_001",
            "tool_input": {"file_path": file_path},
        })
        monkeypatch.setattr("sys.stdin", io.StringIO(stdin_data))
        stdout = io.StringIO()
        monkeypatch.setattr("sys.stdout", stdout)

        log_event.main()

        # Verify allow response
        output = json.loads(stdout.getvalue())
        assert output["hookSpecificOutput"]["permissionDecision"] == "allow"

        # Verify file access was recorded in DB
        verify_conn = db.get_connection(str(db_dir / "skills_analytics.db"))
        rows = verify_conn.execute(
            "SELECT skill_name, relative_path, file_type FROM file_accesses"
        ).fetchall()
        verify_conn.close()
        assert len(rows) == 1
        assert rows[0][0] == "test-skill"
        assert rows[0][1] == os.path.join("references", "guide.md")
        assert rows[0][2] == "reference"

    @pytest.mark.integration
    def test_file_read_outside_skill_no_db_write(self, skill_tree, tmp_path, monkeypatch):
        """Read of a file outside skill directories should not create a DB row."""
        db_dir = tmp_path / "plugin_data"
        db_dir.mkdir()
        monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(db_dir))
        monkeypatch.setenv("HOME", str(skill_tree))
        monkeypatch.setattr(os.path, "expanduser", lambda x: str(skill_tree) if x == "~" else x)

        stdin_data = json.dumps({
            "session_id": "sess-integ-read-2",
            "transcript_path": "/tmp/transcript.jsonl",
            "cwd": str(skill_tree),
            "hook_event_name": "PreToolUse",
            "tool_name": "Read",
            "tool_use_id": "toolu_integ_read_002",
            "tool_input": {"file_path": "/tmp/random/file.py"},
        })
        monkeypatch.setattr("sys.stdin", io.StringIO(stdin_data))
        stdout = io.StringIO()
        monkeypatch.setattr("sys.stdout", stdout)

        log_event.main()

        # Verify allow response
        output = json.loads(stdout.getvalue())
        assert output["hookSpecificOutput"]["permissionDecision"] == "allow"

        # Verify no file access was recorded
        verify_conn = db.get_connection(str(db_dir / "skills_analytics.db"))
        rows = verify_conn.execute("SELECT COUNT(*) FROM file_accesses").fetchone()
        verify_conn.close()
        assert rows[0] == 0


class TestSkillInvocationIntegration:
    """Integration: Skill invocation → DB → analytics query matches."""

    @pytest.mark.integration
    def test_prefixed_invocation_matches_prefixed_skill_in_analytics(self, tmp_path, monkeypatch):
        """Full pipeline: log prefixed invocation, upsert prefixed skill, verify analytics finds it."""
        db_dir = tmp_path / "plugin_data"
        db_dir.mkdir()
        monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(db_dir))

        # Simulate what log_event does: store invocation with prefixed name
        conn = db.get_connection(str(db_dir / "skills_analytics.db"))
        db.init_schema(conn)

        # Simulate inventory_snapshot: store skill with prefixed name
        db.upsert_skill(conn, {
            "name": "vibeflow:manage-work",
            "source": "plugin", "scope": "user",
            "path": "/plugins/vibeflow/skills/manage-work",
            "total_nested_files": 2,
        })
        # Backdate first_seen
        conn.execute(
            "UPDATE skills SET first_seen_at = '2026-03-01T00:00:00+00:00' WHERE name = 'vibeflow:manage-work'"
        )
        conn.commit()

        # Simulate log_event: insert invocations with prefixed name
        for i in range(5):
            db.insert_skill_invocation(conn, {
                "timestamp": f"2026-03-10T{10+i}:00:00Z",
                "session_id": f"sess-{i}",
                "skill_name": "vibeflow:manage-work",
                "invocation_id": f"toolu_integ_{i}",
                "source": "plugin", "scope": "user",
                "project_dir": "/tmp", "args": "",
            })

        from dashboard.analytics import analytics

        # Usefulness should find the invocations
        scores = analytics.usefulness_scores(conn, "2026-03-01T00:00:00Z", "2026-03-31T23:59:59Z")
        skill = [s for s in scores if s["skill_name"] == "vibeflow:manage-work"]
        assert len(skill) == 1
        assert skill[0]["usage_rate"] > 0
        assert skill[0]["score"] > 0

        # Frequency should also find them
        freq = analytics.frequency_ranking(conn, "2026-03-01T00:00:00Z", "2026-03-31T23:59:59Z")
        skill_freq = [f for f in freq if f["skill_name"] == "vibeflow:manage-work"]
        assert len(skill_freq) == 1
        assert skill_freq[0]["count"] == 5
        assert skill_freq[0]["source"] == "plugin"

        conn.close()


class TestSecretKeyIntegration:
    """Integration: SECRET_KEY generation with real filesystem."""

    @pytest.mark.integration
    def test_secret_key_roundtrip(self, tmp_path, monkeypatch):
        """Generate key → persist → reload from file."""
        monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(tmp_path))

        from dashboard.analytics_project import settings

        key1 = settings._get_secret_key()
        assert len(key1) > 20  # Django keys are typically 50+ chars

        # Read directly from file
        secret_file = tmp_path / "django_secret.txt"
        assert secret_file.exists()
        file_key = secret_file.read_text().strip()
        assert file_key == key1

        # Second call returns same key
        key2 = settings._get_secret_key()
        assert key2 == key1

    @pytest.mark.integration
    def test_secret_key_creates_directory(self, tmp_path, monkeypatch):
        """_get_secret_key creates parent directory if needed."""
        nested = tmp_path / "deeply" / "nested" / "dir"
        monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(nested))

        from dashboard.analytics_project import settings

        key = settings._get_secret_key()
        assert len(key) > 0
        assert (nested / "django_secret.txt").exists()
