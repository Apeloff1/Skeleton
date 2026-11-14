/**
 * Builder DNA — 100 sliders × 6 build categories = 600 sliders total.
 *
 *   Each appType (cli / web / api / mobile / desktop / fullstack) gets a
 *   parallel cockpit of 10 groups × 10 sliders. The slider _labels_ stay
 *   stable across categories but the _key prefix_ + descriptive hints
 *   carry the category's vocabulary so the cockpit feels native to each.
 *
 *   Key format:  `bdr_<category>_<group>_<slot>`  (always unique)
 *   Value range: 0.0 (skip / suppress) → 3.0 (saturate). 1.0 = default.
 */
import type { DnaTuple, DnaGroup } from './narrativeDnaData';

/** Public list of build categories — keep in sync with CodeToAppModal.appTypes. */
export const BUILDER_CATEGORIES: ReadonlyArray<{
  key: string;
  label: string;
  emoji: string;
  color: string;
  flavour: string;
}> = [
  { key: 'cli',       label: 'CLI',       emoji: '💻', color: '#a78bfa', flavour: 'command-line tools' },
  { key: 'web',       label: 'Web',       emoji: '🌐', color: '#06b6d4', flavour: 'web applications' },
  { key: 'api',       label: 'API',       emoji: '⚙️', color: '#fbbf24', flavour: 'REST/RPC services' },
  { key: 'mobile',    label: 'Mobile',    emoji: '📱', color: '#10b981', flavour: 'mobile apps' },
  { key: 'desktop',   label: 'Desktop',   emoji: '🖥️', color: '#3b82f6', flavour: 'desktop apps' },
  { key: 'fullstack', label: 'Fullstack', emoji: '📚', color: '#ec4899', flavour: 'fullstack systems' },
];

interface SlotSpec {
  slot:  string;            // unique key within a group
  label: string;            // user-facing label
  hint:  string;            // user-facing hint
}

interface GroupSpec {
  group: string;            // unique key within a category
  title: string;
  icon:  string;
  color: string;
  hint:  string;
  slots: SlotSpec[];        // exactly 10
}

/**
 * Master schema — 10 groups × 10 slots. Hints reference {flavour} which
 * is substituted with the category's `flavour` (e.g. "web applications").
 */
const SCHEMA: GroupSpec[] = [
  {
    group: 'perf', title: 'Performance & scaling', icon: 'speedometer', color: '#10b981',
    hint: 'Throughput, latency and resource use.',
    slots: [
      { slot: 'p95',          label: 'p95 latency budget',    hint: 'How aggressively to chase p95 wins in {flavour}' },
      { slot: 'cold',         label: 'Cold-start budget',     hint: 'Minimise first-byte time on boot' },
      { slot: 'hot',          label: 'Hot-path tuning',       hint: 'Hand-tune inner loops where hot' },
      { slot: 'cache',        label: 'Caching layers',        hint: 'Memoise / CDN / DB cache layering' },
      { slot: 'batch',        label: 'Batch operations',      hint: 'Coalesce IO bursts into batches' },
      { slot: 'concurrency',  label: 'Concurrency',           hint: 'Parallelism vs serial simplicity' },
      { slot: 'memory',       label: 'Memory footprint',      hint: 'Trade memory for CPU or vice-versa' },
      { slot: 'bundle',       label: 'Bundle / binary size',  hint: 'Tree-shake, split, prune unused' },
      { slot: 'profiling',    label: 'Profiling hooks',       hint: 'Add perf marks / spans for tracing' },
      { slot: 'sla',          label: 'SLA strictness',        hint: 'How strictly to enforce SLOs in {flavour}' },
    ],
  },
  {
    group: 'quality', title: 'Code quality & style', icon: 'code-slash', color: '#a78bfa',
    hint: 'How clean, terse and typed the produced code is.',
    slots: [
      { slot: 'terse',   label: 'Terseness',          hint: 'Concise vs verbose expressions in {flavour}' },
      { slot: 'naming',  label: 'Descriptive naming', hint: 'Long-descriptive vs short identifier names' },
      { slot: 'types',   label: 'Type strictness',    hint: 'Strict types over inference where possible' },
      { slot: 'fp',      label: 'Functional bias',    hint: 'Pure functions / immutability discipline' },
      { slot: 'decomp',  label: 'Decomposition',      hint: 'Break large units into small ones' },
      { slot: 'side',    label: 'Side-effects',       hint: 'Avoid hidden side-effects' },
      { slot: 'magic',   label: 'Magic numbers',      hint: 'Replace literals with named constants' },
      { slot: 'lint',    label: 'Lint strictness',    hint: 'Treat lint warnings as errors' },
      { slot: 'fmt',     label: 'Formatter strictness',hint: 'Strict formatter / prettier defaults' },
      { slot: 'comments',label: 'Comment density',    hint: 'Inline comments for non-obvious lines' },
    ],
  },
  {
    group: 'testing', title: 'Testing strategy', icon: 'flask', color: '#fbbf24',
    hint: 'Where the test budget gets invested.',
    slots: [
      { slot: 'unit',     label: 'Unit coverage',      hint: 'Pure-logic test breadth in {flavour}' },
      { slot: 'integ',    label: 'Integration depth',  hint: 'Cross-module / IO tests' },
      { slot: 'e2e',      label: 'E2E weight',         hint: 'Full-flow tests' },
      { slot: 'mock',     label: 'Mocking aggression', hint: 'Stub deps vs real wiring' },
      { slot: 'snapshot', label: 'Snapshot tests',     hint: 'Pin UI / serialised payloads' },
      { slot: 'fuzz',     label: 'Fuzz tests',         hint: 'Random input generators' },
      { slot: 'property', label: 'Property tests',     hint: 'Invariant / hypothesis tests' },
      { slot: 'contract', label: 'Contract tests',     hint: 'External API contract assertions' },
      { slot: 'chaos',    label: 'Chaos drills',       hint: 'Fault injection / resilience' },
      { slot: 'smoke',    label: 'Smoke checks',       hint: '"Can it boot" probes' },
    ],
  },
  {
    group: 'security', title: 'Security & compliance', icon: 'shield-half', color: '#ef4444',
    hint: 'Defensive posture and audit-readiness.',
    slots: [
      { slot: 'input',    label: 'Input validation',  hint: 'Validate every external input to {flavour}' },
      { slot: 'authn',    label: 'AuthN strictness',  hint: 'MFA / scoped tokens default-on' },
      { slot: 'authz',    label: 'AuthZ strictness',  hint: 'Role/attribute-level access checks' },
      { slot: 'secret',   label: 'Secret handling',   hint: 'Never log, always vault' },
      { slot: 'dep',      label: 'Dep audit',         hint: 'Block known-CVE dependencies' },
      { slot: 'csp',      label: 'CSP / sandbox',     hint: 'Tight content-security / sandbox' },
      { slot: 'sqli',     label: 'Injection guards',  hint: 'Parametrise queries; escape outputs' },
      { slot: 'gdpr',     label: 'Privacy compliance',hint: 'GDPR/CCPA-friendly defaults' },
      { slot: 'audit',    label: 'Audit trail',       hint: 'Tamper-evident audit logging' },
      { slot: 'polp',     label: 'Least privilege',   hint: 'Minimal IAM / file perms' },
    ],
  },
  {
    group: 'deploy', title: 'Deployment & DevOps', icon: 'rocket', color: '#06b6d4',
    hint: 'How the artefact ships and is run.',
    slots: [
      { slot: 'cicd',       label: 'CI/CD coverage',  hint: 'Push CI pipelines for every change' },
      { slot: 'iac',        label: 'IaC discipline',  hint: 'Terraform / Pulumi over click-ops' },
      { slot: 'containers', label: 'Containerisation',hint: 'Ship as immutable images' },
      { slot: 'rollback',   label: 'Rollback ease',   hint: 'Single-command rollback' },
      { slot: 'canary',     label: 'Canary rollout',  hint: 'Gradual % rollout vs all-at-once' },
      { slot: 'flag',       label: 'Feature flags',   hint: 'Gate risky paths behind flags' },
      { slot: 'auto',       label: 'Auto-scaling',    hint: 'Scale {flavour} based on load' },
      { slot: 'sec',        label: 'Secret rotation', hint: 'Auto-rotate credentials' },
      { slot: 'env',        label: 'Env parity',      hint: 'Dev/stage/prod parity discipline' },
      { slot: 'monitor',    label: 'Health probes',   hint: 'Liveness / readiness endpoints' },
    ],
  },
  {
    group: 'obs', title: 'Observability & logging', icon: 'pulse', color: '#22d3ee',
    hint: 'What the running system tells you.',
    slots: [
      { slot: 'log',     label: 'Log verbosity',    hint: 'Verbose vs sparse runtime logs' },
      { slot: 'struct',  label: 'Structured logs',  hint: 'JSON / key=value over plain text' },
      { slot: 'metric',  label: 'Metric coverage',  hint: 'Per-feature counters / gauges' },
      { slot: 'trace',  label: 'Distributed trace',hint: 'OTEL spans across {flavour} hops' },
      { slot: 'sample',  label: 'Sample rate',      hint: 'How aggressively to sample traces' },
      { slot: 'alert',   label: 'Alert sensitivity',hint: 'Page / warn thresholds' },
      { slot: 'sla',     label: 'SLO dashboards',   hint: 'Pre-baked SLO panels' },
      { slot: 'error',   label: 'Error capture',    hint: 'Forward errors to Sentry-style sink' },
      { slot: 'context', label: 'Log context',      hint: 'Request-id / user-id breadcrumbs' },
      { slot: 'retain',  label: 'Retention',        hint: 'Days to keep raw logs' },
    ],
  },
  {
    group: 'ux', title: 'UX / DX polish', icon: 'sparkles', color: '#ec4899',
    hint: 'Surface polish — both end-user UX and dev DX.',
    slots: [
      { slot: 'loading',   label: 'Loading states', hint: 'Skeletons & shimmers in {flavour}' },
      { slot: 'empty',     label: 'Empty states',   hint: 'Helpful empty / first-run screens' },
      { slot: 'error',     label: 'Error states',   hint: 'Friendly recoverable error UI' },
      { slot: 'micro',     label: 'Micro-interactions',hint: 'Animations, transitions, hover polish' },
      { slot: 'haptic',    label: 'Haptics / sound',hint: 'Feedback cues' },
      { slot: 'shortcut',  label: 'Power-user shortcuts',hint: 'Keyboard / gesture shortcuts' },
      { slot: 'onboard',   label: 'Onboarding',     hint: 'First-run tour intensity' },
      { slot: 'help',      label: 'In-app help',    hint: 'Inline tooltips & explainers' },
      { slot: 'dx_log',    label: 'DX logging',     hint: 'Helpful dev-mode console output' },
      { slot: 'dx_doc',    label: 'DX docstrings',  hint: 'Doc comments on public surface' },
    ],
  },
  {
    group: 'docs', title: 'Documentation', icon: 'document-text', color: '#3b82f6',
    hint: 'How much explanatory material accompanies the code.',
    slots: [
      { slot: 'readme',   label: 'README depth',    hint: 'Top-level README quality' },
      { slot: 'api',      label: 'API reference',   hint: 'Per-export reference docs' },
      { slot: 'tutorial', label: 'Tutorial walks',  hint: 'Step-by-step learn-by-doing' },
      { slot: 'examples', label: 'Code examples',   hint: 'Snippets per feature' },
      { slot: 'adr',      label: 'ADR records',     hint: 'Record architectural tradeoffs' },
      { slot: 'diagram',  label: 'Diagrams',        hint: 'Sequence / architecture diagrams' },
      { slot: 'patterns', label: 'Pattern catalog', hint: 'Document repeated patterns' },
      { slot: 'edge',     label: 'Edge-case notes', hint: 'Known limits / gotchas' },
      { slot: 'cl',       label: 'Changelog auto',  hint: 'Auto-generated changelogs' },
      { slot: 'inline',   label: 'Inline comments', hint: 'Explanatory inline comments' },
    ],
  },
  {
    group: 'a11y', title: 'A11y & i18n', icon: 'accessibility', color: '#f59e0b',
    hint: 'Inclusivity and reach for {flavour}.',
    slots: [
      { slot: 'contrast', label: 'Contrast',        hint: 'High-contrast palette discipline' },
      { slot: 'sr',       label: 'Screen-reader',   hint: 'Labels & landmarks for AT' },
      { slot: 'keyboard', label: 'Keyboard nav',    hint: 'Full keyboard accessibility' },
      { slot: 'motion',   label: 'Reduce motion',   hint: 'Honour prefers-reduced-motion' },
      { slot: 'font',     label: 'Font scaling',    hint: 'Respect OS font size' },
      { slot: 'i18n',     label: 'i18n breadth',    hint: 'Localise strings via catalogs' },
      { slot: 'rtl',      label: 'RTL support',     hint: 'Right-to-left layouts work' },
      { slot: 'a11y_doc', label: 'A11y docs',       hint: 'Document keyboard / SR flows' },
      { slot: 'colorblind',label: 'Colour-blind mode',hint: 'Distinguish status without colour alone' },
      { slot: 'subtitle', label: 'Captions',        hint: 'Captions / transcripts on media' },
    ],
  },
  {
    group: 'maint', title: 'Maintainability & evolution', icon: 'construct', color: '#f97316',
    hint: 'How easily the codebase evolves.',
    slots: [
      { slot: 'modular',  label: 'Modularity',      hint: 'Loosely coupled modules' },
      { slot: 'ports',    label: 'Ports & adapters',hint: 'Hexagonal boundaries for IO' },
      { slot: 'di',       label: 'Dependency injection',hint: 'Inject collaborators over imports' },
      { slot: 'migration',label: 'Migration friendliness',hint: 'Versioned schemas / contracts' },
      { slot: 'dep_pin',  label: 'Dep pinning',     hint: 'Pin & audit every dependency' },
      { slot: 'deprec',   label: 'Deprecation hygiene',hint: 'Clear deprecation paths' },
      { slot: 'compat',   label: 'Backward compat', hint: 'Avoid breaking changes' },
      { slot: 'plug',     label: 'Plugin surface',  hint: 'Expose plug-in / extension points' },
      { slot: 'fork',     label: 'Forkability',     hint: 'Easy to fork & customise' },
      { slot: 'license',  label: 'License clarity', hint: 'Clear OSS license headers' },
    ],
  },
];

/** Build the 100 sliders for a single category. */
function makeCategoryGroups(catKey: string, flavour: string): DnaGroup[] {
  return SCHEMA.map(grp => ({
    id:    `bdr_${catKey}_${grp.group}`,
    title: grp.title,
    icon:  grp.icon as any,
    color: grp.color,
    hint:  grp.hint.replace('{flavour}', flavour),
    items: grp.slots.map(s => [
      `bdr_${catKey}_${grp.group}_${s.slot}`,
      s.label,
      s.hint.replace('{flavour}', flavour),
    ] as DnaTuple),
  }));
}

/** Pre-computed map: category key → 100-slider cockpit groups. */
export const BUILDER_DNA_BY_CATEGORY: Record<string, DnaGroup[]> =
  BUILDER_CATEGORIES.reduce((acc, c) => {
    acc[c.key] = makeCategoryGroups(c.key, c.flavour);
    return acc;
  }, {} as Record<string, DnaGroup[]>);

/** Pre-computed map: category key → flat list of slider keys. */
export const BUILDER_DNA_KEYS_BY_CATEGORY: Record<string, string[]> =
  Object.keys(BUILDER_DNA_BY_CATEGORY).reduce((acc, k) => {
    acc[k] = BUILDER_DNA_BY_CATEGORY[k].flatMap(g => g.items.map(it => it[0]));
    return acc;
  }, {} as Record<string, string[]>);

/** All slider keys across every category (~600 entries). */
export const BUILDER_DNA_ALL_KEYS: readonly string[] =
  Object.values(BUILDER_DNA_KEYS_BY_CATEGORY).flat();

export const BUILDER_DNA_TOTAL_PER_CATEGORY = 100; // 10 groups × 10 slots
export const BUILDER_DNA_TOTAL_ALL = BUILDER_DNA_ALL_KEYS.length;

// ─── Presets ───────────────────────────────────────────────────────────
// Each preset is a function that, given the current cockpit map, returns
// a new map with the preset's slider biases applied. Other sliders are
// left untouched so the user can layer presets.
type PresetFn = (current: Record<string, number>) => Record<string, number>;

/** Returns a category-aware preset bundle. All preset key paths are
 *  prefixed by the active category's key so they only mutate the
 *  currently visible cockpit. */
export function builderPresetsForCategory(catKey: string): Record<string, PresetFn> {
  const px = `bdr_${catKey}_`;
  // Helper — only set keys that actually exist on the current category.
  const valid = new Set<string>(BUILDER_DNA_KEYS_BY_CATEGORY[catKey] || []);
  const bump = (m: Record<string, number>, leaf: string, v: number) => {
    const k = px + leaf;
    if (valid.has(k)) m[k] = v;
  };
  return {
    'MVP': (c) => {
      const m = { ...c };
      // Lean on speed-to-ship; downplay polish.
      bump(m, 'perf_p95',          0.6);
      bump(m, 'testing_unit',      0.6);
      bump(m, 'testing_e2e',       0.3);
      bump(m, 'docs_api',          0.5);
      bump(m, 'docs_diagram',      0.3);
      bump(m, 'a11y_rtl',          0.4);
      bump(m, 'maint_plug',        0.5);
      bump(m, 'quality_decomp',    1.4);
      bump(m, 'ux_loading',        1.6);
      bump(m, 'ux_empty',          1.6);
      return m;
    },
    'Production-ready': (c) => {
      const m = { ...c };
      bump(m, 'perf_p95',         2.3);
      bump(m, 'perf_cache',       2.2);
      bump(m, 'testing_unit',     2.4);
      bump(m, 'testing_integ',    2.0);
      bump(m, 'testing_smoke',    1.8);
      bump(m, 'security_input',   2.2);
      bump(m, 'security_secret',  2.5);
      bump(m, 'deploy_cicd',      2.4);
      bump(m, 'deploy_canary',    1.8);
      bump(m, 'obs_log',          2.0);
      bump(m, 'obs_trace',        2.2);
      bump(m, 'obs_metric',       2.0);
      bump(m, 'maint_compat',     2.0);
      bump(m, 'docs_readme',      1.6);
      return m;
    },
    'Security-first': (c) => {
      const m = { ...c };
      bump(m, 'security_input',  2.8);
      bump(m, 'security_authn',  2.8);
      bump(m, 'security_authz',  2.6);
      bump(m, 'security_secret', 2.9);
      bump(m, 'security_dep',    2.6);
      bump(m, 'security_sqli',   2.7);
      bump(m, 'security_csp',    2.4);
      bump(m, 'security_gdpr',   2.2);
      bump(m, 'security_polp',   2.4);
      bump(m, 'security_audit',  2.4);
      bump(m, 'obs_error',       2.2);
      return m;
    },
    'Performance-first': (c) => {
      const m = { ...c };
      bump(m, 'perf_p95',         2.8);
      bump(m, 'perf_cold',        2.6);
      bump(m, 'perf_hot',         2.5);
      bump(m, 'perf_cache',       2.6);
      bump(m, 'perf_batch',       2.2);
      bump(m, 'perf_concurrency', 2.4);
      bump(m, 'perf_memory',      2.0);
      bump(m, 'perf_bundle',      2.2);
      bump(m, 'perf_profiling',   2.2);
      bump(m, 'perf_sla',         2.4);
      return m;
    },
    'A11y-first': (c) => {
      const m = { ...c };
      bump(m, 'a11y_contrast',   2.6);
      bump(m, 'a11y_sr',         2.8);
      bump(m, 'a11y_keyboard',   2.6);
      bump(m, 'a11y_motion',     2.4);
      bump(m, 'a11y_font',       2.2);
      bump(m, 'a11y_i18n',       2.2);
      bump(m, 'a11y_rtl',        2.0);
      bump(m, 'a11y_colorblind', 2.4);
      bump(m, 'a11y_subtitle',   2.2);
      bump(m, 'a11y_a11y_doc',   2.0);
      bump(m, 'ux_micro',        1.6);
      return m;
    },
    'Defaults': (c) => {
      // Reset every slider belonging to this category to 1.0 — useful for
      // wiping a preset bias without touching other categories.
      const m = { ...c };
      for (const k of valid) m[k] = 1.0;
      return m;
    },
  };
}
