import type { ApiResponse } from '../types/api'
import type { ReferenceKind, ReferenceRecord } from '../types/models'
import { apiRequest } from './client'

export interface ReferenceListParams {
  page?: number
  page_size?: number
  search?: string
  sort_by?: string
  sort_order?: 'asc' | 'desc'
  review_status?: 'all' | 'ok' | 'incorrect' | 'corrected'
  organization_id?: number
  counterparty_id?: number
  material_id?: number
  characteristic_id?: number
}

function toQuery(params: ReferenceListParams) {
  const query = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (key === 'review_status' && value === 'all') {
      return
    }
    if (value !== undefined && value !== null && value !== '') {
      query.set(key, String(value))
    }
  })
  const value = query.toString()
  return value ? `?${value}` : ''
}

export function listReferences(kind: ReferenceKind, params: ReferenceListParams = {}) {
  return apiRequest<ApiResponse<ReferenceRecord[]>>(`/api/references/${kind}${toQuery(params)}`)
}

export function getReference(kind: ReferenceKind, id: number) {
  return apiRequest<ApiResponse<ReferenceRecord>>(`/api/references/${kind}/${id}`)
}

export function createReference(kind: ReferenceKind, payload: Record<string, unknown>) {
  return apiRequest<ApiResponse<ReferenceRecord>>(`/api/references/${kind}`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function updateReference(kind: ReferenceKind, id: number, payload: Record<string, unknown>) {
  return apiRequest<ApiResponse<ReferenceRecord>>(`/api/references/${kind}/${id}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  })
}

export function deleteReference(kind: ReferenceKind, id: number) {
  return apiRequest<ApiResponse<unknown>>(`/api/references/${kind}/${id}`, {
    method: 'DELETE',
  })
}
