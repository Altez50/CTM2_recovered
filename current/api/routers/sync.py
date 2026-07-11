from __future__ import annotations

import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends

from api.auth_dependencies import get_db, require_sync_token
from api.models.sync import (
    SyncExchangeRequest,
    SyncExchangeResponse,
    SyncRegisterResponse,
    SyncStatusResponse,
    SyncNodeRegistrationRequest,
)
from api.sync_runtime import (
    get_sync_status,
    list_conflicts,
    process_sync_exchange,
    prune_sync_changes,
    register_sync_node,
    resolve_conflict,
)
from api.database import SYNC_SCHEMA_VERSION, get_local_sync_node


router = APIRouter(
    prefix="/api/sync",
    tags=["sync"],
    # Peer-to-peer token gate. No-op unless SYNC_TOKEN is configured on the server.
    dependencies=[Depends(require_sync_token)],
)


@router.post("/register", response_model=SyncRegisterResponse)
def register_node(
    payload: SyncNodeRegistrationRequest,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
) -> SyncRegisterResponse:
    node = register_sync_node(connection, code=payload.code, name=payload.name)
    connection.commit()
    return SyncRegisterResponse(
        node=node,
        local_node=get_local_sync_node(connection),
        schema_version=SYNC_SCHEMA_VERSION,
    )


@router.post("/exchange", response_model=SyncExchangeResponse)
def exchange(
    payload: SyncExchangeRequest,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
) -> SyncExchangeResponse:
    return SyncExchangeResponse(**process_sync_exchange(connection, payload.model_dump()))


@router.get("/status", response_model=SyncStatusResponse)
def status(
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
) -> SyncStatusResponse:
    return SyncStatusResponse(**get_sync_status(connection))


@router.get("/status/{node_id}", response_model=SyncStatusResponse)
def node_status(
    node_id: str,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
) -> SyncStatusResponse:
    return SyncStatusResponse(**get_sync_status(connection, node_id=node_id))


@router.post("/prune")
def prune_queue(
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    safety_margin: int = 0,
) -> dict:
    """Delete sync_changes rows that every known peer has already received."""
    return prune_sync_changes(connection, safety_margin=safety_margin)


@router.get("/conflicts")
def list_sync_conflicts(
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    include_resolved: bool = False,
) -> dict:
    """List archived conflicts awaiting manual resolution."""
    return {"conflicts": list_conflicts(connection, include_resolved=include_resolved)}


@router.post("/conflicts/{conflict_id}/resolve")
def resolve_sync_conflict(
    conflict_id: str,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
) -> dict:
    """Force-apply the remote version of a conflict, overwriting local."""
    return resolve_conflict(connection, conflict_id)
