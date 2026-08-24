import os
import subprocess
import sys

import pytest


@pytest.mark.parametrize(
    "secret_key,publishable_key,should_raise",
    [
        ("sk_live_abc123", "pk_test_abc123", True),
        ("sk_test_abc123", "pk_live_abc123", True),
        ("sk_live_abc123", "pk_live_abc123", True),
        ("sk_test_abc123", "pk_test_abc123", False),
    ],
)
def test_stripe_key_boundary_enforced_at_settings_load(
    secret_key, publishable_key, should_raise
):
    env = {
        **os.environ,
        "DJANGO_SETTINGS_MODULE": "config.settings.dev",
        "STRIPE_SECRET_KEY": secret_key,
        "STRIPE_PUBLISHABLE_KEY": publishable_key,
    }
    result = subprocess.run(
        [sys.executable, "-c", "import django; django.setup()"],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if should_raise:
        assert result.returncode != 0, (
            "Expected boot to fail on a live key, but it succeeded.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "ImproperlyConfigured" in result.stderr
        assert "test-mode" in result.stderr
    else:
        assert result.returncode == 0, (
            "Expected a correctly-configured test-mode pair to boot cleanly.\n"
            f"stderr: {result.stderr}"
        )
