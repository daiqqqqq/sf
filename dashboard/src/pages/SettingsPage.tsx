import { PageHeader } from "../components/PageHeader";
import { useAuth } from "../hooks/useAuth";

export function SettingsPage() {
  const { user } = useAuth();

  return (
    <section className="page">
      <PageHeader title="系统设置" subtitle="当前版本先聚焦部署约定、运维边界和管理员信息展示。" />
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
            <strong>仅应用服务器白名单容器</strong>
          </div>
        </div>
        <div className="panel">
          <h2>管理员信息</h2>
          <div className="key-value">
            <span>当前账号</span>
            <strong>{user?.username ?? "-"}</strong>
          </div>
          <div className="key-value">
            <span>超级管理员</span>
            <strong>{user?.is_superuser ? "是" : "否"}</strong>
          </div>
          <div className="key-value">
            <span>上次登录</span>
            <strong>{user?.last_login_at ? new Date(user.last_login_at).toLocaleString() : "-"}</strong>
          </div>
        </div>
      </div>
    </section>
  );
}

