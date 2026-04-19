import { FormEvent, useEffect, useState } from "react";
import { apiRequest } from "../api/client";
import { PageHeader } from "../components/PageHeader";
import { StatusPill } from "../components/StatusPill";
import { useAuth } from "../hooks/useAuth";

type KnowledgeBase = { id: number; name: string };
type DocumentItem = {
  id: number;
  kb_id: number;
  filename: string;
  size_bytes: number;
  status: string;
  parser_backend: string;
  error_message: string;
};
type JobItem = {
  id: number;
  document_id: number;
  stage: string;
  status: string;
  retries: number;
  error_message: string;
  updated_at: string;
};

const POLL_MS = 5000;
const QUEUE_STUCK_MS = 120000;
const TASK_STAGES = [
  { key: "queued", label: "排队", description: "等待 worker 接手任务" },
  { key: "parsing", label: "解析", description: "提取文本与结构化内容" },
  { key: "indexing", label: "索引", description: "切块并写入检索库" },
  { key: "completed", label: "完成", description: "任务已经可供检索" }
] as const;

function formatTimestamp(value: string): string {
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
}

function formatStage(stage: string): string {
  const matched = TASK_STAGES.find((item) => item.key === stage);
  return matched?.label ?? stage ?? "未知阶段";
}

function summarizeLatestJob(job: JobItem | null, document: DocumentItem | null, stuck: boolean): string {
  if (!job) {
    return "上传文档后，最近任务会在这里自动显示进度、阶段和异常提醒。";
  }
  if (job.error_message) {
    return job.error_message;
  }
  if (job.status === "failed") {
    return "最近任务执行失败，建议检查文档解析日志和 RAG 引擎服务状态。";
  }
  if (stuck) {
    return "任务排队超过 2 分钟，建议检查 celery-worker、kafka 和 rag-engine 的运行日志。";
  }
  if (job.status === "succeeded" || job.stage === "completed") {
    return `${document?.filename ?? `文档 #${job.document_id}`} 已完成解析和索引，可以直接去 RAG 页面检索。`;
  }
  if (job.stage === "indexing") {
    return "系统正在切块并写入索引，最近任务完成后会自动刷新到最新状态。";
  }
  if (job.stage === "parsing") {
    return "系统正在提取文本内容，完成后会进入索引阶段。";
  }
  return "任务已经创建，正在等待后台服务调度。";
}

function resolveStepState(job: JobItem | null, stepKey: string): "done" | "current" | "todo" | "failed" {
  if (!job) {
    return "todo";
  }
  if (job.status === "failed") {
    return job.stage === stepKey ? "failed" : "todo";
  }
  if (job.status === "succeeded" || job.stage === "completed") {
    return "done";
  }
  const currentIndex = TASK_STAGES.findIndex((item) => item.key === job.stage);
  const stepIndex = TASK_STAGES.findIndex((item) => item.key === stepKey);
  if (currentIndex === -1 || stepIndex === -1) {
    return "todo";
  }
  if (stepIndex < currentIndex) {
    return "done";
  }
  if (stepIndex === currentIndex) {
    return "current";
  }
  return "todo";
}

export function DocumentsPage() {
  const { session } = useAuth();
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([]);
  const [selectedKb, setSelectedKb] = useState<number | "">("");
  const [file, setFile] = useState<File | null>(null);
  const [fileInputKey, setFileInputKey] = useState(0);
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [jobs, setJobs] = useState<JobItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [retryingDocumentId, setRetryingDocumentId] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [lastRefreshedAt, setLastRefreshedAt] = useState("");

  const load = async ({ silent = false }: { silent?: boolean } = {}) => {
    if (!silent) {
      setLoading(true);
    }
    try {
      const [kbData, docData, jobData] = await Promise.all([
        apiRequest<KnowledgeBase[]>("/api/kb", { method: "GET" }, session),
        apiRequest<DocumentItem[]>("/api/documents", { method: "GET" }, session),
        apiRequest<JobItem[]>("/api/jobs", { method: "GET" }, session)
      ]);

      setKnowledgeBases(kbData);
      setDocuments(docData);
      setJobs(jobData);
      setSelectedKb((current) => (current === "" && kbData.length > 0 ? kbData[0].id : current));
      setLastRefreshedAt(new Date().toLocaleTimeString());
      if (error) {
        setError("");
      }
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "加载任务数据失败");
    } finally {
      if (!silent) {
        setLoading(false);
      }
    }
  };

  useEffect(() => {
    void load();
    const timer = window.setInterval(() => {
      void load({ silent: true });
    }, POLL_MS);

    return () => {
      window.clearInterval(timer);
    };
  }, [session]);

  const handleUpload = async (event: FormEvent) => {
    event.preventDefault();
    if (!file || !selectedKb) {
      return;
    }
    setUploading(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
      await apiRequest(`/api/documents/upload?kb_id=${selectedKb}`, { method: "POST", body: formData }, session);
      setFile(null);
      setFileInputKey((current) => current + 1);
      await load();
    } catch (uploadError) {
      setError(uploadError instanceof Error ? uploadError.message : "上传失败");
    } finally {
      setUploading(false);
    }
  };

  const retry = async (documentId: number) => {
    setRetryingDocumentId(documentId);
    try {
      await apiRequest(`/api/documents/${documentId}/retry`, { method: "POST" }, session);
      await load();
    } catch (retryError) {
      setError(retryError instanceof Error ? retryError.message : "重试失败");
    } finally {
      setRetryingDocumentId(null);
    }
  };

  const isLikelyStuck = (job: JobItem) =>
    (job.status === "pending" || job.status === "queued") &&
    Date.now() - new Date(job.updated_at).getTime() > QUEUE_STUCK_MS;

  const latestJob = jobs[0] ?? null;
  const latestDocument = latestJob ? documents.find((item) => item.id === latestJob.document_id) ?? null : null;
  const activeKbId = latestDocument?.kb_id ?? (typeof selectedKb === "number" ? selectedKb : null);
  const activeKnowledgeBase = activeKbId
    ? knowledgeBases.find((item) => item.id === activeKbId) ?? null
    : null;
  const latestJobIsStuck = latestJob ? isLikelyStuck(latestJob) : false;
  const latestJobSummary = summarizeLatestJob(latestJob, latestDocument, latestJobIsStuck);
  const selectedFileSummary = file
    ? `${file.name} · ${Math.max(1, Math.round(file.size / 1024))} KB`
    : "选择文件后会立即创建任务，并自动进入解析与索引流程。";

  return (
    <section className="page">
      <PageHeader
        title="文档与任务"
        subtitle="上传文档后进入解析、切块和索引链路，左侧会自动跟随最近任务展示当前处理进度。"
      />
      {error ? <div className="error-banner">{error}</div> : null}

      <div className="two-column document-workspace">
        <form className="panel form-grid upload-panel" onSubmit={handleUpload}>
          <div className="panel-heading">
            <div>
              <h2>上传文档</h2>
              <p className="panel-meta">选择知识库和文件后，最近任务卡会自动切换到最新的处理状态。</p>
            </div>
            {latestJob ? <StatusPill status={latestJob.status} /> : null}
          </div>

          <label>
            目标知识库
            <select value={selectedKb} onChange={(event) => setSelectedKb(Number(event.target.value))}>
              {knowledgeBases.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
          </label>

          <label>
            文件
            <input
              key={fileInputKey}
              type="file"
              onChange={(event) => setFile(event.target.files?.[0] ?? null)}
            />
          </label>

          <div className="file-chip">{selectedFileSummary}</div>

          <button className="primary-button" type="submit" disabled={uploading || loading || !selectedKb}>
            {uploading ? "上传中..." : "上传并入队"}
          </button>

          <div className="task-spotlight">
            <div className="task-spotlight-header">
              <div>
                <span className="section-kicker">最新任务</span>
                <strong>{latestJob ? `任务 #${latestJob.id}` : "等待新任务"}</strong>
              </div>
              {latestJob ? <StatusPill status={latestJob.status} /> : null}
            </div>

            <p className="spotlight-copy">{latestJobSummary}</p>

            <div className="spotlight-grid">
              <div className="spotlight-metric">
                <span>文档</span>
                <strong>{latestDocument?.filename ?? "--"}</strong>
              </div>
              <div className="spotlight-metric">
                <span>知识库</span>
                <strong>{activeKnowledgeBase?.name ?? "--"}</strong>
              </div>
              <div className="spotlight-metric">
                <span>当前阶段</span>
                <strong>{latestJob ? formatStage(latestJob.stage) : "--"}</strong>
              </div>
              <div className="spotlight-metric">
                <span>最近刷新</span>
                <strong>{lastRefreshedAt || "--"}</strong>
              </div>
            </div>

            <div className="task-track">
              {TASK_STAGES.map((step) => {
                const stepState = resolveStepState(latestJob, step.key);
                return (
                  <article className={`task-step ${stepState}`} key={step.key}>
                    <span className="task-step-label">{step.label}</span>
                    <strong>{stepState === "current" ? "进行中" : stepState === "done" ? "已完成" : stepState === "failed" ? "失败" : "等待中"}</strong>
                    <small>{step.description}</small>
                  </article>
                );
              })}
            </div>
          </div>
        </form>

        <div className="panel">
          <h2>最近任务</h2>
          <p className="panel-meta">
            每 {Math.floor(POLL_MS / 1000)} 秒自动刷新
            {lastRefreshedAt ? ` · 最近刷新 ${lastRefreshedAt}` : ""}
          </p>

          <div className="panel-list">
            {jobs.length === 0 ? (
              <p className="empty-hint">暂无任务，上传文档后会自动出现在这里。</p>
            ) : (
              jobs.map((job) => {
                const relatedDocument = documents.find((item) => item.id === job.document_id) ?? null;
                return (
                  <article className={`list-row task-row${job.id === latestJob?.id ? " active" : ""}`} key={job.id}>
                    <div>
                      <strong>任务 #{job.id}</strong>
                      <p>
                        {relatedDocument?.filename ?? `文档 #${job.document_id}`} · {formatStage(job.stage)} ·{" "}
                        {formatTimestamp(job.updated_at)}
                      </p>
                      {job.error_message ? <p className="inline-error">{job.error_message}</p> : null}
                      {isLikelyStuck(job) ? (
                        <p className="inline-hint">
                          排队超过 2 分钟，建议检查 `celery-worker`、`kafka` 和 `rag-engine` 日志。
                        </p>
                      ) : null}
                    </div>
                    <div className="row-meta">
                      <span>重试 {job.retries}</span>
                      <StatusPill status={job.status} />
                    </div>
                  </article>
                );
              })
            )}
          </div>
        </div>
      </div>

      <div className="table-panel">
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>文件名</th>
              <th>知识库</th>
              <th>状态</th>
              <th>解析后端</th>
              <th>大小</th>
              <th>动作</th>
            </tr>
          </thead>
          <tbody>
            {documents.map((item) => (
              <tr key={item.id}>
                <td>{item.id}</td>
                <td>{item.filename}</td>
                <td>{item.kb_id}</td>
                <td>
                  <StatusPill status={item.status} />
                </td>
                <td>{item.parser_backend}</td>
                <td>{Math.round(item.size_bytes / 1024)} KB</td>
                <td>
                  <button
                    className="ghost-button"
                    onClick={() => void retry(item.id)}
                    type="button"
                    disabled={retryingDocumentId === item.id}
                  >
                    {retryingDocumentId === item.id ? "重试中..." : "重试"}
                  </button>
                  {item.error_message ? <p className="inline-error">{item.error_message}</p> : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
