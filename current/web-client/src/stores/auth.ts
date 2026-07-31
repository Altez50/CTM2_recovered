import { defineStore } from 'pinia'
import { getCurrentUser, login as loginRequest, logout as logoutRequest } from '../api/auth'
import { useWorkspaceStore } from './workspace'
import type { UserInfo } from '../types/models'

interface AuthState {
  token: string | null
  user: UserInfo | null
  initialized: boolean
}

export const useAuthStore = defineStore('auth', {
  state: (): AuthState => ({
    token: localStorage.getItem('ctm.token'),
    user: null,
    initialized: false,
  }),
  getters: {
    isAuthenticated: (state) => Boolean(state.token && state.user),
    isAdmin: (state) => state.user?.role === 'admin',
    // Matches the backend AdminOrManager guard used for posting / calculation / distribution.
    canManageCost: (state) => state.user?.role === 'admin' || state.user?.role === 'manager',
    displayName: (state) => state.user?.full_name || state.user?.username || 'Пользователь',
  },
  actions: {
    async initialize() {
      if (this.initialized) {
        return
      }
      if (!this.token) {
        this.initialized = true
        return
      }
      try {
        this.user = await getCurrentUser()
      } catch {
        this.token = null
        this.user = null
        localStorage.removeItem('ctm.token')
      } finally {
        this.initialized = true
      }
    },
    async login(username: string, password: string) {
      const response = await loginRequest(username, password)
      this.token = response.access_token
      this.user = response.user
      this.initialized = true
      localStorage.setItem('ctm.token', response.access_token)
    },
    async logout() {
      try {
        if (this.token) {
          await logoutRequest()
        }
      } finally {
        this.token = null
        this.user = null
        localStorage.removeItem('ctm.token')
        // Сбрасываем открытые вкладки при выходе.
        useWorkspaceStore().reset()
      }
    },
  },
})
