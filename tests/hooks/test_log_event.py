"""Unit tests for scripts/log_event.py."""

import json
import io
import pytest
from unittest.mock import patch, MagicMock

from scripts import log_event


def make_hook_input(tool_name: str, tool_input: dict) -> str:
    """Create a JSON string simulating hook stdin."""
    return json.dumps({
        "session_id": "sess-1",
        "transcript_path": "/tmp/transcript.jsonl",
        "cwd": "/tmp/project",
        "hook_event_name": "PreToolUse",
        "tool_name": tool_name,
        "tool_use_id": "toolu_abc123",
        "tool_input": tool_input,
    })


class TestLogEventSkillInvocation:
    @pytest.mark.unit
    @patch("scripts.log_event.db")
    def test_logs_skill_invocation(self, mock_db, monkeypatch):
        stdin_data = make_hook_input("Skill", {"skill": "commit", "args": "--amend"})
        monkeypatch.setattr("sys.stdin", io.StringIO(stdin_data))
        stdout = io.StringIO()
        monkeypatch.setattr("sys.stdout", stdout)

        log_event.main()

        mock_db.insert_skill_invocation.assert_called_once()
        call_args = mock_db.insert_skill_invocation.call_args
        event = call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get("event", call_args[0][1])
        assert event["skill_name"] == "commit"

    @pytest.mark.unit
    @patch("scripts.log_event.db")
    def test_always_outputs_allow(self, mock_db, monkeypatch):
        stdin_data = make_hook_input("Skill", {"skill": "commit"})
        monkeypatch.setattr("sys.stdin", io.StringIO(stdin_data))
        stdout = io.StringIO()
        monkeypatch.setattr("sys.stdout", stdout)

        log_event.main()

        output = json.loads(stdout.getvalue())
        assert output["hookSpecificOutput"]["permissionDecision"] == "allow"


class TestLogEventFileAccess:
    @pytest.mark.unit
    @patch("scripts.log_event.skill_discovery")
    @patch("scripts.log_event.db")
    def test_logs_file_access_for_skill_path(self, mock_db, mock_discovery, monkeypatch):
        mock_discovery.resolve_skill_for_path.return_value = {
            "skill_name": "commit",
            "relative_path": "references/guide.md",
            "file_type": "reference",
            "hierarchy": "content",
        }
        stdin_data = make_hook_input("Read", {"file_path": "/home/.claude/skills/commit/references/guide.md"})
        monkeypatch.setattr("sys.stdin", io.StringIO(stdin_data))
        stdout = io.StringIO()
        monkeypatch.setattr("sys.stdout", stdout)

        log_event.main()

        mock_db.insert_file_access.assert_called_once()

    @pytest.mark.unit
    @patch("scripts.log_event.skill_discovery")
    @patch("scripts.log_event.db")
    def test_skips_non_skill_path(self, mock_db, mock_discovery, monkeypatch):
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
    def test_always_outputs_allow_on_read(self, mock_db, mock_discovery, monkeypatch):
        mock_discovery.resolve_skill_for_path.return_value = None
        stdin_data = make_hook_input("Read", {"file_path": "/tmp/any/file.py"})
        monkeypatch.setattr("sys.stdin", io.StringIO(stdin_data))
        stdout = io.StringIO()
        monkeypatch.setattr("sys.stdout", stdout)

        log_event.main()

        output = json.loads(stdout.getvalue())
        assert output["hookSpecificOutput"]["permissionDecision"] == "allow"


class TestLogEventErrorHandling:
    @pytest.mark.unit
    @patch("scripts.log_event.db")
    def test_outputs_allow_on_error(self, mock_db, monkeypatch):
        mock_db.insert_skill_invocation.side_effect = Exception("DB write failed")
        stdin_data = make_hook_input("Skill", {"skill": "commit"})
        monkeypatch.setattr("sys.stdin", io.StringIO(stdin_data))
        stdout = io.StringIO()
        monkeypatch.setattr("sys.stdout", stdout)

        log_event.main()

        output = json.loads(stdout.getvalue())
        assert output["hookSpecificOutput"]["permissionDecision"] == "allow"

    @pytest.mark.unit
    def test_outputs_allow_on_invalid_json(self, monkeypatch):
        monkeypatch.setattr("sys.stdin", io.StringIO("not valid json"))
        stdout = io.StringIO()
        monkeypatch.setattr("sys.stdout", stdout)

        log_event.main()

        output = json.loads(stdout.getvalue())
        assert output["hookSpecificOutput"]["permissionDecision"] == "allow"
