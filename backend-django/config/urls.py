from django.contrib import admin
from django.urls import path, re_path
from django.conf import settings
from django.views.static import serve
from strawberry.django.views import GraphQLView

from tracker.api import api
from tracker.graphql_schema import schema

urlpatterns = [
    path("admin/", admin.site.urls),
    path("graphql", GraphQLView.as_view(schema=schema, multipart_uploads_enabled=True)),
    path("graphql/", GraphQLView.as_view(schema=schema, multipart_uploads_enabled=True)),
    path("", api.urls),
    # Serve cached images directly (single-user internal tool, no CDN needed)
    re_path(r"^images/(?P<path>.*)$", serve, {"document_root": settings.MEDIA_ROOT}),
]
