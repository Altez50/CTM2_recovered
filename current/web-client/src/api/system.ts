import type { ApiResponse } from '../types/api'
import type { DashboardSummary } from '../types/models'
import { apiRequest } from './client'

export function fetchDashboardSummary() {
  return apiRequest<ApiResponse<DashboardSummary>>('/api/dashboard/summary')
}
