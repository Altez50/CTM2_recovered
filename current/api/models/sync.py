from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


SyncOperation = Literal["INSERT", "UPDATE", "DELETE"]


class SyncNodeRegistrationRequest(BaseModel):
    code: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=255)


class SyncNodeInfo(BaseModel):
    id: str
    code: str
    name: str
    is_local: bool = False
    last_sync_in: str | None = None
    last_sync_out: str | None = None
    sent_packet_no: int = 0
    received_packet_no: int = 0


class SyncChangeEnvelope(BaseModel):
    change_id: int | None = None
    entity_type: str = Field(min_length=1, max_length=128)
    entity_uuid: str = Field(min_length=1, max_length=128)
    operation: SyncOperation
    created_at: str | None = None
    updated_at: str | None = None
    payload: dict[str, Any] | None = None


class SyncConflictRecord(BaseModel):
    entity_type: str
    entity_uuid: str
    resolution: str
    local_updated_at: str | None = None
    remote_updated_at: str | None = None


class SyncRegisterResponse(BaseModel):
    node: SyncNodeInfo
    local_node: SyncNodeInfo
    schema_version: str


class SyncExchangeRequest(BaseModel):
    schema_version: str
    node_id: str | None = None
    node_code: str = Field(min_length=1, max_length=128)
    node_name: str = Field(min_length=1, max_length=255)
    last_received_change_id: int = Field(default=0, ge=0)
    batch_size: int = Field(default=100, ge=1, le=500)
    changes: list[SyncChangeEnvelope] = Field(default_factory=list)


class SyncExchangeResponse(BaseModel):
    schema_version: str
    local_node: SyncNodeInfo
    remote_node: SyncNodeInfo
    processed_count: int = 0
    skipped_count: int = 0
    error_count: int = 0
    outgoing_count: int = 0
    last_sent_change_id: int = 0
    changes: list[SyncChangeEnvelope] = Field(default_factory=list)
    conflicts: list[SyncConflictRecord] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class SyncStatusResponse(BaseModel):
    schema_version: str
    local_node: SyncNodeInfo
    nodes: list[SyncNodeInfo] = Field(default_factory=list)
    pending_changes: int = 0
