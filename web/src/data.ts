import type { Bundle, Explanation, Relation, Routine, Trigger } from "./types";

const MODE = import.meta.env.VITE_DATA_MODE === "static" ? "static" : "api";
export const isStatic = MODE === "static";

export async function loadBundle(): Promise<Bundle> {
  const url = isStatic ? `${import.meta.env.BASE_URL}bundle.json` : "/api/bundle";
  const resp = await fetch(url);
  if (!resp.ok) throw new Error(`failed to load bundle: ${resp.status}`);
  return (await resp.json()) as Bundle;
}

export async function requestExplanation(routineId: string): Promise<Explanation> {
  if (isStatic) throw new Error("explanation generation is disabled in the static demo");
  const resp = await fetch(`/api/routines/${encodeURIComponent(routineId)}/explain`, {
    method: "POST",
  });
  if (!resp.ok) {
    const detail = await resp.text();
    throw new Error(`explain failed (${resp.status}): ${detail}`);
  }
  return (await resp.json()) as Explanation;
}

// ---------------------------------------------------------------- derived index

export interface SearchResult {
  type: "relation" | "column" | "routine";
  id: string; // relation id or routine id
  label: string;
  context: string;
}

export interface Index {
  bundle: Bundle;
  relationsById: Map<string, Relation>;
  routinesById: Map<string, Routine>;
  readsByRelation: Map<string, Routine[]>;
  writesByRelation: Map<string, Routine[]>;
  triggersByRelation: Map<string, Trigger[]>;
  incomingFks: Map<string, { from: Relation; fk: string }[]>;
  search: (query: string) => SearchResult[];
}

export function buildIndex(bundle: Bundle): Index {
  const relationsById = new Map(bundle.relations.map((r) => [r.id, r]));
  const routinesById = new Map(bundle.routines.map((r) => [r.id, r]));

  const readsByRelation = new Map<string, Routine[]>();
  const writesByRelation = new Map<string, Routine[]>();
  for (const routine of bundle.routines) {
    for (const rel of routine.reads) push(readsByRelation, rel, routine);
    for (const rel of routine.writes) push(writesByRelation, rel, routine);
  }

  const triggersByRelation = new Map<string, Trigger[]>();
  for (const t of bundle.triggers) push(triggersByRelation, t.relation_id, t);

  const incomingFks = new Map<string, { from: Relation; fk: string }[]>();
  for (const rel of bundle.relations) {
    for (const fk of rel.foreign_keys) {
      push(incomingFks, fk.to_relation, { from: rel, fk: fk.name });
    }
  }

  const search = (query: string): SearchResult[] => {
    const q = query.trim().toLowerCase();
    if (!q) return [];
    const out: SearchResult[] = [];
    for (const rel of bundle.relations) {
      if (rel.name.toLowerCase().includes(q) || rel.comment?.toLowerCase().includes(q)) {
        out.push({ type: "relation", id: rel.id, label: rel.id, context: rel.kind });
      }
      for (const col of rel.columns) {
        if (col.name.toLowerCase().includes(q)) {
          out.push({
            type: "column",
            id: rel.id,
            label: `${rel.name}.${col.name}`,
            context: col.data_type,
          });
        }
      }
    }
    for (const routine of bundle.routines) {
      if (
        routine.name.toLowerCase().includes(q) ||
        routine.explanation?.summary?.toLowerCase().includes(q)
      ) {
        out.push({
          type: "routine",
          id: routine.id,
          label: `${routine.schema}.${routine.name}`,
          context: routine.language,
        });
      }
    }
    return out.slice(0, 100);
  };

  return {
    bundle,
    relationsById,
    routinesById,
    readsByRelation,
    writesByRelation,
    triggersByRelation,
    incomingFks,
    search,
  };
}

function push<K, V>(map: Map<K, V[]>, key: K, value: V): void {
  const arr = map.get(key);
  if (arr) arr.push(value);
  else map.set(key, [value]);
}
