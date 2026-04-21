import { ReactNode, createContext, useContext, useEffect, useMemo, useState } from "react";
import { ApiError, SessionTokens, apiRequest, loadSession, saveSession } from "../api/client";

export type UserRole = "superadmin" | "operator" | "viewer";

export type CurrentUser = {
  id: number;
  username: string;
  is_active: boolean;
  is_superuser: boolean;
  role: UserRole;
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
  canManageUsers: boolean;
  canOperateContainers: boolean;
  canWriteKnowledge: boolean;
  canUploadDocuments: boolean;
  canRunRag: boolean;
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
      setError(err instanceof ApiError ? err.message : "加载用户信息失败。");
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

  const capabilities = useMemo(() => {
    const role = user?.role;
    return {
      canManageUsers: role === "superadmin",
      canOperateContainers: role === "superadmin" || role === "operator",
      canWriteKnowledge: role === "superadmin" || role === "operator",
      canUploadDocuments: role === "superadmin" || role === "operator",
      canRunRag: role === "superadmin" || role === "operator"
    };
  }, [user]);

  return (
    <AuthContext.Provider
      value={{
        user,
        session,
        loading,
        error,
        login,
        logout,
        refreshMe,
        ...capabilities
      }}
    >
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
