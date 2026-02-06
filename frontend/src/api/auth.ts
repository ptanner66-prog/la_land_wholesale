/**
 * Authentication API client
 */
import { apiClient } from './client';

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

export interface UserInfo {
  id: number;
  email: string;
  role: string;
  created_at: string;
}

const TOKEN_KEY = 'auth_access_token';
const REFRESH_KEY = 'auth_refresh_token';

export function getStoredToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function getStoredRefreshToken(): string | null {
  return localStorage.getItem(REFRESH_KEY);
}

export function storeTokens(access: string, refresh: string): void {
  localStorage.setItem(TOKEN_KEY, access);
  localStorage.setItem(REFRESH_KEY, refresh);
}

export function clearTokens(): void {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(REFRESH_KEY);
}

export async function loginUser(email: string, password: string): Promise<TokenResponse> {
  const response = await apiClient.post<TokenResponse>('/auth/login', { email, password });
  const data = response.data;
  storeTokens(data.access_token, data.refresh_token);
  return data;
}

export async function registerUser(email: string, password: string): Promise<TokenResponse> {
  const response = await apiClient.post<TokenResponse>('/auth/register', { email, password });
  const data = response.data;
  storeTokens(data.access_token, data.refresh_token);
  return data;
}

export async function refreshAccessToken(): Promise<TokenResponse | null> {
  const refreshToken = getStoredRefreshToken();
  if (!refreshToken) return null;

  try {
    const response = await apiClient.post<TokenResponse>('/auth/refresh', {
      refresh_token: refreshToken,
    });
    const data = response.data;
    storeTokens(data.access_token, data.refresh_token);
    return data;
  } catch {
    clearTokens();
    return null;
  }
}

export async function logoutUser(): Promise<void> {
  const refreshToken = getStoredRefreshToken();
  if (refreshToken) {
    try {
      await apiClient.post('/auth/logout', { refresh_token: refreshToken });
    } catch {
      // Ignore errors on logout
    }
  }
  clearTokens();
}

export async function getCurrentUser(): Promise<UserInfo> {
  const response = await apiClient.get<UserInfo>('/auth/me');
  return response.data;
}
