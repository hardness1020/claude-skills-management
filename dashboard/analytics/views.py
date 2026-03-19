"""Django views for skills analytics dashboard."""

import json
from django.http import JsonResponse, HttpResponse
from django.template import loader

from scripts import db
from dashboard.analytics import analytics


def _parse_date_params(request):
    """Extract and validate start/end date params. Returns (start, end) or raises ValueError."""
    start = request.GET.get("start")
    end = request.GET.get("end")
    if not start or not end:
        raise ValueError("Missing required parameters: start, end")
    if start > end:
        raise ValueError("start must be before end")
    return start, end


def _get_conn():
    """Get a DB connection with schema initialized."""
    conn = db.get_connection()
    db.init_schema(conn)
    return conn


def dashboard(request):
    """Serve the single-page HTML dashboard."""
    template = loader.get_template("analytics/dashboard.html")
    return HttpResponse(template.render({}, request))


def api_frequency(request):
    """GET /api/frequency/?start=<iso>&end=<iso>"""
    try:
        start, end = _parse_date_params(request)
    except ValueError as e:
        return JsonResponse({"error": str(e)}, status=400)

    conn = _get_conn()
    result = analytics.frequency_ranking(conn, start, end)
    conn.close()
    return JsonResponse(result, safe=False)


def api_adoption(request):
    """GET /api/adoption/?start=<iso>&end=<iso>"""
    try:
        start, end = _parse_date_params(request)
    except ValueError as e:
        return JsonResponse({"error": str(e)}, status=400)

    conn = _get_conn()
    result = analytics.adoption_curves(conn, start, end)
    conn.close()
    return JsonResponse(result, safe=False)


def api_usefulness(request):
    """GET /api/usefulness/?start=<iso>&end=<iso>&grace_days=<int>"""
    try:
        start, end = _parse_date_params(request)
    except ValueError as e:
        return JsonResponse({"error": str(e)}, status=400)

    grace_days = int(request.GET.get("grace_days", 7))

    conn = _get_conn()
    result = analytics.usefulness_scores(conn, start, end, grace_period_days=grace_days)
    conn.close()
    return JsonResponse(result, safe=False)


def api_trends(request):
    """GET /api/trends/?start=<iso>&end=<iso>&granularity=<day|week|month>"""
    try:
        start, end = _parse_date_params(request)
    except ValueError as e:
        return JsonResponse({"error": str(e)}, status=400)

    granularity = request.GET.get("granularity", "day")
    if granularity not in ("day", "week", "month"):
        return JsonResponse({"error": "Invalid granularity. Must be day, week, or month."}, status=400)

    conn = _get_conn()
    result = analytics.usage_trends(conn, start, end, granularity=granularity)
    conn.close()
    return JsonResponse(result, safe=False)


def api_coverage(request, skill_name):
    """GET /api/coverage/<skill_name>/?start=<iso>&end=<iso>&file_grace_days=<int>"""
    try:
        start, end = _parse_date_params(request)
    except ValueError as e:
        return JsonResponse({"error": str(e)}, status=400)

    file_grace_days = int(request.GET.get("file_grace_days", 7))

    conn = _get_conn()
    try:
        result = analytics.structure_coverage(conn, skill_name, start, end, file_grace_period_days=file_grace_days)
    except KeyError:
        conn.close()
        return JsonResponse({"error": f"Skill not found: {skill_name}"}, status=404)
    conn.close()
    return JsonResponse(result, safe=False)


def api_skills(request):
    """GET /api/skills/"""
    conn = _get_conn()
    rows = conn.execute(
        """SELECT s.name, s.source, s.scope, s.status, s.first_seen_at,
                  (SELECT MAX(timestamp) FROM skill_invocations WHERE skill_name = s.name) as last_invoked,
                  s.total_nested_files
           FROM skills s
           ORDER BY s.name"""
    ).fetchall()
    conn.close()

    result = [
        {
            "name": r[0], "source": r[1], "scope": r[2], "status": r[3],
            "first_seen": r[4], "last_invoked": r[5], "total_files": r[6],
        }
        for r in rows
    ]
    return JsonResponse(result, safe=False)
