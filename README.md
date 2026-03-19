# Skills Analytics for Claude Code

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Django](https://img.shields.io/badge/Django-4.2-092E20?logo=django&logoColor=white)](https://www.djangoproject.com/)
[![SQLite](https://img.shields.io/badge/SQLite-WAL-003B57?logo=sqlite&logoColor=white)](https://www.sqlite.org/)
[![Claude Code](https://img.shields.io/badge/Claude_Code-Plugin-D97757?logo=anthropic&logoColor=white)](https://claude.ai/claude-code)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

An open-source Claude Code plugin that tracks skill usage and analyzes whether your skills are actually useful.

Skills accumulate over time — from `.claude/skills/` folders and installed plugins — but there's no way to know which ones deliver value and which are dead weight. This plugin logs every skill invocation and nested file access, then provides a local dashboard with time-normalized analytics to answer: **which skills should I keep, improve, or remove?**

## What it does

**Data collection** (runs automatically via Claude Code hooks):
- Logs every skill invocation with metadata (name, source, scope, timestamp)
- Tracks which nested files within skills are accessed (progressive disclosure coverage)
- Snapshots your skill inventory on each conversation start to detect additions and deletions

**Analytics dashboard** (local Django server, on-demand):
- **Frequency** — most/least used skills, sortable
- **Adoption** — how quickly new skills gain traction
- **Usefulness scoring** — composite score factoring in usage rate, decay, and engagement depth
- **Trends** — time-series of invocations by day/week/month
- **Structure coverage** — per-skill file tree showing which nested files are triggered vs. dormant

## Why time-normalization matters

Skills are added at different times. A skill installed yesterday with 5 invocations (5/day) is healthier than one installed 3 months ago with 30 invocations (0.3/day). Raw counts are misleading.

The same applies to nested files — a reference doc added last week shouldn't be penalized alongside files that have existed for months.

The usefulness scoring model handles this:

| Factor | What it measures |
|--------|-----------------|
| **Time-normalized usage rate** | Invocations per day since install, with a 7-day grace period for new skills |
| **Usage decay detection** | Is recent usage declining vs. lifetime average? |
| **Engagement depth** | What fraction of a skill's nested files actually get triggered? |

## Skill sources tracked

| Source | Scope | Location |
|--------|-------|----------|
| Folder-based | User | `~/.claude/skills/` |
| Folder-based | Project | `.claude/skills/` |
| Plugin-based | User | Installed for you across all projects |
| Plugin-based | Project | Installed for all collaborators on a repo |
| Plugin-based | Local | Installed for you, in one repo only |

Deleted skills are preserved in the dashboard as "removed" with full historical data.

## Installation

Requires Python 3.10+ and [uv](https://docs.astral.sh/uv/).

```bash
# Clone the repo
git clone https://github.com/your-username/agent-skills-management.git
cd agent-skills-management

# Install dependencies
uv sync --dev
```

### Configure Claude Code hooks

Add the following to your Claude Code settings (`.claude/settings.json` or `~/.claude/settings.json`):

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Skill|Read",
        "hooks": [
          {
            "type": "command",
            "command": "uv run python /path/to/agent-skills-management/scripts/log_event.py",
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
            "command": "uv run python /path/to/agent-skills-management/scripts/inventory_snapshot.py",
            "timeout": 10
          }
        ]
      }
    ]
  }
}
```

Replace `/path/to/agent-skills-management` with the actual path.

### Launch the dashboard

```bash
uv run python -m django runserver 8787 --settings=dashboard.analytics_project.settings
```

Open http://localhost:8787 to view the dashboard.

## Architecture

```
Claude Code Session
    |
    |-- PreToolUse (Skill)  -->  log_event.py  -->  SQLite
    |-- PreToolUse (Read)   -->  log_event.py  -->  SQLite
    |-- UserPromptSubmit    -->  inventory_snapshot.py --> SQLite
    |
    |           Django Dashboard (localhost:8787)
    |               |
    |               +-- reads from same SQLite
```

Hooks are short-lived Python scripts using only stdlib (`sqlite3`, `json`, `sys`). No Django import overhead in the hot path. The dashboard is a separate process that reads the same SQLite database.

All data stays local. No telemetry, no remote calls.

## Project structure

```
scripts/                          # Hook scripts (stdlib only, fast)
    db.py                         # SQLite connection, schema, CRUD
    skill_discovery.py            # Scan folder + plugin skill sources
    log_event.py                  # PreToolUse hook entry point
    inventory_snapshot.py         # UserPromptSubmit hook entry point

dashboard/                        # Django dashboard (on-demand)
    analytics/
        analytics.py              # Usefulness scoring, trends, coverage
        views.py                  # API endpoints + HTML dashboard
    analytics_project/
        settings.py
        urls.py

tests/
    hooks/                        # Tests for scripts/
    dashboard/                    # Tests for dashboard/
```

## API endpoints

All endpoints accept `start` and `end` query parameters (ISO 8601).

| Endpoint | Description |
|----------|-------------|
| `GET /` | HTML dashboard |
| `GET /api/frequency/` | Skills ranked by invocation count |
| `GET /api/adoption/` | First-use dates and cumulative curves |
| `GET /api/usefulness/` | Composite usefulness scores with breakdowns |
| `GET /api/trends/?granularity=day` | Time-series by day/week/month |
| `GET /api/coverage/<skill>/` | Per-file access counts with time metrics |
| `GET /api/skills/` | Full skill inventory with status |

## Running tests

```bash
uv run python -m pytest tests/ -v
```

96 tests (84 unit + 12 integration), runs in < 0.5s.

## License

MIT
