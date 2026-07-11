import type { ApiResponse } from '../types/api'
import type { DocumentMovements, GoodsDocument, GoodsDocumentPayload, GoodsImportPreview, GoodsKind, GoodsLine, ImportProfile, InventoryBalanceItem, InventoryMovementItem } from '../types/models'
import { apiRequest, downloadRequest } from './client'

interface ListParams {
  page?: number
  page_size?: number
  search?: string
  [key: string]: string | number | boolean | null | undefined
}

function toQuery(params: Record<string, string | number | boolean | null | undefined>) {
  const query = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      query.set(key, String(value))
    }
  })
  const value = query.toString()
  return value ? `?${value}` : ''
}

const PATH: Record<GoodsKind, { list: string; autoScheduleQuery: string }> = {
  receipt: { list: 'receipts', autoScheduleQuery: '' },
  issue: { list: 'issues', autoScheduleQuery: '' },
}

// --- CRUD ---

export function listGoodsDocuments(kind: GoodsKind, params: ListParams = {}) {
  return apiRequest<ApiResponse<GoodsDocument[]>>(`/api/goods/${PATH[kind].list}${toQuery(params)}`)
}

export function getGoodsDocument(kind: GoodsKind, id: number) {
  return apiRequest<ApiResponse<GoodsDocument>>(`/api/goods/${PATH[kind].list}/${id}`)
}

export function createGoodsDocument(kind: GoodsKind, payload: GoodsDocumentPayload) {
  return apiRequest<ApiResponse<GoodsDocument>>(`/api/goods/${PATH[kind].list}`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function updateGoodsDocument(kind: GoodsKind, id: number, payload: GoodsDocumentPayload) {
  return apiRequest<ApiResponse<GoodsDocument>>(`/api/goods/${PATH[kind].list}/${id}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  })
}

export function deleteGoodsDocument(kind: GoodsKind, id: number) {
  return apiRequest<ApiResponse<unknown>>(`/api/goods/${PATH[kind].list}/${id}`, { method: 'DELETE' })
}

export function postGoodsDocument(kind: GoodsKind, id: number, autoSchedule = true) {
  return apiRequest<ApiResponse<unknown>>(`/api/goods/${PATH[kind].list}/${id}/post${autoSchedule ? '' : '?auto_schedule=false'}`, {
    method: 'POST',
  })
}

export function unpostGoodsDocument(kind: GoodsKind, id: number) {
  return apiRequest<ApiResponse<unknown>>(`/api/goods/${PATH[kind].list}/${id}/unpost`, { method: 'POST' })
}

export function copyGoodsDocument(kind: GoodsKind, id: number) {
  return apiRequest<ApiResponse<GoodsDocument>>(`/api/goods/${PATH[kind].list}/${id}/copy`, {
    method: 'POST',
  })
}

// --- Inventory register ---

export function getInventoryBalances(params: { date?: string; object_id?: number | null; material_id?: number | null }) {
  return apiRequest<ApiResponse<InventoryBalanceItem[]>>(`/api/goods/inventory/balances${toQuery(params)}`)
}

export function getInventoryMovements(params: { date_from: string; date_to: string; object_id?: number | null; material_id?: number | null }) {
  return apiRequest<ApiResponse<InventoryMovementItem[]>>(`/api/goods/inventory/movements${toQuery(params)}`)
}

// --- Document register movements viewer ---

export function getDocumentMovements(kind: GoodsKind, id: number) {
  return apiRequest<ApiResponse<DocumentMovements>>(`/api/goods/${kind}/${id}/movements`)
}

// --- Excel export / import of document lines ---

export function exportGoodsLines(kind: GoodsKind, id: number): Promise<Blob> {
  return downloadRequest(`/api/goods/${PATH[kind].list}/${id}/lines/export`)
}

export async function previewGoodsLinesImport(kind: GoodsKind, file: File): Promise<GoodsImportPreview> {
  const form = new FormData()
  form.append('file', file)
  const response = await apiRequest<ApiResponse<GoodsImportPreview>>(`/api/goods/${PATH[kind].list}/0/lines/import`, {
    method: 'POST',
    body: form,
  })
  return response.data
}

export async function previewGoodsLinesByProfile(kind: GoodsKind, file: File): Promise<GoodsImportPreview> {
  const form = new FormData()
  form.append('file', file)
  const response = await apiRequest<ApiResponse<GoodsImportPreview>>(`/api/goods/lines/import-preview?kind=${kind}`, {
    method: 'POST',
    body: form,
  })
  return response.data
}

// --- Import profiles (shared across sync nodes via constants) ---

export function listImportProfiles(target?: ImportProfile['target']) {
  const query = target ? `?target=${target}` : ''
  return apiRequest<ApiResponse<ImportProfile[]>>(`/api/goods/import-profiles${query}`)
}

export function saveImportProfile(profile: ImportProfile) {
  return apiRequest<ApiResponse<ImportProfile>>('/api/goods/import-profiles', {
    method: 'POST',
    body: JSON.stringify(profile),
  })
}

export function deleteImportProfile(name: string, target: ImportProfile['target']) {
  return apiRequest<ApiResponse<unknown>>(`/api/goods/import-profiles/${encodeURIComponent(name)}?target=${target}`, {
    method: 'DELETE',
  })
}

// Re-export the line type for editor components.
export type { GoodsLine }
