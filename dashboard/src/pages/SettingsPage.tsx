import { FormEvent, useEffect, useState } from "react";
import { apiRequest } from "../api/client";
import { PageHeader } from "../components/PageHeader";
import { UserRole, useAuth } from "../hooks/useAuth";

type UserItem = {
  id: number;
  username: string;
  role: UserRole;
  is_active: boolean;
  last_login_at?: string | null;
};

type UserForm = {
  username: string;
  password: string;
  role: UserRole;
  is_active: boolean;
};

const defaultUserForm = {
  username: "",
  password: "",
  role: "viewer" as UserRole,
  is_active: true
} satisfies UserForm;

export function SettingsPage() {
  const { user, session, canManageUsers } = useAuth();
  const [users, setUsers] = useState<UserItem[]>([]);
  const [form, setForm] = useState<UserForm>(defaultUserForm);
  const [resetPassword, setResetPassword] = useState<Record<number, string>>({});
  const [error, setError] = useState("");

  const loadUsers = async () => {
    if (!canManageUsers) {
      return;
    }
    const data = await apiRequest<UserItem[]>("/api/auth/users", { method: "GET" }, session);
    setUsers(data);
  };

  useEffect(() => {
    void loadUsers();
  }, [canManageUsers, session]);

  const createUser = async (event: FormEvent) => {
    event.preventDefault();
    if (!canManageUsers) {
      return;
    }
    try {
      await apiRequest("/api/auth/users", { method: "POST", body: JSON.stringify(form) }, session);
      setForm(defaultUserForm);
      setError("");
      await loadUsers();
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "创建用户失败。");
    }
  };

  const updateUser = async (candidate: UserItem, patch: Partial<Pick<UserItem, "role" | "is_active">>) => {
    try {
      await apiRequest(`/api/auth/users/${candidate.id}`, { method: "PATCH", body: JSON.stringify(patch) }, session);
      await loadUsers();
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "更新用户失败。");
    }
  };

  const resetUserPassword = async (userId: number) => {
    const password = resetPassword[userId];
    if (!password) {
      return;
    }
    try {
      await apiRequest(
        `/api/auth/users/${userId}/reset-password`,
        { method: "POST", body: JSON.stringify({ password }) },
        session
      );
      setResetPassword((current) => ({ ...current, [userId]: "" }));
      setError("");
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "重置密码失败。");
    }
  };

  const roleLabel = {
    superadmin: "超级管理员",
    operator: "运维操作员",
    viewer: "只读审计员"
  }[user?.role ?? "viewer"];

  return (
    <section className="page">
      <PageHeader title="系统设置" subtitle="查看部署边界、当前账号信息，并在超级管理员角色下维护本地账号。" />
      {error ? <div className="error-banner">{error}</div> : null}
      <div className="two-column">
        <div className="panel">
          <h2>部署约定</h2>
          <div className="key-value">
            <span>访问边界</span>
            <strong>内网鉴权</strong>
          </div>
          <div className="key-value">
            <span>应用服务器</span>
            <strong>192.168.110.117</strong>
          </div>
          <div className="key-value">
            <span>GPU 服务器</span>
            <strong>192.168.110.241</strong>
          </div>
          <div className="key-value">
            <span>容器运维范围</span>
            <strong>仅应用服务器白名单服务</strong>
          </div>
        </div>
        <div className="panel">
          <h2>当前账号</h2>
          <div className="key-value">
            <span>用户名</span>
            <strong>{user?.username ?? "-"}</strong>
          </div>
          <div className="key-value">
            <span>角色</span>
            <strong>{roleLabel}</strong>
          </div>
          <div className="key-value">
            <span>上次登录</span>
            <strong>{user?.last_login_at ? new Date(user.last_login_at).toLocaleString() : "-"}</strong>
          </div>
        </div>
      </div>

      <div className="two-column">
        <form className="panel form-grid" onSubmit={createUser}>
          <h2>用户管理</h2>
          {!canManageUsers ? <p className="panel-meta">只有超级管理员可以创建用户、调整角色和重置密码。</p> : null}
          <label>
            用户名
            <input value={form.username} onChange={(event) => setForm({ ...form, username: event.target.value })} disabled={!canManageUsers} />
          </label>
          <label>
            初始密码
            <input
              type="password"
              value={form.password}
              onChange={(event) => setForm({ ...form, password: event.target.value })}
              disabled={!canManageUsers}
            />
          </label>
          <label>
            角色
            <select value={form.role} onChange={(event) => setForm({ ...form, role: event.target.value as UserItem["role"] })} disabled={!canManageUsers}>
              <option value="superadmin">superadmin</option>
              <option value="operator">operator</option>
              <option value="viewer">viewer</option>
            </select>
          </label>
          <label>
            启用状态
            <select
              value={form.is_active ? "true" : "false"}
              onChange={(event) => setForm({ ...form, is_active: event.target.value === "true" })}
              disabled={!canManageUsers}
            >
              <option value="true">启用</option>
              <option value="false">禁用</option>
            </select>
          </label>
          <button className="primary-button" type="submit" disabled={!canManageUsers}>
            创建用户
          </button>
        </form>

        <div className="panel">
          <h2>用户列表</h2>
          <div className="panel-list">
            {!canManageUsers ? <p className="empty-hint">当前角色不可查看用户列表。</p> : null}
            {canManageUsers &&
              users.map((item) => (
                <article className="list-row" key={item.id}>
                  <div>
                    <strong>{item.username}</strong>
                    <p>{item.last_login_at ? `最近登录 ${new Date(item.last_login_at).toLocaleString()}` : "暂无登录记录"}</p>
                  </div>
                  <div className="row-meta">
                    <select value={item.role} onChange={(event) => void updateUser(item, { role: event.target.value as UserItem["role"] })}>
                      <option value="superadmin">superadmin</option>
                      <option value="operator">operator</option>
                      <option value="viewer">viewer</option>
                    </select>
                    <select value={item.is_active ? "true" : "false"} onChange={(event) => void updateUser(item, { is_active: event.target.value === "true" })}>
                      <option value="true">启用</option>
                      <option value="false">禁用</option>
                    </select>
                  </div>
                  <div className="form-grid">
                    <input
                      type="password"
                      placeholder="新密码"
                      value={resetPassword[item.id] ?? ""}
                      onChange={(event) => setResetPassword((current) => ({ ...current, [item.id]: event.target.value }))}
                    />
                    <button className="ghost-button" type="button" onClick={() => void resetUserPassword(item.id)}>
                      重置密码
                    </button>
                  </div>
                </article>
              ))}
          </div>
        </div>
      </div>
    </section>
  );
}
