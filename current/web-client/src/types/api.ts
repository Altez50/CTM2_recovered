export interface Pagination {
  page: number
  page_size: number
  total: number
  pages: number
}

export interface ApiResponse<T> {
  success: boolean
  data: T
  message?: string | null
  pagination?: Pagination | null
}

export class ApiError extends Error {
  status: number
  details: unknown

  constructor(message: string, status: number, details: unknown = null) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.details = details
  }
}
