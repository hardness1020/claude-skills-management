"""Unit tests for log_event.py file read fix (#ft-4).

Tests that _handle_file_read builds skill_paths from discover_all()
before calling resolve_skill_for_path, fixing the bug where
skill_paths was always None.
"""

import json
import io
import pytest
from unittest.mock import patch, MagicMock, call

from scripts import log_event


def make_hook_input(tool_name: str, tool_input: dict, cwd: str = "/tmp/project") -> str:
    """Create a JSON string simulating hook stdin."""
    return json.dumps({
        "session_id": "sess-1",
        "transcript_path": "/tmp/transcript.jsonl",
        "cwd": cwd,
        "hook_event_name": "PreToolUse",
        "tool_name": tool_name,
        "tool_use_id": "toolu_fix123",
        "tool_input": tool_input,
    })


class TestFileReadSkillPathsPopulated:
    """Tests that _handle_file_read populates skill_paths from discover_all()."""

    @pytest.mark.unit
    @patch("scripts.log_event.skill_discovery")
    @patch("scripts.log_event.db")
    def test_calls_discover_all_with_cwd(self, mock_db, mock_discovery, monkeypatch):
        """discover_all() must be called with the project dir from hook input."""
        mock_discovery.discover_all.return_value = []
        mock_discovery.resolve_skill_for_path.return_value = None

        stdin_data = make_hook_input("Read", {"file_path": "/tmp/some/file.py"}, cwd="/my/project")
        monkeypatch.setattr("sys.stdin", io.StringIO(stdin_data))
        stdout = io.StringIO()
        monkeypatch.setattr("sys.stdout", stdout)

        log_event.main()

        mock_discovery.discover_all.assert_called_once_with(project_dir="/my/project")

    @pytest.mark.unit
    @patch("scripts.log_event.skill_discovery")
    @patch("scripts.log_event.db")
    def test_passes_skill_paths_to_resolve(self, mock_db, mock_discovery, monkeypatch):
        """resolve_skill_for_path() must receive a populated skill_paths dict."""
        fake_skill = {
            "name": "my-skill",
            "source": "folder",
            "scope": "user",
            "path": "/home/.claude/skills/my-skill",
            "nested_files": ["SKILL.md"],
        }
        mock_discovery.discover_all.return_value = [fake_skill]
        mock_discovery.resolve_skill_for_path.return_value = None

        stdin_data = make_hook_input("Read", {"file_path": "/tmp/any/file.py"})
        monkeypatch.setattr("sys.stdin", io.StringIO(stdin_data))
        stdout = io.StringIO()
        monkeypatch.setattr("sys.stdout", stdout)

        log_event.main()

        resolve_call = mock_discovery.resolve_skill_for_path.call_args
        assert resolve_call is not None, "resolve_skill_for_path must be called"
        # Second argument (or keyword) should be skill_paths dict keyed by path
        args, kwargs = resolve_call
        skill_paths_arg = kwargs.get("skill_paths", args[1] if len(args) > 1 else None)
        assert skill_paths_arg is not None, "skill_paths must not be None"
        assert "/home/.claude/skills/my-skill" in skill_paths_arg
        assert skill_paths_arg["/home/.claude/skills/my-skill"]["name"] == "my-skill"

    @pytest.mark.unit
    @patch("scripts.log_event.skill_discovery")
    @patch("scripts.log_event.db")
    def test_file_inside_skill_logged_to_db(self, mock_db, mock_discovery, monkeypatch):
        """When resolve returns a match, a file_access row must be inserted."""
        mock_discovery.discover_all.return_value = [{
            "name": "commit",
            "source": "folder",
            "scope": "user",
            "path": "/home/.claude/skills/commit",
            "nested_files": ["SKILL.md", "references/guide.md"],
        }]
        mock_discovery.resolve_skill_for_path.return_value = {
            "skill_name": "commit",
            "relative_path": "references/guide.md",
            "file_type": "reference",
            "hierarchy": "content",
        }

        file_path = "/home/.claude/skills/commit/references/guide.md"
        stdin_data = make_hook_input("Read", {"file_path": file_path})
        monkeypatch.setattr("sys.stdin", io.StringIO(stdin_data))
        stdout = io.StringIO()
        monkeypatch.setattr("sys.stdout", stdout)

        log_event.main()

        mock_db.insert_file_access.assert_called_once()
        event = mock_db.insert_file_access.call_args[0][1]
        assert event["skill_name"] == "commit"
        assert event["relative_path"] == "references/guide.md"

    @pytest.mark.unit
    @patch("scripts.log_event.skill_discovery")
    @patch("scripts.log_event.db")
    def test_file_outside_skill_not_logged(self, mock_db, mock_discovery, monkeypatch):
        """When resolve returns None, no file_access row must be inserted."""
        mock_discovery.discover_all.return_value = []
        mock_discovery.resolve_skill_for_path.return_value = None

        stdin_data = make_hook_input("Read", {"file_path": "/tmp/project/src/main.py"})
        monkeypatch.setattr("sys.stdin", io.StringIO(stdin_data))
        stdout = io.StringIO()
        monkeypatch.setattr("sys.stdout", stdout)

        log_event.main()

        mock_db.insert_file_access.assert_not_called()

    @pytest.mark.unit
    @patch("scripts.log_event.skill_discovery")
    @patch("scripts.log_event.db")
    def test_discover_all_error_still_allows(self, mock_db, mock_discovery, monkeypatch):
        """If discover_all raises, hook must still output allow."""
        mock_discovery.discover_all.side_effect = Exception("discovery failed")

        stdin_data = make_hook_input("Read", {"file_path": "/tmp/any/file.py"})
        monkeypatch.setattr("sys.stdin", io.StringIO(stdin_data))
        stdout = io.StringIO()
        monkeypatch.setattr("sys.stdout", stdout)

        log_event.main()

        output = json.loads(stdout.getvalue())
        assert output["hookSpecificOutput"]["permissionDecision"] == "allow"
        mock_db.insert_file_access.assert_not_called()
