/**
 * Authentication type definitions
 */

export interface User {
  id: string
  email: string
  name: string
  role: string
  created_at: string
}

export interface RegisterRequest {
  email: string
  name: string
  password: string
}

export interface TokenResponse {
  access_token: string
  refresh_token: string
  token_type: string
  expires_in: number
  user: User
}

export interface RefreshTokenRequest {
  refresh_token: string
}

export interface LogoutResponse {
  message: string
}

export interface UpdateProfileRequest {
  name?: string
}
