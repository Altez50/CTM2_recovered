import { apiRequest } from './client'
import type { ApiResponse } from '../types/api'

export interface AccessUser { id: number; username: string; role: string; is_active: boolean; organization_ids: number[] | null }
export const listUsers = () => apiRequest<ApiResponse<AccessUser[]>>('/api/users')
export const saveAccess = (id: number, role: string, organization_ids: number[] | null) =>
  apiRequest<ApiResponse<AccessUser>>(`/api/users/${id}/access`, { method: 'PUT', body: JSON.stringify({ role, organization_ids }) })
export const createUser = (username: string, password: string, role: string, organization_ids: number[] | null) =>
  apiRequest<ApiResponse<AccessUser>>('/api/users', { method: 'POST', body: JSON.stringify({ username, password, role, organization_ids }) })
