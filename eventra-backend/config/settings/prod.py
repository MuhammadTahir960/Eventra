from django.core.exceptions import ImproperlyConfigured

from .base import *

DEBUG = False

if not ALLOWED_HOSTS:
    raise ImproperlyConfigured("ALLOWED_HOSTS must be set explicitly in production.")

_CANONICAL_HOST = next((h for h in ALLOWED_HOSTS if not h.startswith((".", "*"))), None)
if _CANONICAL_HOST is None:
    raise ImproperlyConfigured(
        "ALLOWED_HOSTS must contain at least one exact hostname in production."
    )
MIDDLEWARE = ["apps.common.middleware.InternalHostMiddleware", *MIDDLEWARE]
INTERNAL_CANONICAL_HOST = _CANONICAL_HOST
SECURE_REDIRECT_EXEMPT = [r"^healthz/$", r"^internal/"]

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True

SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])
if not CSRF_TRUSTED_ORIGINS:
    raise ImproperlyConfigured(
        "CSRF_TRUSTED_ORIGINS must be set explicitly in production."
    )

if not CORS_ALLOWED_ORIGINS:
    raise ImproperlyConfigured(
        "CORS_ALLOWED_ORIGINS must be set explicitly in production "
        "(it also gates WebSocket origins)."
    )

if not EMAIL_HOST:
    raise ImproperlyConfigured("EMAIL_HOST must be set in production.")
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"

INSTALLED_APPS = [*INSTALLED_APPS, "storages"]

R2_ACCOUNT_ID = env("R2_ACCOUNT_ID", default="")
R2_ACCESS_KEY_ID = env("R2_ACCESS_KEY_ID", default="")
R2_SECRET_ACCESS_KEY = env("R2_SECRET_ACCESS_KEY", default="")
R2_BUCKET_NAME = env("R2_BUCKET_NAME", default="")
R2_PUBLIC_DOMAIN = env("R2_PUBLIC_DOMAIN", default="")

_missing_r2_vars = [
    name
    for name, value in {
        "R2_ACCOUNT_ID": R2_ACCOUNT_ID,
        "R2_ACCESS_KEY_ID": R2_ACCESS_KEY_ID,
        "R2_SECRET_ACCESS_KEY": R2_SECRET_ACCESS_KEY,
        "R2_BUCKET_NAME": R2_BUCKET_NAME,
        "R2_PUBLIC_DOMAIN": R2_PUBLIC_DOMAIN,
    }.items()
    if not value
]
if _missing_r2_vars:
    raise ImproperlyConfigured(
        "Missing required Cloudflare R2 credential(s) in production: "
        f"{', '.join(_missing_r2_vars)}."
    )

if "://" in R2_PUBLIC_DOMAIN or "/" in R2_PUBLIC_DOMAIN:
    raise ImproperlyConfigured(
        "R2_PUBLIC_DOMAIN must be a bare hostname such as media.example.com, "
        "without a scheme or path."
    )

AWS_ACCESS_KEY_ID = R2_ACCESS_KEY_ID
AWS_SECRET_ACCESS_KEY = R2_SECRET_ACCESS_KEY
AWS_STORAGE_BUCKET_NAME = R2_BUCKET_NAME
AWS_S3_ENDPOINT_URL = f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com"
AWS_S3_CUSTOM_DOMAIN = R2_PUBLIC_DOMAIN
AWS_S3_REGION_NAME = "auto"
AWS_DEFAULT_ACL = None
AWS_QUERYSTRING_AUTH = False
AWS_S3_FILE_OVERWRITE = False
AWS_S3_ADDRESSING_STYLE = "path"

STORAGES = {
    "default": {"BACKEND": "storages.backends.s3boto3.S3Boto3Storage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
