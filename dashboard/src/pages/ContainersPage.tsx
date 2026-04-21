import { useEffect, useState } from "react";
import { apiRequest } from "../api/client";
import { PageHeader } from "../components/PageHeader";
import { StatusPill } from "../components/StatusPill";
import { useAuth } from "../hooks/useAuth";

type ContainerState = {
  name: string;
  status: string;
  image?: string | null;
  started_at?: string | null;
};

const actions = ["start", "stop", "restart", "recreate"];

export function ContainersPage() {
  const { session, canOperateContainers } = useAuth();
  const [items, setItems] = useState<ContainerState[]>([]);
  const [selectedLogs, setSelectedLogs] = useState<string>("");
  const [error, setError] = useState("");

  const load = async () => {
    try {
      const data = await apiRequest<ContainerState[]>("/api/containers", { method: "GET" }, session);
      setItems(data);
      setError("");
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "加载容器状态失败。");
    }
  };

  useEffect(() => {
    void load();
  }, [session]);

  const runAction = async (name: string, action: string) => {
    if (!canOperateContainers) {
      return;
    }
    try {
      await apiRequest(`/api/containers/${name}/actions/${action}`, { method: "POST" }, session);
      await load();
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : "执行容器动作失败。");
    }
  };

  const loadLogs = async (name: string) => {
    try {
      const data = await apiRequest<{ logs: string }>(`/api/containers/${name}/logs?tail=200`, { method: "GET" }, session);
      setSelectedLogs(data.logs);
      setError("");
    } catch (logError) {
      setError(logError instanceof Error ? logError.message : "读取容器日志失败。");
    }
  };

  return (
    <section className="page">
      <PageHeader
        title="容器与服务"
        subtitle="只对白名单服务开放日志查看和容器动作。GPU 模型服务器保持只读监测。"
        actions={
          <button className="secondary-button" onClick={() => void load()} type="button">
            刷新
          </button>
        }
      />
      {error ? <div className="error-banner">{error}</div> : null}

      <div className="table-panel">
        <table>
          <thead>
            <tr>
              <th>服务</th>
              <th>状态</th>
              <th>镜像</th>
              <th>启动时间</th>
              <th>动作</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={item.name}>
                <td>{item.name}</td>
                <td>
                  <StatusPill status={item.status} />
                </td>
                <td>{item.image ?? "-"}</td>
                <td>{item.started_at ? new Date(item.started_at).toLocaleString() : "-"}</td>
                <td>
                  <div className="action-row">
                    <button className="ghost-button" onClick={() => void loadLogs(item.name)} type="button">
                      日志
                    </button>
                    {actions.map((action) => (
                      <button
                        key={action}
                        className="ghost-button"
                        onClick={() => void runAction(item.name, action)}
                        type="button"
                        disabled={!canOperateContainers}
                      >
                        {action}
                      </button>
                    ))}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="panel">
        <h2>容器日志</h2>
        <pre className="log-view">{selectedLogs || "点击上方“日志”查看容器输出。"}</pre>
      </div>
    </section>
  );
}
