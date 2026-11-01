import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useIndex } from "../App";
import type { SearchResult } from "../data";

export function SearchPage() {
  const index = useIndex();
  const [query, setQuery] = useState("");

  const results = useMemo(() => index.search(query), [index, query]);
  const grouped = useMemo(() => groupResults(results), [results]);

  const { relations, routines, triggers } = index.bundle;
  const tables = relations.filter((r) => r.kind === "table");
  const views = relations.filter((r) => r.kind !== "table");

  return (
    <div className="search-page">
      <div className="hero">
        <h1 className="hero-title">Explore {index.bundle.meta.db_name}</h1>
        <p className="hero-sub">
          Search every table, column, and function. Follow what reads and writes what.
        </p>
      </div>

      <div className="search-wrap">
        <span className="search-icon" aria-hidden="true">
          ⌕
        </span>
        <input
          className="search-box"
          placeholder="Search tables, columns, functions…"
          value={query}
          autoFocus
          onChange={(e) => setQuery(e.target.value)}
          aria-label="Search the schema"
        />
        {query && (
          <button className="search-clear" onClick={() => setQuery("")} aria-label="Clear search">
            ×
          </button>
        )}
      </div>

      {!query && (
        <section className="overview">
          <div className="stat-cards">
            <StatCard n={relations.length} label="relations" tone="read" />
            <StatCard n={routines.length} label="routines" tone="write" />
            <StatCard n={triggers.length} label="triggers" tone="trigger" />
          </div>

          <div className="browse">
            <BrowseGroup title="Tables" count={tables.length}>
              {tables.map((r) => (
                <RelationItem key={r.id} id={r.id} name={r.id} kind={r.kind} />
              ))}
            </BrowseGroup>

            {views.length > 0 && (
              <BrowseGroup title="Views & materialized views" count={views.length}>
                {views.map((r) => (
                  <RelationItem key={r.id} id={r.id} name={r.id} kind={r.kind} />
                ))}
              </BrowseGroup>
            )}

            <BrowseGroup title="Routines" count={routines.length}>
              {routines.map((r) => (
                <li key={r.id}>
                  <Link to={`/r/${encodeURIComponent(r.id)}`}>
                    {r.schema}.{r.name}
                  </Link>
                  <span className="tag">{r.language}</span>
                  {r.flags.some((f) => f.kind === "dynamic_sql") && (
                    <span className="tag tag-warn">dynamic</span>
                  )}
                </li>
              ))}
            </BrowseGroup>
          </div>
        </section>
      )}

      {query && (
        <section className="results">
          <p className="result-count muted">
            {results.length === 0
              ? "No matches."
              : `${results.length} result${results.length === 1 ? "" : "s"} for “${query}”`}
          </p>
          <Group title="Relations" items={grouped.relation} kind="relation" />
          <Group title="Columns" items={grouped.column} kind="column" />
          <Group title="Routines" items={grouped.routine} kind="routine" />
        </section>
      )}
    </div>
  );
}

function StatCard({ n, label, tone }: { n: number; label: string; tone: string }) {
  return (
    <div className={`stat-card tone-${tone}`}>
      <strong>{n}</strong>
      <span>{label}</span>
    </div>
  );
}

function RelationItem({ id, name, kind }: { id: string; name: string; kind: string }) {
  return (
    <li>
      <Link to={`/t/${encodeURIComponent(id)}`}>{name}</Link>
      <span className="tag">{kind}</span>
    </li>
  );
}

function BrowseGroup({
  title,
  count,
  children,
}: {
  title: string;
  count: number;
  children: React.ReactNode;
}) {
  return (
    <div className="browse-group">
      <h2>
        {title} <span className="count">{count}</span>
      </h2>
      <ul className="link-list">{children}</ul>
    </div>
  );
}

function Group({
  title,
  items,
  kind,
}: {
  title: string;
  items: SearchResult[];
  kind: SearchResult["type"];
}) {
  if (items.length === 0) return null;
  return (
    <div className="result-group">
      <h3>
        {title} <span className="count">{items.length}</span>
      </h3>
      <ul className="link-list">
        {items.map((item, i) => (
          <li key={`${item.id}-${item.label}-${i}`}>
            <Link to={linkFor(kind, item.id)}>{item.label}</Link>
            <span className="tag">{item.context}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function linkFor(kind: SearchResult["type"], id: string): string {
  if (kind === "routine") return `/r/${encodeURIComponent(id)}`;
  return `/t/${encodeURIComponent(id)}`;
}

function groupResults(results: SearchResult[]) {
  return {
    relation: results.filter((r) => r.type === "relation"),
    column: results.filter((r) => r.type === "column"),
    routine: results.filter((r) => r.type === "routine"),
  };
}
