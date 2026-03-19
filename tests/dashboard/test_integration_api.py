"""Integration tests for Django API → DB pipeline.

These tests exercise the full path from Django request through
views to actual SQLite reads, without mocking the analytics layer.
"""

import json
import os
import pytest
from django.test import RequestFactory

from scripts import db
from dashboard.analytics import views


@pytest.fixture
def rf():
    return RequestFactory()


@pytest.fixture
def seeded_db(tmp_path, monkeypatch):
    """Provide a seeded SQLite DB and point views to it."""
    db_dir = tmp_path / "plugin_data"
    db_dir.mkdir()
    db_path = str(db_dir / "skills_analytics.db")
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(db_dir))

    conn = db.get_connection(db_path)
    db.init_schema(conn)

    # Seed a skill
    skill_id = db.upsert_skill(conn, {
        "name": "test-skill",
        "source": "folder",
        "scope": "user",
        "path": "/test/skills/test-skill",
        "total_nested_files": 2,
    })

    # Seed nested files
    db.upsert_skill_file(conn, skill_id, "SKILL.md", "markdown", "content", "2026-03-01T00:00:00Z")
    db.upsert_skill_file(conn, skill_id, "scripts/run.py", "script", "script", "2026-03-01T00:00:00Z")

    # Seed invocations
    for i in range(3):
        db.insert_skill_invocation(conn, {
            "timestamp": f"2026-03-{10+i:02d}T10:00:00Z",
            "session_id": f"sess-api-{i}",
            "skill_name": "test-skill",
            "invocation_id": f"toolu_api_{i}",
            "source": "folder",
            "scope": "user",
            "project_dir": "/test",
            "args": "",
        })

    # Seed file accesses
    db.insert_file_access(conn, {
        "timestamp": "2026-03-10T11:00:00Z",
        "session_id": "sess-api-0",
        "skill_name": "test-skill",
        "file_path": "/test/skills/test-skill/SKILL.md",
        "relative_path": "SKILL.md",
        "file_type": "markdown",
        "hierarchy": "content",
        "project_dir": "/test",
    })

    conn.close()
    return db_path


class TestApiFrequencyIntegration:
    @pytest.mark.integration
    def test_returns_real_data(self, rf, seeded_db):
        request = rf.get("/api/frequency/", {
            "start": "2026-03-01T00:00:00Z",
            "end": "2026-03-31T23:59:59Z",
        })
        response = views.api_frequency(request)
        assert response.status_code == 200
        data = json.loads(response.content)
        assert len(data) == 1
        assert data[0]["skill_name"] == "test-skill"
        assert data[0]["count"] == 3


class TestApiAdoptionIntegration:
    @pytest.mark.integration
    def test_returns_cumulative_curve(self, rf, seeded_db):
        request = rf.get("/api/adoption/", {
            "start": "2026-03-01T00:00:00Z",
            "end": "2026-03-31T23:59:59Z",
        })
        response = views.api_adoption(request)
        assert response.status_code == 200
        data = json.loads(response.content)
        assert len(data) == 1
        assert len(data[0]["cumulative"]) >= 1


class TestApiUsefulnessIntegration:
    @pytest.mark.integration
    def test_returns_scores(self, rf, seeded_db):
        request = rf.get("/api/usefulness/", {
            "start": "2026-03-01T00:00:00Z",
            "end": "2026-03-31T23:59:59Z",
        })
        response = views.api_usefulness(request)
        assert response.status_code == 200
        data = json.loads(response.content)
        assert len(data) >= 1
        assert "score" in data[0]
        assert "usage_rate" in data[0]


class TestApiTrendsIntegration:
    @pytest.mark.integration
    def test_returns_daily_trends(self, rf, seeded_db):
        request = rf.get("/api/trends/", {
            "start": "2026-03-01T00:00:00Z",
            "end": "2026-03-31T23:59:59Z",
            "granularity": "day",
        })
        response = views.api_trends(request)
        assert response.status_code == 200
        data = json.loads(response.content)
        assert len(data) >= 1
        total = sum(d["count"] for d in data)
        assert total == 3


class TestApiCoverageIntegration:
    @pytest.mark.integration
    def test_returns_file_coverage(self, rf, seeded_db):
        request = rf.get("/api/coverage/test-skill/", {
            "start": "2026-03-01T00:00:00Z",
            "end": "2026-03-31T23:59:59Z",
        })
        response = views.api_coverage(request, "test-skill")
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data["skill_name"] == "test-skill"
        assert data["total_files"] == 2
        assert data["accessed_files"] >= 1
        # Check per-file time metrics
        for f in data["files"]:
            assert "first_seen_at" in f
            assert "access_rate" in f
            assert "in_grace_period" in f

    @pytest.mark.integration
    def test_404_for_missing_skill(self, rf, seeded_db):
        request = rf.get("/api/coverage/nonexistent/", {
            "start": "2026-03-01T00:00:00Z",
            "end": "2026-03-31T23:59:59Z",
        })
        response = views.api_coverage(request, "nonexistent")
        assert response.status_code == 404


class TestApiSkillsIntegration:
    @pytest.mark.integration
    def test_returns_all_skills(self, rf, seeded_db):
        request = rf.get("/api/skills/")
        response = views.api_skills(request)
        assert response.status_code == 200
        data = json.loads(response.content)
        assert len(data) >= 1
        assert data[0]["name"] == "test-skill"
        assert data[0]["status"] == "active"


class TestDashboardIntegration:
    @pytest.mark.integration
    def test_returns_html_page(self, rf, seeded_db):
        request = rf.get("/")
        response = views.dashboard(request)
        assert response.status_code == 200
        assert "text/html" in response["Content-Type"]
