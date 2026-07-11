import type { ApiResponse } from '../types/api'
import type { OverdueItem, SettlementBalanceItem, SettlementLedgerItem, SettlementTurnoverRow } from '../types/models'
import { apiRequest } from './client'

function toQuery(params: Record<string, string | number | boolean | undefined>) {
  const query = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== '') {
      query.set(key, String(value))
    }
  })
  const value = query.toString()
  return value ? `?${value}` : ''
}

export function getSettlementsBalance(params: {
  organization_id?: number | null
  counterparty_id?: number | null
  contract_id?: number | null
  object_id?: number | null
  date?: string | null
}) {
  return apiRequest<ApiResponse<SettlementBalanceItem[]>>(`/api/settlements/balance${toQuery(params as Record<string, string | number | boolean | undefined>)}`)
}

export function getSettlementsLedger(params: {
  organization_id: number
  counterparty_id?: number | null
  contract_id?: number | null
  date_from?: string | null
  date_to?: string | null
}) {
  return apiRequest<ApiResponse<SettlementLedgerItem[]>>(`/api/settlements/ledger${toQuery(params as Record<string, string | number | boolean | undefined>)}`)
}

export function getOverdue(params: { date?: string | null }) {
  return apiRequest<ApiResponse<OverdueItem[]>>(`/api/settlements/overdue${toQuery(params as Record<string, string | number | boolean | undefined>)}`)
}

export function getSettlementsTurnover(params: {
  date_from: string
  date_to: string
  organization_id?: number | null
  counterparty_id?: number | null
  contract_id?: number | null
}) {
  return apiRequest<ApiResponse<SettlementTurnoverRow[]>>(`/api/settlements/turnover${toQuery(params as Record<string, string | number | boolean | undefined>)}`)
}
