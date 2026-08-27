/** API-клиент инженерного раздела «Таблицы». См. TABLES_ENGINEERING_SPEC.md. */

import { apiRequest } from './client'
import type { ApiResponse, Pagination } from '../types/api'

export interface EngineeringField {
  name: string
  synonym: string
  type: string
  ref_table?: string
  hidden_default?: boolean
  is_representation?: boolean
  for?: string
}

export interface EngineeringTable {
  name: string
  synonym: string
  fields: EngineeringField[]
}

export interface EngineeringCategory {
  id: string
  label: string
  tables: EngineeringTable[]
}

export interface EngineeringCatalog {
  categories: EngineeringCategory[]
}

export interface TableData {
  rows: Record<string, unknown>[]
  columns: EngineeringField[]
  table: string
}

export interface QueryColumn {
  name: string
  synonym: string
}

export interface QueryResult {
  columns: QueryColumn[]
  rows: Record<string, unknown>[]
  row_count: number
  truncated: boolean
  elapsed_ms: number
  sql?: string
}

export interface TableQueryParams {
  page?: number
  page_size?: number
  search?: string
  sort_by?: string
  sort_order?: 'asc' | 'desc' | ''
  filters?: Record<string, string>
}

/** GET /api/engineering/catalog — каталог таблиц с синонимами полей. */
export function getEngineeringCatalog() {
  return apiRequest<ApiResponse<EngineeringCatalog>>('/api/engineering/catalog')
}

/** GET /api/engineering/tables/{name} — данные таблицы (просмотрщик). */
export function getTableData(table: string, params: TableQueryParams = {}) {
  const search = new URLSearchParams()
  if (params.page) search.set('page', String(params.page))
  if (params.page_size) search.set('page_size', String(params.page_size))
  if (params.search) search.set('search', params.search)
  if (params.sort_by) search.set('sort_by', params.sort_by)
  if (params.sort_order) search.set('sort_order', params.sort_order)
  if (params.filters) {
    for (const [key, value] of Object.entries(params.filters)) {
      if (value) search.set(`f_${key}`, value)
    }
  }
  const qs = search.toString()
  return apiRequest<ApiResponse<TableData>>(
    `/api/engineering/tables/${encodeURIComponent(table)}${qs ? `?${qs}` : ''}`,
  )
}

/** POST /api/engineering/query — выполнение запроса консоли. */
export function executeQuery(text: string, limit = 1000) {
  return apiRequest<ApiResponse<QueryResult>>('/api/engineering/query', {
    method: 'POST',
    body: JSON.stringify({ text, limit }),
  })
}

export type { Pagination }
