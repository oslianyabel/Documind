import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { api, ApiError, coverHref, downloadHref } from "../api";
import { useApiKey, useAuth } from "../auth";
import { formatBytes, formatDate, statusLabel } from "../format";
import type { DocumentResponse } from "../types";

export function DocumentDetailPage() {
  const { name = "" } = useParams();
  const navigate = useNavigate();
  const apiKey = useApiKey();
  const { clearApiKey } = useAuth();

  const [doc, setDoc] = useState<DocumentResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const pollRef = useRef<number | null>(null);

  const load = useCallback(async () => {
    try {
      setDoc(await api.getDocument(apiKey, name));
      setError(null);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) clearApiKey();
      else if (err instanceof ApiError && err.status === 404) {
        setError(`El documento «${name}» no existe o fue eliminado.`);
      } else setError(err instanceof Error ? err.message : "Error al cargar el documento.");
    } finally {
      setLoading(false);
    }
  }, [apiKey, name, clearApiKey]);

  useEffect(() => {
    void load();
  }, [load]);

  // Auto-refresh while the ingestion worker is still processing it.
  useEffect(() => {
    const processing = doc?.status === "processing";
    if (processing && pollRef.current === null) {
      pollRef.current = window.setInterval(() => void load(), 3000);
    }
    if (!processing && pollRef.current !== null) {
      window.clearInterval(pollRef.current);
      pollRef.current = null;
    }
    return () => {
      if (pollRef.current !== null) {
        window.clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, [doc, load]);

  async function handleDelete() {
    if (!doc) return;
    if (!window.confirm(`¿Eliminar el documento "${doc.name}"?`)) return;
    try {
      await api.deleteDocument(apiKey, doc.name);
      navigate("/documents");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al eliminar.");
    }
  }

  return (
    <div className="stack">
      <section className="panel">
        <div className="panel-head">
          <h2>
            <Link to="/documents" className="back-link">
              ← Documentos
            </Link>{" "}
            / {name}
          </h2>
          {doc && (
            <div className="filters">
              <a className="button-link" href={downloadHref(doc.download_url)} download>
                ⬇ Descargar PDF
              </a>
              <button className="danger" onClick={() => void handleDelete()}>
                Eliminar
              </button>
            </div>
          )}
        </div>

        {error && <p className="error">{error}</p>}
        {loading && <p className="muted">Cargando…</p>}

        {doc && (
          <div className="detail-layout">
            {doc.has_cover_image && (
              <img
                className="detail-cover"
                src={coverHref(doc.name)}
                alt={`Portada de ${doc.name}`}
              />
            )}
            <div className="detail-main">
              <div className="detail-badges">
                <span className={`badge badge-${doc.status}`}>{statusLabel(doc.status)}</span>
                <span className="chip">{doc.chunk_count} chunks</span>
                <span className="chip">{doc.page_count} páginas</span>
                <span className="chip">{formatBytes(doc.size_bytes)}</span>
                <span className="chip">{doc.search_hit_count} búsquedas</span>
              </div>

              {doc.summary && (
                <div className="answer-panel">
                  <span className="answer-label">Resumen IA</span>
                  {doc.summary}
                </div>
              )}

              <dl className="detail-grid">
                <dt>Nombre</dt>
                <dd>{doc.name}</dd>
                <dt>Archivo original</dt>
                <dd>{doc.original_filename}</dd>
                <dt>Tipo</dt>
                <dd>{doc.mime_type}</dd>
                <dt>Estado</dt>
                <dd>{statusLabel(doc.status)}</dd>
                <dt>Páginas</dt>
                <dd>{doc.page_count}</dd>
                <dt>Chunks asociados</dt>
                <dd>{doc.chunk_count}</dd>
                <dt>Tamaño</dt>
                <dd>
                  {formatBytes(doc.size_bytes)} ({doc.size_bytes.toLocaleString("es")} bytes)
                </dd>
                <dt>Tokens de embeddings</dt>
                <dd>{doc.embedding_tokens_used.toLocaleString("es")}</dd>
                <dt>Autor</dt>
                <dd>{doc.author ?? "—"}</dd>
                <dt>Año de publicación</dt>
                <dd>{doc.publication_year ?? "—"}</dd>
                <dt>Categoría</dt>
                <dd>{doc.category ?? "—"}</dd>
                <dt>Idioma</dt>
                <dd>{doc.language ?? "—"}</dd>
                <dt>Descripción</dt>
                <dd>{doc.description ?? "—"}</dd>
                <dt>Búsquedas con coincidencia</dt>
                <dd>{doc.search_hit_count}</dd>
                <dt>Subido</dt>
                <dd>{formatDate(doc.created_at)}</dd>
                <dt>SHA-256</dt>
                <dd className="mono">{doc.sha256}</dd>
                <dt>Enlace de descarga</dt>
                <dd>
                  <a href={downloadHref(doc.download_url)} download>
                    {downloadHref(doc.download_url)}
                  </a>
                </dd>
              </dl>
            </div>
          </div>
        )}
      </section>
    </div>
  );
}
