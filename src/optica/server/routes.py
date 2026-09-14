"""The browser server's HTTP routes.

Implements plan § "Labeling & Curation": the routes both pages share — the page
itself, the idle-timer heartbeat and "Keep Session Active", and image serving —
with each page's own routes alongside. Route handlers are the one place Optica is
asynchronous (plan § "Coding Style" → *Async/await*); what they call is not.

**This is the only module that imports FastAPI**, and nothing imports it except
:func:`optica.server.app.load_web`, which turns a missing ``optica[web]`` into
``OpticaWebError``.

Every request is checked twice before a handler sees it. The ``Host`` header must
name this server, and every ``/api/`` request must carry the session cookie,
which the page receives only by opening the tokened link the terminal prints.
Binding to 127.0.0.1 keeps the network out; these keep out *other pages in the
user's own browser*, which can reach 127.0.0.1 too, and which could otherwise
drive a session whose Finish writes ``dataset/``.
"""

from __future__ import annotations

import secrets
from collections.abc import Awaitable, Callable
from typing import Any, Final

from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from optica.server.app import STATIC_DIR, BrowserSession

__all__ = ["create_app"]

_NO_STORE: Final = {"Cache-Control": "no-store"}

_NOT_AUTHORIZED_PAGE: Final = """<!doctype html>
<meta charset="utf-8"><title>Optica</title>
<body style="font-family: system-ui, sans-serif; margin: 3rem">
<h1>Open the link from your terminal</h1>
<p>This page belongs to a running Optica session. Open the address Optica printed
in the terminal, which includes the session's key.</p>
</body>"""


def create_app(session: BrowserSession) -> FastAPI:
    """Build the application for one browser session.

    Args:
        session: The shared state for this run — its page controller, idle timer
            and secret.

    Returns:
        The FastAPI application uvicorn serves.
    """
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    def authorized(request: Request) -> bool:
        presented = request.cookies.get(session.cookie_name, "")
        return secrets.compare_digest(presented, session.token)

    @app.middleware("http")
    async def guard(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if request.headers.get("host", "") not in session.allowed_hosts:
            return JSONResponse({"error": "Unrecognized host."}, status_code=403)
        is_api = request.url.path.startswith("/api/")
        if is_api and not authorized(request):
            return JSONResponse(
                {
                    "error": "This session's key is missing. "
                    "Open the link from the terminal."
                },
                status_code=403,
            )
        try:
            response = await call_next(request)
        except Exception as exc:  # noqa: BLE001 - reported by the terminal, not here
            # A failed write must end the session visibly rather than let the page
            # carry on over a decision that was never saved.
            session.fail(exc)
            return JSONResponse(
                {"error": "Optica hit an error; see the terminal.", "ended": True},
                status_code=500,
            )
        if is_api:
            response.headers.update(_NO_STORE)
        return response

    @app.get("/", response_model=None)
    async def page(request: Request, token: str | None = None) -> Response:
        if token is not None:
            if not secrets.compare_digest(token, session.token):
                return HTMLResponse(_NOT_AUTHORIZED_PAGE, status_code=403)
            # Trade the key in the address bar for a cookie, so it does not sit in
            # the visible URL for the rest of the session.
            redirect = RedirectResponse("/", status_code=303)
            redirect.set_cookie(
                session.cookie_name,
                session.token,
                httponly=True,
                samesite="strict",
                path="/",
            )
            return redirect
        if not authorized(request):
            return HTMLResponse(_NOT_AUTHORIZED_PAGE, status_code=403)
        return FileResponse(
            STATIC_DIR / f"{session.controller.page}.html", headers=_NO_STORE
        )

    @app.get("/api/heartbeat")
    async def heartbeat() -> dict[str, Any]:
        # Polled by the page; deliberately not activity, or an open tab would
        # keep a session alive forever.
        status = session.timer.status()
        return {
            "timeout_enabled": status.enabled,
            "remaining_seconds": status.remaining_seconds,
            "warning_seconds_left": status.warning_seconds_left,
            "ended": session.done or status.expired,
        }

    @app.post("/api/keepalive")
    async def keepalive() -> dict[str, Any]:
        session.activity()
        return {"ok": True}

    @app.get("/api/image/{image_id:path}", response_model=None)
    async def image(image_id: str) -> Response:
        path = session.controller.image_path(image_id)
        if path is None or not path.is_file():
            return JSONResponse({"error": "No such image."}, status_code=404)
        return FileResponse(path)

    return app
