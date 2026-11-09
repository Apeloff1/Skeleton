/**
 * Wire types for the forge operator console.
 *
 * Two real backends are driven from here:
 *   • the Skeleton engine (`SKELETON_API_BASE`, FastAPI mounted at /api/v1):
 *     stateful cockpit (`/context/snapshot`, `/context/command`), the sealed
 *     ten-stage forge (`/gameforge/run`, `/gameforge/intake`) and the public
 *     forge catalogue (`/forge/kinds`, `/forge/eras`, `/ledger/*`);
 *   • the application backend (`API_BASE`): era/beat/generation catalogues,
 *     plan and walk previews (`/api/skeleton/*`, backend/routes/skeleton_gameforge.py)
 *     and the governed execution fabric (`/api/admin/ops/product-control/*`).
 *
 * Shapes mirror skeleton/context/cockpit.py, skeleton/context/pipeline.py,
 * skeleton/forge/{playtest,repair,verify_loop,sim,walk}.py. Only fields the
 * console reads are typed; unknown keys are tolerated so a growing backend
 * never breaks the UI. Shared compose/stage/verification shapes come from
 * the skeleton-forge contract so both surfaces agree on one definition.
 */
import type {
  Beat,
  ComposeResult,
  EraRow,
  GenerationRow,
  RunPayload,
  StageRow,
  VerificationBlock,
  VerifyLoopBlock,
} from '../skeletonForge/types';

export type { Beat, ComposeResult, EraRow, GenerationRow, StageRow, VerificationBlock };

/** skeleton/context/tensor.py AXES (order matters for bar layout). */
export const TENSOR_AXES = [
  'risk', 'tempo', 'lethality', 'opacity', 'scarcity',
  'agency', 'spectacle', 'intimacy', 'grind', 'authorial',
] as const;
export type TensorAxis = (typeof TENSOR_AXES)[number];

/** skeleton/context/dodeca.py faces. */
export const LATTICE_FACES = [
  'combat', 'heat', 'loot', 'forge', 'extract', 'narrative',
  'ai', 'world', 'economy', 'ui', 'audio', 'meta',
] as const;

/** GameForgeRun stage order (skeleton/context/pipeline.py). */
export const FORGE_STAGES = [
  'ingest', 'detect', 'tensor', 'lattice', 'oracle',
  'forge', 'jeeves', 'sim', 'emit', 'seal',
] as const;
export type ForgeStage = (typeof FORGE_STAGES)[number];

/** skeleton/forge/playtest.py PLAYTEST_MODES. */
export const PLAYTEST_MODES = ['off', 'auto', 'require'] as const;
export type PlaytestMode = (typeof PLAYTEST_MODES)[number];

/** skeleton/forge/repair.py REPAIR_MODES. */
export const REPAIR_MODES = ['apply', 'suggest'] as const;
export type RepairMode = (typeof REPAIR_MODES)[number];

/** skeleton/application/command_contracts.py MATERIALISE_TARGETS. */
export const MATERIALISE_TARGETS = ['json', 'yaml', 'godot'] as const;
export type MaterialiseTarget = (typeof MATERIALISE_TARGETS)[number];

/** skeleton/context/pipeline.py COMPOSE_ARCHETYPES (vision-composed forging). */
export const COMPOSE_ARCHETYPES = ['auto', 'vision'] as const;

// ── Cockpit ────────────────────────────────────────────────────────────

export interface TensorState {
  era: string;
  axes: Record<string, number>;
  dominant: { axis: string; value: number }[];
  fingerprint: string;
}

export interface LatticeState {
  era: string;
  faces: Record<string, number>;
  hottest: { face: string; p: number }[];
  vertices: number;
  edges: number;
}

export interface HelixState {
  turns: number;
  twist: number;
  writhe: number;
  linking_number: number;
  supercoiling: number;
  nicked: number;
  Tm: number;
  pairs?: unknown[];
}

export interface LedgerHead {
  height: number;
  head: string;
  valid: boolean;
}

export interface SnowballState {
  mass: number;
  complete: boolean;
  done: Record<string, number>;
  missing: string[];
  log: string[];
}

export interface OracleReading {
  index: number;
  text: string;
  faces: string[];
  weight: number;
  seed: string;
}

/** `GET /api/v1/context/snapshot` (Cockpit.snapshot()). */
export interface CockpitSnapshot {
  tensor: TensorState;
  lattice: LatticeState;
  helix: HelixState;
  ledger: LedgerHead;
  snowball: SnowballState;
  oracle: OracleReading | null;
  blend: [string, string, number] | null;
  generation: string | null;
  archetype: string | null;
  composition: ComposeResult | null;
  history: string[];
}

/** `POST /api/v1/context/command` success envelope (Cockpit.apply()). */
export interface CommandEnvelope {
  ok: boolean;
  verb: string;
  result: unknown;
}

// ── Forge run ──────────────────────────────────────────────────────────

/** skeleton/forge/playtest.py result. */
export interface PlaytestReport {
  status: 'passed' | 'failed' | 'unavailable' | string;
  passed: boolean;
  binary?: string | null;
  binary_source?: string | null;
  verified?: boolean;
  frames?: number;
  errors?: string[];
  reason?: string;
  returncode?: number | null;
  duration_s?: number;
  [k: string]: unknown;
}

export interface RepairAction {
  path?: string;
  class?: string;
  action?: string;
  issue?: string;
  notes?: unknown;
  applied?: number;
}

/** skeleton/forge/repair.py attempt_repair() (minus `files`). */
export interface RepairAttempt {
  kind?: string;
  mode?: RepairMode | string;
  ok?: number;
  reason?: string;
  weakest_path?: string;
  targeted_path?: string;
  before?: VerificationBlock;
  after?: VerificationBlock;
  actions?: RepairAction[];
  changed?: number;
  changed_paths?: string[];
  proposed_paths?: string[];
  [k: string]: unknown;
}

export interface VerifyRound {
  accepted: boolean;
  confidence: number;
  revised?: boolean;
  forge?: VerificationBlock;
  code?: { path?: string; confidence?: number; issues?: string[] };
}

export interface EngineVerifyLoop extends VerifyLoopBlock {
  repair_mode?: RepairMode | string;
  rounds_detail?: VerifyRound[];
  code_verdict?: { path?: string; confidence?: number; accepted_as_code?: boolean; issues?: string[]; advisory?: boolean } | null;
}

export interface FileReport {
  path: string;
  score: number;
  issues?: string[];
  hard_issues?: string[];
  soft_issues?: string[];
  subscores?: Record<string, number>;
}

export interface EngineVerification extends VerificationBlock {
  file_reports?: FileReport[];
}

export interface SimEncounter {
  enemy_id: string;
  mode: 'ideal' | 'thermal' | string;
  target_ttk: number;
  measured_ttk: number;
  error: number;
  shots?: number;
  vents?: number;
  overheat?: boolean;
  collapsed?: boolean;
  killed?: boolean;
  heat_end?: number;
}

export interface WalkStep {
  t: number;
  room: string;
  action: string;
  detail?: string;
}

/** skeleton/forge/walk.py WalkResult.to_dict(). */
export interface WalkResult {
  extracted: boolean;
  collapsed: boolean;
  passed: boolean;
  t: number;
  bound: number;
  mode: string;
  heat_peak: number;
  vents: number;
  hops: number;
  fights: number;
  cores: number;
  required_cores: number;
  path?: string[];
  notes?: string[];
  steps?: WalkStep[];
}

export interface SimReport {
  era: string;
  primary_dps: number;
  passed: boolean;
  collapse_max?: number;
  encounters?: SimEncounter[];
  notes?: string[];
  walk?: WalkResult | null;
}

/** skeleton/jeeves/builder.py BuildPlan.to_dict(). */
export interface BuildPlan {
  era: string;
  seed: string;
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

/** skeleton/context/questionnaire.py Intake.to_dict(). */
export interface IntakeSummary {
  era: string;
  tensor: TensorState;
  ballots: Record<string, number>;
  vision: string;
  answers: Record<string, string>;
}

/** `POST /api/v1/gameforge/run` / `/intake` body (GameForgeRun.execute()). */
export interface EngineRunPayload {
  succeeded?: boolean;
  era?: string | null;
  generation?: string | null;
  reference?: string | null;
  citation?: string | null;
  jeeves?: RunPayload['jeeves'];
  ledger?: LedgerHead | null;
  file_names?: string[];
  run?: { run_id?: string; pipeline?: string; succeeded?: boolean; stages?: StageRow[]; duration_s?: number };
  tensor?: TensorState;
  lattice?: LatticeState;
  oracle?: OracleReading | null;
  helix?: HelixState;
  snowball?: SnowballState;
  forge?: {
    blueprint_id?: string | null;
    file_count?: number | null;
    primary_dps?: number | null;
    verification?: EngineVerification | null;
    verify_loop?: EngineVerifyLoop | null;
    repair?: RepairAttempt | null;
    composition?: ComposeResult | null;
  };
  sim?: SimReport | null;
  playtest?: PlaytestReport | null;
  build_plan?: BuildPlan | null;
  intake?: IntakeSummary;
  G?: number;
  law?: string;
  mass?: number;
  complete?: boolean;
  postprocess_error?: string | null;
  [k: string]: unknown;
}

export interface EngineRunRequest {
  vision: string;
  era?: string;
  archetype?: string;
  target: MaterialiseTarget;
  playtest: PlaytestMode;
  repair_mode: RepairMode;
  answers?: Record<string, string>;
  include_files?: boolean;
}

export interface EngineIntakeRequest {
  answers: Record<string, string>;
  archetype?: string;
  target: MaterialiseTarget;
  playtest: PlaytestMode;
  repair_mode: RepairMode;
}

// ── Catalogues and previews ────────────────────────────────────────────

export interface EngineEras {
  eras: string[];
  default: string;
  sample: number;
}

export interface WalkPreview {
  walk: WalkResult;
  plan: BuildPlan;
}

export interface PlanRequest {
  vision?: string;
  era?: string | null;
  blend?: [string, string] | null;
  t?: number;
}

export interface EngineLedgerEntry {
  index?: number;
  kind?: string;
  hash?: string;
  prev?: string;
  payload?: Record<string, unknown>;
  [k: string]: unknown;
}

// ── Governed execution projection ──────────────────────────────────────

/** backend/core/cockpit_execution_projection.py CockpitExecutionProjection.as_dict(). */
export interface ExecutionProjection {
  operationId: string;
  state: string;
  confidence: 'low' | 'medium' | 'high' | string;
  pending: boolean;
  executorBound: boolean;
  receiptPresent: boolean;
  anomalyCount: number;
  anomalies: string[];
  evidenceSha256: string;
  writable: boolean;
}

export interface ExecutionProjectionResponse {
  count: number;
  rejected: number;
  executions: ExecutionProjection[];
}
