import { ReactNode, createContext, useContext, useEffect, useState } from "react";
import { ApiError, SessionTokens, apiRequest, loadSession, saveSession } from "../api/client";

type CurrentUser = {
  id: number;
  username: string;
  is_active: boolean;
  is_superuser: boolean;
  last_login_at?: string | null;
};

type AuthContextValue = {
  user: CurrentUser | null;
  session: SessionTokens | null;
  loading: boolean;
  error: string | null;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  refreshMe: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<SessionTokens | null>(() => loadSession());
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refreshMe = async (candidateSession: SessionTokens | null = session) => {
    if (!candidateSession) {
      setUser(null);
      setLoading(false);
      return;
    }
    try {
      const data = await apiRequest<CurrentUser>("/api/auth/me", { method: "GET" }, candidateSession);
      setUser(data);
      setError(null);
    } catch (err) {
      saveSession(null);
      setSession(null);
      setUser(null);
      setError(err instanceof ApiError ? err.message : "加载用户信息失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void refreshMe();
  }, []);

  const login = async (username: string, password: string) => {
    const tokens = await apiRequest<{ access_token: string; refresh_token: string }>(
      "/api/auth/login",
      {
        method: "POST",
        body: JSON.stringify({ username, password })
      }
    );
    const nextSession = {
      accessToken: tokens.access_token,
      refreshToken: tokens.refresh_token
    };
    saveSession(nextSession);
    setSession(nextSession);
    setLoading(true);
    await refreshMe(nextSession);
  };

  const logout = () => {
    saveSession(null);
    setSession(null);
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, session, loading, error, login, logout, refreshMe }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return context;
}
