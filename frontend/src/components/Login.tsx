import { useState, type FormEvent } from "react";

import { api, ApiError } from "../api";
import { useAuth } from "../auth";

export function Login() {
  const { setApiKey } = useAuth();
  const [keyInput, setKeyInput] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [verifying, setVerifying] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const trimmed = keyInput.trim();
    if (!trimmed) return;
    setVerifying(true);
    setError(null);
    try {
      await api.verifyKey(trimmed);
      setApiKey(trimmed);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        setError("API key inválida.");
      } else {
        setError(err instanceof Error ? err.message : "No se pudo verificar la API key.");
      }
    } finally {
      setVerifying(false);
    }
  }

  return (
    <div className="login-screen">
      <form className="login-card" onSubmit={handleSubmit}>
        <h1>Launch Intelligence</h1>
        <p className="muted">
          Introduce tu API key para acceder a tus documentos y búsquedas.
        </p>
        <input
          type="password"
          placeholder="X-API-Key"
          value={keyInput}
          onChange={(e) => setKeyInput(e.target.value)}
          autoFocus
        />
        {error && <p className="error">{error}</p>}
        <button type="submit" disabled={verifying || !keyInput.trim()}>
          {verifying ? "Verificando…" : "Entrar"}
        </button>
      </form>
    </div>
  );
}
