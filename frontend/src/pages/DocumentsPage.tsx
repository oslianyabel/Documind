import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";

import { api, ApiError } from "../api";
import { useApiKey, useAuth } from "../auth";
import { formatBytes, formatDate, statusLabel } from "../format";
import type { DocumentResponse } from "../types";

const PAGE_SIZE = 20;

export function DocumentsPage() {
  const apiKey = useApiKey();
  const { clearApiKey } = useAuth();

  const [documents, setDocuments] = useState<DocumentResponse[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [nameFilter, setNameFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const pollRef = useRef<number | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await api.listDocuments(apiKey, {
        name: nameFilter || undefined,
        status: statusFilter || undefined,
        limit: PAGE_SIZE,
        offset,
      });
      setDocuments(result.items);
      setTotal(result.total);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) clearApiKey();
      else setError(err instanceof Error ? err.message : "Error al listar documentos.");
    } finally {
      setLoading(false);
    }
  }, [apiKey, nameFilter, statusFilter, offset, clearApiKey]);

  useEffect(() => {
    void load();
  }, [load]);

  // Auto-refresh while any document is still being ingested.
  useEffect(() => {
    const anyProcessing = documents.some((doc) => doc.status === "processing");
    if (anyProcessing && pollRef.current === null) {
      pollRef.current = window.setInterval(() => void load(), 3000);
    }
    if (!anyProcessing && pollRef.current !== null) {
      window.clearInterval(pollRef.current);
      pollRef.current = null;
    }
    return () => {
      if (pollRef.current !== null) {
        window.clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, [documents, load]);

  async function handleDelete(name: string) {
    if (!window.confirm(`¿Eliminar el documento "${name}"?`)) return;
    try {
      await api.deleteDocument(apiKey, name);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al eliminar.");
    }
  }

  return (
    <div className="stack">
      <UploadForm apiKey={apiKey} onUploaded={() => void load()} onError={setError} />

      <section className="panel">
        <div className="panel-head">
          <h2>Documentos ({total})</h2>
          <div className="filters">
            <input
              placeholder="Filtrar por nombre"
              value={nameFilter}
              onChange={(e) => {
                setOffset(0);
                setNameFilter(e.target.value);
              }}
            />
            <select
              value={statusFilter}
              onChange={(e) => {
                setOffset(0);
                setStatusFilter(e.target.value);
              }}
            >
              <option value="">Todos los estados</option>
              <option value="ready">Listo</option>
              <option value="processing">Procesando</option>
              <option value="failed">Fallido</option>
            </select>
            <button onClick={() => void load()} disabled={loading}>
              Refrescar
            </button>
          </div>
        </div>

        {error && <p className="error">{error}</p>}

        <table className="grid">
          <thead>
            <tr>
              <th>Nombre</th>
              <th>Estado</th>
              <th>Págs</th>
              <th>Chunks</th>
              <th>Tamaño</th>
              <th>Búsquedas</th>
              <th>Subido</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {documents.map((doc) => (
              <tr key={doc.id}>
                <td>
                  <strong>{doc.name}</strong>
                  {doc.summary && <div className="muted clamp">{doc.summary}</div>}
                </td>
                <td>
                  <span className={`badge badge-${doc.status}`}>
                    {statusLabel(doc.status)}
                  </span>
                </td>
                <td>{doc.page_count}</td>
                <td>{doc.chunk_count}</td>
                <td>{formatBytes(doc.size_bytes)}</td>
                <td>{doc.search_hit_count}</td>
                <td className="muted">{formatDate(doc.created_at)}</td>
                <td>
                  <button className="danger" onClick={() => void handleDelete(doc.name)}>
                    Eliminar
                  </button>
                </td>
              </tr>
            ))}
            {documents.length === 0 && !loading && (
              <tr>
                <td colSpan={8} className="muted center">
                  No hay documentos.
                </td>
              </tr>
            )}
          </tbody>
        </table>

        <div className="pager">
          <button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>
            ← Anteriores
          </button>
          <span className="muted">
            {offset + 1}–{Math.min(offset + PAGE_SIZE, total)} de {total}
          </span>
          <button
            disabled={offset + PAGE_SIZE >= total}
            onClick={() => setOffset(offset + PAGE_SIZE)}
          >
            Siguientes →
          </button>
        </div>
      </section>
    </div>
  );
}

function UploadForm({
  apiKey,
  onUploaded,
  onError,
}: {
  apiKey: string;
  onUploaded: () => void;
  onError: (message: string) => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [cover, setCover] = useState<File | null>(null);
  const [name, setName] = useState("");
  const [author, setAuthor] = useState("");
  const [year, setYear] = useState("");
  const [category, setCategory] = useState("");
  const [language, setLanguage] = useState("");
  const [uploading, setUploading] = useState(false);
  const [notice, setNotice] = useState<{ text: string; warn: boolean } | null>(null);
  const formRef = useRef<HTMLFormElement>(null);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!file) return;
    setUploading(true);
    setNotice(null);
    onError("");
    try {
      const { document, isDuplicate } = await api.uploadDocument(
        apiKey,
        file,
        {
          name: name || undefined,
          author: author || undefined,
          publication_year: year || undefined,
          category: category || undefined,
          language: language || undefined,
        },
        cover,
      );
      formRef.current?.reset();
      setFile(null);
      setCover(null);
      setName("");
      setAuthor("");
      setYear("");
      setCategory("");
      setLanguage("");
      if (isDuplicate) {
        setNotice({
          text: `Este documento ya existía como «${document.name}» y no se ha vuelto a procesar.`,
          warn: true,
        });
      } else {
        setNotice({
          text: `«${document.name}» subido correctamente; se está indexando.`,
          warn: false,
        });
      }
      onUploaded();
    } catch (err) {
      onError(err instanceof Error ? err.message : "Error al subir el documento.");
    } finally {
      setUploading(false);
    }
  }

  return (
    <section className="panel">
      <h2>Subir documento</h2>
      <form ref={formRef} className="upload-form" onSubmit={handleSubmit}>
        <div className="field">
          <label>PDF *</label>
          <input
            type="file"
            accept="application/pdf,.pdf"
            required
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
        </div>
        <div className="field">
          <label>Nombre (opcional)</label>
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Auto del archivo" />
        </div>
        <div className="field">
          <label>Autor</label>
          <input value={author} onChange={(e) => setAuthor(e.target.value)} />
        </div>
        <div className="field">
          <label>Año</label>
          <input value={year} onChange={(e) => setYear(e.target.value)} inputMode="numeric" />
        </div>
        <div className="field">
          <label>Categoría</label>
          <input value={category} onChange={(e) => setCategory(e.target.value)} />
        </div>
        <div className="field">
          <label>Idioma</label>
          <input value={language} onChange={(e) => setLanguage(e.target.value)} placeholder="es" />
        </div>
        <div className="field">
          <label>Portada (opcional)</label>
          <input
            type="file"
            accept="image/*"
            onChange={(e) => setCover(e.target.files?.[0] ?? null)}
          />
        </div>
        <div className="field field-submit">
          <button type="submit" disabled={uploading || !file}>
            {uploading ? "Subiendo…" : "Subir e indexar"}
          </button>
        </div>
      </form>
      {notice && (
        <p className={notice.warn ? "notice notice-warn" : "notice notice-ok"}>{notice.text}</p>
      )}
      <p className="muted">
        La ingesta (embeddings + resumen) corre en segundo plano; el estado pasará de
        «Procesando» a «Listo» automáticamente.
      </p>
    </section>
  );
}
