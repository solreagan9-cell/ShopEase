from django.conf import settings
from django.conf.urls.static import static
from django.urls import path, include

app_name = "pharmacy"

urlpatterns = [
    path("api/v1/", include("pharmacy.api_urls")),
]

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)