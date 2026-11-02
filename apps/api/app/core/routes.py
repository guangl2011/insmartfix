"""Route-table introspection that sees through FastAPI's lazily included routers.

`app.routes` holds `_IncludedRouter` placeholders; `iter_route_contexts` expands them into the
effective routes with their full prefix and dependency tree (used by T-AUTH-14 and T-AUTH-18).
"""

from collections.abc import Iterator

from fastapi import FastAPI
from fastapi.routing import RouteContext, iter_route_contexts


def iter_http_routes(app: FastAPI) -> Iterator[RouteContext]:
    for rc in iter_route_contexts(app.routes):
        if rc.methods:
            yield rc
