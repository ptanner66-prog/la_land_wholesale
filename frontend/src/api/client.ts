import axios, { AxiosInstance, AxiosError, InternalAxiosRequestConfig } from 'axios'

// Get base URL from localStorage, env var, or use default
// Default port is 8001 to match the FastAPI server
const getBaseUrl = (): string => {
  if (typeof window !== 'undefined') {
    return localStorage.getItem('api_base_url') || 
           import.meta.env.VITE_API_BASE_URL || 
           'http://127.0.0.1:8001'
  }
  return 'http://127.0.0.1:8001'
}

// Create axios instance
const client: AxiosInstance = axios.create({
  baseURL: getBaseUrl(),
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Request interceptor
client.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    // Update base URL in case it changed
    config.baseURL = getBaseUrl()
    return config
  },
  (error: AxiosError) => {
    return Promise.reject(error)
  }
)

// Response interceptor
client.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    // Handle common errors
    if (error.response) {
      const status = error.response.status
      const data = error.response.data as Record<string, unknown>
      
      switch (status) {
        case 401:
          console.error('Unauthorized')
          break
        case 403:
          console.error('Forbidden')
          break
        case 404:
          console.error('Not found')
          break
        case 422:
          console.error('Validation error:', data)
          break
        case 500:
          console.error('Server error:', data)
          break
        case 503:
          console.error('Service unavailable:', data)
          break
      }
    } else if (error.request) {
      console.error('Network error - no response received')
    } else {
      console.error('Request error:', error.message)
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

