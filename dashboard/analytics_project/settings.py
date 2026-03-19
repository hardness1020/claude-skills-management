"""Django settings for skills analytics dashboard."""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

def _get_secret_key():
    """Generate and persist a Django SECRET_KEY on first run."""
    plugin_data = os.environ.get(
        "CLAUDE_PLUGIN_DATA",
        os.path.expanduser("~/.skills-analytics"),
    )
    secret_path = Path(plugin_data) / "django_secret.txt"
    if secret_path.exists():
        return secret_path.read_text().strip()
    from django.core.management.utils import get_random_secret_key
    key = get_random_secret_key()
    Path(plugin_data).mkdir(parents=True, exist_ok=True)
    secret_path.write_text(key)
    return key


SECRET_KEY = _get_secret_key()

DEBUG = True

ALLOWED_HOSTS = ["127.0.0.1", "localhost"]

INSTALLED_APPS = [
    "dashboard.analytics",
]

MIDDLEWARE = [
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "dashboard.analytics_project.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [],
        },
    },
]

# No Django ORM — we use raw SQLite via scripts/db.py
DATABASES = {}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Database path for skills analytics
SKILLS_ANALYTICS_DB = os.environ.get(
    "SKILLS_ANALYTICS_DB",
    os.path.join(
        os.environ.get("CLAUDE_PLUGIN_DATA", os.path.expanduser("~/.skills-analytics")),
        "skills_analytics.db",
    ),
)
