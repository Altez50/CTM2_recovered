import type { ApiResponse } from '../types/api'
import type {
  AllocationBase,
  CostCalculation,
  CostCardResponse,
  CostElement,
  DeviationsReportResponse,
  DrilldownQuery,
  DrilldownResponse,
  LimitCheckResponse,
  Machine,
  MachineryUsageReport,
  MaterialConsumption,
  OverheadDistributionRequest,
  OverheadDistributionResult,
  OverheadExpense,
  ProfitabilityReportResponse,
  SubcontractAcceptance,
  TurnoverReportResponse,
} from '../types/costAccounting'
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

// ── References ────────────────────────────────────────────────────────────

export function listCostElements() {
  return apiRequest<ApiResponse<CostElement[]>>('/api/cost/cost-elements')
}

export function listAllocationBases() {
  return apiRequest<ApiResponse<AllocationBase[]>>('/api/cost/allocation-bases')
}

// ── Machines ──────────────────────────────────────────────────────────────

export function listMachines(params: ListParams = {}) {
  return apiRequest<ApiResponse<Machine[]>>(`/api/cost/machines${toQuery(params)}`)
}

export function getMachine(id: number) {
  return apiRequest<ApiResponse<Machine>>(`/api/cost/machines/${id}`)
}

export function createMachine(payload: Machine) {
  return apiRequest<ApiResponse<Machine>>('/api/cost/machines', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function updateMachine(id: number, payload: Machine) {
  return apiRequest<ApiResponse<Machine>>(`/api/cost/machines/${id}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  })
}

export function deleteMachine(id: number) {
  return apiRequest<ApiResponse<unknown>>(`/api/cost/machines/${id}`, {
    method: 'DELETE',
  })
}

// ── Material Consumptions ─────────────────────────────────────────────────

export function listMaterialConsumptions(params: ListParams = {}) {
  return apiRequest<ApiResponse<MaterialConsumption[]>>(
    `/api/cost/material-consumptions${toQuery(params)}`,
  )
}

export function getMaterialConsumption(id: number) {
  return apiRequest<ApiResponse<MaterialConsumption>>(`/api/cost/material-consumptions/${id}`)
}

export function createMaterialConsumption(payload: MaterialConsumption) {
  return apiRequest<ApiResponse<MaterialConsumption>>('/api/cost/material-consumptions', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function updateMaterialConsumption(id: number, payload: MaterialConsumption) {
  return apiRequest<ApiResponse<MaterialConsumption>>(`/api/cost/material-consumptions/${id}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  })
}

export function deleteMaterialConsumption(id: number) {
  return apiRequest<ApiResponse<unknown>>(`/api/cost/material-consumptions/${id}`, {
    method: 'DELETE',
  })
}

export function restoreMaterialConsumption(id: number) {
  return apiRequest<ApiResponse<unknown>>(`/api/cost/material-consumptions/${id}/restore`, {
    method: 'POST',
  })
}

export function postMaterialConsumption(id: number) {
  return apiRequest<ApiResponse<unknown>>(`/api/cost/material-consumptions/${id}/post`, {
    method: 'POST',
  })
}

export function unpostMaterialConsumption(id: number) {
  return apiRequest<ApiResponse<unknown>>(`/api/cost/material-consumptions/${id}/unpost`, {
    method: 'POST',
  })
}

// ── Machinery Usage Reports ───────────────────────────────────────────────

export function listMachineryUsageReports(params: ListParams = {}) {
  return apiRequest<ApiResponse<MachineryUsageReport[]>>(
    `/api/cost/machinery-usage-reports${toQuery(params)}`,
  )
}

export function getMachineryUsageReport(id: number) {
  return apiRequest<ApiResponse<MachineryUsageReport>>(`/api/cost/machinery-usage-reports/${id}`)
}

export function createMachineryUsageReport(payload: MachineryUsageReport) {
  return apiRequest<ApiResponse<MachineryUsageReport>>('/api/cost/machinery-usage-reports', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function updateMachineryUsageReport(id: number, payload: MachineryUsageReport) {
  return apiRequest<ApiResponse<MachineryUsageReport>>(`/api/cost/machinery-usage-reports/${id}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  })
}

export function deleteMachineryUsageReport(id: number) {
  return apiRequest<ApiResponse<unknown>>(`/api/cost/machinery-usage-reports/${id}`, {
    method: 'DELETE',
  })
}

export function restoreMachineryUsageReport(id: number) {
  return apiRequest<ApiResponse<unknown>>(`/api/cost/machinery-usage-reports/${id}/restore`, {
    method: 'POST',
  })
}

export function postMachineryUsageReport(id: number) {
  return apiRequest<ApiResponse<unknown>>(`/api/cost/machinery-usage-reports/${id}/post`, {
    method: 'POST',
  })
}

export function unpostMachineryUsageReport(id: number) {
  return apiRequest<ApiResponse<unknown>>(`/api/cost/machinery-usage-reports/${id}/unpost`, {
    method: 'POST',
  })
}

// ── Subcontract Acceptances ───────────────────────────────────────────────

export function listSubcontractAcceptances(params: ListParams = {}) {
  return apiRequest<ApiResponse<SubcontractAcceptance[]>>(
    `/api/cost/subcontract-acceptances${toQuery(params)}`,
  )
}

export function getSubcontractAcceptance(id: number) {
  return apiRequest<ApiResponse<SubcontractAcceptance>>(`/api/cost/subcontract-acceptances/${id}`)
}

export function createSubcontractAcceptance(payload: SubcontractAcceptance) {
  return apiRequest<ApiResponse<SubcontractAcceptance>>('/api/cost/subcontract-acceptances', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function updateSubcontractAcceptance(id: number, payload: SubcontractAcceptance) {
  return apiRequest<ApiResponse<SubcontractAcceptance>>(
    `/api/cost/subcontract-acceptances/${id}`,
    { method: 'PUT', body: JSON.stringify(payload) },
  )
}

export function deleteSubcontractAcceptance(id: number) {
  return apiRequest<ApiResponse<unknown>>(`/api/cost/subcontract-acceptances/${id}`, {
    method: 'DELETE',
  })
}

export function restoreSubcontractAcceptance(id: number) {
  return apiRequest<ApiResponse<unknown>>(`/api/cost/subcontract-acceptances/${id}/restore`, {
    method: 'POST',
  })
}

export function postSubcontractAcceptance(id: number) {
  return apiRequest<ApiResponse<unknown>>(`/api/cost/subcontract-acceptances/${id}/post`, {
    method: 'POST',
  })
}

export function unpostSubcontractAcceptance(id: number) {
  return apiRequest<ApiResponse<unknown>>(`/api/cost/subcontract-acceptances/${id}/unpost`, {
    method: 'POST',
  })
}

// ── Overhead Expenses ─────────────────────────────────────────────────────

export function listOverheadExpenses(params: ListParams = {}) {
  return apiRequest<ApiResponse<OverheadExpense[]>>(
    `/api/cost/overhead-expenses${toQuery(params)}`,
  )
}

export function getOverheadExpense(id: number) {
  return apiRequest<ApiResponse<OverheadExpense>>(`/api/cost/overhead-expenses/${id}`)
}

export function createOverheadExpense(payload: OverheadExpense) {
  return apiRequest<ApiResponse<OverheadExpense>>('/api/cost/overhead-expenses', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function updateOverheadExpense(id: number, payload: OverheadExpense) {
  return apiRequest<ApiResponse<OverheadExpense>>(`/api/cost/overhead-expenses/${id}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  })
}

export function deleteOverheadExpense(id: number) {
  return apiRequest<ApiResponse<unknown>>(`/api/cost/overhead-expenses/${id}`, {
    method: 'DELETE',
  })
}

export function restoreOverheadExpense(id: number) {
  return apiRequest<ApiResponse<unknown>>(`/api/cost/overhead-expenses/${id}/restore`, {
    method: 'POST',
  })
}

// ── Overhead Distribution ─────────────────────────────────────────────────

export function distributeOverhead(payload: OverheadDistributionRequest) {
  return apiRequest<ApiResponse<OverheadDistributionResult>>('/api/cost/overhead/distribute', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function cancelOverheadDistribution(period: string) {
  return apiRequest<ApiResponse<{ period: string; cancelled: boolean }>>(
    `/api/cost/overhead/cancel-distribution?period=${period}`,
    { method: 'POST' },
  )
}

// ── Cost Calculations ────────────────────────────────────────────────────

export function listCostCalculations(params: ListParams = {}) {
  return apiRequest<ApiResponse<CostCalculation[]>>(
    `/api/cost/cost-calculations${toQuery(params)}`,
  )
}

export function getCostCalculation(id: number) {
  return apiRequest<ApiResponse<CostCalculation>>(`/api/cost/cost-calculations/${id}`)
}

export function createCostCalculation(payload: CostCalculation) {
  return apiRequest<ApiResponse<CostCalculation>>('/api/cost/cost-calculations', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function updateCostCalculation(id: number, payload: CostCalculation) {
  return apiRequest<ApiResponse<CostCalculation>>(`/api/cost/cost-calculations/${id}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  })
}

export function deleteCostCalculation(id: number) {
  return apiRequest<ApiResponse<unknown>>(`/api/cost/cost-calculations/${id}`, {
    method: 'DELETE',
  })
}

export function restoreCostCalculation(id: number) {
  return apiRequest<ApiResponse<unknown>>(`/api/cost/cost-calculations/${id}/restore`, {
    method: 'POST',
  })
}

export function calculateCost(id: number) {
  return apiRequest<ApiResponse<{ calculation_id: number; status: string; record_count: number; warnings: string[] }>>(
    `/api/cost/cost-calculations/${id}/calculate`,
    { method: 'POST' },
  )
}

export function postCostCalculation(id: number) {
  return apiRequest<ApiResponse<unknown>>(`/api/cost/cost-calculations/${id}/post`, {
    method: 'POST',
  })
}

export function unpostCostCalculation(id: number) {
  return apiRequest<ApiResponse<unknown>>(`/api/cost/cost-calculations/${id}/unpost`, {
    method: 'POST',
  })
}

// ── Reports ───────────────────────────────────────────────────────────────

export function getCostCard(objectId: number, periodFrom?: string | null, periodTo?: string | null) {
  const params = new URLSearchParams()
  params.set('object_id', String(objectId))
  if (periodFrom) params.set('period_from', periodFrom)
  if (periodTo) params.set('period_to', periodTo)
  return apiRequest<ApiResponse<CostCardResponse>>(`/api/cost/reports/cost-card?${params}`)
}

export function getCostTurnover(periodFrom: string, periodTo: string, objectId: number = 0) {
  return apiRequest<ApiResponse<TurnoverReportResponse>>(
    `/api/cost/reports/cost-turnover?period_from=${periodFrom}&period_to=${periodTo}&object_id=${objectId}`,
  )
}

export function getCostDeviations(period: string, threshold: number = 0, objectId: number = 0) {
  return apiRequest<ApiResponse<DeviationsReportResponse>>(
    `/api/cost/reports/cost-deviations?period=${period}&threshold=${threshold}&object_id=${objectId}`,
  )
}

export function getCostProfitability(
  period?: string | null,
  groupBy: 'object' | 'contract' | 'object_contract' = 'object',
) {
  const params = new URLSearchParams()
  if (period) params.set('period', period)
  params.set('group_by', groupBy)
  const qs = params.toString()
  return apiRequest<ApiResponse<ProfitabilityReportResponse>>(
    `/api/cost/reports/cost-profitability${qs ? `?${qs}` : ''}`,
  )
}

// ── Limit Check ───────────────────────────────────────────────────────────
// Note: limit check uses data from CostItemMaterial, returned directly from
// the report endpoints. For now, client-side limit validation is optional.

// ── Document text import / export (TSV / JSON / XLSX) ─────────────────────

export type DocDataExchangeKind =
  | 'material-consumptions'
  | 'machinery-usage-reports'
  | 'subcontract-acceptances'
  | 'overhead-expenses'
  | 'daily-reports'

export interface DocImportResult {
  imported: number
  warnings?: string[]
  format: string
  preview?: boolean
}

/**
 * Import tabular lines into a cost-accounting document from raw text/bytes.
 * Missing reference entities (materials, units, works, counterparties) are
 * created automatically on the server.
 */
export function importDocumentText(
  kind: DocDataExchangeKind,
  docId: number,
  format: 'tsv' | 'json' | 'xlsx',
  body: string | ArrayBuffer,
  replace = true,
  preview = false,
): Promise<ApiResponse<DocImportResult>> {
  const isBinary = format === 'xlsx' && typeof body !== 'string'
  const headers: Record<string, string> = isBinary
    ? { 'Content-Type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' }
    : format === 'json'
      ? { 'Content-Type': 'application/json' }
      : { 'Content-Type': 'text/tab-separated-values; charset=utf-8' }
  const qs = new URLSearchParams({ format, replace: String(replace), preview: String(preview) })
  return apiRequest<ApiResponse<DocImportResult>>(
    `/api/cost/${kind}/${docId}/import-text?${qs}`,
    { method: 'POST', headers, body: body as BodyInit },
  )
}

/** Export a document's tabular lines as a downloadable blob (tsv/json/xlsx). */
export function exportDocumentText(
  kind: DocDataExchangeKind,
  docId: number,
  format: 'tsv' | 'json' | 'xlsx',
): Promise<Blob> {
  return downloadRequest(`/api/cost/${kind}/${docId}/export-text?format=${format}`)
}

// ── Drilldown (COST_DRILLDOWN_SPEC.md §6.4) ───────────────────────────────

export function getActualCostsDrilldown(
  params: DrilldownQuery,
): Promise<ApiResponse<DrilldownResponse>> {
  const qs = new URLSearchParams()
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') qs.set(k, String(v))
  })
  return apiRequest(`/api/cost/drilldown/actual-costs?${qs}`)
}

export function getPlannedCostsDrilldown(
  params: DrilldownQuery,
): Promise<ApiResponse<DrilldownResponse>> {
  const qs = new URLSearchParams()
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') qs.set(k, String(v))
  })
  return apiRequest(`/api/cost/drilldown/planned-costs?${qs}`)
}

export function getOverheadDrilldown(
  params: DrilldownQuery,
): Promise<ApiResponse<DrilldownResponse>> {
  const qs = new URLSearchParams()
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') qs.set(k, String(v))
  })
  return apiRequest(`/api/cost/drilldown/overhead?${qs}`)
}
