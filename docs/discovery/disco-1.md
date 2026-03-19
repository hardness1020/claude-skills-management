# Discovery — Claude Code Skills Analytics (#ft-1)

**Version:** v1.0.0
**File:** docs/discovery/disco-1.md
**Last_updated:** 2026-03-18

## Summary

Greenfield project analyzed for building a Claude Code plugin that tracks skill usage analytics. Key findings: (1) PreToolUse hook with `Skill` and `Read` matchers captures invocations and nested file accesses; (2) UserPromptSubmit hook enables periodic skill inventory snapshots for add/remove detection; (3) `${CLAUDE_PLUGIN_DATA}` provides persistent SQLite storage; (4) Skills exist in 4 sources — `~/.claude/skills/`, `.claude/skills/`, plugin caches, and project-scoped plugins — all discoverable via filesystem scanning and `installed_plugins.json`. No blockers identified. **Recommendation: GO.**

## Phase 0: Spec Discovery

This is a greenfield project — no existing specs or code beyond LICENSE and README. The PRD (`docs/prds/prd.md`) defines all requirements. Key specs needed:

- **Log schema spec**: JSON event format for `skill_invoked`, `nested_file_accessed`, `skill_added`, `skill_removed`
- **Hook implementation spec**: How PreToolUse and UserPromptSubmit hooks collect data
- **Django app spec**: Models, views, and dashboard components
- **Usefulness scoring spec**: Algorithm details for the 4-factor composite score

## Phase 1: Claude Code Hook System Analysis

### Hook Types Available

| Hook Event | When It Fires | Relevant to Us |
|------------|---------------|----------------|
| `PreToolUse` | Before tool execution | **Primary** — captures skill invocations and file reads |
| `UserPromptSubmit` | When user submits a prompt | **Primary** — skill inventory snapshots |
| `PostToolUse` | After tool succeeds | Could capture duration, but PreToolUse is sufficient for v1 |
| `SessionStart` | Session begins | Could initialize state, not needed for v1 |

### PreToolUse Hook — Data Available

The hook receives JSON on stdin:

```json
{
  "session_id": "abc123",
  "transcript_path": "/Users/.../.claude/projects/.../transcript.jsonl",
  "cwd": "/Users/my-project",
  "hook_event_name": "PreToolUse",
  "tool_name": "Skill",
  "tool_use_id": "toolu_01ABC123...",
  "tool_input": {
    "skill": "skill-name",
    "args": "optional arguments"
  }
}
```

**Key finding: Skill invocations use the `Skill` tool.** When a user invokes `/my-skill`, the `tool_name` is `"Skill"` and `tool_input.skill` contains the skill name. This is the primary data point for logging skill invocations.

**For nested file access tracking:** When Claude reads a file within a skill directory, `tool_name` is `"Read"` and `tool_input.file_path` contains the path. We can detect if this path falls within a known skill directory to log it as a nested file access.

**Hook matcher for skills:** `"Skill"` matches skill invocations. `"Read"` matches file reads. We need two matchers.

### PreToolUse Hook — Output Format

The hook must output JSON to stdout:

```json
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "allow"
  }
}
```

We always return `"allow"` — our hook is passive (logging only), never blocking.

### UserPromptSubmit Hook — Data Available

```json
{
  "session_id": "abc123",
  "cwd": "/Users/my-project",
  "hook_event_name": "UserPromptSubmit",
  "prompt": "user's message text"
}
```

This fires on every conversation turn — ideal for periodic inventory snapshots.

### Hook Configuration Location

Hooks are configured in `settings.json` at multiple levels:

| Scope | File |
|-------|------|
| User | `~/.claude/settings.json` |
| Project | `.claude/settings.json` |
| Local | `.claude/settings.local.json` |
| Plugin | `hooks/hooks.json` within plugin directory |

**Decision: Package as a plugin** — this lets us ship hooks in `hooks/hooks.json`, use `${CLAUDE_PLUGIN_ROOT}` for script paths, and `${CLAUDE_PLUGIN_DATA}` for persistent storage (SQLite DB + logs).

### Environment Variables Available to Hooks

```bash
CLAUDE_SESSION_ID        # Current session
CLAUDE_PROJECT_DIR       # Project root
CLAUDE_CWD               # Working directory
CLAUDE_PLUGIN_ROOT       # Plugin directory (if hook is in a plugin)
CLAUDE_PLUGIN_DATA       # Persistent data dir: ~/.claude/plugins/data/{id}/
```

`CLAUDE_PLUGIN_DATA` is critical — it persists across sessions and plugin updates, perfect for our SQLite database.

## Phase 2: Skill Source & Scope Architecture

### Skill Sources and Locations

| Source | Location | How to Discover |
|--------|----------|-----------------|
| Folder-based (project) | `.claude/skills/` in project repo | Scan directory |
| Folder-based (user) | `~/.claude/skills/` | Scan directory |
| Plugin-based | `~/.claude/plugins/cache/{marketplace}/{plugin}/{version}/skills/` | Read `~/.claude/plugins/installed_plugins.json` |

### Plugin Scope Detection

`~/.claude/plugins/installed_plugins.json` contains all installed plugins with scope metadata:

```json
{
  "plugin-name@marketplace": {
    "scope": "user|local",
    "installPath": "~/.claude/plugins/cache/...",
    "version": "1.0.0",
    "projectPath": "/path/to/project"  // for local scope
  }
}
```

**Project-scope plugins** are defined in `.claude/settings.json` under `enabledPlugins`.

**Scope detection strategy:**
1. Read `~/.claude/plugins/installed_plugins.json` → get user-scope and local-scope plugins
2. Read `.claude/settings.json` in project → get project-scope enabled plugins
3. Scan `~/.claude/skills/` → user folder-based skills
4. Scan `.claude/skills/` in project → project folder-based skills

### Skill File Hierarchy

Each skill has a directory structure. Nested files fall into two hierarchies:

**Content hierarchy** (progressive disclosure for Claude):
```
skill-name/
├── SKILL.md                    # Always loaded (entry point)
├── references/                 # Loaded on demand
│   ├── guide.md
│   └── examples.md
└── assets/                     # Templates loaded on demand
    └── template.md
```

**Script hierarchy** (executed by hooks or dynamic context):
```
skill-name/
├── scripts/                    # Executed by hooks or !`command` syntax
│   ├── validate.py
│   └── helper.sh
└── data/                       # Supporting data files
    └── config.json
```

**Key insight:** A `Read` tool call to a path inside a skill's `references/` is a content hierarchy access. A `Bash` tool call running a script in `scripts/` is a script hierarchy access. We can classify based on path patterns.

## Phase 3: Dependency & Side Effect Mapping

### External Dependencies

| Dependency | Purpose | Version Constraint |
|------------|---------|-------------------|
| Python 3.10+ | Runtime | Already required by Claude Code |
| Django 4.2+ | Web framework + ORM | LTS version |
| SQLite | Database | Bundled with Python |
| Chart.js | Dashboard charts | CDN or bundled |

### Data Flow

```
Claude Code Session
    │
    ├── UserPromptSubmit hook
    │   └── inventory_snapshot.py
    │       ├── Scans skill sources (folder + plugin)
    │       ├── Diffs against previous snapshot
    │       ├── Writes skill_added/skill_removed events → SQLite
    │       └── Stores current snapshot → SQLite
    │
    ├── PreToolUse hook (matcher: "Skill")
    │   └── log_skill_invocation.py
    │       └── Writes skill_invoked event → SQLite
    │
    ├── PreToolUse hook (matcher: "Read")
    │   └── log_file_access.py
    │       ├── Checks if file_path is inside a known skill directory
    │       ├── If yes: classifies as content/script hierarchy
    │       └── Writes nested_file_accessed event → SQLite
    │
    └── (Django dashboard reads from same SQLite)
```

### Side Effects

- **Hook latency**: Every `Read` tool call goes through our hook. Must be fast (< 50ms). Path-matching against skill directories is the hot path.
- **SQLite write contention**: Hooks and dashboard may access DB simultaneously. SQLite WAL mode handles this.
- **Disk usage**: Log events accumulate. Need a retention/archival strategy.

### File System Locations

| Component | Path |
|-----------|------|
| SQLite DB | `${CLAUDE_PLUGIN_DATA}/skills_analytics.db` |
| Hook scripts | `${CLAUDE_PLUGIN_ROOT}/scripts/` |
| Django app | `${CLAUDE_PLUGIN_ROOT}/dashboard/` |
| Inventory snapshots | Stored as rows in SQLite, not separate files |

## Phase 4: Reusable Component Discovery

### Existing Patterns to Follow

1. **Plugin packaging**: Follow the same structure as vibeflow plugin — `hooks/hooks.json`, `skills/`, `scripts/`, `.claude-plugin/plugin.json`
2. **Hook script pattern**: Use Python scripts invoked via `type: "command"`, reading JSON from stdin, writing JSON to stdout
3. **Persistent storage**: Use `${CLAUDE_PLUGIN_DATA}` for SQLite DB — survives plugin updates
4. **Skill frontmatter**: Follow standard SKILL.md frontmatter for the dashboard launch skill

### Components to Build

| Component | Type | Description |
|-----------|------|-------------|
| `scripts/log_skill_invocation.py` | Hook script | PreToolUse handler for Skill tool — logs invocations |
| `scripts/log_file_access.py` | Hook script | PreToolUse handler for Read tool — logs nested file accesses within skills |
| `scripts/inventory_snapshot.py` | Hook script | UserPromptSubmit handler — snapshots skill inventory, diffs for adds/removes |
| `scripts/db.py` | Shared module | SQLite schema, connection, write helpers |
| `scripts/skill_discovery.py` | Shared module | Scans folder/plugin skill sources, resolves scopes |
| `dashboard/` | Django app | Models, views, templates, static assets for the single-page dashboard |
| `dashboard/analytics.py` | Module | Usefulness scoring: time-normalized rate, decay, depth, composite |
| `hooks/hooks.json` | Config | Hook definitions wiring PreToolUse and UserPromptSubmit to scripts |
| `.claude-plugin/plugin.json` | Config | Plugin manifest |
| `skills/analytics-dashboard/SKILL.md` | Skill | User-invocable skill to launch/open the dashboard |

## Risk Assessment & Go/No-Go Recommendation

### Risks Identified

| Risk | Severity | Mitigation |
|------|----------|------------|
| **Read hook latency**: Every file read goes through our hook. If slow, it degrades Claude's performance. | High | Fast path check: maintain an in-memory set of skill directory prefixes. If file path doesn't match any prefix, exit immediately (< 5ms). |
| **Skill tool_input format may vary**: The Skill tool's `tool_input` structure needs verification — we're assuming `tool_input.skill` contains the skill name. | Medium | Verify by inspecting actual hook payloads during development. Add defensive parsing. |
| **Plugin-scope detection complexity**: Distinguishing user/project/local scope requires reading multiple config files. | Medium | Build a unified `skill_discovery.py` module that handles all sources. Test with real configs. |
| **SQLite WAL mode on network filesystems**: If `CLAUDE_PLUGIN_DATA` is on a network mount, WAL may not work. | Low | Document requirement for local filesystem. |

### Go/No-Go

**GO** — All core data points are accessible through existing Claude Code hook infrastructure:

- Skill invocations → PreToolUse hook with `Skill` matcher
- Nested file reads → PreToolUse hook with `Read` matcher + path matching
- Skill inventory → UserPromptSubmit hook + filesystem/config scanning
- Persistent storage → `CLAUDE_PLUGIN_DATA` + SQLite
- Distribution → Standard plugin packaging

No blockers identified. The main technical risk (Read hook latency) has a clear mitigation path.
