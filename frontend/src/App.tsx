import { NavLink, Navigate, Route, Routes } from "react-router-dom";

import { useAuth } from "./auth";
import { Login } from "./components/Login";
import { DocumentsPage } from "./pages/DocumentsPage";
import { HistoryPage } from "./pages/HistoryPage";
import { SearchPage } from "./pages/SearchPage";

export function App() {
  const { apiKey, clearApiKey } = useAuth();

  if (apiKey === null) {
    return <Login />;
  }

  return (
    <div className="app">
      <header className="topbar">
        <span className="brand">Launch Intelligence</span>
        <nav>
          <NavLink to="/documents">Documentos</NavLink>
          <NavLink to="/search">Búsqueda</NavLink>
          <NavLink to="/history">Historial</NavLink>
        </nav>
        <button className="link-button" onClick={clearApiKey}>
          Cerrar sesión
        </button>
      </header>
      <main className="content">
        <Routes>
          <Route path="/documents" element={<DocumentsPage />} />
          <Route path="/search" element={<SearchPage />} />
          <Route path="/history" element={<HistoryPage />} />
          <Route path="*" element={<Navigate to="/documents" replace />} />
        </Routes>
      </main>
    </div>
  );
}
