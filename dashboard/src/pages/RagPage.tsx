import { FormEvent, useEffect, useState } from "react";
import { apiRequest } from "../api/client";
import { PageHeader } from "../components/PageHeader";
import { useAuth } from "../hooks/useAuth";

type KnowledgeBase = { id: number; name: string };
type ModelProvider = { id: number; name: string; kind: string };
type RagResponse = {
  answer: string;
  used_model?: string | null;
  debug: Record<string, unknown>;
  results: Array<{
    chunk_id: number;
    document_id: number;
    score: number;
    source: string;
    content: string;
  }>;
};

export function RagPage() {
  const { session, canRunRag } = useAuth();
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([]);
  const [providers, setProviders] = useState<ModelProvider[]>([]);
  const [kbId, setKbId] = useState<number>(1);
  const [providerId, setProviderId] = useState<number | "">("");
  const [query, setQuery] = useState("这套平台的模型和检索链路如何协作？");
  const [response, setResponse] = useState<RagResponse | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([
      apiRequest<KnowledgeBase[]>("/api/kb", { method: "GET" }, session),
      apiRequest<ModelProvider[]>("/api/models/providers", { method: "GET" }, session)
    ]).then(([kbData, providerData]) => {
      setKnowledgeBases(kbData);
      setProviders(providerData.filter((item) => item.kind === "generation"));
      if (kbData.length > 0) {
        setKbId(kbData[0].id);
      }
    });
  }, [session]);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!canRunRag) {
      return;
    }
    try {
      const data = await apiRequest<RagResponse>(
        "/api/rag/debug",
        {
          method: "POST",
          body: JSON.stringify({
            kb_id: kbId,
            query,
            top_k: 6,
            model_provider_id: providerId || null
          })
        },
        session
      );
      setResponse(data);
      setError("");
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "RAG 调试失败。");
    }
  };

  return (
    <section className="page">
      <PageHeader title="RAG 调试" subtitle="直接验证召回、融合、重排和生成模型路由结果。" />
      {error ? <div className="error-banner">{error}</div> : null}
      <div className="two-column">
        <form className="panel form-grid" onSubmit={submit}>
          <h2>调试参数</h2>
          {!canRunRag ? <p className="panel-meta">当前角色只有只读权限，不能执行 RAG 查询。</p> : null}
          <label>
            知识库
            <select value={kbId} onChange={(event) => setKbId(Number(event.target.value))} disabled={!canRunRag}>
              {knowledgeBases.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            生成模型
            <select value={providerId} onChange={(event) => setProviderId(event.target.value ? Number(event.target.value) : "")} disabled={!canRunRag}>
              <option value="">自动选择</option>
              {providers.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            查询语句
            <textarea value={query} onChange={(event) => setQuery(event.target.value)} disabled={!canRunRag} />
          </label>
          <button className="primary-button" type="submit" disabled={!canRunRag}>
            开始调试
          </button>
        </form>

        <div className="panel">
          <h2>生成回答</h2>
          <p className="answer-box">{response?.answer ?? "提交查询后，在这里查看生成结果。"}</p>
          <div className="key-value">
            <span>使用模型</span>
            <strong>{response?.used_model ?? "-"}</strong>
          </div>
        </div>
      </div>

      <div className="two-column">
        <div className="panel">
          <h2>检索片段</h2>
          <div className="panel-list">
            {response?.results.map((item) => (
              <article key={item.chunk_id} className="rag-result">
                <div className="row-meta">
                  <span>文档 #{item.document_id}</span>
                  <strong>{item.score.toFixed(3)}</strong>
                </div>
                <p>{item.content}</p>
              </article>
            )) ?? <p className="empty-hint">暂无检索结果。</p>}
          </div>
        </div>
        <div className="panel">
          <h2>调试信息</h2>
          <pre className="log-view">{response ? JSON.stringify(response.debug, null, 2) : "暂无调试信息。"}</pre>
        </div>
      </div>
    </section>
  );
}
