import { FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";

export function LoginPage() {
  const { login, error } = useAuth();
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);
  const navigate = useNavigate();

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSubmitting(true);
    setLocalError(null);
    try {
      await login(username, password);
      navigate("/");
    } catch (err) {
      setLocalError(err instanceof Error ? err.message : "登录失败。");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="login-shell">
      <section className="login-panel">
        <div className="login-copy">
          <span className="brand-kicker">Private Intranet Control Plane</span>
          <h1>统一管理双机 RAG 平台</h1>
          <p>同一入口管理应用服务器容器、知识库索引任务、RAG 调试，以及 GPU 模型服务健康状态。</p>
        </div>
        <form className="login-form" onSubmit={handleSubmit}>
          <label>
            用户名
            <input value={username} onChange={(event) => setUsername(event.target.value)} />
          </label>
          <label>
            密码
            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder="输入管理员密码"
            />
          </label>
          {localError || error ? <div className="error-banner">{localError ?? error}</div> : null}
          <button className="primary-button" disabled={submitting} type="submit">
            {submitting ? "登录中..." : "进入 Dashboard"}
          </button>
        </form>
      </section>
    </div>
  );
}
