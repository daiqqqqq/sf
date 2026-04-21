import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";

export function AppLayout() {
  const { user, logout, canOperateContainers, canRunRag } = useAuth();

  const navItems = [
    { to: "/", label: "总览", visible: true },
    { to: "/containers", label: "容器与服务", visible: canOperateContainers },
    { to: "/knowledge", label: "知识库", visible: true },
    { to: "/documents", label: "文档与任务", visible: true },
    { to: "/models", label: "模型连接", visible: true },
    { to: "/rag", label: "RAG 调试", visible: canRunRag },
    { to: "/settings", label: "系统设置", visible: true },
    { to: "/audit", label: "审计日志", visible: true }
  ];

  const roleLabel = {
    superadmin: "超级管理员",
    operator: "运维操作员",
    viewer: "只读审计员"
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
            <strong>{user?.username ?? "未登录"}</strong>
          </div>
          <button className="ghost-button" onClick={logout} type="button">
            退出登录
          </button>
        </div>
      </aside>
      <main className="content">
        <Outlet />
      </main>
    </div>
  );
}
