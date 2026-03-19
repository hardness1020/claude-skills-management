"""Unit tests for scripts/skill_discovery.py."""

import os
import json
import pytest

from scripts import skill_discovery


@pytest.fixture
def skill_tree(tmp_path):
    """Create a mock skill directory tree."""
    skill_dir = tmp_path / ".claude" / "skills" / "my-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# My Skill")
    refs = skill_dir / "references"
    refs.mkdir()
    (refs / "guide.md").write_text("# Guide")
    scripts = skill_dir / "scripts"
    scripts.mkdir()
    (scripts / "validate.py").write_text("print('ok')")
    data = skill_dir / "data"
    data.mkdir()
    (data / "config.json").write_text("{}")
    assets = skill_dir / "assets"
    assets.mkdir()
    (assets / "template.md").write_text("# Template")
    (assets / "logo.png").write_bytes(b"PNG")
    return tmp_path


@pytest.fixture
def plugin_tree(tmp_path):
    """Create a mock plugin directory with installed_plugins.json."""
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()

    plugins_dir = claude_dir / "plugins"
    plugins_dir.mkdir()

    cache_dir = plugins_dir / "cache" / "marketplace" / "my-plugin" / "1.0.0"
    cache_dir.mkdir(parents=True)
    skill_dir = cache_dir / "skills" / "plugin-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# Plugin Skill")

    installed = {
        "my-plugin@marketplace": {
            "scope": "user",
            "installPath": str(cache_dir),
            "version": "1.0.0",
        }
    }
    (plugins_dir / "installed_plugins.json").write_text(json.dumps(installed))

    return tmp_path


# --- classify_file ---

class TestClassifyFile:
    @pytest.mark.unit
    def test_skill_md(self):
        file_type, hierarchy = skill_discovery.classify_file("SKILL.md")
        assert file_type == "markdown"
        assert hierarchy == "content"

    @pytest.mark.unit
    def test_reference_md(self):
        file_type, hierarchy = skill_discovery.classify_file("references/guide.md")
        assert file_type == "reference"
        assert hierarchy == "content"

    @pytest.mark.unit
    def test_script_py(self):
        file_type, hierarchy = skill_discovery.classify_file("scripts/validate.py")
        assert file_type == "script"
        assert hierarchy == "script"

    @pytest.mark.unit
    def test_data_json(self):
        file_type, hierarchy = skill_discovery.classify_file("data/config.json")
        assert file_type == "asset"
        assert hierarchy == "script"

    @pytest.mark.unit
    def test_asset_md(self):
        file_type, hierarchy = skill_discovery.classify_file("assets/template.md")
        assert file_type == "reference"
        assert hierarchy == "content"

    @pytest.mark.unit
    def test_asset_non_md(self):
        file_type, hierarchy = skill_discovery.classify_file("assets/logo.png")
        assert file_type == "asset"
        assert hierarchy == "content"

    @pytest.mark.unit
    def test_top_level_md(self):
        file_type, hierarchy = skill_discovery.classify_file("README.md")
        assert file_type == "markdown"
        assert hierarchy == "content"

    @pytest.mark.unit
    def test_config_yaml(self):
        file_type, hierarchy = skill_discovery.classify_file("config.yaml")
        assert file_type == "config"
        assert hierarchy == "script"

    @pytest.mark.unit
    def test_config_json(self):
        file_type, hierarchy = skill_discovery.classify_file("settings.json")
        assert file_type == "config"
        assert hierarchy == "script"


# --- discover_folder_skills ---

class TestDiscoverFolderSkills:
    @pytest.mark.unit
    def test_finds_skills_in_directory(self, skill_tree):
        skills_dir = str(skill_tree / ".claude" / "skills")
        result = skill_discovery.discover_folder_skills(skills_dir, "user")
        assert len(result) == 1
        assert result[0]["name"] == "my-skill"
        assert result[0]["source"] == "folder"
        assert result[0]["scope"] == "user"

    @pytest.mark.unit
    def test_lists_nested_files(self, skill_tree):
        skills_dir = str(skill_tree / ".claude" / "skills")
        result = skill_discovery.discover_folder_skills(skills_dir, "user")
        assert len(result[0]["nested_files"]) >= 5

    @pytest.mark.unit
    def test_empty_directory(self, tmp_path):
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        result = skill_discovery.discover_folder_skills(str(empty_dir), "user")
        assert result == []

    @pytest.mark.unit
    def test_nonexistent_directory(self, tmp_path):
        result = skill_discovery.discover_folder_skills(str(tmp_path / "nope"), "user")
        assert result == []


# --- discover_plugin_skills ---

class TestDiscoverPluginSkills:
    @pytest.mark.unit
    def test_finds_plugin_skills(self, plugin_tree, monkeypatch):
        monkeypatch.setenv("HOME", str(plugin_tree))
        monkeypatch.setattr(os.path, "expanduser", lambda x: str(plugin_tree) if x == "~" else x)
        result = skill_discovery.discover_plugin_skills(str(plugin_tree))
        assert len(result) >= 1
        plugin_skill = [s for s in result if s["name"] == "plugin-skill"]
        assert len(plugin_skill) == 1
        assert plugin_skill[0]["source"] == "plugin"


# --- discover_all ---

class TestDiscoverAll:
    @pytest.mark.unit
    def test_combines_sources(self, skill_tree, monkeypatch):
        monkeypatch.setenv("HOME", str(skill_tree))
        monkeypatch.setattr(os.path, "expanduser", lambda x: str(skill_tree) if x == "~" else x)
        result = skill_discovery.discover_all(str(skill_tree))
        assert len(result) >= 1
        names = {s["name"] for s in result}
        assert "my-skill" in names


# --- resolve_skill_for_path ---

class TestResolveSkillForPath:
    @pytest.mark.unit
    def test_resolves_file_inside_skill(self):
        skill_paths = {
            "/home/.claude/skills/commit": {
                "name": "commit",
                "source": "folder",
                "scope": "user",
            }
        }
        result = skill_discovery.resolve_skill_for_path(
            "/home/.claude/skills/commit/references/guide.md",
            skill_paths=skill_paths,
        )
        assert result is not None
        assert result["skill_name"] == "commit"
        assert result["relative_path"] == "references/guide.md"
        assert result["file_type"] == "reference"
        assert result["hierarchy"] == "content"

    @pytest.mark.unit
    def test_returns_none_for_unrelated_path(self):
        skill_paths = {
            "/home/.claude/skills/commit": {
                "name": "commit",
                "source": "folder",
                "scope": "user",
            }
        }
        result = skill_discovery.resolve_skill_for_path(
            "/home/projects/myapp/src/main.py",
            skill_paths=skill_paths,
        )
        assert result is None
