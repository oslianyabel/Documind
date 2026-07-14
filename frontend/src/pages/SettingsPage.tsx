import { useEffect, useState, type FormEvent } from "react";

import { api, ApiError } from "../api";
import { useApiKey, useAuth } from "../auth";

export function SettingsPage() {
  const apiKey = useApiKey();
  const { clearApiKey } = useAuth();

  // Search-scope guardrail prompt.
  const [prompt, setPrompt] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  // Answer-agent template.
  const [answerPrompt, setAnswerPrompt] = useState("");
  const [answerIsDefault, setAnswerIsDefault] = useState(true);
  const [answerLoading, setAnswerLoading] = useState(true);
  const [answerSaving, setAnswerSaving] = useState(false);
  const [answerError, setAnswerError] = useState<string | null>(null);
  const [answerNotice, setAnswerNotice] = useState<string | null>(null);

  function handle401OrError(
    err: unknown,
    setter: (message: string) => void,
    fallback: string,
  ) {
    if (err instanceof ApiError && err.status === 401) clearApiKey();
    else setter(err instanceof Error ? err.message : fallback);
  }

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const scope = await api.getSearchScope(apiKey);
        if (!cancelled) setPrompt(scope.prompt ?? "");
      } catch (err) {
        if (!cancelled) handle401OrError(err, setError, "Error al cargar el alcance.");
      } finally {
        if (!cancelled) setLoading(false);
      }
      try {
        const answer = await api.getAnswerPrompt(apiKey);
        if (!cancelled) {
          setAnswerPrompt(answer.prompt);
          setAnswerIsDefault(answer.is_default);
        }
      } catch (err) {
        if (!cancelled) handle401OrError(err, setAnswerError, "Error al cargar el prompt.");
      } finally {
        if (!cancelled) setAnswerLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
      handle401OrError(err, setError, "Error al guardar.");
    } finally {
      setSaving(false);
    }
  }

  async function saveAnswerPrompt(value: string) {
    setAnswerSaving(true);
    setAnswerError(null);
    setAnswerNotice(null);
    try {
      const result = await api.updateAnswerPrompt(apiKey, value);
      setAnswerPrompt(result.prompt);
      setAnswerIsDefault(result.is_default);
      setAnswerNotice(
        result.is_default
          ? "Prompt restaurado al valor por defecto."
          : "Prompt guardado. Se usará en las próximas búsquedas.",
      );
    } catch (err) {
      handle401OrError(err, setAnswerError, "Error al guardar el prompt.");
    } finally {
      setAnswerSaving(false);
    }
  }

  async function handleAnswerSubmit(event: FormEvent) {
    event.preventDefault();
    await saveAnswerPrompt(answerPrompt);
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

      <section className="panel">
        <h2>Prompt del agente de respuestas</h2>
        <p className="muted">
          Plantilla que recibe el agente que redacta la respuesta a partir de la consulta y de
          los fragmentos más relevantes. Debe incluir los marcadores{" "}
          <code>{"{context}"}</code> (los fragmentos recuperados) y <code>{"{query}"}</code> (la
          consulta del usuario). Para llaves literales usa <code>{"{{"}</code> y{" "}
          <code>{"}}"}</code>.{" "}
          {answerIsDefault
            ? "Actualmente se usa la plantilla por defecto (mostrada abajo)."
            : "Actualmente se usa una plantilla personalizada."}
        </p>
        <form onSubmit={handleAnswerSubmit} className="stack">
          <textarea
            rows={12}
            value={answerPrompt}
            disabled={answerLoading}
            onChange={(e) => setAnswerPrompt(e.target.value)}
            placeholder="Responde a {query} usando únicamente {context}…"
            spellCheck={false}
          />
          <div className="button-row">
            <button type="submit" disabled={answerSaving || answerLoading}>
              {answerSaving ? "Guardando…" : "Guardar prompt"}
            </button>
            <button
              type="button"
              className="secondary"
              disabled={answerSaving || answerLoading || answerIsDefault}
              onClick={() => saveAnswerPrompt("")}
            >
              Restaurar por defecto
            </button>
          </div>
        </form>
        {answerNotice && <p className="notice notice-ok">{answerNotice}</p>}
        {answerError && <p className="error">{answerError}</p>}
      </section>
    </div>
  );
}
