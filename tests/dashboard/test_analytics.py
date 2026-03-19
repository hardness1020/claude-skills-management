"""Unit tests for dashboard/analytics/analytics.py."""

import sqlite3
import pytest
from datetime import datetime, timedelta

from scripts import db
from dashboard.analytics import analytics


@pytest.fixture
def conn(tmp_path):
    """Provide an initialized SQLite connection with test data."""
    connection = db.get_connection(str(tmp_path / "test.db"))
    db.init_schema(connection)
    return connection


def seed_skills(conn):
    """Insert test skills."""
    db.upsert_skill(conn, {"name": "popular", "source": "folder", "scope": "user", "path": "/popular", "total_nested_files": 3})
    db.upsert_skill(conn, {"name": "unused", "source": "plugin", "scope": "project", "path": "/unused", "total_nested_files": 2})
    db.upsert_skill(conn, {"name": "new-skill", "source": "folder", "scope": "user", "path": "/new", "total_nested_files": 1})


def seed_invocations(conn, skill_name, count, start_date="2026-03-01"):
    """Insert test invocations spread over days."""
    base = datetime.fromisoformat(start_date)
    for i in range(count):
        ts = (base + timedelta(hours=i * 6)).isoformat() + "Z"
        db.insert_skill_invocation(conn, {
            "timestamp": ts,
            "session_id": f"sess-{i}",
            "skill_name": skill_name,
            "invocation_id": f"toolu_{skill_name}_{i}",
            "source": "folder",
            "scope": "user",
            "project_dir": "/tmp",
            "args": "",
        })


def seed_file_accesses(conn, skill_name, files, count_each=1):
    """Insert file access events for a skill."""
    for f in files:
        for i in range(count_each):
            db.insert_file_access(conn, {
                "timestamp": f"2026-03-{10+i:02d}T10:00:00Z",
                "session_id": f"sess-{i}",
                "skill_name": skill_name,
                "file_path": f"/skills/{skill_name}/{f}",
                "relative_path": f,
                "file_type": "reference",
                "hierarchy": "content",
                "project_dir": "/tmp",
            })


# --- frequency_ranking ---

class TestFrequencyRanking:
    @pytest.mark.unit
    def test_ranks_by_count(self, conn):
        seed_skills(conn)
        seed_invocations(conn, "popular", 10)
        seed_invocations(conn, "unused", 0)

        result = analytics.frequency_ranking(conn, "2026-03-01T00:00:00Z", "2026-03-31T23:59:59Z")

        assert len(result) >= 1
        assert result[0]["skill_name"] == "popular"
        assert result[0]["count"] == 10

    @pytest.mark.unit
    def test_respects_time_window(self, conn):
        seed_skills(conn)
        seed_invocations(conn, "popular", 10, "2026-03-01")

        result = analytics.frequency_ranking(conn, "2026-04-01T00:00:00Z", "2026-04-30T23:59:59Z")
        popular = [r for r in result if r["skill_name"] == "popular"]
        if popular:
            assert popular[0]["count"] == 0
        # or empty result is fine

    @pytest.mark.unit
    def test_empty_db_returns_empty(self, conn):
        result = analytics.frequency_ranking(conn, "2026-03-01T00:00:00Z", "2026-03-31T23:59:59Z")
        assert result == []


# --- adoption_curves ---

class TestAdoptionCurves:
    @pytest.mark.unit
    def test_returns_first_seen_and_cumulative(self, conn):
        seed_skills(conn)
        seed_invocations(conn, "popular", 5)

        result = analytics.adoption_curves(conn, "2026-03-01T00:00:00Z", "2026-03-31T23:59:59Z")

        popular = [r for r in result if r["skill_name"] == "popular"]
        assert len(popular) == 1
        assert "first_seen" in popular[0]
        assert "cumulative" in popular[0]
        assert isinstance(popular[0]["cumulative"], list)


# --- usefulness_scores ---

class TestUsefulnessScores:
    @pytest.mark.unit
    def test_excludes_skills_in_grace_period(self, conn):
        seed_skills(conn)
        # new-skill first seen today — should be in grace period
        conn.execute(
            "UPDATE skills SET first_seen_at = ? WHERE name = 'new-skill'",
            (datetime.now().isoformat() + "Z",)
        )
        conn.commit()

        result = analytics.usefulness_scores(
            conn, "2026-03-01T00:00:00Z", "2026-03-31T23:59:59Z",
            grace_period_days=7,
        )
        new_skill = [r for r in result if r["skill_name"] == "new-skill"]
        if new_skill:
            assert new_skill[0]["in_grace_period"] is True

    @pytest.mark.unit
    def test_returns_composite_score_fields(self, conn):
        seed_skills(conn)
        seed_invocations(conn, "popular", 20)
        # Set first_seen_at to 30 days ago
        conn.execute(
            "UPDATE skills SET first_seen_at = ? WHERE name = 'popular'",
            ((datetime.now() - timedelta(days=30)).isoformat() + "Z",)
        )
        conn.commit()

        result = analytics.usefulness_scores(
            conn, "2026-03-01T00:00:00Z", "2026-03-31T23:59:59Z"
        )
        popular = [r for r in result if r["skill_name"] == "popular"]
        assert len(popular) == 1
        assert "score" in popular[0]
        assert "usage_rate" in popular[0]
        assert "decay_ratio" in popular[0]
        assert "depth_score" in popular[0]

    @pytest.mark.unit
    def test_usage_rate_calculation(self, conn):
        seed_skills(conn)
        seed_invocations(conn, "popular", 10)
        conn.execute(
            "UPDATE skills SET first_seen_at = ? WHERE name = 'popular'",
            ((datetime.now() - timedelta(days=10)).isoformat() + "Z",)
        )
        conn.commit()

        result = analytics.usefulness_scores(
            conn, "2026-03-01T00:00:00Z", "2026-03-31T23:59:59Z"
        )
        popular = [r for r in result if r["skill_name"] == "popular"]
        assert popular[0]["usage_rate"] == pytest.approx(1.0, abs=0.2)

    @pytest.mark.unit
    def test_configurable_weights(self, conn):
        seed_skills(conn)
        seed_invocations(conn, "popular", 10)
        conn.execute(
            "UPDATE skills SET first_seen_at = ? WHERE name = 'popular'",
            ((datetime.now() - timedelta(days=30)).isoformat() + "Z",)
        )
        conn.commit()

        result = analytics.usefulness_scores(
            conn, "2026-03-01T00:00:00Z", "2026-03-31T23:59:59Z",
            weights={"w1": 1.0, "w2": 0.0, "w3": 0.0},
        )
        assert len(result) >= 1


# --- usage_trends ---

class TestUsageTrends:
    @pytest.mark.unit
    def test_aggregates_by_day(self, conn):
        seed_skills(conn)
        seed_invocations(conn, "popular", 4)

        result = analytics.usage_trends(
            conn, "2026-03-01T00:00:00Z", "2026-03-31T23:59:59Z",
            granularity="day",
        )
        assert isinstance(result, list)
        if result:
            assert "date" in result[0]
            assert "count" in result[0]

    @pytest.mark.unit
    def test_aggregates_by_week(self, conn):
        seed_skills(conn)
        seed_invocations(conn, "popular", 10)

        result = analytics.usage_trends(
            conn, "2026-03-01T00:00:00Z", "2026-03-31T23:59:59Z",
            granularity="week",
        )
        assert isinstance(result, list)

    @pytest.mark.unit
    def test_aggregates_by_month(self, conn):
        seed_skills(conn)
        seed_invocations(conn, "popular", 10)

        result = analytics.usage_trends(
            conn, "2026-03-01T00:00:00Z", "2026-03-31T23:59:59Z",
            granularity="month",
        )
        assert isinstance(result, list)

    @pytest.mark.unit
    def test_invalid_granularity_raises(self, conn):
        with pytest.raises(ValueError):
            analytics.usage_trends(
                conn, "2026-03-01T00:00:00Z", "2026-03-31T23:59:59Z",
                granularity="hour",
            )


# --- structure_coverage ---

class TestStructureCoverage:
    @pytest.mark.unit
    def test_returns_file_level_coverage(self, conn):
        seed_skills(conn)
        skill_id = conn.execute("SELECT id FROM skills WHERE name = 'popular'").fetchone()[0]
        db.upsert_skill_file(conn, skill_id, "SKILL.md", "markdown", "content", "2026-03-01T00:00:00Z")
        db.upsert_skill_file(conn, skill_id, "references/guide.md", "reference", "content", "2026-03-01T00:00:00Z")
        db.upsert_skill_file(conn, skill_id, "scripts/run.py", "script", "script", "2026-03-01T00:00:00Z")
        seed_file_accesses(conn, "popular", ["SKILL.md", "references/guide.md"], count_each=3)

        result = analytics.structure_coverage(
            conn, "popular", "2026-03-01T00:00:00Z", "2026-03-31T23:59:59Z"
        )
        assert result["skill_name"] == "popular"
        assert result["total_files"] == 3
        assert result["accessed_files"] == 2
        assert "files" in result
        assert len(result["files"]) == 3

    @pytest.mark.unit
    def test_includes_per_file_time_metrics(self, conn):
        seed_skills(conn)
        skill_id = conn.execute("SELECT id FROM skills WHERE name = 'popular'").fetchone()[0]
        db.upsert_skill_file(conn, skill_id, "SKILL.md", "markdown", "content", "2026-03-01T00:00:00Z")
        seed_file_accesses(conn, "popular", ["SKILL.md"], count_each=5)

        result = analytics.structure_coverage(
            conn, "popular", "2026-03-01T00:00:00Z", "2026-03-31T23:59:59Z"
        )
        file_info = result["files"][0]
        assert "first_seen_at" in file_info
        assert "days_since_first_seen" in file_info
        assert "access_rate" in file_info
        assert "in_grace_period" in file_info

    @pytest.mark.unit
    def test_excludes_grace_period_files_from_depth_score(self, conn):
        seed_skills(conn)
        skill_id = conn.execute("SELECT id FROM skills WHERE name = 'popular'").fetchone()[0]
        db.upsert_skill_file(conn, skill_id, "SKILL.md", "markdown", "content", "2026-03-01T00:00:00Z")
        # This file was just added — should be in grace period
        db.upsert_skill_file(conn, skill_id, "references/new.md", "reference", "content", datetime.now().isoformat() + "Z")
        seed_file_accesses(conn, "popular", ["SKILL.md"], count_each=1)

        result = analytics.structure_coverage(
            conn, "popular", "2026-03-01T00:00:00Z", "2026-03-31T23:59:59Z",
            file_grace_period_days=7,
        )
        # depth_score should be 1/1 (only mature file SKILL.md, which is accessed)
        # not 1/2 (which would unfairly penalize for the new file)
        assert result["depth_score"] == pytest.approx(1.0)

    @pytest.mark.unit
    def test_skill_not_found_raises(self, conn):
        with pytest.raises(KeyError):
            analytics.structure_coverage(
                conn, "nonexistent", "2026-03-01T00:00:00Z", "2026-03-31T23:59:59Z"
            )
