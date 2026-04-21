import { FormEvent, useEffect, useState } from "react";
import { apiRequest } from "../api/client";
import { PageHeader } from "../components/PageHeader";
import { useAuth } from "../hooks/useAuth";

type KnowledgeBase = {
  id: number;
  name: string;
  description: string;
  chunk_size: number;
  chunk_overlap: number;
  retrieval_top_k: number;
};

const defaultForm = {
  name: "",
  description: "",
  chunk_size: 800,
  chunk_overlap: 120,
  retrieval_top_k: 6
};

export function KnowledgeBasesPage() {
  const { session, canWriteKnowledge } = useAuth();
  const [items, setItems] = useState<KnowledgeBase[]>([]);
  const [form, setForm] = useState(defaultForm);
  const [error, setError] = useState("");

  const load = async () => {
    const data = await apiRequest<KnowledgeBase[]>("/api/kb", { method: "GET" }, session);
    setItems(data);
  };

  useEffect(() => {
    void load();
  }, [session]);

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (!canWriteKnowledge) {
      return;
    }
    try {
      await apiRequest("/api/kb", { method: "POST", body: JSON.stringify(form) }, session);
      setForm(defaultForm);
      setError("");
      await load();
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "创建知识库失败。");
    }
  };

  return (
    <section className="page">
      <PageHeader title="知识库" subtitle="管理切块参数、检索 Top-K 和文档归属。" />
      {error ? <div className="error-banner">{error}</div> : null}
      <div className="two-column">
        <div className="panel">
          <h2>知识库列表</h2>
          <div className="panel-list">
            {items.length === 0 ? <p className="empty-hint">暂无知识库。</p> : null}
            {items.map((item) => (
              <article className="list-row" key={item.id}>
                <div>
                  <strong>{item.name}</strong>
                  <p>{item.description || "暂无描述"}</p>
                </div>
                <div className="row-meta">
                  <span>Chunk {item.chunk_size}</span>
                  <span>Top-K {item.retrieval_top_k}</span>
                </div>
              </article>
            ))}
          </div>
        </div>
        <form className="panel form-grid" onSubmit={handleSubmit}>
          <h2>新建知识库</h2>
          {!canWriteKnowledge ? <p className="panel-meta">当前角色只有只读权限，不能创建知识库。</p> : null}
          <label>
            名称
            <input value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} disabled={!canWriteKnowledge} />
          </label>
          <label>
            描述
            <textarea value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} disabled={!canWriteKnowledge} />
          </label>
          <label>
            Chunk Size
            <input
              type="number"
              value={form.chunk_size}
              onChange={(event) => setForm({ ...form, chunk_size: Number(event.target.value) })}
              disabled={!canWriteKnowledge}
            />
          </label>
          <label>
            Chunk Overlap
            <input
              type="number"
              value={form.chunk_overlap}
              onChange={(event) => setForm({ ...form, chunk_overlap: Number(event.target.value) })}
              disabled={!canWriteKnowledge}
            />
          </label>
          <label>
            Top-K
            <input
              type="number"
              value={form.retrieval_top_k}
              onChange={(event) => setForm({ ...form, retrieval_top_k: Number(event.target.value) })}
              disabled={!canWriteKnowledge}
            />
          </label>
          <button className="primary-button" type="submit" disabled={!canWriteKnowledge}>
            创建
          </button>
        </form>
      </div>
    </section>
  );
}
