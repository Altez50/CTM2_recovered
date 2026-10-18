import { apiRequest } from './client'
import type { ApiResponse } from '../types/api'
import type { StockDimensions } from '../types/models'
export interface OpeningInventory extends StockDimensions {
  material_id: number; material_name?: string; warehouse_id: number; warehouse_name?: string
  unit_id: number; unit_name?: string; object_id?: number | null; quantity: number; cost: number
}
export interface OpeningSettlement {
  counterparty_id: number; counterparty_name?: string; contract_id: number; contract_number?: string
  object_id?: number | null; direction: 'payable' | 'receivable'; amount: number
}
export interface OpeningPayload {
  number: string; date: string; organization_id: number; description?: string
  inventory: OpeningInventory[]; settlements: OpeningSettlement[]
}
export interface OpeningBalance extends OpeningPayload { id: number; is_posted: boolean; organization_name?: string }
export const listOpenings = (page = 1) => apiRequest<ApiResponse<OpeningBalance[]>>(`/api/goods/opening-balances?page=${page}`)
export const getOpening = (id: number) => apiRequest<ApiResponse<OpeningBalance>>(`/api/goods/opening-balances/${id}`)
export const saveOpening = (payload: OpeningPayload, id?: number) => apiRequest<ApiResponse<OpeningBalance>>(`/api/goods/opening-balances${id ? `/${id}` : ''}`, { method: id ? 'PUT' : 'POST', body: JSON.stringify(payload) })
export const openingAction = (id: number, action: 'post' | 'unpost' | 'delete') => apiRequest<ApiResponse<OpeningBalance>>(`/api/goods/opening-balances/${id}${action === 'delete' ? '' : '/' + action}`, { method: action === 'delete' ? 'DELETE' : 'POST' })
export const openingMovements = (id: number) => apiRequest<ApiResponse<unknown>>(`/api/goods/opening-balances/${id}/movements`)
export const inventoryTurnover = (params: Record<string, string | number | undefined>) => {
  const query = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) if (value !== undefined && value !== '') query.set(key, String(value))
  return apiRequest<ApiResponse<Record<string, unknown>[]>>(`/api/goods/inventory/turnover?${query}`)
}
