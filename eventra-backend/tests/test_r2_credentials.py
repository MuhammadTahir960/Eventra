import os
import subprocess
import sys

import pytest

_PROD_ENV = {
    "ALLOWED_HOSTS": "example.com",
    "CSRF_TRUSTED_ORIGINS": "https://example.com",
    "CORS_ALLOWED_ORIGINS": "https://example.com",
    "EMAIL_HOST": "smtp.example.com",
    "R2_ACCOUNT_ID": "a",
    "R2_ACCESS_KEY_ID": "b",
    "R2_SECRET_ACCESS_KEY": "c",
    "R2_BUCKET_NAME": "d",
    "R2_PUBLIC_DOMAIN": "media.example.com",
}


def _run_settings_boot(settings_module, extra_env):
    env = {
        **os.environ,
        "DJANGO_SETTINGS_MODULE": settings_module,
        **extra_env,
    }
    return subprocess.run(
        [sys.executable, "-c", "import django; django.setup()"],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )


@pytest.mark.parametrize(
    "missing_var",
    [
        "R2_ACCOUNT_ID",
        "R2_ACCESS_KEY_ID",
        "R2_SECRET_ACCESS_KEY",
        "R2_BUCKET_NAME",
        "R2_PUBLIC_DOMAIN",
    ],
)
def test_prod_boot_fails_loud_naming_the_missing_r2_credential(missing_var):
    creds = {
        "R2_ACCOUNT_ID": "demo-account-id",
        "R2_ACCESS_KEY_ID": "demo-access-key",
        "R2_SECRET_ACCESS_KEY": "demo-secret-key",
        "R2_BUCKET_NAME": "demo-bucket",
        "R2_PUBLIC_DOMAIN": "media.example.com",
    }
    creds[missing_var] = ""
    result = _run_settings_boot(
        "config.settings.prod",
        {
            "ALLOWED_HOSTS": "example.com",
            "CSRF_TRUSTED_ORIGINS": "https://example.com",
            "CORS_ALLOWED_ORIGINS": "https://example.com",
            "EMAIL_HOST": "smtp.example.com",
            **creds,
        },
    )
    assert result.returncode != 0, (
        "Expected boot to fail with an R2 credential missing, "
        f"but it succeeded.\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert "ImproperlyConfigured" in result.stderr
    assert missing_var in result.stderr


def test_prod_boot_fails_loud_when_all_four_credentials_missing():
    result = _run_settings_boot(
        "config.settings.prod",
        {
            "ALLOWED_HOSTS": "example.com",
            "CSRF_TRUSTED_ORIGINS": "https://example.com",
            "CORS_ALLOWED_ORIGINS": "https://example.com",
            "EMAIL_HOST": "smtp.example.com",
            "R2_ACCOUNT_ID": "",
            "R2_ACCESS_KEY_ID": "",
            "R2_SECRET_ACCESS_KEY": "",
            "R2_BUCKET_NAME": "",
        },
    )
    assert result.returncode != 0
    assert "ImproperlyConfigured" in result.stderr
    for name in (
        "R2_ACCOUNT_ID",
        "R2_ACCESS_KEY_ID",
        "R2_SECRET_ACCESS_KEY",
        "R2_BUCKET_NAME",
    ):
        assert name in result.stderr


def test_prod_boots_cleanly_with_all_four_credentials_present():
    result = _run_settings_boot(
        "config.settings.prod",
        {
            "ALLOWED_HOSTS": "example.com",
            "CSRF_TRUSTED_ORIGINS": "https://example.com",
            "CORS_ALLOWED_ORIGINS": "https://example.com",
            "EMAIL_HOST": "smtp.example.com",
            "R2_ACCOUNT_ID": "demo-account-id",
            "R2_ACCESS_KEY_ID": "demo-access-key",
            "R2_SECRET_ACCESS_KEY": "demo-secret-key",
            "R2_BUCKET_NAME": "demo-bucket",
            "R2_PUBLIC_DOMAIN": "media.example.com",
        },
    )
    assert result.returncode == 0, (
        "Expected a correctly-configured prod boot to succeed.\n"
        f"stderr: {result.stderr}"
    )


@pytest.mark.parametrize(
    "settings_module", ["config.settings.dev", "config.settings.test"]
)
def test_dev_and_test_boot_cleanly_with_zero_r2_env_vars(settings_module):
    env = {k: v for k, v in os.environ.items() if not k.startswith("R2_")}
    env["DJANGO_SETTINGS_MODULE"] = settings_module
    result = subprocess.run(
        [sys.executable, "-c", "import django; django.setup()"],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, (
        f"Expected {settings_module} to boot with no R2 vars set.\n"
        f"stderr: {result.stderr}"
    )


@pytest.mark.parametrize(
    "bad_domain", ["https://media.example.com", "media.example.com/images"]
)
def test_prod_rejects_r2_public_domain_that_is_not_a_bare_hostname(bad_domain):
    result = _run_settings_boot(
        "config.settings.prod", {**_PROD_ENV, "R2_PUBLIC_DOMAIN": bad_domain}
    )
    assert result.returncode != 0
    assert "R2_PUBLIC_DOMAIN" in result.stderr


def test_prod_refuses_to_boot_without_cors_allowed_origins():
    result = _run_settings_boot(
        "config.settings.prod", {**_PROD_ENV, "CORS_ALLOWED_ORIGINS": ""}
    )
    assert result.returncode != 0
    assert "CORS_ALLOWED_ORIGINS" in result.stderr


def test_prod_refuses_to_boot_with_only_wildcard_allowed_hosts():
    result = _run_settings_boot(
        "config.settings.prod", {**_PROD_ENV, "ALLOWED_HOSTS": ".example.com"}
    )
    assert result.returncode != 0
    assert "exact hostname" in result.stderr
