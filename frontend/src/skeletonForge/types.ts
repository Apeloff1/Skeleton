/**
 * Wire types for the Skeleton GameForge HTTP surface (`/api/skeleton/*`,
 * backend/routes/skeleton_gameforge.py). Only the fields the cockpit reads
 * are typed; everything else is tolerated as `unknown` so a backend that
 * grows new keys never breaks the UI.
 */

export type FeatureName =
  | 'combat'
  | 'crafting'
  | 'heat'
  | 'collapse'
  | 'extraction'
  | 'companion'
  | 'persistence'
  | 'hud'
  | 'player';

export interface ComposeComponent {
  instance_id: string;
  kind: string;
  feature: string;
}

export interface ComposeWire {
  from: string[];
  to: string[];
}

export interface TopologyPort {
  name: string;
  type: string;
  direction: string;
}

export interface TopologyComponent {
  kind: string;
  ports?: TopologyPort[];
  config?: { feature?: string; description?: string; triggers?: string[]; [k: string]: unknown };
}

export interface Topology {
  blueprint_id?: string;
  name?: string;
  components?: Record<string, TopologyComponent>;
  wires?: ComposeWire[];
}

/** `POST /api/skeleton/compose` response (and cockpit `COMPOSE` result). */
export interface ComposeResult {
  vision_chars?: number;
  features: string[];
  matches: Record<string, string[]>;
  fallback: boolean;
  components: ComposeComponent[];
  wires: ComposeWire[];
  blueprint_id?: string;
  summary?: string;
  topology?: Topology;
}

export interface Beat {
  id: string;
  prompt: string;
  options: string[];
}

export interface EraRow {
  id: string;
  primary_dps: number;
  speed: number;
  ttk: { trash?: number; elite?: number; boss?: number; player_glass?: number; [k: string]: number | undefined };
  philosophy: string;
}

export interface GenerationRow {
  key: string;
  label?: string;
  order?: number;
  tagline?: string;
  [k: string]: unknown;
}

export interface RunRequest {
  vision: string;
  era?: string | null;
  archetype: string;
  target: string;
  answers: Record<string, string>;
  generation?: string | null;
  include_files?: boolean;
}

export interface StageRow {
  name: string;
  status: string;
  attempts?: number;
  duration_s?: number;
  error?: string | null;
  gate_failure?: unknown;
}

export interface VerificationBlock {
  accepted?: boolean;
  score?: number;
  reason?: string;
  blocking_issues?: unknown[];
  project_issues?: unknown[];
  weakest_path?: string;
  thresholds?: Record<string, number>;
  summary?: {
    files_checked?: number;
    failed_files?: number;
    warned_files?: number;
    passed_files?: number;
    blocking_issues?: number;
  };
}

export interface VerifyLoopBlock {
  accepted?: boolean;
  stopped_reason?: string;
  threshold?: number;
  trace?: { rounds?: number; history?: number[]; stopped_reason?: string; forced_rounds?: number };
}

/** `POST /api/skeleton/run` response (only the parts the cockpit renders). */
export interface RunPayload {
  succeeded?: boolean;
  era?: string | null;
  generation?: string | null;
  reference?: string | null;
  citation?: string | null;
  run?: { run_id?: string; pipeline?: string; succeeded?: boolean; stages?: StageRow[] };
  forge?: {
    blueprint_id?: string | null;
    file_count?: number | null;
    primary_dps?: number | null;
    verification?: VerificationBlock | null;
    verify_loop?: VerifyLoopBlock | null;
    repair?: Record<string, unknown> | null;
    composition?: ComposeResult | null;
  };
  jeeves?: { next?: { text?: string; action?: string; priority?: number } | null; briefing?: string } | null;
  sim?: { passed?: boolean; primary_dps?: number } | null;
  build_plan?: { seed?: string; briefing?: string; room_bias?: string; enemy_mix?: Record<string, number> } | null;
  ledger?: { height?: number; head?: string; valid?: boolean } | null;
  file_names?: string[];
  [k: string]: unknown;
}

export interface CockpitResult {
  [k: string]: unknown;
}
