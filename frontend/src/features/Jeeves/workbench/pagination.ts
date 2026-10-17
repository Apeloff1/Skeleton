export interface Page<T> {
  items: T[];
  index: number;
  pages: number;
  size: number;
  total: number;
  first: number;
  last: number;
  hasPrevious: boolean;
  hasNext: boolean;
}

/** Bound rendered collections while retaining filters and exports over the complete dataset. */
export function paginate<T>(items: readonly T[], requestedPage: number, requestedSize = 30): Page<T> {
  const size = Number.isFinite(requestedSize) ? Math.max(1, Math.min(100, Math.floor(requestedSize))) : 30;
  const pages = Math.max(1, Math.ceil(items.length / size));
  const index = Number.isFinite(requestedPage) ? Math.max(0, Math.min(pages - 1, Math.floor(requestedPage))) : 0;
  const offset = index * size;
  return {
    items: items.slice(offset, offset + size),
    index,
    pages,
    size,
    total: items.length,
    first: items.length ? offset + 1 : 0,
    last: Math.min(items.length, offset + size),
    hasPrevious: index > 0,
    hasNext: index + 1 < pages,
  };
}

export function pageForRecord<T extends { id: string }>(items: readonly T[], id: string, size = 30): number | null {
  const position = items.findIndex(item => item.id === id);
  if (position < 0) return null;
  const safeSize = paginate(items, 0, size).size;
  return Math.floor(position / safeSize);
}
