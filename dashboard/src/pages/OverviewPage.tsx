import { useEffect, useState } from "react";
import { apiRequest } from "../api/client";
import { MetricCard } from "../components/MetricCard";
import { PageHeader } from "../components/PageHeader";
import { StatusPill } from "../components/StatusPill";
import { useAuth } from "../hooks/useAuth";

type OverviewResponse = {
  metrics: Record<string, number>;
  backup_status: Record<string, unknown>;
  service_health: Array<{
    service_name: string;
    service_type: string;
    host: string;
    status: string;
    response_ms: number;
    checked_at: string;
  }>;
  latest_jobs: Array<{
    id: number;
    document_id: number;
    stage: string;
    status: string;
    updated_at: string;
  }>;
  latest_audits: Array<{
    id: number;
    actor_username: string;
    target_service: string;
    action: string;
    status: string;
    created_at: string;
  }>;
};

export function OverviewPage() {
  const { session } = useAuth();
  const [data, setData] = useState<OverviewResponse | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    void apiRequest<OverviewResponse>("/api/system/overview", { method: "GET" }, session)
      .then((result) => {
        setData(result);
        setError("");
      })
      .catch((loadError) => setError(loadError instanceof Error ? loadError.message : "加载总览失败。"));
  }, [session]);

  const backupStatus = data?.backup_status ?? {};

  return (
    <section className="page">
      <PageHeader title="总览" subtitle="掌握服务健康、索引任务、最近审计和最新备份状态。" />
      {error ? <div className="error-banner">{error}</div> : null}
      <div className="metric-grid">
        <MetricCard label="知识库" value={data?.metrics.knowledge_bases ?? "-"} />
        <MetricCard label="文档总数" value={data?.metrics.documents ?? "-"} />
        <MetricCard label="待处理任务" value={data?.metrics.jobs_pending ?? "-"} />
        <MetricCard label="运行中任务" value={data?.metrics.jobs_running ?? "-"} />
        <MetricCard label="失败任务" value={data?.metrics.jobs_failed ?? "-"} />
        <MetricCard label="异常服务" value={data?.metrics.unhealthy_services ?? "-"} />
      </div>

      <div className="two-column">
        <div className="panel">
          <h2>服务健康</h2>
          <div className="panel-list">
            {data?.service_health.map((item) => (
              <article key={`${item.service_name}-${item.checked_at}`} className="list-row">
                <div>
                  <strong>{item.service_name}</strong>
                  <p>{item.host}</p>
                </div>
                <div className="row-meta">
                  <span>{item.response_ms} ms</span>
                  <StatusPill status={item.status} />
                </div>
              </article>
            )) ?? <p className="empty-hint">暂无健康检查数据。</p>}
          </div>
        </div>

        <div className="panel">
          <h2>最新备份</h2>
          <div className="key-value">
            <span>状态</span>
            <strong>{String(backupStatus.status ?? "missing")}</strong>
          </div>
          <div className="key-value">
            <span>快照</span>
            <strong>{String(backupStatus.snapshot ?? "-")}</strong>
          </div>
          <div className="key-value">
            <span>更新时间</span>
            <strong>{String(backupStatus.updated_at ?? "-")}</strong>
          </div>
          <div className="key-value">
            <span>Elasticsearch 快照</span>
            <strong>{String(backupStatus.elasticsearch_snapshot ?? "-")}</strong>
          </div>
        </div>
      </div>

      <div className="two-column">
        <div className="panel">
          <h2>最近任务</h2>
          <div className="panel-list">
            {data?.latest_jobs.map((item) => (
              <article key={item.id} className="list-row">
                <div>
                  <strong>任务 #{item.id}</strong>
                  <p>文档 #{item.document_id}</p>
                </div>
                <div className="row-meta">
                  <span>{item.stage}</span>
                  <StatusPill status={item.status} />
                </div>
              </article>
            )) ?? <p className="empty-hint">暂无任务。</p>}
          </div>
        </div>

        <div className="panel">
          <h2>最近审计</h2>
          <div className="panel-list">
            {data?.latest_audits.map((item) => (
              <article key={item.id} className="list-row">
                <div>
                  <strong>{item.actor_username}</strong>
                  <p>
                    {item.action} {item.target_service}
                  </p>
                </div>
                <div className="row-meta">
                  <span>{new Date(item.created_at).toLocaleString()}</span>
                  <StatusPill status={item.status} />
                </div>
              </article>
            )) ?? <p className="empty-hint">暂无审计记录。</p>}
          </div>
        </div>
      </div>
    </section>
  );
}
