# Discovery — #ft-4 plugin-packaging

**File:** docs/discovery/disco-4.md
**Work Item:** #ft-4 — Package as Claude Code plugin with user-scope hooks and dashboard skill
**Date:** 2026-03-19

---

## Phase 0: Spec Discovery

### Existing Specs

| Document | Relevance | Notes |
|----------|-----------|-------|
| `docs/adrs/adr-1-plugin-packaging.md` | **Primary** — already approved plugin distribution | Defines the target structure: `.claude-plugin/plugin.json`, `hooks/hooks.json`, skills dir, `${CLAUDE_PLUGIN_DATA}` |
| `docs/specs/spec-skills-analytics.md` | **High** — defines plugin directory layout and component inventory | Section "References > Plugin Directory Structure" shows the target layout |
| `docs/features/ft-1-skills-analytics.md` | **Medium** — API design and acceptance criteria are implemented | No changes needed to the analytics/dashboard code itself |
| `docs/adrs/adr-1-sqlite-storage.md` | **Low** — storage decision already in place, no changes needed |  |

### Key Decisions Already Made

1. **Plugin packaging over manual setup** (ADR-1) — one-command install via `claude plugin install`
2. **`${CLAUDE_PLUGIN_DATA}` for DB storage** — survives plugin updates
3. **User-scope hooks** — fire across all projects (matches the user's stated requirement)

---

## Phase 1: Spec-Code Validation

### Hook Scripts

| Spec Claim | Code Reality | Status |
|------------|-------------|--------|
| Hooks use `${CLAUDE_PLUGIN_ROOT}` for script paths | Scripts use `$CLAUDE_PROJECT_DIR/scripts/` | **MISMATCH** — must switch to `${CLAUDE_PLUGIN_ROOT}` |
| Hooks declared in `hooks/hooks.json` | Hooks declared in `.claude/settings.json` (project-scoped) | **MISMATCH** — must create `hooks/hooks.json` |
| `log_event.py` resolves skill paths via `skill_discovery` | `resolve_skill_for_path()` is called with `skill_paths=None` → always returns `None` | **BUG** — file read tracking is broken; must build skill_paths map before calling |

### Import Mechanism

| Spec Claim | Code Reality | Status |
|------------|-------------|--------|
| Hook scripts are standalone | Both scripts use `sys.path.insert(0, _PROJECT_ROOT)` + `from scripts import db, skill_discovery` | **WORKS** — but `_PROJECT_ROOT` derivation assumes scripts are two levels below root. Must verify this still holds in plugin install path |

### DB Path

| Spec Claim | Code Reality | Status |
|------------|-------------|--------|
| DB at `${CLAUDE_PLUGIN_DATA}/skills_analytics.db` | `db.get_connection()` checks `CLAUDE_PLUGIN_DATA` env, falls back to `~/.skills-analytics/` | **OK** — already compatible |

### Dashboard

| Spec Claim | Code Reality | Status |
|------------|-------------|--------|
| Dashboard launched via `/analytics-dashboard` skill | No skill exists — `skills/analytics-dashboard/` is empty | **NOT IMPLEMENTED** |
| `SECRET_KEY` generated and stored in plugin data | Hardcoded `"dev-secret-key-change-in-production"` | **MISMATCH** — should generate on first run |

---

## Phase 2: Test Impact Analysis

### Tests to Update

- `tests/hooks/test_log_event.py` — any tests that reference `$CLAUDE_PROJECT_DIR` paths need to work with `${CLAUDE_PLUGIN_ROOT}` too
- `tests/hooks/test_inventory_snapshot.py` — same path reference changes

### Tests to Add

- Plugin structure validation: `plugin.json` has required fields, `hooks.json` schema is correct
- Dashboard skill SKILL.md: verify it contains the expected content
- `log_event.py` fix: test that `resolve_skill_for_path` is called with a populated `skill_paths` dict

### No Tests Needed For

- `analytics.py`, `views.py`, `db.py` — no functional changes to these modules

---

## Phase 3: Dependency & Side Effect Mapping

### Current Dependencies

```
.claude/settings.json (project-scoped hooks)
    ↓ triggers
scripts/log_event.py
scripts/inventory_snapshot.py
    ↓ imports (via sys.path hack)
scripts/db.py
scripts/skill_discovery.py
    ↓ writes to
~/.skills-analytics/skills_analytics.db
    ↓ read by
dashboard/analytics/views.py → dashboard/analytics/analytics.py → scripts/db.py
```

### Target Dependencies (after plugin packaging)

```
hooks/hooks.json (auto-registered at user scope)
    ↓ triggers
scripts/log_event.py  (referenced via ${CLAUDE_PLUGIN_ROOT}/scripts/)
scripts/inventory_snapshot.py
    ↓ imports
scripts/db.py
scripts/skill_discovery.py
    ↓ writes to
${CLAUDE_PLUGIN_DATA}/skills_analytics.db
    ↓ read by
dashboard/ (launched via /analytics-dashboard skill)
```

### Side Effects

| Change | Blast Radius | Risk |
|--------|-------------|------|
| Move hooks from `.claude/settings.json` to `hooks/hooks.json` | Existing project-scoped users lose hooks until they install the plugin | **Medium** — document migration in README |
| `${CLAUDE_PLUGIN_ROOT}` replaces `$CLAUDE_PROJECT_DIR` | Hook scripts must still resolve imports correctly from the plugin install path | **Low** — `_PROJECT_ROOT` derivation is relative to `__file__` |
| New `SKILL.md` for `/analytics-dashboard` | New user-invocable skill appears for all users who install the plugin | **None** — additive |
| `plugin.json` creation | Enables `claude plugin install` | **None** — additive |

### Breaking Changes

- Users who cloned this repo and rely on `.claude/settings.json` project hooks will need to transition to the plugin install. The `.claude/settings.json` hooks should be preserved for development but the README should guide users toward plugin install.

---

## Phase 4: Reusable Component Discovery

### Existing Components to Reuse

| Component | Location | Reuse |
|-----------|----------|-------|
| `scripts/db.py` | DB connection, schema, CRUD | **As-is** — already uses `${CLAUDE_PLUGIN_DATA}` fallback |
| `scripts/skill_discovery.py` | Skill scanning | **As-is** — no changes needed |
| `scripts/log_event.py` | PreToolUse hook | **Minor fix** — `resolve_skill_for_path` call needs `skill_paths` populated |
| `scripts/inventory_snapshot.py` | UserPromptSubmit hook | **As-is** |
| `dashboard/` | Full Django dashboard | **As-is** |

### Patterns to Follow

- **VibeFlow plugin structure**: `~/.claude/plugins/cache/vibeflow/` has a working plugin with `hooks/`, `skills/`, `.claude-plugin/plugin.json` — use as reference for our `plugin.json` and `hooks.json` format
- **Skill SKILL.md format**: Follow existing skills (e.g., vibeflow skills) for the `/analytics-dashboard` skill definition

### New Components Needed

| Component | Purpose |
|-----------|---------|
| `.claude-plugin/plugin.json` | Plugin metadata (name, version, description) |
| `hooks/hooks.json` | Hook declarations replacing `.claude/settings.json` |
| `skills/analytics-dashboard/SKILL.md` | Skill that launches the Django dashboard server |

---

## Risk Assessment & Go/No-Go Recommendation

### Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Plugin packaging format not well-documented | Medium | Reference vibeflow plugin as working example; validate with `claude plugin install --plugin-dir .` during dev |
| `resolve_skill_for_path` bug (always returns None) | Low | Fix is straightforward — build skill_paths from `discover_all()` before calling |
| Breaking existing project-scoped hook users | Medium | Keep `.claude/settings.json` for dev; document plugin migration path |
| Django server management in SKILL.md | Low | Skill can use a simple shell command to start/stop the server |

### Go/No-Go

**GO** — All risks are manageable. The core code is already written and tested. This is primarily a packaging and configuration task with one bug fix. The vibeflow plugin provides a working reference implementation.

### Estimated Scope

- 3 new files: `plugin.json`, `hooks.json`, `SKILL.md`
- 1 bug fix: `log_event.py` `resolve_skill_for_path` call
- 1 minor improvement: Django `SECRET_KEY` generation
- README update for plugin install instructions

---

## References

- ADR: `docs/adrs/adr-1-plugin-packaging.md`
- Tech Spec: `docs/specs/spec-skills-analytics.md` (Plugin Directory Structure section)
- VibeFlow plugin reference: `~/.claude/plugins/cache/vibeflow/`
