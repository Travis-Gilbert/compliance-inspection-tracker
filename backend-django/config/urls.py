from django.contrib import admin
from django.urls import path, re_path
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from django.views.static import serve
from strawberry.django.views import GraphQLView

from tracker.api import api
from tracker.graphql_schema import schema

# The GraphQL endpoint is a cross-origin API consumed by the separate Next.js
# fork (urql POSTs plain JSON from the Vercel origin), not a cookie-authenticated
# Django form. Django's CsrfViewMiddleware otherwise 403s those POSTs. CORS is
# the access control here (CORS_ALLOWED_ORIGINS); the private auth gate is added
# separately (GCLBA-FE-008). So the GraphQL view is csrf_exempt.
_graphql_view = csrf_exempt(GraphQLView.as_view(schema=schema, multipart_uploads_enabled=True))

urlpatterns = [
    path("admin/", admin.site.urls),
    path("graphql", _graphql_view),
    path("graphql/", _graphql_view),
    path("", api.urls),
    # Serve cached images directly (single-user internal tool, no CDN needed)
    re_path(r"^images/(?P<path>.*)$", serve, {"document_root": settings.MEDIA_ROOT}),
]
