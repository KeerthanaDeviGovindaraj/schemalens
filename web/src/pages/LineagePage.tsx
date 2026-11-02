import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  Background,
  Controls,
  type Edge,
  type Node,
  ReactFlow,
  ReactFlowProvider,
} from "@xyflow/react";
import dagre from "@dagrejs/dagre";
import "@xyflow/react/dist/style.css";
import { useIndex } from "../App";
import { buildAdjacency, type GraphEdge } from "../lineage";

export function LineagePage() {
  const { nodeId = "" } = useParams();
  return (
    <ReactFlowProvider>
      <LineageInner key={nodeId} nodeId={nodeId} />
    </ReactFlowProvider>
  );
}

function LineageInner({ nodeId }: { nodeId: string }) {
  const index = useIndex();
  const [depth, setDepth] = useState(1);

  const graph = useMemo(() => buildAdjacency(index), [index]);

  const known =
    index.relationsById.has(nodeId) || index.routinesById.has(nodeId);

  const { nodes, edges } = useMemo(
    () => layout(graph, index, nodeId, depth),
    [graph, index, nodeId, depth],
  );

  if (!known) return <div className="status error">Unknown node: {nodeId}</div>;

  const center = labelFor(index, nodeId);

  return (
    <div className="lineage">
      <div className="lineage-head">
        <h1>Lineage: {center}</h1>
        <div className="legend">
          <span className="legend-item read">read</span>
          <span className="legend-item write">write</span>
          <span className="legend-item trigger">trigger</span>
          <button className="btn" onClick={() => setDepth(depth === 1 ? 2 : 1)}>
            {depth === 1 ? "Expand to depth 2" : "Collapse to depth 1"}
          </button>
        </div>
      </div>
      <div className="flow-wrap">
        <ReactFlow nodes={nodes} edges={edges} fitView proOptions={{ hideAttribution: true }}>
          <Background />
          <Controls />
        </ReactFlow>
      </div>
    </div>
  );
}

function labelFor(index: ReturnType<typeof useIndex>, id: string): string {
  const rel = index.relationsById.get(id);
  if (rel) return rel.id;
  const rtn = index.routinesById.get(id);
  return rtn ? `${rtn.schema}.${rtn.name}` : id;
}

const NODE_W = 230;
const NODE_H = 46;

function layout(
  graph: Map<string, GraphEdge[]>,
  index: ReturnType<typeof useIndex>,
  center: string,
  depth: number,
): { nodes: Node[]; edges: Edge[] } {
  // BFS out to `depth`, collecting nodes and edges.
  const visited = new Set<string>([center]);
  const edgeSet = new Map<string, GraphEdge>();
  let frontier = [center];
  for (let d = 0; d < depth; d++) {
    const next: string[] = [];
    for (const id of frontier) {
      for (const e of graph.get(id) ?? []) {
        edgeSet.set(`${e.source}->${e.target}:${e.kind}`, e);
        for (const other of [e.source, e.target]) {
          if (!visited.has(other)) {
            visited.add(other);
            next.push(other);
          }
        }
      }
    }
    frontier = next;
  }

  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: "LR", nodesep: 24, ranksep: 120 });

  for (const id of visited) g.setNode(id, { width: NODE_W, height: NODE_H });
  for (const e of edgeSet.values()) g.setEdge(e.source, e.target);
  dagre.layout(g);

  const nodes: Node[] = [...visited].map((id) => {
    const pos = g.node(id);
    const isRelation = index.relationsById.has(id);
    return {
      id,
      position: { x: pos.x - NODE_W / 2, y: pos.y - NODE_H / 2 },
      data: { label: nodeLabel(index, id, id === center) },
      className: `flow-node ${isRelation ? "node-relation" : "node-routine"} ${
        id === center ? "node-center" : ""
      }`,
      style: { width: NODE_W },
    };
  });

  const edges: Edge[] = [...edgeSet.values()].map((e, i) => ({
    id: `e${i}`,
    source: e.source,
    target: e.target,
    className: `edge-${e.kind}`,
    animated: false,
    label: e.kind,
  }));

  return { nodes, edges };
}

function nodeLabel(
  index: ReturnType<typeof useIndex>,
  id: string,
  _center: boolean,
): React.ReactNode {
  const rel = index.relationsById.get(id);
  const to = rel ? `/t/${encodeURIComponent(id)}` : `/r/${encodeURIComponent(id)}`;
  const text = rel ? rel.name : (index.routinesById.get(id)?.name ?? id);
  return (
    <Link to={to} className="node-link">
      {text}
    </Link>
  );
}
