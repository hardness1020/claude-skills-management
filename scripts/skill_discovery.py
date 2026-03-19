"""Skill discovery module.

Scans all skill sources (folder-based and plugin-based) and returns
a unified list of SkillInfo dicts. Also provides file classification
and path-to-skill resolution.
"""

import json
import os


def discover_all(project_dir: str = None) -> list[dict]:
    """Scan all skill sources and return a deduplicated list of SkillInfo dicts."""
    if project_dir is None:
        project_dir = os.getcwd()

    skills = []

    # User-level folder skills
    user_skills_dir = os.path.join(os.path.expanduser("~"), ".claude", "skills")
    skills.extend(discover_folder_skills(user_skills_dir, "user"))

    # Project-level folder skills
    project_skills_dir = os.path.join(project_dir, ".claude", "skills")
    skills.extend(discover_folder_skills(project_skills_dir, "project"))

    # Plugin-based skills
    skills.extend(discover_plugin_skills(project_dir))

    # Deduplicate by (name, source, scope)
    seen = set()
    deduped = []
    for s in skills:
        key = (s["name"], s["source"], s["scope"])
        if key not in seen:
            seen.add(key)
            deduped.append(s)

    return deduped


def discover_folder_skills(skills_dir: str, scope: str) -> list[dict]:
    """Scan a .claude/skills/ directory for folder-based skills."""
    if not os.path.isdir(skills_dir):
        return []

    skills = []
    for entry in os.listdir(skills_dir):
        skill_path = os.path.join(skills_dir, entry)
        if not os.path.isdir(skill_path):
            continue

        skill_md = os.path.join(skill_path, "SKILL.md")
        if not os.path.isfile(skill_md):
            continue

        nested_files, file_types, hierarchies = _scan_nested_files(skill_path)

        skills.append({
            "name": entry,
            "source": "folder",
            "scope": scope,
            "path": skill_path,
            "nested_files": nested_files,
            "file_types": file_types,
            "hierarchies": hierarchies,
        })

    return skills


def discover_plugin_skills(project_dir: str = None) -> list[dict]:
    """Read installed_plugins.json and scan plugin skill directories."""
    installed_path = os.path.join(
        os.path.expanduser("~"), ".claude", "plugins", "installed_plugins.json"
    )

    if not os.path.isfile(installed_path):
        return []

    try:
        with open(installed_path) as f:
            installed = json.load(f)
    except (json.JSONDecodeError, OSError):
        return []

    # Format: {"version": 2, "plugins": {"name@marketplace": [{"scope":..., "installPath":...}, ...]}}
    plugins_dict = installed.get("plugins", installed)
    if not isinstance(plugins_dict, dict):
        return []

    skills = []
    for plugin_key, installations in plugins_dict.items():
        # Each plugin can have multiple installations (different scopes)
        if not isinstance(installations, list):
            continue

        # Extract plugin name from key format "plugin_name@marketplace"
        plugin_name = plugin_key.split("@")[0] if "@" in plugin_key else plugin_key

        for plugin_info in installations:
            if not isinstance(plugin_info, dict):
                continue

            install_path = plugin_info.get("installPath", "")
            scope = plugin_info.get("scope", "user")

            # Look for skills in the plugin's skills/ directory
            # Check both top-level skills/ and .claude/skills/
            for skills_subdir in ("skills", os.path.join(".claude", "skills")):
                plugin_skills_dir = os.path.join(install_path, skills_subdir)
                if not os.path.isdir(plugin_skills_dir):
                    continue

                for entry in os.listdir(plugin_skills_dir):
                    skill_path = os.path.join(plugin_skills_dir, entry)
                    if not os.path.isdir(skill_path):
                        continue

                    skill_md = os.path.join(skill_path, "SKILL.md")
                    if not os.path.isfile(skill_md):
                        continue

                    nested_files, file_types, hierarchies = _scan_nested_files(skill_path)

                    # Prefix with plugin name to match Claude Code's
                    # invocation format (e.g., "vibeflow:manage-work")
                    prefixed_name = f"{plugin_name}:{entry}"

                    skills.append({
                        "name": prefixed_name,
                        "source": "plugin",
                        "scope": scope,
                        "path": skill_path,
                        "nested_files": nested_files,
                        "file_types": file_types,
                        "hierarchies": hierarchies,
                    })

    return skills


def resolve_skill_for_path(
    file_path: str, skill_paths: dict[str, dict] = None
) -> dict | None:
    """Given an absolute file path, return the SkillInfo dict if inside a skill directory."""
    if skill_paths is None:
        return None

    # Normalize path for comparison
    file_path = os.path.normpath(file_path)

    for skill_root, skill_info in skill_paths.items():
        skill_root = os.path.normpath(skill_root)
        if file_path.startswith(skill_root + os.sep) or file_path.startswith(skill_root + "/"):
            relative_path = os.path.relpath(file_path, skill_root)
            file_type, hierarchy = classify_file(relative_path)
            return {
                "skill_name": skill_info["name"],
                "relative_path": relative_path,
                "file_type": file_type,
                "hierarchy": hierarchy,
            }

    return None


def classify_file(relative_path: str) -> tuple[str, str]:
    """Classify a file within a skill by type and hierarchy.

    Returns:
        Tuple of (file_type, hierarchy) where:
        - file_type: "markdown" | "script" | "asset" | "reference" | "config"
        - hierarchy: "content" | "script"
    """
    parts = relative_path.replace("\\", "/").split("/")
    filename = parts[-1]
    ext = os.path.splitext(filename)[1].lower()

    # Scripts directory
    if parts[0] == "scripts":
        return ("script", "script")

    # Data directory
    if parts[0] == "data":
        return ("asset", "script")

    # References directory
    if parts[0] == "references":
        return ("reference", "content")

    # Assets directory
    if parts[0] == "assets":
        if ext == ".md":
            return ("reference", "content")
        return ("asset", "content")

    # Top-level config files
    if ext in (".json", ".yaml", ".yml"):
        return ("config", "script")

    # Top-level markdown files
    if ext == ".md":
        return ("markdown", "content")

    # Default
    return ("asset", "script")


def _scan_nested_files(skill_path: str) -> tuple[list[str], dict[str, str], dict[str, str]]:
    """Walk a skill directory and collect nested files with classifications."""
    nested_files = []
    file_types = {}
    hierarchies = {}

    for root, _dirs, files in os.walk(skill_path):
        for fname in files:
            abs_path = os.path.join(root, fname)
            rel_path = os.path.relpath(abs_path, skill_path)
            nested_files.append(rel_path)
            ft, hier = classify_file(rel_path)
            file_types[rel_path] = ft
            hierarchies[rel_path] = hier

    return nested_files, file_types, hierarchies
