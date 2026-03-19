# PRD — Claude Code Skills Analytics

**Version:** v1.0.0
**File:** docs/prds/prd.md
**Owners:** Eng (Marcus Chang)
**Last_updated:** 2026-03-18

## Summary

There is no open-source tool for measuring whether Claude Code skills are actually useful. Teams accumulate skills over time with no visibility into usage patterns, adoption rates, or underutilization. Crucially, Claude Code skills use progressive disclosure — a skill is a hierarchy of markdown files, scripts, and assets where nested references are only loaded on demand. Tracking only top-level skill invocations misses whether the skill's internal structure is well-designed. This project delivers a Claude Code hook that logs both skill invocations and nested file accesses, plus a Django-based local dashboard with frequency, adoption, underutilization, trend analysis, and skill structure coverage — enabling data-driven decisions about which skills to keep, improve, or restructure.

## Problem & Context

- Claude Code supports extensibility through skills from two distinct sources, each with different installation scopes:
  - **Folder-based skills**: Defined directly in `.claude/skills/` within a project repository.
  - **Plugin-based skills**: Installed via plugins with three scope levels:
    - **User scope** — installed for the individual user across all projects
    - **Project scope** — installed for all collaborators on a repository
    - **Local scope** — installed for the individual user, in a specific repo only
- Teams accumulate dozens of skills across these sources and scopes with no way to measure their value. The same skill may exist at different scopes, and usage patterns differ by source (folder skills tend to be project-specific; plugin skills may be general-purpose).
- Anthropic internally uses a PreToolUse hook to log skill usage and identify popular vs. underperforming skills (per "Lessons from Building Claude Code" article). No open-source equivalent exists.
- Without usage data, teams cannot answer: Which skills are actually used? Which are declining? Which were installed but never invoked? Are new skills being adopted?
- Comparing skills by raw invocation count is misleading because **skills are added at different times** (a skill installed yesterday can't be compared to one installed 3 months ago). Useful analytics must normalize for skill age.
- Skills use **progressive disclosure**: a skill's nested files (scripts, reference docs, asset files) are loaded only when needed. A skill may have 10 internal files but only 3 get triggered in typical use. Tracking only top-level invocations misses this — you can't tell if a skill is well-structured or if half its content is dead weight.
- The skill hierarchy (skill → markdown → references) is distinct from the script/asset hierarchy (skill → scripts → data files). Both need to be tracked separately to understand skill design quality.

## Users & Use Cases

**Primary Users:**
- **Individual Developers**: Use Claude Code with various skills and want to understand which ones deliver value vs. clutter, and whether skill internals are well-structured.
- **Team Leads / Platform Engineers**: Manage skill inventories across teams, need data to curate recommended skill sets and retire unused ones.
- **Skill Authors**: Build and maintain skills, need data on which nested files/scripts within their skills are actually triggered to improve progressive disclosure design.

**Key Use Cases:**
1. A developer installs 20 Claude Code skills, wants a dashboard showing which 5 they actually use regularly.
2. A team lead reviews adoption trends after rolling out a new set of recommended skills, checking uptake over the past 2 weeks.
3. A platform engineer sees that a skill installed 3 months ago has a usage rate of 0.1/day while a skill installed last week already hits 3/day — the old skill is flagged for review despite having more total invocations.
6. A developer sees a skill with a high decay ratio — it was used heavily in the first 2 weeks but hasn't been touched in a month, suggesting it was a one-time need or has been superseded.
8. A team lead sees that 3 skills were deleted last month. The dashboard shows their historical usage — one had zero invocations (good riddance), but another was moderately used, prompting investigation into why it was removed.
4. A skill author sees that their skill has 8 nested reference files but only 2 are ever accessed — the other 6 may need restructuring or removal.
5. A developer drills into a skill's structure coverage to see which scripts and nested docs are triggered vs. dormant.
7. A team lead compares usage between project-scoped plugin skills (shared across the team) and local folder-based skills to decide which folder skills should be promoted to plugins for wider adoption.

## Scope (MoSCoW)

**Must Have:**
- JSON log schema for two event types: skill invocations and nested file accesses
- Log schema includes skill source (folder vs. plugin) and installation scope (user/project/local)
- Claude Code `PreToolUse` hook that logs skill invocation events and nested file accesses locally
- Claude Code `UserPromptSubmit` hook that snapshots the skill inventory on each conversation start, diffs against the previous snapshot, and logs `skill_added`/`skill_removed` lifecycle events
- Skill inventory snapshots via `UserPromptSubmit` hook: on each conversation start, scan all skill sources (`.claude/skills/` folder + plugin configs at all scopes), snapshot the current inventory, and diff against the previous snapshot to detect additions and deletions
- Deleted skill handling: when a skill is no longer present on disk but has historical log entries, mark it as "removed" in the dashboard with its deletion timestamp; preserve all historical data for removed skills
- Django + SQLite local web server with a single-page dashboard
- Frequency tracking: most and least used skills, sortable table
- Adoption pattern analysis: new skill first-use detection and uptake curve
- Underutilization detection using time-normalized analysis (see Usefulness Scoring below)
- Usage trend analysis: time-series view of skill invocations over configurable intervals
- Skill structure coverage: per-skill view showing which nested files are triggered vs. dormant, with separate tracking for the content hierarchy (markdown/references) and the script/asset hierarchy
- Time interval selector on dashboard (day, week, month, custom range)
- All data stored locally (no telemetry, no remote calls)

**Should Have:**
- Export dashboard data as CSV/JSON
- Skill metadata registry (name, description, category, source, scope) auto-populated from skill frontmatter and plugin config
- Filter/group dashboard by source (folder vs. plugin) and scope (user/project/local)
- Coverage heatmap showing nested file access frequency across all skills
- Drill-down from skill to its file tree with access counts

**Could Have:**
- CLI companion for quick terminal queries (e.g., `skills top 10`)
- Skill co-occurrence analysis (which skills are used together)
- Token/cost efficiency tracking per skill invocation
- Recommendations for skill restructuring based on coverage patterns

**Won't Have (this version):**
- Remote/cloud telemetry or aggregation
- Real-time streaming dashboard (batch refresh is fine)
- Built-in skill marketplace or recommendation engine
- Automated skill installation/removal based on analytics
- Multi-agent support (Codex, OpenClaw, etc.) — Claude Code only for v1

## Success Metrics

**Primary Metrics:**
| Metric | Baseline | Target | Timeline |
|--------|----------|--------|----------|
| Dashboard analysis views | 0 | 5 (frequency, adoption, usefulness scoring, trends, structure coverage) | v1.0 |
| Log-to-dashboard latency | N/A | < 5s for 10K events | v1.0 |
| Setup time for new user | N/A | < 10 minutes (install hook + first dashboard view) | v1.0 |
| Nested file tracking coverage | 0 | Track all file reads within skill directories | v1.0 |

**Guardrail Metrics:**
- Zero data leaves the local machine — no outbound network calls from the analytics system
- Dashboard page load < 3s with up to 100K logged events
- Log file growth < 1MB per 1000 invocations

## Non-Goals

- This project does not measure skill *correctness* or output quality — only usage and structure patterns
- This project does not integrate with any remote analytics platform (Grafana, Datadog, etc.)
- This project does not modify or manage skills themselves — it is read-only analytics
- This project does not support agents other than Claude Code in v1
- This project does not evaluate whether a nested file's *content* is good — only whether it gets accessed

## Usefulness Scoring Model

The core analytics challenge: skills are added at different times and may be improved during their lifetime. A simple "total invocations" ranking is meaningless. The system must use the following methods to fairly assess skill usefulness:

### 1. Time-Normalized Usage Rate

Compare skills by **invocations per unit time since installation**, not absolute counts. A skill added 2 days ago with 10 invocations (5/day) is healthier than one added 60 days ago with 30 invocations (0.5/day).

- **Metric**: `usage_rate = invocations / days_since_install`
- **Grace period**: Skills younger than a configurable threshold (default: 7 days) are excluded from underutilization flags — they haven't had enough time to prove themselves.

### 2. Usage Decay Detection

Detect skills whose usage is **declining over time**, signaling they may have been useful once but are now stale or superseded.

- **Method**: Compare usage rate in the recent window (e.g., last 14 days) vs. the skill's lifetime average rate. A significant drop (e.g., recent rate < 30% of lifetime rate) flags the skill as "decaying."
- **Output**: Decay ratio per skill, surfaced in the dashboard as a trend indicator.

### 3. Engagement Depth Scoring

A skill that gets invoked but only triggers 1 of its 8 nested files is shallowly used. A skill that consistently triggers deep references is deeply engaged.

- **Metric**: `depth_score = unique_nested_files_accessed / total_nested_files_in_skill` (averaged over invocations in the time window)
- **Interpretation**: Low depth + high invocations = the skill is used but its progressive disclosure structure may be bloated. High depth + low invocations = the skill is thorough when used but rarely needed.

### 4. Composite Usefulness Score

Combine the above into a single score for ranking and flagging:

```
usefulness = w1 * normalized_usage_rate
           + w2 * (1 - decay_ratio)
           + w3 * depth_score
```

- Weights (w1–w3) are configurable with sensible defaults
- Skills below a threshold are flagged as "candidates for review"
- The dashboard shows the composite score with a breakdown of contributing factors

## Requirements

### Functional Requirements

**User Stories:**
- As a developer, I can install a Claude Code hook so that every skill invocation is automatically logged locally, regardless of whether the skill comes from a folder or a plugin
- As a developer, I can see which nested files (scripts, references, assets) within a skill are accessed during each invocation
- As a team lead, I can see which skills are folder-based vs. plugin-installed, and at what scope (user/project/local), to understand the skill inventory
- As a developer, I can open a local dashboard and see my most/least used skills at a glance
- As a developer, I can set a time interval (day/week/month/custom) to scope all dashboard views
- As a developer, I can view adoption trends to see how quickly new skills gain traction
- As a developer, I can identify underutilized skills using a time-normalized score that accounts for when each skill was installed
- As a team lead, I can see deleted skills labeled as "removed" in the dashboard with their full historical usage preserved, so I can audit whether the right skills were removed
- As a team lead, I can see a composite usefulness score per skill that factors in usage rate, decay, and depth
- As a skill author, I can view structure coverage for my skill to see which nested files are triggered vs. dormant
- As a skill author, I can distinguish between content hierarchy access (markdown/references) and script/asset hierarchy access

**Acceptance Criteria:**
- Hook logs skill invocations with: timestamp, skill_name, invocation_id, duration_ms, source (folder/plugin), scope (user/project/local), and metadata
- Hook logs nested file accesses with: timestamp, skill_name, file_path, file_type (markdown/script/asset/reference), and parent invocation_id
- `UserPromptSubmit` hook snapshots the skill inventory on each conversation start; diffs detect `skill_added` and `skill_removed` events with timestamps
- Removed skills retain all historical data and are labeled "removed" in the dashboard
- Dashboard loads and renders all 5 analysis views from a SQLite database
- Time interval selector updates all views without page reload
- Underutilization view ranks skills by composite usefulness score, not raw invocation counts
- Skills younger than the grace period (default 7 days) are excluded from underutilization flags
- Decay detection compares recent usage rate vs. lifetime average and flags skills with significant decline
- Adoption view shows first-use date and cumulative invocation curve per skill
- Trend view shows a time-series chart of invocations with configurable granularity
- Structure coverage view shows per-skill file tree with access counts, distinguishing content hierarchy from script hierarchy

### Non-Functional Requirements

| Category | Requirement |
|----------|-------------|
| Latency | Dashboard page load < 3s with 100K events |
| Privacy | All data local-only, zero outbound network calls |
| Portability | Runs on macOS, Linux, Windows (Python 3.10+) |
| Storage | SQLite, single-file database, < 1MB per 1K events |
| Security | No authentication required (local-only access on localhost) |

## Dependencies

**Data Dependencies:**
- Claude Code PreToolUse hook event data (skill invocations)
- Claude Code file read events within skill directories (nested file access tracking)
- `.claude/skills/` directory contents (folder-based skill discovery)
- Claude Code plugin configuration (plugin-based skill discovery with scope metadata)

**Service Dependencies:**
- None (fully local, self-contained)

**Legal/Policy:**
- Open-source license (already MIT per existing LICENSE)
- No PII collection — skill names and timestamps only

**Third-Party:**
- Django (web framework)
- SQLite (database, bundled with Python)
- Chart.js or similar (frontend charting library)

## Risks & Mitigations

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Nested file access tracking may miss reads if Claude Code doesn't expose file-level hooks | High | Medium | Investigate available hook points during discovery; fallback to filesystem watching or log parsing |
| Hook overhead slows down agent execution | Medium | Low | Hook writes are async/non-blocking; benchmark during implementation |
| SQLite performance degrades at high event volumes | Medium | Low | Add indexes on timestamp and skill_name; archive old data |
| Django is heavy for a local dashboard | Low | Low | Use minimal Django config; consider switching to lighter framework in v2 if needed |

## Analytics & Telemetry

**Events to Track:**
- `skill_invoked`: Core event — logged by PreToolUse hook on every skill invocation
- `nested_file_accessed`: Logged when a file within a skill directory is read during an invocation (tracks both content hierarchy and script hierarchy separately)
- `skill_added`: Logged by UserPromptSubmit hook when a new skill is detected in the inventory snapshot diff
- `skill_removed`: Logged by UserPromptSubmit hook when a previously known skill is no longer present in the inventory snapshot diff
- `dashboard_viewed`: Fired when user opens the dashboard (local only, for self-analytics)

**Dashboards:**
- Single-page local dashboard: frequency, adoption, usefulness scoring (time-normalized), trends, and structure coverage views

**Alerts:**
- None in v1 (local-only system, no alerting infrastructure)

---

> **Note:** Implementation details (framework choices, specific technologies) belong in TECH-SPEC and ADRs, not in the PRD.
