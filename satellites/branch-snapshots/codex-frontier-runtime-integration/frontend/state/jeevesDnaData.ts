/**
 * Jeeves Mastery Cockpit — 100 sliders across 10 categories.
 *
 *   • Each slider runs 0.0 (skip / suppress) → 3.0 (saturate).
 *   • 1.0 = neutral default. Toggle the categories collapsed to keep render
 *     cost low (same pattern as Galaxy Studio).
 *   • Keys must be globally unique snake_case strings prefixed by category.
 */
import type { DnaTuple, DnaGroup } from './narrativeDnaData';

export const JEEVES_DNA_GROUPS_DATA: DnaGroup[] = [
  // ── 1. Code Style (10) ────────────────────────────────────────────
  { id: 'jv_style', title: 'Code style', icon: 'code-slash', color: '#a78bfa',
    hint: 'How Jeeves writes code — terseness, naming, decomposition, types.',
    items: [
      ['jv_style_terseness',    'Terseness',          'Prefer concise expressions over verbose blocks'],
      ['jv_style_comments',     'Comment density',    'How chatty inline comments should be'],
      ['jv_style_naming',       'Descriptive naming', 'Long-descriptive vs short-cryptic identifier names'],
      ['jv_style_decomp',       'Decomposition',      'Break functions/components into smaller pieces'],
      ['jv_style_types',        'Type strictness',    'Lean into strict typing over inference'],
      ['jv_style_err',          'Error handling',     'Explicit guards / Result types over throws'],
      ['jv_style_sideeffects',  'Side-effect avoidance','Prefer pure functions / FP discipline'],
      ['jv_style_immutable',    'Immutability',       'Const-by-default, freeze data'],
      ['jv_style_linewidth',    'Line width',         'Hard wrap aggressively at <=80 cols'],
      ['jv_style_doc',          'Doc strings',        'Add JSDoc/docstrings on exports'],
    ] as DnaTuple[],
  },
  // ── 2. Architecture (10) ──────────────────────────────────────────
  { id: 'jv_arch', title: 'Architecture bias', icon: 'git-network', color: '#06b6d4',
    hint: 'How Jeeves shapes structural choices.',
    items: [
      ['jv_arch_monolith',     'Monolith bias',       'Favour single deployable over services'],
      ['jv_arch_layers',       'Layered separation',  'Strict UI/domain/infra boundaries'],
      ['jv_arch_di',           'Dependency injection','Inject collaborators over import-singletons'],
      ['jv_arch_event',        'Event-driven',        'Pub/sub over direct calls'],
      ['jv_arch_rest',         'REST-first',          'HTTP/REST over gRPC/WS unless needed'],
      ['jv_arch_bus',          'Message bus',         'Central bus for cross-module coordination'],
      ['jv_arch_repo',         'Repository pattern',  'Wrap persistence behind repositories'],
      ['jv_arch_hex',          'Hexagonal',           'Adapt-port boundaries for IO'],
      ['jv_arch_screaming',    'Screaming arch',      'Folder names reveal domain over framework'],
      ['jv_arch_ddd',          'DDD bias',            'Lean on aggregates / bounded contexts'],
    ] as DnaTuple[],
  },
  // ── 3. Testing (10) ───────────────────────────────────────────────
  { id: 'jv_test', title: 'Testing rigor', icon: 'flask', color: '#fbbf24',
    hint: 'Where Jeeves invests its testing budget.',
    items: [
      ['jv_test_unit',     'Unit coverage',     'Target line/branch coverage of pure logic'],
      ['jv_test_integ',    'Integration depth', 'Cross-module/IO tests'],
      ['jv_test_mock',     'Mocking strategy',  'Stub external deps aggressively'],
      ['jv_test_snapshot', 'Snapshot tests',    'UI/serialized snapshots'],
      ['jv_test_e2e',      'E2E weight',        'Browser/device flow coverage'],
      ['jv_test_contract', 'Contract tests',    'API contract assertions'],
      ['jv_test_fuzz',     'Fuzz tests',        'Random input generators'],
      ['jv_test_property', 'Property tests',    'Hypothesis-style invariants'],
      ['jv_test_smoke',    'Smoke checks',      'Light "can it boot" probes'],
      ['jv_test_chaos',    'Chaos drills',      'Fault injection / resilience'],
    ] as DnaTuple[],
  },
  // ── 4. Security (10) ──────────────────────────────────────────────
  { id: 'jv_sec', title: 'Security paranoia', icon: 'shield-half', color: '#ef4444',
    hint: 'How defensively Jeeves treats inputs and dependencies.',
    items: [
      ['jv_sec_input',  'Input validation',  'Validate every external input'],
      ['jv_sec_auth',   'Auth strictness',   'MFA / scoped tokens by default'],
      ['jv_sec_secret', 'Secret handling',   'Never log / always vault'],
      ['jv_sec_dep',    'Dep audit',         'Block known-CVE dependencies'],
      ['jv_sec_sandbox','Sandbox bias',      'Run untrusted code in jail'],
      ['jv_sec_csp',    'CSP enforcement',   'Tight content-security-policy'],
      ['jv_sec_csrf',   'CSRF protection',   'Anti-CSRF tokens on state changes'],
      ['jv_sec_sqli',   'SQL-injection wall','Parametrise every query'],
      ['jv_sec_ssrf',   'SSRF guards',       'Whitelist outbound network targets'],
      ['jv_sec_polp',   'Least privilege',   'Minimal IAM / file perms'],
    ] as DnaTuple[],
  },
  // ── 5. Performance (10) ───────────────────────────────────────────
  { id: 'jv_perf', title: 'Performance bias', icon: 'speedometer', color: '#10b981',
    hint: 'Latency / memory / bundle-size tradeoffs.',
    items: [
      ['jv_perf_latency',   'Latency focus',     'Optimise wall-time over memory'],
      ['jv_perf_batching',  'Batch operations',  'Coalesce IO into batches'],
      ['jv_perf_cache',     'Caching layers',    'Add memoisation / HTTP cache'],
      ['jv_perf_lazy',      'Lazy loading',      'Defer non-critical code paths'],
      ['jv_perf_bundle',    'Bundle size',       'Aggressive tree-shake / split'],
      ['jv_perf_fp',        'Functional purity', 'Bias to pure fns despite alloc cost'],
      ['jv_perf_coldstart', 'Cold-start budget', 'Trim startup work'],
      ['jv_perf_hotpath',   'Hot-path tuning',   'Hand-optimise inner loops'],
      ['jv_perf_profile',   'Auto profiling',    'Add perf marks / traces'],
      ['jv_perf_opt_aggro', 'Optimisation aggression','Premature optimisation tolerance'],
    ] as DnaTuple[],
  },
  // ── 6. Documentation (10) ─────────────────────────────────────────
  { id: 'jv_doc', title: 'Documentation richness', icon: 'document-text', color: '#3b82f6',
    hint: 'How much explanatory material Jeeves authors alongside code.',
    items: [
      ['jv_doc_api',       'API reference',     'Per-export reference docs'],
      ['jv_doc_readme',    'README quality',    'Top-level project READMEs'],
      ['jv_doc_adr',       'Architecture decisions','Record ADRs for tradeoffs'],
      ['jv_doc_examples',  'Code examples',     'Snippets per feature'],
      ['jv_doc_diagram',   'Diagrams',          'Sequence / arch diagrams'],
      ['jv_doc_tutorial',  'Tutorial walks',    'Step-by-step learn-by-doing'],
      ['jv_doc_inline',    'Inline comments',   'Explain non-obvious lines'],
      ['jv_doc_changelog', 'Changelog auto',    'Generate changelog from commits'],
      ['jv_doc_patterns',  'Pattern catalogue', 'Document repeated patterns'],
      ['jv_doc_edge',      'Edge-case notes',   'Document known limits / gotchas'],
    ] as DnaTuple[],
  },
  // ── 7. Refactor (10) ──────────────────────────────────────────────
  { id: 'jv_ref', title: 'Refactor aggressiveness', icon: 'construct', color: '#f97316',
    hint: 'How eagerly Jeeves rewrites neighbouring code.',
    items: [
      ['jv_ref_rename',  'Rename freely',    'Rename for clarity even outside scope'],
      ['jv_ref_extract', 'Extract functions','Pull complex blocks into helpers'],
      ['jv_ref_dedupe',  'Dedupe',           'Collapse repeated patterns'],
      ['jv_ref_magicnum','Magic-number kill','Replace literals with consts'],
      ['jv_ref_dead',    'Dead code removal','Strip unused code'],
      ['jv_ref_format',  'Reformat',         'Apply formatter to touched files'],
      ['jv_ref_lint',    'Lint fix',         'Run lint --fix on edits'],
      ['jv_ref_smell',   'Code-smell radar', 'Flag complexity / long fns'],
      ['jv_ref_recursion','Recursion vs loop','Prefer recursion where natural'],
      ['jv_ref_pattern', 'Pattern match',    'Lean on pattern-matching style'],
    ] as DnaTuple[],
  },
  // ── 8. Reviewer voice (10) ────────────────────────────────────────
  { id: 'jv_voice', title: 'Reviewer voice', icon: 'chatbubbles', color: '#ec4899',
    hint: 'Tone Jeeves uses when reviewing code or answering.',
    items: [
      ['jv_voice_friendly', 'Friendliness',      'Warm / encouraging tone'],
      ['jv_voice_blunt',    'Bluntness',         'Direct vs softened phrasing'],
      ['jv_voice_depth',    'Depth of reply',    'Short fix vs full rationale'],
      ['jv_voice_examples', 'Examples included', 'Always show code examples'],
      ['jv_voice_altsol',   'Alt solutions',     'Offer alternatives, not single answer'],
      ['jv_voice_citing',   'Code citation',     'Reference exact file/line numbers'],
      ['jv_voice_blocker',  'Blocker tagging',   'Mark blocker vs nit'],
      ['jv_voice_ranking',  'Priority ranking',  'Order findings by severity'],
      ['jv_voice_freq',     'Comment frequency', 'How often to chime in'],
      ['jv_voice_mentor',   'Mentorship tone',   'Teach-don\'t-just-fix posture'],
    ] as DnaTuple[],
  },
  // ── 9. Tooling (10) ───────────────────────────────────────────────
  { id: 'jv_tool', title: 'Tooling preferences', icon: 'hardware-chip', color: '#22d3ee',
    hint: 'Stack & toolchain leanings.',
    items: [
      ['jv_tool_ts',         'TypeScript bias',  'Prefer TS over JS'],
      ['jv_tool_py',         'Python bias',      'Prefer Python for scripting'],
      ['jv_tool_rust',       'Rust bias',        'Prefer Rust for systems work'],
      ['jv_tool_agnostic',   'Framework-agnostic','Avoid framework lock-in'],
      ['jv_tool_latest',     'Bleeding edge',    'Latest vs stable releases'],
      ['jv_tool_monorepo',   'Monorepo bias',    'One repo over many'],
      ['jv_tool_polyrepo',   'Polyrepo bias',    'Many small repos'],
      ['jv_tool_ci',         'CI automation',    'Push CI pipelines for everything'],
      ['jv_tool_oss',        'OSS bias',         'Open-source over proprietary'],
      ['jv_tool_ide',        'IDE plug-ins',     'Author editor extensions'],
    ] as DnaTuple[],
  },
  // ── 10. Error narrative (10) ──────────────────────────────────────
  { id: 'jv_errn', title: 'Error narrative', icon: 'warning', color: '#f59e0b',
    hint: 'How Jeeves talks about and surfaces failures.',
    items: [
      ['jv_errn_stack',     'Stack verbosity',     'Full stack vs trimmed'],
      ['jv_errn_context',   'Context messages',    'Add what-when-why on every error'],
      ['jv_errn_recovery',  'Recovery tips',       'Suggest next steps'],
      ['jv_errn_antipat',   'Anti-pattern call',   'Name the anti-pattern in messages'],
      ['jv_errn_diff',      'Diff annotation',     'Show before/after diff on fix'],
      ['jv_errn_blame',     'Blame integration',   'Tag the responsible commit'],
      ['jv_errn_rootcause', 'Root-cause depth',    'Dig past the symptom'],
      ['jv_errn_log',       'Log richness',        'Verbose vs sparse log output'],
      ['jv_errn_telemetry', 'Telemetry capture',   'Forward errors to telemetry'],
      ['jv_errn_panic',     'Panic vs graceful',   'Crash hard vs degrade'],
    ] as DnaTuple[],
  },
];

export const JEEVES_DNA_KEYS: readonly string[] =
  JEEVES_DNA_GROUPS_DATA.flatMap(g => g.items.map(([k]) => k));

export const JEEVES_DNA_TOTAL = JEEVES_DNA_KEYS.length; // 100
