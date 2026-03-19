"""Unit tests for scripts/inventory_snapshot.py."""

import json
import io
import pytest
from unittest.mock import patch, MagicMock, call

from scripts import inventory_snapshot


def make_hook_input(cwd: str = "/tmp/project") -> str:
    """Create a JSON string simulating UserPromptSubmit hook stdin."""
    return json.dumps({
        "session_id": "sess-1",
        "transcript_path": "/tmp/transcript.jsonl",
        "cwd": cwd,
        "hook_event_name": "UserPromptSubmit",
        "prompt": "hello",
    })


class TestInventorySnapshotFirstRun:
    @pytest.mark.unit
    @patch("scripts.inventory_snapshot.db")
    @patch("scripts.inventory_snapshot.skill_discovery")
    def test_treats_all_skills_as_new(self, mock_discovery, mock_db, monkeypatch):
        mock_discovery.discover_all.return_value = [
            {"name": "skill-a", "source": "folder", "scope": "user", "path": "/a", "nested_files": ["SKILL.md"], "file_types": {"SKILL.md": "markdown"}, "hierarchies": {"SKILL.md": "content"}},
        ]
        mock_db.get_latest_snapshot.return_value = None
        mock_db.upsert_skill.return_value = 1
        mock_db.get_connection.return_value = MagicMock()

        monkeypatch.setattr("sys.stdin", io.StringIO(make_hook_input()))
        stdout = io.StringIO()
        monkeypatch.setattr("sys.stdout", stdout)

        inventory_snapshot.main()

        mock_db.insert_lifecycle_event.assert_called()
        event = mock_db.insert_lifecycle_event.call_args[0][1]
        assert event["event_type"] == "skill_added"
        assert event["skill_name"] == "skill-a"


class TestInventorySnapshotDiffSkills:
    @pytest.mark.unit
    @patch("scripts.inventory_snapshot.db")
    @patch("scripts.inventory_snapshot.skill_discovery")
    def test_detects_added_skill(self, mock_discovery, mock_db, monkeypatch):
        mock_discovery.discover_all.return_value = [
            {"name": "skill-a", "source": "folder", "scope": "user", "path": "/a", "nested_files": ["SKILL.md"], "file_types": {"SKILL.md": "markdown"}, "hierarchies": {"SKILL.md": "content"}},
            {"name": "skill-b", "source": "plugin", "scope": "project", "path": "/b", "nested_files": ["SKILL.md"], "file_types": {"SKILL.md": "markdown"}, "hierarchies": {"SKILL.md": "content"}},
        ]
        mock_db.get_latest_snapshot.return_value = [
            {"name": "skill-a", "source": "folder", "scope": "user", "path": "/a"},
        ]
        mock_db.upsert_skill.return_value = 2
        mock_db.get_connection.return_value = MagicMock()

        monkeypatch.setattr("sys.stdin", io.StringIO(make_hook_input()))
        stdout = io.StringIO()
        monkeypatch.setattr("sys.stdout", stdout)

        inventory_snapshot.main()

        lifecycle_calls = mock_db.insert_lifecycle_event.call_args_list
        added_events = [c for c in lifecycle_calls if c[0][1]["event_type"] == "skill_added"]
        assert len(added_events) >= 1
        added_names = {c[0][1]["skill_name"] for c in added_events}
        assert "skill-b" in added_names

    @pytest.mark.unit
    @patch("scripts.inventory_snapshot.db")
    @patch("scripts.inventory_snapshot.skill_discovery")
    def test_detects_removed_skill(self, mock_discovery, mock_db, monkeypatch):
        mock_discovery.discover_all.return_value = [
            {"name": "skill-a", "source": "folder", "scope": "user", "path": "/a", "nested_files": ["SKILL.md"], "file_types": {"SKILL.md": "markdown"}, "hierarchies": {"SKILL.md": "content"}},
        ]
        mock_db.get_latest_snapshot.return_value = [
            {"name": "skill-a", "source": "folder", "scope": "user", "path": "/a"},
            {"name": "skill-gone", "source": "folder", "scope": "user", "path": "/gone"},
        ]
        mock_db.get_connection.return_value = MagicMock()

        monkeypatch.setattr("sys.stdin", io.StringIO(make_hook_input()))
        stdout = io.StringIO()
        monkeypatch.setattr("sys.stdout", stdout)

        inventory_snapshot.main()

        lifecycle_calls = mock_db.insert_lifecycle_event.call_args_list
        removed_events = [c for c in lifecycle_calls if c[0][1]["event_type"] == "skill_removed"]
        assert len(removed_events) >= 1
        removed_names = {c[0][1]["skill_name"] for c in removed_events}
        assert "skill-gone" in removed_names


class TestInventorySnapshotDiffNestedFiles:
    @pytest.mark.unit
    @patch("scripts.inventory_snapshot.db")
    @patch("scripts.inventory_snapshot.skill_discovery")
    def test_detects_new_nested_file(self, mock_discovery, mock_db, monkeypatch):
        mock_discovery.discover_all.return_value = [
            {
                "name": "skill-a", "source": "folder", "scope": "user", "path": "/a",
                "nested_files": ["SKILL.md", "references/new.md"],
                "file_types": {"SKILL.md": "markdown", "references/new.md": "reference"},
                "hierarchies": {"SKILL.md": "content", "references/new.md": "content"},
            },
        ]
        mock_db.get_latest_snapshot.return_value = [
            {"name": "skill-a", "source": "folder", "scope": "user", "path": "/a"},
        ]
        mock_db.upsert_skill.return_value = 1
        mock_db.get_skill_files.return_value = [
            {"relative_path": "SKILL.md", "file_type": "markdown", "hierarchy": "content", "first_seen_at": "2026-03-01T00:00:00Z", "removed_at": None},
        ]
        mock_db.get_connection.return_value = MagicMock()

        monkeypatch.setattr("sys.stdin", io.StringIO(make_hook_input()))
        stdout = io.StringIO()
        monkeypatch.setattr("sys.stdout", stdout)

        inventory_snapshot.main()

        upsert_file_calls = mock_db.upsert_skill_file.call_args_list
        new_file_calls = [c for c in upsert_file_calls if c[0][2] == "references/new.md"]
        assert len(new_file_calls) >= 1

    @pytest.mark.unit
    @patch("scripts.inventory_snapshot.db")
    @patch("scripts.inventory_snapshot.skill_discovery")
    def test_detects_removed_nested_file(self, mock_discovery, mock_db, monkeypatch):
        mock_discovery.discover_all.return_value = [
            {
                "name": "skill-a", "source": "folder", "scope": "user", "path": "/a",
                "nested_files": ["SKILL.md"],
                "file_types": {"SKILL.md": "markdown"},
                "hierarchies": {"SKILL.md": "content"},
            },
        ]
        mock_db.get_latest_snapshot.return_value = [
            {"name": "skill-a", "source": "folder", "scope": "user", "path": "/a"},
        ]
        mock_db.upsert_skill.return_value = 1
        mock_db.get_skill_files.return_value = [
            {"relative_path": "SKILL.md", "file_type": "markdown", "hierarchy": "content", "first_seen_at": "2026-03-01T00:00:00Z", "removed_at": None},
            {"relative_path": "scripts/old.py", "file_type": "script", "hierarchy": "script", "first_seen_at": "2026-03-01T00:00:00Z", "removed_at": None},
        ]
        mock_db.get_connection.return_value = MagicMock()

        monkeypatch.setattr("sys.stdin", io.StringIO(make_hook_input()))
        stdout = io.StringIO()
        monkeypatch.setattr("sys.stdout", stdout)

        inventory_snapshot.main()

        remove_calls = mock_db.mark_skill_file_removed.call_args_list
        removed_paths = [c[0][2] for c in remove_calls]
        assert "scripts/old.py" in removed_paths
