/**
 * src/utils/breadcrumbs.ts — frontend breadcrumb trail (Feb 2026).
 *
 * Mirrors the backend BreadcrumbTracker. Records the last 50 user
 * interactions / route changes / API errors in an in-memory ring so a
 * future error report or BootLauncher diagnostic sheet can include them.
 *
 *   trail.add('nav', 'route_change', { from: '/', to: '/hub' });
 *   trail.add('api', '500 on /api/x', { rid: 'abc...' });
 */
type Breadcrumb = {
  ts: number;
  category: string;
  message: string;
  level?: 'info' | 'warn' | 'error';
  data?: Record<string, any>;
};

const MAX = 50;
const _crumbs: Breadcrumb[] = [];

export const trail = {
  add(category: string, message: string, data?: Record<string, any>, level: Breadcrumb['level'] = 'info') {
    try {
      _crumbs.push({ ts: Date.now(), category, message, level, data });
      while (_crumbs.length > MAX) _crumbs.shift();
    } catch {}
  },
  snapshot(): Breadcrumb[] { return [..._crumbs]; },
  clear() { _crumbs.length = 0; },
};

export default trail;
