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
};

export function DocumentsPage() {
  const { session } = useAuth();
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([]);
  const [selectedKb, setSelectedKb] = useState<number | "">("");
  const [file, setFile] = useState<File | null>(null);
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [jobs, setJobs] = useState<JobItem[]>([]);

  const load = async () => {
    const [kbData, docData, jobData] = await Promise.all([
      apiRequest<KnowledgeBase[]>("/api/kb", { method: "GET" }, session),
      apiRequest<DocumentItem[]>("/api/documents", { method: "GET" }, session),
      apiRequest<JobItem[]>("/api/jobs", { method: "GET" }, session)
    ]);
    setKnowledgeBases(kbData);
    setDocuments(docData);
    setJobs(jobData);
    if (selectedKb === "" && kbData.length > 0) {
      setSelectedKb(kbData[0].id);
    }
  };

  useEffect(() => {
    void load();
  }, [session]);

  const handleUpload = async (event: FormEvent) => {
    event.preventDefault();
    if (!file || !selectedKb) {
      return;
    }
    const formData = new FormData();
    formData.append("file", file);
    await apiRequest(`/api/documents/upload?kb_id=${selectedKb}`, { method: "POST", body: formData }, session);
    setFile(null);
    await load();
  };

  const retry = async (documentId: number) => {
    await apiRequest(`/api/documents/${documentId}/retry`, { method: "POST" }, session);
    await load();
  };

  return (
    <section className="page">
      <PageHeader title="文档与任务" subtitle="上传文档后进入解析、切块、索引链路，并在这里追踪异步任务状态。" />
      <div className="two-column">
        <form className="panel form-grid" onSubmit={handleUpload}>
          <h2>上传文档</h2>
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
            <input type="file" onChange={(event) => setFile(event.target.files?.[0] ?? null)} />
          </label>
          <button className="primary-button" type="submit">
            上传并入队
          </button>
        </form>

        <div className="panel">
          <h2>最近任务</h2>
          <div className="panel-list">
            {jobs.map((job) => (
              <article className="list-row" key={job.id}>
                <div>
                  <strong>任务 #{job.id}</strong>
                  <p>文档 #{job.document_id} · {job.stage}</p>
                </div>
                <div className="row-meta">
                  <span>重试 {job.retries}</span>
                  <StatusPill status={job.status} />
                </div>
              </article>
            ))}
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
                  <button className="ghost-button" onClick={() => void retry(item.id)} type="button">
                    重试
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

