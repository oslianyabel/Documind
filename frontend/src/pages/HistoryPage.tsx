import { Fragment, useCallback, useEffect, useState } from "react";

import { api, ApiError } from "../api";
import { useApiKey, useAuth } from "../auth";
import { formatDate } from "../format";
import type { SearchHistoryEntry } from "../types";

const PAGE_SIZE = 20;

export function HistoryPage() {
  const apiKey = useApiKey();
  const { clearApiKey } = useAuth();

  const [entries, setEntries] = useState<SearchHistoryEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [expanded, setExpanded] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await api.searchHistory(apiKey, {
        from_date: fromDate ? new Date(fromDate).toISOString() : undefined,
        to_date: toDate ? new Date(toDate).toISOString() : undefined,
        limit: PAGE_SIZE,
        offset,
      });
      setEntries(result.items);
      setTotal(result.total);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) clearApiKey();
      else setError(err instanceof Error ? err.message : "Error al cargar el historial.");
    } finally {
      setLoading(false);
    }
  }, [apiKey, fromDate, toDate, offset, clearApiKey]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="stack">
      <section className="panel">
        <div className="panel-head">
          <h2>Historial de búsquedas ({total})</h2>
          <div className="filters">
            <label className="inline">
              Desde
              <input
                type="datetime-local"
                value={fromDate}
                onChange={(e) => {
                  setOffset(0);
                  setFromDate(e.target.value);
                }}
              />
            </label>
            <label className="inline">
              Hasta
              <input
                type="datetime-local"
                value={toDate}
                onChange={(e) => {
                  setOffset(0);
                  setToDate(e.target.value);
                }}
              />
            </label>
            <button onClick={() => void load()} disabled={loading}>
              Aplicar
            </button>
          </div>
        </div>

        {error && <p className="error">{error}</p>}

        <table className="grid">
          <thead>
            <tr>
              <th>Fecha</th>
              <th>Consulta</th>
              <th>Resultados</th>
              <th>Tokens</th>
              <th>Tiempo</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {entries.map((entry) => (
              <Fragment key={entry.id}>
                <tr>
                  <td className="muted">{formatDate(entry.created_at)}</td>
                  <td>{entry.query_text}</td>
                  <td>{entry.response?.chunks?.length ?? 0}</td>
                  <td>{entry.embedding_tokens}</td>
                  <td>{entry.duration_ms.toFixed(0)} ms</td>
                  <td>
                    <button
                      className="link-button"
                      onClick={() => setExpanded(expanded === entry.id ? null : entry.id)}
                    >
                      {expanded === entry.id ? "Ocultar" : "Ver"}
                    </button>
                  </td>
                </tr>
                {expanded === entry.id && (
                  <tr>
                    <td colSpan={6}>
                      <div className="history-detail">
                        {(entry.response?.documents ?? []).map((doc) => (
                          <span key={doc.id} className="chip">
                            {doc.name}
                          </span>
                        ))}
                        <ol className="results">
                          {(entry.response?.chunks ?? []).map((chunk, index) => (
                            <li key={index} className="result">
                              <div className="result-head">
                                <strong>{chunk.document_name}</strong>
                                <span className="muted">
                                  pág. {chunk.start_page} · sim {chunk.similarity.toFixed(3)}
                                </span>
                              </div>
                              <p className="result-text clamp">{chunk.text}</p>
                            </li>
                          ))}
                        </ol>
                      </div>
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
            {entries.length === 0 && !loading && (
              <tr>
                <td colSpan={6} className="muted center">
                  Sin búsquedas registradas.
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
            {total === 0 ? 0 : offset + 1}–{Math.min(offset + PAGE_SIZE, total)} de {total}
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
