import type { ApiResponse } from '../types/api'
import type { DailyReport, Estimate, Timesheet, TimesheetImportPreview } from '../types/models'
import { apiRequest, downloadRequest } from './client'

interface ListParams {
  page?: number
  page_size?: number
  search?: string
  sort_by?: string
  sort_order?: 'asc' | 'desc'
  [key: string]: string | number | undefined
}

function toQuery(params: Record<string, string | number | undefined>) {
  const query = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== '') {
      query.set(key, String(value))
    }
  })
  const value = query.toString()
  return value ? `?${value}` : ''
}

export function listEstimates(params: ListParams = {}) {
  return apiRequest<ApiResponse<Estimate[]>>(`/api/documents/estimates${toQuery(params)}`)
}

export function getEstimate(id: number) {
  return apiRequest<ApiResponse<Estimate>>(`/api/documents/estimates/${id}`)
}

export function createEstimate(payload: Estimate) {
  return apiRequest<ApiResponse<Estimate>>('/api/documents/estimates', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function updateEstimate(id: number, payload: Estimate) {
  return apiRequest<ApiResponse<Estimate>>(`/api/documents/estimates/${id}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  })
}

export function deleteEstimate(id: number) {
  return apiRequest<ApiResponse<unknown>>(`/api/documents/estimates/${id}`, {
    method: 'DELETE',
  })
}

export function postEstimate(id: number) {
  return apiRequest<ApiResponse<unknown>>(`/api/documents/estimates/${id}/post`, { method: 'POST' })
}

export function unpostEstimate(id: number) {
  return apiRequest<ApiResponse<unknown>>(`/api/documents/estimates/${id}/unpost`, { method: 'POST' })
}

export function printEstimate(id: number, format: 'pdf' | 'excel') {
  return downloadRequest(`/api/documents/estimates/${id}/print?format=${format}`)
}

export function printAct(id: number, format: 'pdf' | 'excel') {
  return downloadRequest(`/api/documents/estimates/${id}/print-act?format=${format}`)
}

export function copyEstimate(id: number) {
  return apiRequest<ApiResponse<Estimate>>(`/api/documents/estimates/${id}/copy`, {
    method: 'POST',
  })
}

// ── Estimate text import / export (TSV / JSON / XLSX) ──────────────────────

export interface EstimateImportResult {
  imported: number
  warnings?: string[]
  format: string
}

export function importEstimateText(
  id: number,
  format: 'tsv' | 'json' | 'xlsx',
  body: string | ArrayBuffer,
  replace = true,
): Promise<ApiResponse<EstimateImportResult>> {
  const isBinary = format === 'xlsx' && typeof body !== 'string'
  const headers: Record<string, string> = isBinary
    ? { 'Content-Type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' }
    : format === 'json'
      ? { 'Content-Type': 'application/json' }
      : { 'Content-Type': 'text/tab-separated-values; charset=utf-8' }
  const qs = new URLSearchParams({ format, replace: String(replace) })
  return apiRequest<ApiResponse<EstimateImportResult>>(
    `/api/documents/estimates/${id}/import-text?${qs}`,
    { method: 'POST', headers, body: body as BodyInit },
  )
}

export function exportEstimateText(
  id: number,
  format: 'tsv' | 'json' | 'xlsx',
): Promise<Blob> {
  return downloadRequest(`/api/documents/estimates/${id}/export-text?format=${format}`)
}

export function listDailyReports(params: ListParams = {}) {
  return apiRequest<ApiResponse<DailyReport[]>>(`/api/documents/daily-reports${toQuery(params)}`)
}

export function getDailyReport(id: number) {
  return apiRequest<ApiResponse<DailyReport>>(`/api/documents/daily-reports/${id}`)
}

export function createDailyReport(payload: DailyReport) {
  return apiRequest<ApiResponse<DailyReport>>('/api/documents/daily-reports', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function updateDailyReport(id: number, payload: DailyReport) {
  return apiRequest<ApiResponse<DailyReport>>(`/api/documents/daily-reports/${id}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  })
}

export function deleteDailyReport(id: number) {
  return apiRequest<ApiResponse<unknown>>(`/api/documents/daily-reports/${id}`, {
    method: 'DELETE',
  })
}

export function postDailyReport(id: number) {
  return apiRequest<ApiResponse<unknown>>(`/api/documents/daily-reports/${id}/post`, { method: 'POST' })
}

export function unpostDailyReport(id: number) {
  return apiRequest<ApiResponse<unknown>>(`/api/documents/daily-reports/${id}/unpost`, { method: 'POST' })
}

export function printDailyReport(id: number, format: 'pdf' | 'excel') {
  return downloadRequest(`/api/documents/daily-reports/${id}/print?format=${format}`)
}

export function printDailyReportAct(id: number, format: 'pdf' | 'excel') {
  return downloadRequest(`/api/documents/daily-reports/${id}/print-act?format=${format}`)
}

export function copyDailyReport(id: number) {
  return apiRequest<ApiResponse<DailyReport>>(`/api/documents/daily-reports/${id}/copy`, {
    method: 'POST',
  })
}

export function listTimesheets(params: ListParams = {}) {
  return apiRequest<ApiResponse<Timesheet[]>>(`/api/documents/timesheets${toQuery(params)}`)
}

export function getTimesheet(id: number) {
  return apiRequest<ApiResponse<Timesheet>>(`/api/documents/timesheets/${id}`)
}

export function createTimesheet(payload: Timesheet) {
  return apiRequest<ApiResponse<Timesheet>>('/api/documents/timesheets', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function updateTimesheet(id: number, payload: Timesheet) {
  return apiRequest<ApiResponse<Timesheet>>(`/api/documents/timesheets/${id}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  })
}

export function deleteTimesheet(id: number) {
  return apiRequest<ApiResponse<unknown>>(`/api/documents/timesheets/${id}`, {
    method: 'DELETE',
  })
}

export function postTimesheet(id: number) {
  return apiRequest<ApiResponse<unknown>>(`/api/documents/timesheets/${id}/post`, { method: 'POST' })
}

export function unpostTimesheet(id: number) {
  return apiRequest<ApiResponse<unknown>>(`/api/documents/timesheets/${id}/unpost`, { method: 'POST' })
}

export function printTimesheet(id: number, format: 'pdf' | 'excel') {
  return downloadRequest(`/api/documents/timesheets/${id}/print?format=${format}`)
}

export function exportTimesheet(id: number, format: 'json' | 'excel') {
  return downloadRequest(`/api/documents/timesheets/${id}/export?format=${format}`)
}

export function copyTimesheet(id: number) {
  return apiRequest<ApiResponse<Timesheet>>(`/api/documents/timesheets/${id}/copy`, {
    method: 'POST',
  })
}

export function autofillTimesheet(payload: { object_id: number; estimate_id?: number | null; month_year: string }) {
  return apiRequest<ApiResponse<Timesheet['lines']>>('/api/documents/timesheets/autofill', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function previewTimesheetImport(file: File) {
  const formData = new FormData()
  formData.append('file', file)
  return apiRequest<ApiResponse<TimesheetImportPreview>>('/api/documents/timesheets/import-preview', {
    method: 'POST',
    body: formData,
  })
}
