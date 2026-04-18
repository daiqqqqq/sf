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
  const { session } = useAuth();
  const [items, setItems] = useState<KnowledgeBase[]>([]);
  const [form, setForm] = useState(defaultForm);

  const load = async () => {
    const data = await apiRequest<KnowledgeBase[]>("/api/kb", { method: "GET" }, session);
    setItems(data);
  };

  useEffect(() => {
    void load();
  }, [session]);

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    await apiRequest("/api/kb", { method: "POST", body: JSON.stringify(form) }, session);
    setForm(defaultForm);
    await load();
  };

  return (
    <section className="page">
      <PageHeader title="知识库" subtitle="管理切块参数、检索 Top-K 和后续文档归属。" />
      <div className="two-column">
        <div className="panel">
          <h2>知识库列表</h2>
          <div className="panel-list">
            {items.map((item) => (
              <article className="list-row" key={item.id}>
                <div>
                  <strong>{item.name}</strong>
                  <p>{item.description || "无描述"}</p>
                </div>
                <div className="row-meta">
                  <span>chunk {item.chunk_size}</span>
                  <span>topK {item.retrieval_top_k}</span>
                </div>
              </article>
            ))}
          </div>
        </div>
        <form className="panel form-grid" onSubmit={handleSubmit}>
          <h2>新建知识库</h2>
          <label>
            名称
            <input value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} />
          </label>
          <label>
            描述
            <textarea value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} />
          </label>
          <label>
            Chunk Size
            <input
              type="number"
              value={form.chunk_size}
              onChange={(event) => setForm({ ...form, chunk_size: Number(event.target.value) })}
            />
          </label>
          <label>
            Chunk Overlap
            <input
              type="number"
              value={form.chunk_overlap}
              onChange={(event) => setForm({ ...form, chunk_overlap: Number(event.target.value) })}
            />
          </label>
          <label>
            Top-K
            <input
              type="number"
              value={form.retrieval_top_k}
              onChange={(event) => setForm({ ...form, retrieval_top_k: Number(event.target.value) })}
            />
          </label>
          <button className="primary-button" type="submit">
            创建
          </button>
        </form>
      </div>
    </section>
  );
}

