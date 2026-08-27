import type { ApiResponse } from '../types/api'
import type { WorkExecutionResponse } from '../types/models'
import { apiRequest } from './client'

export interface RegisterQuery {
  page?: number
  page_size?: number
  period_from?: string
  period_to?: string
  object_id?: number | ''
  estimate_id?: number | ''
  work_id?: number | ''
  customer_id?: number | ''
  contract_id?: number | ''
  group_by?: string
  sort_by?: string
  sort_order?: 'asc' | 'desc' | null
  [key: string]: unknown
}

export function queryWorkExecution(params: RegisterQuery) {
  const query = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== '' && value !== null) {
      query.set(key, String(value))
    }
  })
  const suffix = query.toString() ? `?${query.toString()}` : ''
  return apiRequest<ApiResponse<WorkExecutionResponse>>(`/api/registers/work-execution${suffix}`)
}

/** URL для экспорта (возвращает binary-файл). */
export function buildExportUrl(params: RegisterQuery, format: 'csv' | 'xlsx'): string {
  const query = new URLSearchParams()
  query.set('format', format)
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== '' && value !== null) {
      query.set(key, String(value))
    }
  })
  return `/api/registers/work-execution/export?${query.toString()}`
}
