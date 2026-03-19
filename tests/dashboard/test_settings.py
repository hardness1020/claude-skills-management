"""Unit tests for Django SECRET_KEY generation (#ft-4).

Tests that _get_secret_key() generates a key on first run,
persists it, and reuses it on subsequent calls.
"""

import os
import pytest
import tempfile

from dashboard.analytics_project import settings


class TestGetSecretKey:
    @pytest.mark.unit
    def test_get_secret_key_exists(self):
        """_get_secret_key function must exist in settings module."""
        assert hasattr(settings, "_get_secret_key"), "settings must define _get_secret_key()"
        assert callable(settings._get_secret_key)

    @pytest.mark.unit
    def test_get_secret_key_returns_string(self):
        """_get_secret_key must return a non-empty string."""
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["CLAUDE_PLUGIN_DATA"] = tmpdir
            try:
                key = settings._get_secret_key()
                assert isinstance(key, str)
                assert len(key) > 0
            finally:
                os.environ.pop("CLAUDE_PLUGIN_DATA", None)

    @pytest.mark.unit
    def test_get_secret_key_persists_to_file(self):
        """_get_secret_key must write the key to django_secret.txt."""
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["CLAUDE_PLUGIN_DATA"] = tmpdir
            try:
                key = settings._get_secret_key()
                secret_path = os.path.join(tmpdir, "django_secret.txt")
                assert os.path.isfile(secret_path), "django_secret.txt must be created"
                with open(secret_path) as f:
                    stored = f.read().strip()
                assert stored == key
            finally:
                os.environ.pop("CLAUDE_PLUGIN_DATA", None)

    @pytest.mark.unit
    def test_get_secret_key_reuses_existing(self):
        """_get_secret_key must return the same key on subsequent calls."""
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["CLAUDE_PLUGIN_DATA"] = tmpdir
            try:
                key1 = settings._get_secret_key()
                key2 = settings._get_secret_key()
                assert key1 == key2, "Must return the same key on subsequent calls"
            finally:
                os.environ.pop("CLAUDE_PLUGIN_DATA", None)

    @pytest.mark.unit
    def test_get_secret_key_uses_plugin_data_env(self):
        """_get_secret_key must use CLAUDE_PLUGIN_DATA when set."""
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["CLAUDE_PLUGIN_DATA"] = tmpdir
            try:
                settings._get_secret_key()
                secret_path = os.path.join(tmpdir, "django_secret.txt")
                assert os.path.isfile(secret_path)
            finally:
                os.environ.pop("CLAUDE_PLUGIN_DATA", None)

    @pytest.mark.unit
    def test_secret_key_is_not_hardcoded_dev_key(self):
        """SECRET_KEY must not be the hardcoded dev key."""
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["CLAUDE_PLUGIN_DATA"] = tmpdir
            try:
                key = settings._get_secret_key()
                assert key != "dev-secret-key-change-in-production", \
                    "SECRET_KEY must be generated, not the hardcoded dev value"
            finally:
                os.environ.pop("CLAUDE_PLUGIN_DATA", None)
