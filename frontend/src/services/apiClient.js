import axios from 'axios'

function getBaseUrl() {
  const envUrl = import.meta.env.VITE_API_BASE_URL
  if (typeof window !== 'undefined' && window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1') {
    if (!envUrl || envUrl.includes('localhost') || envUrl.includes('127.0.0.1')) {
      return '/api/v1'
    }
  }
  return envUrl || '/api/v1'
}

const API_BASE_URL = getBaseUrl()

let accessToken = localStorage.getItem('ar_access_token') || null
let refreshToken = localStorage.getItem('ar_refresh_token') || null
let logoutHandler = null

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
})

export function setTokens(access, refresh) {
  accessToken = access
  if (access) {
    localStorage.setItem('ar_access_token', access)
  } else {
    localStorage.removeItem('ar_access_token')
  }

  refreshToken = refresh
  if (refresh) {
    localStorage.setItem('ar_refresh_token', refresh)
  } else {
    localStorage.removeItem('ar_refresh_token')
  }
}

export function getAccessToken() {
  return accessToken
}

export function getRefreshToken() {
  return refreshToken
}

export function clearTokens() {
  accessToken = null
  refreshToken = null
  localStorage.removeItem('ar_access_token')
  localStorage.removeItem('ar_refresh_token')
  localStorage.removeItem('ar_user')
}

export function registerLogoutHandler(handler) {
  logoutHandler = handler
}

// Request Interceptor: Attach Bearer token
apiClient.interceptors.request.use(
  (config) => {
    if (accessToken && !config.headers.Authorization) {
      config.headers.Authorization = `Bearer ${accessToken}`
    }
    return config
  },
  (error) => Promise.reject(error)
)

// Response Interceptor: Automatic token refresh on 401
let isRefreshing = false
let failedQueue = []

const processQueue = (error, token = null) => {
  failedQueue.forEach((prom) => {
    if (error) {
      prom.reject(error)
    } else {
      prom.resolve(token)
    }
  })
  failedQueue = []
}

apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config

    if (
      error.response &&
      error.response.status === 401 &&
      !originalRequest._retry &&
      !originalRequest.url.includes('/auth/login') &&
      !originalRequest.url.includes('/auth/register') &&
      !originalRequest.url.includes('/auth/refresh')
    ) {
      if (isRefreshing) {
        return new Promise((resolve, reject) => {
          failedQueue.push({ resolve, reject })
        })
          .then((token) => {
            originalRequest.headers.Authorization = `Bearer ${token}`
            return apiClient(originalRequest)
          })
          .catch((err) => Promise.reject(err))
      }

      originalRequest._retry = true
      isRefreshing = true

      const currentRefresh = getRefreshToken()
      if (!currentRefresh) {
        clearTokens()
        if (logoutHandler) logoutHandler()
        return Promise.reject(error)
      }

      try {
        const response = await axios.post(`${API_BASE_URL}/auth/refresh`, {
          refresh_token: currentRefresh,
        })

        const { access_token, refresh_token: newRefresh } = response.data
        setTokens(access_token, newRefresh)
        processQueue(null, access_token)

        originalRequest.headers.Authorization = `Bearer ${access_token}`
        return apiClient(originalRequest)
      } catch (refreshErr) {
        processQueue(refreshErr, null)
        clearTokens()
        if (logoutHandler) logoutHandler()
        return Promise.reject(refreshErr)
      } finally {
        isRefreshing = false
      }
    }

    return Promise.reject(error)
  }
)
