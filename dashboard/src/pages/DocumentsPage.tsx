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

export function DocumentsPage() {
  const { session, canUploadDocuments } = useAuth();
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
      setError("");
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "加载文档与任务失败。");
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
    return () => window.clearInterval(timer);
  }, [session]);

  const handleUpload = async (event: FormEvent) => {
    event.preventDefault();
    if (!file || !selectedKb || !canUploadDocuments) {
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
      setError(uploadError instanceof Error ? uploadError.message : "上传失败。");
    } finally {
      setUploading(false);
    }
  };

  const retry = async (documentId: number) => {
    if (!canUploadDocuments) {
      return;
    }
    setRetryingDocumentId(documentId);
    try {
      await apiRequest(`/api/documents/${documentId}/retry`, { method: "POST" }, session);
      await load();
    } catch (retryError) {
      setError(retryError instanceof Error ? retryError.message : "重试失败。");
    } finally {
      setRetryingDocumentId(null);
    }
  };

  const latestJob = jobs[0] ?? null;

  return (
    <section className="page">
      <PageHeader title="文档与任务" subtitle="上传文档后自动进入解析、切块和混合索引链路。" />
      {error ? <div className="error-banner">{error}</div> : null}

      <div className="two-column">
        <form className="panel form-grid" onSubmit={handleUpload}>
          <h2>上传文档</h2>
          {!canUploadDocuments ? <p className="panel-meta">当前角色只有只读权限，不能上传或重试任务。</p> : null}
          <label>
            目标知识库
            <select value={selectedKb} onChange={(event) => setSelectedKb(Number(event.target.value))} disabled={!canUploadDocuments}>
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
              disabled={!canUploadDocuments}
            />
          </label>
          <button className="primary-button" type="submit" disabled={!canUploadDocuments || uploading || loading || !selectedKb}>
            {uploading ? "上传中..." : "上传并入队"}
          </button>
        </form>

        <div className="panel">
          <h2>任务概览</h2>
          <p className="panel-meta">
            每 {Math.floor(POLL_MS / 1000)} 秒自动刷新
            {lastRefreshedAt ? ` · 最近刷新 ${lastRefreshedAt}` : ""}
          </p>
          {latestJob ? (
            <div className="panel-list">
              <article className="list-row">
                <div>
                  <strong>最新任务 #{latestJob.id}</strong>
                  <p>{latestJob.stage}</p>
                </div>
                <div className="row-meta">
                  <span>{new Date(latestJob.updated_at).toLocaleString()}</span>
                  <StatusPill status={latestJob.status} />
                </div>
              </article>
              {latestJob.error_message ? <div className="inline-error">{latestJob.error_message}</div> : null}
            </div>
          ) : (
            <p className="empty-hint">暂无任务。</p>
          )}
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
                    disabled={!canUploadDocuments || retryingDocumentId === item.id}
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

      <div className="table-panel">
        <table>
          <thead>
            <tr>
              <th>任务 ID</th>
              <th>文档 ID</th>
              <th>阶段</th>
              <th>状态</th>
              <th>重试次数</th>
              <th>更新时间</th>
            </tr>
          </thead>
          <tbody>
            {jobs.map((job) => (
              <tr key={job.id}>
                <td>{job.id}</td>
                <td>{job.document_id}</td>
                <td>{job.stage}</td>
                <td>
                  <StatusPill status={job.status} />
                </td>
                <td>{job.retries}</td>
                <td>{new Date(job.updated_at).toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
