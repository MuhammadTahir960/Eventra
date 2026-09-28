import os
import subprocess
import sys
import textwrap

SCRIPT = textwrap.dedent("""
    import django
    django.setup()
    from django.test import Client
    c = Client()
    r1 = c.get("/healthz/", HTTP_HOST="localhost")
    r2 = c.post("/internal/seats/broadcast/", data="{}",
                content_type="application/json", HTTP_HOST="web:8000")
    r3 = c.get("/events/", HTTP_HOST="example.com")
    print(r1.status_code, r2.status_code, r3.status_code)
    """)


def test_internal_endpoints_are_not_redirected_but_public_ones_are():
    env = {
        **os.environ,
        "DJANGO_SETTINGS_MODULE": "config.settings.prod",
        "ALLOWED_HOSTS": "example.com",
        "CSRF_TRUSTED_ORIGINS": "https://example.com",
        "EMAIL_HOST": "smtp.example.com",
        "R2_ACCOUNT_ID": "a",
        "R2_ACCESS_KEY_ID": "b",
        "R2_SECRET_ACCESS_KEY": "c",
        "R2_BUCKET_NAME": "d",
    }
    result = subprocess.run(
        [sys.executable, "-c", SCRIPT],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    healthz, internal, public = result.stdout.split()[-3:]
    assert healthz == "200"
    assert internal != "301"
    assert public == "301"


def test_prod_refuses_to_boot_without_an_email_host():
    env = {
        **os.environ,
        "DJANGO_SETTINGS_MODULE": "config.settings.prod",
        "ALLOWED_HOSTS": "example.com",
        "CSRF_TRUSTED_ORIGINS": "https://example.com",
        "EMAIL_HOST": "",
        "R2_ACCOUNT_ID": "a",
        "R2_ACCESS_KEY_ID": "b",
        "R2_SECRET_ACCESS_KEY": "c",
        "R2_BUCKET_NAME": "d",
    }
    result = subprocess.run(
        [sys.executable, "-c", "import django; django.setup()"],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode != 0
    assert "EMAIL_HOST" in result.stderr
