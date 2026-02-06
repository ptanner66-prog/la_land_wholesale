import axios, { AxiosInstance, AxiosError, InternalAxiosRequestConfig } from 'axios'

// Get base URL from localStorage, env var, or use default
// In production (Railway), use relative URLs (empty string) to call same domain
// In development, use localhost:8001
const getBaseUrl = (): string => {
  if (typeof window !== 'undefined') {
    // Check localStorage first (allows runtime override)
    const stored = localStorage.getItem('api_base_url')
    if (stored) return stored

    // Use env var if set
    const envUrl = import.meta.env.VITE_API_BASE_URL
    if (envUrl) return envUrl

    // Default: use relative URLs in production, localhost in dev
    // Relative URLs work when frontend and backend are on same domain (Railway)
    return import.meta.env.DEV ? 'http://127.0.0.1:8001' : ''
  }
  return ''
}

// Create axios instance
const client: AxiosInstance = axios.create({
  baseURL: getBaseUrl(),
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Request interceptor — attach JWT and update base URL
client.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    config.baseURL = getBaseUrl()
    const token = localStorage.getItem('auth_access_token')
    if (token && config.headers) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error: AxiosError) => {
    return Promise.reject(error)
  }
)

// Track if a token refresh is in progress to avoid loops
let isRefreshing = false

// Response interceptor — handle 401 with token refresh
client.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    if (error.response) {
      const status = error.response.status

      // Auto-redirect to /login on 401 (except for auth endpoints)
      if (status === 401 && !error.config?.url?.startsWith('/auth/')) {
        if (!isRefreshing) {
          isRefreshing = true
          try {
            const refreshToken = localStorage.getItem('auth_refresh_token')
            if (refreshToken) {
              const res = await client.post('/auth/refresh', { refresh_token: refreshToken })
              localStorage.setItem('auth_access_token', res.data.access_token)
              localStorage.setItem('auth_refresh_token', res.data.refresh_token)
              isRefreshing = false
              // Retry the original request
              if (error.config) {
                error.config.headers.Authorization = `Bearer ${res.data.access_token}`
                return client(error.config)
              }
            }
          } catch {
            // Refresh failed — clear tokens and redirect
            localStorage.removeItem('auth_access_token')
            localStorage.removeItem('auth_refresh_token')
            isRefreshing = false
            if (window.location.pathname !== '/login') {
              window.location.href = '/login'
            }
          }
        }
      }
    } else if (error.request) {
      console.error('Network error - no response received')
    }

    return Promise.reject(error)
  }
)

// Helper to update base URL
export const setBaseUrl = (url: string): void => {
  localStorage.setItem('api_base_url', url)
}

// Named export for consistency
export const apiClient = client

export default client

