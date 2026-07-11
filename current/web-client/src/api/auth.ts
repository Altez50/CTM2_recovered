import type { ApiResponse } from '../types/api'
import type { UserInfo } from '../types/models'
import { apiRequest } from './client'

interface LoginResponse {
  access_token: string
  token_type: string
  expires_in: number
  user: UserInfo
}

export function login(username: string, password: string) {
  return apiRequest<LoginResponse>('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  })
}

export function logout() {
  return apiRequest<ApiResponse<unknown>>('/api/auth/logout', {
    method: 'POST',
  })
}

export function getCurrentUser() {
  return apiRequest<UserInfo>('/api/auth/me')
}
