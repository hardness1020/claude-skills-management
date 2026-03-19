"""Unit tests for plugin configuration files (#ft-4).

Validates that .claude-plugin/plugin.json and hooks/hooks.json
have the correct structure for Claude Code plugin packaging.
"""

import json
import os
import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestPluginJson:
    @pytest.mark.unit
    def test_plugin_json_exists(self):
        path = os.path.join(PROJECT_ROOT, ".claude-plugin", "plugin.json")
        assert os.path.isfile(path), ".claude-plugin/plugin.json must exist"

    @pytest.mark.unit
    def test_plugin_json_valid_json(self):
        path = os.path.join(PROJECT_ROOT, ".claude-plugin", "plugin.json")
        with open(path) as f:
            data = json.load(f)
        assert isinstance(data, dict)

    @pytest.mark.unit
    def test_plugin_json_has_name(self):
        path = os.path.join(PROJECT_ROOT, ".claude-plugin", "plugin.json")
        with open(path) as f:
            data = json.load(f)
        assert "name" in data, "plugin.json must have 'name' field"
        assert data["name"] == "skills-analytics"

    @pytest.mark.unit
    def test_plugin_json_has_version(self):
        path = os.path.join(PROJECT_ROOT, ".claude-plugin", "plugin.json")
        with open(path) as f:
            data = json.load(f)
        assert "version" in data, "plugin.json must have 'version' field"
        assert data["version"] == "1.2.0"

    @pytest.mark.unit
    def test_plugin_json_has_description(self):
        path = os.path.join(PROJECT_ROOT, ".claude-plugin", "plugin.json")
        with open(path) as f:
            data = json.load(f)
        assert "description" in data, "plugin.json must have 'description' field"
        assert len(data["description"]) > 0


class TestHooksJson:
    @pytest.mark.unit
    def test_hooks_json_exists(self):
        path = os.path.join(PROJECT_ROOT, "hooks", "hooks.json")
        assert os.path.isfile(path), "hooks/hooks.json must exist"

    @pytest.mark.unit
    def test_hooks_json_valid_json(self):
        path = os.path.join(PROJECT_ROOT, "hooks", "hooks.json")
        with open(path) as f:
            data = json.load(f)
        assert isinstance(data, dict)

    @pytest.mark.unit
    def test_hooks_json_has_pretooluse(self):
        path = os.path.join(PROJECT_ROOT, "hooks", "hooks.json")
        with open(path) as f:
            data = json.load(f)
        assert "hooks" in data
        assert "PreToolUse" in data["hooks"], "hooks.json must declare PreToolUse hooks"

    @pytest.mark.unit
    def test_hooks_json_has_userpromptsubmit(self):
        path = os.path.join(PROJECT_ROOT, "hooks", "hooks.json")
        with open(path) as f:
            data = json.load(f)
        assert "hooks" in data
        assert "UserPromptSubmit" in data["hooks"], "hooks.json must declare UserPromptSubmit hooks"

    @pytest.mark.unit
    def test_hooks_json_pretooluse_has_matcher(self):
        path = os.path.join(PROJECT_ROOT, "hooks", "hooks.json")
        with open(path) as f:
            data = json.load(f)
        pretooluse = data["hooks"]["PreToolUse"]
        assert len(pretooluse) > 0
        assert "matcher" in pretooluse[0], "PreToolUse hook must have a matcher"
        assert "Skill" in pretooluse[0]["matcher"]
        assert "Read" in pretooluse[0]["matcher"]

    @pytest.mark.unit
    def test_hooks_json_uses_plugin_root(self):
        path = os.path.join(PROJECT_ROOT, "hooks", "hooks.json")
        with open(path) as f:
            content = f.read()
        assert "${CLAUDE_PLUGIN_ROOT}" in content, "Hook commands must use ${CLAUDE_PLUGIN_ROOT}"
        assert "$CLAUDE_PROJECT_DIR" not in content, "Hook commands must not use $CLAUDE_PROJECT_DIR"


class TestDashboardSkill:
    @pytest.mark.unit
    def test_skill_md_exists(self):
        path = os.path.join(PROJECT_ROOT, "skills", "skills-analytics-dashboard", "SKILL.md")
        assert os.path.isfile(path), "skills/skills-analytics-dashboard/SKILL.md must exist"

    @pytest.mark.unit
    def test_skill_md_has_frontmatter(self):
        path = os.path.join(PROJECT_ROOT, "skills", "skills-analytics-dashboard", "SKILL.md")
        with open(path) as f:
            content = f.read()
        assert content.startswith("---"), "SKILL.md must start with YAML frontmatter"
        # Must have closing frontmatter
        assert content.count("---") >= 2, "SKILL.md must have opening and closing frontmatter"

    @pytest.mark.unit
    def test_skill_md_has_name(self):
        path = os.path.join(PROJECT_ROOT, "skills", "skills-analytics-dashboard", "SKILL.md")
        with open(path) as f:
            content = f.read()
        assert "name: skills-analytics-dashboard" in content, "SKILL.md must declare name: skills-analytics-dashboard"

    @pytest.mark.unit
    def test_skill_md_has_description(self):
        path = os.path.join(PROJECT_ROOT, "skills", "skills-analytics-dashboard", "SKILL.md")
        with open(path) as f:
            content = f.read()
        assert "description:" in content, "SKILL.md must have a description"

    @pytest.mark.unit
    def test_skill_md_mentions_dashboard_command(self):
        path = os.path.join(PROJECT_ROOT, "skills", "skills-analytics-dashboard", "SKILL.md")
        with open(path) as f:
            content = f.read()
        assert "django" in content.lower() or "runserver" in content.lower() or "8787" in content, \
            "SKILL.md must contain instructions for starting the dashboard"
