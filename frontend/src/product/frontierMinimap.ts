/** Pure minimap, multilevel and world-portal navigation model (GF-P0-131).
 *
 * No React, no network. Panels feed it real Forge Studio layers and portal
 * connectors; it never invents layers or portals that the source does not
 * declare.
 */

export type FrontierLevelKind = 'underground' | 'surface' | 'sky';

export type MinimapLayer = {
  id: string;
  size: [number, number];
  elevation_m: number;
};

export type FrontierLevel = MinimapLayer & { kind: FrontierLevelKind; index: number };

export type PortalEndpoint = { layer: string; x: number; y: number };
export type FrontierPortal = {
  portal_id: string;
  from: PortalEndpoint;
  to: PortalEndpoint;
  mode: string;
  bidirectional: boolean;
};

export type MinimapView = {
  layer: string;
  zoom: number;
  center: [number, number];
};

export type MinimapViewport = {
  x0: number; y0: number; x1: number; y1: number;
  widthTiles: number; heightTiles: number;
};

export const MIN_ZOOM = 1;
export const MAX_ZOOM = 16;
/** Underground below this elevation, sky island at or above SKY_ELEVATION_M. */
export const UNDERGROUND_BELOW_M = 0;
export const SKY_ELEVATION_M = 120;
const KIND_ORDER: Record<FrontierLevelKind, number> = { underground: 0, surface: 1, sky: 2 };

function finite(value: number, fallback: number): number {
  return Number.isFinite(value) ? value : fallback;
}

export function classifyLevel(elevation_m: number): FrontierLevelKind {
  const e = finite(elevation_m, 0);
  if (e < UNDERGROUND_BELOW_M) return 'underground';
  if (e >= SKY_ELEVATION_M) return 'sky';
  return 'surface';
}

/** Order layers bottom-to-top (deepest underground first), dropping invalid ones. */
export function buildLevelStack(layers: readonly MinimapLayer[]): FrontierLevel[] {
  const seen = new Set<string>();
  const valid = layers.filter(layer => {
    if (!layer || typeof layer.id !== 'string' || !layer.id || seen.has(layer.id)) return false;
    const [w, h] = layer.size || [0, 0];
    if (!(Number.isSafeInteger(w) && Number.isSafeInteger(h) && w > 0 && h > 0)) return false;
    seen.add(layer.id);
    return true;
  });
  return valid
    .map(layer => ({ ...layer, kind: classifyLevel(layer.elevation_m) }))
    .sort((a, b) => KIND_ORDER[a.kind] - KIND_ORDER[b.kind]
      || finite(a.elevation_m, 0) - finite(b.elevation_m, 0)
      || a.id.localeCompare(b.id))
    .map((layer, index) => ({ ...layer, index }));
}

export function clampZoom(zoom: number): number {
  const z = finite(zoom, MIN_ZOOM);
  return Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, z));
}

/** Zoom by powers of two: +1 doubles, -1 halves, always inside bounds. */
export function stepZoom(zoom: number, direction: 1 | -1): number {
  return clampZoom(direction > 0 ? clampZoom(zoom) * 2 : clampZoom(zoom) / 2);
}

export function canZoom(zoom: number, direction: 1 | -1): boolean {
  return stepZoom(zoom, direction) !== clampZoom(zoom);
}

function clampInt(value: number, lo: number, hi: number): number {
  return Math.min(hi, Math.max(lo, Math.round(finite(value, lo))));
}

/** Tile rectangle visible at this zoom; always inside the layer. */
export function viewportFor(view: MinimapView, layer: MinimapLayer): MinimapViewport {
  const [w, h] = layer.size;
  const zoom = clampZoom(view.zoom);
  const widthTiles = Math.max(1, Math.min(w, Math.ceil(w / zoom)));
  const heightTiles = Math.max(1, Math.min(h, Math.ceil(h / zoom)));
  const cx = clampInt(view.center[0], 0, w - 1);
  const cy = clampInt(view.center[1], 0, h - 1);
  const x0 = clampInt(cx - Math.floor(widthTiles / 2), 0, w - widthTiles);
  const y0 = clampInt(cy - Math.floor(heightTiles / 2), 0, h - heightTiles);
  return { x0, y0, x1: x0 + widthTiles - 1, y1: y0 + heightTiles - 1, widthTiles, heightTiles };
}

export function initialView(stack: readonly FrontierLevel[]): MinimapView | null {
  const start = stack.find(level => level.kind === 'surface') || stack[0];
  if (!start) return null;
  return {
    layer: start.id,
    zoom: MIN_ZOOM,
    center: [Math.floor((start.size[0] - 1) / 2), Math.floor((start.size[1] - 1) / 2)],
  };
}

/** Move one level up (+1) or down (-1), keeping relative position on the new layer. */
export function switchLevel(
  stack: readonly FrontierLevel[], view: MinimapView, direction: 1 | -1,
): MinimapView {
  const current = stack.find(level => level.id === view.layer);
  if (!current) return view;
  const next = stack[current.index + direction];
  if (!next) return view;
  return { ...view, layer: next.id, center: rescale(view.center, current.size, next.size) };
}

export function jumpToLevel(stack: readonly FrontierLevel[], view: MinimapView, layerId: string): MinimapView {
  const current = stack.find(level => level.id === view.layer);
  const target = stack.find(level => level.id === layerId);
  if (!target || !current || target.id === current.id) return view;
  return { ...view, layer: target.id, center: rescale(view.center, current.size, target.size) };
}

function rescale(center: [number, number], from: [number, number], to: [number, number]): [number, number] {
  const fx = from[0] > 1 ? center[0] / (from[0] - 1) : 0.5;
  const fy = from[1] > 1 ? center[1] / (from[1] - 1) : 0.5;
  return [Math.round(fx * (to[0] - 1)), Math.round(fy * (to[1] - 1))];
}

export function panView(view: MinimapView, layer: MinimapLayer, dx: number, dy: number): MinimapView {
  const step = Math.max(1, Math.floor(viewportFor(view, layer).widthTiles / 4));
  const [w, h] = layer.size;
  return {
    ...view,
    center: [clampInt(view.center[0] + dx * step, 0, w - 1), clampInt(view.center[1] + dy * step, 0, h - 1)],
  };
}

function endpointValid(end: PortalEndpoint, stack: readonly FrontierLevel[]): boolean {
  const layer = stack.find(level => level.id === end?.layer);
  return !!layer && Number.isSafeInteger(end.x) && Number.isSafeInteger(end.y)
    && end.x >= 0 && end.y >= 0 && end.x < layer.size[0] && end.y < layer.size[1];
}

/** Portals usable from a layer, with only declared, in-bounds endpoints. */
export function portalsFrom(
  portals: readonly FrontierPortal[], stack: readonly FrontierLevel[], layerId: string,
): { portal: FrontierPortal; exit: PortalEndpoint }[] {
  const out: { portal: FrontierPortal; exit: PortalEndpoint }[] = [];
  for (const portal of portals) {
    if (!portal || !endpointValid(portal.from, stack) || !endpointValid(portal.to, stack)) continue;
    if (portal.from.layer === layerId) out.push({ portal, exit: portal.to });
    else if (portal.bidirectional && portal.to.layer === layerId) out.push({ portal, exit: portal.from });
  }
  return out.sort((a, b) => a.portal.portal_id.localeCompare(b.portal.portal_id));
}

export function travelThroughPortal(
  portals: readonly FrontierPortal[], stack: readonly FrontierLevel[], view: MinimapView, portalId: string,
): MinimapView {
  const hit = portalsFrom(portals, stack, view.layer).find(entry => entry.portal.portal_id === portalId);
  if (!hit) return view;
  return { ...view, layer: hit.exit.layer, center: [hit.exit.x, hit.exit.y] };
}

export function levelLabel(level: FrontierLevel): string {
  const name = level.kind === 'underground' ? 'Underground' : level.kind === 'sky' ? 'Sky island' : 'Surface';
  return `${name} · ${level.id} · ${Math.round(finite(level.elevation_m, 0))} m`;
}
