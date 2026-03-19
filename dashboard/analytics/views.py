"""Django views for skills analytics dashboard."""

from django.http import JsonResponse, HttpResponse


def dashboard(request):
    """Serve the single-page HTML dashboard."""
    raise NotImplementedError


def api_frequency(request):
    """GET /api/frequency/?start=<iso>&end=<iso>"""
    raise NotImplementedError


def api_adoption(request):
    """GET /api/adoption/?start=<iso>&end=<iso>"""
    raise NotImplementedError


def api_usefulness(request):
    """GET /api/usefulness/?start=<iso>&end=<iso>&grace_days=<int>"""
    raise NotImplementedError


def api_trends(request):
    """GET /api/trends/?start=<iso>&end=<iso>&granularity=<day|week|month>"""
    raise NotImplementedError


def api_coverage(request, skill_name):
    """GET /api/coverage/<skill_name>/?start=<iso>&end=<iso>&file_grace_days=<int>"""
    raise NotImplementedError


def api_skills(request):
    """GET /api/skills/"""
    raise NotImplementedError
