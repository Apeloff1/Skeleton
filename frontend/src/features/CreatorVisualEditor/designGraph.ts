/**
 * Client mirror of the B012 creator design-graph contract
 * (skeleton/forge/creator/design_graph.py, schema `creator.design_graph.v1`).
 *
 * B019 edits this graph visually. To keep source round-trip fidelity the
 * client validates and normalizes exactly like `parse_design_graph` /
 * `build_design_graph`, then recomputes the same SHA-256 digest over the same
 * canonical bytes. Editor-only state (layout, selection) never enters the
 * graph payload, so a visual session that changes nothing serializes back to
 * the byte-identical source.
 */
import {
  CanonicalJsonError,
  PyFloat,
  canonicalStringify,
  compareCodepoints,
  parseCanonicalJson,
  type JsonScalar,
  type JsonValue,
} from './canonicalJson';
import { sha256Hex } from './sha256';

export const DESIGN_GRAPH_SCHEMA = 'creator.design_graph.v1';
export const DESIGN_GRAPH_VERSION = 1;
export const MAX_NODES = 4096;
export const MAX_EDGES = 16_384;
export const MAX_ATTRIBUTES = 64;
export const MAX_CANONICAL_BYTES = 4 * 1024 * 1024;
export const MAX_TEXT = 4096;
export const MAX_ID = 160;

export const NODE_KINDS = [
  'assumption', 'asset', 'concept', 'constraint', 'content', 'evidence',
  'interface', 'mechanic', 'narrative', 'scene', 'system', 'validation',
  'world',
] as const;
export const EDGE_KINDS = [
  'assumes', 'constrained_by', 'contains', 'depends_on', 'produces',
  'references', 'validated_by', 'validates',
] as const;

export type NodeKind = (typeof NODE_KINDS)[number];
export type EdgeKind = (typeof EDGE_KINDS)[number];
export type Attributes = Readonly<Record<string, JsonScalar>>;

export interface GraphNode {
  readonly id: string;
  readonly kind: NodeKind;
  readonly label: string;
  readonly attributes: Attributes;
}

export interface GraphEdge {
  readonly id: string;
  readonly kind: EdgeKind;
  readonly source: string;
  readonly target: string;
  readonly attributes: Attributes;
}

export interface DesignGraph {
  readonly projectId: string;
  readonly revision: number;
  readonly sourcePlanDigest: string | null;
  readonly nodes: readonly GraphNode[];
  readonly edges: readonly GraphEdge[];
}

export class DesignGraphError extends Error {
  readonly code = 'CRE.DESIGN_GRAPH';
  readonly context: Record<string, unknown>;
  constructor(message: string, context: Record<string, unknown> = {}) {
    super(message);
    this.name = 'DesignGraphError';
    this.context = context;
  }
}

const ID_RE = /^[a-z][a-z0-9._:-]{0,159}$/;
const SHA256_RE = /^[0-9a-f]{64}$/;
const codepointLength = (s: string) => Array.from(s).length;

export function isNodeKind(value: unknown): value is NodeKind {
  return typeof value === 'string' && (NODE_KINDS as readonly string[]).includes(value);
}
export function isEdgeKind(value: unknown): value is EdgeKind {
  return typeof value === 'string' && (EDGE_KINDS as readonly string[]).includes(value);
}
export function isGraphIdentifier(value: unknown): value is string {
  return typeof value === 'string' && value.length <= MAX_ID && ID_RE.test(value);
}

function identifier(value: unknown, field: string): string {
  if (!isGraphIdentifier(value)) throw new DesignGraphError(`${field} must be a canonical identifier`, { field });
  return value;
}

function text(value: unknown, field: string): string {
  if (typeof value !== 'string' || !value.trim()) throw new DesignGraphError(`${field} must be a non-empty string`, { field });
  // Python str.strip() strips Unicode whitespace; String.prototype.trim matches for the practical set.
  const t = value.trim();
  if (codepointLength(t) > MAX_TEXT || t.includes('\u0000') || t.includes('\r')) {
    throw new DesignGraphError(`${field} exceeds text/safety bound`, { field });
  }
  return t;
}

export function checkScalar(value: unknown, field: string): JsonScalar {
  if (value === null || typeof value === 'boolean') return value;
  if (typeof value === 'string') {
    if (codepointLength(value) > MAX_TEXT) throw new DesignGraphError(`${field} exceeds text bound`, { field });
    return value;
  }
  if (value instanceof PyFloat) return value;
  if (typeof value === 'number') {
    if (!Number.isSafeInteger(value)) throw new DesignGraphError(`${field} must be a safe integer (wrap floats in PyFloat)`, { field });
    return value;
  }
  throw new DesignGraphError(`${field} must be a JSON scalar`, { field });
}

function attributes(raw: unknown): Attributes {
  if (raw === null || typeof raw !== 'object' || Array.isArray(raw) || raw instanceof PyFloat) {
    throw new DesignGraphError('attributes must be a mapping');
  }
  const keys = Object.keys(raw as object);
  if (keys.length > MAX_ATTRIBUTES) throw new DesignGraphError('attribute count exceeds configured bound');
  const out: Record<string, JsonScalar> = {};
  for (const key of [...keys].sort(compareCodepoints)) {
    const k = identifier(key, 'attribute key');
    out[k] = checkScalar((raw as Record<string, unknown>)[key], `attribute ${k}`);
  }
  return Object.freeze(out);
}

function exactKeys(raw: Record<string, unknown>, expected: string[], kind: string): void {
  const extra = Object.keys(raw).filter((k) => !expected.includes(k)).sort();
  const missing = expected.filter((k) => !Object.prototype.hasOwnProperty.call(raw, k)).sort();
  if (extra.length || missing.length) throw new DesignGraphError(`${kind} keys mismatch`, { missing, extra });
}

function asRecord(raw: unknown, kind: string): Record<string, unknown> {
  if (raw === null || typeof raw !== 'object' || Array.isArray(raw) || raw instanceof PyFloat) {
    throw new DesignGraphError(`${kind} must be a mapping`);
  }
  const prototype = Object.getPrototypeOf(raw);
  if (prototype !== Object.prototype && prototype !== null) {
    throw new DesignGraphError(`${kind} must be a plain source mapping`);
  }
  for (const key of Object.keys(raw)) {
    const prop = Object.getOwnPropertyDescriptor(raw, key);
    if (!prop || !('value' in prop)) throw new DesignGraphError(`${kind} has an untrusted accessor`);
  }
  return raw as Record<string, unknown>;
}

export interface NodeInput { id: string; kind: string; label: string; attributes?: Record<string, unknown> }
export interface EdgeInput { id: string; kind: string; source: string; target: string; attributes?: Record<string, unknown> }
export interface DesignGraphInput {
  projectId: string;
  revision?: number;
  sourcePlanDigest?: string | null;
  nodes: readonly (NodeInput | GraphNode)[];
  edges: readonly (EdgeInput | GraphEdge)[];
}

function coerceNode(raw: NodeInput | GraphNode): GraphNode {
  const r = asRecord(raw, 'node');
  const kind = r.kind;
  if (!isNodeKind(kind)) throw new DesignGraphError('unsupported design graph node kind', { kind });
  return Object.freeze({
    id: identifier(r.id, 'node_id'),
    kind,
    label: text(r.label, 'label'),
    attributes: attributes(r.attributes ?? {}),
  });
}

function coerceEdge(raw: EdgeInput | GraphEdge): GraphEdge {
  const r = asRecord(raw, 'edge');
  const kind = r.kind;
  if (!isEdgeKind(kind)) throw new DesignGraphError('unsupported design graph edge kind', { kind });
  return Object.freeze({
    id: identifier(r.id, 'edge_id'),
    kind,
    source: identifier(r.source, 'source'),
    target: identifier(r.target, 'target'),
    attributes: attributes(r.attributes ?? {}),
  });
}

/** Mirror of `build_design_graph`: validate, normalize order, bound bytes. */
export function buildDesignGraph(input: DesignGraphInput): DesignGraph {
  const projectId = identifier(input.projectId, 'project_id');
  const revision = input.revision ?? 0;
  if (typeof revision !== 'number' || !Number.isSafeInteger(revision) || revision < 0) {
    throw new DesignGraphError('revision must be a non-negative integer');
  }
  const sourcePlanDigest = input.sourcePlanDigest ?? null;
  if (sourcePlanDigest !== null && (typeof sourcePlanDigest !== 'string' || !SHA256_RE.test(sourcePlanDigest))) {
    throw new DesignGraphError('source_plan_digest must be a lowercase SHA-256 digest');
  }
  if (!Array.isArray(input.nodes) || !Array.isArray(input.edges)) {
    throw new DesignGraphError('design graph nodes/edges must be lists');
  }
  if (input.nodes.length > MAX_NODES) throw new DesignGraphError('node count exceeds configured bound');
  if (input.edges.length > MAX_EDGES) throw new DesignGraphError('edge count exceeds configured bound');

  const nodes: GraphNode[] = [];
  const nodeIds = new Set<string>();
  for (const raw of input.nodes) {
    const node = coerceNode(raw);
    if (nodeIds.has(node.id)) throw new DesignGraphError('duplicate design graph node', { node_id: node.id });
    nodeIds.add(node.id);
    nodes.push(node);
  }
  const edges: GraphEdge[] = [];
  const edgeIds = new Set<string>();
  for (const raw of input.edges) {
    const edge = coerceEdge(raw);
    if (edgeIds.has(edge.id)) throw new DesignGraphError('duplicate design graph edge', { edge_id: edge.id });
    edgeIds.add(edge.id);
    edges.push(edge);
  }
  nodes.sort((a, b) => compareCodepoints(a.id, b.id));
  edges.sort(
    (a, b) =>
      compareCodepoints(a.source, b.source) ||
      compareCodepoints(a.kind, b.kind) ||
      compareCodepoints(a.target, b.target) ||
      compareCodepoints(a.id, b.id),
  );
  for (const edge of edges) {
    if (!nodeIds.has(edge.source) || !nodeIds.has(edge.target)) {
      throw new DesignGraphError('edge references unknown node', { edge_id: edge.id, source: edge.source, target: edge.target });
    }
    if (edge.source === edge.target) throw new DesignGraphError('self edges are forbidden', { edge_id: edge.id });
  }
  const graph: DesignGraph = Object.freeze({
    projectId,
    revision,
    sourcePlanDigest,
    nodes: Object.freeze(nodes),
    edges: Object.freeze(edges),
  });
  if (serializeDesignGraph(graph).length > MAX_CANONICAL_BYTES) {
    // Canonical output is ASCII-only, so string length equals byte length.
    throw new DesignGraphError('design graph exceeds canonical byte bound');
  }
  return graph;
}

/** Same field layout as `DesignGraphSnapshot.to_payload`. */
export function designGraphPayload(graph: DesignGraph, includeDigest = true): { [key: string]: JsonValue } {
  const payload: { [key: string]: JsonValue } = {
    schema: DESIGN_GRAPH_SCHEMA,
    schema_version: DESIGN_GRAPH_VERSION,
    project_id: graph.projectId,
    revision: graph.revision,
    source_plan_digest: graph.sourcePlanDigest,
    nodes: graph.nodes.map((n) => ({ id: n.id, kind: n.kind, label: n.label, attributes: { ...n.attributes } })),
    edges: graph.edges.map((e) => ({
      id: e.id,
      kind: e.kind,
      source: e.source,
      target: e.target,
      attributes: { ...e.attributes },
    })),
  };
  if (includeDigest) payload.digest = designGraphDigest(graph);
  return payload;
}

export function designGraphDigest(graph: DesignGraph): string {
  return sha256Hex(canonicalStringify(designGraphPayload(graph, false)));
}

/** Canonical bytes identical to `DesignGraphSnapshot.serialize()`. */
export function serializeDesignGraph(graph: DesignGraph): string {
  return canonicalStringify(designGraphPayload(graph, true));
}

/** Mirror of `parse_design_graph`: strict keys, schema, digest verification. */
export function parseDesignGraph(raw: string | JsonValue): DesignGraph {
  let payload: JsonValue;
  if (typeof raw === 'string') {
    try {
      payload = parseCanonicalJson(raw);
    } catch (err) {
      if (err instanceof CanonicalJsonError) {
        throw new DesignGraphError(
          err.reason === 'duplicate_key' ? err.message : 'design graph is not valid JSON',
          { reason: err.reason },
        );
      }
      throw err;
    }
  } else {
    payload = raw;
  }
  const record = asRecord(payload, 'design graph');
  exactKeys(
    record,
    ['schema', 'schema_version', 'project_id', 'revision', 'source_plan_digest', 'nodes', 'edges', 'digest'],
    'design graph',
  );
  if (record.schema !== DESIGN_GRAPH_SCHEMA) throw new DesignGraphError('unsupported design graph schema');
  if (record.schema_version !== DESIGN_GRAPH_VERSION) throw new DesignGraphError('unsupported design graph version');
  if (!Array.isArray(record.nodes) || !Array.isArray(record.edges)) {
    throw new DesignGraphError('design graph nodes/edges must be lists');
  }
  for (const n of record.nodes) exactKeys(asRecord(n, 'node'), ['id', 'kind', 'label', 'attributes'], 'node');
  for (const e of record.edges) exactKeys(asRecord(e, 'edge'), ['id', 'kind', 'source', 'target', 'attributes'], 'edge');
  const graph = buildDesignGraph({
    projectId: record.project_id as string,
    revision: record.revision as number,
    sourcePlanDigest: record.source_plan_digest as string | null,
    nodes: record.nodes as unknown as NodeInput[],
    edges: record.edges as unknown as EdgeInput[],
  });
  const declared = record.digest;
  if (typeof declared !== 'string' || !SHA256_RE.test(declared)) {
    throw new DesignGraphError('digest must be a lowercase SHA-256 digest');
  }
  if (declared !== designGraphDigest(graph)) throw new DesignGraphError('design graph digest mismatch');
  return graph;
}

export interface RoundTripReport {
  readonly ok: boolean;
  /** True when the source text was already canonical and re-serializes byte for byte. */
  readonly byteIdentical: boolean;
  readonly digest: string | null;
  readonly canonical: string | null;
  readonly error: string | null;
}

/** Parse → serialize → parse, proving the editor can write the source back unchanged. */
export function checkRoundTrip(source: string): RoundTripReport {
  try {
    const graph = parseDesignGraph(source);
    const canonical = serializeDesignGraph(graph);
    const again = parseDesignGraph(canonical);
    if (serializeDesignGraph(again) !== canonical) {
      return { ok: false, byteIdentical: false, digest: null, canonical: null, error: 'canonical form is not stable' };
    }
    return { ok: true, byteIdentical: canonical === source, digest: designGraphDigest(graph), canonical, error: null };
  } catch (err) {
    return { ok: false, byteIdentical: false, digest: null, canonical: null, error: err instanceof Error ? err.message : String(err) };
  }
}

export function nodeMap(graph: DesignGraph): Map<string, GraphNode> {
  return new Map(graph.nodes.map((n) => [n.id, n]));
}
