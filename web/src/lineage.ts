import type { Index } from "./data";

export interface GraphEdge {
  source: string;
  target: string;
  kind: "read" | "write" | "trigger";
}

// Builds an undirected-ish adjacency map keyed by node id. Each node lists the
// edges touching it (in both directions) so BFS from any node finds neighbors.
export function buildAdjacency(index: Index): Map<string, GraphEdge[]> {
  const map = new Map<string, GraphEdge[]>();
  const add = (e: GraphEdge) => {
    push(map, e.source, e);
    push(map, e.target, e);
  };

  for (const routine of index.bundle.routines) {
    // read: relation -> routine (the routine consumes the relation)
    for (const rel of routine.reads) {
      if (index.relationsById.has(rel)) {
        add({ source: rel, target: routine.id, kind: "read" });
      }
    }
    // write: routine -> relation
    for (const rel of routine.writes) {
      if (index.relationsById.has(rel)) {
        add({ source: routine.id, target: rel, kind: "write" });
      }
    }
  }

  for (const trig of index.bundle.triggers) {
    if (trig.routine_id && index.routinesById.has(trig.routine_id)) {
      // trigger: relation -> routine (dashed)
      add({ source: trig.relation_id, target: trig.routine_id, kind: "trigger" });
    }
  }

  return map;
}

function push(map: Map<string, GraphEdge[]>, key: string, value: GraphEdge): void {
  const arr = map.get(key);
  if (arr) arr.push(value);
  else map.set(key, [value]);
}
