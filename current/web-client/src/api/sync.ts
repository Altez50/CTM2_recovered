import type {
  SyncConflictRecord,
  SyncExchangeRequest,
  SyncExchangeResponse,
  SyncRegisterResponse,
  SyncStatusResponse,
} from '../types/models'
import { apiRequest } from './client'

export function fetchSyncStatus(nodeId?: string) {
  const path = nodeId ? `/api/sync/status/${nodeId}` : '/api/sync/status'
  return apiRequest<SyncStatusResponse>(path)
}

export function registerSyncNode(code: string, name: string) {
  return apiRequest<SyncRegisterResponse>('/api/sync/register', {
    method: 'POST',
    body: JSON.stringify({ code, name }),
  })
}

export function exchangeSync(payload: SyncExchangeRequest) {
  return apiRequest<SyncExchangeResponse>('/api/sync/exchange', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function fetchSyncConflicts(includeResolved = false) {
  const query = includeResolved ? '?include_resolved=true' : ''
  return apiRequest<{ conflicts: SyncConflictRecord[] }>(`/api/sync/conflicts${query}`)
}

export function resolveSyncConflict(conflictId: string) {
  return apiRequest<{ status: string; entity_type: string; entity_uuid: string }>(
    `/api/sync/conflicts/${conflictId}/resolve`,
    { method: 'POST' },
  )
}
