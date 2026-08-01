/**
 * Предзаполнение формы документа-результата по документу-основанию
 * (DOCUMENT_LIST_SPEC.md, раздел 3.6.3 «Ввод на основании»).
 *
 * useDocumentList.openBaseOn() navigates to a create-route with the query
 * params `based_on_type` / `based_on_id` / `based_on_number`. This composable
 * reads those params, loads the source document and returns a normalized set of
 * common requisites that the target form applies to its header. Per the spec,
 * only header requisites are transferred; tabular parts are out of scope (О6).
 */
import { useRoute } from 'vue-router'
import { getEstimate, getDailyReport, getTimesheet } from '../api/documents'
import {
  getMaterialConsumption,
  getMachineryUsageReport,
  getSubcontractAcceptance,
  getOverheadExpense,
} from '../api/costAccounting'
import { getGoodsDocument } from '../api/goods'
import { getPaymentSchedule } from '../api/payments'

/** Метаданные документа-основания для сохранения в БД (раздел 4.4). */
export interface BasedOnMeta {
  based_on_type: string
  based_on_id: number
  based_on_number: string
}

/** Нормализованные общие реквизиты источника (раздел 3.6.3). */
export interface BasedOnSource {
  type: string
  id: number
  number: string
  object_id?: number | null
  object_name?: string | null
  estimate_id?: number | null
  estimate_number?: string | null
  organization_id?: number | null
  organization_name?: string | null
  counterparty_id?: number | null
  counterparty_name?: string | null
  contract_id?: number | null
  contract_number?: string | null
  responsible_id?: number | null
  responsible_name?: string | null
  foreman_id?: number | null
  foreman_name?: string | null
  sum?: number | null
}

export interface BasedOnResult {
  source: BasedOnSource
  meta: BasedOnMeta
}

function readBasedOnQuery(route: ReturnType<typeof useRoute>): BasedOnMeta | null {
  const type = route.query.based_on_type
  const id = route.query.based_on_id
  const number = route.query.based_on_number
  if (!type || !id) return null
  const numericId = Number(id)
  if (!Number.isFinite(numericId) || numericId <= 0) return null
  return {
    based_on_type: String(type),
    based_on_id: numericId,
    based_on_number: number ? String(number) : '',
  }
}

/** Загрузка источника по его doc_kind и нормализация общих реквизитов. */
async function loadSourceDocument(type: string, id: number): Promise<BasedOnSource | null> {
  try {
    switch (type) {
      case 'estimates': {
        const { data: d } = await getEstimate(id)
        return {
          type,
          id,
          number: d.number,
          object_id: d.object_id ?? null,
          object_name: d.object_name ?? null,
          estimate_id: id,
          estimate_number: d.number,
          contract_id: d.contract_id ?? null,
          contract_number: d.contract_number ?? null,
          responsible_id: d.responsible_id ?? null,
          responsible_name: d.responsible_name ?? null,
          sum: d.total_sum ?? null,
        }
      }
      case 'daily-reports': {
        const { data: d } = await getDailyReport(id)
        return {
          type,
          id,
          number: d.number,
          estimate_id: d.estimate_id ?? null,
          estimate_number: d.estimate_number ?? null,
          foreman_id: d.foreman_id ?? null,
          foreman_name: d.foreman_name ?? null,
        }
      }
      case 'timesheets': {
        const { data: d } = await getTimesheet(id)
        return {
          type,
          id,
          number: d.number,
          object_id: d.object_id ?? null,
          object_name: d.object_name ?? null,
          estimate_id: d.estimate_id ?? null,
          estimate_number: d.estimate_number ?? null,
          foreman_id: d.foreman_id ?? null,
          foreman_name: d.foreman_name ?? null,
          sum: d.total_amount ?? null,
        }
      }
      case 'material-consumptions': {
        const { data: d } = await getMaterialConsumption(id)
        return {
          type,
          id,
          number: d.number,
          object_id: d.object_id ?? null,
          object_name: d.object_name ?? null,
          estimate_id: d.estimate_id ?? null,
          estimate_number: d.estimate_number ?? null,
          foreman_id: d.foreman_id ?? null,
          foreman_name: d.foreman_name ?? null,
        }
      }
      case 'machinery-usage': {
        const { data: d } = await getMachineryUsageReport(id)
        return {
          type,
          id,
          number: d.number,
          object_id: d.object_id ?? null,
          object_name: d.object_name ?? null,
          estimate_id: d.estimate_id ?? null,
          estimate_number: d.estimate_number ?? null,
          foreman_id: d.foreman_id ?? null,
          foreman_name: d.foreman_name ?? null,
        }
      }
      case 'subcontract-acceptances': {
        const { data: d } = await getSubcontractAcceptance(id)
        return {
          type,
          id,
          number: d.number,
          object_id: d.object_id ?? null,
          object_name: d.object_name ?? null,
          estimate_id: d.estimate_id ?? null,
          estimate_number: d.estimate_number ?? null,
        }
      }
      case 'overhead-expenses': {
        const { data: d } = await getOverheadExpense(id)
        return {
          type,
          id,
          number: d.number,
          sum: (d.lines ?? []).reduce((acc, l) => acc + (l.sum || 0), 0) || null,
        }
      }
      case 'goods-receipts': {
        const { data: d } = await getGoodsDocument('receipt', id)
        return {
          type,
          id,
          number: d.number,
          organization_id: d.organization_id ?? null,
          organization_name: d.organization_name ?? null,
          counterparty_id: d.counterparty_id ?? null,
          counterparty_name: d.counterparty_name ?? null,
          contract_id: d.contract_id ?? null,
          contract_number: d.contract_number ?? null,
          object_id: d.object_id ?? null,
          object_name: d.object_name ?? null,
          sum: d.sum_with_vat ?? null,
        }
      }
      case 'goods-issues': {
        const { data: d } = await getGoodsDocument('issue', id)
        return {
          type,
          id,
          number: d.number,
          organization_id: d.organization_id ?? null,
          organization_name: d.organization_name ?? null,
          counterparty_id: d.counterparty_id ?? null,
          counterparty_name: d.counterparty_name ?? null,
          contract_id: d.contract_id ?? null,
          contract_number: d.contract_number ?? null,
          object_id: d.object_id ?? null,
          object_name: d.object_name ?? null,
          sum: d.sum_with_vat ?? null,
        }
      }
      case 'payment-schedules': {
        const { data: d } = await getPaymentSchedule(id)
        return {
          type,
          id,
          number: d.number,
          object_id: d.object_id ?? null,
          object_name: d.object_name ?? null,
          contract_id: d.contract_id ?? null,
          contract_number: d.contract_number ?? null,
          responsible_id: d.responsible_id ?? null,
          responsible_name: d.responsible_name ?? null,
        }
      }
      default:
        return null
    }
  } catch {
    // Источник недоступен — prefill тихо пропускается.
    return null
  }
}

/**
 * Читает query-параметры «ввода на основании» и (опционально) загружает источник.
 * Возвращает `hasBasedOn`, чтобы форма могла решить, выполнять ли prefill
 * (только при создании нового документа, не при редактировании).
 */
export function useBasedOnPrefill() {
  const route = useRoute()
  const meta = readBasedOnQuery(route)

  async function loadSource(): Promise<BasedOnResult | null> {
    if (!meta) return null
    const source = await loadSourceDocument(meta.based_on_type, meta.based_on_id)
    if (!source) return null
    return { source, meta }
  }

  return {
    hasBasedOn: meta !== null,
    meta,
    loadSource,
  }
}
