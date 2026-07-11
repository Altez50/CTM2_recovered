import type { ApiResponse } from '../types/api'
import type {
  ComponentType,
  ImportPreview,
  MissingImportedMaterial,
  ImportMaterialCreateResult,
  MaterialRecord,
  UnitRecord,
  WorkCorrectionImportResult,
  WorkDetail,
  WorkRecord,
  WorkSpecificationRecord,
} from '../types/models'
import { apiRequest, downloadRequest } from './client'

export interface MaterialListParams extends Record<string, string | number | undefined | null> {
  page?: number
  page_size?: number
  search?: string
}

function toQuery(params: Record<string, string | number | undefined | null>) {
  const query = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      query.set(key, String(value))
    }
  })
  const value = query.toString()
  return value ? `?${value}` : ''
}

export function listUnits(search = '') {
  return apiRequest<ApiResponse<UnitRecord[]>>(`/api/units${toQuery({ search })}`)
}

export function listMaterials(params: MaterialListParams = {}) {
  return apiRequest<ApiResponse<MaterialRecord[]>>(`/api/materials${toQuery(params)}`)
}

export function updateMaterial(id: number, payload: Partial<MaterialRecord>) {
  return apiRequest<ApiResponse<MaterialRecord>>(`/api/materials/${id}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  })
}

export function deleteMaterial(id: number) {
  return apiRequest<ApiResponse<unknown>>(`/api/materials/${id}`, {
    method: 'DELETE',
  })
}

export function getWork(id: number) {
  return apiRequest<ApiResponse<WorkDetail>>(`/api/works/${id}`)
}

export function createWork(payload: Omit<WorkDetail, 'id'> | Record<string, unknown>) {
  return apiRequest<ApiResponse<WorkDetail>>('/api/works', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function updateWork(id: number, payload: Omit<WorkDetail, 'id'> | Record<string, unknown>) {
  return apiRequest<ApiResponse<WorkDetail>>(`/api/works/${id}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  })
}

export function deleteWork(id: number) {
  return apiRequest<ApiResponse<unknown>>(`/api/works/${id}`, {
    method: 'DELETE',
  })
}

export function previewCopySpecifications(targetWorkId: number, sourceWorkId: number) {
  return apiRequest<ApiResponse<{ target_work_id: number; source_work_id: number; rows: WorkSpecificationRecord[] }>>(
    `/api/works/${targetWorkId}/specifications/copy-from/${sourceWorkId}`,
    {
      method: 'POST',
    },
  )
}

export function previewSpecificationImport(workId: number, file: File) {
  const formData = new FormData()
  formData.append('file', file)
  return apiRequest<ApiResponse<ImportPreview>>(`/api/works/${workId}/specifications/import`, {
    method: 'POST',
    body: formData,
  })
}

export function createImportMaterials(workId: number, materials: MissingImportedMaterial[]) {
  return apiRequest<
    ApiResponse<{
      created_count: number
      reused_count: number
      materials: ImportMaterialCreateResult[]
    }>
  >(`/api/works/${workId}/specifications/import/materials`, {
    method: 'POST',
    body: JSON.stringify({ materials }),
  })
}

export function exportSpecifications(workId: number) {
  return downloadRequest(`/api/works/${workId}/specifications/export`)
}

export function exportFlaggedSpecifications(reviewStatus: 'incorrect' | 'corrected' | 'ok' = 'incorrect') {
  return downloadRequest(`/api/works/specifications/export-flagged${toQuery({ review_status: reviewStatus })}`)
}

export function importSpecificationCorrections(file: File) {
  const formData = new FormData()
  formData.append('file', file)
  return apiRequest<ApiResponse<WorkCorrectionImportResult>>('/api/works/specifications/import-corrections', {
    method: 'POST',
    body: formData,
  })
}

function escapeXml(value: string) {
  return value
    .split('&').join('&amp;')
    .split('<').join('&lt;')
    .split('>').join('&gt;')
    .split('"').join('&quot;')
    .split("'").join('&apos;')
}

function spreadsheetRow(values: Array<string | number>) {
  return `<Row>${values
    .map((value) => `<Cell><Data ss:Type="String">${escapeXml(String(value))}</Data></Cell>`)
    .join('')}</Row>`
}

export function buildWorkSpecificationExport(
  work: Pick<WorkRecord, 'name' | 'code' | 'unit'>,
  specifications: WorkSpecificationRecord[],
) {
  const componentTypes: ComponentType[] = ['Material', 'Labor', 'Equipment', 'Other']
  const total = specifications.reduce((sum, row) => sum + Number(row.total_cost || 0), 0)
  const totalsByType = componentTypes.map((type) => ({
    type,
    total: specifications
      .filter((row) => row.component_type === type)
      .reduce((sum, row) => sum + Number(row.total_cost || 0), 0),
  }))

  const rows = [
    spreadsheetRow(['Карточка работы', work.name, '', '', '', '']),
    spreadsheetRow(['Код работы', work.code ?? '', '', '', '', '']),
    spreadsheetRow(['Единица работы', work.unit ?? '', '', '', '', '']),
    spreadsheetRow(['Итоговая стоимость', '', '', '', '', total.toFixed(2)]),
    spreadsheetRow(['', '', '', '', '', '']),
    spreadsheetRow(['Тип', 'Наименование', 'Ед. изм.', 'Норма', 'Цена', 'Сумма']),
    ...specifications.map((row) =>
      spreadsheetRow([
        row.component_type,
        row.component_name,
        row.unit_name ?? '',
        Number(row.consumption_rate || 0).toString(),
        Number(row.unit_price || 0).toFixed(2),
        Number(row.total_cost || 0).toFixed(2),
      ]),
    ),
    spreadsheetRow(['', '', '', '', '', '']),
    spreadsheetRow(['Подитоги по типам', '', '', '', '', '']),
    ...totalsByType.map((item) => spreadsheetRow([item.type, '', '', '', '', item.total.toFixed(2)])),
    spreadsheetRow(['Итого', '', '', '', '', total.toFixed(2)]),
  ]

  const xml = `<?xml version="1.0" encoding="UTF-8"?>
<?mso-application progid="Excel.Sheet"?>
<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet"
 xmlns:o="urn:schemas-microsoft-com:office:office"
 xmlns:x="urn:schemas-microsoft-com:office:excel"
 xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">
  <Worksheet ss:Name="Спецификация">
    <Table>
      ${rows.join('')}
    </Table>
  </Worksheet>
</Workbook>`

  return new Blob([xml], {
    type: 'application/vnd.ms-excel;charset=utf-8',
  })
}

export function cloneSpecificationRow(row: WorkSpecificationRecord): WorkSpecificationRecord {
  return {
    component_type: row.component_type,
    component_name: row.component_name,
    unit_id: row.unit_id ?? null,
    unit_name: row.unit_name ?? null,
    consumption_rate: row.consumption_rate,
    unit_price: row.unit_price,
    total_cost: row.total_cost,
    material_id: row.material_id ?? null,
  }
}

export function createEmptySpecificationRow(): WorkSpecificationRecord {
  return {
    component_type: 'Material',
    component_name: '',
    unit_id: null,
    unit_name: '',
    consumption_rate: 1,
    unit_price: 0,
    total_cost: 0,
    material_id: null,
  }
}

export function toWorkPayload(work: WorkRecord, specifications: WorkSpecificationRecord[]) {
  return {
    name: work.name,
    code: work.code ?? null,
    unit: work.unit ?? null,
    price: work.price,
    labor_rate: work.labor_rate,
    specification_review_status: work.specification_review_status ?? 'ok',
    specification_review_note: work.specification_review_note ?? null,
    parent_id: work.parent_id ?? null,
    marked_for_deletion: work.marked_for_deletion,
    is_group: work.is_group,
    specifications: specifications.map((row) => ({
      id: row.id,
      component_type: row.component_type,
      component_name: row.component_name,
      unit_id: row.unit_id ?? null,
      unit_name: row.unit_name ?? null,
      consumption_rate: row.consumption_rate,
      unit_price: row.unit_price,
      material_id: row.material_id ?? null,
    })),
  }
}
