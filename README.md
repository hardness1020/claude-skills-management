# Skills Analytics for Claude Code

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Django](https://img.shields.io/badge/Django-4.2-092E20?logo=django&logoColor=white)](https://www.djangoproject.com/)
[![SQLite](https://img.shields.io/badge/SQLite-WAL-003B57?logo=sqlite&logoColor=white)](https://www.sqlite.org/)
[![Claude Code](https://img.shields.io/badge/Claude_Code-Plugin-D97757?logo=anthropic&logoColor=white)](https://claude.ai/claude-code)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**Stop guessing which skills matter.** This Claude Code plugin tracks every skill invocation across all your projects and scores each one. You know what to keep, improve, or remove.

## Demo

https://github.com/user-attachments/assets/0eeb34f8-f564-4022-a1c3-d1062d5825f9

You have skills accumulating over time but there's no way to know which ones deliver value and which are dead weight. Install this plugin once, and it logs every skill invocation and nested file access via Claude Code hooks across every project, then provides a local dashboard with time-normalized analytics to answer: **which skills should I keep, improve, or remove?**

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

| Factor                               | What it measures                                                            |
| ------------------------------------ | --------------------------------------------------------------------------- |
| **Time-normalized usage rate** | Invocations per day since install, with a 7-day grace period for new skills |
| **Usage decay detection**      | Is recent usage declining vs. lifetime average?                             |
| **Engagement depth**           | What fraction of a skill's nested files actually get triggered?             |

## Skill sources tracked

| Source       | Scope   | Location                                  |
| ------------ | ------- | ----------------------------------------- |
| Folder-based | User    | `~/.claude/skills/`                     |
| Folder-based | Project | `.claude/skills/`                       |
| Plugin-based | User    | Installed for you across all projects     |
| Plugin-based | Project | Installed for all collaborators on a repo |
| Plugin-based | Local   | Installed for you, in one repo only       |

Deleted skills are preserved in the dashboard as "removed" with full historical data.

## Installation

Requires Python 3.10+ and [uv](https://docs.astral.sh/uv/).

### 1. Add the marketplace and install

```bash
claude plugin marketplace add hardness1020/claude-skills-management
claude plugin install skills-analytics
```

Installs at user scope by default, tracking skill usage across all your projects. Hooks are auto-registered, no manual `settings.json` editing needed.

### 2. Restart Claude Code

Start a new Claude Code session for the hooks to take effect. Every prompt you submit will now snapshot your skill inventory, and every skill invocation or file read will be logged.

### 3. Launch the dashboard

Use the `/skills-analytics-dashboard` skill in any Claude Code session. It starts a local server and opens the dashboard at http://localhost:8787.


## Architecture

```
Claude Code Session (any project)
    |
    |-- UserPromptSubmit         -->  inventory_snapshot.py --> SQLite
    |-- PreToolUse (Skill|Read)  -->  log_event.py  -->  SQLite
    |
    |           Django Dashboard (localhost:8787)
    |               |
    |               +-- reads from same SQLite
```

Hooks are short-lived Python scripts using only stdlib (`sqlite3`, `json`, `sys`). No Django import overhead in the hot path. The dashboard is a separate process that reads the same SQLite database.

All data stays local in `~/.claude/plugins/data/skills-analytics-claude-skills-management/skills_analytics.db`. No telemetry, no remote calls. One shared database across all projects.

## Known Issues

- **User slash commands are not tracked.** The project records agent-initiated skill calls via `PreToolUse` on `Skill('skill-name')`, but user slash commands (`/skill-name`) bypass the tool hook pipeline entirely and are not captured.
- **Subagent behavior is unverified.** It is unclear whether `PreToolUse` hooks fire for tool calls made by subagents (spawned via the Agent tool). File reads inside subagents may not be captured.
- **Skill scripts invoked via Bash are not tracked.** When a skill's logic is triggered by a shell command (e.g., `uv run python scripts/...`) rather than the `Skill` tool, `PreToolUse` fires for `Bash` — not `Skill` — so the invocation is not attributed to the skill.

## Project structure

```
├── .claude-plugin/
│   └── plugin.json                    # Plugin metadata for claude plugin install
├── hooks/
│   └── hooks.json                     # Hook declarations (auto-registered on install)
├── skills/
│   └── skills-analytics-dashboard/
│       └── SKILL.md                   # /skills-analytics-dashboard skill
├── scripts/                           # Hook scripts (stdlib only, fast)
│   ├── db.py                          # SQLite connection, schema, CRUD
│   ├── skill_discovery.py             # Scan folder + plugin skill sources
│   ├── log_event.py                   # PreToolUse hook entry point
│   └── inventory_snapshot.py          # UserPromptSubmit hook entry point
├── dashboard/                         # Django dashboard (on-demand)
│   ├── analytics/
│   │   ├── analytics.py               # Usefulness scoring, trends, coverage
│   │   ├── views.py                   # API endpoints + HTML dashboard
│   │   └── templates/analytics/
│   │       └── dashboard.html         # Single-page dashboard UI
│   └── analytics_project/
│       ├── settings.py
│       └── urls.py
└── tests/
    ├── hooks/                         # Tests for scripts/ and plugin config
    └── dashboard/                     # Tests for dashboard/
```

