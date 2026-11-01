import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { Link, Route, Routes } from "react-router-dom";
import { buildIndex, isStatic, loadBundle, type Index } from "./data";
import type { Bundle } from "./types";
import { SearchPage } from "./pages/SearchPage";
import { RelationPage } from "./pages/RelationPage";
import { RoutinePage } from "./pages/RoutinePage";
import { LineagePage } from "./pages/LineagePage";

const IndexContext = createContext<Index | null>(null);

export function useIndex(): Index {
  const ctx = useContext(IndexContext);
  if (!ctx) throw new Error("useIndex must be used within <App>");
  return ctx;
}

export function App() {
  const [bundle, setBundle] = useState<Bundle | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [theme, setTheme] = useState<"light" | "dark">(
    () => (localStorage.getItem("theme") as "light" | "dark") || "light",
  );

  useEffect(() => {
    loadBundle().then(setBundle).catch((e) => setError(String(e)));
  }, []);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("theme", theme);
  }, [theme]);

  const index = useMemo(() => (bundle ? buildIndex(bundle) : null), [bundle]);

  if (error) return <div className="status error">Could not load data: {error}</div>;
  if (!index) return <div className="status">Loading…</div>;

  const version = index.bundle.meta.server_version?.split(" ")[0] ?? "?";

  return (
    <IndexContext.Provider value={index}>
      <header className="topbar">
        <Link to="/" className="brand" aria-label="SchemaLens home">
          <span className="brand-mark" aria-hidden="true">
            ◴
          </span>
          SchemaLens
        </Link>
        <span className="db-label">
          <span className="db-dot" aria-hidden="true" />
          {index.bundle.meta.db_name} · PostgreSQL {version}
          {isStatic && <span className="badge">demo</span>}
        </span>
        <button
          className="theme-toggle"
          onClick={() => setTheme(theme === "light" ? "dark" : "light")}
          aria-label={`Switch to ${theme === "light" ? "dark" : "light"} theme`}
          title="Toggle theme"
        >
          {theme === "light" ? "🌙" : "☀️"}
        </button>
      </header>
      <main className="content">
        <Routes>
          <Route path="/" element={<SearchPage />} />
          <Route path="/t/:relationId" element={<RelationPage />} />
          <Route path="/r/:routineId" element={<RoutinePage />} />
          <Route path="/lineage/:nodeId" element={<LineagePage />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </main>
      <footer className="site-footer">
        <span>
          Only system catalogs were read. Row data is never queried, stored, or sent anywhere.
        </span>
        {index.bundle.meta.scanned_at && (
          <span className="muted">Scanned {formatDate(index.bundle.meta.scanned_at)}</span>
        )}
      </footer>
    </IndexContext.Provider>
  );
}

function NotFound() {
  return (
    <div className="status">
      <p>Nothing here.</p>
      <Link to="/">Back to search</Link>
    </div>
  );
}

function formatDate(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString();
}
