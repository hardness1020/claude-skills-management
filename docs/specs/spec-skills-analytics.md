# Tech Spec — skills-analytics

**Version:** v1.0.0
**File:** docs/specs/spec-skills-analytics.md
**Status:** Current
**PRD:** `docs/prds/prd.md` (v1.0.0)
**Discovery:** `docs/discovery/disco-1.md` (v1.0.0)
**Contract Versions:** Event Schema v1.0 • Django Models v1.0

## Table of Contents

- [Overview & Goals](#overview--goals)
- [Architecture](#architecture)
- [Interfaces & Data Contracts](#interfaces--data-contracts)
- [Data & Storage](#data--storage)
- [Reliability & SLIs/SLOs](#reliability--slisslos)
- [Security & Privacy](#security--privacy)
- [Evaluation Plan](#evaluation-plan)

## Overview & Goals

A Claude Code plugin that logs skill invocations, nested file accesses, and skill lifecycle events, then presents analytics through a local Django dashboard. Packaged as a standard Claude Code plugin for easy installation.

**Goals:**
- Capture all skill usage data via Claude Code hooks without impacting performance
- Track skill inventory changes (additions/deletions) across all sources and scopes
- Compute time-normalized usefulness scores that account for different install dates
- Deliver a single-page Django dashboard with 5 analysis views and time interval filtering

**Links:**
- PRD: `docs/prds/prd.md` v1.0.0
- Discovery: `docs/discovery/disco-1.md` v1.0.0

## Architecture

### Topology

```
Claude Code Session
│
├─ UserPromptSubmit ──────────────────────────────────┐
│   hook fires on every conversation turn              │
│                                                      ▼
├─ PreToolUse (matcher: "Skill") ──┐         ┌─────────────────┐
│   hook fires on skill invocation │         │ inventory_      │
│                                  │         │ snapshot.py     │
├─ PreToolUse (matcher: "Read") ──┐│         │                 │
│   hook fires on file read       ││         │ • scan sources  │
│                                 ▼▼         │ • diff snapshot │
│                          ┌──────────────┐  │ • emit add/     │
│                          │ log_event.py │  │   remove events │
│                          │              │  └────────┬────────┘
│                          │ • classify   │           │
│                          │   event type │           │
│                          │ • write to   │           │
│                          │   SQLite     │           │
│                          └──────┬───────┘           │
│                                 │                   │
│                                 ▼                   ▼
│                          ┌─────────────────────────────┐
│                          │  SQLite DB (WAL mode)       │
│                          │  ${CLAUDE_PLUGIN_DATA}/     │
│                          │  skills_analytics.db        │
│                          └──────────────┬──────────────┘
│                                         │
│                                         ▼
│                          ┌─────────────────────────────┐
│                          │  Django Dashboard            │
│                          │  localhost:8787               │
│                          │                              │
│                          │  ┌─────────┐ ┌───────────┐  │
│                          │  │Frequency│ │ Adoption  │  │
│                          │  └─────────┘ └───────────┘  │
│                          │  ┌─────────┐ ┌───────────┐  │
│                          │  │Useful-  │ │  Trends   │  │
│                          │  │ness     │ │           │  │
│                          │  └─────────┘ └───────────┘  │
│                          │  ┌──────────────────────┐   │
│                          │  │ Structure Coverage   │   │
│                          │  └──────────────────────┘   │
│                          └─────────────────────────────┘
```

### Component Inventory

| Component | Framework/Runtime | Purpose | Interfaces | Depends On | Owner |
|-----------|------------------|---------|------------|------------|-------|
| `log_event.py` | Python 3.10+ | Log skill invocations and nested file accesses | In: hook JSON (stdin); Out: hook response (stdout) | `db.py` | Hook scripts |
| `inventory_snapshot.py` | Python 3.10+ | Snapshot skill inventory, diff for adds/removes | In: hook JSON (stdin); Out: hook response (stdout) | `db.py`, `skill_discovery.py` | Hook scripts |
| `skill_discovery.py` | Python 3.10+ | Scan all skill sources and resolve scopes | In: filesystem + config files; Out: `list[SkillInfo]` | None (stdlib only) | Shared module |
| `db.py` | Python 3.10+ / sqlite3 | Database schema, connection, write/read helpers | In: event dicts; Out: query results | None (stdlib only) | Shared module |
| `dashboard/analytics/analytics.py` | Python 3.10+ | Usefulness scoring computations | In: query results; Out: scored skill list | `db.py` | Dashboard |
| Django dashboard | Django 4.2 | Single-page analytics dashboard | In: HTTP GET; Out: HTML + JSON API | `db.py`, `dashboard/analytics/analytics.py` | Web app |
| `hooks/hooks.json` | JSON config | Wire hooks to scripts | N/A | N/A | Plugin config |
| `.claude-plugin/plugin.json` | JSON manifest | Plugin metadata | N/A | N/A | Plugin config |

## Interfaces & Data Contracts

### Hook Input Schema (stdin)

All hooks receive JSON on stdin from Claude Code:

```python
@dataclass
class PreToolUseInput:
    session_id: str
    transcript_path: str
    cwd: str
    hook_event_name: str  # "PreToolUse"
    tool_name: str        # "Skill" | "Read" | ...
    tool_use_id: str
    tool_input: dict      # tool-specific fields

@dataclass
class UserPromptSubmitInput:
    session_id: str
    transcript_path: str
    cwd: str
    hook_event_name: str  # "UserPromptSubmit"
    prompt: str
```

### Hook Output Schema (stdout)

```python
# PreToolUse hooks — always allow, passive logging only
@dataclass
class PreToolUseOutput:
    hookSpecificOutput: dict
    # Always: {"hookEventName": "PreToolUse", "permissionDecision": "allow"}
```

### Skill Tool Input Fields

When `tool_name == "Skill"`:

```python
@dataclass
class SkillToolInput:
    skill: str       # skill name (e.g., "commit", "vibeflow:manage-work")
    args: str = ""   # optional arguments
```

### Read Tool Input Fields

When `tool_name == "Read"`:

```python
@dataclass
class ReadToolInput:
    file_path: str          # absolute path to file being read
    offset: int = None      # optional line offset
    limit: int = None       # optional line limit
```

### Event Data Contracts

```python
@dataclass
class SkillInvokedEvent:
    event_type: str = "skill_invoked"
    timestamp: str           # ISO 8601
    session_id: str
    skill_name: str          # e.g., "vibeflow:manage-work" or "commit"
    invocation_id: str       # tool_use_id from hook input
    source: str              # "folder" | "plugin"
    scope: str               # "user" | "project" | "local"
    project_dir: str         # cwd from hook input
    args: str = ""           # skill arguments

@dataclass
class NestedFileAccessedEvent:
    event_type: str = "nested_file_accessed"
    timestamp: str           # ISO 8601
    session_id: str
    skill_name: str          # resolved from file path → skill directory mapping
    file_path: str           # absolute path of file read
    relative_path: str       # path relative to skill root
    file_type: str           # "markdown" | "script" | "asset" | "reference" | "config"
    hierarchy: str           # "content" | "script"
    project_dir: str

@dataclass
class SkillLifecycleEvent:
    event_type: str          # "skill_added" | "skill_removed"
    timestamp: str           # ISO 8601
    skill_name: str
    source: str              # "folder" | "plugin"
    scope: str               # "user" | "project" | "local"
    skill_path: str          # absolute path to skill directory
    nested_files: list[str]  # list of files within the skill directory (for total count)
    added_files: list[str]   # files newly detected in this snapshot diff
    removed_files: list[str] # files no longer present in this snapshot diff
```

### SkillInfo Data Contract (internal)

```python
@dataclass
class SkillInfo:
    name: str                # skill identifier
    source: str              # "folder" | "plugin"
    scope: str               # "user" | "project" | "local"
    path: str                # absolute path to skill directory
    nested_files: list[str]  # all files within skill directory
    file_types: dict[str, str]  # {relative_path: file_type}
    hierarchies: dict[str, str] # {relative_path: "content" | "script"}
```

### File Type Classification Rules

| Path Pattern | file_type | hierarchy |
|-------------|-----------|-----------|
| `*.md` | `markdown` | `content` |
| `references/**` | `reference` | `content` |
| `assets/**/*.md` | `reference` | `content` |
| `assets/**` (non-md) | `asset` | `content` |
| `scripts/**` | `script` | `script` |
| `data/**` | `asset` | `script` |
| `*.json`, `*.yaml` | `config` | `script` |
| `SKILL.md` | `markdown` | `content` |

### Skill Source Resolution

```python
class SkillDiscovery:
    """Scans all skill sources and returns unified SkillInfo list."""

    def discover_all(self) -> list[SkillInfo]:
        """Scan all sources, return deduplicated skill list."""
        # NO IMPLEMENTATION - interface signature only

    def discover_folder_skills(self, base_path: str) -> list[SkillInfo]:
        """Scan .claude/skills/ directory."""
        # NO IMPLEMENTATION - interface signature only

    def discover_user_skills(self) -> list[SkillInfo]:
        """Scan ~/.claude/skills/ directory."""
        # NO IMPLEMENTATION - interface signature only

    def discover_plugin_skills(self) -> list[SkillInfo]:
        """Read installed_plugins.json and scan plugin skill directories."""
        # NO IMPLEMENTATION - interface signature only

    def resolve_skill_for_path(self, file_path: str) -> Optional[SkillInfo]:
        """Given an absolute file path, return the SkillInfo if it's inside a skill directory."""
        # NO IMPLEMENTATION - interface signature only
```

### Analytics Interface

```python
class SkillAnalytics:
    """Computes usefulness scores and analytics."""

    def frequency_ranking(
        self, start: datetime, end: datetime
    ) -> list[dict]:
        """Return skills ranked by invocation count in time window."""
        # NO IMPLEMENTATION - interface signature only

    def adoption_curve(
        self, skill_name: str, start: datetime, end: datetime
    ) -> list[dict]:
        """Return cumulative invocation time-series for a skill."""
        # NO IMPLEMENTATION - interface signature only

    def usefulness_scores(
        self, start: datetime, end: datetime,
        weights: dict = None, grace_period_days: int = 7
    ) -> list[dict]:
        """Return composite usefulness score per skill."""
        # NO IMPLEMENTATION - interface signature only

    def usage_trends(
        self, start: datetime, end: datetime, granularity: str = "day"
    ) -> list[dict]:
        """Return time-series of total invocations by granularity."""
        # NO IMPLEMENTATION - interface signature only

    def structure_coverage(
        self, skill_name: str, start: datetime, end: datetime,
        file_grace_period_days: int = 7
    ) -> dict:
        """Return per-file access counts within a skill, with time-normalized metrics per file."""
        # NO IMPLEMENTATION - interface signature only
```

### Django API Endpoints

```
GET /
  Response: HTML single-page dashboard

GET /api/frequency/?start=<iso>&end=<iso>
  Response: [{"skill_name": str, "count": int, "source": str, "scope": str, "status": str}]

GET /api/adoption/?start=<iso>&end=<iso>
  Response: [{"skill_name": str, "first_seen": str, "cumulative": [{"date": str, "count": int}]}]

GET /api/usefulness/?start=<iso>&end=<iso>&grace_days=<int>
  Response: [{"skill_name": str, "score": float, "usage_rate": float, "decay_ratio": float, "depth_score": float, "status": str}]

GET /api/trends/?start=<iso>&end=<iso>&granularity=<day|week|month>
  Response: [{"date": str, "count": int, "by_skill": {str: int}}]

GET /api/coverage/<skill_name>/?start=<iso>&end=<iso>&file_grace_days=<int>
  Response: {"skill_name": str, "total_files": int, "accessed_files": int, "depth_score": float, "files": [{"path": str, "type": str, "hierarchy": str, "access_count": int, "first_seen_at": str, "days_since_first_seen": int, "access_rate": float, "in_grace_period": bool}]}

GET /api/skills/
  Response: [{"name": str, "source": str, "scope": str, "status": str, "first_seen": str, "last_invoked": str, "total_files": int}]
```

### Error Taxonomy

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `INVALID_DATE_RANGE` | 400 | Start date is after end date |
| `SKILL_NOT_FOUND` | 404 | Skill name not in database |
| `INVALID_GRANULARITY` | 400 | Granularity not in day/week/month |

## Data & Storage

### Database Tables

```sql
-- Skill registry: current and historical skills
CREATE TABLE skills (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    source TEXT NOT NULL CHECK (source IN ('folder', 'plugin')),
    scope TEXT NOT NULL CHECK (scope IN ('user', 'project', 'local')),
    path TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'removed')),
    first_seen_at TEXT NOT NULL,     -- ISO 8601
    removed_at TEXT,                  -- ISO 8601, NULL if active
    total_nested_files INTEGER DEFAULT 0,
    UNIQUE(name, source, scope)
);

CREATE INDEX idx_skills_name ON skills(name);
CREATE INDEX idx_skills_status ON skills(status);

-- Nested files within each skill (for structure coverage)
CREATE TABLE skill_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    skill_id INTEGER NOT NULL REFERENCES skills(id),
    relative_path TEXT NOT NULL,
    file_type TEXT NOT NULL CHECK (file_type IN ('markdown', 'script', 'asset', 'reference', 'config')),
    hierarchy TEXT NOT NULL CHECK (hierarchy IN ('content', 'script')),
    first_seen_at TEXT NOT NULL,      -- ISO 8601, when this file was first detected
    removed_at TEXT,                   -- ISO 8601, NULL if still present
    UNIQUE(skill_id, relative_path)
);

CREATE INDEX idx_skill_files_skill ON skill_files(skill_id);

-- Skill invocation events
CREATE TABLE skill_invocations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,          -- ISO 8601
    session_id TEXT NOT NULL,
    skill_name TEXT NOT NULL,
    invocation_id TEXT NOT NULL UNIQUE,
    source TEXT NOT NULL,
    scope TEXT NOT NULL,
    project_dir TEXT,
    args TEXT DEFAULT ''
);

CREATE INDEX idx_invocations_timestamp ON skill_invocations(timestamp);
CREATE INDEX idx_invocations_skill ON skill_invocations(skill_name);
CREATE INDEX idx_invocations_session ON skill_invocations(session_id);

-- Nested file access events
CREATE TABLE file_accesses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,          -- ISO 8601
    session_id TEXT NOT NULL,
    skill_name TEXT NOT NULL,
    file_path TEXT NOT NULL,
    relative_path TEXT NOT NULL,
    file_type TEXT NOT NULL,
    hierarchy TEXT NOT NULL,
    project_dir TEXT
);

CREATE INDEX idx_accesses_timestamp ON file_accesses(timestamp);
CREATE INDEX idx_accesses_skill ON file_accesses(skill_name);

-- Skill lifecycle events (added/removed)
CREATE TABLE skill_lifecycle (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,          -- ISO 8601
    event_type TEXT NOT NULL CHECK (event_type IN ('skill_added', 'skill_removed')),
    skill_name TEXT NOT NULL,
    source TEXT NOT NULL,
    scope TEXT NOT NULL,
    skill_path TEXT NOT NULL
);

CREATE INDEX idx_lifecycle_timestamp ON skill_lifecycle(timestamp);
CREATE INDEX idx_lifecycle_skill ON skill_lifecycle(skill_name);

-- Inventory snapshots (stores last known state for diffing)
CREATE TABLE inventory_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,          -- ISO 8601
    snapshot_json TEXT NOT NULL       -- JSON array of {name, source, scope, path}
);
```

### Migrations

Managed by Django's migration framework. Initial migration creates all tables above.

| Migration | Description | Rollback |
|-----------|-------------|----------|
| `0001_initial.py` | Create all tables and indexes | Drop all tables |

### Data Retention

| Data Type | Retention Period | Cleanup Strategy |
|-----------|-----------------|------------------|
| Skill invocations | 90 days (default, configurable) | Django management command `cleanup_old_events` |
| File accesses | 90 days (default, configurable) | Same command |
| Lifecycle events | Indefinite | Never deleted — full history needed |
| Inventory snapshots | Keep latest 100 | Delete oldest when count > 100 |
| Skills registry | Indefinite | Removed skills kept with `status=removed` |

## Reliability & SLIs/SLOs

### SLIs (Service Level Indicators)

- **Hook latency**: Time from hook invocation to stdout response
- **Dashboard page load**: Time from HTTP request to full page render
- **Query latency**: Time for API endpoints to return JSON

### SLOs (Service Level Objectives)

| SLI | Target | Measurement |
|-----|--------|-------------|
| Hook latency (Skill matcher) | < 20ms p95 | Timer in log_event.py |
| Hook latency (Read matcher, non-skill path) | < 5ms p95 | Early exit path check |
| Hook latency (Read matcher, skill path) | < 20ms p95 | Timer in log_event.py |
| Inventory snapshot | < 500ms p95 | Timer in inventory_snapshot.py |
| Dashboard page load | < 3s with 100K events | Browser timing |
| API query latency | < 500ms p95 | Django middleware |

### Fault Tolerance

**Hook failure handling:**
- Hooks must never block Claude Code. If any error occurs, write to stderr and exit 0.
- SQLite write failures are logged but do not affect hook response.
- All hooks return `permissionDecision: "allow"` unconditionally.

**Database resilience:**
- SQLite in WAL mode for concurrent read/write.
- Connection timeout: 5 seconds.
- If DB is locked, skip the write (log to stderr) rather than block.

**Dashboard resilience:**
- If DB is empty or missing, dashboard shows "No data yet" state.
- All API endpoints return empty arrays/objects on no data, never errors.

## Security & Privacy

### Authentication/Authorization

- No authentication — dashboard runs on localhost only (`127.0.0.1:8787`)
- Django `ALLOWED_HOSTS = ["127.0.0.1", "localhost"]`
- No remote access, no CSRF needed for read-only GET endpoints

### Data Privacy

| Data Type | Classification | Handling |
|-----------|---------------|----------|
| Skill names | Non-sensitive | Stored as-is |
| File paths (within skills) | Low sensitivity | Stored as relative paths |
| Session IDs | Internal | Stored for correlation, not displayed |
| Prompt content | **Not collected** | UserPromptSubmit hook ignores prompt field |
| Skill arguments | Low sensitivity | Stored but not displayed prominently |

### Secrets Management

- No secrets required — fully local system
- No API keys, no auth tokens
- Django `SECRET_KEY` generated locally on first run, stored in `${CLAUDE_PLUGIN_DATA}/django_secret.txt`

### Audit Logging

- All hook invocations are the audit log (stored in SQLite)
- No additional audit logging needed

## Evaluation Plan

### Test Strategy

| Test Type | Scope | Coverage Target |
|-----------|-------|-----------------|
| Unit | `skill_discovery.py`, `dashboard/analytics/analytics.py`, `db.py`, `log_event.py` | 90% |
| Integration | Hook → SQLite → Django API pipeline | Critical paths |
| E2E | Install plugin → trigger skills → view dashboard | Key flows |

### Performance Benchmarks

| Operation | Target | Measurement |
|-----------|--------|-------------|
| PreToolUse hook (Read, non-skill path) | < 5ms | Pytest benchmark with 100 skill prefixes |
| PreToolUse hook (Skill invocation) | < 20ms | Pytest benchmark with DB write |
| Inventory snapshot (50 skills) | < 500ms | Pytest benchmark |
| Dashboard page load (100K events) | < 3s | Browser timing |
| Frequency API (100K events) | < 500ms | Django test client |
| Usefulness scoring (100 skills, 100K events) | < 1s | Pytest benchmark |

### Quality Gates

- All unit tests pass
- Hook latency benchmarks pass
- Dashboard renders with test dataset
- Plugin installs cleanly via `claude plugin install`

---

## References

### Plugin Directory Structure

```
skills-analytics/
├── .claude-plugin/
│   └── plugin.json
├── hooks/
│   └── hooks.json
├── scripts/
│   ├── db.py
│   ├── skill_discovery.py
│   ├── log_event.py
│   └── inventory_snapshot.py
├── dashboard/
│   ├── analytics_project/
│   │   ├── settings.py
│   │   └── urls.py
│   └── analytics/
│       ├── views.py
│       ├── analytics.py
│       ├── templates/
│       │   └── analytics/
│       │       └── dashboard.html
│       └── static/
│           └── analytics/
│               ├── dashboard.js
│               └── dashboard.css
├── skills/
│   └── analytics-dashboard/
│       └── SKILL.md
├── tests/
│   ├── hooks/
│   │   ├── test_db.py
│   │   ├── test_skill_discovery.py
│   │   ├── test_log_event.py
│   │   └── test_inventory_snapshot.py
│   └── dashboard/
│       ├── test_analytics.py
│       └── test_api.py
└── README.md
```

### Related Specs
- None (first spec in project)

### Related ADRs
- Pending: Plugin packaging decision
- Pending: SQLite vs alternatives

### External Documentation
- Claude Code Hooks: hook event lifecycle and configuration
- Django 4.2 LTS: web framework
- SQLite WAL mode: concurrent access

---

> **Code Detail Guidance:**
> - Interface signatures (no implementation)
> - Data schemas and contracts
> - Configuration tables (summary form)
> - No full implementations (→ Feature Spec)
> - No algorithms with logic (→ Feature Spec)
