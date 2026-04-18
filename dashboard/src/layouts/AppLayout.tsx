import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";

const navItems = [
  { to: "/", label: "总览" },
  { to: "/containers", label: "容器与服务" },
  { to: "/knowledge", label: "知识库" },
  { to: "/documents", label: "文档与任务" },
  { to: "/models", label: "模型连接" },
  { to: "/rag", label: "RAG 调试" },
  { to: "/settings", label: "系统设置" },
  { to: "/audit", label: "审计日志" }
];

export function AppLayout() {
  const { user, logout } = useAuth();

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-kicker">Dual-Server Ops</span>
          <strong>RAG Platform</strong>
        </div>
        <nav className="nav">
          {navItems.map((item) => (
            <NavLink key={item.to} to={item.to} end={item.to === "/"}>
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-footer">
          <div className="user-card">
            <span>管理员</span>
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

