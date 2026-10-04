from django.conf import settings


class InternalHostMiddleware:
    INTERNAL_HOSTS = {"localhost", "127.0.0.1", "web"}
    INTERNAL_PATH_PREFIXES = ("/healthz/", "/internal/")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        host = request.META.get("HTTP_HOST", "").rsplit(":", 1)[0]
        if host in self.INTERNAL_HOSTS and request.path.startswith(
            self.INTERNAL_PATH_PREFIXES
        ):
            request.META["HTTP_HOST"] = settings.INTERNAL_CANONICAL_HOST
        return self.get_response(request)
