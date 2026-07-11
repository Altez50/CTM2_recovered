import type { ApiResponse } from '../types/api'
import type {
  CashflowDayItem,
  PaymentRegisterResponse,
  PaymentSchedule,
  PaymentScheduleLine,
  PaymentTransaction,
} from '../types/models'
import { apiRequest } from './client'

interface ListParams {
  page?: number
  page_size?: number
  search?: string
  [key: string]: string | number | boolean | undefined
}

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

// --- Schedules ---

export function listPaymentSchedules(params: ListParams = {}) {
  return apiRequest<ApiResponse<PaymentSchedule[]>>(`/api/payments/schedules${toQuery(params)}`)
}

export function getPaymentSchedule(id: number) {
  return apiRequest<ApiResponse<PaymentSchedule>>(`/api/payments/schedules/${id}`)
}

export function createPaymentSchedule(payload: Partial<PaymentSchedule>) {
  return apiRequest<ApiResponse<PaymentSchedule>>('/api/payments/schedules', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function updatePaymentSchedule(id: number, payload: Partial<PaymentSchedule>) {
  return apiRequest<ApiResponse<PaymentSchedule>>(`/api/payments/schedules/${id}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  })
}

export function deletePaymentSchedule(id: number) {
  return apiRequest<ApiResponse<unknown>>(`/api/payments/schedules/${id}`, { method: 'DELETE' })
}

export function postPaymentSchedule(id: number) {
  return apiRequest<ApiResponse<unknown>>(`/api/payments/schedules/${id}/post`, { method: 'POST' })
}

export function unpostPaymentSchedule(id: number) {
  return apiRequest<ApiResponse<unknown>>(`/api/payments/schedules/${id}/unpost`, { method: 'POST' })
}

// --- Suggest previews ---

export function previewIncoming(data: { date_from: string; date_to: string; object_id?: number | null; contract_id?: number | null }) {
  return apiRequest<ApiResponse<PaymentScheduleLine[]>>('/api/payments/schedules/preview/incoming', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export function previewPayroll(data: { date_from: string; date_to: string; object_id?: number | null; estimate_id?: number | null }) {
  return apiRequest<ApiResponse<PaymentScheduleLine[]>>('/api/payments/schedules/preview/payroll', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

// --- Suggest previews from the ТМЦ subsystem (supplier / customer invoices) ---

export function previewGoodsReceiptSuggestions(data: { date_from: string; date_to: string; organization_id?: number | null; object_id?: number | null }) {
  return apiRequest<ApiResponse<PaymentScheduleLine[]>>('/api/payments/schedules/preview/goods-receipts', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export function previewGoodsIssueSuggestions(data: { date_from: string; date_to: string; organization_id?: number | null; object_id?: number | null }) {
  return apiRequest<ApiResponse<PaymentScheduleLine[]>>('/api/payments/schedules/preview/goods-issues', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

// --- Transactions ---

export function listPaymentTransactions(params: ListParams = {}) {
  return apiRequest<ApiResponse<PaymentTransaction[]>>(`/api/payments/transactions${toQuery(params)}`)
}

export function getPaymentTransaction(id: number) {
  return apiRequest<ApiResponse<PaymentTransaction>>(`/api/payments/transactions/${id}`)
}

export function createPaymentTransaction(payload: Partial<PaymentTransaction>) {
  return apiRequest<ApiResponse<PaymentTransaction>>('/api/payments/transactions', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function updatePaymentTransaction(id: number, payload: Partial<PaymentTransaction>) {
  return apiRequest<ApiResponse<PaymentTransaction>>(`/api/payments/transactions/${id}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  })
}

export function deletePaymentTransaction(id: number) {
  return apiRequest<ApiResponse<unknown>>(`/api/payments/transactions/${id}`, { method: 'DELETE' })
}

export function postPaymentTransaction(id: number) {
  return apiRequest<ApiResponse<unknown>>(`/api/payments/transactions/${id}/post`, { method: 'POST' })
}

export function unpostPaymentTransaction(id: number) {
  return apiRequest<ApiResponse<unknown>>(`/api/payments/transactions/${id}/unpost`, { method: 'POST' })
}

// --- Register + Cashflow ---

export interface RegisterQuery {
  page?: number
  page_size?: number
  period_from?: string
  period_to?: string
  object_id?: number | ''
  counterparty_id?: number | ''
  contract_id?: number | ''
  direction?: string
  category?: string
  group_by?: string
}

export function queryPaymentRegister(params: RegisterQuery) {
  return apiRequest<ApiResponse<PaymentRegisterResponse>>(`/api/payments/register${toQuery(params as Record<string, string | number | boolean | undefined>)}`)
}

export function queryCashflow(params: { date_from: string; date_to: string; object_id?: number | null; counterparty_id?: number | null }) {
  return apiRequest<ApiResponse<CashflowDayItem[]>>(`/api/payments/cashflow${toQuery(params as Record<string, string | number | boolean | undefined>)}`)
}
