import { apiRequest } from './client'
import type { ApiResponse } from '../types/api'
import type { GoodsDocument, GoodsLine, StockDimensions } from '../types/models'

export interface ReturnLine extends StockDimensions {
  source_line_id: number
  quantity: number
  name?: string
  sum_with_vat?: number
  inventory_cost?: number
}
export interface ReturnRefund {
  id: number
  return_id: number
  number: string
  date: string
  amount: number
  is_posted: boolean
}
export interface GoodsReturn {
  id: number
  kind: 'customer' | 'supplier'
  source_id: number
  source_number: string
  number: string
  date: string
  organization_name?: string
  counterparty_name?: string
  contract_number?: string
  warehouse_name?: string
  object_name?: string
  description?: string
  sum_with_vat: number
  inventory_cost: number
  is_posted: boolean
  lines: ReturnLine[]
  refunds: ReturnRefund[]
}
export interface ReturnPayload {
  kind: 'customer' | 'supplier'
  source_id: number
  number?: string
  date: string
  description?: string
  lines: ReturnLine[]
}
export const listReturns = (page = 1) => apiRequest<ApiResponse<GoodsReturn[]>>(`/api/goods/returns?page=${page}&page_size=50`)
export const getReturn = (id: number) => apiRequest<ApiResponse<GoodsReturn>>(`/api/goods/returns/${id}`)
export const saveReturn = (payload: ReturnPayload, id?: number) => apiRequest<ApiResponse<GoodsReturn>>(`/api/goods/returns${id ? `/${id}` : ''}`, { method: id ? 'PUT' : 'POST', body: JSON.stringify(payload) })
export const returnAction = (id: number, action: 'post' | 'unpost' | 'delete') => apiRequest<ApiResponse<GoodsReturn>>(`/api/goods/returns/${id}${action === 'delete' ? '' : `/${action}`}`, { method: action === 'delete' ? 'DELETE' : 'POST' })
export const saveRefund = (payload: { return_id: number; date: string; amount: number; number?: string }, id?: number) => apiRequest<ApiResponse<ReturnRefund>>(`/api/goods/return-refunds${id ? `/${id}` : ''}`, { method: id ? 'PUT' : 'POST', body: JSON.stringify(payload) })
export const refundAction = (id: number, action: 'post' | 'unpost' | 'delete') => apiRequest<ApiResponse<ReturnRefund>>(`/api/goods/return-refunds/${id}${action === 'delete' ? '' : `/${action}`}`, { method: action === 'delete' ? 'DELETE' : 'POST' })
export const returnMovements = (id: number) => apiRequest<ApiResponse<unknown>>(`/api/goods/returns/${id}/movements`)
export const getReturnSource = (kind: 'customer' | 'supplier', id: number, excludeId?: number) => apiRequest<ApiResponse<Omit<GoodsDocument, 'lines'> & { lines: (GoodsLine & { returnable_quantity: number })[] }>>(`/api/goods/return-sources/${kind}/${id}${excludeId ? `?exclude_id=${excludeId}` : ''}`)
