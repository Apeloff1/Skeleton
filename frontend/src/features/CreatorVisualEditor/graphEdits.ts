/**
 * Pure, immutable visual edit operations over a B012 design graph.
 *
 * Every operation returns a freshly validated graph (via buildDesignGraph), so
 * the editor can never hold a graph the backend would reject. Operations are
 * also recorded as typed {@link VisualEditOp} values that become the `patch`
 * of B014 `edit` creator commands (see creatorCommand.ts).
 */
import { compareCodepoints, type JsonScalar } from './canonicalJson';
import { sha256Hex } from './sha256';
import {
  DesignGraphError,
  buildDesignGraph,
  checkScalar,
  isEdgeKind,
  isGraphIdentifier,
  isNodeKind,
  type DesignGraph,
  type EdgeKind,
  type GraphEdge,
  type GraphNode,
  type NodeKind,
} from './designGraph';

export const MAX_UNCOMMITTED_EDITS = 1024;

export type VisualEditOp =
  | { op: 'add_node'; node_id: string; kind: NodeKind; label: string }
  | { op: 'remove_node'; node_id: string }
  | { op: 'rename_node'; node_id: string; label: string }
  | { op: 'change_kind'; node_id: string; kind: NodeKind }
  | { op: 'set_attribute'; node_id: string; key: string; value: JsonScalar }
  | { op: 'remove_attribute'; node_id: string; key: string }
  | { op: 'add_edge'; edge_id: string; kind: EdgeKind; source: string; target: string }
  | { op: 'remove_edge'; edge_id: string }
  | { op: 'set_edge_attribute'; edge_id: string; key: string; value: JsonScalar }
  | { op: 'remove_edge_attribute'; edge_id: string; key: string };

export interface EditResult {
  readonly graph: DesignGraph;
  readonly op: VisualEditOp;
}

function rebuild(graph: DesignGraph, nodes: readonly GraphNode[], edges: readonly GraphEdge[]): DesignGraph {
  return buildDesignGraph({
    projectId: graph.projectId,
    revision: graph.revision,
    sourcePlanDigest: graph.sourcePlanDigest,
    nodes,
    edges,
  });
}

function requireNode(graph: DesignGraph, id: string): GraphNode {
  const node = graph.nodes.find((n) => n.id === id);
  if (!node) throw new DesignGraphError('unknown design graph node', { node_id: id });
  return node;
}

function requireEdge(graph: DesignGraph, id: string): GraphEdge {
  const edge = graph.edges.find((e) => e.id === id);
  if (!edge) throw new DesignGraphError('unknown design graph edge', { edge_id: id });
  return edge;
}

function replaceNode(graph: DesignGraph, next: GraphNode): DesignGraph {
  return rebuild(graph, graph.nodes.map((n) => (n.id === next.id ? next : n)), graph.edges);
}

function replaceEdge(graph: DesignGraph, next: GraphEdge): DesignGraph {
  return rebuild(graph, graph.nodes, graph.edges.map((e) => (e.id === next.id ? next : e)));
}

function withoutKey(attrs: Readonly<Record<string, JsonScalar>>, key: string): Record<string, JsonScalar> {
  const out: Record<string, JsonScalar> = {};
  for (const k of Object.keys(attrs).sort(compareCodepoints)) if (k !== key) out[k] = attrs[k];
  return out;
}

/** Same id scheme as design_graph `_edge_id(prefix, source, target)`. */
export function edgeIdFor(kind: string, source: string, target: string): string {
  const raw = `${kind}:${source}:${target}`;
  if (isGraphIdentifier(raw)) return raw;
  return `${kind}:${sha256Hex(raw).slice(0, 24)}`;
}

export function addNode(graph: DesignGraph, input: { id: string; kind: string; label: string }): EditResult {
  if (!isNodeKind(input.kind)) throw new DesignGraphError('unsupported design graph node kind', { kind: input.kind });
  if (graph.nodes.some((n) => n.id === input.id)) throw new DesignGraphError('duplicate design graph node', { node_id: input.id });
  const next = rebuild(graph, [...graph.nodes, { id: input.id, kind: input.kind, label: input.label, attributes: {} }], graph.edges);
  const node = requireNode(next, input.id);
  return { graph: next, op: { op: 'add_node', node_id: node.id, kind: node.kind, label: node.label } };
}

/** Removing a node also removes its incident relationships (no dangling edges). */
export function removeNode(graph: DesignGraph, nodeId: string): EditResult {
  requireNode(graph, nodeId);
  const next = rebuild(
    graph,
    graph.nodes.filter((n) => n.id !== nodeId),
    graph.edges.filter((e) => e.source !== nodeId && e.target !== nodeId),
  );
  return { graph: next, op: { op: 'remove_node', node_id: nodeId } };
}

export function renameNode(graph: DesignGraph, nodeId: string, label: string): EditResult {
  const node = requireNode(graph, nodeId);
  const next = replaceNode(graph, { ...node, label });
  return { graph: next, op: { op: 'rename_node', node_id: nodeId, label: requireNode(next, nodeId).label } };
}

export function changeNodeKind(graph: DesignGraph, nodeId: string, kind: string): EditResult {
  if (!isNodeKind(kind)) throw new DesignGraphError('unsupported design graph node kind', { kind });
  const node = requireNode(graph, nodeId);
  return { graph: replaceNode(graph, { ...node, kind }), op: { op: 'change_kind', node_id: nodeId, kind } };
}

export function setNodeAttribute(graph: DesignGraph, nodeId: string, key: string, value: unknown): EditResult {
  const node = requireNode(graph, nodeId);
  const scalar = checkScalar(value, `attribute ${key}`);
  const next = replaceNode(graph, { ...node, attributes: { ...withoutKey(node.attributes, key), [key]: scalar } });
  return { graph: next, op: { op: 'set_attribute', node_id: nodeId, key, value: scalar } };
}

export function removeNodeAttribute(graph: DesignGraph, nodeId: string, key: string): EditResult {
  const node = requireNode(graph, nodeId);
  if (!(key in node.attributes)) throw new DesignGraphError('unknown attribute', { node_id: nodeId, key });
  return { graph: replaceNode(graph, { ...node, attributes: withoutKey(node.attributes, key) }), op: { op: 'remove_attribute', node_id: nodeId, key } };
}

/** B016 forbids two edges with the same (kind, source, target); so do we. */
export function addEdge(graph: DesignGraph, input: { kind: string; source: string; target: string }): EditResult {
  if (!isEdgeKind(input.kind)) throw new DesignGraphError('unsupported design graph edge kind', { kind: input.kind });
  if (graph.edges.some((e) => e.kind === input.kind && e.source === input.source && e.target === input.target)) {
    throw new DesignGraphError('relationship already exists', { kind: input.kind, source: input.source, target: input.target });
  }
  const id = edgeIdFor(input.kind, input.source, input.target);
  if (graph.edges.some((e) => e.id === id)) throw new DesignGraphError('duplicate design graph edge', { edge_id: id });
  const next = rebuild(graph, graph.nodes, [...graph.edges, { id, kind: input.kind, source: input.source, target: input.target, attributes: {} }]);
  return { graph: next, op: { op: 'add_edge', edge_id: id, kind: input.kind, source: input.source, target: input.target } };
}

export function removeEdge(graph: DesignGraph, edgeId: string): EditResult {
  requireEdge(graph, edgeId);
  return { graph: rebuild(graph, graph.nodes, graph.edges.filter((e) => e.id !== edgeId)), op: { op: 'remove_edge', edge_id: edgeId } };
}

export function setEdgeAttribute(graph: DesignGraph, edgeId: string, key: string, value: unknown): EditResult {
  const edge = requireEdge(graph, edgeId);
  const scalar = checkScalar(value, `attribute ${key}`);
  const next = replaceEdge(graph, { ...edge, attributes: { ...withoutKey(edge.attributes, key), [key]: scalar } });
  return { graph: next, op: { op: 'set_edge_attribute', edge_id: edgeId, key, value: scalar } };
}

export function removeEdgeAttribute(graph: DesignGraph, edgeId: string, key: string): EditResult {
  const edge = requireEdge(graph, edgeId);
  if (!(key in edge.attributes)) throw new DesignGraphError('unknown attribute', { edge_id: edgeId, key });
  return { graph: replaceEdge(graph, { ...edge, attributes: withoutKey(edge.attributes, key) }), op: { op: 'remove_edge_attribute', edge_id: edgeId, key } };
}

/** Stable id of the graph entity an op targets (B014 `target_id`). */
export function opTarget(op: VisualEditOp): string {
  return 'node_id' in op ? op.node_id : op.edge_id;
}

/**
 * Editor session: immutable base (the loaded source), current working graph,
 * ordered op log, and an undo stack. Undo restores the previous graph exactly.
 */
export interface EditSession {
  readonly base: DesignGraph;
  readonly working: DesignGraph;
  readonly ops: readonly VisualEditOp[];
  readonly history: readonly DesignGraph[];
}

export function startSession(base: DesignGraph): EditSession {
  return Object.freeze({ base, working: base, ops: Object.freeze([]), history: Object.freeze([]) });
}

export function applyEdit(session: EditSession, edit: (g: DesignGraph) => EditResult): EditSession {
  if (session.ops.length >= MAX_UNCOMMITTED_EDITS) {
    throw new DesignGraphError('visual edit session budget exceeded; review and commit before continuing');
  }
  const result = edit(session.working);
  return Object.freeze({
    base: session.base,
    working: result.graph,
    ops: Object.freeze([...session.ops, result.op]),
    history: Object.freeze([...session.history, session.working]),
  });
}

export function undo(session: EditSession): EditSession {
  if (!session.history.length) return session;
  return Object.freeze({
    base: session.base,
    working: session.history[session.history.length - 1],
    ops: Object.freeze(session.ops.slice(0, -1)),
    history: Object.freeze(session.history.slice(0, -1)),
  });
}
