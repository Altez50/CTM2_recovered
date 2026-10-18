import { apiRequest } from './client'
import type { ApiResponse } from '../types/api'
import type { GoodsLine, GoodsLineInput } from '../types/models'

export const purchaseTitles = {
  orders: 'Заказы поставщикам', acquisitions: 'Приобретения', 'receipt-orders': 'Приходные ордера',
  cancellations: 'Отмена остатка заказа', discrepancies: 'Акты расхождений', 'quantity-adjustments': 'Корректировки количества',
}
export type PurchaseKind = keyof typeof purchaseTitles
export const purchaseSources: Partial<Record<PurchaseKind, PurchaseKind>> = {
  acquisitions: 'orders', 'receipt-orders': 'orders', cancellations: 'orders',
  discrepancies: 'acquisitions', 'quantity-adjustments': 'discrepancies',
}
export interface PurchaseLine extends GoodsLine {
  id: number
  line_type: 'goods' | 'service'
  order_line_id: number
  source_line_id?: number | null
  receipt_line_id?: number | null
  open_quantity?: number
  received_quantity?: number
  financial_quantity?: number
  cancelled_quantity?: number
  shortage_quantity?: number
}
export interface PurchaseDocument {
  id: number; uuid: string; kind: PurchaseKind; number: string; date: string
  is_posted: boolean; posted_at: string | null
  source_id?: number | null; source_number?: string; order_id?: number | null
  organization_id: number; organization_name?: string; counterparty_id: number; counterparty_name?: string
  contract_id: number; contract_number?: string; warehouse_id?: number | null; warehouse_name?: string
  object_id?: number | null; object_name?: string | null; estimate_id?: number | null; description?: string | null
  receipt_mode: 'direct' | 'order'; sum_without_vat: number; vat_amount: number; sum_with_vat: number
  lines: PurchaseLine[]
}
export type PurchaseOrderLine = GoodsLine & { line_type: 'goods' | 'service' }
export interface PurchaseBasisLine { source_line_id: number; quantity: number; receipt_line_id?: number | null }
export interface PurchaseExpense { id: number; period: string; name: string; contract_id: number; expense_amount: number; vat_amount: number }
export interface PurchaseMovements {
  inventory: { line_number: number; quantity_income: number; quantity_expense: number; sum_income: number; sum_expense: number }[]
  settlements: { line_number: number; accrual_amount: number; payment_amount: number }[]
  expenses: PurchaseExpense[]
}
export const listPurchases = (kind: PurchaseKind, page = 1) => apiRequest<ApiResponse<PurchaseDocument[]>>(`/api/purchases/${kind}?page=${page}&page_size=100`)
export const getPurchase = (kind: PurchaseKind, id: number) => apiRequest<ApiResponse<PurchaseDocument>>(`/api/purchases/${kind}/${id}`)
export const savePurchase = (kind: PurchaseKind, payload: unknown, id?: number) => apiRequest<ApiResponse<PurchaseDocument>>(`/api/purchases/${kind}${id ? '/'+id : ''}`, { method: id ? 'PUT' : 'POST', body: JSON.stringify(payload) })
export const changePurchase = (kind: PurchaseKind, id: number, action: 'post' | 'unpost' | 'delete') => apiRequest<ApiResponse<PurchaseDocument>>(`/api/purchases/${kind}/${id}${action === 'delete' ? '' : '/'+action}`, { method: action === 'delete' ? 'DELETE' : 'POST' })
export const purchaseMovements = (kind: PurchaseKind, id: number) => apiRequest<ApiResponse<PurchaseMovements>>(`/api/purchases/${kind}/${id}/movements`)
export const purchaseExpenses = () => apiRequest<ApiResponse<PurchaseExpense[]>>('/api/purchases/expenses')
