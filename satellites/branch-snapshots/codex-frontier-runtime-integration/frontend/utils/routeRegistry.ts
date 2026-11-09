/**
 * routeRegistry — central registry of every navigable route in the app.
 *
 * Used by /audit-routes for validation and by deep-link helpers. Routes
 * are categorised the same way as /menu so the UX stays consistent.
 *
 * To add a new route: drop a line here, drop the file in /app/<name>.tsx.
 */
export interface RouteEntry {
  path:     string;
  title:    string;
  category: 'core' | 'learn' | 'build' | 'code' | 'ai' | 'tools' | 'progress' | 'settings' | 'system';
  /** True if the route lazily lazy-loads heavy native modules and may
   *  be slow to mount. The audit screen surfaces this as a "heavy" badge. */
  heavy?: boolean;
}

export const ROUTE_REGISTRY: ReadonlyArray<RouteEntry> = [
  // ── Core ─────────────────────────────────────────────────────────
  { path: '/',            title: 'Entry (redirect)',     category: 'core' },
  { path: '/welcome',     title: 'Welcome / Starfall',   category: 'core' },
  { path: '/hub',         title: 'Ultimate Hub',         category: 'core', heavy: true },
  { path: '/menu',        title: 'Menu',                 category: 'core' },
  { path: '/safe-mode',   title: 'Safe Mode',            category: 'system' },
  { path: '/audit-routes',title: 'Audit Routes',         category: 'system' },
  { path: '/perf',        title: 'Performance',          category: 'system' },
  { path: '/telemetry',   title: 'Telemetry',            category: 'system' },

  // ── Learn ────────────────────────────────────────────────────────
  { path: '/my-classes',          title: 'My Classes',          category: 'learn' },
  { path: '/class-week',          title: 'Class Week',          category: 'learn' },
  { path: '/readingLibrary',      title: 'Reading Library',     category: 'learn' },
  { path: '/reading-corner',      title: 'Reading Corner',      category: 'learn' },
  { path: '/mega-academy',        title: 'Mega Academy',        category: 'learn' },
  { path: '/cs-academy',          title: 'CS Academy',          category: 'learn' },
  { path: '/math-academy',        title: 'Math Academy',        category: 'learn' },
  { path: '/math-academy-full',   title: 'Math Academy (Full)', category: 'learn' },
  { path: '/physics-academy',     title: 'Physics Academy',     category: 'learn' },
  { path: '/language-academy',    title: 'Language Academy',    category: 'learn' },
  { path: '/language-track',      title: 'Language Track',      category: 'learn' },
  { path: '/masterclass',         title: 'Masterclass',         category: 'learn' },
  { path: '/study-paths',         title: 'Study Paths',         category: 'learn' },
  { path: '/education',           title: 'Education Hub',       category: 'learn' },
  { path: '/learning-hub',        title: 'Learning Hub',        category: 'learn' },
  { path: '/immersive-learning',  title: 'Immersive Learning',  category: 'learn' },
  { path: '/immersive-tutor',     title: 'Immersive Tutor',     category: 'learn' },
  { path: '/knowledge-databases', title: 'Knowledge DBs',       category: 'learn' },
  { path: '/curriculum',          title: 'Curriculum',          category: 'learn' },
  { path: '/flashcards',          title: 'Flashcards',          category: 'learn' },
  { path: '/interactive-quizzes', title: 'Interactive Quizzes', category: 'learn' },
  { path: '/daily-challenges',    title: 'Daily Challenges',    category: 'learn' },
  { path: '/challenges',          title: 'Challenge Arena',     category: 'learn' },
  { path: '/rosetta',             title: 'Rosetta',             category: 'learn' },
  { path: '/rosetta-playground',  title: 'Rosetta Playground',  category: 'learn' },
  { path: '/bible',               title: 'Code Bible',          category: 'learn' },

  // ── Build ────────────────────────────────────────────────────────
  { path: '/galaxy',         title: 'Galaxy Studio',     category: 'build', heavy: true },
  { path: '/ai-game-generator', title: 'AI Game Generator', category: 'build' },
  { path: '/game-factory',   title: 'Game Factory',      category: 'build' },
  { path: '/code-to-app',    title: 'Code → App',        category: 'build' },
  { path: '/playground',     title: 'Code Playground',   category: 'build' },
  { path: '/assets',         title: 'Asset Pipeline',    category: 'build' },
  { path: '/music',          title: 'Music Pipeline',    category: 'build' },
  { path: '/imagine',        title: 'Imagine',           category: 'build' },
  { path: '/ai-pipeline',    title: 'AI Pipeline',       category: 'build' },
  { path: '/hybrid-pipeline',title: 'Hybrid Pipeline',   category: 'build' },
  { path: '/agents',         title: 'Multi-Agent',       category: 'build' },
  { path: '/multi-agent',    title: 'Multi-Agent (alt)', category: 'build' },
  { path: '/gallery',        title: 'Build Gallery',     category: 'build' },
  { path: '/my-builds',      title: 'My Builds',         category: 'build' },
  { path: '/agentCodex',     title: 'Agent Codex',       category: 'build' },
  { path: '/build-hub',      title: 'Build · Code · AI Hub', category: 'build' },

  // ── Code ─────────────────────────────────────────────────────────
  { path: '/compiler',       title: 'Compiler Suite',    category: 'code' },
  { path: '/debugger',       title: 'Debugger',          category: 'code' },
  { path: '/intelligence',   title: 'Code Intelligence', category: 'code' },
  { path: '/bugfix-library', title: 'Bugfix Library',    category: 'code' },
  { path: '/reference',      title: 'Reference Hub',     category: 'code' },
  { path: '/collab',         title: 'Live Collab',       category: 'code' },
  { path: '/collaboration',  title: 'Collaboration Hub', category: 'code' },
  { path: '/group-chat',     title: 'Group Chat',        category: 'code' },
  { path: '/vault',          title: 'Vault',             category: 'code' },
  { path: '/lang-recommend', title: 'Language Recommend',category: 'code' },

  // ── AI ───────────────────────────────────────────────────────────
  { path: '/jeeves',         title: 'Jeeves',            category: 'ai' },
  { path: '/jeeves-hub',     title: 'Jeeves Hub',        category: 'ai' },
  { path: '/jeeves-eq',      title: 'Jeeves EQ',         category: 'ai' },
  { path: '/jeeves-level',   title: 'Jeeves Level',      category: 'ai' },
  { path: '/jeeves-audio-test', title: 'Jeeves Audio',   category: 'ai' },
  { path: '/ai-suggestions', title: 'AI Suggestions',    category: 'ai' },
  { path: '/ai-interactions',title: 'AI Interactions',   category: 'ai' },
  { path: '/sota',           title: 'SOTA Models',       category: 'ai' },
  { path: '/sota-extended',  title: 'SOTA Extended',     category: 'ai' },

  // ── Tools ────────────────────────────────────────────────────────
  { path: '/apk-inspector',  title: 'APK Inspector',     category: 'tools' },
  { path: '/tools-arena',    title: 'Tools Arena',       category: 'tools' },
  { path: '/scheduler',      title: 'Scheduler',         category: 'tools' },
  { path: '/pomodoro',       title: 'Pomodoro',          category: 'tools' },
  { path: '/search',         title: 'Search',            category: 'tools' },
  { path: '/notes',          title: 'Sticky Notes',      category: 'tools' },
  { path: '/advanced',       title: 'Advanced Features', category: 'tools' },
  { path: '/offline-sync',   title: 'Offline Sync',      category: 'tools' },
  { path: '/thermal',        title: 'Thermal Monitor',   category: 'tools' },

  // ── Progress ─────────────────────────────────────────────────────
  { path: '/dashboard',      title: 'Dashboard',         category: 'progress' },
  { path: '/profile',        title: 'Profile',           category: 'progress' },
  { path: '/progress',       title: 'My Progress',       category: 'progress' },
  { path: '/achievements',   title: 'Achievements',      category: 'progress' },
  { path: '/gamification',   title: 'Gamification',      category: 'progress' },
  { path: '/leaderboard',    title: 'Leaderboard',       category: 'progress' },
  { path: '/certificate',    title: 'Certificate',       category: 'progress' },

  // ── Settings ─────────────────────────────────────────────────────
  { path: '/settings',                title: 'All Settings',          category: 'settings' },
  { path: '/settings/academy',        title: 'Academy Settings',      category: 'settings' },
  { path: '/settings/api',            title: 'API Settings',          category: 'settings' },
  { path: '/settings/coding',         title: 'Coding Settings',       category: 'settings' },
  { path: '/settings/galaxy-studio',  title: 'Galaxy Studio Settings',category: 'settings' },
  { path: '/settings/haptics',        title: 'Haptics Intensity',     category: 'settings' },
  { path: '/settings/jeeves',         title: 'Jeeves Settings',       category: 'settings' },
  { path: '/settings/offline',        title: 'Offline Settings',      category: 'settings' },
  { path: '/settings/feature-flags',  title: 'Feature Flags',         category: 'settings' },
];

export function getRoutesByCategory(): Record<string, RouteEntry[]> {
  const out: Record<string, RouteEntry[]> = {};
  for (const r of ROUTE_REGISTRY) {
    (out[r.category] ||= []).push(r);
  }
  return out;
}

export function getRouteCount(): number {
  return ROUTE_REGISTRY.length;
}
