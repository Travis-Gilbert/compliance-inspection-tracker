from django.contrib import admin
from django.urls import path, re_path
from django.conf import settings
from django.views.static import serve

from tracker.api import api

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", api.urls),
    # Serve cached images directly (single-user internal tool, no CDN needed)
    re_path(r"^images/(?P<path>.*)$", serve, {"document_root": settings.MEDIA_ROOT}),
]
