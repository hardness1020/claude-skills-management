# ADR: Use SQLite for Event Storage

**File:** docs/adrs/adr-1-sqlite-storage.md
**Status:** Accepted
**Date:** 2026-03-18
**Decision Makers:** Marcus Chang

## Context

The skills analytics system needs a storage layer that:
- Handles concurrent writes from hook scripts and reads from the Django dashboard
- Persists across Claude Code sessions
- Supports time-range queries with indexing (the dashboard filters by date intervals)
- Stores structured event data (invocations, file accesses, lifecycle events, inventory snapshots)
- Works locally with zero setup (no external database server)
- Performs well up to 100K+ events

The hook scripts are the write-heavy path (every skill invocation and file read), while the dashboard is the read-heavy path (aggregation queries over time ranges).

## Decision

We will adopt **SQLite in WAL (Write-Ahead Logging) mode** because it handles concurrent read/write access, requires zero setup, and is bundled with Python's standard library.

Key aspects:
- Database file stored at `${CLAUDE_PLUGIN_DATA}/skills_analytics.db`
- WAL mode enabled on first connection (`PRAGMA journal_mode=WAL`)
- Indexes on `timestamp` and `skill_name` columns for query performance
- Django ORM for dashboard reads; raw `sqlite3` module for hook script writes (to avoid Django dependency in hooks)
- Connection timeout of 5 seconds — if locked, skip the write rather than block Claude Code
- Hook scripts open/close connections per invocation (no connection pooling needed for short-lived processes)

## Consequences

### Positive

+ Zero setup — SQLite is bundled with Python, no external server needed
+ Single-file database — easy to back up, move, or inspect
+ WAL mode supports concurrent readers and a single writer without blocking
+ Excellent performance for the expected scale (100K events = ~50MB)
+ `${CLAUDE_PLUGIN_DATA}` provides a stable, persistent location
+ Django has native SQLite support via `django.db.backends.sqlite3`

### Negative

- Single-writer limitation — if two hook scripts fire simultaneously, one waits (mitigated by WAL mode and short write duration)
- No built-in replication or sharing — analytics data is per-machine only
- SQLite on network filesystems (NFS, SMB) can corrupt — must be on local disk

### Neutral

* Hook scripts use raw `sqlite3` (stdlib) to avoid importing Django — this means two code paths for DB access (hooks vs. dashboard), but they share the same schema
* 90-day retention with periodic cleanup keeps the database from growing unbounded

## Alternatives Considered

### Alternative 1: JSON Log Files

**Description:** Append events as JSON lines to flat files (one file per day or per event type). Dashboard reads and parses the files.

**Pros:**
- Simplest possible implementation
- Human-readable logs
- No database dependency

**Cons:**
- No indexing — time-range queries require scanning all files
- Aggregation queries (frequency, adoption curves) are expensive on large files
- No concurrent access guarantees (append-only helps, but race conditions possible)
- Dashboard performance degrades linearly with data volume

**Why not chosen:** The dashboard needs fast aggregation queries over configurable time ranges. Without indexes, query latency grows linearly with event count, violating the <3s page load SLO at 100K events.

### Alternative 2: PostgreSQL

**Description:** Use PostgreSQL for full relational database features, running as a local service or via Docker.

**Pros:**
- Excellent concurrent access
- Rich query features (window functions, CTEs)
- Better suited for very large datasets

**Cons:**
- Requires external service installation (PostgreSQL server or Docker)
- Significant setup overhead for a local-only analytics tool
- Overkill for single-user, single-machine use case
- Cannot use `${CLAUDE_PLUGIN_DATA}` — needs its own data directory

**Why not chosen:** The setup overhead contradicts the <10 minute install SLO. PostgreSQL is designed for multi-user networked access — we're single-user, local-only. SQLite is the right tool for this scale.

### Alternative 3: DuckDB

**Description:** Use DuckDB, an embedded analytical database optimized for OLAP queries.

**Pros:**
- Excellent aggregation performance
- Columnar storage is ideal for time-series analytics
- Embedded, no server needed

**Cons:**
- Not bundled with Python — requires `pip install duckdb`
- Less mature ecosystem than SQLite
- Django has no native DuckDB backend — would need a custom adapter or skip ORM
- Concurrent write support is more limited than SQLite WAL

**Why not chosen:** The extra dependency and lack of Django ORM support add complexity without sufficient benefit at our scale. SQLite with proper indexes handles 100K events well within our SLOs.

## Rollback Plan

1. Export all data from SQLite using Django's `dumpdata` or a custom export script
2. Set up the target database (PostgreSQL, DuckDB, or flat files)
3. Import data into new storage
4. Update `db.py` connection helper and Django `settings.py` database backend
5. Update hook scripts to write to new storage

**Estimated rollback effort:** Medium
**Data considerations:** All data is structured with clear schemas — export/import is straightforward. The Django ORM abstraction in the dashboard means most view code doesn't change.

## Links

**PRD:** `docs/prds/prd.md`
**TECH-SPECs:** `docs/specs/spec-skills-analytics.md`
**FEATUREs:** None yet
**Related ADRs:** `docs/adrs/adr-1-plugin-packaging.md`
