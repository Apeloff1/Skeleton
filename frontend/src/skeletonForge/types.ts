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

/**
 * `BuildPlan.to_dict` from skeleton/jeeves/builder.py. Every field is
 * optional: older servers omit keys, and the plan viewer must tolerate that.
 */
export interface BuildPlanPayload {
  era?: string;
  seed?: string;
  tensor_fp?: string;
  oracle_index?: number;
  oracle_text?: string;
  briefing?: string;
  room_bias?: string;
  spawn_weapon?: boolean;
  extract_late?: boolean;
  enemy_mix?: Record<string, number>;
  recipes?: string[];
  notes?: string[];
  adapt?: string;
  slack?: number;
  authored?: string;
}

export interface RunRequest {
  vision: string;
  era?: string | null;
  archetype: string;
  target: string;
  answers: Record<string, string>;
  /** Sparse, explicitly overridden design tensor axes (0..1). */
  operator_axes?: Record<string, number>;
  generation?: string | null;
  include_files?: boolean;
  /** Optional playable Godot archetype sidecar scene (three verified templates). */
  playable_content?: boolean;
  /** Optional main-scene Godot boot, plus playable sidecar completion if present. */
  playtest?: 'auto' | 'require';
  /** Optional native room-entry quest attached to the generated Godot project. */
  quest_content?: boolean;
  quest_length?: number;
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
    /** Actual generated sidecar scene template: extraction|combat_loop|pipeline. */
    playable_archetype?: string | null;
  };
  jeeves?: { next?: { text?: string; action?: string; priority?: number } | null; briefing?: string } | null;
  sim?: { passed?: boolean; primary_dps?: number } | null;
  build_plan?: BuildPlanPayload | null;
  playtest?: { status?: string; passed?: boolean; verified?: boolean; errors?: string[] } | null;
  playable_scene_playtest?: { status?: string; passed?: boolean; verified?: boolean; scene?: string; errors?: string[] } | null;
  /** Source-bound, opt-in in-game launch/return control for the playable archetype. */
  playable_portal?: {
    schema?: string; scene?: string; script?: string; source_sha256?: string;
    return_supported?: boolean; headless_inert?: boolean; sealed?: boolean;
  };
  operator_axes?: Record<string, number>;
  /** Mechanical controls actually written into the native playable script. */
  playable_mechanics?: {
    schema?: 'skeleton.forge.playable_mechanics.v1';
    archetype?: string; source_verified?: boolean;
    applied_axes?: Record<string, number>;
  } | null;
  ledger?: { height?: number; head?: string; valid?: boolean } | null;
  file_names?: string[];
  /** Actual emitted files, returned only with explicit and bounded source export. */
  files?: Record<string, string>;
  source_manifest?: {
    schema?: string; file_count?: number; sha256?: string; files?: Record<string, string>;
  } | null;
  source_export?: {
    status?: 'ready' | 'unavailable'; bytes?: number; file_count?: number;
    manifest_sha256?: string; reason?: string;
  } | null;
  native_quest?: {
    schema?: string;
    source_world_sha256?: string;
    quest_sha256?: string;
    steps?: number;
    quest?: string;
    runtime?: string;
    replay_verified?: boolean;
    sealed?: boolean;
  };
  [k: string]: unknown;
}

export interface CockpitResult {
  [k: string]: unknown;
}
