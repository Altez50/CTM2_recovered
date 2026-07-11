"""Background sync worker.

Periodically exchanges changes between this local base and a remote peer over
HTTP. Reads the local append-only journal (`sync_changes`), serializes entities
through the same runtime used by the API, POSTs them to the remote
`/api/sync/exchange` endpoint, and applies the remote's outgoing changes back
to the local database via `api.sync_runtime.apply_sync_change`.

Designed to run as a standalone process alongside the FastAPI server:

    python -m api.sync_worker

Configuration is read from environment variables (consistent with `api/config.py`):

    SYNC_SERVER_URL            Remote peer base URL, e.g. http://office-server:8000
    SYNC_NODE_CODE             Our identity reported to the remote (default: derived
                               from the local DB filename, e.g. LOCAL-CONSTRUCTION)
    SYNC_NODE_NAME             Human-readable name reported to the remote
    SYNC_INTERVAL_SECONDS      Seconds between exchange cycles (default: 300)
    SYNC_BATCH_SIZE            Max changes per direction per cycle (default: 100)
    SYNC_WORKER_ONCE           If "1", run a single cycle and exit (for testing)
    SYNC_WORKER_LOG_LEVEL      Logging level (default: INFO)
    SYNC_TOKEN                 Shared secret forwarded as ``X-Sync-Token`` to the
                               remote peer. Required when the remote has SYNC_TOKEN
                               configured; ignored otherwise.

Cursors are persisted in the local `constants` table so the worker survives
restarts without re-sending or re-applying changes. Re-sending is nonetheless
safe because the exchange engine deduplicates by UUID + timestamp.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
import urllib.error
import urllib.request
from typing import Any

from api.config import settings
from api.database import (
    SYNC_SCHEMA_VERSION,
    _get_constant,
    _set_constant,
    ensure_local_sync_node,
    get_connection,
    initialize_database,
)
from api.sync_runtime import apply_sync_change, collect_outgoing_changes, prune_sync_changes

logger = logging.getLogger("sync_worker")

# Cursor keys persisted in the local constants table.
CURSOR_REMOTE_SENT = "sync.worker.remote_sent_change_id"  # highest change_id received FROM remote
CURSOR_LOCAL_SENT = "sync.worker.local_sent_change_id"   # highest local sync_changes.id pushed TO remote
CURSOR_REMOTE_NODE_ID = "sync.worker.remote_node_id"     # remote-assigned node id (cached)


def _env(name: str, default: str) -> str:
    value = os.getenv(name)
    return default if value is None or value.strip() == "" else value.strip()


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("Invalid integer for %s=%r, using default %d", name, raw, default)
        return default


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def http_post_json(
    url: str,
    payload: dict[str, Any],
    *,
    timeout: float = 30.0,
    sync_token: str = "",
) -> dict[str, Any]:
    """POST JSON to the remote peer and return the parsed JSON response.

    Raises WorkerHttpError on non-2xx responses or transport failures so the
    caller can log and retry on the next cycle instead of crashing.
    """
    import gzip as _gzip

    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json; charset=utf-8"}
    if sync_token:
        headers["X-Sync-Token"] = sync_token
    # Compress large payloads to save bandwidth on WAN links.
    if len(data) > 1024:
        data = _gzip.compress(data)
        headers["Content-Encoding"] = "gzip"
    request = urllib.request.Request(
        url,
        data=data,
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise WorkerHttpError(f"HTTP {exc.code} from {url}: {detail}", status=exc.code) from exc
    except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
        raise WorkerHttpError(f"Transport error contacting {url}: {exc}", status=None) from exc


class WorkerHttpError(RuntimeError):
    def __init__(self, message: str, status: int | None) -> None:
        super().__init__(message)
        self.status = status


def _read_cursor(connection: sqlite3.Connection, key: str) -> int:
    raw = _get_constant(connection, key)
    if raw is None or raw.strip() == "":
        return 0
    try:
        return int(raw)
    except ValueError:
        return 0


def _apply_incoming(connection: sqlite3.Connection, remote_node_id: str, changes: list[dict[str, Any]]) -> tuple[int, int, int]:
    """Apply remote changes locally. Returns (processed, skipped, errors)."""
    processed = 0
    skipped = 0
    errors = 0
    for change in changes:
        try:
            result = apply_sync_change(connection, source_node_id=remote_node_id, change=change)
        except Exception as exc:  # noqa: BLE001 — per-change isolation
            errors += 1
            logger.error(
                "Failed applying remote change %s:%s -> %s",
                change.get("entity_type"),
                change.get("entity_uuid"),
                exc,
            )
            continue
        if result["status"] == "applied":
            processed += 1
        else:
            skipped += 1
    return processed, skipped, errors


def run_once(
    connection: sqlite3.Connection,
    *,
    server_url: str,
    node_code: str,
    node_name: str,
    batch_size: int,
    sync_token: str = "",
) -> dict[str, int]:
    """Execute one exchange cycle against the remote peer.

    Returns a small summary dict for logging.
    """
    remote_cursor = _read_cursor(connection, CURSOR_REMOTE_SENT)
    local_cursor = _read_cursor(connection, CURSOR_LOCAL_SENT)

    # 1. Collect our outgoing changes since the last acked local id.
    outgoing, new_local_cursor = collect_outgoing_changes(
        connection,
        since_change_id=local_cursor,
        limit=batch_size,
    )

    # 2. Send them to the remote, asking back for changes after our remote cursor.
    cached_remote_node_id = _get_constant(connection, CURSOR_REMOTE_NODE_ID)
    request_payload: dict[str, Any] = {
        "schema_version": SYNC_SCHEMA_VERSION,
        "node_code": node_code,
        "node_name": node_name,
        "last_received_change_id": remote_cursor,
        "batch_size": batch_size,
        "changes": outgoing,
    }
    if cached_remote_node_id:
        request_payload["node_id"] = cached_remote_node_id

    response = http_post_json(
        f"{server_url.rstrip('/')}/api/sync/exchange",
        request_payload,
        sync_token=sync_token,
    )

    remote_node = response.get("remote_node") or {}
    remote_node_id = str(remote_node.get("id") or cached_remote_node_id or "unknown")

    # 3. Apply the remote's outgoing changes to the local DB.
    incoming = response.get("changes") or []
    processed, skipped, errors = _apply_incoming(connection, remote_node_id, incoming)
    connection.commit()

    # 4. Persist updated cursors.
    new_remote_cursor = int(response.get("last_sent_change_id") or remote_cursor)
    if new_remote_cursor > remote_cursor:
        _set_constant(connection, CURSOR_REMOTE_SENT, str(new_remote_cursor))
    if new_local_cursor > local_cursor:
        _set_constant(connection, CURSOR_LOCAL_SENT, str(new_local_cursor))
    if remote_node.get("id") and remote_node.get("id") != cached_remote_node_id:
        _set_constant(connection, CURSOR_REMOTE_NODE_ID, str(remote_node["id"]))
    connection.commit()

    # 5. Prune local journal entries that every known peer has received.
    prune_result = prune_sync_changes(connection)

    summary = {
        "sent": len(outgoing),
        "received": len(incoming),
        "processed": processed,
        "skipped": skipped,
        "errors": errors,
        "response_errors": len(response.get("errors") or []),
        "conflicts": len(response.get("conflicts") or []),
        "pruned": prune_result["pruned_count"],
    }
    return summary


def main() -> None:
    logging.basicConfig(
        level=getattr(logging, _env("SYNC_WORKER_LOG_LEVEL", "INFO").upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    server_url = _env("SYNC_SERVER_URL", "http://localhost:8000")
    node_code = _env("SYNC_NODE_CODE", "")
    node_name = _env("SYNC_NODE_NAME", "")
    interval = max(5, _env_int("SYNC_INTERVAL_SECONDS", 300))
    batch_size = max(1, _env_int("SYNC_BATCH_SIZE", 100))
    run_once_flag = _env_bool("SYNC_WORKER_ONCE", False)
    sync_token = os.getenv("SYNC_TOKEN", "").strip()

    logger.info(
        "sync_worker starting: server=%s interval=%ss batch=%d once=%s token=%s",
        server_url,
        interval,
        batch_size,
        run_once_flag,
        "set" if sync_token else "none",
    )

    initialize_database()
    connection = get_connection()

    # Default our reported identity to the local node code/name.
    if not node_code or not node_name:
        local_node = ensure_local_sync_node(connection)
        if not node_code:
            node_code = str(local_node["code"])
        if not node_name:
            node_name = str(local_node["name"])

    if run_once_flag:
        try:
            summary = run_once(
                connection,
                server_url=server_url,
                node_code=node_code,
                node_name=node_name,
                batch_size=batch_size,
                sync_token=sync_token,
            )
            logger.info("Single cycle complete: %s", summary)
        except WorkerHttpError as exc:
            logger.error("Exchange failed: %s", exc)
        finally:
            connection.close()
        return

    # Continuous loop: log and retry on errors rather than crashing.
    while True:
        try:
            summary = run_once(
                connection,
                server_url=server_url,
                node_code=node_code,
                node_name=node_name,
                batch_size=batch_size,
                sync_token=sync_token,
            )
            if any(summary.values()):
                logger.info("Cycle complete: %s", summary)
        except WorkerHttpError as exc:
            logger.warning("Exchange cycle failed (will retry): %s", exc)
        except Exception:
            logger.exception("Unexpected error in sync cycle")
        time.sleep(interval)


if __name__ == "__main__":
    main()
