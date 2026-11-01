import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useIndex } from "../App";
import { isStatic, requestExplanation } from "../data";
import type { Explanation } from "../types";
import { highlightSql } from "../sql-highlight";
import { Breadcrumb } from "../components";

export function RoutinePage() {
  const { routineId = "" } = useParams();
  const index = useIndex();
  const routine = index.routinesById.get(routineId);

  const [explanation, setExplanation] = useState<Explanation | null>(
    routine?.explanation ?? null,
  );
  const [loading, setLoading] = useState(false);
  const [explainError, setExplainError] = useState<string | null>(null);

  if (!routine)
    return (
      <div className="status error">
        <p>Routine not found: {routineId}</p>
        <Link to="/">Back to search</Link>
      </div>
    );

  const generate = async () => {
    setLoading(true);
    setExplainError(null);
    try {
      const result = await requestExplanation(routine.id);
      setExplanation(result);
    } catch (e) {
      setExplainError(String(e));
    } finally {
      setLoading(false);
    }
  };

  return (
    <article className="detail">
      <Breadcrumb current={`${routine.schema}.${routine.name}`} />
      <header className="detail-head">
        <h1>
          {routine.schema}.{routine.name}
          <span className="kind-tag">{routine.language}</span>
        </h1>
        <Link className="lineage-link" to={`/lineage/${encodeURIComponent(routine.id)}`}>
          View lineage →
        </Link>
      </header>
      <p className="mono muted signature">
        ({routine.args}) → {routine.returns}
      </p>

      {routine.flags.length > 0 && (
        <div className="flags">
          {routine.flags.map((f, i) => (
            <span key={i} className={`flag flag-${f.kind}`} title={f.detail}>
              {f.kind}
            </span>
          ))}
        </div>
      )}

      <div className="two-col">
        <RefList title="Reads" refs={routine.reads} />
        <RefList title="Writes" refs={routine.writes} />
      </div>

      <h2>Source</h2>
      <pre className="source">
        <code dangerouslySetInnerHTML={{ __html: highlightSql(routine.definition) }} />
      </pre>

      <h2>Explanation</h2>
      {!explanation && !isStatic && (
        <button className="btn" onClick={generate} disabled={loading}>
          {loading ? "Generating…" : "Generate explanation"}
        </button>
      )}
      {!explanation && isStatic && <p className="muted">No cached explanation for this routine.</p>}
      {explainError && <p className="status error">{explainError}</p>}
      {explanation && <ExplanationPanel explanation={explanation} />}
    </article>
  );
}

function RefList({ title, refs }: { title: string; refs: string[] }) {
  return (
    <div>
      <h2>{title}</h2>
      {refs.length === 0 ? (
        <p className="muted">None.</p>
      ) : (
        <ul className="link-list">
          {refs.map((r) => (
            <li key={r}>
              <Link to={`/t/${encodeURIComponent(r)}`}>{r}</Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function ExplanationPanel({ explanation }: { explanation: Explanation }) {
  return (
    <div className="explanation">
      {explanation.disagreements.length > 0 && (
        <div className="disagreement" role="alert">
          <strong>Explanation disagrees with analysis</strong>
          <ul>
            {explanation.disagreements.map((d, i) => (
              <li key={i}>{d}</li>
            ))}
          </ul>
        </div>
      )}
      <p className="summary">{explanation.summary}</p>
      {explanation.purpose && (
        <p>
          <strong>Purpose:</strong> {explanation.purpose}
        </p>
      )}
      {explanation.parameters.length > 0 && (
        <>
          <h3>Parameters</h3>
          <ul>
            {explanation.parameters.map((p) => (
              <li key={p.name}>
                <span className="mono">{p.name}</span>: {p.meaning}
              </li>
            ))}
          </ul>
        </>
      )}
      {explanation.side_effects.length > 0 && (
        <>
          <h3>Side effects</h3>
          <ul>
            {explanation.side_effects.map((s, i) => (
              <li key={i}>{s}</li>
            ))}
          </ul>
        </>
      )}
      {explanation.caveats.length > 0 && (
        <>
          <h3>Caveats</h3>
          <ul>
            {explanation.caveats.map((c, i) => (
              <li key={i}>{c}</li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
