"""Analytics module for skills usage analysis.

Computes usefulness scores, frequency rankings, adoption curves,
usage trends, and structure coverage with time-normalized metrics.
"""

import sqlite3
from datetime import datetime, timezone


def frequency_ranking(
    conn: sqlite3.Connection, start: str, end: str
) -> list[dict]:
    """Return skills ranked by invocation count in time window."""
    # Count invocations first, then join skill metadata
    rows = conn.execute(
        """SELECT si.skill_name, si.cnt,
                  COALESCE(s.source, '') as source,
                  COALESCE(s.scope, '') as scope,
                  COALESCE(s.status, 'active') as status
           FROM (
               SELECT skill_name, COUNT(*) as cnt
               FROM skill_invocations
               WHERE timestamp >= ? AND timestamp <= ?
               GROUP BY skill_name
           ) si
           LEFT JOIN skills s ON si.skill_name = s.name AND s.id = (
               SELECT MIN(id) FROM skills WHERE name = si.skill_name
           )
           ORDER BY si.cnt DESC""",
        (start, end),
    ).fetchall()
    return [
        {"skill_name": r[0], "count": r[1], "source": r[2], "scope": r[3], "status": r[4]}
        for r in rows
    ]


def adoption_curves(
    conn: sqlite3.Connection, start: str, end: str
) -> list[dict]:
    """Return first-use date and cumulative invocation curve per skill."""
    # Get all skills with invocations in window
    skills = conn.execute(
        """SELECT DISTINCT skill_name,
                  MIN(timestamp) as first_seen
           FROM skill_invocations
           WHERE timestamp >= ? AND timestamp <= ?
           GROUP BY skill_name""",
        (start, end),
    ).fetchall()

    result = []
    for skill_name, first_seen in skills:
        # Get daily cumulative counts
        daily = conn.execute(
            """SELECT DATE(timestamp) as day, COUNT(*) as cnt
               FROM skill_invocations
               WHERE skill_name = ? AND timestamp >= ? AND timestamp <= ?
               GROUP BY DATE(timestamp)
               ORDER BY day""",
            (skill_name, start, end),
        ).fetchall()

        cumulative = []
        running = 0
        for day, cnt in daily:
            running += cnt
            cumulative.append({"date": day, "count": running})

        result.append({
            "skill_name": skill_name,
            "first_seen": first_seen,
            "cumulative": cumulative,
        })

    return result


def usefulness_scores(
    conn: sqlite3.Connection,
    start: str,
    end: str,
    grace_period_days: int = 7,
    weights: dict = None,
) -> list[dict]:
    """Compute composite usefulness score per skill."""
    if weights is None:
        weights = {"w1": 0.4, "w2": 0.35, "w3": 0.25}

    now = datetime.now(timezone.utc)

    skills = conn.execute(
        "SELECT id, name, source, scope, status, first_seen_at, total_nested_files FROM skills"
    ).fetchall()

    result = []
    for skill_id, name, source, scope, status, first_seen_at, total_files in skills:
        try:
            first_seen = datetime.fromisoformat(first_seen_at.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            first_seen = now

        days_since = max((now - first_seen).days, 1)
        in_grace = days_since < grace_period_days

        # Usage rate
        inv_count = conn.execute(
            "SELECT COUNT(*) FROM skill_invocations WHERE skill_name = ? AND timestamp >= ? AND timestamp <= ?",
            (name, start, end),
        ).fetchone()[0]
        usage_rate = inv_count / days_since

        # Decay: compare last 14 days vs lifetime
        recent_start = max(
            first_seen,
            now - __import__("datetime").timedelta(days=14),
        ).isoformat()
        recent_count = conn.execute(
            "SELECT COUNT(*) FROM skill_invocations WHERE skill_name = ? AND timestamp >= ?",
            (name, recent_start),
        ).fetchone()[0]
        recent_days = max((now - datetime.fromisoformat(recent_start.replace("Z", "+00:00"))).days, 1)
        recent_rate = recent_count / recent_days
        lifetime_rate = usage_rate
        if lifetime_rate > 0:
            decay_ratio = max(0.0, 1.0 - (recent_rate / lifetime_rate))
        else:
            decay_ratio = 0.0

        # Depth score
        if total_files and total_files > 0:
            accessed = conn.execute(
                """SELECT COUNT(DISTINCT relative_path)
                   FROM file_accesses
                   WHERE skill_name = ? AND timestamp >= ? AND timestamp <= ?""",
                (name, start, end),
            ).fetchone()[0]
            depth_score = min(accessed / total_files, 1.0)
        else:
            depth_score = 0.0

        # Composite score
        score = (
            weights["w1"] * min(usage_rate, 10.0) / 10.0
            + weights["w2"] * (1.0 - decay_ratio)
            + weights["w3"] * depth_score
        )

        result.append({
            "skill_name": name,
            "score": round(score, 4),
            "usage_rate": round(usage_rate, 4),
            "decay_ratio": round(decay_ratio, 4),
            "depth_score": round(depth_score, 4),
            "days_since_install": days_since,
            "status": status,
            "in_grace_period": in_grace,
        })

    result.sort(key=lambda x: x["score"], reverse=True)
    return result


def usage_trends(
    conn: sqlite3.Connection, start: str, end: str, granularity: str = "day"
) -> list[dict]:
    """Return time-series of invocations aggregated by granularity."""
    if granularity not in ("day", "week", "month"):
        raise ValueError(f"Invalid granularity: {granularity}. Must be day, week, or month.")

    if granularity == "day":
        date_expr = "DATE(timestamp)"
    elif granularity == "week":
        date_expr = "DATE(timestamp, 'weekday 0', '-6 days')"
    else:
        date_expr = "DATE(timestamp, 'start of month')"

    rows = conn.execute(
        f"""SELECT {date_expr} as period, skill_name, COUNT(*) as cnt
            FROM skill_invocations
            WHERE timestamp >= ? AND timestamp <= ?
            GROUP BY period, skill_name
            ORDER BY period""",
        (start, end),
    ).fetchall()

    # Group by period
    periods = {}
    for period, skill_name, cnt in rows:
        if period not in periods:
            periods[period] = {"date": period, "count": 0, "by_skill": {}}
        periods[period]["count"] += cnt
        periods[period]["by_skill"][skill_name] = cnt

    return list(periods.values())


def structure_coverage(
    conn: sqlite3.Connection,
    skill_name: str,
    start: str,
    end: str,
    file_grace_period_days: int = 7,
) -> dict:
    """Return per-file access counts within a skill, with time-normalized metrics."""
    row = conn.execute(
        "SELECT id, total_nested_files FROM skills WHERE name = ?",
        (skill_name,),
    ).fetchone()

    if row is None:
        raise KeyError(f"Skill not found: {skill_name}")

    skill_id = row[0]
    now = datetime.now(timezone.utc)

    # Get all registered files
    files = conn.execute(
        "SELECT relative_path, file_type, hierarchy, first_seen_at, removed_at FROM skill_files WHERE skill_id = ?",
        (skill_id,),
    ).fetchall()

    # Get access counts per file
    accesses = conn.execute(
        """SELECT relative_path, COUNT(*) as cnt
           FROM file_accesses
           WHERE skill_name = ? AND timestamp >= ? AND timestamp <= ?
           GROUP BY relative_path""",
        (skill_name, start, end),
    ).fetchall()
    access_map = {r[0]: r[1] for r in accesses}

    file_results = []
    mature_count = 0
    accessed_mature = 0
    total_count = len(files)
    accessed_count = 0

    for rel_path, file_type, hierarchy, first_seen_at, removed_at in files:
        try:
            first_seen = datetime.fromisoformat(first_seen_at.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            first_seen = now

        days_since = max((now - first_seen).days, 0)
        in_grace = days_since < file_grace_period_days
        count = access_map.get(rel_path, 0)
        access_rate = count / max(days_since, 1)

        if count > 0:
            accessed_count += 1

        if not in_grace:
            mature_count += 1
            if count > 0:
                accessed_mature += 1

        file_results.append({
            "relative_path": rel_path,
            "file_type": file_type,
            "hierarchy": hierarchy,
            "access_count": count,
            "first_seen_at": first_seen_at,
            "days_since_first_seen": days_since,
            "access_rate": round(access_rate, 4),
            "in_grace_period": in_grace,
        })

    depth_score = accessed_mature / mature_count if mature_count > 0 else 0.0

    return {
        "skill_name": skill_name,
        "total_files": total_count,
        "mature_files": mature_count,
        "accessed_files": accessed_count,
        "depth_score": round(depth_score, 4),
        "files": file_results,
    }
