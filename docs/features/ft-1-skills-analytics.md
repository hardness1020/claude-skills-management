# Feature — 1 skills-analytics

**File:** docs/features/ft-1-skills-analytics.md
**Owner:** Marcus Chang
**TECH-SPECs:** spec-analytics.md (v1.0.0) — `docs/specs/spec-skills-analytics.md`

---

## Stage B Discovery Findings

> Reference: `docs/discovery/disco-1.md`

### Test Impact Analysis

**Tests to Update:**
- None (greenfield project)

**Tests to Remove:**
- None

**Coverage Gaps:**
- All components are new — no existing coverage

**Test Update Checklist:**
- [ ] Add unit tests for `db.py` (Stage F)
- [ ] Add unit tests for `skill_discovery.py` (Stage F)
- [ ] Add unit tests for `log_event.py` (Stage F)
- [ ] Add unit tests for `inventory_snapshot.py` (Stage F)
- [ ] Add unit tests for `analytics.py` (Stage F)
- [ ] Add unit tests for Django API views (Stage F)
- [ ] Add integration tests for hook → DB → API pipeline (Stage H)

### Existing Implementation Analysis

**Similar Features:**
- None (greenfield)

**Reusable Components:**
- Claude Code plugin structure from vibeflow plugin — follow same layout for `.claude-plugin/`, `hooks/`, `scripts/`, `skills/`

**Patterns to Follow:**
- Hook script pattern: read JSON stdin → process → write JSON stdout → exit 0
- Plugin persistent storage via `${CLAUDE_PLUGIN_DATA}`

**Code to Refactor:** None

### Dependency & Side Effect Mapping

**Dependencies:**
- Claude Code hook system — provides PreToolUse and UserPromptSubmit events
- `~/.claude/plugins/installed_plugins.json` — plugin registry for skill discovery
- `.claude/skills/` directories — folder-based skill discovery
- `${CLAUDE_PLUGIN_DATA}` — persistent storage location

**Side Effects:**
- Database: INSERT on every skill invocation, file read within skill dirs, and inventory diff
- Filesystem: SQLite DB file created in `${CLAUDE_PLUGIN_DATA}`

**Impact Radius:**
- Hook layer: Adds latency to every Skill and Read tool invocation (must be < 20ms)

**Risk Areas:**
- `log_event.py` Read matcher — High — fires on every file read, must exit fast for non-skill paths

---

## Architecture Conformance

**Layer Assignment:**
- Hook scripts in `scripts/` (data collection layer)
- Shared modules in `scripts/` (data access layer)
- Django app in `dashboard/` (presentation layer)
- Plugin config in `.claude-plugin/` and `hooks/` (configuration layer)

**Pattern Compliance:**
- Follows Claude Code plugin structure ✓
- Hook scripts are stateless, short-lived processes ✓
- SQLite WAL mode for concurrent access ✓

**Dependencies:**
- `scripts/db.py` (shared by hooks and importable by Django)
- `scripts/skill_discovery.py` (shared by inventory snapshot and Django)
- `scripts/analytics.py` (used by Django views)

---

## API Design

> This section defines the contract for Stage F. Exact names, parameters, and return types become implementation stubs.

### db.get_connection()

- **Signature:** `get_connection(db_path: str = None) -> sqlite3.Connection`
- **Purpose:** Get a SQLite connection with WAL mode enabled
- **Parameters:**
  - `db_path`: `str | None` - Path to DB file. Defaults to `${CLAUDE_PLUGIN_DATA}/skills_analytics.db`
- **Returns:** `sqlite3.Connection` with WAL mode, 5s timeout
- **Raises:**
  - `sqlite3.OperationalError`: If DB path is inaccessible

### db.init_schema()

- **Signature:** `init_schema(conn: sqlite3.Connection) -> None`
- **Purpose:** Create all tables and indexes if they don't exist
- **Parameters:**
  - `conn`: Active SQLite connection
- **Returns:** None

### db.insert_skill_invocation()

- **Signature:** `insert_skill_invocation(conn: sqlite3.Connection, event: dict) -> None`
- **Purpose:** Insert a skill_invoked event into skill_invocations table
- **Parameters:**
  - `conn`: Active SQLite connection
  - `event`: Dict with keys: `timestamp`, `session_id`, `skill_name`, `invocation_id`, `source`, `scope`, `project_dir`, `args`
- **Returns:** None

### db.insert_file_access()

- **Signature:** `insert_file_access(conn: sqlite3.Connection, event: dict) -> None`
- **Purpose:** Insert a nested_file_accessed event into file_accesses table
- **Parameters:**
  - `conn`: Active SQLite connection
  - `event`: Dict with keys: `timestamp`, `session_id`, `skill_name`, `file_path`, `relative_path`, `file_type`, `hierarchy`, `project_dir`
- **Returns:** None

### db.insert_lifecycle_event()

- **Signature:** `insert_lifecycle_event(conn: sqlite3.Connection, event: dict) -> None`
- **Purpose:** Insert a skill_added or skill_removed event
- **Parameters:**
  - `conn`: Active SQLite connection
  - `event`: Dict with keys: `timestamp`, `event_type`, `skill_name`, `source`, `scope`, `skill_path`
- **Returns:** None

### db.upsert_skill()

- **Signature:** `upsert_skill(conn: sqlite3.Connection, skill_info: dict) -> int`
- **Purpose:** Insert or update a skill in the skills registry, return skill ID
- **Parameters:**
  - `conn`: Active SQLite connection
  - `skill_info`: Dict with keys: `name`, `source`, `scope`, `path`, `total_nested_files`
- **Returns:** `int` — the skill's row ID

### db.mark_skill_removed()

- **Signature:** `mark_skill_removed(conn: sqlite3.Connection, skill_name: str, source: str, scope: str, removed_at: str) -> None`
- **Purpose:** Set a skill's status to 'removed' with timestamp
- **Parameters:**
  - `conn`: Active SQLite connection
  - `skill_name`: Skill identifier
  - `source`: "folder" or "plugin"
  - `scope`: "user", "project", or "local"
  - `removed_at`: ISO 8601 timestamp
- **Returns:** None

### db.save_snapshot()

- **Signature:** `save_snapshot(conn: sqlite3.Connection, timestamp: str, snapshot: list[dict]) -> None`
- **Purpose:** Save an inventory snapshot and prune old snapshots (keep latest 100)
- **Parameters:**
  - `conn`: Active SQLite connection
  - `timestamp`: ISO 8601 timestamp
  - `snapshot`: List of dicts with keys: `name`, `source`, `scope`, `path`
- **Returns:** None

### db.get_latest_snapshot()

- **Signature:** `get_latest_snapshot(conn: sqlite3.Connection) -> list[dict] | None`
- **Purpose:** Retrieve the most recent inventory snapshot
- **Parameters:**
  - `conn`: Active SQLite connection
- **Returns:** List of skill dicts, or None if no snapshots exist

---

### SkillDiscovery.discover_all()

- **Signature:** `discover_all(project_dir: str = None) -> list[dict]`
- **Purpose:** Scan all skill sources and return a deduplicated list of SkillInfo dicts
- **Parameters:**
  - `project_dir`: `str | None` - Project directory for project/local scope detection. Defaults to cwd.
- **Returns:** List of dicts with keys: `name`, `source`, `scope`, `path`, `nested_files`, `file_types`, `hierarchies`

### SkillDiscovery.discover_folder_skills()

- **Signature:** `discover_folder_skills(skills_dir: str, scope: str) -> list[dict]`
- **Purpose:** Scan a `.claude/skills/` directory for folder-based skills
- **Parameters:**
  - `skills_dir`: Absolute path to `.claude/skills/` directory
  - `scope`: "user" or "project"
- **Returns:** List of SkillInfo dicts

### SkillDiscovery.discover_plugin_skills()

- **Signature:** `discover_plugin_skills(project_dir: str = None) -> list[dict]`
- **Purpose:** Read installed_plugins.json and scan plugin skill directories
- **Parameters:**
  - `project_dir`: Project dir for scope resolution
- **Returns:** List of SkillInfo dicts with source="plugin" and appropriate scope

### SkillDiscovery.resolve_skill_for_path()

- **Signature:** `resolve_skill_for_path(file_path: str, skill_paths: dict[str, dict] = None) -> dict | None`
- **Purpose:** Given an absolute file path, return the SkillInfo dict if it's inside a skill directory
- **Parameters:**
  - `file_path`: Absolute path of the file being read
  - `skill_paths`: Optional pre-computed mapping of {skill_root_path: SkillInfo}. Built from discover_all() if not provided.
- **Returns:** Dict with keys: `skill_name`, `relative_path`, `file_type`, `hierarchy`, or None if not inside a skill

### SkillDiscovery.classify_file()

- **Signature:** `classify_file(relative_path: str) -> tuple[str, str]`
- **Purpose:** Classify a file within a skill by type and hierarchy
- **Parameters:**
  - `relative_path`: Path relative to the skill root directory
- **Returns:** Tuple of `(file_type, hierarchy)` where file_type is one of "markdown", "script", "asset", "reference", "config" and hierarchy is "content" or "script"

---

### log_event.main()

- **Signature:** `main() -> None`
- **Purpose:** PreToolUse hook entry point. Reads JSON from stdin, logs the event, writes allow response to stdout.
- **Parameters:** None (reads from stdin)
- **Returns:** None (writes to stdout)
- **Behavior:**
  - If `tool_name == "Skill"`: extract `tool_input.skill` and `tool_input.args`, write `skill_invoked` event to DB
  - If `tool_name == "Read"`: extract `tool_input.file_path`, check if path is inside a skill directory. If yes, write `nested_file_accessed` event to DB. If no, skip (fast path).
  - Always output `{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "allow"}}` to stdout
  - On any error, write error to stderr and still output allow response

---

### inventory_snapshot.main()

- **Signature:** `main() -> None`
- **Purpose:** UserPromptSubmit hook entry point. Snapshots skill inventory, diffs against previous, logs adds/removes.
- **Parameters:** None (reads from stdin)
- **Returns:** None (writes to stdout)
- **Behavior:**
  1. Read hook JSON from stdin to get `cwd`
  2. Call `SkillDiscovery.discover_all(project_dir=cwd)`
  3. Load previous snapshot from DB via `db.get_latest_snapshot()`
  4. Diff current vs. previous: detect added and removed skills
  5. For each added skill: insert `skill_added` lifecycle event, upsert skill in registry
  6. For each removed skill: insert `skill_removed` lifecycle event, mark skill as removed
  7. Save current snapshot to DB
  8. Output empty JSON `{}` to stdout (UserPromptSubmit hooks don't need structured output)

---

### SkillAnalytics.frequency_ranking()

- **Signature:** `frequency_ranking(conn: sqlite3.Connection, start: str, end: str) -> list[dict]`
- **Purpose:** Return skills ranked by invocation count in time window
- **Parameters:**
  - `conn`: Active SQLite connection
  - `start`: ISO 8601 start timestamp
  - `end`: ISO 8601 end timestamp
- **Returns:** List of dicts: `{"skill_name": str, "count": int, "source": str, "scope": str, "status": str}` sorted by count desc

### SkillAnalytics.adoption_curves()

- **Signature:** `adoption_curves(conn: sqlite3.Connection, start: str, end: str) -> list[dict]`
- **Purpose:** Return first-use date and cumulative invocation curve per skill
- **Parameters:**
  - `conn`: Active SQLite connection
  - `start`: ISO 8601 start timestamp
  - `end`: ISO 8601 end timestamp
- **Returns:** List of dicts: `{"skill_name": str, "first_seen": str, "cumulative": [{"date": str, "count": int}]}`

### SkillAnalytics.usefulness_scores()

- **Signature:** `usefulness_scores(conn: sqlite3.Connection, start: str, end: str, grace_period_days: int = 7, weights: dict = None) -> list[dict]`
- **Purpose:** Compute composite usefulness score per skill
- **Parameters:**
  - `conn`: Active SQLite connection
  - `start`: ISO 8601 start timestamp
  - `end`: ISO 8601 end timestamp
  - `grace_period_days`: Skills younger than this are excluded from scoring (default 7)
  - `weights`: Dict with keys `w1` (usage_rate), `w2` (decay), `w3` (depth). Defaults: `{"w1": 0.4, "w2": 0.35, "w3": 0.25}`
- **Returns:** List of dicts: `{"skill_name": str, "score": float, "usage_rate": float, "decay_ratio": float, "depth_score": float, "days_since_install": int, "status": str, "in_grace_period": bool}` sorted by score desc

### SkillAnalytics.usage_trends()

- **Signature:** `usage_trends(conn: sqlite3.Connection, start: str, end: str, granularity: str = "day") -> list[dict]`
- **Purpose:** Return time-series of invocations aggregated by granularity
- **Parameters:**
  - `conn`: Active SQLite connection
  - `start`: ISO 8601 start timestamp
  - `end`: ISO 8601 end timestamp
  - `granularity`: "day", "week", or "month"
- **Returns:** List of dicts: `{"date": str, "count": int, "by_skill": {"skill_name": int}}`
- **Raises:**
  - `ValueError`: If granularity not in ("day", "week", "month")

### SkillAnalytics.structure_coverage()

- **Signature:** `structure_coverage(conn: sqlite3.Connection, skill_name: str, start: str, end: str) -> dict`
- **Purpose:** Return per-file access counts within a skill
- **Parameters:**
  - `conn`: Active SQLite connection
  - `skill_name`: Skill identifier
  - `start`: ISO 8601 start timestamp
  - `end`: ISO 8601 end timestamp
- **Returns:** Dict: `{"skill_name": str, "total_files": int, "accessed_files": int, "depth_score": float, "files": [{"relative_path": str, "file_type": str, "hierarchy": str, "access_count": int}]}`
- **Raises:**
  - `KeyError`: If skill_name not found in DB

---

### Django API Views

### GET /api/frequency/

- **Method:** GET
- **Path:** `/api/frequency/`
- **Query Params:** `start` (ISO 8601), `end` (ISO 8601)
- **Response Body:**
  ```json
  [{"skill_name": "str", "count": 0, "source": "str", "scope": "str", "status": "str"}]
  ```
- **Error Responses:**
  - `400`: Invalid date format or start > end

### GET /api/adoption/

- **Method:** GET
- **Path:** `/api/adoption/`
- **Query Params:** `start` (ISO 8601), `end` (ISO 8601)
- **Response Body:**
  ```json
  [{"skill_name": "str", "first_seen": "str", "cumulative": [{"date": "str", "count": 0}]}]
  ```
- **Error Responses:**
  - `400`: Invalid date format or start > end

### GET /api/usefulness/

- **Method:** GET
- **Path:** `/api/usefulness/`
- **Query Params:** `start` (ISO 8601), `end` (ISO 8601), `grace_days` (int, optional, default 7)
- **Response Body:**
  ```json
  [{"skill_name": "str", "score": 0.0, "usage_rate": 0.0, "decay_ratio": 0.0, "depth_score": 0.0, "days_since_install": 0, "status": "str", "in_grace_period": false}]
  ```
- **Error Responses:**
  - `400`: Invalid date format or start > end

### GET /api/trends/

- **Method:** GET
- **Path:** `/api/trends/`
- **Query Params:** `start` (ISO 8601), `end` (ISO 8601), `granularity` (str: "day"|"week"|"month", default "day")
- **Response Body:**
  ```json
  [{"date": "str", "count": 0, "by_skill": {"skill_name": 0}}]
  ```
- **Error Responses:**
  - `400`: Invalid date format, start > end, or invalid granularity

### GET /api/coverage/{skill_name}/

- **Method:** GET
- **Path:** `/api/coverage/{skill_name}/`
- **Query Params:** `start` (ISO 8601), `end` (ISO 8601)
- **Response Body:**
  ```json
  {"skill_name": "str", "total_files": 0, "accessed_files": 0, "depth_score": 0.0, "files": [{"relative_path": "str", "file_type": "str", "hierarchy": "str", "access_count": 0}]}
  ```
- **Error Responses:**
  - `404`: Skill not found
  - `400`: Invalid date format or start > end

### GET /api/skills/

- **Method:** GET
- **Path:** `/api/skills/`
- **Response Body:**
  ```json
  [{"name": "str", "source": "str", "scope": "str", "status": "str", "first_seen": "str", "last_invoked": "str", "total_files": 0}]
  ```

### GET / (Dashboard)

- **Method:** GET
- **Path:** `/`
- **Response:** HTML single-page dashboard rendering all 5 views
- **Behavior:** Serves static HTML with embedded JavaScript that calls the API endpoints above

---

## Acceptance Criteria

> Must be testable. Each criterion becomes one or more tests.

### Hook Scripts
- [ ] `log_event.py` logs a `skill_invoked` event when PreToolUse fires with `tool_name="Skill"`
- [ ] `log_event.py` logs a `nested_file_accessed` event when PreToolUse fires with `tool_name="Read"` and the file path is inside a known skill directory
- [ ] `log_event.py` exits in < 5ms when the Read file path is NOT inside any skill directory
- [ ] `log_event.py` always outputs `permissionDecision: "allow"` regardless of errors
- [ ] `log_event.py` writes errors to stderr, never blocks Claude Code
- [ ] `inventory_snapshot.py` detects newly added skills by diffing current vs. previous snapshot
- [ ] `inventory_snapshot.py` detects removed skills by diffing current vs. previous snapshot
- [ ] `inventory_snapshot.py` handles first run (no previous snapshot) by treating all skills as new
- [ ] `inventory_snapshot.py` completes in < 500ms for 50 skills

### Skill Discovery
- [ ] `discover_all()` finds folder-based skills in `~/.claude/skills/`
- [ ] `discover_all()` finds folder-based skills in `.claude/skills/` (project scope)
- [ ] `discover_all()` finds plugin-based skills from `installed_plugins.json`
- [ ] `resolve_skill_for_path()` returns correct SkillInfo for a file inside a skill directory
- [ ] `resolve_skill_for_path()` returns None for files not inside any skill directory
- [ ] `classify_file()` correctly classifies markdown, script, asset, reference, and config files
- [ ] `classify_file()` correctly assigns content vs. script hierarchy

### Database
- [ ] `init_schema()` creates all 6 tables with correct columns and indexes
- [ ] `init_schema()` is idempotent (safe to call multiple times)
- [ ] `insert_skill_invocation()` writes a row to `skill_invocations`
- [ ] `insert_file_access()` writes a row to `file_accesses`
- [ ] `insert_lifecycle_event()` writes a row to `skill_lifecycle`
- [ ] `upsert_skill()` creates a new skill or updates an existing one
- [ ] `mark_skill_removed()` sets status='removed' and removed_at timestamp
- [ ] `save_snapshot()` stores snapshot and prunes to keep latest 100
- [ ] DB uses WAL mode for concurrent access

### Analytics
- [ ] `frequency_ranking()` returns skills sorted by invocation count within time window
- [ ] `adoption_curves()` returns first_seen date and cumulative curve per skill
- [ ] `usefulness_scores()` excludes skills within grace period
- [ ] `usefulness_scores()` computes correct usage_rate as invocations / days_since_install
- [ ] `usefulness_scores()` computes decay_ratio by comparing recent vs. lifetime usage rate
- [ ] `usefulness_scores()` computes depth_score as unique_files_accessed / total_files
- [ ] `usefulness_scores()` returns weighted composite score with configurable weights
- [ ] `usage_trends()` aggregates by day, week, or month correctly
- [ ] `structure_coverage()` returns file-level access counts with type and hierarchy

### Django Dashboard
- [ ] `GET /api/frequency/` returns JSON array with correct fields
- [ ] `GET /api/adoption/` returns JSON array with cumulative curves
- [ ] `GET /api/usefulness/` returns JSON array with score breakdowns
- [ ] `GET /api/trends/` returns JSON array aggregated by requested granularity
- [ ] `GET /api/coverage/{skill_name}/` returns file tree with access counts
- [ ] `GET /api/skills/` returns all registered skills with status
- [ ] All API endpoints return empty arrays/objects (not errors) when no data
- [ ] All API endpoints validate date params and return 400 on invalid input
- [ ] `GET /` returns HTML dashboard page
- [ ] Dashboard time interval selector updates all views via AJAX without page reload
- [ ] Dashboard loads in < 3s with 100K events in DB

---

## Design Changes

### API Changes

- All endpoints are new (greenfield project)
- 6 JSON API endpoints + 1 HTML dashboard endpoint
- All endpoints are GET (read-only analytics)

### Schema Changes

- 6 new SQLite tables: `skills`, `skill_files`, `skill_invocations`, `file_accesses`, `skill_lifecycle`, `inventory_snapshots`
- See tech spec for full CREATE TABLE statements
- Migration: `0001_initial.py` (Django migration)

### UI Changes

- New single-page dashboard at `localhost:8787`
- 5 views: Frequency, Adoption, Usefulness Scoring, Trends, Structure Coverage
- Time interval selector (day/week/month/custom date range)
- Charts rendered with Chart.js

---

## Test & Eval Plan

### Unit Tests (Stage F)

- Test `db.py`: init_schema, all insert functions, upsert_skill, mark_skill_removed, save/get snapshot
- Test `skill_discovery.py`: discover_folder_skills, discover_plugin_skills, resolve_skill_for_path, classify_file
- Test `log_event.py`: Skill tool input processing, Read tool input processing, non-skill path fast exit, error handling
- Test `inventory_snapshot.py`: first run (no previous snapshot), diff with additions, diff with removals, diff with no changes
- Test `analytics.py`: frequency_ranking, adoption_curves, usefulness_scores (all sub-metrics), usage_trends (all granularities), structure_coverage
- Test Django API views: all 6 endpoints with valid params, invalid params, empty data
- Mock: filesystem for skill_discovery, stdin/stdout for hook scripts

### Integration Tests (Stage H)

- Test full hook → DB pipeline: simulate PreToolUse JSON → verify DB rows
- Test full inventory snapshot → DB pipeline: simulate UserPromptSubmit → verify lifecycle events
- Test full API pipeline: seed DB → call API endpoint → verify response
- Test dashboard HTML loads and Chart.js initializes

---

## Telemetry & Metrics

**Events to Track:**
- `skill_invoked`: Every skill invocation (logged by PreToolUse hook)
- `nested_file_accessed`: Every file read within a skill directory (logged by PreToolUse hook)
- `skill_added` / `skill_removed`: Lifecycle events (logged by UserPromptSubmit hook)

**Dashboards:**
- Single-page local dashboard with 5 views (this IS the analytics product)

**Alerts:**
- None in v1 (local-only)

---

## Edge Cases & Risks

**Edge Cases:**
- First run with empty DB: inventory_snapshot treats all discovered skills as "added"
- Skill invoked that isn't in the skill registry yet: log_event writes the invocation; the skill will be registered at next inventory snapshot
- Same skill name at different scopes (e.g., "commit" as user-scope and project-scope): treated as separate entries in the registry (unique on name + source + scope)
- Read tool reads a file in a skill that was just deleted: resolve_skill_for_path may return None if the skill dir no longer exists; skip logging
- SQLite DB locked during write: catch OperationalError, log to stderr, skip write, still return allow
- Very large skill directory (100+ nested files): classify_file iterates once at snapshot time, not per-read
- `${CLAUDE_PLUGIN_DATA}` not set (running outside plugin context): fall back to `~/.skills-analytics/`

**Risks:**
| Risk | Impact | Mitigation |
|------|--------|------------|
| Read hook latency > 5ms for non-skill paths | Degrades Claude Code UX | Cache skill directory prefixes in a set; prefix-match is O(n) but n is small (< 100 skills) |
| installed_plugins.json format changes | Plugin discovery breaks | Defensive JSON parsing with fallbacks |
| Django import overhead in hook scripts | Hook startup too slow | Hooks use stdlib only (sqlite3, json, sys, os); Django is only for dashboard |

**Fallback Behavior:**
- If DB write fails: log error to stderr, continue, return allow
- If skill discovery fails: log error, use empty skill list, continue
- If `${CLAUDE_PLUGIN_DATA}` is missing: create `~/.skills-analytics/` as fallback

---

## References

- Discovery: `docs/discovery/disco-1.md`
- Tech Specs: `docs/specs/spec-skills-analytics.md` (v1.0.0)
- ADRs: `docs/adrs/adr-1-plugin-packaging.md`, `docs/adrs/adr-1-sqlite-storage.md`
