import { useEffect, useState } from "react";
import { apiRequest } from "../api/client";
import { PageHeader } from "../components/PageHeader";
import { StatusPill } from "../components/StatusPill";
import { useAuth } from "../hooks/useAuth";

type ModelProvider = {
  id: number;
  name: string;
  kind: string;
  protocol: string;
  base_url: string;
  model_name: string;
  enabled: boolean;
  priority: number;
  metadata_json: Record<string, unknown>;
};

type HealthSnapshot = {
  service_name: string;
  host: string;
  status: string;
  response_ms: number;
  details_json: Record<string, unknown>;
};

export function ModelsPage() {
  const { session } = useAuth();
  const [providers, setProviders] = useState<ModelProvider[]>([]);
  const [health, setHealth] = useState<HealthSnapshot[]>([]);

  const load = async () => {
    const [providerData, healthData] = await Promise.all([
      apiRequest<ModelProvider[]>("/api/models/providers", { method: "GET" }, session),
      apiRequest<HealthSnapshot[]>("/api/models/health", { method: "GET" }, session)
    ]);
    setProviders(providerData);
    setHealth(healthData);
  };

  useEffect(() => {
    void load();
  }, [session]);

  return (
    <section className="page">
      <PageHeader
        title="模型连接"
        subtitle="应用机只读监测 GPU 服务器上的 Embedding 和生成模型接口。"
        actions={
          <button className="secondary-button" onClick={() => void load()} type="button">
            立即探测
          </button>
        }
      />

      <div className="two-column">
        <div className="panel">
          <h2>Provider 配置</h2>
          <div className="panel-list">
            {providers.map((item) => (
              <article className="list-row" key={item.id}>
                <div>
                  <strong>{item.name}</strong>
                  <p>
                    {item.protocol} · {item.model_name}
                  </p>
                </div>
                <div className="row-meta">
                  <span>优先级 {item.priority}</span>
                  <StatusPill status={item.enabled ? "enabled" : "disabled"} />
                </div>
              </article>
            ))}
          </div>
        </div>

        <div className="panel">
          <h2>连通性探测</h2>
          <div className="panel-list">
            {health.map((item) => (
              <article className="list-row" key={`${item.service_name}-${item.host}`}>
                <div>
                  <strong>{item.service_name}</strong>
                  <p>{item.host}</p>
                </div>
                <div className="row-meta">
                  <span>{item.response_ms} ms</span>
                  <StatusPill status={item.status} />
                </div>
              </article>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

