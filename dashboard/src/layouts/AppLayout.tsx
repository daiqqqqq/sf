import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";

export function AppLayout() {
  const { user, logout, canOperateContainers, canRunRag } = useAuth();

  const navItems = [
    { to: "/", label: "Overview", visible: true },
    { to: "/containers", label: "Containers", visible: canOperateContainers },
    { to: "/knowledge", label: "Knowledge", visible: true },
    { to: "/documents", label: "Documents", visible: true },
    { to: "/models", label: "Models", visible: true },
    { to: "/gpu", label: "GPU Monitor", visible: true },
    { to: "/rag", label: "RAG Debug", visible: canRunRag },
    { to: "/settings", label: "Settings", visible: true },
    { to: "/audit", label: "Audit", visible: true }
  ];

  const roleLabel = {
    superadmin: "Superadmin",
    operator: "Operator",
    viewer: "Viewer"
  }[user?.role ?? "viewer"];

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-kicker">Dual-Server Ops</span>
          <strong>RAG Platform</strong>
        </div>
        <nav className="nav">
          {navItems
            .filter((item) => item.visible)
            .map((item) => (
              <NavLink key={item.to} to={item.to} end={item.to === "/"}>
                {item.label}
              </NavLink>
            ))}
        </nav>
        <div className="sidebar-footer">
          <div className="user-card">
            <span>{roleLabel}</span>
            <strong>{user?.username ?? "Anonymous"}</strong>
          </div>
          <button className="ghost-button" onClick={logout} type="button">
            Sign out
          </button>
        </div>
      </aside>
      <main className="content">
        <Outlet />
      </main>
    </div>
  );
}
