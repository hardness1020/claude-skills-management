# Tech Spec — plugin-packaging

**Version:** v1.0.0
**File:** docs/specs/spec-plugin-packaging.md
**Status:** Current
**PRD:** `docs/prds/prd.md` (v1.0.0)
**Discovery:** `docs/discovery/disco-4.md` (v1.0.0)
**Contract Versions:** Plugin Manifest v2 • Hooks Config v1

## Table of Contents

- [Overview & Goals](#overview--goals)
- [Architecture](#architecture)
- [Interfaces & Data Contracts](#interfaces--data-contracts)
- [Data & Storage](#data--storage)
- [Reliability & SLIs/SLOs](#reliability--slisslos)
- [Security & Privacy](#security--privacy)
- [Evaluation Plan](#evaluation-plan)

## Overview & Goals

Package the skills analytics system as a Claude Code plugin so users can install it once and have hooks fire across all projects without cloning this repo.

**Goals:**
- One-command install: `claude plugin install skills-analytics`
- Hooks auto-registered at user scope, firing in every project
- Dashboard launchable via `/analytics-dashboard` skill
- No cloning or manual `settings.json` editing required
- Fix existing `resolve_skill_for_path` bug (always returns None)

**Non-Goals:**
- Publishing to a marketplace (local/git install is sufficient for now)
- Project-level dashboard filtering (tracked separately in `docs/TODO.md`)
- Changes to analytics logic or dashboard UI

**Links:**
- Discovery: `docs/discovery/disco-4.md`
- ADR: `docs/adrs/adr-1-plugin-packaging.md`
- Parent spec: `docs/specs/spec-skills-analytics.md`

## Architecture

### Topology

```
Plugin Install (user scope)
│
├── ~/.claude/plugins/installed_plugins.json
│   └── "skills-analytics@...": [{"scope": "user", "installPath": "~/.claude/plugins/cache/..."}]
│
├── ${CLAUDE_PLUGIN_ROOT}/
│   ├── .claude-plugin/plugin.json     ← plugin metadata
│   ├── hooks/hooks.json               ← hook declarations (auto-registered)
│   ├── scripts/
│   │   ├── log_event.py               ← PreToolUse hook (Skill|Read)
│   │   ├── inventory_snapshot.py      ← UserPromptSubmit hook
│   │   ├── db.py                      ← shared DB module
│   │   └── skill_discovery.py         ← shared discovery module
│   ├── dashboard/                     ← Django app (unchanged)
│   └── skills/
│       └── analytics-dashboard/
│           └── SKILL.md               ← /analytics-dashboard skill
│
└── ${CLAUDE_PLUGIN_DATA}/
    └── skills_analytics.db            ← persistent SQLite DB (survives updates)
```

### Component Inventory

| Component | Change Type | Purpose |
|-----------|------------|---------|
| `.claude-plugin/plugin.json` | **NEW** | Plugin metadata for `claude plugin install` |
| `hooks/hooks.json` | **NEW** | Hook declarations replacing `.claude/settings.json` |
| `skills/analytics-dashboard/SKILL.md` | **NEW** | Skill to launch the Django dashboard |
| `scripts/log_event.py` | **FIX** | Populate `skill_paths` before calling `resolve_skill_for_path` |
| `dashboard/analytics_project/settings.py` | **MINOR** | Generate `SECRET_KEY` on first run |
| `.claude/settings.json` | **KEEP** | Preserved for development; not used by plugin consumers |
| All other files | **UNCHANGED** | No modifications needed |

## Interfaces & Data Contracts

### Plugin Manifest (`.claude-plugin/plugin.json`)

```json
{
  "name": "skills-analytics",
  "version": "1.0.0",
  "description": "Track and analyze Claude Code skill usage with a local dashboard",
  "author": { "name": "Marcus Chang" },
  "repository": "https://github.com/hardness1020/claude-skills-management",
  "license": "MIT",
  "keywords": ["analytics", "skills", "dashboard", "usage-tracking"]
}
```

Required fields: `name`, `version`, `description`.
Optional fields: `author`, `repository`, `license`, `keywords`, `homepage`.

### Hooks Declaration (`hooks/hooks.json`)

```json
{
  "description": "Skills analytics usage tracking hooks",
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Skill|Read",
        "hooks": [
          {
            "type": "command",
            "command": "${CLAUDE_PLUGIN_ROOT}/scripts/log_event.py",
            "timeout": 10
          }
        ]
      }
    ],
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "${CLAUDE_PLUGIN_ROOT}/scripts/inventory_snapshot.py",
            "timeout": 10
          }
        ]
      }
    ]
  }
}
```

**Key difference from `.claude/settings.json`:**
- Uses `${CLAUDE_PLUGIN_ROOT}` instead of `$CLAUDE_PROJECT_DIR`
- Hooks are auto-registered on plugin install — no manual editing
- Scope is determined by the plugin installation scope (user/project/local)

### Dashboard Skill (`skills/analytics-dashboard/SKILL.md`)

The SKILL.md file defines a user-invocable skill `/analytics-dashboard` that:
1. Starts the Django development server on port 8787
2. Opens the dashboard URL in the user's browser (if possible)
3. Provides instructions for stopping the server

The skill instructs Claude to run:
```bash
cd "${CLAUDE_PLUGIN_ROOT}" && uv run python -m django runserver 8787 --settings=dashboard.analytics_project.settings
```

### log_event.py Fix — `resolve_skill_for_path`

**Current (broken):**
```python
result = skill_discovery.resolve_skill_for_path(file_path)
# skill_paths defaults to None → always returns None
```

**Fixed:**
```python
# Build skill_paths map from discover_all()
all_skills = skill_discovery.discover_all(project_dir=data.get("cwd", ""))
skill_paths = {s["path"]: s for s in all_skills}

result = skill_discovery.resolve_skill_for_path(file_path, skill_paths=skill_paths)
```

**Performance note:** `discover_all()` is called once per hook invocation. For the Read matcher, this adds ~10-50ms depending on skill count. This is acceptable given the 10s timeout, but could be optimized later with caching if needed.

### Django SECRET_KEY Generation

**Current:**
```python
SECRET_KEY = "dev-secret-key-change-in-production"
```

**Fixed:**
```python
import os
from pathlib import Path

def _get_secret_key():
    plugin_data = os.environ.get(
        "CLAUDE_PLUGIN_DATA",
        os.path.expanduser("~/.skills-analytics"),
    )
    secret_path = Path(plugin_data) / "django_secret.txt"
    if secret_path.exists():
        return secret_path.read_text().strip()
    from django.core.management.utils import get_random_secret_key
    key = get_random_secret_key()
    Path(plugin_data).mkdir(parents=True, exist_ok=True)
    secret_path.write_text(key)
    return key

SECRET_KEY = _get_secret_key()
```

## Data & Storage

### No Schema Changes

The DB schema is unchanged. All existing tables (`skills`, `skill_files`, `skill_invocations`, `file_accesses`, `skill_lifecycle`, `inventory_snapshots`) remain as-is.

The `project_dir` column already exists on `skill_invocations` and `file_accesses` — it's populated by the hooks from `data.get("cwd", "")`. No migration needed.

### Storage Path

| Context | DB Path |
|---------|---------|
| Plugin installed | `${CLAUDE_PLUGIN_DATA}/skills_analytics.db` |
| Development (cloned repo) | `~/.skills-analytics/skills_analytics.db` (fallback) |

Both paths are already handled by `db.get_connection()`.

## Reliability & SLIs/SLOs

### No SLO Changes

All existing SLOs from `spec-skills-analytics.md` remain unchanged:

| SLI | Target |
|-----|--------|
| Hook latency (Skill matcher) | < 20ms p95 |
| Hook latency (Read, non-skill path) | < 5ms p95 |
| Hook latency (Read, skill path) | < 20ms p95 |
| Inventory snapshot | < 500ms p95 |

**Note:** The `log_event.py` fix adds `discover_all()` to the Read path, which may push latency above 5ms for non-skill paths. The 20ms target for skill paths should still hold. If profiling shows issues, add a cache (file-based or in-memory with TTL).

### Fault Tolerance

- Hook scripts continue to never block Claude Code — all errors caught and logged to stderr
- If `${CLAUDE_PLUGIN_ROOT}` is misconfigured, scripts fail gracefully (empty output + allow)
- If `${CLAUDE_PLUGIN_DATA}` is unset, falls back to `~/.skills-analytics/`

## Security & Privacy

### No Security Changes

- Dashboard remains localhost-only (`127.0.0.1:8787`)
- No authentication (local-only system)
- No new data collected
- `SECRET_KEY` improvement: generated once and stored in `${CLAUDE_PLUGIN_DATA}/django_secret.txt` instead of hardcoded

## Evaluation Plan

### Test Strategy

| Test Type | Scope | What to Test |
|-----------|-------|-------------|
| Unit | `log_event.py` fix | `_handle_file_read` populates `skill_paths` and resolves correctly |
| Unit | Plugin config files | `plugin.json` has required fields, `hooks.json` schema is valid |
| Integration | Hook → DB with plugin paths | Simulate hook invocation with `${CLAUDE_PLUGIN_ROOT}` set |
| Manual | Plugin install | `claude plugin install --plugin-dir .` installs cleanly, hooks fire |
| Manual | Dashboard skill | `/analytics-dashboard` starts the server |

### Quality Gates

- All existing tests pass (96 tests)
- `plugin.json` validates against Claude Code plugin schema
- `hooks.json` validates against Claude Code hooks schema
- Hook scripts run correctly when invoked via `${CLAUDE_PLUGIN_ROOT}/scripts/`
- Dashboard starts via the skill command

---

## References

- Discovery: `docs/discovery/disco-4.md`
- ADR: `docs/adrs/adr-1-plugin-packaging.md`
- Parent spec: `docs/specs/spec-skills-analytics.md`
- Reference implementation: vibeflow plugin at `~/.claude/plugins/cache/vibeflow/vibeflow/1.0.0/`
