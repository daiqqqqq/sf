import { useEffect, useState } from "react";
import { apiRequest } from "../api/client";
import { MetricCard } from "../components/MetricCard";
import { PageHeader } from "../components/PageHeader";
import { StatusPill } from "../components/StatusPill";
import { useAuth } from "../hooks/useAuth";

type GpuDevice = {
  id: string;
  label: string;
  uuid?: string | null;
  model_name?: string | null;
  status: string;
  utilization_percent?: number | null;
  memory_used_mb?: number | null;
  memory_total_mb?: number | null;
  memory_utilization_percent?: number | null;
  temperature_celsius?: number | null;
  power_watts?: number | null;
  sample_time?: string | null;
};

type GpuServiceStatus = {
  name: string;
  base_url: string;
  status: string;
  response_ms?: number | null;
  detail: string;
};

type GpuOverview = {
  node_host: string;
  node_status: string;
  exporter_status: string;
  prometheus_status: string;
  sampled_at?: string | null;
  gpu_count: number;
  total_memory_mb: number;
  used_memory_mb: number;
  average_utilization_percent?: number | null;
  max_temperature_celsius?: number | null;
  total_power_watts?: number | null;
  grafana_url: string;
  warnings: string[];
  devices: GpuDevice[];
  model_services: GpuServiceStatus[];
};

function clampPercent(value: number | null | undefined): number {
  if (value == null || Number.isNaN(value)) {
    return 0;
  }
  return Math.max(0, Math.min(100, value));
}

function formatGiB(megabytes: number | null | undefined): string {
  if (megabytes == null || Number.isNaN(megabytes)) {
    return "-";
  }
  return `${(megabytes / 1024).toFixed(1)} GiB`;
}

function formatPercent(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) {
    return "-";
  }
  return `${value.toFixed(1)}%`;
}

function formatTemperature(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) {
    return "-";
  }
  return `${value.toFixed(1)} C`;
}

function formatPower(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) {
    return "-";
  }
  return `${value.toFixed(1)} W`;
}

export function GpuPage() {
  const { session } = useAuth();
  const [data, setData] = useState<GpuOverview | null>(null);
  const [error, setError] = useState("");

  const load = async () => {
    try {
      const overview = await apiRequest<GpuOverview>("/api/gpu/overview", { method: "GET" }, session);
      setData(overview);
      setError("");
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Failed to load GPU monitoring.");
    }
  };

  useEffect(() => {
    void load();
  }, [session]);

  return (
    <section className="page">
      <PageHeader
        title="GPU Monitor"
        subtitle="Review GPU load, memory, temperature, power, and model service reachability from one control-room view."
        actions={
          <>
            <button className="secondary-button" onClick={() => void load()} type="button">
              Refresh now
            </button>
            <a
              className="ghost-button inline-link-button"
              href={data?.grafana_url ?? "#"}
              rel="noreferrer"
              target="_blank"
            >
              Open Grafana
            </a>
          </>
        }
      />
      {error ? <div className="error-banner">{error}</div> : null}

      <div className="gpu-status-strip">
        <article className="gpu-status-card">
          <span className="metric-label">GPU Node</span>
          <strong>{data?.node_host ?? "192.168.110.241"}</strong>
          <StatusPill status={data?.node_status ?? "unknown"} />
        </article>
        <article className="gpu-status-card">
          <span className="metric-label">Exporter</span>
          <strong>{data?.devices.length ? `${data.devices.length} device(s)` : "Waiting for data"}</strong>
          <StatusPill status={data?.exporter_status ?? "unknown"} />
        </article>
        <article className="gpu-status-card">
          <span className="metric-label">Prometheus</span>
          <strong>{data?.prometheus_status ?? "unknown"}</strong>
          <StatusPill status={data?.prometheus_status ?? "unknown"} />
        </article>
        <article className="gpu-status-card">
          <span className="metric-label">Last Sample</span>
          <strong>{data?.sampled_at ? new Date(data.sampled_at).toLocaleString() : "-"}</strong>
          <span className="metric-hint">Instant query from Prometheus</span>
        </article>
      </div>

      <div className="metric-grid">
        <MetricCard label="GPU Count" value={data?.gpu_count ?? "-"} />
        <MetricCard label="Total Memory" value={formatGiB(data?.total_memory_mb)} />
        <MetricCard label="Used Memory" value={formatGiB(data?.used_memory_mb)} />
        <MetricCard label="Average Load" value={formatPercent(data?.average_utilization_percent)} />
        <MetricCard label="Peak Temp" value={formatTemperature(data?.max_temperature_celsius)} />
        <MetricCard label="Total Power" value={formatPower(data?.total_power_watts)} />
      </div>

      {data?.warnings.length ? (
        <div className="panel">
          <h2>Monitoring Warnings</h2>
          <div className="panel-list">
            {data.warnings.map((item) => (
              <article className="list-row" key={item}>
                <div>
                  <strong>GPU monitoring is degraded</strong>
                  <p>{item}</p>
                </div>
                <StatusPill status="warning" />
              </article>
            ))}
          </div>
        </div>
      ) : null}

      <div className="two-column">
        <div className="panel">
          <div className="panel-heading">
            <div>
              <h2>Device Snapshot</h2>
              <p className="panel-meta">The platform shows core inspection metrics here. Historical trends live in Grafana.</p>
            </div>
          </div>
          <div className="gpu-device-grid">
            {data?.devices.length ? (
              data.devices.map((device) => (
                <article className="gpu-device-card" key={device.id}>
                  <div className="gpu-device-header">
                    <div>
                      <strong>{device.label}</strong>
                      <p>{device.model_name ?? device.uuid ?? "Unknown GPU"}</p>
                    </div>
                    <StatusPill status={device.status} />
                  </div>

                  <div className="gpu-meter-block">
                    <div className="row-meta">
                      <span>Utilization</span>
                      <strong>{formatPercent(device.utilization_percent)}</strong>
                    </div>
                    <div className="gpu-meter">
                      <div
                        className="gpu-meter-bar accent"
                        style={{ width: `${clampPercent(device.utilization_percent)}%` }}
                      />
                    </div>
                  </div>

                  <div className="gpu-meter-block">
                    <div className="row-meta">
                      <span>Memory</span>
                      <strong>
                        {formatGiB(device.memory_used_mb)} / {formatGiB(device.memory_total_mb)}
                      </strong>
                    </div>
                    <div className="gpu-meter">
                      <div
                        className="gpu-meter-bar info"
                        style={{ width: `${clampPercent(device.memory_utilization_percent)}%` }}
                      />
                    </div>
                  </div>

                  <div className="gpu-device-stats">
                    <div className="spotlight-metric">
                      <span>Temperature</span>
                      <strong>{formatTemperature(device.temperature_celsius)}</strong>
                    </div>
                    <div className="spotlight-metric">
                      <span>Power</span>
                      <strong>{formatPower(device.power_watts)}</strong>
                    </div>
                  </div>
                </article>
              ))
            ) : (
              <p className="empty-hint">No GPU metrics are available yet. Confirm that dcgm-exporter is running and Prometheus is scraping it.</p>
            )}
          </div>
        </div>

        <div className="panel">
          <div className="panel-heading">
            <div>
              <h2>Model Service Status</h2>
              <p className="panel-meta">Use model reachability with GPU load to tell apart healthy load, idle GPUs, and service faults.</p>
            </div>
          </div>
          <div className="panel-list">
            {data?.model_services.map((service) => (
              <article className="list-row" key={service.name}>
                <div>
                  <strong>{service.name}</strong>
                  <p>{service.base_url}</p>
                  <p>{service.detail}</p>
                </div>
                <div className="row-meta">
                  <span>{service.response_ms != null ? `${service.response_ms} ms` : "-"}</span>
                  <StatusPill status={service.status} />
                </div>
              </article>
            )) ?? <p className="empty-hint">No model status data is available.</p>}
          </div>
        </div>
      </div>
    </section>
  );
}
