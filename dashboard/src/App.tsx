import type { ReactElement } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { AppLayout } from "./layouts/AppLayout";
import { useAuth } from "./hooks/useAuth";
import { AuditPage } from "./pages/AuditPage";
import { ContainersPage } from "./pages/ContainersPage";
import { DocumentsPage } from "./pages/DocumentsPage";
import { KnowledgeBasesPage } from "./pages/KnowledgeBasesPage";
import { LoginPage } from "./pages/LoginPage";
import { ModelsPage } from "./pages/ModelsPage";
import { OverviewPage } from "./pages/OverviewPage";
import { RagPage } from "./pages/RagPage";
import { SettingsPage } from "./pages/SettingsPage";

function ProtectedRoutes() {
  const { loading, user } = useAuth();

  if (loading) {
    return <div className="loading-screen">正在加载平台状态...</div>;
  }

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  return <AppLayout />;
}

function GuardedRoute({ allowed, element }: { allowed: boolean; element: ReactElement }) {
  return allowed ? element : <Navigate to="/" replace />;
}

export default function App() {
  const { user, canOperateContainers, canRunRag } = useAuth();

  return (
    <Routes>
      <Route path="/login" element={user ? <Navigate to="/" replace /> : <LoginPage />} />
      <Route element={<ProtectedRoutes />}>
        <Route path="/" element={<OverviewPage />} />
        <Route path="/containers" element={<GuardedRoute allowed={canOperateContainers} element={<ContainersPage />} />} />
        <Route path="/knowledge" element={<KnowledgeBasesPage />} />
        <Route path="/documents" element={<DocumentsPage />} />
        <Route path="/models" element={<ModelsPage />} />
        <Route path="/rag" element={<GuardedRoute allowed={canRunRag} element={<RagPage />} />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/audit" element={<AuditPage />} />
      </Route>
      <Route path="*" element={<Navigate to={user ? "/" : "/login"} replace />} />
    </Routes>
  );
}
