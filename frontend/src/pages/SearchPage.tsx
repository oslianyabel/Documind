import { useState, type FormEvent } from "react";

import { api, ApiError } from "../api";
import { useApiKey, useAuth } from "../auth";
import type { DocumentResponse, SearchResponse } from "../types";

export function SearchPage() {
  const apiKey = useApiKey();
  const { clearApiKey } = useAuth();
  const [query, setQuery] = useState("");
  const [result, setResult] = useState<SearchResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [searching, setSearching] = useState(false);

  const [downloading, setDownloading] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const trimmed = query.trim();
    if (!trimmed) return;
    setSearching(true);
    setError(null);
    try {
      setResult(await api.search(apiKey, trimmed));
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) clearApiKey();
      else setError(err instanceof Error ? err.message : "Error en la búsqueda.");
    } finally {
      setSearching(false);
    }
  }

  async function handleDownload(doc: DocumentResponse) {
    setDownloading(doc.id);
    setError(null);
    try {
      const blob = await api.downloadDocument(apiKey, doc.download_url);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = doc.original_filename;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) clearApiKey();
      else setError(err instanceof Error ? err.message : "Error al descargar.");
    } finally {
      setDownloading(null);
    }
  }

  return (
    <div className="stack">
      <section className="panel">
        <h2>Búsqueda semántica</h2>
        <form className="search-form" onSubmit={handleSubmit}>
          <input
            placeholder="Describe lo que buscas en lenguaje natural…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            autoFocus
          />
          <button type="submit" disabled={searching || !query.trim()}>
            {searching ? "Buscando…" : "Buscar"}
          </button>
        </form>
        {error && <p className="error">{error}</p>}
      </section>

      {result && (
        <>
          <section className="panel">
            <div className="metrics">
              <div>
                <span className="metric-value">{result.chunks.length}</span>
                <span className="muted">fragmentos</span>
              </div>
              <div>
                <span className="metric-value">{result.documents.length}</span>
                <span className="muted">documentos</span>
              </div>
              <div>
                <span className="metric-value">{result.metadata.embedding_tokens}</span>
                <span className="muted">tokens consulta</span>
              </div>
              <div>
                <span className="metric-value">
                  {result.metadata.total_time_ms.toFixed(0)} ms
                </span>
                <span className="muted">tiempo total</span>
              </div>
            </div>
            {result.documents.length > 0 && (
              <div className="chips">
                {result.documents.map((doc) => (
                  <button
                    key={doc.id}
                    className="chip chip-download"
                    onClick={() => void handleDownload(doc)}
                    disabled={downloading === doc.id}
                    title={`Descargar ${doc.original_filename}`}
                  >
                    ⬇ {doc.name}
                    {downloading === doc.id ? " …" : ""}
                  </button>
                ))}
              </div>
            )}
          </section>

          <section className="panel">
            <h2>Fragmentos relevantes</h2>
            <ol className="results">
              {result.chunks.map((chunk, index) => (
                <li key={index} className="result">
                  <div className="result-head">
                    <strong>{chunk.document_name}</strong>
                    <span className="muted">
                      pág. {chunk.start_page}
                      {chunk.end_page !== chunk.start_page ? `–${chunk.end_page}` : ""} · sim{" "}
                      {chunk.similarity.toFixed(3)}
                    </span>
                  </div>
                  <p className="result-text">{chunk.text}</p>
                </li>
              ))}
              {result.chunks.length === 0 && (
                <li className="muted">Sin coincidencias.</li>
              )}
            </ol>
          </section>
        </>
      )}
    </div>
  );
}
