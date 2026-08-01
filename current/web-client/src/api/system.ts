import { apiRequest } from './client'
import type { ApiResponse } from '../types/api'
import type { DashboardSummary } from '../types/models'

export function fetchDashboardSummary() {
  return apiRequest<ApiResponse<DashboardSummary>>('/api/dashboard/summary')
}

/**
 * Пользовательские настройки формы (состав колонок, сортировка).
 * См. DOCUMENT_LIST_SPEC.md, раздел 4.3. Значения — строковый JSON.
 */

export function getUserSettings(formName: string) {
  return apiRequest<ApiResponse<Record<string, string>>>(`/api/system/user-settings/${encodeURIComponent(formName)}`)
}

export function putUserSettings(formName: string, payload: Record<string, unknown>) {
  return apiRequest<ApiResponse<Record<string, string>>>(
    `/api/system/user-settings/${encodeURIComponent(formName)}`,
    { method: 'PUT', body: JSON.stringify(payload) },
  )
}

export function deleteUserSetting(formName: string, settingKey: string) {
  return apiRequest<ApiResponse<null>>(
    `/api/system/user-settings/${encodeURIComponent(formName)}/${encodeURIComponent(settingKey)}`,
    { method: 'DELETE' },
  )
}
