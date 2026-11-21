import textwrap

import pytest

from tests.helpers import PROD_ENV, run_with_settings

# ==================================================
# Production refuses to start with unsafe or missing config
# ==================================================

R2_CREDENTIALS = [
    "R2_ACCOUNT_ID",
    "R2_ACCESS_KEY_ID",
    "R2_SECRET_ACCESS_KEY",
    "R2_BUCKET_NAME",
]


@pytest.mark.parametrize("missing_var", [*R2_CREDENTIALS, "R2_PUBLIC_DOMAIN"])
def test_prod_boot_fails_loud_naming_the_missing_r2_credential(missing_var):
    result = run_with_settings("config.settings.prod", {**PROD_ENV, missing_var: ""})
    assert result.returncode != 0, (
        "Expected boot to fail with an R2 credential missing, "
        f"but it succeeded.\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert "ImproperlyConfigured" in result.stderr
    assert missing_var in result.stderr


def test_prod_boot_fails_loud_when_all_four_credentials_missing():
    result = run_with_settings(
        "config.settings.prod", {**PROD_ENV, **dict.fromkeys(R2_CREDENTIALS, "")}
    )
    assert result.returncode != 0
    assert "ImproperlyConfigured" in result.stderr
    for name in R2_CREDENTIALS:
        assert name in result.stderr


def test_prod_boots_cleanly_with_all_four_credentials_present():
    result = run_with_settings("config.settings.prod", PROD_ENV)
    assert result.returncode == 0, (
        "Expected a correctly-configured prod boot to succeed.\n"
        f"stderr: {result.stderr}"
    )


@pytest.mark.parametrize(
    "settings_module", ["config.settings.dev", "config.settings.test"]
)
def test_dev_and_test_boot_cleanly_with_zero_r2_env_vars(settings_module):
    no_r2 = dict.fromkeys([*R2_CREDENTIALS, "R2_PUBLIC_DOMAIN"], "")
    result = run_with_settings(settings_module, no_r2)
    assert result.returncode == 0, (
        f"Expected {settings_module} to boot with no R2 vars set.\n"
        f"stderr: {result.stderr}"
    )


@pytest.mark.parametrize(
    "bad_domain", ["https://media.example.com", "media.example.com/images"]
)
def test_prod_rejects_r2_public_domain_that_is_not_a_bare_hostname(bad_domain):
    result = run_with_settings(
        "config.settings.prod", {**PROD_ENV, "R2_PUBLIC_DOMAIN": bad_domain}
    )
    assert result.returncode != 0
    assert "R2_PUBLIC_DOMAIN" in result.stderr


@pytest.mark.parametrize(
    "override, message",
    [
        ({"CORS_ALLOWED_ORIGINS": ""}, "CORS_ALLOWED_ORIGINS"),
        ({"ALLOWED_HOSTS": ".example.com"}, "exact hostname"),
        ({"EMAIL_HOST": ""}, "EMAIL_HOST"),
        ({"TURNSTILE_SECRET_KEY": ""}, "TURNSTILE_SECRET_KEY"),
        (
            {"TURNSTILE_SECRET_KEY": "1x0000000000000000000000000000000AA"},
            "TURNSTILE_SECRET_KEY",
        ),
        (
            {"REDIS_URL": "redis://localhost:6379/0"},
            "REDIS_URL must include a password",
        ),
        ({"SECRET_KEY": "change-me"}, "SECRET_KEY must be a long random value"),
        ({"SECRET_KEY": "django-insecure-" + "a1b2c3" * 9}, "SECRET_KEY must be"),
        ({"SECRET_KEY": "x" * 60}, "SECRET_KEY must be"),
        ({"JWT_SIGNING_KEY": "change-me-too"}, "JWT_SIGNING_KEY must be"),
        ({"FRONTEND_URL": "not-a-url"}, "FRONTEND_URL must be a full https"),
        ({"FRONTEND_URL": "//evil.example"}, "FRONTEND_URL must be a full https"),
        ({"FRONTEND_URL": "http://example.com"}, "FRONTEND_URL must be a full https"),
    ],
)
def test_prod_refuses_to_boot_with_unsafe_settings(override, message):
    result = run_with_settings("config.settings.prod", {**PROD_ENV, **override})
    assert result.returncode != 0
    assert message in result.stderr


# ==================================================
# Every settings module refuses live Stripe keys
# ==================================================


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
    result = run_with_settings(
        "config.settings.dev",
        {"STRIPE_SECRET_KEY": secret_key, "STRIPE_PUBLISHABLE_KEY": publishable_key},
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


# ==================================================
# Production routing: health check, HTTPS redirect, private Hosts, JSON only
# ==================================================

SCRIPT = textwrap.dedent("""
    import django
    django.setup()
    from django.test import Client
    c = Client()
    r1 = c.get("/healthz/", HTTP_HOST="localhost")
    r3 = c.get("/events/", HTTP_HOST="example.com")
    # Private Hosts must NOT work on public paths.
    r4 = c.get("/events/", HTTP_HOST="localhost")
    r5 = c.get("/events/", HTTP_HOST="web:8000")
    # A browser asking for HTML still gets JSON: production has no browsable API
    r6 = c.get("/categories/", HTTP_HOST="example.com", secure=True,
               HTTP_ACCEPT="text/html")
    print(r1.status_code, r3.status_code, r4.status_code, r5.status_code,
          r6["Content-Type"].split(";")[0])
    """)


def test_healthz_is_not_redirected_public_paths_are_and_only_json_is_served():
    result = run_with_settings("config.settings.prod", PROD_ENV, code=SCRIPT)
    assert result.returncode == 0, result.stderr
    healthz, public, localhost_public, web_public, html_ask = result.stdout.split()[-5:]
    assert healthz == "200"
    assert public == "301"
    assert localhost_public == "400"
    assert web_public == "400"
    assert html_ask == "application/json"


def test_production_settings_pass_djangos_deployment_checks():
    code = (
        "import django; django.setup(); "
        "from django.core.management import call_command; "
        "call_command('check', deploy=True, fail_level='WARNING')"
    )
    result = run_with_settings("config.settings.prod", PROD_ENV, code=code)
    assert result.returncode == 0, result.stderr


def test_production_sends_mail_over_smtp_with_the_email_env_variables():
    code = (
        "import django; django.setup(); "
        "from django.core.mail import mailers; m = mailers.default; "
        "print(type(m).__module__, m.host, m.port, m.username, m.use_tls)"
    )
    env = {**PROD_ENV, "EMAIL_PORT": "2525", "EMAIL_HOST_USER": "mailer"}
    result = run_with_settings("config.settings.prod", env, code=code)
    assert result.returncode == 0, result.stderr
    assert result.stdout.split() == [
        "django.core.mail.backends.smtp",
        "smtp.example.com",
        "2525",
        "mailer",
        "True",
    ]
