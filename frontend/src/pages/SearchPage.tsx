import { useEffect, useState, type FormEvent } from "react";

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
  // document name -> object URL of its cover image (only for docs that have one)
  const [coverUrls, setCoverUrls] = useState<Record<string, string>>({});

  // Covers are behind the authenticated /cover endpoint, so we fetch each one
  // as a blob and expose it as an object URL, revoking them when results change.
  useEffect(() => {
    if (!result) {
      setCoverUrls({});
      return;
    }
    const withCover = result.documents.filter((doc) => doc.has_cover_image);
    if (withCover.length === 0) {
      setCoverUrls({});
      return;
    }
    let cancelled = false;
    const created: string[] = [];
    (async () => {
      const entries: [string, string][] = [];
      for (const doc of withCover) {
        try {
          const blob = await api.downloadCover(apiKey, doc.name);
          if (cancelled) return;
          const url = URL.createObjectURL(blob);
          created.push(url);
          entries.push([doc.name, url]);
        } catch {
          // A missing/failed cover just means no thumbnail; ignore.
        }
      }
      if (!cancelled) setCoverUrls(Object.fromEntries(entries));
    })();
    return () => {
      cancelled = true;
      created.forEach(URL.revokeObjectURL);
    };
  }, [result, apiKey]);

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

  const docsByName = new Map((result?.documents ?? []).map((doc) => [doc.name, doc]));

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
          </section>

          <section className="panel">
            <h2>Fragmentos relevantes</h2>
            <ol className="results">
              {result.chunks.map((chunk, index) => {
                const doc = docsByName.get(chunk.document_name);
                const coverUrl = coverUrls[chunk.document_name];
                const pageRange =
                  chunk.end_page !== chunk.start_page
                    ? `${chunk.start_page}–${chunk.end_page}`
                    : `${chunk.start_page}`;
                return (
                  <li key={index} className="result-card">
                    {coverUrl && (
                      <img
                        className="result-cover"
                        src={coverUrl}
                        alt={`Portada de ${chunk.document_name}`}
                      />
                    )}
                    <div className="result-body">
                      <div className="result-head">
                        <span className="chunk-badge">chunk{index + 1}</span>
                        <span className="sim-badge">
                          similitud {chunk.similarity.toFixed(3)}
                        </span>
                      </div>
                      <div className="result-doc">
                        <span className="doc-name" title={chunk.document_name}>
                          📄 {chunk.document_name}
                        </span>
                        {doc && (
                          <button
                            className="link-download"
                            onClick={() => void handleDownload(doc)}
                            disabled={downloading === doc.id}
                          >
                            {downloading === doc.id ? "descargando…" : "⬇ descargar"}
                          </button>
                        )}
                      </div>
                      <div className="result-meta muted">
                        pág. {pageRange} · líneas {chunk.start_line}–{chunk.end_line} ·{" "}
                        {chunk.text.length.toLocaleString("es")} letras
                      </div>
                      <details className="result-details">
                        <summary>Ver contenido del fragmento</summary>
                        <pre className="result-text">{chunk.text}</pre>
                      </details>
                    </div>
                  </li>
                );
              })}
              {result.chunks.length === 0 && <li className="muted">Sin coincidencias.</li>}
            </ol>
          </section>
        </>
      )}
    </div>
  );
}
