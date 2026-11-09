/**
 * Pure view-model for vision → component-graph previews.
 *
 * Mirrors the closed vocabulary of skeleton/forge/vision_compose.py (feature
 * names + canonical order) for presentation only: colours, labels and a
 * deterministic layered layout. It never decides *which* systems exist; that
 * is always the server's `features` / `matches` answer.
 */
import type { ComposeComponent, ComposeResult, ComposeWire } from './types';

export interface FeatureMeta {
  label: string;
  color: string;
  glyph: string;
  blurb: string;
}

/** Canonical order == vision_compose.FEATURES order (player first). */
export const FEATURE_ORDER = [
  'player',
  'combat',
  'crafting',
  'heat',
  'collapse',
  'extraction',
  'companion',
  'persistence',
  'hud',
] as const;

export const FEATURE_META: Record<string, FeatureMeta> = {
  player: { label: 'Player', color: '#94a3b8', glyph: '◎', blurb: 'the operator: intent + state' },
  combat: { label: 'Combat', color: '#ef4444', glyph: '⚔', blurb: 'hostile pressure that scales with player intent' },
  crafting: { label: 'Crafting', color: '#f59e0b', glyph: '⚒', blurb: 'turns salvaged parts into new weapons' },
  heat: { label: 'Heat', color: '#fb7185', glyph: '♨', blurb: 'escalation meter driven by player actions' },
  collapse: { label: 'Collapse', color: '#a855f7', glyph: '⏳', blurb: 'run-ending fail clock' },
  extraction: { label: 'Extraction', color: '#22c55e', glyph: '⇪', blurb: 'win condition: get out with the haul' },
  companion: { label: 'Companion', color: '#3b82f6', glyph: '✦', blurb: 'tactical companion reading player telemetry' },
  persistence: { label: 'Persistence', color: '#14b8a6', glyph: '▣', blurb: 'persistent player state and economy' },
  hud: { label: 'HUD', color: '#ec4899', glyph: '▤', blurb: 'player-facing readout' },
};

const UNKNOWN_META: FeatureMeta = { label: 'System', color: '#64748b', glyph: '•', blurb: '' };

export function featureMeta(name: string | undefined | null): FeatureMeta {
  if (!name) return UNKNOWN_META;
  return FEATURE_META[name] ?? { ...UNKNOWN_META, label: humanize(name) };
}

export function humanize(id: string): string {
  return String(id || '')
    .replace(/[_~-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/\b([a-z])/g, (m) => m.toUpperCase());
}

// ─── Vision highlighting ────────────────────────────────────────────────

export interface VisionSegment {
  text: string;
  /** Features this word triggered (empty for plain text). */
  features: string[];
}

const WORD_SPLIT = /([A-Za-z][A-Za-z0-9']*)/;

/** Map each matched (lower-case) word to the features it triggered. */
export function triggerIndex(matches: Record<string, string[]> | undefined | null): Map<string, string[]> {
  const index = new Map<string, string[]>();
  if (!matches) return index;
  for (const feature of FEATURE_ORDER) {
    for (const word of matches[feature] ?? []) {
      const key = String(word).toLowerCase();
      const list = index.get(key) ?? [];
      if (!list.includes(feature)) list.push(feature);
      index.set(key, list);
    }
  }
  // Features the UI does not know yet still highlight (in server order).
  for (const [feature, words] of Object.entries(matches)) {
    if ((FEATURE_ORDER as readonly string[]).includes(feature)) continue;
    for (const word of words ?? []) {
      const key = String(word).toLowerCase();
      const list = index.get(key) ?? [];
      if (!list.includes(feature)) list.push(feature);
      index.set(key, list);
    }
  }
  return index;
}

/**
 * Split the vision into plain / trigger segments. Whitespace and punctuation
 * are preserved verbatim so the rendered text reads exactly as typed.
 */
export function highlightVision(vision: string, matches: Record<string, string[]> | undefined | null): VisionSegment[] {
  const text = String(vision ?? '');
  if (!text) return [];
  const index = triggerIndex(matches);
  const out: VisionSegment[] = [];
  for (const part of text.split(WORD_SPLIT)) {
    if (!part) continue;
    const features = index.get(part.toLowerCase()) ?? [];
    const last = out[out.length - 1];
    if (!features.length && last && !last.features.length) {
      last.text += part;
    } else {
      out.push({ text: part, features: [...features] });
    }
  }
  return out;
}

// ─── Feature explanation rows ───────────────────────────────────────────

export interface FeatureRow {
  feature: string;
  meta: FeatureMeta;
  instanceId: string;
  kind: string;
  triggers: string[];
  /** Instance ids this component sends to. */
  feeds: string[];
  /** Instance ids this component receives from. */
  fedBy: string[];
}

export function explainComposition(result: ComposeResult | null | undefined): FeatureRow[] {
  if (!result) return [];
  const wires = result.wires ?? [];
  const rows: FeatureRow[] = [];
  for (const c of result.components ?? []) {
    const feature = c.feature || 'player';
    rows.push({
      feature,
      meta: featureMeta(feature),
      instanceId: c.instance_id,
      kind: c.kind,
      triggers: feature === 'player' ? [] : [...(result.matches?.[feature] ?? [])],
      feeds: unique(wires.filter((w) => w.from?.[0] === c.instance_id).map((w) => String(w.to?.[0]))),
      fedBy: unique(wires.filter((w) => w.to?.[0] === c.instance_id).map((w) => String(w.from?.[0]))),
    });
  }
  return rows;
}

/** Screen-reader sentence summarising the composed graph. */
export function describeComposition(result: ComposeResult | null | undefined): string {
  if (!result) return 'No composition yet.';
  const rows = explainComposition(result).filter((r) => r.feature !== 'player');
  if (!rows.length) return 'No systems composed.';
  const parts = rows.map((r) =>
    r.triggers.length ? `${r.meta.label} (from “${r.triggers.join('”, “')}”)` : `${r.meta.label}`,
  );
  const lead = result.fallback
    ? `No recognised systems in the vision; using the ${rows.length}-system fallback loop: `
    : `${rows.length} system${rows.length === 1 ? '' : 's'} composed: `;
  return `${lead}${parts.join(', ')}. ${(result.wires ?? []).length} wire${(result.wires ?? []).length === 1 ? '' : 's'}.`;
}

function unique<T>(xs: T[]): T[] {
  return Array.from(new Set(xs));
}

// ─── Layered layout ─────────────────────────────────────────────────────

export interface GraphNode {
  id: string;
  kind: string;
  feature: string;
  depth: number;
  wired: boolean;
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface GraphEdge {
  id: string;
  from: string;
  to: string;
  fromPort: string;
  toPort: string;
  d: string;
  labelX: number;
  labelY: number;
}

export interface GraphLayout {
  orientation: 'horizontal' | 'vertical';
  width: number;
  height: number;
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface LayoutOptions {
  /** Available width in px; drives orientation + wrapping. */
  width: number;
  nodeWidth?: number;
  nodeHeight?: number;
  gap?: number;
  pad?: number;
  /** Switch to a vertical (top-down) layout below this width. */
  breakpoint?: number;
}

/** Longest-path depth from the operator; unwired systems sit at depth 1. */
export function computeDepths(components: ComposeComponent[], wires: ComposeWire[]): Map<string, number> {
  const ids = components.map((c) => c.instance_id);
  const depth = new Map<string, number>(ids.map((id) => [id, 0]));
  const incoming = new Set(wires.map((w) => String(w.to?.[0])));
  for (const c of components) {
    if (c.feature !== 'player' && !incoming.has(c.instance_id)) depth.set(c.instance_id, 1);
  }
  // Bounded relaxation (graphs are DAGs of ≤ 9 nodes; the bound also
  // protects against a malformed cyclic payload).
  for (let pass = 0; pass < ids.length + 1; pass += 1) {
    let changed = false;
    for (const w of wires) {
      const a = String(w.from?.[0]);
      const b = String(w.to?.[0]);
      if (!depth.has(a) || !depth.has(b)) continue;
      const next = (depth.get(a) ?? 0) + 1;
      if (next > (depth.get(b) ?? 0) && next <= ids.length) {
        depth.set(b, next);
        changed = true;
      }
    }
    if (!changed) break;
  }
  return depth;
}

export function layoutGraph(
  components: ComposeComponent[] | undefined | null,
  wires: ComposeWire[] | undefined | null,
  opts: LayoutOptions,
): GraphLayout {
  const comps = components ?? [];
  const ws = (wires ?? []).filter((w) => Array.isArray(w.from) && Array.isArray(w.to));
  const pad = opts.pad ?? 16;
  const gap = opts.gap ?? 28;
  const avail = Math.max(200, Math.floor(opts.width || 0));
  const orientation: GraphLayout['orientation'] = avail >= (opts.breakpoint ?? 560) ? 'horizontal' : 'vertical';
  const w = opts.nodeWidth ?? (orientation === 'horizontal' ? 150 : Math.min(150, Math.floor((avail - pad * 2 - gap) / 2)));
  const h = opts.nodeHeight ?? 60;
  if (!comps.length) return { orientation, width: avail, height: pad * 2, nodes: [], edges: [] };

  const depths = computeDepths(comps, ws);
  const wiredIds = new Set<string>();
  for (const x of ws) {
    wiredIds.add(String(x.from[0]));
    wiredIds.add(String(x.to[0]));
  }
  const layers = new Map<number, ComposeComponent[]>();
  for (const c of comps) {
    const d = depths.get(c.instance_id) ?? 0;
    layers.set(d, [...(layers.get(d) ?? []), c]);
  }
  const layerKeys = Array.from(layers.keys()).sort((a, b) => a - b);
  const nodes: GraphNode[] = [];
  let width = avail;
  let height = pad * 2;

  if (orientation === 'horizontal') {
    const colGap = Math.max(gap * 2, Math.floor((avail - pad * 2 - layerKeys.length * w) / Math.max(1, layerKeys.length - 1)));
    const tallest = Math.max(...layerKeys.map((k) => layers.get(k)!.length));
    height = pad * 2 + tallest * h + (tallest - 1) * gap;
    layerKeys.forEach((k, col) => {
      const layer = layers.get(k)!;
      const layerH = layer.length * h + (layer.length - 1) * gap;
      const top = pad + (height - pad * 2 - layerH) / 2;
      layer.forEach((c, row) => {
        nodes.push(node(c, k, wiredIds, pad + col * (w + colGap), top + row * (h + gap), w, h));
      });
    });
    width = Math.max(avail, pad * 2 + layerKeys.length * w + (layerKeys.length - 1) * colGap);
  } else {
    const perRow = Math.max(1, Math.floor((avail - pad * 2 + gap) / (w + gap)));
    let y = pad;
    for (const k of layerKeys) {
      const layer = layers.get(k)!;
      for (let i = 0; i < layer.length; i += perRow) {
        const chunk = layer.slice(i, i + perRow);
        const rowW = chunk.length * w + (chunk.length - 1) * gap;
        const left = (avail - rowW) / 2;
        chunk.forEach((c, j) => nodes.push(node(c, k, wiredIds, left + j * (w + gap), y, w, h)));
        y += h + gap * 1.6;
      }
    }
    height = y - gap * 1.6 + pad;
  }

  const byId = new Map(nodes.map((n) => [n.id, n]));
  const edges: GraphEdge[] = [];
  ws.forEach((x, i) => {
    const a = byId.get(String(x.from[0]));
    const b = byId.get(String(x.to[0]));
    if (!a || !b) return;
    edges.push(edge(a, b, String(x.from[1] ?? ''), String(x.to[1] ?? ''), orientation, i));
  });
  return { orientation, width: Math.round(width), height: Math.round(height), nodes, edges };
}

function node(c: ComposeComponent, depth: number, wired: Set<string>, x: number, y: number, w: number, h: number): GraphNode {
  return {
    id: c.instance_id,
    kind: c.kind,
    feature: c.feature || 'player',
    depth,
    wired: wired.has(c.instance_id),
    x: Math.round(x),
    y: Math.round(y),
    w,
    h,
  };
}

function edge(a: GraphNode, b: GraphNode, fromPort: string, toPort: string, o: GraphLayout['orientation'], i: number): GraphEdge {
  const r = (n: number) => Math.round(n * 10) / 10;
  if (o === 'horizontal') {
    const x1 = a.x + a.w;
    const y1 = a.y + a.h / 2;
    const x2 = b.x;
    const y2 = b.y + b.h / 2;
    const dx = Math.max(24, (x2 - x1) / 2);
    return {
      id: `e${i}`, from: a.id, to: b.id, fromPort, toPort,
      d: `M${r(x1)},${r(y1)} C${r(x1 + dx)},${r(y1)} ${r(x2 - dx)},${r(y2)} ${r(x2)},${r(y2)}`,
      labelX: r((x1 + x2) / 2), labelY: r((y1 + y2) / 2 - 6),
    };
  }
  const x1 = a.x + a.w / 2;
  const y1 = a.y + a.h;
  const x2 = b.x + b.w / 2;
  const y2 = b.y;
  const dy = Math.max(18, (y2 - y1) / 2);
  return {
    id: `e${i}`, from: a.id, to: b.id, fromPort, toPort,
    d: `M${r(x1)},${r(y1)} C${r(x1)},${r(y1 + dy)} ${r(x2)},${r(y2 - dy)} ${r(x2)},${r(y2)}`,
    labelX: r((x1 + x2) / 2 + 4), labelY: r((y1 + y2) / 2),
  };
}
