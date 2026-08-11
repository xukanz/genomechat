/**
 * Authentication API service
 * Handles all auth-related backend communication
 */

import type {
  User,
  RegisterRequest,
  TokenResponse,
  RefreshTokenRequest,
  LogoutResponse,
  UpdateProfileRequest,
} from '@/types/auth'

// API base URL priority:
// 1. Runtime injection via window.__API_URL__ (set by inject-config.js from Vault Secrets)
// 2. Build-time via import.meta.env.VITE_API_URL
// 3. Default to localhost for development
declare global {
  interface Window {
    __API_URL__?: string
  }
}

const API_BASE_URL =
  (typeof window !== 'undefined' && window.__API_URL__) ||
  import.meta.env.VITE_API_URL ||
  'http://localhost:8000'

/**
 * Handle API response errors
 */
async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    // Try to get error detail from response
    try {
      const error = await response.json()
      throw new Error(error.detail || `Request failed with status ${response.status}`)
    } catch (e) {
      if (e instanceof Error && e.message.includes('detail')) {
        throw e
      }
      throw new Error(`Request failed with status ${response.status}`)
    }
  }

  return response.json()
}

/**
 * Login user with email and password
 * Uses OAuth2 password flow (form-urlencoded)
 */
export async function loginUser(email: string, password: string): Promise<TokenResponse> {
  // OAuth2 password flow expects form-urlencoded data with 'username' field
  const formData = new URLSearchParams()
  formData.append('username', email) // Backend maps 'username' to email
  formData.append('password', password)

  const response = await fetch(`${API_BASE_URL}/auth/login`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
    },
    body: formData.toString(),
  })

  return handleResponse<TokenResponse>(response)
}

/**
 * Register new user
 */
export async function registerUser(
  email: string,
  name: string,
  password: string
): Promise<TokenResponse> {
  const body: RegisterRequest = { email, name, password }

  const response = await fetch(`${API_BASE_URL}/auth/register`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(body),
  })

  return handleResponse<TokenResponse>(response)
}

/**
 * Refresh access token using refresh token
 */
export async function refreshAccessToken(refreshToken: string): Promise<TokenResponse> {
  const body: RefreshTokenRequest = { refresh_token: refreshToken }

  const response = await fetch(`${API_BASE_URL}/auth/refresh`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(body),
  })

  return handleResponse<TokenResponse>(response)
}

/**
 * Get current user info
 */
export async function getCurrentUser(accessToken: string): Promise<User> {
  const response = await fetch(`${API_BASE_URL}/auth/me`, {
    method: 'GET',
    headers: {
      Authorization: `Bearer ${accessToken}`,
    },
  })

  return handleResponse<User>(response)
}

/**
 * Logout user (server-side cleanup)
 */
export async function logoutUser(accessToken: string): Promise<LogoutResponse> {
  const response = await fetch(`${API_BASE_URL}/auth/logout`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${accessToken}`,
    },
  })

  return handleResponse<LogoutResponse>(response)
}

/**
 * Update current user's profile
 */
export async function updateProfile(
  accessToken: string,
  data: UpdateProfileRequest
): Promise<User> {
  const response = await fetch(`${API_BASE_URL}/users/me`, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${accessToken}`,
    },
    body: JSON.stringify(data),
  })

  return handleResponse<User>(response)
}
