import { useEffect, useState, type FormEvent } from "react";

import { api, ApiError } from "../api";
import { useApiKey, useAuth } from "../auth";

export function SettingsPage() {
  const apiKey = useApiKey();
  const { clearApiKey } = useAuth();
  const [prompt, setPrompt] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const scope = await api.getSearchScope(apiKey);
        if (!cancelled) setPrompt(scope.prompt ?? "");
      } catch (err) {
        if (err instanceof ApiError && err.status === 401) clearApiKey();
        else if (!cancelled) {
          setError(err instanceof Error ? err.message : "Error al cargar el alcance.");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [apiKey, clearApiKey]);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    setNotice(null);
    try {
      await api.updateSearchScope(apiKey, prompt);
      setNotice(
        prompt.trim()
          ? "Alcance guardado. Las consultas fuera de este alcance serán rechazadas."
          : "Alcance vacío guardado: la validación queda desactivada (se permite todo).",
      );
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) clearApiKey();
      else setError(err instanceof Error ? err.message : "Error al guardar.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="stack">
      <section className="panel">
        <h2>Alcance de las búsquedas semánticas</h2>
        <p className="muted">
          Este texto define qué consultas están permitidas. Un agente IA evalúa cada consulta
          contra este alcance antes de procesarla; las consultas fuera de alcance se rechazan
          y quedan registradas en el historial. Déjalo vacío para permitir cualquier consulta.
        </p>
        <form onSubmit={handleSubmit} className="stack">
          <textarea
            rows={6}
            value={prompt}
            disabled={loading}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder="Ej.: Solo se permiten consultas sobre diagnósticos de vehículos, códigos de avería y contenido de los informes técnicos indexados."
          />
          <div>
            <button type="submit" disabled={saving || loading}>
              {saving ? "Guardando…" : "Guardar alcance"}
            </button>
          </div>
        </form>
        {notice && <p className="notice notice-ok">{notice}</p>}
        {error && <p className="error">{error}</p>}
      </section>
    </div>
  );
}
