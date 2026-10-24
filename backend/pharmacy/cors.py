from django.conf import settings
from django.http import HttpResponse


class SimpleCorsMiddleware:
    """Lets the separate frontend (another port) call this API from the browser.

    Allowed origins come from FRONTEND_ORIGINS in settings.py.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        origin = request.headers.get("Origin", "")
        allowed = origin in getattr(settings, "FRONTEND_ORIGINS", [])

        is_preflight = (
            request.method == "OPTIONS"
            and "Access-Control-Request-Method" in request.headers
        )

        if allowed and is_preflight:
            response = HttpResponse(status=204)
        else:
            response = self.get_response(request)

        if allowed:
            response["Access-Control-Allow-Origin"] = origin
            response["Access-Control-Allow-Headers"] = "Authorization, Content-Type"
            response["Access-Control-Allow-Methods"] = "GET, POST, DELETE, OPTIONS"
            response["Access-Control-Max-Age"] = "600"
            response["Vary"] = "Origin"

        return response