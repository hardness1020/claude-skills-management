"""Analytics module for skills usage analysis.

Computes usefulness scores, frequency rankings, adoption curves,
usage trends, and structure coverage with time-normalized metrics.
"""

import sqlite3


def frequency_ranking(
    conn: sqlite3.Connection, start: str, end: str
) -> list[dict]:
    """Return skills ranked by invocation count in time window."""
    raise NotImplementedError


def adoption_curves(
    conn: sqlite3.Connection, start: str, end: str
) -> list[dict]:
    """Return first-use date and cumulative invocation curve per skill."""
    raise NotImplementedError


def usefulness_scores(
    conn: sqlite3.Connection,
    start: str,
    end: str,
    grace_period_days: int = 7,
    weights: dict = None,
) -> list[dict]:
    """Compute composite usefulness score per skill."""
    raise NotImplementedError


def usage_trends(
    conn: sqlite3.Connection, start: str, end: str, granularity: str = "day"
) -> list[dict]:
    """Return time-series of invocations aggregated by granularity."""
    raise NotImplementedError


def structure_coverage(
    conn: sqlite3.Connection,
    skill_name: str,
    start: str,
    end: str,
    file_grace_period_days: int = 7,
) -> dict:
    """Return per-file access counts within a skill, with time-normalized metrics."""
    raise NotImplementedError
