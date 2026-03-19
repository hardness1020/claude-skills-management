"""Django settings for skills analytics dashboard."""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = "dev-secret-key-change-in-production"

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
