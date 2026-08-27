from __future__ import annotations

import gzip

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from api.config import settings
from api.database import initialize_database
from api.routers import auth, cost_accounting, documents, engineering, goods, payments, references, registers, settlements, sync, system, works


class GZipRequestMiddleware:
    """Decompress ``Content-Encoding: gzip`` request bodies before routing.

    Pairs with ``GZipMiddleware`` (which handles response compression) so that
    sync workers can exchange large batches with compression in both directions.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(
            (k.decode("latin-1").lower(), v.decode("latin-1"))
            for k, v in scope.get("headers", [])
        )
        if headers.get("content-encoding", "").lower() != "gzip":
            await self.app(scope, receive, send)
            return

        # Strip the encoding header so downstream parsers see plain JSON.
        new_headers = [
            (k, v)
            for k, v in scope.get("headers", [])
            if k.lower() != b"content-encoding"
        ]
        scope = {**scope, "headers": new_headers}

        decompressed_buffer = bytearray()
        more_body = True

        async def gzip_receive() -> Message:
            nonlocal more_body
            if not more_body:
                return {"type": "http.request", "body": b"", "more_body": False}
            more_body = False
            while True:
                message = await receive()
                if message["type"] != "http.request":
                    return message
                decompressed_buffer.extend(message.get("body", b""))
                if not message.get("more_body", False):
                    break
            body = gzip.decompress(bytes(decompressed_buffer))
            return {"type": "http.request", "body": body, "more_body": False}

        await self.app(scope, gzip_receive, send)


app = FastAPI(
    title="CTM API",
    version="0.1.0",
    description="REST API for the Construction Time Management web client",
)

app.add_middleware(GZipMiddleware, minimum_size=512)
app.add_middleware(GZipRequestMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(references.router)
app.include_router(works.router)
app.include_router(documents.router)
app.include_router(payments.router)
app.include_router(goods.router)
app.include_router(settlements.router)
app.include_router(registers.router)
app.include_router(cost_accounting.router)
app.include_router(sync.router)
app.include_router(system.router)
app.include_router(engineering.router)


@app.on_event("startup")
def on_startup() -> None:
    initialize_database()
    # Start the relay-v2 sync bridge if RELAY_SYNC_ENABLED=true. Runs in a
    # background daemon thread inside this process; no-op if disabled.
    try:
        from api.sync_relay_bridge import ServerRelayBridge

        bridge = ServerRelayBridge.from_env()
        if bridge is not None:
            bridge.start()
            app.state.relay_bridge = bridge
    except Exception:  # noqa: BLE001
        # Bridge is optional — never let its init failure crash the API.
        import logging

        logging.getLogger(__name__).exception("relay bridge startup failed")


@app.on_event("shutdown")
def on_shutdown() -> None:
    bridge = getattr(app.state, "relay_bridge", None)
    if bridge is not None:
        bridge.stop()
        app.state.relay_bridge = None


if settings.web_dist_path.exists() and (settings.web_dist_path / "assets").exists():
    app.mount("/assets", StaticFiles(directory=settings.web_dist_path / "assets"), name="assets")


@app.get("/", include_in_schema=False, response_model=None)
def root() -> HTMLResponse | FileResponse:
    index_file = settings.web_dist_path / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return HTMLResponse(
        """
        <html>
          <head><title>CTM API</title></head>
          <body>
            <h1>CTM API is running</h1>
            <p>Open <a href="/docs">/docs</a> for API docs or build the Vue client under <code>web-client/</code>.</p>
          </body>
        </html>
        """
    )


@app.get("/{full_path:path}", include_in_schema=False, response_model=None)
def spa_fallback(full_path: str) -> FileResponse | HTMLResponse:
    index_file = settings.web_dist_path / "index.html"
    candidate = settings.web_dist_path / full_path
    if candidate.is_file():
        return FileResponse(candidate)
    if index_file.exists():
        return FileResponse(index_file)
    return HTMLResponse("<h1>CTM Web Client build not found</h1>", status_code=404)
