# ADR: Package as a Claude Code Plugin

**File:** docs/adrs/adr-1-plugin-packaging.md
**Status:** Accepted
**Date:** 2026-03-18
**Decision Makers:** Marcus Chang

## Context

We need to decide how to distribute and install the skills analytics system. The system consists of:
- Hook scripts (PreToolUse, UserPromptSubmit) that must run inside Claude Code sessions
- A Django dashboard that runs as a local web server
- A SQLite database for persistent storage

Claude Code supports two primary distribution mechanisms:
1. **Plugin packaging** — distributed via marketplaces or local install, with structured directories for hooks, skills, and scripts
2. **Manual setup** — users copy files into `.claude/` directories and configure hooks in `settings.json` by hand

The hooks must integrate tightly with Claude Code's lifecycle, and the database must persist across sessions and plugin updates.

## Decision

We will adopt **Claude Code plugin packaging** because it provides the most seamless installation experience and gives us access to `${CLAUDE_PLUGIN_DATA}` for persistent storage.

Key aspects:
- Plugin structure follows the standard layout: `.claude-plugin/plugin.json`, `hooks/hooks.json`, `scripts/`, `dashboard/`, `skills/`
- Hooks are declared in `hooks/hooks.json` and automatically registered on install — no manual `settings.json` editing
- `${CLAUDE_PLUGIN_ROOT}` provides stable references to hook scripts
- `${CLAUDE_PLUGIN_DATA}` provides a persistent directory (`~/.claude/plugins/data/{id}/`) that survives plugin updates, ideal for the SQLite database
- Users install via `claude plugin install` with scope selection (user/project/local)
- A user-invocable skill (`/analytics-dashboard`) launches the Django server

## Consequences

### Positive

+ One-command installation: `claude plugin install skills-analytics`
+ Hooks are auto-registered — no manual configuration needed
+ `${CLAUDE_PLUGIN_DATA}` provides persistent, update-safe storage for the SQLite database
+ Plugin scoping (user/project/local) lets teams control where analytics runs
+ Distribution via marketplace enables easy updates
+ Standard plugin structure is familiar to the Claude Code ecosystem

### Negative

- Users must have Claude Code plugin support (available in current versions)
- Plugin updates require marketplace publishing workflow
- The Django dashboard is bundled inside the plugin directory, which is less conventional than a standalone Python package

### Neutral

* Plugin cache lives at `~/.claude/plugins/cache/` — standard location, no surprises
* Plugin can be developed locally with `--plugin-dir` flag during development

## Alternatives Considered

### Alternative 1: Manual `.claude/` Setup

**Description:** Users manually copy hook scripts into their project's `.claude/hooks/` directory and add hook configuration to `.claude/settings.json`.

**Pros:**
- No plugin infrastructure dependency
- Full user control over configuration

**Cons:**
- Error-prone manual setup (JSON editing, path configuration)
- No `${CLAUDE_PLUGIN_DATA}` — must pick a storage location manually
- No automatic updates
- Hard to share across teams

**Why not chosen:** The installation friction would severely limit adoption. The main value proposition is ease of use — manual setup contradicts that.

### Alternative 2: Standalone Python Package (pip install)

**Description:** Distribute as a PyPI package that installs a CLI tool. The CLI generates the hook configuration and manages the Django server.

**Pros:**
- Familiar Python packaging ecosystem
- Can be used outside Claude Code context
- Easier to test in isolation

**Cons:**
- Still requires manual hook wiring into Claude Code settings
- No access to `${CLAUDE_PLUGIN_DATA}` — must manage storage path independently
- Two installation steps (pip install + configure hooks)
- Version drift between pip package and Claude Code hook expectations

**Why not chosen:** The two-step installation and manual hook wiring negates the convenience advantage. Plugin packaging handles both in one step.

## Rollback Plan

1. Extract hook scripts and Django app from plugin into standalone directories
2. Write a setup script that adds hook configuration to `~/.claude/settings.json`
3. Update storage path from `${CLAUDE_PLUGIN_DATA}` to a user-configurable location (e.g., `~/.skills-analytics/`)
4. Distribute as a git repository with setup instructions

**Estimated rollback effort:** Medium
**Data considerations:** SQLite database can be copied from `${CLAUDE_PLUGIN_DATA}` to the new location without migration — it's a single file.

## Links

**PRD:** `docs/prds/prd.md`
**TECH-SPECs:** `docs/specs/spec-skills-analytics.md`
**FEATUREs:** None yet
**Related ADRs:** `docs/adrs/adr-1-sqlite-storage.md` (pending)
