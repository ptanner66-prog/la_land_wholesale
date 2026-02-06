/**
 * Authentication context — stores user state, handles token refresh, redirects on 401.
 */
import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from 'react';
import {
  getStoredToken,
  clearTokens,
  refreshAccessToken,
  getCurrentUser,
  logoutUser,
  type UserInfo,
} from '@/api/auth';

interface AuthContextType {
  user: UserInfo | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType>({
  user: null,
  isAuthenticated: false,
  isLoading: true,
  logout: async () => {},
  refreshUser: async () => {},
});

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserInfo | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const loadUser = useCallback(async () => {
    const token = getStoredToken();
    if (!token) {
      setUser(null);
      setIsLoading(false);
      return;
    }

    try {
      const userInfo = await getCurrentUser();
      setUser(userInfo);
    } catch {
      // Token might be expired — try refresh
      const refreshResult = await refreshAccessToken();
      if (refreshResult) {
        try {
          const userInfo = await getCurrentUser();
          setUser(userInfo);
        } catch {
          clearTokens();
          setUser(null);
        }
      } else {
        setUser(null);
      }
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadUser();
  }, [loadUser]);

  const logout = useCallback(async () => {
    await logoutUser();
    setUser(null);
  }, []);

  const refreshUser = useCallback(async () => {
    await loadUser();
  }, [loadUser]);

  return (
    <AuthContext.Provider
      value={{
        user,
        isAuthenticated: user !== null,
        isLoading,
        logout,
        refreshUser,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
