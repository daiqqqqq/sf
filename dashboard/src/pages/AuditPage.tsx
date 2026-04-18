import { useEffect, useState } from "react";
import { apiRequest } from "../api/client";
import { PageHeader } from "../components/PageHeader";
import { StatusPill } from "../components/StatusPill";
import { useAuth } from "../hooks/useAuth";

type AuditItem = {
  id: number;
  actor_username: string;
  target_service: string;
  action: string;
  status: string;
  details_json: Record<string, unknown>;
  created_at: string;
};

export function AuditPage() {
  const { session } = useAuth();
  const [items, setItems] = useState<AuditItem[]>([]);

  useEffect(() => {
    void apiRequest<{ items: AuditItem[] }>("/api/audit", { method: "GET" }, session).then((data) => setItems(data.items));
  }, [session]);

  return (
    <section className="page">
      <PageHeader title="审计日志" subtitle="记录谁对哪个服务执行了什么动作，以及结果是否成功。" />
      <div className="table-panel">
        <table>
          <thead>
            <tr>
              <th>时间</th>
              <th>操作者</th>
              <th>目标服务</th>
              <th>动作</th>
              <th>状态</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={item.id}>
                <td>{new Date(item.created_at).toLocaleString()}</td>
                <td>{item.actor_username}</td>
                <td>{item.target_service}</td>
                <td>{item.action}</td>
                <td>
                  <StatusPill status={item.status} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

