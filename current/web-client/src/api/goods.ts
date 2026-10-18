import type { ApiResponse } from '../types/api'
import type { DocumentMovements, GoodsDocument, GoodsDocumentPayload, GoodsImportPreview, GoodsKind, GoodsLine, GoodsTransfer, GoodsTransferPayload, ImportProfile, InventoryBalanceItem, InventoryMovementItem } from '../types/models'
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

// --- Internal warehouse transfers ---

export function listGoodsTransfers(params: ListParams = {}) {
  return apiRequest<ApiResponse<GoodsTransfer[]>>(`/api/goods/transfers${toQuery(params)}`)
}

export function getGoodsTransfer(id: number) {
  return apiRequest<ApiResponse<GoodsTransfer>>(`/api/goods/transfers/${id}`)
}

export function saveGoodsTransfer(payload: GoodsTransferPayload, id?: number) {
  return apiRequest<ApiResponse<GoodsTransfer>>(`/api/goods/transfers${id ? `/${id}` : ''}`, {
    method: id ? 'PUT' : 'POST', body: JSON.stringify(payload),
  })
}

export function postGoodsTransfer(id: number) {
  return apiRequest<ApiResponse<unknown>>(`/api/goods/transfers/${id}/post`, { method: 'POST' })
}

export function unpostGoodsTransfer(id: number) {
  return apiRequest<ApiResponse<unknown>>(`/api/goods/transfers/${id}/unpost`, { method: 'POST' })
}

export function copyGoodsTransfer(id: number) {
  return apiRequest<ApiResponse<GoodsTransfer>>(`/api/goods/transfers/${id}/copy`, { method: 'POST' })
}

export function deleteGoodsTransfer(id: number) {
  return apiRequest<ApiResponse<unknown>>(`/api/goods/transfers/${id}`, { method: 'DELETE' })
}

export function getGoodsTransferMovements(id: number) {
  return apiRequest<ApiResponse<{ document: GoodsTransfer; inventory: InventoryMovementItem[]; settlements: [] }>>(`/api/goods/transfers/${id}/movements`)
}

// --- Inventory register ---

export function getInventoryBalances(params: { date?: string; object_id?: number | null; material_id?: number | null; warehouse_id?: number | null }) {
  return apiRequest<ApiResponse<InventoryBalanceItem[]>>(`/api/goods/inventory/balances${toQuery(params)}`)
}

export function getInventoryMovements(params: { date_from: string; date_to: string; object_id?: number | null; material_id?: number | null; warehouse_id?: number | null }) {
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

export interface GoodsMaterialResolveInput {
  material_name: string
  material_code?: string | null
  unit_name?: string | null
  unit_id?: number | null
  unit_price?: number
  source_row_numbers: number[]
}

export interface GoodsMaterialResolveResult {
  material_id: number
  material_name: string
  material_code?: string | null
  unit_id?: number | null
  unit_name?: string | null
  price: number
  status: 'created' | 'reused'
  source_row_numbers: number[]
}

export function resolveGoodsMaterials(materials: GoodsMaterialResolveInput[]) {
  return apiRequest<ApiResponse<{
    created_count: number
    reused_count: number
    materials: GoodsMaterialResolveResult[]
  }>>('/api/goods/materials/resolve', {
    method: 'POST',
    body: JSON.stringify({ materials }),
  })
}

const GOODS_LINE_HEADERS = [
  '№', 'Материал', 'Код материала', 'Наименование', 'Ед.изм.', 'Количество',
  'Цена без НДС', 'Ставка НДС %', 'Сумма без НДС', 'Сумма НДС',
  'Сумма с НДС', 'Объект', 'Чертёж/СП', 'Примечание',
  'ID единицы', 'ID упаковки', 'ID характеристики', 'ID серии',
]

function escapeExcelXml(value: unknown): string {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

/** Build an Excel-compatible table from the current editor state, including unsaved rows. */
export function exportCurrentGoodsLines(lines: GoodsLine[], title: string): Blob {
  const worksheetTitle = title.replace(/[\\/*?:\[\]]/g, '_').trim().slice(0, 31) || 'ТМЦ'
  const rows = lines.map((line, index) => [
    line.line_number || index + 1,
    line.material_id ?? '',
    line.material_code ?? '',
    line.name ?? '',
    line.unit_name || line.unit || '',
    line.quantity ?? '',
    line.price_without_vat ?? '',
    line.vat_rate ?? '',
    line.sum_without_vat ?? '',
    line.vat_amount ?? '',
    line.sum_with_vat ?? '',
    line.object_id ?? '',
    line.drawing_code ?? '',
    line.note ?? '',
    line.unit_id ?? '', line.package_id ?? '', line.characteristic_id ?? '', line.series_id ?? '',
  ])
  const renderRow = (cells: unknown[]) => `<Row>${cells.map((cell) => `<Cell><Data ss:Type="String">${escapeExcelXml(cell)}</Data></Cell>`).join('')}</Row>`
  const xml = `<?xml version="1.0"?>
<?mso-application progid="Excel.Sheet"?>
<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet"
 xmlns:o="urn:schemas-microsoft-com:office:office"
 xmlns:x="urn:schemas-microsoft-com:office:excel"
 xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">
 <Worksheet ss:Name="${escapeExcelXml(worksheetTitle)}"><Table>
 ${renderRow(GOODS_LINE_HEADERS)}${rows.map(renderRow).join('')}
 </Table></Worksheet>
</Workbook>`
  return new Blob([`\ufeff${xml}`], { type: 'application/vnd.ms-excel;charset=utf-8' })
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
