import { apiRequest } from './client'
import type { ApiResponse } from '../types/api'
import type { GoodsDocument, GoodsLine, StockDimensions } from '../types/models'

export type PriceAdjustmentKind = 'sale' | 'purchase'
export interface PriceAdjustmentLine extends StockDimensions {
  source_line_id: number
  name: string
  quantity: number
  old_price: number
  new_price: number
  vat_rate: number
  delta_without_vat: number
  delta_vat: number
  delta_with_vat: number
}
export interface PriceAdjustment {
  id: number
  kind: PriceAdjustmentKind
  source_id: number
  source_number: string
  number: string
  date: string
  description?: string
  organization_name?: string
  counterparty_name?: string
  contract_number?: string
  warehouse_name?: string
  object_name?: string
  delta_without_vat: number
  delta_vat: number
  delta_with_vat: number
  is_posted: boolean
  lines: PriceAdjustmentLine[]
}
export interface PriceAdjustmentPayload {
  kind: PriceAdjustmentKind
  source_id: number
  date: string
  number: string
  description?: string
  lines: { source_line_id: number; new_price: number }[]
}
export const listPriceAdjustments = (page = 1) => apiRequest<ApiResponse<PriceAdjustment[]>>(`/api/goods/price-adjustments?page=${page}&page_size=50`)
export const getPriceAdjustment = (id: number) => apiRequest<ApiResponse<PriceAdjustment>>(`/api/goods/price-adjustments/${id}`)
export const getPriceAdjustmentSource = (kind: PriceAdjustmentKind, id: number, excludeId?: number) => apiRequest<ApiResponse<Omit<GoodsDocument, 'lines'> & { lines: (GoodsLine & { effective_price: number })[] }>>(`/api/goods/price-adjustment-sources/${kind}/${id}${excludeId ? `?exclude_id=${excludeId}` : ''}`)
export const savePriceAdjustment = (payload: PriceAdjustmentPayload, id?: number) => apiRequest<ApiResponse<PriceAdjustment>>(`/api/goods/price-adjustments${id ? `/${id}` : ''}`, { method: id ? 'PUT' : 'POST', body: JSON.stringify(payload) })
export const priceAdjustmentAction = (id: number, action: 'post' | 'unpost' | 'delete') => apiRequest<ApiResponse<PriceAdjustment>>(`/api/goods/price-adjustments/${id}${action === 'delete' ? '' : `/${action}`}`, { method: action === 'delete' ? 'DELETE' : 'POST' })
export const priceAdjustmentMovements = (id: number) => apiRequest<ApiResponse<unknown>>(`/api/goods/price-adjustments/${id}/movements`)
