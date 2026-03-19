"""URL configuration for skills analytics dashboard."""

from django.urls import path
from dashboard.analytics import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("api/frequency/", views.api_frequency, name="api_frequency"),
    path("api/adoption/", views.api_adoption, name="api_adoption"),
    path("api/usefulness/", views.api_usefulness, name="api_usefulness"),
    path("api/trends/", views.api_trends, name="api_trends"),
    path("api/coverage/<str:skill_name>/", views.api_coverage, name="api_coverage"),
    path("api/skills/", views.api_skills, name="api_skills"),
]
