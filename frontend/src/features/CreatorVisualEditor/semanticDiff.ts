/**
 * Client mirror of the B016 semantic game diff
 * (skeleton/forge/creator/semantic_diff.py, schema `creator.semantic_diff.v1`).
 *
 * The visual editor previews what an edit *means* (scene/mechanic/asset
 * changes) before anything is submitted. The algorithm, ordering, summaries,
 * change ids and digest match the Python implementation byte for byte, so a
 * server-side `validate_semantic_diff` over the same graphs agrees with what
 * the user saw. The backend stays authoritative.
 */
import { canonicalStringify, compareCodepoints, pyScalarEquals, type JsonScalar, type JsonValue } from './canonicalJson';
import { designGraphDigest, nodeMap, parseDesignGraph, serializeDesignGraph, type DesignGraph, type GraphEdge, type GraphNode } from './designGraph';
import { sha256Hex } from './sha256';

export const SEMANTIC_DIFF_SCHEMA = 'creator.semantic_diff.v1';
export const SEMANTIC_DIFF_VERSION = 1;
export const MAX_CHANGES = 65_536;
export const IGNORED_ATTRIBUTES: ReadonlySet<string> = new Set(['source_path']);
export const CHANGE_ACTIONS = [
  'node_removed',
  'node_added',
  'node_kind_changed',
  'node_renamed',
  'node_attributes_changed',
  'relationship_removed',
  'relationship_added',
  'relationship_attributes_changed',
] as const;
export type ChangeAction = (typeof CHANGE_ACTIONS)[number];

const EDGE_VERBS: Record<string, [string, string]> = {
  assumes: ['now assumes', 'no longer assumes'],
  constrained_by: ['is now constrained by', 'is no longer constrained by'],
  contains: ['now contains', 'no longer contains'],
  depends_on: ['now depends on', 'no longer depends on'],
  produces: ['now produces', 'no longer produces'],
  references: ['now references', 'no longer references'],
  validated_by: ['is now validated by', 'is no longer validated by'],
  validates: ['now validates', 'no longer validates'],
};

export interface SemanticValueDelta {
  readonly field: string;
  readonly before_present: boolean;
  readonly before: JsonScalar;
  readonly after_present: boolean;
  readonly after: JsonScalar;
}

export interface SemanticChange {
  readonly change_id: string;
  readonly entity: 'node' | 'relationship';
  readonly domain: string;
  readonly action: ChangeAction;
  readonly subject_id: string;
  readonly summary: string;
  readonly source_id: string | null;
  readonly target_id: string | null;
  readonly deltas: readonly SemanticValueDelta[];
}

export interface SemanticDiff {
  readonly project_id: string;
  readonly base_revision: number;
  readonly target_revision: number;
  readonly base_digest: string;
  readonly target_digest: string;
  readonly changes: readonly SemanticChange[];
  readonly counts_by_domain: readonly { domain: string; count: number }[];
  readonly counts_by_action: readonly { action: string; count: number }[];
  readonly ignored_change_count: number;
  readonly digest: string;
}

export class SemanticDiffError extends Error {
  readonly code = 'CRE.SEMANTIC_DIFF';
  readonly reason: string;
  constructor(message: string, reason: string) {
    super(message);
    this.name = 'SemanticDiffError';
    this.reason = reason;
  }
}

const deltaPayload = (d: SemanticValueDelta): JsonValue => ({ ...d });

const entityPhrase = (kind: string, label: string) => `${kind} "${label}"`;

function visible(attrs: Readonly<Record<string, JsonScalar>>): Record<string, JsonScalar> {
  const out: Record<string, JsonScalar> = {};
  for (const [k, v] of Object.entries(attrs)) if (!IGNORED_ATTRIBUTES.has(k)) out[k] = v;
  return out;
}

function attributeDeltas(before: Record<string, JsonScalar>, after: Record<string, JsonScalar>): SemanticValueDelta[] {
  const fields = [...new Set([...Object.keys(before), ...Object.keys(after)])].sort(compareCodepoints);
  const out: SemanticValueDelta[] = [];
  for (const field of fields) {
    const bp = field in before;
    const ap = field in after;
    if (bp === ap && pyScalarEquals(before[field] ?? null, after[field] ?? null)) continue;
    out.push({
      field: `attribute.${field}`,
      before_present: bp,
      before: bp ? before[field] : null,
      after_present: ap,
      after: ap ? after[field] : null,
    });
  }
  return out;
}

function presenceDeltas(node: GraphNode, beforePresent: boolean): SemanticValueDelta[] {
  const mk = (field: string, value: JsonScalar): SemanticValueDelta => ({
    field,
    before_present: beforePresent,
    before: beforePresent ? value : null,
    after_present: !beforePresent,
    after: beforePresent ? null : value,
  });
  const out = [mk('kind', node.kind), mk('label', node.label)];
  const attrs = visible(node.attributes);
  for (const key of Object.keys(attrs).sort(compareCodepoints)) out.push(mk(`attribute.${key}`, attrs[key]));
  return out;
}

function cleanSummary(value: string): string {
  if (!value || Array.from(value).length > 2048) throw new SemanticDiffError('semantic summary exceeds contract', 'summary');
  for (const ch of value) {
    if (ch.charCodeAt(0) < 32 && ch !== '\t') throw new SemanticDiffError('semantic summary contains control character', 'summary');
  }
  return value;
}

function change(args: {
  entity: 'node' | 'relationship';
  domain: string;
  action: ChangeAction;
  subject_id: string;
  summary: string;
  source_id?: string | null;
  target_id?: string | null;
  deltas?: SemanticValueDelta[];
}): SemanticChange {
  const deltas = args.deltas ?? [];
  const payload: { [key: string]: JsonValue } = {
    entity: args.entity,
    domain: args.domain,
    action: args.action,
    subject_id: args.subject_id,
    summary: cleanSummary(args.summary),
    source_id: args.source_id ?? null,
    target_id: args.target_id ?? null,
    deltas: deltas.map(deltaPayload),
  };
  return Object.freeze({
    change_id: `chg_${sha256Hex(canonicalStringify(payload)).slice(0, 24)}`,
    entity: args.entity,
    domain: args.domain,
    action: args.action,
    subject_id: args.subject_id,
    summary: args.summary,
    source_id: args.source_id ?? null,
    target_id: args.target_id ?? null,
    deltas: Object.freeze(deltas),
  });
}

const fieldList = (deltas: SemanticValueDelta[]) =>
  deltas.map((d) => d.field.replace(/^attribute\./, '').split('_').join(' ')).join(', ');

function ignoredAttributeChanges(a: Readonly<Record<string, JsonScalar>>, b: Readonly<Record<string, JsonScalar>>): number {
  let n = 0;
  for (const key of IGNORED_ATTRIBUTES) {
    if (!pyScalarEquals(a[key] ?? null, b[key] ?? null) && (key in a || key in b)) n += 1;
  }
  return n;
}

function nodeChanges(base: DesignGraph, target: DesignGraph): [SemanticChange[], number] {
  const out: SemanticChange[] = [];
  let ignored = 0;
  const before = nodeMap(base);
  const after = nodeMap(target);
  const sortIds = (ids: string[]) => ids.sort(compareCodepoints);
  for (const id of sortIds([...before.keys()].filter((k) => !after.has(k)))) {
    const node = before.get(id) as GraphNode;
    out.push(change({ entity: 'node', domain: node.kind, action: 'node_removed', subject_id: id, summary: `Removed ${entityPhrase(node.kind, node.label)}.`, deltas: presenceDeltas(node, true) }));
  }
  for (const id of sortIds([...after.keys()].filter((k) => !before.has(k)))) {
    const node = after.get(id) as GraphNode;
    out.push(change({ entity: 'node', domain: node.kind, action: 'node_added', subject_id: id, summary: `Added ${entityPhrase(node.kind, node.label)}.`, deltas: presenceDeltas(node, false) }));
  }
  for (const id of sortIds([...before.keys()].filter((k) => after.has(k)))) {
    const o = before.get(id) as GraphNode;
    const n = after.get(id) as GraphNode;
    if (o.kind !== n.kind) {
      out.push(change({
        entity: 'node', domain: n.kind, action: 'node_kind_changed', subject_id: id,
        summary: `Changed "${n.label}" from ${o.kind} to ${n.kind}.`,
        deltas: [{ field: 'kind', before_present: true, before: o.kind, after_present: true, after: n.kind }],
      }));
    }
    if (o.label !== n.label) {
      out.push(change({
        entity: 'node', domain: n.kind, action: 'node_renamed', subject_id: id,
        summary: `Renamed ${n.kind} "${o.label}" to "${n.label}".`,
        deltas: [{ field: 'label', before_present: true, before: o.label, after_present: true, after: n.label }],
      }));
    }
    ignored += ignoredAttributeChanges(o.attributes, n.attributes);
    const deltas = attributeDeltas(visible(o.attributes), visible(n.attributes));
    if (deltas.length) {
      out.push(change({
        entity: 'node', domain: n.kind, action: 'node_attributes_changed', subject_id: id,
        summary: `Updated ${n.kind} "${n.label}": ${fieldList(deltas)}.`, deltas,
      }));
    }
  }
  return [out, ignored];
}

type RelKey = [string, string, string];
const relKeyString = (k: RelKey) => JSON.stringify(k);
const compareRelKeys = (a: RelKey, b: RelKey) =>
  compareCodepoints(a[0], b[0]) || compareCodepoints(a[1], b[1]) || compareCodepoints(a[2], b[2]);

function semanticEdges(graph: DesignGraph): Map<string, { key: RelKey; edge: GraphEdge }> {
  const out = new Map<string, { key: RelKey; edge: GraphEdge }>();
  for (const edge of graph.edges) {
    const key: RelKey = [edge.kind, edge.source, edge.target];
    const s = relKeyString(key);
    if (out.has(s)) throw new SemanticDiffError('design graph contains duplicate semantic relationship', 'ambiguous_relationship');
    out.set(s, { key, edge });
  }
  return out;
}

export function relationshipSubject(key: RelKey): string {
  return `rel_${sha256Hex(canonicalStringify([...key])).slice(0, 24)}`;
}

function relationshipSummary(edge: GraphEdge, nodes: Map<string, GraphNode>, added: boolean): string {
  const source = nodes.get(edge.source) as GraphNode;
  const target = nodes.get(edge.target) as GraphNode;
  const [positive, negative] = EDGE_VERBS[edge.kind];
  let phrase = entityPhrase(source.kind, source.label);
  phrase = phrase.slice(0, 1).toUpperCase() + phrase.slice(1);
  return `${phrase} ${added ? positive : negative} ${entityPhrase(target.kind, target.label)}.`;
}

function relationshipChanges(base: DesignGraph, target: DesignGraph): [SemanticChange[], number] {
  const out: SemanticChange[] = [];
  let ignored = 0;
  const before = semanticEdges(base);
  const after = semanticEdges(target);
  const baseNodes = nodeMap(base);
  const targetNodes = nodeMap(target);
  const sorted = (entries: { key: RelKey; edge: GraphEdge }[]) => entries.sort((a, b) => compareRelKeys(a.key, b.key));

  for (const { key, edge } of sorted([...before.entries()].filter(([s]) => !after.has(s)).map(([, v]) => v))) {
    out.push(change({
      entity: 'relationship', domain: (baseNodes.get(edge.source) as GraphNode).kind, action: 'relationship_removed',
      subject_id: relationshipSubject(key), source_id: edge.source, target_id: edge.target,
      summary: relationshipSummary(edge, baseNodes, false),
    }));
  }
  for (const { key, edge } of sorted([...after.entries()].filter(([s]) => !before.has(s)).map(([, v]) => v))) {
    out.push(change({
      entity: 'relationship', domain: (targetNodes.get(edge.source) as GraphNode).kind, action: 'relationship_added',
      subject_id: relationshipSubject(key), source_id: edge.source, target_id: edge.target,
      summary: relationshipSummary(edge, targetNodes, true),
    }));
  }
  for (const { key, edge: o } of sorted([...before.entries()].filter(([s]) => after.has(s)).map(([, v]) => v))) {
    const n = (after.get(relKeyString(key)) as { edge: GraphEdge }).edge;
    if (o.id !== n.id) ignored += 1;
    ignored += ignoredAttributeChanges(o.attributes, n.attributes);
    const deltas = attributeDeltas(visible(o.attributes), visible(n.attributes));
    if (deltas.length) {
      const s = targetNodes.get(n.source) as GraphNode;
      const t = targetNodes.get(n.target) as GraphNode;
      out.push(change({
        entity: 'relationship', domain: s.kind, action: 'relationship_attributes_changed',
        subject_id: relationshipSubject(key), source_id: n.source, target_id: n.target,
        summary: `Updated ${n.kind} relationship from ${entityPhrase(s.kind, s.label)} to ${entityPhrase(t.kind, t.label)}: ${fieldList(deltas)}.`,
        deltas,
      }));
    }
  }
  return [out, ignored];
}

function counts(changes: readonly SemanticChange[], field: 'domain' | 'action'): [string, number][] {
  const map = new Map<string, number>();
  for (const c of changes) map.set(c[field], (map.get(c[field]) ?? 0) + 1);
  return [...map.entries()].sort((a, b) => compareCodepoints(a[0], b[0]));
}

const ACTION_ORDER = new Map<string, number>(CHANGE_ACTIONS.map((a, i) => [a, i]));

/** Deterministic, user-meaningful graph changes from base to target (B016 mirror). */
export function semanticDiff(base: DesignGraph, target: DesignGraph): SemanticDiff {
  // Same integrity gate as `_validated_snapshot`: both sides must round-trip.
  const checkedBase = parseDesignGraph(serializeDesignGraph(base));
  const checkedTarget = parseDesignGraph(serializeDesignGraph(target));
  if (checkedBase.projectId !== checkedTarget.projectId) {
    throw new SemanticDiffError('cannot diff design graphs from different projects', 'project_mismatch');
  }
  const [nodeCh, nodeIgnored] = nodeChanges(checkedBase, checkedTarget);
  const [relCh, relIgnored] = relationshipChanges(checkedBase, checkedTarget);
  const all = [...nodeCh, ...relCh];
  if (all.length > MAX_CHANGES) throw new SemanticDiffError('semantic change count exceeds configured bound', 'bound');
  const changes = all.sort(
    (a, b) =>
      compareCodepoints(a.domain, b.domain) ||
      (ACTION_ORDER.get(a.action) as number) - (ACTION_ORDER.get(b.action) as number) ||
      compareCodepoints(a.subject_id, b.subject_id) ||
      compareCodepoints(a.change_id, b.change_id),
  );
  let ignored = nodeIgnored + relIgnored;
  if (checkedBase.sourcePlanDigest !== checkedTarget.sourcePlanDigest) ignored += 1;
  const byDomain = counts(changes, 'domain').map(([domain, count]) => ({ domain, count }));
  const byAction = counts(changes, 'action').map(([action, count]) => ({ action, count }));
  const baseDigest = designGraphDigest(checkedBase);
  const targetDigest = designGraphDigest(checkedTarget);
  const payload: { [key: string]: JsonValue } = {
    schema: SEMANTIC_DIFF_SCHEMA,
    schema_version: SEMANTIC_DIFF_VERSION,
    project_id: checkedBase.projectId,
    base_revision: checkedBase.revision,
    target_revision: checkedTarget.revision,
    base_digest: baseDigest,
    target_digest: targetDigest,
    changes: changes.map(changePayload),
    counts_by_domain: byDomain,
    counts_by_action: byAction,
    ignored_change_count: ignored,
  };
  return Object.freeze({
    project_id: checkedBase.projectId,
    base_revision: checkedBase.revision,
    target_revision: checkedTarget.revision,
    base_digest: baseDigest,
    target_digest: targetDigest,
    changes: Object.freeze(changes),
    counts_by_domain: Object.freeze(byDomain),
    counts_by_action: Object.freeze(byAction),
    ignored_change_count: ignored,
    digest: sha256Hex(canonicalStringify(payload)),
  });
}

function changePayload(c: SemanticChange): JsonValue {
  return {
    change_id: c.change_id,
    entity: c.entity,
    domain: c.domain,
    action: c.action,
    subject_id: c.subject_id,
    summary: c.summary,
    source_id: c.source_id,
    target_id: c.target_id,
    deltas: c.deltas.map(deltaPayload),
  };
}

/** Same bytes as `serialize_semantic_diff` (`SemanticDiff.to_dict()`). */
export function serializeSemanticDiff(diff: SemanticDiff): string {
  return canonicalStringify({
    schema: SEMANTIC_DIFF_SCHEMA,
    schema_version: SEMANTIC_DIFF_VERSION,
    project_id: diff.project_id,
    base_revision: diff.base_revision,
    target_revision: diff.target_revision,
    base_digest: diff.base_digest,
    target_digest: diff.target_digest,
    changes: diff.changes.map(changePayload),
    counts_by_domain: diff.counts_by_domain.map((c) => ({ ...c })),
    counts_by_action: diff.counts_by_action.map((c) => ({ ...c })),
    ignored_change_count: diff.ignored_change_count,
    digest: diff.digest,
  });
}
