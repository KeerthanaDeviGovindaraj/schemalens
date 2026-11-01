import { Link, useParams } from "react-router-dom";
import { useIndex } from "../App";
import { Breadcrumb } from "../components";
import type { Routine } from "../types";

export function RelationPage() {
  const { relationId = "" } = useParams();
  const index = useIndex();
  const rel = index.relationsById.get(relationId);

  if (!rel)
    return (
      <div className="status error">
        <p>Relation not found: {relationId}</p>
        <Link to="/">Back to search</Link>
      </div>
    );

  const reads = index.readsByRelation.get(rel.id) ?? [];
  const writes = index.writesByRelation.get(rel.id) ?? [];
  const triggers = index.triggersByRelation.get(rel.id) ?? [];
  const incoming = index.incomingFks.get(rel.id) ?? [];

  return (
    <article className="detail">
      <Breadcrumb current={rel.id} />
      <header className="detail-head">
        <h1>
          {rel.id} <span className="kind-tag">{rel.kind}</span>
        </h1>
        <Link className="lineage-link" to={`/lineage/${encodeURIComponent(rel.id)}`}>
          View lineage →
        </Link>
      </header>
      {rel.comment && <p className="comment">{rel.comment}</p>}

      <h2>Columns</h2>
      <table className="columns">
        <thead>
          <tr>
            <th>Name</th>
            <th>Type</th>
            <th>Null</th>
            <th>Key</th>
            <th>Default</th>
            <th>Comment</th>
          </tr>
        </thead>
        <tbody>
          {rel.columns.map((c) => (
            <tr key={c.name}>
              <td className="mono">{c.name}</td>
              <td className="mono muted">{c.data_type}</td>
              <td>{c.nullable ? "" : "NOT NULL"}</td>
              <td>{c.is_pk ? "PK" : ""}</td>
              <td className="mono muted">{c.default_expr ?? ""}</td>
              <td className="muted">{c.comment ?? ""}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {rel.foreign_keys.length > 0 && (
        <>
          <h2>Foreign keys (outgoing)</h2>
          <ul className="link-list">
            {rel.foreign_keys.map((fk) => (
              <li key={fk.name}>
                <span className="mono">({fk.from_cols.join(", ")})</span> →{" "}
                <Link to={`/t/${encodeURIComponent(fk.to_relation)}`}>{fk.to_relation}</Link>{" "}
                <span className="mono muted">({fk.to_cols.join(", ")})</span>
              </li>
            ))}
          </ul>
        </>
      )}

      {incoming.length > 0 && (
        <>
          <h2>Referenced by (incoming)</h2>
          <ul className="link-list">
            {incoming.map((ref) => (
              <li key={ref.fk}>
                <Link to={`/t/${encodeURIComponent(ref.from.id)}`}>{ref.from.id}</Link>{" "}
                <span className="muted">via {ref.fk}</span>
              </li>
            ))}
          </ul>
        </>
      )}

      <div className="two-col">
        <RoutineList title="Read by" routines={reads} />
        <RoutineList title="Written by" routines={writes} />
      </div>

      {triggers.length > 0 && (
        <>
          <h2>Triggers</h2>
          <ul className="link-list">
            {triggers.map((t) => (
              <li key={t.name}>
                <span className="mono">{t.name}</span>
                {t.routine_id && index.routinesById.has(t.routine_id) && (
                  <>
                    {" → "}
                    <Link to={`/r/${encodeURIComponent(t.routine_id)}`}>
                      {index.routinesById.get(t.routine_id)!.name}
                    </Link>
                  </>
                )}
              </li>
            ))}
          </ul>
        </>
      )}
    </article>
  );
}

function RoutineList({ title, routines }: { title: string; routines: Routine[] }) {
  return (
    <div>
      <h2>{title}</h2>
      {routines.length === 0 ? (
        <p className="muted">None.</p>
      ) : (
        <ul className="link-list">
          {routines.map((r) => (
            <li key={r.id}>
              <Link to={`/r/${encodeURIComponent(r.id)}`}>
                {r.schema}.{r.name}
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
