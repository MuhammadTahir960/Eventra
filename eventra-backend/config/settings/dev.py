from .base import *

DEBUG = True

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

if not CORS_ALLOWED_ORIGINS:
    CORS_ALLOWED_ORIGINS = ["http://localhost:5173"]

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
