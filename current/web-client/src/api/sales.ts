import { apiRequest } from './client'
import type { ApiResponse } from '../types/api'
import type { GoodsLine } from '../types/models'

export const saleTitles = { orders: 'Заказы клиентов', realizations: 'Реализации', 'expense-orders': 'Расходные ордера', cancellations: 'Отмена остатка заказа клиента' }
export type SaleKind = keyof typeof saleTitles
export const saleSources: Partial<Record<SaleKind, SaleKind>> = { realizations: 'orders', 'expense-orders': 'orders', cancellations: 'orders' }
export interface SaleLine extends GoodsLine {
  id: number; line_type: 'goods' | 'service'; order_line_id: number; source_line_id?: number | null
  shipped_quantity?: number; financial_quantity?: number; cancelled_quantity?: number; open_quantity?: number; reserved_quantity?: number; inventory_cost?: number | null
}
export interface SaleDocument {
  id: number; uuid: string; kind: SaleKind; number: string; date: string; is_posted: boolean; posted_at: string | null
  source_id?: number | null; order_id?: number | null; source_number?: string
  organization_id: number; organization_name?: string; counterparty_id: number; counterparty_name?: string
  contract_id: number; contract_number?: string; warehouse_id?: number | null; warehouse_name?: string
  object_id?: number | null; object_name?: string | null; estimate_id?: number | null; description?: string | null
  issue_mode: 'direct' | 'order'; sum_without_vat: number; vat_amount: number; sum_with_vat: number; lines: SaleLine[]
}
export type SaleOrderLine = GoodsLine & { line_type: 'goods' | 'service' }
export interface SaleBasisLine { source_line_id: number; quantity: number }
export interface SaleRevenue { id: number; period: string; name: string; contract_id: number; revenue_amount: number; vat_amount: number }
export interface SaleMovements {
  inventory: { line_number: number; quantity_income: number; quantity_expense: number; sum_income: number; sum_expense: number }[]
  settlements: { line_number: number; accrual_amount: number }[]
  reservations: { line_number: number; reserve_income: number; reserve_expense: number }[]
  revenue: SaleRevenue[]
}
export const listSales = (kind: SaleKind, page = 1) => apiRequest<ApiResponse<SaleDocument[]>>(`/api/sales/${kind}?page=${page}&page_size=100`)
export const getSale = (kind: SaleKind, id: number) => apiRequest<ApiResponse<SaleDocument>>(`/api/sales/${kind}/${id}`)
export const saveSale = (kind: SaleKind, payload: unknown, id?: number) => apiRequest<ApiResponse<SaleDocument>>(`/api/sales/${kind}${id ? '/'+id : ''}`, { method: id ? 'PUT' : 'POST', body: JSON.stringify(payload) })
export const changeSale = (kind: SaleKind, id: number, action: 'post' | 'unpost' | 'delete') => apiRequest<ApiResponse<SaleDocument>>(`/api/sales/${kind}/${id}${action === 'delete' ? '' : '/'+action}`, { method: action === 'delete' ? 'DELETE' : 'POST' })
export const saleMovements = (kind: SaleKind, id: number) => apiRequest<ApiResponse<SaleMovements>>(`/api/sales/${kind}/${id}/movements`)
export const salesRevenue = () => apiRequest<ApiResponse<SaleRevenue[]>>('/api/sales/revenue')
