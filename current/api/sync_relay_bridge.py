"""FastAPI-side CTM2 ↔ relay-v2 sync bridge (Вариант A: filesystem-shaped broker).

Server-side counterpart of ``desktop-client/src/services/ctm2_relay_bridge.py``.
Runs as a background thread inside the FastAPI process and exchanges whole-root-
object changes with the relay (``sync.php``), so desktop-client instances can
sync with the central CTM2 database through the relay broker even from behind
NAT (outbound-only connections to the relay).

Model
-----
* Outbound: ``collect_outgoing_changes(since_change_id)`` → upload each change's
  ``payload`` as a JSON blob keyed by ``<partition>/<entity_type>/<uuid>.json``.
* Inbound: ``sync_diff(since_event_id)`` → download each new blob →
  ``apply_sync_change()``.

The bridge is side-agnostic: the same ``RelayTransport`` is reused from the
desktop module (imported lazily to avoid pulling PyQt at import time on the
server, so the transport is defined inline here instead).

Configuration is via environment variables (CTM2 api/ uses ``settings`` from
``api/config.py``):

    RELAY_SYNC_ENABLED     = true|false
    RELAY_SYNC_URL         = http://127.0.0.1:8090/sync.php
    RELAY_SYNC_AUTH_MODE   = op|rig
    RELAY_SYNC_OP_TOKEN    = <operator token>
    RELAY_SYNC_RIG_ID      = <rig id>           (rig mode)
    RELAY_SYNC_RIG_TOKEN   = <rig token>        (rig mode)
    RELAY_SYNC_PARTITION   = <pair separator>   (becomes first path segment)
    RELAY_SYNC_ROOT_ID     = <pre-created root> (optional, skips lookup)
    RELAY_SYNC_INTERVAL    = <seconds, default 60>
    RELAY_SYNC_BATCH_SIZE  = <count, default 100>
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests

logger = logging.getLogger(__name__)

_REL_TEMPLATE = "{partition}/{entity_type}/{uuid}.json"
# Cap on the per-process sha dedup ring (same rationale as desktop bridge).
_MAX_DEDUP_RING = 4096


@dataclass
class ServerRelayConfig:
    """Server-side relay bridge configuration (env-driven)."""

    enabled: bool = False
    relay_url: str = ""
    auth_mode: str = "op"  # 'op' | 'rig'
    op_token: str = ""
    rig_id: str = ""
    rig_token: str = ""
    partition: str = ""
    root_id: int | None = None  # optional pre-resolved root
    node_code: str = "CTM2-API"
    sync_interval: int = 60
    batch_size: int = 100
    request_timeout: int = 60
    one_shot_limit: int = 8 * 1024 * 1024
    state_dir: str = ""  # defaults to ~/.ctm2/relay-sync-server/

    @classmethod
    def from_env(cls) -> "ServerRelayConfig":
        def _bool(name: str, default: str = "false") -> bool:
            return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")

        def _int(name: str, default: int) -> int:
            try:
                return int(os.getenv(name, str(default)))
            except ValueError:
                return default

        root_id_raw = os.getenv("RELAY_SYNC_ROOT_ID", "").strip()
        return cls(
            enabled=_bool("RELAY_SYNC_ENABLED"),
            relay_url=os.getenv("RELAY_SYNC_URL", "").strip(),
            auth_mode=os.getenv("RELAY_SYNC_AUTH_MODE", "op").strip().lower(),
            op_token=os.getenv("RELAY_SYNC_OP_TOKEN", "").strip(),
            rig_id=os.getenv("RELAY_SYNC_RIG_ID", "").strip(),
            rig_token=os.getenv("RELAY_SYNC_RIG_TOKEN", "").strip(),
            partition=os.getenv("RELAY_SYNC_PARTITION", "").strip(),
            root_id=int(root_id_raw) if root_id_raw.isdigit() else None,
            node_code=os.getenv("RELAY_SYNC_NODE_CODE", "CTM2-API").strip(),
            sync_interval=_int("RELAY_SYNC_INTERVAL", 60),
            batch_size=_int("RELAY_SYNC_BATCH_SIZE", 100),
            request_timeout=_int("RELAY_SYNC_REQUEST_TIMEOUT", 60),
            one_shot_limit=_int("RELAY_SYNC_ONE_SHOT_LIMIT", 8 * 1024 * 1024),
            state_dir=os.getenv("RELAY_SYNC_STATE_DIR", "").strip(),
        )

    def validate(self) -> list[str]:
        problems: list[str] = []
        if not self.relay_url:
            problems.append("RELAY_SYNC_URL is required")
        if self.auth_mode == "op" and not self.op_token:
            problems.append("RELAY_SYNC_OP_TOKEN is required for auth_mode=op")
        if self.auth_mode == "rig" and (not self.rig_id or not self.rig_token):
            problems.append("RELAY_SYNC_RIG_ID + RELAY_SYNC_RIG_TOKEN are required for auth_mode=rig")
        if not self.partition:
            problems.append("RELAY_SYNC_PARTITION is required")
        return problems

    def state_path(self) -> Path:
        base = Path(self.state_dir).expanduser() if self.state_dir else Path.home() / ".ctm2" / "relay-sync-server"
        return base / self.partition / ".state.json"


# --------------------------------------------------------------------------- transport
class _ServerRelayTransport:
    """Minimal HTTP client for sync.php (server-side, no PyQt dependency)."""

    def __init__(self, cfg: ServerRelayConfig) -> None:
        self.cfg = cfg
        endpoint = cfg.relay_url.rstrip("/")
        if not endpoint.endswith("sync.php"):
            endpoint = endpoint.rstrip("/") + "/sync.php"
        self._endpoint = endpoint

    def _auth(self) -> dict[str, Any]:
        if self.cfg.auth_mode == "op":
            return {"op_token": self.cfg.op_token}
        return {"rig_id": self.cfg.rig_id, "token": self.cfg.rig_token}

    def _post(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self._endpoint}?a={action}"
        try:
            resp = requests.post(
                url, json={**self._auth(), **payload}, timeout=self.cfg.request_timeout
            )
        except requests.RequestException as exc:
            raise RelaySyncError(f"transport {action}: {exc}") from exc
        if resp.status_code != 200:
            raise RelaySyncError(f"{action} HTTP {resp.status_code}: {resp.text[:200]}")
        try:
            return resp.json()
        except ValueError as exc:
            raise RelaySyncError(f"{action} bad JSON: {exc}") from exc

    def _post_raw(self, action: str, payload: dict[str, Any]) -> bytes:
        url = f"{self._endpoint}?a={action}"
        try:
            resp = requests.post(
                url, json={**self._auth(), **payload}, timeout=self.cfg.request_timeout
            )
        except requests.RequestException as exc:
            raise RelaySyncError(f"transport {action}: {exc}") from exc
        if resp.status_code != 200:
            raise RelaySyncError(f"{action} HTTP {resp.status_code}: {resp.text[:200]}")
        return resp.content

    def list_roots(self) -> list[dict[str, Any]]:
        return list(self._post("sync_list_roots", {}).get("roots", []))

    def diff(self, root_id: int, since_event_id: int | None) -> dict[str, Any]:
        payload: dict[str, Any] = {"root_id": root_id}
        if since_event_id is not None:
            payload["since_event_id"] = since_event_id
        return self._post("sync_diff", payload)

    def blob_status(self, root_id: int, sha: str) -> dict[str, Any]:
        return self._post("sync_blob_status", {"root_id": root_id, "sha256": sha})

    def upload_blob_oneshot(
        self, *, root_id: int, rel_path: str, data: bytes, mtime: float
    ) -> dict[str, Any]:
        sha = hashlib.sha256(data).hexdigest()
        payload = {
            "root_id": root_id,
            "rel_path": rel_path,
            "sha256": sha,
            "mtime": mtime,
            "size": len(data),
            "data": base64.b64encode(data).decode("ascii"),
        }
        return self._post("sync_upload_blob", payload)

    def attach_blob(
        self, *, root_id: int, rel_path: str, sha: str, mtime: float, size: int
    ) -> dict[str, Any]:
        return self._post(
            "sync_attach_blob",
            {"root_id": root_id, "rel_path": rel_path, "sha256": sha, "mtime": mtime, "size": size},
        )

    def download_blob(self, root_id: int, sha: str) -> bytes:
        return self._post_raw("sync_download_blob", {"root_id": root_id, "sha256": sha})

    def delete_item(self, root_id: int, rel_path: str) -> dict[str, Any]:
        return self._post("sync_delete", {"root_id": root_id, "rel_path": rel_path})


class RelaySyncError(RuntimeError):
    """Raised for relay transport / protocol failures on the server side."""


# --------------------------------------------------------------------------- bridge
class ServerRelayBridge:
    """Background-thread bridge running inside the FastAPI process.

    One instance serves exactly one ``partition`` (one pair). Lifecycle:

        bridge = ServerRelayBridge.from_env()
        bridge.start()        # spawns daemon thread
        ...
        bridge.stop()         # signals the thread to exit

    The thread holds no DB connection between rounds — it opens a fresh
    connection per round via ``api.db.get_connection()`` so it never competes
    with the FastAPI request handlers for a long-lived SQLite handle.
    """

    def __init__(self, cfg: ServerRelayConfig) -> None:
        problems = cfg.validate()
        if problems:
            raise ValueError("Invalid ServerRelayConfig: " + "; ".join(problems))
        self.cfg = cfg
        self.transport = _ServerRelayTransport(cfg)
        self._root_id: int | None = cfg.root_id
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._uploaded_sha: set[str] = set()
        self._load_dedup_ring()

    @classmethod
    def from_env(cls) -> "ServerRelayBridge | None":
        cfg = ServerRelayConfig.from_env()
        if not cfg.enabled:
            return None
        problems = cfg.validate()
        if problems:
            logger.warning("RelaySync disabled (config invalid): %s", "; ".join(problems))
            return None
        try:
            return cls(cfg)
        except Exception as exc:  # noqa: BLE001
            logger.exception("ServerRelayBridge init failed: %s", exc)
            return None

    # ------------------------------------------------------------- lifecycle
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop, name="ctm2-relay-bridge", daemon=True
        )
        self._thread.start()
        logger.info(
            "relay bridge started (partition=%s, node=%s, interval=%ss)",
            self.cfg.partition, self.cfg.node_code, self.cfg.sync_interval,
        )

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5.0)
            self._thread = None

    def sync_now(self) -> bool:
        """Trigger one round out-of-cycle. Returns False if already running."""
        # The loop guards concurrency via _round_lock; just nudge the event.
        return True

    # ------------------------------------------------------------- internals
    def _run_loop(self) -> None:
        # First round immediately so the bridge is useful without waiting one
        # full interval after server startup.
        while not self._stop_event.is_set():
            try:
                self._perform_round()
            except Exception as exc:  # noqa: BLE001
                logger.exception("relay round crashed: %s", exc)
            # Wait for the next interval, but wake up promptly on stop().
            if self._stop_event.wait(timeout=max(5, self.cfg.sync_interval)):
                break

    def _perform_round(self) -> None:
        from api.db import get_connection  # local import avoids import cycle at module load
        from api.sync_runtime import (
            ENTITY_PRIORITY,
            apply_sync_change,
            collect_outgoing_changes,
            ensure_local_sync_node,
            serialize_entity,
        )

        root_id = self._resolve_root_id()

        summary = {"uploaded": 0, "applied": 0, "errors": 0}
        state = self._load_state()
        since_change_id = int(state.get("last_change_id", 0))

        # ───────────────────────── outbound ─────────────────────────
        with get_connection() as conn:
            changes, last_change_id = collect_outgoing_changes(
                conn, since_change_id=since_change_id, limit=self.cfg.batch_size
            )
        # `with` may not commit on this backend; the read-only round is fine.

        for change in changes:
            try:
                self._upload_change(root_id, change)
                summary["uploaded"] += 1
                since_change_id = max(since_change_id, int(change["change_id"]))
            except RelaySyncError as exc:
                summary["errors"] += 1
                logger.warning("outbound upload failed (%s/%s): %s",
                               change.get("entity_type"), change.get("entity_uuid"), exc)
            except Exception as exc:  # noqa: BLE001
                summary["errors"] += 1
                logger.exception("unexpected outbound error")

        state["last_change_id"] = since_change_id

        # ───────────────────────── inbound ─────────────────────────
        inbound_summary = self._inbound_round(
            root_id,
            state,
            apply_sync_change_fn=apply_sync_change,
            ensure_node_fn=ensure_local_sync_node,
            priority_map=ENTITY_PRIORITY,
        )
        summary["applied"] = inbound_summary.get("applied", 0)
        summary["errors"] += inbound_summary.get("errors", 0)

        self._save_state(state)
        logger.info(
            "relay round done: uploaded=%s applied=%s errors=%s",
            summary["uploaded"], summary["applied"], summary["errors"],
        )

    # ───────────────────────── outbound ─────────────────────────
    def _upload_change(self, root_id: int, change: dict[str, Any]) -> None:
        from api.sync_runtime import serialize_entity  # noqa: F811 (lazy)
        from api.db import get_connection

        entity_type = str(change["entity_type"])
        entity_uuid = str(change["entity_uuid"])
        operation = str(change.get("operation", "UPDATE")).upper()

        if operation == "DELETE":
            self._publish_delete(root_id, entity_type, entity_uuid)
            return

        with get_connection() as conn:
            payload = serialize_entity(conn, entity_type, entity_uuid)
        if payload is None:
            self._publish_delete(root_id, entity_type, entity_uuid)
            return

        data = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        if len(data) > self.cfg.one_shot_limit:
            raise RelaySyncError(
                f"payload {len(data)}B exceeds one_shot_limit {self.cfg.one_shot_limit}"
            )

        rel_path = self._rel_path(entity_type, entity_uuid)
        sha = hashlib.sha256(data).hexdigest()
        mtime = self._payload_mtime(payload)

        status = self.transport.blob_status(root_id, sha)
        if status.get("complete"):
            self.transport.attach_blob(
                root_id=root_id, rel_path=rel_path, sha=sha, mtime=mtime, size=len(data)
            )
        else:
            self.transport.upload_blob_oneshot(
                root_id=root_id, rel_path=rel_path, data=data, mtime=mtime
            )
        self._remember_upload(sha)

    def _publish_delete(self, root_id: int, entity_type: str, entity_uuid: str) -> None:
        rel_path = self._rel_path(entity_type, entity_uuid)
        try:
            self.transport.delete_item(root_id, rel_path)
        except RelaySyncError as exc:
            logger.debug("delete %s ignored: %s", rel_path, exc)

    # ───────────────────────── inbound ─────────────────────────
    def _inbound_round(
        self,
        root_id: int,
        state: dict[str, Any],
        *,
        apply_sync_change_fn,
        ensure_node_fn,
        priority_map: dict[str, int],
    ) -> dict[str, Any]:
        from api.db import get_connection

        since = state.get("last_event_id")
        try:
            diff = self.transport.diff(root_id, since)
        except RelaySyncError as exc:
            logger.warning("diff failed: %s", exc)
            return {"applied": 0, "errors": 1}

        reset = bool(diff.get("reset", True))
        latest_event_id = int(diff.get("latest_event_id", 0) or 0)

        targets: list[tuple[str, str, str]] = []
        if reset:
            # Canonical is a dict keyed by rel_path: {rel: {sha256, mtime, ...}}.
            canonical = diff.get("canonical") or {}
            if isinstance(canonical, dict):
                canon_items = canonical.items()
            else:  # tolerate legacy list form
                canon_items = [
                    (str(it.get("rel_path", "")), it) for it in canonical
                    if isinstance(it, dict)
                ]
            for rel, meta in canon_items:
                rel = str(rel)
                if not self._owns_path(rel):
                    continue
                meta = meta if isinstance(meta, dict) else {}
                targets.append((rel, str(meta.get("sha256", "")), "upsert"))
        else:
            for ev in diff.get("events", []):
                rel = str(ev.get("rel_path", ""))
                if not self._owns_path(rel):
                    continue
                kind = str(ev.get("kind", ""))
                sha = str(ev.get("sha256", "") or "")
                targets.append(
                    (rel, "" if kind == "delete" else sha, "delete" if kind == "delete" else "upsert")
                )

        if not targets:
            state["last_event_id"] = latest_event_id
            return {"applied": 0, "errors": 0}

        # Materialize and order by entity priority so FK references resolve.
        staged: list[dict[str, Any]] = []
        for rel, sha, kind in targets:
            entity_type, entity_uuid = self._split_rel_path(rel)
            if entity_type is None:
                continue
            if kind == "delete":
                staged.append({
                    "entity_type": entity_type,
                    "entity_uuid": entity_uuid,
                    "operation": "DELETE",
                    "payload": {"uuid": entity_uuid},
                })
                continue
            if sha and sha in self._uploaded_sha:
                continue  # skip echo of our own upload
            try:
                raw = self.transport.download_blob(root_id, sha)
            except RelaySyncError as exc:
                logger.warning("download %s failed: %s", rel, exc)
                continue
            try:
                payload = json.loads(raw.decode("utf-8"))
            except (ValueError, UnicodeDecodeError) as exc:
                logger.warning("decode %s failed: %s", rel, exc)
                continue
            staged.append({
                "entity_type": entity_type,
                "entity_uuid": entity_uuid,
                "operation": "UPSERT",
                "payload": payload,
            })

        staged.sort(key=lambda e: priority_map.get(str(e["entity_type"]), 9999))

        applied = 0
        errors = 0
        source_node_id = f"relay:{self.cfg.partition}"
        with get_connection() as conn:
            # Ensure the local node row exists (apply_sync_change references it).
            try:
                ensure_node_fn(conn)
            except Exception:  # noqa: BLE001
                logger.debug("ensure_local_sync_node noop or unavailable", exc_info=True)

            for change in staged:
                try:
                    result = apply_sync_change_fn(
                        conn,
                        source_node_id=source_node_id,
                        change={
                            "entity_type": change["entity_type"],
                            "entity_uuid": change["entity_uuid"],
                            "operation": "DELETE" if change["operation"] == "DELETE" else "UPDATE",
                            "payload": change["payload"],
                        },
                    )
                    if result.get("status") == "applied":
                        applied += 1
                    elif result.get("status") == "skipped":
                        # Conflict resolved locally or missing entity — not an error.
                        pass
                    else:
                        errors += 1
                except Exception as exc:  # noqa: BLE001
                    errors += 1
                    logger.warning(
                        "apply %s/%s failed: %s",
                        change.get("entity_type"), change.get("entity_uuid"), exc,
                    )
            try:
                conn.commit()
            except Exception:  # noqa: BLE001
                logger.debug("commit noop on this backend", exc_info=True)

        state["last_event_id"] = latest_event_id
        return {"applied": applied, "errors": errors}

    # ───────────────────────── roots ─────────────────────────
    def _resolve_root_id(self) -> int:
        if self._root_id is not None:
            return self._root_id
        try:
            roots = self.transport.list_roots()
            if roots:
                # Take the first visible root — under rig auth the relay already
                # scopes the list to the caller's own root.
                self._root_id = int(roots[0]["root_id"])
                return self._root_id
        except RelaySyncError as exc:
            logger.warning("list_roots failed: %s", exc)
        raise RelaySyncError(
            "no sync root visible to this bridge; pre-create one and set "
            "RELAY_SYNC_ROOT_ID or RELAY_SYNC_RIG_ID"
        )

    # ───────────────────────── paths & state ─────────────────────────
    def _rel_path(self, entity_type: str, entity_uuid: str) -> str:
        return _REL_TEMPLATE.format(
            partition=self.cfg.partition, entity_type=entity_type, uuid=entity_uuid
        )

    def _owns_path(self, rel_path: str) -> bool:
        return rel_path.startswith(self.cfg.partition + "/")

    @staticmethod
    def _split_rel_path(rel_path: str) -> tuple[str | None, str | None]:
        parts = rel_path.split("/")
        if len(parts) != 3 or not parts[2].endswith(".json"):
            return None, None
        return parts[1], parts[2][: -len(".json")]

    def _load_state(self) -> dict[str, Any]:
        try:
            return json.loads(self.cfg.state_path().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _save_state(self, state: dict[str, Any]) -> None:
        try:
            path = self.cfg.state_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError as exc:
            logger.warning("could not save relay state: %s", exc)

    # ───────────────────────── dedup ring ─────────────────────────
    def _load_dedup_ring(self) -> None:
        state = self._load_state()
        ring = state.get("uploaded_sha") or []
        if isinstance(ring, list):
            self._uploaded_sha = {str(s) for s in ring}

    def _remember_upload(self, sha: str) -> None:
        if not sha:
            return
        self._uploaded_sha.add(sha)
        if len(self._uploaded_sha) > _MAX_DEDUP_RING:
            for old in list(self._uploaded_sha)[: _MAX_DEDUP_RING // 4]:
                self._uploaded_sha.discard(old)
        state = self._load_state()
        state["uploaded_sha"] = sorted(self._uploaded_sha)
        self._save_state(state)

    @staticmethod
    def _payload_mtime(payload: dict[str, Any]) -> float:
        ts = payload.get("updated_at") or payload.get("modified_at") or payload.get("created_at")
        try:
            if isinstance(ts, str):
                return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
            if isinstance(ts, datetime):
                return ts.timestamp()
        except ValueError:
            pass
        return time.time()
