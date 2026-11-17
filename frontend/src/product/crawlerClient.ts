import { CryptoDigestAlgorithm, digestStringAsync } from 'expo-crypto';
import { API_BASE } from '../utils/apiBase';
import api, { type ApiResult } from '../utils/apiClient';
import { authHeaders, getAuthToken } from '../auth/gameforgeAuth';
import { ChatClientError, chatApiError } from './chatErrors';
import { canonicalPilotReceipt, pilotReceiptBody } from './crawlerPilotReceipt';

export type CrawlerReadiness = { available: boolean; configured: boolean; code: string; message: string; action?: string | null; network_reachability_verified?: boolean; limits: Record<string, number>; capabilities: Record<string, boolean> };
export type CrawlUsage = { requests: number; bytes: number; documents: number; failures: number; reserved_bytes?: number };
export type CrawlAutomation = {
  enabled: boolean; state: 'authorized' | 'running' | 'waiting' | 'stopped' | 'disabled' | 'blocked' | 'not_authorized';
  epoch: number; slices_started: number; max_slices: number; navigation_discourse?: boolean;
  expires_at: string | null; next_run_at: string | null; stop_reason: string | null;
};
export type CrawlWorker = { active: boolean; quiescent: boolean; local: boolean; lease_until: string | null; confirmation?: string; recovery_eligible?: boolean };
export type CrawlCapabilities = { can_run: boolean; can_pause: boolean; can_resume: boolean; can_cancel: boolean; can_erase: boolean; can_automate: boolean };
export type CrawlInstructionIncident = {
  sequence: number; url_digest: string; stage: 'response' | 'extracted' | 'robots_comment';
  categories: string[]; match_count_lower_bound: number; inspection_limited: boolean;
  inspected_bytes: number; input_digest: string | null; match_fingerprints: Record<string, string>;
  payload_retained: false; execution_authorized: false;
};
export type CrawlInstructionSecurity = {
  count: number; categories: Record<string, number>; records: CrawlInstructionIncident[];
  payload_retained: false; execution_authorized: false;
};
export type CrawlOriginHealth = {
  successes: number; failures: number; rejections: number; failure_streak: number;
  posterior_success: number; uncertainty: number; evidence_count: number;
};
export type CrawlDuplicateEvidence = { count: number; represented_sources: number; observed_origins: number; independent_evidence: false; raw_bytes_retained: false };
export type CrawlCheckpointRecovery = { replica_present: boolean; replica_verified: false; reason: string; last_repair_at: string | null; last_repair_sequence: number | null; ancestor_rollback: false };
export type CrawlHostEconomics = {
  host: string; observations: number; successes: number; failures: number; novelty_observations: number;
  mean_latency_seconds: number; tail_latency_seconds: number; mean_cost_bytes: number;
  reliability: number; novelty_probability: number; uncertainty: number; conservative_delay: number;
};
export type CrawlAcquisitionEconomics = {
  settled_requests: number; charged_bytes: number; uncertain_bytes: number;
  hosts: Record<string, CrawlHostEconomics>; network_authority_expanded: false;
};
export type DragonSanctuary = {
  schema: 'skeleton.dragon.sanctuary.v1'; collection_index: number; stage: number;
  form: 'hatchling' | 'scout' | 'scholar' | 'pathfinder' | 'archivist';
  eligible_expeditions: number; contributing_expeditions: number; unqualified_expeditions: number;
  candidate_sources: number; distinct_content: number; credited_sources: number; exact_duplicates: number;
  low_signal_sources: number; distinct_origins: number; habitats: Record<string, number>;
  source_refs: { session_id: string; source_id: string; credit_milli: number }[];
  revision_digest: string; candidate_limit_reached: boolean; as_of_unix: number; earliest_source_expiry: number | null;
  current_consent_only: true; persistent_reward_wallet: false; source_text_returned: false;
  training_permission: false; network_authority_expanded: false;
};
export type DragonQuest = {
  code: string; branch: 'discovery' | 'scholar' | 'ecology' | 'stewardship';
  target: number; progress: number; prerequisite: string | null;
  state: 'completed' | 'active' | 'locked'; applicable: boolean;
  source_ids: string[]; last_evidence_sequence: number | null; evidence_redacted?: boolean;
};
export type DragonQuestbook = {
  schema: 'skeleton.dragon.questbook.v1'; completed: number; total: number; quests: DragonQuest[];
  contribution_count: number; credited_sources: number; revision_digest: string;
  derived_not_persisted: true; training_permission: false; network_authority_expanded: false;
  evidence_access?: 'current_source_policy_filtered';
};
export type DragonCurriculumDecision = {
  strategy: 'companion' | 'companion_curiosity' | 'companion_scholar' | 'companion_guardian';
  quest: DragonCompanion['quest']; candidate_digest: string; eligible: number;
  base_milli: number; priority_milli: number; phase: 'policy' | 'content';
  network_authority_expanded: false; request: number; event_sequence: number;
  outcome: string; source_id: string | null;
};
export type DragonCurriculumTrace = {
  decisions: number;
  quests: Record<DragonCompanion['quest'], { content_attempts: number; captures: number; policy_attempts: number; uncertain_attempts: number }>;
  recent: DragonCurriculumDecision[]; training_permission: false; network_authority_expanded: false;
};
export type DragonCompanion = {
  schema: 'skeleton.dragon.companion.v1';
  form: 'hatchling' | 'scout' | 'scholar' | 'pathfinder' | 'archivist';
  stage: number; growth: number;
  skills: Record<'discovery' | 'understanding' | 'diversity' | 'discipline' | 'resilience', number>;
  energy: number;
  quest: 'explore' | 'synthesize' | 'diversify' | 'conserve' | 'recover' | 'rest';
  posture: 'resting' | 'recovering' | 'studying' | 'roaming';
  style: 'balanced' | 'curious' | 'scholarly' | 'guardian';
  captured_sources: number; novel_origins: number; habitats: Record<string, number>;
  covered_terms: number; term_count: number; multi_origin_terms: number;
  recovery_observations: number; quarantines: number; uncertain_bytes: number;
  unreviewed_evidence_only: true; network_authority_expanded: false;
  training_permission: false; inactivity_penalty: false;
  learning_progress: number; novelty_yield: number;
  questbook?: DragonQuestbook;
};
export type DragonEvolution = {
  form: 'hatchling' | 'scout' | 'scholar' | 'pathfinder' | 'archivist' | 'hoarder';
  stage: number; level: number; expedition_growth: number; treasury_growth: number;
  total_evolution: number; effective_evolution: number; stage_progress: number;
  hoarder_qualified: boolean; next_threshold: number | null;
};
export type DragonTreasuryWatch = {
  schema:'skeleton.dragon.treasury-watch.v1'; source_id:string; enabled:boolean;
  state:'waiting'|'working'|'stopped'|'blocked'; expires_at:number; max_cycles:number;
  cycles_started:number; cycles_completed:number; next_due:number; retention_days:number;
  minimum_interval:number; last_child_id:string|null; stop_reason:string|null;
  network_scope:'exact_public_seed_canonical_policy'; owner_revocable:true;
};
export type TreasuryWatchCommand = CrawlCommand & { enabled:boolean;source_id:string;days:number;cycles:number;
  minimum_interval:number;retention_days:number;capture_rights_acknowledged:boolean;archive_rights_acknowledged:boolean };
function validWatch(w:DragonTreasuryWatch):boolean {
  return !!w&&w.schema==='skeleton.dragon.treasury-watch.v1'&&HASH.test(w.source_id)
    &&typeof w.enabled==='boolean'&&['waiting','working','stopped','blocked'].includes(w.state)
    &&Number.isFinite(w.expires_at)&&Number.isFinite(w.next_due)&&w.next_due<=w.expires_at
    &&integer(w.max_cycles,6)&&w.max_cycles>0&&integer(w.cycles_started,w.max_cycles)&&integer(w.cycles_completed,w.cycles_started)
    &&integer(w.retention_days,30)&&w.retention_days>=1&&integer(w.minimum_interval,604800)&&w.minimum_interval>=21600
    &&(w.last_child_id===null||ID.test(w.last_child_id))
    &&(w.stop_reason===null||typeof w.stop_reason==='string'&&w.stop_reason.length<=64)
    &&w.network_scope==='exact_public_seed_canonical_policy'&&w.owner_revocable===true;
}
export type DragonArchiveGrant = { active: boolean; expires_at: number | null; granted_sources: number; usable_sources: number; history_only: true; network_authority_expanded: false };
export type TreasuryMode = 'current_only' | 'historic_only' | 'all_revisions' | 'timeline' | 'compare' | 'at_time';
export type TreasuryDelta = { kind: 'initial' | 'minor_update' | 'substantive_update' | 'major_rewrite' | 'changed_unclassified' | 'rollback'; similarity: number | null; added_terms: number | null; removed_terms: number | null; changed_sections: number | null; numeric_change: boolean | null };
export type TreasuryRevision = {
  revision_id: string; family_id: string; previous_revision_id: string | null;
  session_id: string | null; source_id: string | null; first_seen: number; last_seen: number;
  reobservations: number; indexed: boolean; metadata_only: boolean; archive_only: boolean; indexed_capture_at: number | null;
  latest_observed: boolean; plane: 'current' | 'historic'; projection_digest: string | null;
  delta: TreasuryDelta; score?: number;
};
export type TreasuryFamily = {
  family_id: string; revision_count: number; current_revision: string; first_seen: number; last_seen: number;
  current_indexed: boolean; simultaneous_conflict: boolean; alias_conflict: boolean; refresh_url: string | null;
  revisit: { due_at: number; change_probability_estimate: number; observed_changes: number; interval_seconds: number;
    ready_for_review: boolean; model: 'interval_censored_grid_v1'; qualified_intervals: number; ambiguous_intervals: number;
    expected_changes_per_day: number; utility_per_cost: number; target_stale_risk: number;
    fresh_consent_required: true; network_executed: false };
};
export type DragonVaultState = {
  state:'pending'|'vaulted'; accepted_at:number; active_slot_released:boolean; snapshot_digest:string;
  execution_authorized:false; historical_grant_extended:false;
};
export type DragonVaultScrub = {checked_at:number;state:'redundant'|'primary_only'|'repairable_primary'|'held';
  primary:'exact'|'held';replica:'exact'|'held'|'unavailable';live_verified:false};
export type DragonVaultCare = {enabled:boolean;active:boolean;issued_at:number;expires_at:number;budget:number;used:number;remaining:number;
  last_repair:{side:'primary'|'replica';at:number;version:number}|null;source_use_authorized:false;network_authorized:false};
export type DragonVaultCareHistory = {
  schema:'skeleton.dragon.vault-care-history.v1';session_id:string;version:number;as_of_unix:number;
  state:'recorded'|'unrecorded'|'held';prefix_unknown:boolean;omitted:number;
  events:{sequence:number;version:number;at:number;kind:'grant'|'withdraw'|'auto_primary'|'auto_replica';budget:number;used:number}[];
  read_only:true;independent_audit:false;source_text_returned:false;network_executed:false;
};
export async function getDragonVaultCareHistory(id:string,signal?:AbortSignal):Promise<DragonVaultCareHistory>{
  const p=await read(api.get<DragonVaultCareHistory>(ROOT+'/sessions/'+identifier(id)+'/vault-care-history',options(signal)),
    getAuthToken(),'Custody history unavailable.');
  if(!p||p.schema!=='skeleton.dragon.vault-care-history.v1'||p.session_id!==id||!integer(p.version)||p.version<1
    ||!Number.isFinite(p.as_of_unix)||p.as_of_unix<0||!['recorded','unrecorded','held'].includes(p.state)
    ||typeof p.prefix_unknown!=='boolean'||!integer(p.omitted,2147483647)||!Array.isArray(p.events)||p.events.length>16
    ||(p.state==='recorded'?p.events.length===0:!p.prefix_unknown||p.omitted!==0||p.events.length!==0)
    ||p.events.some((e,i)=>!e||e.sequence!==p.omitted+i+1||!integer(e.version,p.version)||e.version<1
      ||!['grant','withdraw','auto_primary','auto_replica'].includes(e.kind)||!Number.isFinite(e.at)||e.at<0||e.at>p.as_of_unix
      ||!integer(e.budget,3)||e.budget<1||!integer(e.used,e.budget)||(e.kind==='grant'||e.kind==='withdraw'?e.used!==0:e.used<1)
      ||i>0&&(e.version<=p.events[i-1].version||e.at<p.events[i-1].at))
    ||p.read_only!==true||p.independent_audit!==false||p.source_text_returned!==false||p.network_executed!==false)
    invalid('Invalid custody history receipt.');
  return p;
}
export type DragonVaultCareCommand = {schema:'skeleton.dragon.vault-care-command.v1';session_id:string;version:number;
  care:DragonVaultCare;network_executed:false};
function validVaultCare(p:DragonVaultCare,version:number,asOf?:number):boolean{
  return !!p&&typeof p.enabled==='boolean'&&typeof p.active==='boolean'
    &&Number.isFinite(p.issued_at)&&p.issued_at>=0&&Number.isFinite(p.expires_at)
    &&p.expires_at>p.issued_at&&p.expires_at-p.issued_at<=7*86400
    &&integer(p.budget,3)&&p.budget>=1&&integer(p.used,p.budget)&&p.remaining===p.budget-p.used
    &&(!p.active||p.enabled&&p.remaining>0)&&(asOf===undefined||p.active===(p.enabled&&p.remaining>0&&p.issued_at<=asOf&&asOf<p.expires_at))
    &&(p.used===0?p.last_repair===null:!!p.last_repair&&['primary','replica'].includes(p.last_repair.side)
      &&Number.isFinite(p.last_repair.at)&&p.last_repair.at>=p.issued_at&&p.last_repair.at<p.expires_at
      &&integer(p.last_repair.version,version)&&p.last_repair.version>=2)
    &&p.source_use_authorized===false&&p.network_authorized===false;
}
export async function configureDragonVaultCare(id:string,body:CrawlCommand&{enabled:boolean;days:number;repairs:number;retention_acknowledged:boolean},
  signal?:AbortSignal):Promise<DragonVaultCareCommand>{
  if(typeof body.enabled!=='boolean'||!integer(body.days,7)||body.days<1||!integer(body.repairs,3)||body.repairs<1
      ||typeof body.retention_acknowledged!=='boolean'||body.enabled&&!body.retention_acknowledged)invalid('Invalid finite maintenance consent.');
  const p=await read(api.post<DragonVaultCareCommand>(ROOT+'/sessions/'+identifier(id)+'/vault-care',body,options(signal)),
    getAuthToken(),'Maintenance consent unconfirmed. Reload before retrying.');
  if(!p||p.schema!=='skeleton.dragon.vault-care-command.v1'||p.session_id!==id||!integer(p.version)||p.version<=body.expected_version
    ||!validVaultCare(p.care,p.version)||p.care.enabled!==body.enabled||p.care.budget!==body.repairs
    ||Math.abs(p.care.expires_at-p.care.issued_at-body.days*86400)>0.001||p.network_executed!==false)invalid('Invalid maintenance consent receipt.');
  return p;
}
export type DragonVaultEntry = {session_id:string;version:number;vault:DragonVaultState|null;
  archive_expires_at:number|null;legacy_runtime:boolean|null;integrity_held:boolean;last_scrub?:DragonVaultScrub|null;care?:DragonVaultCare|null};
export type DragonVaultCatalog = {schema:'skeleton.dragon.vault-catalog.v1';sessions:DragonVaultEntry[];
  next_cursor:string|null;capacity:1024;as_of_unix:number;archive_use_verified:false;network_executed:false};
export type DragonVaultCommand = {schema:'skeleton.dragon.vault-command.v1';session_id:string;version:number;
  vault:DragonVaultState;outcome:'vaulted'|'held'|'capacity_or_quota_held'|'quota_held'|'superseded';network_executed:false};
export type DragonTreasury = {
  schema: 'skeleton.dragon.treasury.v1'; parser: 'retained-text-sections-v3'; mode: TreasuryMode;
  family: string | null; as_of_unix: number; partition_digest: string; candidate_limit_reached: boolean; excluded_sessions: number;
  observed_before: number | null; page_offset: number; next_cursor: string | null; query_scope_digest: string;
  comparison_selection: {left:string;right:string} | null;
  vault_window?:string[]|null;
  observations: number; families: number; revisions: number; changed_families: number; rollbacks: number;
  current_indexed: number; historic_indexed: number; metadata_only: number; blocked_current: number; changes: number; revalidated_revisions: number;
  verified_historic_transitions: number; verified_changed_families: number; alias_held_families: number; revisit_plan: string[]; parsed_unique_payloads: number;
  materialized_payload_hits: number; invalid_materialized_segments: number; legacy_history_sessions: number;
  index_health?: {active_grants:number; qualified_segments:number; missing_segments:number;
    stale_segments:number; invalid_segments:number; eligible_archive_members:number; materialized_archive_members:number};
  index_admission: 'temporal_diversity_v1'|'temporal_query_rerank_v2'; eligible_observations: number; indexed_observations: number;
  query_admission?: {eligible_representatives:number; scanned_representatives:number; scanned_bytes:number;
    matching_representatives:number; prioritized_representatives:number; full_structural_corpus:false;
    score_basis:'permitted_plane_scan_bm25'}|null;
  evolution: DragonEvolution; family_rows: TreasuryFamily[]; hits: TreasuryRevision[];
  timeline: TreasuryRevision[]; comparison: { current: TreasuryRevision; previous: TreasuryRevision; delta: TreasuryDelta } | null;
  earliest_source_expiry: number | null; latest_observed_only: true; source_text_returned: false;
  network_executed: false; training_permission: false; fresh_consent_required: true;
};
export type CrawlAcquisitionReadiness = {
  schema: 'skeleton.dragon.acquisition-readiness.v1';
  hosts: { host: string; state: 'consent_expired' | 'held_for_grant' | 'cooldown' | 'no_host_hold';
    host_ready_at: number; settled: number; denial_statuses: number; throttle_statuses: number;
    rejected_success_statuses: number; queued: number }[];
  settled_requests: number; queued: number;
  network_authority_expanded: false; reason_inferred: false;
  independent_intake_requires_new_authorization: true;
};
export type NavigationDiscourse = {
  url: string; quest: string; objective_coverage: number; uncovered_terms: number;
  evidence_novelty: number; jeeves_proposal: number; dragon_counterproposal: number;
  disagreement: number; final_priority: number; authority: 'advisory_only'; digest: string;
};
export type NavigationBacklogSummary = {
  unique_targets: number; pending: number; active: number; visited: number;
  depth_held_targets: number; counts: Record<string, number>;
  max_records: number; max_bytes: number; last_discourse: NavigationDiscourse | null;
  inventory_complete: false; authority: 'advisory_only';
};
export type NavigationTarget = {
  url: string; ordinal: number; depth: number; parent_url: string | null;
  parents: string[]; kind: string; relations: string[]; observations: number;
  pending: boolean; phase: 'visited' | 'active' | 'depth_held' | 'pending' | 'observed_only';
  navigation_authorized: false;
};
export type NavigationPacket = { snapshot_digest:string; packet_digest:string; as_of:number; objective:string[];
  candidates:{id:string;terms:string[];depth:number;attempts:number;semantic:number}[] };
export type NavigationAdvice = { snapshot_digest:string; packet_digest:string; as_of:number;
  jeeves_rank:string[];dragon_rank:string[] };
export type NavigationFederationPage = { targets:{id:string;url:string;host:string;semantic:number;
  witness:{grant_id:string;source_session:string;checkpoint:string;expires:number;relation:string;occurrence_count:number};
  network_authorized:false;reviewed:false}[]; next_cursor:string|null;
  candidate_metadata_only:true;network_authorized:false;global_completeness_claimed:false };
export type NavigationInventory = {
  ok: true; session_id: string; snapshot_digest: string; read_only: true;
  targets: NavigationTarget[]; next_after: number | null; summary: NavigationBacklogSummary;
  network_authorized: false;
};
export type CrawlSession = {
  session_id: string; title: string; status: 'queued' | 'ready' | 'running' | 'paused' | 'completed' | 'cancelled' | 'budget_exhausted' | 'failed' | 'interrupted';
  state?: string; version: number; created_at: string; updated_at: string; seeds: string[];
  limits: { max_requests: number; max_documents: number; max_total_bytes: number; max_depth: number; [key: string]: unknown };
  counters: CrawlUsage; frontier_count: number; source_count: number; consent_current: boolean; consent_expires_at: string;
  next_ready_at?: number | null; stop_reason?: string | null; error?: { code?: string; message?: string } | null;
  automation?: CrawlAutomation; worker?: CrawlWorker; capabilities?: CrawlCapabilities;
  instruction_security?: CrawlInstructionSecurity; adaptive_origin_health?: Record<string, CrawlOriginHealth>;
  duplicate_evidence?: CrawlDuplicateEvidence; checkpoint_recovery?: CrawlCheckpointRecovery;
  acquisition_economics?: CrawlAcquisitionEconomics;
  acquisition_readiness?: CrawlAcquisitionReadiness;
  navigation_backlog?: NavigationBacklogSummary;
  publisher_intent?: { schema: 'skeleton.dragon.publisher-intent.v1'; method: PublisherIntakeMethod;
    intent_digest: string; operator_acknowledged: true; publisher_verified: false;
    license_verified: false; network_authority_expanded: false };
  publisher_capture_review?: {
    schema: 'skeleton.dragon.publisher-capture-review.v1';
    state: 'consent_expired' | 'restriction_observed' | 'representation_review_required' |
      'declared_type_match_only' | 'discovery_metadata_only' | 'no_reviewable_capture';
    settled_requests: number; retained_captures: number; declared_type_matches: number;
    other_declared_types: number; inferred_or_unknown_types: number;
    discovery_observations: number; denial_statuses: number; rejected_observations: number;
    protocol_verified: false; publisher_verified: false; license_verified: false;
    source_use_authorized: false; network_executed: false;
  };
  publisher_archive_preflight?: {
    schema: 'skeleton.dragon.publisher-archive-preflight.v1';
    state: 'checkpoint_unwitnessed' | 'terminal_capture_required' | 'restriction_review_required' |
      'no_retained_capture' | 'representation_review_required' | 'archive_policy_held' |
      'explicit_archive_grant_required';
    snapshot_digest: string; retained_captures: number; archive_policy_candidates: number;
    terminal_capture: boolean; checkpoint_witnessed: boolean;
    archive_grant_issued: false; raw_dataset_verified: false;
    source_use_authorized: false; network_executed: false;
  };
  companion?: DragonCompanion;
  curriculum_trace?: DragonCurriculumTrace;
  archive_grant?: DragonArchiveGrant; treasury_watch?: DragonTreasuryWatch|null; watch_managed?: boolean;
  treasury_vault?:DragonVaultState;
  queue: { url: string; depth: number; attempts: number; ready_at: number }[];
};
export type SourceUsePolicy = { version: number; enabled: boolean; max_age_seconds: number; changed_at: string | null };
export type SourceFreshness = {
  usable: boolean; state: 'current' | 'withdrawn' | 'stale' | 'consent_expired' | 'session_revoked' | 'capture_time_invalid' | 'instruction_quarantined';
  capture_age_seconds: number; valid_until: string; remote_freshness_verified: false;
};
export type CapturedSource = { source_id: string; url: string; canonical_url?: string; title: string; text?: string; content_digest: string; fetched_at: string; review_state: string; provenance: Record<string, unknown>; text_truncated?: boolean; use_policy?: SourceUsePolicy; freshness?: SourceFreshness };
export type CrawlCreate = { idempotency_key: string; seeds: string[]; title?: string; topics: string[]; max_requests: number; max_documents: number; max_bytes: number; max_depth: number; discover_sitemaps?: boolean; frontier_strategy?: 'fifo' | 'balanced' | 'coverage' | 'companion' | 'companion_curiosity' | 'companion_scholar' | 'companion_guardian'; consent: true; rights_acknowledged: true };
export type CrawlCommand = { idempotency_key: string; expected_version: number };
export type SourceExport = { filename: string; media_type: string; content: string; content_digest: string; session_id: string; source_id: string };
const ROOT = '/api/dragon-academy/crawler';
const ID = /^[A-Za-z0-9_-]{1,128}$/;
const HASH = /^[a-f0-9]{64}$/;
const OPERATION_STAGE_NAMES = [
  'exact_canonical_event_timeline',
  'per_origin_robots_and_cooldown_safety',
  'physical_worker_restart_and_cas_witness',
  'measured_resource_capacity_envelope',
  'opaque_bounded_dispatch_preflight',
  'review_only_operator_recovery_runbook',
] as const;
const FORENSIC_STAGE_NAMES = [
  'exact_selected_source_custody',
  'source_text_security_inspection',
  'anchored_passage_geometry',
  'possible_source_reuse',
  'objective_failure_counterfactual',
  'source_boilerplate_screening',
  'bounded_capture_age_analysis',
  'cross_source_sentence_echoes',
  'active_content_render_risk',
  'privacy_and_secret_exposure',
  'objective_host_concentration',
  'possible_polarity_collisions',
  'canonical_capture_provenance_posture',
  'operator_objective_grounding',
  'selected_reference_concentration',
  'mandate_consent_horizon',
  'reverse_source_objective_usage',
  'policy_bound_research_deficit_matrix',
  'untrusted_context_resource_budget',
  'captured_extraction_quality_diagnostics',
  'operator_query_rank_support_audit',
  'captured_origin_redirect_hygiene',
  'objective_selection_fairness_metrics',
  'conservative_risky_source_ablation',
  'script_coverage_lexical_limitations',
  'review_only_forensic_queue',
] as const;

const STATUSES = new Set(['queued', 'ready', 'running', 'paused', 'completed', 'cancelled', 'budget_exhausted', 'failed', 'interrupted']);
export function crawlRequestKey(action: string): string { return 'crawler:' + action + ':' + (globalThis.crypto?.randomUUID?.() || Date.now().toString(36) + '-' + Math.random().toString(36).slice(2)); }
function invalid(message: string): never { throw new ChatClientError(message, { kind: 'protocol', retryable: false }); }
function identifier(value: string): string { if (!ID.test(value)) invalid('The crawler identity is invalid.'); return encodeURIComponent(value); }
function integer(value: unknown, maximum = Number.MAX_SAFE_INTEGER): boolean { return Number.isSafeInteger(value) && (value as number) >= 0 && (value as number) <= maximum; }
async function read<T>(operation: Promise<ApiResult<T>>, token: string, message: string): Promise<T> {
  const result = await operation;
  if (token !== getAuthToken()) throw new ChatClientError('Your account changed. Reopen web capture.', { kind: 'authorization', retryable: false });
  if (!result.ok || !result.data) throw chatApiError(result, message);
  return result.data;
}
function options(signal?: AbortSignal) { return { signal, headers: authHeaders(), timeoutMs: 65000, retries: 0 }; }
const INSTRUCTION_CODES = new Set(['authority_override', 'role_impersonation', 'secret_request',
  'tool_execution', 'agent_directive', 'policy_evasion', 'instruction_artifact', 'instruction_file', 'inspection_limit']);
function validInstructionSecurity(value: CrawlInstructionSecurity, requests: number): boolean {
  if (!value || !integer(value.count, Math.min(128, requests)) ||
      !Array.isArray(value.records) || value.records.length !== value.count ||
      value.payload_retained !== false || value.execution_authorized !== false ||
      !value.categories || typeof value.categories !== 'object' || Array.isArray(value.categories)) return false;
  const counts: Record<string, number> = {};
  let previous = 0;
  for (const record of value.records) {
    if (!record || typeof record !== 'object' || !integer(record.sequence, 10000) || record.sequence <= previous ||
        typeof record.url_digest !== 'string' || !HASH.test(record.url_digest) ||
        !['response', 'extracted', 'robots_comment'].includes(record.stage) ||
        !Array.isArray(record.categories) || !record.categories.length || record.categories.length > INSTRUCTION_CODES.size ||
        new Set(record.categories).size !== record.categories.length ||
        record.categories.some(code => !INSTRUCTION_CODES.has(code)) ||
        !integer(record.match_count_lower_bound, 16) || !integer(record.inspected_bytes, 2097152) ||
        record.inspection_limited !== record.categories.includes('inspection_limit') ||
        record.payload_retained !== false || record.execution_authorized !== false ||
        (record.input_digest !== null && (typeof record.input_digest !== 'string' || !HASH.test(record.input_digest))) ||
        !record.match_fingerprints || typeof record.match_fingerprints !== 'object' || Array.isArray(record.match_fingerprints) ||
        Object.entries(record.match_fingerprints).some(([key, digest]) =>
          !record.categories.includes(key) || typeof digest !== 'string' || !HASH.test(digest)) ||
        (record.input_digest === null && Object.keys(record.match_fingerprints).length > 0)) return false;
    previous = record.sequence;
    for (const code of record.categories) counts[code] = (counts[code] || 0) + 1;
  }
  return Object.keys(counts).length === Object.keys(value.categories).length &&
    Object.entries(counts).every(([code, count]) => value.categories[code] === count);
}
function validOriginHealth(value: Record<string, CrawlOriginHealth>): boolean {
  if (!value || typeof value !== 'object' || Array.isArray(value) || Object.keys(value).length > 16) return false;
  return Object.entries(value).every(([host, health]) => /^[a-z0-9.-]{1,253}$/.test(host) &&
    health && typeof health === 'object' &&
    [health.successes, health.failures, health.rejections, health.failure_streak, health.evidence_count].every(n => integer(n, 16)) &&
    health.successes + health.failures + health.rejections === health.evidence_count &&
    health.failure_streak <= health.failures &&
    [health.posterior_success, health.uncertainty].every(n => Number.isFinite(n) && n >= 0 && n <= 1));
}
const QUEST_SPEC: ReadonlyArray<readonly [string, DragonQuest['branch'], number, string | null]> = [
  ['first_scale','discovery',1,null], ['novel_trail','discovery',3,'first_scale'],
  ['cartographer','discovery',8,'novel_trail'], ['first_insight','scholar',1,null],
  ['mosaic','scholar',70,'first_insight'], ['many_perspectives','scholar',2,'mosaic'],
  ['new_habitat','ecology',2,null], ['habitat_keeper','ecology',3,'new_habitat'],
  ['far_roamer','ecology',3,'new_habitat'], ['measured_expedition','stewardship',4,null],
  ['careful_researcher','stewardship',60,'measured_expedition'], ['balanced_mastery','stewardship',4,'careful_researcher'],
];
function validQuestbook(book: DragonQuestbook, value: CrawlSession): boolean {
  if (!book || book.schema !== 'skeleton.dragon.questbook.v1' || book.total !== QUEST_SPEC.length
    || !integer(book.completed, book.total) || !integer(book.contribution_count, value.source_count)
    || !integer(book.credited_sources, book.contribution_count) || !HASH.test(book.revision_digest)
    || book.derived_not_persisted !== true || book.training_permission !== false || book.network_authority_expanded !== false
    || (book.evidence_access !== undefined && book.evidence_access !== 'current_source_policy_filtered')
    || !Array.isArray(book.quests) || book.quests.length !== book.total) return false;
  const achieved = new Set<string>();
  for (let i = 0; i < QUEST_SPEC.length; i++) {
    const q = book.quests[i], [code, branch, target, prerequisite] = QUEST_SPEC[i];
    if (!q || q.code !== code || q.branch !== branch || q.target !== target || q.prerequisite !== prerequisite
      || !integer(q.progress, target) || typeof q.applicable !== 'boolean'
      || !['completed', 'active', 'locked'].includes(q.state) || !Array.isArray(q.source_ids)
      || q.source_ids.length > 8 || new Set(q.source_ids).size !== q.source_ids.length
      || q.source_ids.some(id => typeof id !== 'string' || !HASH.test(id))
      || q.evidence_redacted !== undefined && typeof q.evidence_redacted !== 'boolean') return false;
    const ready = q.applicable && (prerequisite === null || achieved.has(prerequisite));
    if ((!ready && q.state !== 'locked') || (ready && q.state === 'locked')) return false;
    if (q.state === 'completed') {
      if (q.progress !== target || (!q.source_ids.length && q.evidence_redacted !== true)
        || !integer(q.last_evidence_sequence, 10000) || q.last_evidence_sequence === 0) return false;
      achieved.add(q.code);
    } else if (q.source_ids.length || q.last_evidence_sequence !== null || q.evidence_redacted === true) return false;
  }
  return achieved.size === book.completed;
}
function validCurriculumTrace(trace: DragonCurriculumTrace, value: CrawlSession): boolean {
  if (!trace || !integer(trace.decisions, value.counters.requests) || trace.training_permission !== false
    || trace.network_authority_expanded !== false || !trace.quests || !Array.isArray(trace.recent)
    || trace.recent.length !== Math.min(trace.decisions, 8)) return false;
  const quests = ['explore','synthesize','diversify','conserve','recover','rest'] as const;
  if (Object.keys(trace.quests).length !== quests.length) return false;
  let total = 0;
  for (const key of quests) {
    const q = trace.quests[key];
    if (!q || !integer(q.content_attempts, trace.decisions) || !integer(q.policy_attempts, trace.decisions)
      || !integer(q.captures, q.content_attempts) || !integer(q.uncertain_attempts, q.content_attempts + q.policy_attempts)) return false;
    total += q.content_attempts + q.policy_attempts;
  }
  if (total !== trace.decisions) return false;
  let prev = 0;
  for (const d of trace.recent) {
    if (!d || !['companion','companion_curiosity','companion_scholar','companion_guardian'].includes(d.strategy)
      || d.strategy !== value.limits.frontier_strategy || !quests.includes(d.quest) || !HASH.test(d.candidate_digest)
      || !integer(d.eligible, 512) || d.eligible === 0 || !integer(d.base_milli, 1000) || !integer(d.priority_milli, 1000)
      || Math.abs(d.base_milli - d.priority_milli) > 121
      || ['rest','recover','conserve'].includes(d.quest) && d.base_milli !== d.priority_milli
      || !['policy','content'].includes(d.phase) || d.network_authority_expanded !== false
      || !integer(d.request, value.counters.requests) || d.request <= prev
      || !integer(d.event_sequence, 10000) || d.event_sequence === 0
      || typeof d.outcome !== 'string' || d.outcome.length > 64
      || d.source_id !== null && (d.outcome !== 'captured' || !HASH.test(d.source_id))) return false;
    prev = d.request;
  }
  return true;
}
const NAVIGATION_KINDS = new Set(['seed', 'robots_sitemap', 'sitemap_urlset', 'sitemap_index', 'structured', 'document_link', 'http_link']);
function navigationUrl(value: unknown): value is string {
  if (typeof value !== 'string' || value.length > 4096) return false;
  try { const parsed = new URL(value); return ['https:', 'http:'].includes(parsed.protocol)
    && !parsed.username && !parsed.password && !parsed.hash; } catch { return false; }
}
function validNavigationSummary(row: NavigationBacklogSummary): boolean {
  if (!row || row.authority !== 'advisory_only' || row.inventory_complete !== false
    || row.max_records !== 4096 || row.max_bytes !== 1024 * 1024
    || !integer(row.unique_targets, 4096) || !integer(row.pending, row.unique_targets)
    || !integer(row.active, 512) || !integer(row.visited, 1024)
    || !integer(row.depth_held_targets, row.unique_targets) || !row.counts) return false;
  for (const name of ['observations', 'outside_policy', 'capacity_omissions', 'circuit_held',
    'depth_held', 'promoted', 'retired', 'parser_capped']) {
    if (!integer(row.counts[name], 1000000000)) return false;
  }
  const d = row.last_discourse;
  if (d === null) return true;
  if (!d || d.authority !== 'advisory_only' || !navigationUrl(d.url) || !HASH.test(d.digest)
    || !['rest', 'recover', 'conserve', 'explore', 'synthesize', 'diversify'].includes(d.quest)) return false;
  return [d.objective_coverage, d.uncovered_terms, d.evidence_novelty, d.jeeves_proposal,
    d.dragon_counterproposal, d.disagreement, d.final_priority].every(
      x => typeof x === 'number' && Number.isFinite(x) && x >= 0 && x <= 1);
}
function session(value: CrawlSession, expectedId?: string): CrawlSession {
  if (!value || !ID.test(value.session_id) || expectedId && value.session_id !== expectedId || !STATUSES.has(value.status)
    || !integer(value.version) || value.version < 1 || typeof value.title !== 'string' || value.title.length > 160
    || !Array.isArray(value.seeds) || value.seeds.length > 16 || value.seeds.some(url => typeof url !== 'string' || url.length > 4096)
    || !value.limits || !value.counters || !integer(value.frontier_count) || !integer(value.source_count, 64)
    || typeof value.consent_current !== 'boolean' || !Number.isFinite(Date.parse(value.consent_expires_at))
    || !Array.isArray(value.queue) || value.queue.length > 32 || JSON.stringify(value).length > 512 * 1024) invalid('The crawler returned an invalid session projection.');
  for (const count of Object.values(value.counters)) if (!integer(count, 33554432)) invalid('The crawler counters are invalid.');
  for (const field of ['requests', 'bytes', 'documents', 'failures'] as const) if (!integer(value.counters[field], 33554432)) invalid('The crawler counters are incomplete.');
  if (value.navigation_backlog !== undefined && !validNavigationSummary(value.navigation_backlog)) invalid('Invalid checkpointed navigation inventory.');
  if (value.instruction_security !== undefined && !validInstructionSecurity(value.instruction_security, value.counters.requests)) invalid('The crawler instruction incident custody is invalid.');
  if (value.adaptive_origin_health !== undefined && !validOriginHealth(value.adaptive_origin_health)) invalid('The crawler origin health projection is invalid.');
  if (value.publisher_intent !== undefined) {
    const intent = value.publisher_intent;
    if (!intent || intent.schema !== 'skeleton.dragon.publisher-intent.v1'
      || !PUBLISHER_INTAKE_METHODS.includes(intent.method)
      || !HASH.test(intent.intent_digest) || intent.operator_acknowledged !== true
      || intent.publisher_verified !== false || intent.license_verified !== false
      || intent.network_authority_expanded !== false || value.seeds.length !== 1
      || value.limits.max_requests !== 8 || value.limits.max_documents !== 1
      || value.limits.max_depth !== 0 || value.limits.max_total_bytes !== 2097152)
      invalid('Invalid verified publisher intent projection.');
  }
  if (value.publisher_capture_review !== undefined) {
    const r = value.publisher_capture_review;
    if (!r || !value.publisher_intent || r.schema !== 'skeleton.dragon.publisher-capture-review.v1'
      || !['consent_expired','restriction_observed','representation_review_required','declared_type_match_only',
        'discovery_metadata_only','no_reviewable_capture'].includes(r.state)
      || r.protocol_verified !== false || r.publisher_verified !== false || r.license_verified !== false
      || r.source_use_authorized !== false || r.network_executed !== false
      || !integer(r.settled_requests, value.counters.requests) || r.retained_captures !== value.source_count
      || !integer(r.declared_type_matches, r.retained_captures)
      || !integer(r.other_declared_types, r.retained_captures)
      || !integer(r.inferred_or_unknown_types, r.retained_captures)
      || r.declared_type_matches + r.other_declared_types + r.inferred_or_unknown_types !== r.retained_captures
      || !integer(r.discovery_observations, r.settled_requests) || !integer(r.denial_statuses, r.settled_requests)
      || !integer(r.rejected_observations, r.settled_requests)) invalid('Invalid publisher capture review projection.');
  }
  if (value.publisher_archive_preflight !== undefined) {
    const p = value.publisher_archive_preflight;
    if (!p || !value.publisher_intent || !value.publisher_capture_review
      || p.schema !== 'skeleton.dragon.publisher-archive-preflight.v1'
      || !['checkpoint_unwitnessed','terminal_capture_required','restriction_review_required',
        'no_retained_capture','representation_review_required','archive_policy_held',
        'explicit_archive_grant_required'].includes(p.state)
      || !HASH.test(p.snapshot_digest) || p.retained_captures !== value.source_count
      || !integer(p.archive_policy_candidates, p.retained_captures)
      || typeof p.terminal_capture !== 'boolean' || typeof p.checkpoint_witnessed !== 'boolean'
      || p.archive_grant_issued !== false || p.raw_dataset_verified !== false
      || p.source_use_authorized !== false || p.network_executed !== false
      || (p.state === 'explicit_archive_grant_required' &&
        (!p.checkpoint_witnessed || !p.terminal_capture || !p.retained_captures
          || p.archive_policy_candidates !== p.retained_captures)))
      invalid('Invalid publisher archive preflight projection.');
  }
  if (value.acquisition_readiness !== undefined) {
    const r = value.acquisition_readiness;
    if (!r || r.schema !== 'skeleton.dragon.acquisition-readiness.v1'
      || r.network_authority_expanded !== false || r.reason_inferred !== false
      || r.independent_intake_requires_new_authorization !== true
      || !Array.isArray(r.hosts) || r.hosts.length > 16
      || !integer(r.settled_requests, value.counters.requests)
      || r.queued !== value.frontier_count) invalid('Invalid acquisition readiness receipt.');
    let settled = 0, queued = 0;
    const hosts = new Set<string>();
    for (const h of r.hosts) {
      if (!h || typeof h.host !== 'string' || !/^[a-z0-9][a-z0-9.-]{0,252}$/.test(h.host) || hosts.has(h.host)
        || !['consent_expired','held_for_grant','cooldown','no_host_hold'].includes(h.state)
        || typeof h.host_ready_at !== 'number' || !Number.isFinite(h.host_ready_at) || h.host_ready_at < 0 || h.host_ready_at > 1e12
        || !integer(h.settled, r.settled_requests) || !integer(h.queued, r.queued)
        || !integer(h.denial_statuses, h.settled) || !integer(h.throttle_statuses, h.settled)
        || !integer(h.rejected_success_statuses, h.settled)
        || h.denial_statuses + h.throttle_statuses + h.rejected_success_statuses > h.settled
        || (h.state === 'consent_expired') === value.consent_current) invalid('Invalid host readiness receipt.');
      hosts.add(h.host); settled += h.settled; queued += h.queued;
    }
    if (settled !== r.settled_requests || queued !== r.queued) invalid('Acquisition readiness accounting differs.');
  }
  if (value.acquisition_economics !== undefined) {
    const e = value.acquisition_economics;
    const finite = (n: unknown, max: number) => typeof n === 'number' && Number.isFinite(n) && n >= 0 && n <= max;
    if (!e || e.network_authority_expanded !== false || !integer(e.settled_requests, value.counters.requests)
      || !integer(e.charged_bytes, 33554432) || !integer(e.uncertain_bytes, 33554432)
      || e.charged_bytes !== value.counters.bytes || e.charged_bytes + e.uncertain_bytes > 33554432
      || !e.hosts || typeof e.hosts !== 'object' || Array.isArray(e.hosts) || Object.keys(e.hosts).length > 16) invalid('Invalid acquisition economics custody.');
    let counted = 0;
    for (const [host, h] of Object.entries(e.hosts)) {
      if (!h || h.host !== host || !/^[a-z0-9][a-z0-9.-]{0,252}$/.test(host)
        || !integer(h.observations, e.settled_requests) || !integer(h.successes, Math.min(16, h.observations))
        || !integer(h.failures, Math.min(16, h.observations)) || !integer(h.novelty_observations, Math.min(16, h.observations))
        || !finite(h.mean_latency_seconds, 60) || !finite(h.tail_latency_seconds, 60)
        || !finite(h.mean_cost_bytes, 2097152) || !finite(h.reliability, 1) || !finite(h.novelty_probability, 1)
        || !finite(h.uncertainty, 1) || !finite(h.conservative_delay, 120)) invalid('Invalid host acquisition measurements.');
      counted += h.observations;
    }
    if (counted !== e.settled_requests) invalid('Acquisition economics request accounting is incomplete.');
  }
  if (value.archive_grant !== undefined && !validArchiveGrant(value.archive_grant, value.source_count)) invalid('Invalid historical grant projection.');
  if (value.treasury_watch!==undefined&&value.treasury_watch!==null&&!validWatch(value.treasury_watch)||value.watch_managed!==undefined&&typeof value.watch_managed!=='boolean') invalid('Invalid treasury watch projection.');
  if (value.treasury_vault!==undefined&&(!validVaultState(value.treasury_vault)
      ||value.consent_current||!['completed','budget_exhausted'].includes(value.status))) invalid('Invalid retired custody projection.');
  if (value.companion !== undefined) {
    const p = value.companion;
    const unit = (n: unknown) => typeof n === 'number' && Number.isFinite(n) && n >= 0 && n <= 1;
    const forms = ['hatchling', 'scout', 'scholar', 'pathfinder', 'archivist'];
    const stages = [120, 300, 550, 800];
    const skills = ['discovery', 'understanding', 'diversity', 'discipline', 'resilience'] as const;
    const habitats = ['web', 'document', 'structured', 'media', 'text', 'artifact'];
    if (!p || p.schema !== 'skeleton.dragon.companion.v1' || !integer(p.stage, 4) || forms[p.stage] !== p.form
      || !integer(p.growth, 1000) || p.stage !== stages.filter(t => p.growth >= t).length
      || !unit(p.energy) || !unit(p.learning_progress) || !unit(p.novelty_yield)
      || !p.skills || Object.keys(p.skills).length !== skills.length || !skills.every(k => unit(p.skills[k]))
      || !['explore', 'synthesize', 'diversify', 'conserve', 'recover', 'rest'].includes(p.quest)
      || !['resting', 'recovering', 'studying', 'roaming'].includes(p.posture)
      || !['balanced', 'curious', 'scholarly', 'guardian'].includes(p.style)
      || !integer(p.captured_sources, value.source_count) || !integer(p.novel_origins, Math.min(16, p.captured_sources))
      || !integer(p.term_count, 32) || !integer(p.covered_terms, p.term_count) || !integer(p.multi_origin_terms, p.covered_terms)
      || !integer(p.recovery_observations, value.counters.requests) || !integer(p.quarantines, 128)
      || !integer(p.uncertain_bytes, value.counters.reserved_bytes ?? 33554432)
      || !p.habitats || typeof p.habitats !== 'object' || Array.isArray(p.habitats)
      || Object.entries(p.habitats).some(([k, n]) => !habitats.includes(k) || !integer(n, p.captured_sources) || n < 1)
      || Object.values(p.habitats).reduce((a, n) => a + n, 0) > p.captured_sources
      || p.unreviewed_evidence_only !== true || p.network_authority_expanded !== false
      || p.training_permission !== false || p.inactivity_penalty !== false) invalid('Invalid evidence-fed companion projection.');
    if (p.questbook !== undefined && !validQuestbook(p.questbook, value)) invalid('Invalid source-bound companion questbook.');
  }
  if (value.curriculum_trace !== undefined && !validCurriculumTrace(value.curriculum_trace, value)) invalid('Invalid companion decision trace.');
  if (value.duplicate_evidence !== undefined) {
    const d = value.duplicate_evidence;
    if (!d || !integer(d.count, Math.min(128, value.counters.requests)) || !integer(d.represented_sources, Math.min(d.count, value.source_count))
      || !integer(d.observed_origins, d.count) || d.independent_evidence !== false || d.raw_bytes_retained !== false) invalid('Invalid exact-duplicate evidence custody.');
  }
  if (value.checkpoint_recovery !== undefined) {
    const c = value.checkpoint_recovery;
    if (!c || typeof c.replica_present !== 'boolean' || c.replica_verified !== false || c.ancestor_rollback !== false
      || !['exact_current_revision', 'replica_capacity', 'write_envelope_capacity', 'legacy_unwitnessed'].includes(c.reason)
      || (c.last_repair_at === null) !== (c.last_repair_sequence === null)
      || c.last_repair_at !== null && (typeof c.last_repair_at !== 'string' || !Number.isFinite(Date.parse(c.last_repair_at)))
      || c.last_repair_sequence !== null && !integer(c.last_repair_sequence, 10000)) invalid('Invalid exact-checkpoint recovery projection.');
  }
  for (const row of value.queue) if (!row || typeof row.url !== 'string' || row.url.length > 4096 || !integer(row.depth, 3) || !integer(row.attempts, 128) || typeof row.ready_at !== 'number' || !Number.isFinite(row.ready_at)) invalid('The crawler queue is invalid.');
  if (value.automation) {
    const a = value.automation;
    if (typeof a.enabled !== 'boolean' || !['authorized', 'running', 'waiting', 'stopped', 'disabled', 'blocked', 'not_authorized'].includes(a.state)
      || !integer(a.epoch) || !integer(a.slices_started, 64) || !integer(a.max_slices, 64) || a.slices_started > a.max_slices
      || a.enabled && a.max_slices < 1 || a.expires_at !== null && !Number.isFinite(Date.parse(a.expires_at))
      || a.next_run_at !== null && !Number.isFinite(Date.parse(a.next_run_at))
      || a.stop_reason !== null && (typeof a.stop_reason !== 'string' || a.stop_reason.length > 4096)) invalid('The crawler automation authorization is invalid.');
  }
  if (value.worker && (['active', 'quiescent', 'local'].some(key => typeof value.worker![key as keyof CrawlWorker] !== 'boolean')
    || value.worker.lease_until !== null && !Number.isFinite(Date.parse(value.worker.lease_until))
    || value.worker.confirmation !== undefined && (typeof value.worker.confirmation !== 'string' || value.worker.confirmation.length > 256)
    || value.worker.recovery_eligible !== undefined && typeof value.worker.recovery_eligible !== 'boolean')) invalid('The crawler worker projection is invalid.');
  if (value.capabilities && ['can_run', 'can_pause', 'can_resume', 'can_cancel', 'can_erase', 'can_automate'].some(key => typeof value.capabilities![key as keyof CrawlCapabilities] !== 'boolean')) invalid('The crawler command capabilities are invalid.');
  return value;
}
function source(value: CapturedSource, id?: string): CapturedSource {
  if (!value || !ID.test(value.source_id) || id && value.source_id !== id || typeof value.url !== 'string' || value.url.length > 4096 || typeof value.title !== 'string'
    || !HASH.test(value.content_digest) || typeof value.review_state !== 'string' || !value.provenance || typeof value.provenance !== 'object'
    || value.text !== undefined && (typeof value.text !== 'string' || new TextEncoder().encode(value.text).byteLength > 2 * 1024 * 1024)) invalid('The captured source projection is invalid.');
  if ((value.use_policy === undefined) !== (value.freshness === undefined)) invalid('The source-use projection is incomplete.');
  if (value.use_policy && value.freshness) {
    const policy = value.use_policy, freshness = value.freshness;
    if (!integer(policy.version, 2147483647) || typeof policy.enabled !== 'boolean' || !integer(policy.max_age_seconds, 86400) || policy.max_age_seconds < 60
      || policy.changed_at !== null && (typeof policy.changed_at !== 'string' || !Number.isFinite(Date.parse(policy.changed_at)))
      || policy.version === 0 && policy.changed_at !== null || policy.version > 0 && policy.changed_at === null
      || typeof freshness.usable !== 'boolean' || !['current', 'withdrawn', 'stale', 'consent_expired', 'session_revoked', 'capture_time_invalid', 'instruction_quarantined'].includes(freshness.state)
      || freshness.usable !== (freshness.state === 'current') || freshness.usable && !policy.enabled
      || !integer(freshness.capture_age_seconds) || typeof freshness.valid_until !== 'string' || !Number.isFinite(Date.parse(freshness.valid_until))
      || freshness.remote_freshness_verified !== false) invalid('The source-use or capture-age projection is invalid.');
  }
  return value;
}
function validArchiveGrant(p: DragonArchiveGrant, count: number): boolean {
  return !!p && typeof p.active === 'boolean' && integer(p.granted_sources,count)
    && integer(p.usable_sources,p.granted_sources) && p.active === (p.usable_sources>0)
    && (p.expires_at===null || Number.isFinite(p.expires_at) && p.expires_at>0)
    && (!p.active || p.expires_at!==null) && p.history_only===true && p.network_authority_expanded===false;
}
function validEvolution(v: DragonEvolution): boolean {
  const thresholds=[0,120,300,550,800,1150,1500];
  const forms=['hatchling','scout','scholar','pathfinder','archivist','hoarder'];
  if (!v || !integer(v.expedition_growth,1000) || !integer(v.treasury_growth,500)
    || v.total_evolution!==v.expedition_growth+v.treasury_growth || typeof v.hoarder_qualified!=='boolean') return false;
  const effective=v.expedition_growth>=800&&v.hoarder_qualified?v.total_evolution:v.expedition_growth;
  const stage=thresholds.slice(1,-1).filter(t=>effective>=t).length;
  const fraction=Math.min(1,Math.max(0,(effective-thresholds[stage])/(thresholds[stage+1]-thresholds[stage])));
  return v.effective_evolution===effective && v.stage===stage && v.form===forms[stage]
    && v.level===Math.min(stage*10+10,stage*10+1+Math.floor(fraction*10))
    && Number.isFinite(v.stage_progress) && Math.abs(v.stage_progress-fraction)<=.000001
    && v.next_threshold===(stage===5?null:thresholds[stage+1]);
}
function validDelta(d: TreasuryDelta): boolean {
  return !!d && ['initial','minor_update','substantive_update','major_rewrite','changed_unclassified','rollback'].includes(d.kind)
    && (d.similarity===null || Number.isFinite(d.similarity) && d.similarity>=0 && d.similarity<=1)
    && (d.added_terms===null || integer(d.added_terms,2048)) && (d.removed_terms===null || integer(d.removed_terms,2048))
    && (d.changed_sections===null || integer(d.changed_sections,64))
    && (d.numeric_change===null || typeof d.numeric_change==='boolean');
}
function validRevision(v: TreasuryRevision): boolean {
  return !!v && HASH.test(v.revision_id) && HASH.test(v.family_id)
    && (v.previous_revision_id===null||HASH.test(v.previous_revision_id))
    && Number.isFinite(v.first_seen) && v.first_seen>=0 && Number.isFinite(v.last_seen) && v.last_seen>=v.first_seen
    && integer(v.reobservations,2048) && typeof v.indexed==='boolean' && v.metadata_only===!v.indexed
    && typeof v.archive_only==='boolean' && typeof v.latest_observed==='boolean' && ['historic','current'].includes(v.plane)
    && (v.plane!=='current'||v.latest_observed&&!v.archive_only)
    && (v.indexed ? typeof v.session_id==='string'&&ID.test(v.session_id)&&typeof v.source_id==='string'&&HASH.test(v.source_id)&&typeof v.projection_digest==='string'&&HASH.test(v.projection_digest)
                  : v.session_id===null&&v.source_id===null&&v.projection_digest===null)
    && (v.indexed ? typeof v.indexed_capture_at==='number'&&Number.isFinite(v.indexed_capture_at)&&v.indexed_capture_at>=v.first_seen&&v.indexed_capture_at<=v.last_seen : v.indexed_capture_at===null)
    && (!v.indexed||v.plane!=='current'||v.indexed_capture_at===v.last_seen)
    && validDelta(v.delta) && (v.score===undefined||Number.isFinite(v.score)&&v.score>=0);
}
function validFamily(f: TreasuryFamily): boolean {
  if(!f||!HASH.test(f.family_id)||!HASH.test(f.current_revision)||!integer(f.revision_count,2048)||f.revision_count===0
    ||!Number.isFinite(f.first_seen)||!Number.isFinite(f.last_seen)||f.last_seen<f.first_seen
    ||typeof f.current_indexed!=='boolean'||typeof f.simultaneous_conflict!=='boolean'||typeof f.alias_conflict!=='boolean'||((f.simultaneous_conflict||f.alias_conflict)&&f.current_indexed))return false;
  if(f.refresh_url!==null){try{const u=new URL(f.refresh_url);if(f.refresh_url.length>4096||!['http:','https:'].includes(u.protocol)||u.username||u.password)return false;}catch{return false;}}
  const r=f.revisit;
  return !!r&&Number.isFinite(r.due_at)&&r.due_at>=f.last_seen&&Number.isFinite(r.interval_seconds)&&r.interval_seconds>=3600
    &&Number.isFinite(r.change_probability_estimate)&&r.change_probability_estimate>=0&&r.change_probability_estimate<=1
    &&integer(r.observed_changes,511)&&integer(r.qualified_intervals,511)&&integer(r.ambiguous_intervals,511)
    &&r.observed_changes<=r.qualified_intervals&&r.model==='interval_censored_grid_v1'
    &&Number.isFinite(r.expected_changes_per_day)&&r.expected_changes_per_day>=0&&r.expected_changes_per_day<=64
    &&Number.isFinite(r.utility_per_cost)&&r.utility_per_cost>=0&&r.utility_per_cost<=1
    &&Number.isFinite(r.target_stale_risk)&&r.target_stale_risk>=.2&&r.target_stale_risk<=.45
    &&typeof r.ready_for_review==='boolean'&&r.fresh_consent_required===true&&r.network_executed===false;
}
export type TreasuryPassage = {
  schema: 'skeleton.dragon.treasury-passage.v1'; session_id: string; source_id: string; session_version: number;
  snapshot_digest: string; preserved_text_hash: string; captured_at: number; valid_until: number; as_of_unix: number;
  offset: number; end: number; total_chars: number; text: string; span_sha256: string; next_offset: number | null;
  history_only: boolean; review_state: 'unreviewed'; model_context_permission: false; training_permission: false; network_executed: false;
};
export async function getTreasuryPassage(sessionId: string, sourceId: string, offset=0, signal?: AbortSignal): Promise<TreasuryPassage> {
  if(!HASH.test(sourceId)||!integer(offset,24000)) invalid('Invalid historical passage coordinates.');
  const p=await read(api.get<TreasuryPassage>(ROOT+'/companion/treasury/'+identifier(sessionId)+'/'+sourceId+'/passage?offset='+offset+'&length=1600',options(signal)),getAuthToken(),'Historical passage is unavailable.');
  if(!p||p.schema!=='skeleton.dragon.treasury-passage.v1'||p.session_id!==sessionId||p.source_id!==sourceId
    ||!Number.isSafeInteger(p.session_version)||p.session_version<1||!HASH.test(p.snapshot_digest)||!HASH.test(p.preserved_text_hash)
    ||!Number.isFinite(p.captured_at)||!Number.isFinite(p.as_of_unix)||!Number.isFinite(p.valid_until)||p.valid_until<=p.as_of_unix
    ||p.offset!==offset||!integer(p.total_chars,24000)||!integer(p.end,p.total_chars)||p.end<p.offset||p.end-p.offset>1600
    ||typeof p.text!=='string'||Array.from(p.text).length!==p.end-p.offset||!HASH.test(p.span_sha256)
    ||p.next_offset!==(p.end<p.total_chars?p.end:null)||typeof p.history_only!=='boolean'||p.review_state!=='unreviewed'
    ||p.model_context_permission!==false||p.training_permission!==false||p.network_executed!==false)invalid('Invalid historical passage custody.');
  return p;
}
function validVaultState(v:DragonVaultState):boolean{
  return !!v&&['pending','vaulted'].includes(v.state)&&Number.isFinite(v.accepted_at)&&v.accepted_at>=0
    &&typeof v.active_slot_released==='boolean'&&(!v.active_slot_released||v.state==='vaulted')
    &&typeof v.snapshot_digest==='string'&&HASH.test(v.snapshot_digest)
    &&v.execution_authorized===false&&v.historical_grant_extended===false;
}
function vaultSelection(ids:string[]):string[]{
  if(!Array.isArray(ids)||ids.length<1||ids.length>32||ids.some(id=>typeof id!=='string'||!ID.test(id))
      ||new Set(ids).size!==ids.length)invalid('Select 1–32 distinct retired expeditions.');
  return [...ids].sort();
}
export type DragonVaultDiscoveryMatch = {session_id:string;version:number;valid_until:number;eligible_sources:number;
  matched_sources:number;distinct_matching_payloads:number;matched_terms:number;best_source_terms:number;scanned_bytes:number};
export type DragonVaultDiscovery = {schema:'skeleton.dragon.vault-discovery.v1';scope_digest:string;as_of_unix:number;
  earliest_expiry:number|null;catalogue_size:number;page_offset:number;scanned_sessions:number;query_terms:number;
  qualified:number;no_grant:number;held:number;eligible_sources:number;scanned_bytes:number;matches:DragonVaultDiscoveryMatch[];
  next_cursor:string|null;page_local_ranking:true;source_text_returned:false;network_executed:false;model_context_permission:false};
export async function discoverDragonVault(query:string,cursor?:string,signal?:AbortSignal):Promise<DragonVaultDiscovery>{
  if(typeof query!=='string'||!query.trim()||query.length>256||cursor!==undefined&&!/^[a-f0-9]{64}:[0-9]{1,4}$/.test(cursor))invalid('Invalid chamber discovery.');
  const p=await read(api.get<DragonVaultDiscovery>(ROOT+'/companion/vault-discovery?query='+encodeURIComponent(query)
    +(cursor?'&cursor='+encodeURIComponent(cursor):''),options(signal)),getAuthToken(),'Chamber discovery unavailable.');
  if(!p||p.schema!=='skeleton.dragon.vault-discovery.v1'||!HASH.test(p.scope_digest)||!Number.isFinite(p.as_of_unix)||p.as_of_unix<0
    ||!integer(p.catalogue_size,1024)||!integer(p.page_offset,p.catalogue_size)||p.page_offset%8!==0
    ||p.page_offset!==(cursor?Number(cursor.split(':')[1]):0)||cursor&&cursor.split(':')[0]!==p.scope_digest
    ||p.scanned_sessions!==Math.min(8,p.catalogue_size-p.page_offset)||!integer(p.query_terms,32)||p.query_terms<1
    ||![p.qualified,p.no_grant,p.held].every(n=>integer(n,p.scanned_sessions))||p.qualified+p.no_grant+p.held!==p.scanned_sessions
    ||!integer(p.eligible_sources,64*p.qualified)||p.eligible_sources<p.qualified||!integer(p.scanned_bytes,24000*p.eligible_sources)
    ||(p.qualified===0)!==(p.earliest_expiry===null)
    ||p.earliest_expiry!==null&&(!Number.isFinite(p.earliest_expiry)||p.earliest_expiry<=p.as_of_unix)
    ||p.next_cursor!==(p.page_offset+p.scanned_sessions<p.catalogue_size?p.scope_digest+':'+(p.page_offset+p.scanned_sessions):null)
    ||!Array.isArray(p.matches)||p.matches.length>p.qualified||new Set(p.matches.map(x=>x?.session_id)).size!==p.matches.length
    ||p.matches.some((x,i)=>!x||typeof x.session_id!=='string'||!ID.test(x.session_id)||!integer(x.version)||x.version<1
       ||!Number.isFinite(x.valid_until)||x.valid_until<=p.as_of_unix||p.earliest_expiry===null||x.valid_until<p.earliest_expiry
       ||!integer(x.eligible_sources,64)||!integer(x.matched_sources,x.eligible_sources)||x.matched_sources<1
       ||!integer(x.distinct_matching_payloads,x.matched_sources)||x.distinct_matching_payloads<1
       ||!integer(x.matched_terms,p.query_terms)||x.matched_terms<1||!integer(x.best_source_terms,x.matched_terms)||x.best_source_terms<1
       ||!integer(x.scanned_bytes,24000*x.eligible_sources)
       ||(i>0&&(()=>{const a=p.matches[i-1];return a.matched_terms<x.matched_terms
          ||a.matched_terms===x.matched_terms&&(a.best_source_terms<x.best_source_terms
           ||a.best_source_terms===x.best_source_terms&&(a.distinct_matching_payloads<x.distinct_matching_payloads
             ||a.distinct_matching_payloads===x.distinct_matching_payloads&&a.session_id>=x.session_id));})()))
    ||p.matches.reduce((n,x)=>n+x.eligible_sources,0)>p.eligible_sources||p.matches.reduce((n,x)=>n+x.scanned_bytes,0)>p.scanned_bytes
    ||p.page_local_ranking!==true||p.source_text_returned!==false||p.network_executed!==false||p.model_context_permission!==false)
    invalid('Invalid chamber discovery receipt.');
  return p;
}
export type DragonVaultHealth = {
  schema:'skeleton.dragon.vault-health.v1';as_of_unix:number;valid_until:number;records:number;
  pending:number;vaulted:number;marker_held:number;uninspected:number;stale:number;
  redundant:number;primary_only:number;repairable_primary:number;held:number;
  care_active:number;care_inactive:number;care_absent:number;care_held:number;remaining_repairs:number;due:number;
  live_verified:false;source_text_returned:false;independent_backup:false;
};
export async function getDragonVaultHealth(signal?:AbortSignal):Promise<DragonVaultHealth>{
  const p=await read(api.get<DragonVaultHealth>(ROOT+'/companion/vault-health',options(signal)),getAuthToken(),'Custody health unavailable.');
  if(!p||p.schema!=='skeleton.dragon.vault-health.v1'||!Number.isFinite(p.as_of_unix)||p.as_of_unix<0
    ||!Number.isFinite(p.valid_until)||p.valid_until<=p.as_of_unix||p.valid_until>p.as_of_unix+60
    ||!integer(p.records,1056)||![p.pending,p.vaulted,p.marker_held].every(x=>integer(x,p.records))
    ||p.pending+p.vaulted+p.marker_held!==p.records
    ||![p.uninspected,p.stale,p.redundant,p.primary_only,p.repairable_primary,p.held,p.due,
         p.care_active,p.care_inactive,p.care_absent,p.care_held].every(x=>integer(x,p.vaulted))
    ||p.uninspected+p.stale+p.redundant+p.primary_only+p.repairable_primary+p.held!==p.vaulted
    ||p.care_active+p.care_inactive+p.care_absent+p.care_held!==p.vaulted
    ||!integer(p.remaining_repairs,3*p.care_active)||p.remaining_repairs<p.care_active
    ||p.live_verified!==false||p.source_text_returned!==false||p.independent_backup!==false)
    invalid('Invalid retained custody health census.');
  return p;
}
export type DragonArchivePointer = {session_id:string;source_id:string;version:number;score:number;valid_until:number;
  citation:string;plane:'historic';review_state:'unreviewed_external_evidence';model_context_authorized:false;stored_prose:0};
export type DragonArchiveIndexSearch = {schema:'skeleton.dragon.archive-index-search.v1';as_of_unix:number;
  candidate_chambers:number;candidate_limit_reached:boolean;rechecked_chambers:number;held_chambers:number;
  results:DragonArchivePointer[];result_limit_reached:boolean;ranking:'indexed_term_overlap_then_exact_coverage';
  complete_corpus:false;stored_prose:0;model_context_authorized:false;network_executed:false};
export async function searchDragonArchiveIndex(query:string,signal?:AbortSignal):Promise<DragonArchiveIndexSearch>{
  if(typeof query!=='string'||!query.trim()||query.length>256)invalid('Invalid archive query.');
  const p=await read(api.get<DragonArchiveIndexSearch>(ROOT+'/companion/archive-index?query='+encodeURIComponent(query),options(signal)),
    getAuthToken(),'Archive index unavailable.');
  if(!p||p.schema!=='skeleton.dragon.archive-index-search.v1'||!Number.isFinite(p.as_of_unix)||p.as_of_unix<0
    ||!integer(p.candidate_chambers,64)||p.rechecked_chambers!==Math.min(16,p.candidate_chambers)
    ||!integer(p.held_chambers,p.rechecked_chambers)||p.candidate_limit_reached!==(p.candidate_chambers>16)
    ||typeof p.result_limit_reached!=='boolean'||!Array.isArray(p.results)||p.results.length>32
    ||new Set(p.results.map(x=>x?.citation)).size!==p.results.length
    ||p.results.some((x,i)=>!x||!ID.test(x.session_id)||!HASH.test(x.source_id)||!integer(x.version)||x.version<1
      ||!integer(x.score,32)||x.score<1||!Number.isFinite(x.valid_until)||x.valid_until<=p.as_of_unix
      ||x.citation!=='dragon-crawl://'+x.session_id+'/'+x.source_id||x.plane!=='historic'
      ||x.review_state!=='unreviewed_external_evidence'||x.model_context_authorized!==false||x.stored_prose!==0
      ||i>0&&p.results[i-1].score<x.score)
    ||p.ranking!=='indexed_term_overlap_then_exact_coverage'||p.complete_corpus!==false||p.stored_prose!==0
    ||p.model_context_authorized!==false||p.network_executed!==false)invalid('Invalid archive index receipt.');
  return p;
}
export type DragonVaultQuota = {
  schema:'skeleton.dragon.vault-quota.v1'; as_of_unix:number; active_reserved:number; vault_reserved:number;
  distinct_reserved:number;dual_reserved:number;active_capacity:32;vault_capacity:1024;
  active:number;vaulted:number;in_transit:number;tombstoned:number;missing:number;integrity_held:number;
  missing_auto_reclaimed:false;source_records_erased:false;read_only:true;
};
export async function getDragonVaultQuota(signal?:AbortSignal):Promise<DragonVaultQuota>{
  const p=await read(api.get<DragonVaultQuota>(ROOT+'/companion/vault-quota',options(signal)),getAuthToken(),'Vault quota health unavailable.');
  if(!p||p.schema!=='skeleton.dragon.vault-quota.v1'||!Number.isFinite(p.as_of_unix)||p.as_of_unix<0
    ||p.active_capacity!==32||p.vault_capacity!==1024||!integer(p.active_reserved,32)||!integer(p.vault_reserved,1024)
    ||!integer(p.dual_reserved,Math.min(p.active_reserved,p.vault_reserved))
    ||!integer(p.distinct_reserved,1056)||p.distinct_reserved!==p.active_reserved+p.vault_reserved-p.dual_reserved
    ||![p.active,p.vaulted,p.in_transit,p.tombstoned,p.missing,p.integrity_held].every(n=>integer(n,p.distinct_reserved))
    ||p.active+p.vaulted+p.in_transit+p.tombstoned+p.missing+p.integrity_held!==p.distinct_reserved
    ||p.active>p.active_reserved||p.vaulted>p.vault_reserved
    ||p.missing_auto_reclaimed!==false||p.source_records_erased!==false||p.read_only!==true)
    invalid('Invalid vault quota health projection.');
  return p;
}
export async function getDragonVault(cursor?:string,signal?:AbortSignal):Promise<DragonVaultCatalog>{
  if(cursor!==undefined&&!ID.test(cursor))invalid('Invalid vault catalogue cursor.');
  const p=await read(api.get<DragonVaultCatalog>(ROOT+'/companion/vault?limit=32'+(cursor?'&cursor='+encodeURIComponent(cursor):''),options(signal)),getAuthToken(),'Vault catalogue unavailable.');
  if(!p||p.schema!=='skeleton.dragon.vault-catalog.v1'||p.capacity!==1024||!Number.isFinite(p.as_of_unix)||p.as_of_unix<0
    ||p.archive_use_verified!==false||p.network_executed!==false||!Array.isArray(p.sessions)||p.sessions.length>32
    ||new Set(p.sessions.map(row=>row?.session_id)).size!==p.sessions.length
    ||p.sessions.some((row,i)=>!row||typeof row.session_id!=='string'||!ID.test(row.session_id)||!integer(row.version)||row.version<1
      ||(i>0&&p.sessions[i-1].session_id<=row.session_id)||(cursor!==undefined&&row.session_id>=cursor)
      ||typeof row.integrity_held!=='boolean'
      ||row.integrity_held&&(row.vault!==null||row.archive_expires_at!==null||row.legacy_runtime!==null||row.last_scrub!=null||row.care!=null)
      ||row.care!=null&&!validVaultCare(row.care,row.version,p.as_of_unix)
      ||row.last_scrub!=null&&(!Number.isFinite(row.last_scrub.checked_at)||row.last_scrub.checked_at<0||row.last_scrub.checked_at>p.as_of_unix
          ||row.last_scrub.live_verified!==false||!['exact','held'].includes(row.last_scrub.primary)
          ||!['exact','held','unavailable'].includes(row.last_scrub.replica)
          ||row.last_scrub.state!==(row.last_scrub.primary==='exact'?(row.last_scrub.replica==='exact'?'redundant':'primary_only'):
                                    row.last_scrub.replica==='exact'?'repairable_primary':'held'))
      ||!row.integrity_held&&(!row.vault||!validVaultState(row.vault)||row.legacy_runtime!==null&&typeof row.legacy_runtime!=='boolean'
        ||row.archive_expires_at!==null&&(!Number.isFinite(row.archive_expires_at)||row.archive_expires_at<=p.as_of_unix)))
    ||p.next_cursor!==null&&(p.sessions.length!==32||p.next_cursor!==p.sessions[p.sessions.length-1].session_id))invalid('Invalid vault catalogue custody.');
  return p;
}
export type DragonVaultRedundancy = {
  schema:'skeleton.dragon.vault-redundancy.v1';session_id:string;version:number;as_of_unix:number;
  state:'redundant'|'primary_only'|'repairable_primary'|'held';primary:'exact'|'held';
  replica:'exact'|'held'|'unavailable';snapshot_digest:string|null;independent_backup:false;
  read_only:true;source_text_returned:false;historical_grant_extended:false;network_executed:false;
};
export async function getDragonVaultRedundancy(id:string,signal?:AbortSignal):Promise<DragonVaultRedundancy>{
  const p=await read(api.get<DragonVaultRedundancy>(ROOT+'/sessions/'+identifier(id)+'/vault-redundancy',options(signal)),
    getAuthToken(),'Historical copy verification unavailable.');
  if(!p||p.schema!=='skeleton.dragon.vault-redundancy.v1'||p.session_id!==id||!integer(p.version)||p.version<1
    ||!Number.isFinite(p.as_of_unix)||p.as_of_unix<0||!['exact','held'].includes(p.primary)
    ||!['exact','held','unavailable'].includes(p.replica)
    ||p.state!==(p.primary==='exact'?(p.replica==='exact'?'redundant':'primary_only'):
                    p.replica==='exact'?'repairable_primary':'held')
    ||p.snapshot_digest!==null&&!HASH.test(p.snapshot_digest)||p.state!=='held'&&p.snapshot_digest===null
    ||p.independent_backup!==false||p.read_only!==true||p.source_text_returned!==false
    ||p.historical_grant_extended!==false||p.network_executed!==false)
    invalid('Invalid historical redundancy receipt.');
  return p;
}
export type DragonVaultReplicaRepair = {
  schema:'skeleton.dragon.vault-replica-repair.v1';session_id:string;version:number;outcome:'repaired'|'already_intact';
  snapshot_digest:string;primary_rewritten:false;witness_rewritten:false;historical_grant_extended:false;
  network_executed:false;independent_backup:false;
};
export async function repairDragonVaultReplica(id:string,body:CrawlCommand&{retention_acknowledged:true},
  signal?:AbortSignal):Promise<DragonVaultReplicaRepair>{
  if(body.retention_acknowledged!==true||!integer(body.expected_version)||body.expected_version<1)
    invalid('Explicit retained duplicate repair acknowledgement required.');
  const p=await read(api.post<DragonVaultReplicaRepair>(ROOT+'/sessions/'+identifier(id)+'/repair-vault-replica',body,options(signal)),
    getAuthToken(),'Retained duplicate repair unconfirmed.');
  if(!p||p.schema!=='skeleton.dragon.vault-replica-repair.v1'||p.session_id!==id||!integer(p.version)||p.version<body.expected_version
    ||!['repaired','already_intact'].includes(p.outcome)||p.outcome==='repaired'&&p.version<=body.expected_version
    ||!HASH.test(p.snapshot_digest)||p.primary_rewritten!==false||p.witness_rewritten!==false
    ||p.historical_grant_extended!==false||p.network_executed!==false||p.independent_backup!==false)
    invalid('Invalid retained duplicate repair receipt.');
  return p;
}
export type DragonVaultRestore = {
  schema:'skeleton.dragon.vault-restore.v1';session_id:string;version:number;outcome:'restored'|'already_intact';
  snapshot_digest:string;ancestor_rollback:false;capture_consent_extended:false;historical_grant_extended:false;
  network_executed:false;model_context_permission:false;
};
export async function restoreDragonVaultPrimary(id:string,body:CrawlCommand&{retention_acknowledged:true},
  signal?:AbortSignal):Promise<DragonVaultRestore>{
  if(body.retention_acknowledged!==true||!integer(body.expected_version)||body.expected_version<1)
    invalid('Explicit cold-custody repair acknowledgement required.');
  const p=await read(api.post<DragonVaultRestore>(ROOT+'/sessions/'+identifier(id)+'/restore-vault-primary',body,options(signal)),
    getAuthToken(),'Historical primary repair unconfirmed. Refresh before retrying.');
  if(!p||p.schema!=='skeleton.dragon.vault-restore.v1'||p.session_id!==id||!integer(p.version)||p.version<body.expected_version
    ||!['restored','already_intact'].includes(p.outcome)||p.outcome==='restored'&&p.version<=body.expected_version
    ||!HASH.test(p.snapshot_digest)||p.ancestor_rollback!==false||p.capture_consent_extended!==false
    ||p.historical_grant_extended!==false||p.network_executed!==false||p.model_context_permission!==false)
    invalid('Invalid historical primary repair receipt.');
  return p;
}
export async function retireDragonSession(id:string,body:CrawlCommand&{retention_acknowledged:true},signal?:AbortSignal):Promise<DragonVaultCommand>{
  if(body.retention_acknowledged!==true||!integer(body.expected_version)||body.expected_version<1)invalid('Explicit retirement acknowledgement required.');
  const p=await read(api.post<DragonVaultCommand>(ROOT+'/sessions/'+identifier(id)+'/retire-to-vault',body,options(signal)),getAuthToken(),'Vault retirement unconfirmed. Refresh before retrying.');
  if(!p||p.schema!=='skeleton.dragon.vault-command.v1'||p.session_id!==id||!integer(p.version)||p.version<body.expected_version
     ||!validVaultState(p.vault)||!['vaulted','held','capacity_or_quota_held','quota_held','superseded'].includes(p.outcome)
     ||p.outcome==='vaulted'&&(!p.vault.active_slot_released||p.vault.state!=='vaulted')||p.network_executed!==false)invalid('Invalid retirement receipt.');
  return p;
}
export type TreasurySearchOptions = { cursor?:string; observedBefore?:number; left?:string; right?:string; vaultSessions?:string[] };
export async function getDragonTreasury(mode: TreasuryMode, query='', family?: string, signal?: AbortSignal, search: TreasurySearchOptions={}): Promise<DragonTreasury> {
  const {cursor,observedBefore,left,right,vaultSessions}=search;
  const selected=vaultSessions===undefined?null:vaultSelection(vaultSessions);
  if(selected&&mode==='current_only')invalid('Selected vault windows are history-only.');
  if (!['current_only','historic_only','all_revisions','timeline','compare','at_time'].includes(mode)||query.length>256||family!==undefined&&!HASH.test(family)
    ||cursor!==undefined&&!/^[a-f0-9]{64}:[0-9]{1,4}$/.test(cursor)
    ||(mode==='at_time')!==(observedBefore!==undefined)||observedBefore!==undefined&&(!Number.isFinite(observedBefore)||observedBefore<0)
    ||(left===undefined)!==(right===undefined)||left!==undefined&&(!right||!HASH.test(left)||!HASH.test(right)||left===right||mode!=='compare'||!family)) invalid('Invalid treasury search.');
  const params='?mode='+mode+'&query='+encodeURIComponent(query)+(family?'&family='+family:'')
    +(cursor?'&cursor='+encodeURIComponent(cursor):'')+(observedBefore!==undefined?'&observed_before='+observedBefore:'')
    +(left&&right?'&left='+left+'&right='+right:'')
    +(selected?'&vault_sessions='+encodeURIComponent(selected.join(',')):'');
  const p=await read(api.get<DragonTreasury>(ROOT+'/companion/treasury'+params,options(signal)),getAuthToken(),'Treasury reparse failed.');
  if(!p||p.schema!=='skeleton.dragon.treasury.v1'||p.parser!=='retained-text-sections-v3'||p.mode!==mode||p.family!==(family??null)
    ||!Number.isFinite(p.as_of_unix)||!HASH.test(p.partition_digest)||typeof p.candidate_limit_reached!=='boolean'||!integer(p.excluded_sessions,32)
    ||selected===null&&p.vault_window!=null
    ||selected!==null&&(!Array.isArray(p.vault_window)||p.vault_window.length!==selected.length
      ||p.vault_window.some((id,i)=>id!==selected[i])||p.current_indexed!==0||!p.candidate_limit_reached
      ||p.evolution?.hoarder_qualified!==false||p.evolution?.expedition_growth!==0
      ||!Array.isArray(p.revisit_plan)||p.revisit_plan.length!==0)
    ||p.observed_before!==(observedBefore??null)||!HASH.test(p.query_scope_digest)||!integer(p.page_offset,2048)||p.page_offset%24!==0
    ||p.page_offset!==(cursor?Number(cursor.split(':')[1]):0)||cursor!==undefined&&cursor.split(':')[0]!==p.query_scope_digest
    ||p.next_cursor!==null&&p.next_cursor!==p.query_scope_digest+':'+(p.page_offset+24)
    ||left===undefined&&p.comparison_selection!==null||left!==undefined&&(!p.comparison_selection||p.comparison_selection.left!==left||p.comparison_selection.right!==right)
    ||!integer(p.observations,2048)||!integer(p.families,p.observations)||!integer(p.revisions,p.observations)
    ||!integer(p.current_indexed,p.families)||!integer(p.historic_indexed,p.revisions)||!integer(p.metadata_only,p.revisions)
    ||p.current_indexed+p.historic_indexed+p.metadata_only!==p.revisions
    ||!integer(p.blocked_current,p.families)||p.blocked_current+p.current_indexed!==p.families
    ||!integer(p.changed_families,p.families)||!integer(p.rollbacks,p.revisions)||!integer(p.changes,p.revisions)
    ||!integer(p.revalidated_revisions,p.observations)||!integer(p.verified_historic_transitions,p.historic_indexed)
    ||!integer(p.verified_changed_families,p.changed_families)||!integer(p.alias_held_families,p.blocked_current)||!integer(p.parsed_unique_payloads,Math.min(256,p.observations))
    ||!integer(p.materialized_payload_hits,p.parsed_unique_payloads)||!integer(p.invalid_materialized_segments,32)||!integer(p.legacy_history_sessions,32)
    ||p.index_health!==undefined&&(!p.index_health||!integer(p.index_health.active_grants,32)
      ||![p.index_health.qualified_segments,p.index_health.missing_segments,p.index_health.stale_segments,p.index_health.invalid_segments]
        .every(value=>integer(value,p.index_health!.active_grants))
      ||p.index_health.qualified_segments+p.index_health.missing_segments+p.index_health.stale_segments+p.index_health.invalid_segments!==p.index_health.active_grants
      ||p.index_health.invalid_segments+p.index_health.stale_segments!==p.invalid_materialized_segments
      ||!integer(p.index_health.eligible_archive_members,2048)
      ||!integer(p.index_health.materialized_archive_members,p.index_health.eligible_archive_members))
    ||!['temporal_diversity_v1','temporal_query_rerank_v2'].includes(p.index_admission)
    ||!integer(p.eligible_observations,p.observations)||!integer(p.indexed_observations,Math.min(256,p.eligible_observations))
    ||p.index_admission==='temporal_diversity_v1'&&p.query_admission!=null
    ||p.index_admission==='temporal_query_rerank_v2'&&(!p.candidate_limit_reached||!p.query_admission
      ||!integer(p.query_admission.eligible_representatives,p.eligible_observations)
      ||p.query_admission.scanned_representatives!==p.query_admission.eligible_representatives
      ||!integer(p.query_admission.scanned_bytes,24000*p.query_admission.scanned_representatives)
      ||!integer(p.query_admission.matching_representatives,p.query_admission.scanned_representatives)
      ||!integer(p.query_admission.prioritized_representatives,Math.min(192,p.query_admission.matching_representatives,p.indexed_observations))
      ||p.query_admission.full_structural_corpus!==false
      ||p.query_admission.score_basis!=='permitted_plane_scan_bm25')
    ||p.parsed_unique_payloads>p.indexed_observations
    ||!Array.isArray(p.revisit_plan)||p.revisit_plan.length>24||p.revisit_plan.length>p.families
    ||p.revisit_plan.some(id=>typeof id!=='string'||!HASH.test(id))||new Set(p.revisit_plan).size!==p.revisit_plan.length
    ||!validEvolution(p.evolution)||!Array.isArray(p.family_rows)||p.family_rows.length>24||!p.family_rows.every(validFamily)
    ||new Set(p.family_rows.map(f=>f.family_id)).size!==p.family_rows.length
    ||![p.hits,p.timeline].every(rows=>Array.isArray(rows)&&rows.length<=24&&rows.every(validRevision)&&new Set(rows.map(v=>v.revision_id)).size===rows.length)
    ||p.hits.some(v=>!v.indexed||mode==='current_only'&&v.plane!=='current'||mode==='historic_only'&&v.plane!=='historic'||family&&v.family_id!==family
      ||mode==='at_time'&&(v.plane!=='historic'||v.last_seen>(observedBefore??0)||v.indexed_capture_at===null||v.indexed_capture_at>(observedBefore??0)))
    ||p.comparison!==null&&(!validRevision(p.comparison.current)||!validRevision(p.comparison.previous)||!validDelta(p.comparison.delta)
      ||p.comparison.current.family_id!==family||p.comparison.previous.family_id!==family
      ||left===undefined&&p.comparison.current.previous_revision_id!==p.comparison.previous.revision_id
      ||left!==undefined&&(p.comparison.previous.revision_id!==left||p.comparison.current.revision_id!==right))
    ||selected!==null&&([...(p.hits??[]),...(p.timeline??[]),...(p.comparison?[p.comparison.current,p.comparison.previous]:[])]
      .some(v=>v.plane!=='historic'||v.indexed&&(!v.session_id||!selected.includes(v.session_id)||!v.archive_only))
      ||p.family_rows.some(v=>v.current_indexed||v.refresh_url!==null))
    ||p.earliest_source_expiry!==null&&(!Number.isFinite(p.earliest_source_expiry)||p.earliest_source_expiry<=p.as_of_unix)
    ||p.latest_observed_only!==true||p.source_text_returned!==false||p.network_executed!==false||p.training_permission!==false||p.fresh_consent_required!==true)invalid('Invalid version-separated treasury projection.');
  return p;
}
export type DragonLegacyCandidate = {
  session_id:string;version:number;qualified:boolean;eligible_sources:number;
  archive_grant:DragonArchiveGrant|null;snapshot_digest:string|null;historical_runtime_digest:string|null;
};
export type DragonLegacyCatalog = {
  schema:'skeleton.dragon.legacy-catalog.v1';sessions:DragonLegacyCandidate[];
  capacity_reached:boolean;execution_authorized:false;
};
export async function getLegacyTreasuryCatalog(signal?:AbortSignal):Promise<DragonLegacyCatalog>{
  const p=await read(api.get<DragonLegacyCatalog>(ROOT+'/companion/legacy-catalog',options(signal)),getAuthToken(),'Historical catalogue unavailable.');
  if(!p||p.schema!=='skeleton.dragon.legacy-catalog.v1'||p.execution_authorized!==false||typeof p.capacity_reached!=='boolean'
    ||!Array.isArray(p.sessions)||p.sessions.length>32||new Set(p.sessions.map(v=>v?.session_id)).size!==p.sessions.length
    ||p.sessions.some(v=>!v||typeof v.session_id!=='string'||!ID.test(v.session_id)||!integer(v.version)||v.version<1
      ||typeof v.qualified!=='boolean'||!integer(v.eligible_sources,64)
      ||v.qualified&&(!v.snapshot_digest||!HASH.test(v.snapshot_digest)||!v.historical_runtime_digest||!HASH.test(v.historical_runtime_digest)
        ||!v.archive_grant||!validArchiveGrant(v.archive_grant,64))
      ||!v.qualified&&(v.eligible_sources!==0||v.snapshot_digest!==null||v.historical_runtime_digest!==null||v.archive_grant!==null)))
    invalid('Invalid legacy archive catalogue.');
  return p;
}
export async function configureLegacyTreasuryArchive(id:string,body:CrawlCommand&{enabled:boolean;days:number;archive_rights_acknowledged:boolean},signal?:AbortSignal):Promise<{version:number;enabled:boolean;execution_authorized:false}>{
  if(!integer(body.days,30)||body.days<1||typeof body.enabled!=='boolean'||typeof body.archive_rights_acknowledged!=='boolean'
    ||body.enabled&&!body.archive_rights_acknowledged)invalid('Explicit historical retention rights required.');
  const p=await read(api.post<{version:number;enabled:boolean;execution_authorized:false}>(ROOT+'/sessions/'+identifier(id)+'/legacy-archive',body,options(signal)),getAuthToken(),'Legacy archive command unconfirmed.');
  if(!p||!integer(p.version)||p.version<body.expected_version||typeof p.enabled!=='boolean'||p.execution_authorized!==false)invalid('Invalid legacy archive receipt.');
  return p;
}
export async function configureTreasuryWatch(id:string,body:TreasuryWatchCommand,signal?:AbortSignal):Promise<{watch:DragonTreasuryWatch|null;version:number}> {
  if(typeof body.enabled!=='boolean'||!HASH.test(body.source_id)||!integer(body.days,7)||body.days<1
    ||!integer(body.cycles,6)||body.cycles<1||!integer(body.minimum_interval,604800)||body.minimum_interval<21600
    ||!integer(body.retention_days,30)||body.retention_days<1||typeof body.capture_rights_acknowledged!=='boolean'
    ||typeof body.archive_rights_acknowledged!=='boolean'||body.enabled&&(!body.capture_rights_acknowledged||!body.archive_rights_acknowledged)) invalid('Explicit finite source-watch authority is required.');
  const p=await read(api.post<{watch:DragonTreasuryWatch|null;version:number}>(ROOT+'/sessions/'+identifier(id)+'/treasury-watch',body,options(signal)),getAuthToken(),'Treasury watch command not confirmed.');
  if(!p||!Number.isSafeInteger(p.version)||p.version<body.expected_version||p.watch!==null&&!validWatch(p.watch)) invalid('Invalid treasury watch command receipt.');
  return p;
}
export async function configureDragonArchive(id: string, body: CrawlCommand & { enabled: boolean; days: number; archive_rights_acknowledged: boolean }, signal?: AbortSignal): Promise<CrawlSession> {
  if(!integer(body.days,30)||body.days<1||typeof body.enabled!=='boolean'||typeof body.archive_rights_acknowledged!=='boolean'||body.enabled&&!body.archive_rights_acknowledged)invalid('Explicit historical retention rights required.');
  const p=await read(api.post<{session:CrawlSession}>(ROOT+'/sessions/'+identifier(id)+'/archive-grant',body,options(signal)),getAuthToken(),'Archive permission could not be confirmed. Refresh current session state.');
  return session(p.session,id);
}
export async function getDragonSanctuary(signal?: AbortSignal): Promise<DragonSanctuary> {
  const p = await read(api.get<DragonSanctuary>(ROOT + '/companion/sanctuary', options(signal)), getAuthToken(), 'The companion sanctuary could not be refreshed.');
  const forms = ['hatchling','scout','scholar','pathfinder','archivist'];
  const habitats = ['web','document','structured','media','text','artifact'];
  if (!p || p.schema !== 'skeleton.dragon.sanctuary.v1'
    || !integer(p.collection_index, 1000) || !integer(p.stage, 4) || forms[p.stage] !== p.form
    || p.stage !== [120,300,550,800].filter(t => p.collection_index >= t).length
    || !integer(p.eligible_expeditions, 8) || !integer(p.unqualified_expeditions, 8)
    || p.eligible_expeditions + p.unqualified_expeditions > 8
    || !integer(p.contributing_expeditions, p.eligible_expeditions)
    || !integer(p.candidate_sources, 128) || !integer(p.distinct_content, p.candidate_sources)
    || !integer(p.exact_duplicates, p.candidate_sources) || p.distinct_content + p.exact_duplicates !== p.candidate_sources
    || !integer(p.credited_sources, p.distinct_content) || !integer(p.low_signal_sources, p.distinct_content)
    || p.credited_sources + p.low_signal_sources !== p.distinct_content || !integer(p.distinct_origins, p.credited_sources)
    || !p.habitats || typeof p.habitats !== 'object' || Array.isArray(p.habitats)
    || Object.entries(p.habitats).some(([k,n]) => !habitats.includes(k) || !integer(n,p.credited_sources) || n < 1)
    || Object.values(p.habitats).reduce((a,n)=>a+n,0) !== p.credited_sources
    || !Array.isArray(p.source_refs) || p.source_refs.length !== Math.min(16,p.credited_sources)
    || p.source_refs.some(row => !row || !ID.test(row.session_id) || !HASH.test(row.source_id)
      || !integer(row.credit_milli,1000) || row.credit_milli < 50)
    || new Set(p.source_refs.map(row=>row.session_id+':'+row.source_id)).size !== p.source_refs.length
    || !HASH.test(p.revision_digest) || typeof p.candidate_limit_reached !== 'boolean'
    || !Number.isFinite(p.as_of_unix) || p.as_of_unix < 0
    || (p.candidate_sources === 0) !== (p.earliest_source_expiry === null)
    || p.earliest_source_expiry !== null && (!Number.isFinite(p.earliest_source_expiry) || p.earliest_source_expiry <= p.as_of_unix)
    || p.current_consent_only !== true || p.persistent_reward_wallet !== false || p.source_text_returned !== false
    || p.training_permission !== false || p.network_authority_expanded !== false) invalid('Invalid current-consent sanctuary projection.');
  return p;
}
export type AcquisitionHoldCatalog = {
  ok: true; schema: 'skeleton.dragon.acquisition-holds.v1'; as_of: number;
  qualified_sessions: number; excluded_sessions: number; capacity_reached: boolean;
  holds: {host: string; observed_grants: number; latest_grant_expiry: number;
    denial_statuses: number; rejected_success_statuses: number}[];
  reason_inferred: false; network_executed: false; dispatch_lock: false; network_authority_expanded: false;
};

export async function getAcquisitionHoldCatalog(signal?: AbortSignal): Promise<AcquisitionHoldCatalog> {
  const result = await read(api.get<AcquisitionHoldCatalog>(ROOT + '/acquisition-holds', options(signal)),
    getAuthToken(), 'The owner acquisition restriction catalogue could not be observed.');
  if (!result || result.ok !== true || result.schema !== 'skeleton.dragon.acquisition-holds.v1'
    || !Number.isFinite(result.as_of) || result.as_of < 0 || result.as_of > 8640000000
    || !integer(result.qualified_sessions, 32) || !integer(result.excluded_sessions, 32)
    || result.qualified_sessions + result.excluded_sessions > 32
    || typeof result.capacity_reached !== 'boolean' || result.reason_inferred !== false
    || result.network_executed !== false || result.dispatch_lock !== false || result.network_authority_expanded !== false
    || !Array.isArray(result.holds) || result.holds.length > 512
    || result.holds.some(h => !h || typeof h.host !== 'string' || !/^[a-z0-9][a-z0-9.-]{0,252}$/.test(h.host)
      || !integer(h.observed_grants, result.qualified_sessions) || h.observed_grants < 1
      || !Number.isFinite(h.latest_grant_expiry) || h.latest_grant_expiry <= result.as_of
      || h.latest_grant_expiry > 8640000000
      || !integer(h.denial_statuses, h.observed_grants * 128)
      || !integer(h.rejected_success_statuses, h.observed_grants * 128)
      || h.denial_statuses + h.rejected_success_statuses > h.observed_grants * 128)
    || new Set(result.holds.map(h => h.host)).size !== result.holds.length) {
    invalid('Invalid owner acquisition restriction catalogue.');
  }
  return result;
}

export async function getCrawlerReadiness(signal?: AbortSignal): Promise<CrawlerReadiness> {
  const value = await read(api.get<CrawlerReadiness>(ROOT + '/readiness', options(signal)), getAuthToken(), 'Crawler readiness is unavailable.');
  if (!value || typeof value.available !== 'boolean' || typeof value.configured !== 'boolean' || typeof value.message !== 'string' || !value.capabilities || !value.limits) invalid('The crawler readiness projection is invalid.');
  return value;
}
export async function listCrawls(cursor?: string, signal?: AbortSignal): Promise<{ sessions: CrawlSession[]; next_cursor: string | null }> {
  const value = await read(api.get<{ sessions: CrawlSession[]; next_cursor: string | null }>(ROOT + '/sessions?limit=32' + (cursor ? '&cursor=' + identifier(cursor) : ''), options(signal)), getAuthToken(), 'Your crawler sessions could not be loaded.');
  if (!Array.isArray(value.sessions) || value.sessions.length > 32 || value.next_cursor !== null && !ID.test(value.next_cursor)) invalid('The crawler session page is invalid.');
  value.sessions.forEach(row => session(row)); return value;
}
export async function getCrawl(id: string, signal?: AbortSignal): Promise<CrawlSession> {
  const value = await read(api.get<{ session: CrawlSession }>(ROOT + '/sessions/' + identifier(id), options(signal)), getAuthToken(), 'The crawler session could not be refreshed.'); return session(value.session, id);
}
export async function getNavigationPacket(id:string,signal?:AbortSignal): Promise<{packet:NavigationPacket;version:number}> {
  const v=await read(api.get<{ok:true;session_id:string;packet:NavigationPacket;version:number;network_authorized:false}>(
    ROOT+'/sessions/'+identifier(id)+'/navigation/packet',options(signal)),getAuthToken(),'Navigation packet unavailable.');
  const p=v?.packet;
  if(!v||v.ok!==true||v.session_id!==id||v.network_authorized!==false||!integer(v.version)||!p
    ||!HASH.test(p.snapshot_digest)||!HASH.test(p.packet_digest)||!integer(p.as_of,1000000000000)||!Array.isArray(p.objective)||p.objective.length>20
    ||!Array.isArray(p.candidates)||p.candidates.length>48
    ||p.candidates.some(c=>!HASH.test(c.id)||!Array.isArray(c.terms)||c.terms.length>8
      ||!integer(c.depth,3)||!integer(c.attempts,3)||!integer(c.semantic,1000))) invalid('Invalid navigation packet.');
  return {packet:p,version:v.version};
}
export async function retainNavigationInventory(id:string,body:{expected_snapshot_digest:string;
    rights_reference:string;retention_seconds:number;acknowledged:true},signal?:AbortSignal) {
  if(!HASH.test(body.expected_snapshot_digest)||body.acknowledged!==true||!integer(body.retention_seconds,315360000)
    ||body.retention_seconds<900||!body.rights_reference.trim()) invalid('Explicit locator retention authority required.');
  const v=await read(api.post<{grant_id:string;checkpoint:string;accepted:number;omitted_nonpublic:number;
    retention_expires_at:number;replayed:boolean;network_authorized:false;metadata_only:true}>(
      ROOT+'/sessions/'+identifier(id)+'/navigation/federate',body,options(signal)),getAuthToken(),'Locator retention not confirmed.');
  if(!v||!HASH.test(v.grant_id)||v.checkpoint!==body.expected_snapshot_digest||v.metadata_only!==true
    ||v.network_authorized!==false||!integer(v.accepted,4096)||!integer(v.omitted_nonpublic,4096)) invalid('Invalid locator retention receipt.');
  return v;
}
export async function searchNavigationFederation(query:string,cursor?:string,signal?:AbortSignal):Promise<NavigationFederationPage> {
  if(query.length>512||cursor&&!/^[a-f0-9]{64}:[a-f0-9]{64}$/.test(cursor)) invalid('Invalid federation search.');
  const v=await read(api.get<NavigationFederationPage>(ROOT+'/navigation/federation?query='+encodeURIComponent(query)
    +(cursor?'&after='+encodeURIComponent(cursor):''),options(signal)),getAuthToken(),'Navigation federation search unavailable.');
  if(!v||v.candidate_metadata_only!==true||v.network_authorized!==false||v.global_completeness_claimed!==false
    ||!Array.isArray(v.targets)||v.targets.length>32||v.targets.some(t=>!HASH.test(t.id)||!navigationUrl(t.url)
      ||t.network_authorized!==false||t.reviewed!==false||!t.witness||!HASH.test(t.witness.grant_id)
      ||!HASH.test(t.witness.checkpoint)||!Number.isFinite(t.semantic)||t.semantic<0||t.semantic>1)
    ||v.next_cursor!==null&&!/^[a-f0-9]{64}:[a-f0-9]{64}$/.test(v.next_cursor)) invalid('Invalid federation page.');
  return v;
}
export type ResearchNavigationPlan = {
  schema:'skeleton.dragon.navigation-plan.v1'; mode:'balanced'|'coverage'|'exploration'|'conservation';
  epoch:number; facets:{id:string;terms:string[];concepts:number[];estimated_coverage:number}[];
  targets:{target_id:string;url:string;host:string;jeeves:number;dragon:number;joint:number;estimated_work_units:number;
    coverage_gain:number;redundancy_penalty:number;historical_yield_prior:number;historical_uncertainty:number;
    supporting_lineage:number;facet_scores:{id:string;score:number}[];dense_similarity?:number;calibrated_yield?:number;network_authorized:false;reviewed:false}[];
  budget:number;remaining:number;distinct_hosts:number;excluded_prior_targets:number;pool_truncated:boolean;
  index_backfill_pending:boolean;objective_coverage_is_estimated:true;cost_is_advisory:true;
  network_authorized:false;training_permission:false;receipt:string;
  learning?:{dense:{status:'encoded'|'empty_pool'|'local_encoder_held';model_digest?:string;dimensions?:number;batches?:number};
    calibration:{status:'insufficient_outcomes'|'baseline_retained'|'heldout_improvement';training_targets:number;holdout_targets:number;holdout_log_loss:number|null;baseline_log_loss:number|null;telemetry_only:true;persisted:false;production_quality_verified:false}};
};
function navigationUnit(x:unknown):x is number {return typeof x==='number'&&Number.isFinite(x)&&x>=0&&x<=1;}
export async function getResearchNavigationPlan(query:string,mode:ResearchNavigationPlan['mode']='balanced',
    budget=16,previous:string[]=[],signal?:AbortSignal,learned=false):Promise<ResearchNavigationPlan>{
  if(!query.trim()||query.length>512||!['balanced','coverage','exploration','conservation'].includes(mode)
      ||!integer(budget,48)||budget<1||previous.length>128||new Set(previous).size!==previous.length
      ||previous.some(id=>!HASH.test(id))) invalid('Invalid bounded research plan.');
  const v=await read(api.post<ResearchNavigationPlan>(ROOT+'/navigation/federation/research-plan',
    {query,budget,mode,previous,learned},options(signal)),getAuthToken(),'Research plan unavailable.');
  if(!v||v.schema!=='skeleton.dragon.navigation-plan.v1'||v.mode!==mode||v.budget!==budget
    ||!integer(v.remaining,budget)||!integer(v.epoch)||!integer(v.distinct_hosts,24)
    ||v.excluded_prior_targets!==previous.length||v.network_authorized!==false||v.training_permission!==false
    ||v.objective_coverage_is_estimated!==true||v.cost_is_advisory!==true||!HASH.test(v.receipt)
    ||typeof v.pool_truncated!=='boolean'||typeof v.index_backfill_pending!=='boolean'
    ||!Array.isArray(v.facets)||v.facets.length<1||v.facets.length>8
    ||v.facets.some(f=>!f||!/^([a-f0-9]{16})$/.test(f.id)||!Array.isArray(f.terms)||f.terms.length>48
      ||!Array.isArray(f.concepts)||f.concepts.length>128||!navigationUnit(f.estimated_coverage))
    ||!Array.isArray(v.targets)||v.targets.length>24
    ||v.targets.some(t=>!t||!HASH.test(t.target_id)||previous.includes(t.target_id)||!navigationUrl(t.url)
       ||t.network_authorized!==false||t.reviewed!==false||!integer(t.estimated_work_units,3)||t.estimated_work_units<1
       ||![t.jeeves,t.dragon,t.coverage_gain,t.redundancy_penalty,t.historical_yield_prior,t.historical_uncertainty,t.supporting_lineage].every(navigationUnit)
       ||t.dense_similarity!==undefined&&!navigationUnit(t.dense_similarity)||t.calibrated_yield!==undefined&&!navigationUnit(t.calibrated_yield)
       ||!Number.isFinite(t.joint)||t.joint<-.2||t.joint>1||!Array.isArray(t.facet_scores)||t.facet_scores.length!==v.facets.length
       ||t.facet_scores.some((x,i)=>x.id!==v.facets[i].id||!navigationUnit(x.score)))
    ||new Set(v.targets.map(t=>t.target_id)).size!==v.targets.length
    ||v.targets.reduce((total,t)=>total+t.estimated_work_units,0)+v.remaining!==budget)
    invalid('Invalid research plan receipt.');
  return v;
}
export type ResearchCampaign={
  campaign_id:string;objective_digest:string;mode:ResearchNavigationPlan['mode'];learned:boolean;
  created_at:number;expires_at:number;budget:number;remaining:number;revision:number;rounds:number;
  state:'active'|'exhausted'|'closed'|'expired';network_authorized:false;training_permission:false
};
export type CampaignRound={campaign:ResearchCampaign;round:number;plan_digest:string;spent:number;created_at:number;
  pool_truncated:boolean;targets:{target_id:string;position:number;cost:number;url:string;host:string;network_authorized:false}[];
  replayed:boolean;network_authorized:false;training_permission:false;receipt:string};
const CAMPAIGNS=ROOT+'/navigation/campaigns';
function campaignValid(v:ResearchCampaign,id?:string){
  if(!v||!HASH.test(v.campaign_id)||id!==undefined&&v.campaign_id!==id||!HASH.test(v.objective_digest)
      ||!['balanced','coverage','exploration','conservation'].includes(v.mode)||typeof v.learned!=='boolean'
      ||!integer(v.created_at)||!integer(v.expires_at)||v.expires_at<=v.created_at||v.expires_at-v.created_at>2592000
      ||!integer(v.budget,4096)||v.budget<1||!integer(v.remaining,v.budget)||!integer(v.revision,130)||v.revision<1
      ||!integer(v.rounds,128)||!['active','exhausted','closed','expired'].includes(v.state)
      ||v.network_authorized!==false||v.training_permission!==false) invalid('Invalid research campaign custody.');
  return v;
}
function campaignOperation(operation:string){return typeof operation==='string'&&/^[!-~]{16,128}$/.test(operation);}
export async function createResearchCampaign(body:{query:string;operation:string;budget:number;retention_seconds:number;
  mode:ResearchCampaign['mode'];learned:boolean;acknowledged:true},signal?:AbortSignal){
  if(!body.query.trim()||body.query.length>512||!campaignOperation(body.operation)||!integer(body.budget,4096)||body.budget<1
    ||!integer(body.retention_seconds,2592000)||body.retention_seconds<900||body.acknowledged!==true)
    invalid('Explicit finite campaign required.');
  const v=await read(api.post<ResearchCampaign&{replayed:boolean}>(CAMPAIGNS,body,options(signal)),getAuthToken(),'Campaign creation held.');
  campaignValid(v);
  if(typeof v.replayed!=='boolean'||v.budget!==body.budget||v.mode!==body.mode||v.learned!==body.learned)
    invalid('Campaign creation identity differs.');
  return v;
}
export async function advanceResearchCampaign(id:string,body:{query:string;operation:string;expected_revision:number;budget:number},signal?:AbortSignal){
  if(!HASH.test(id)||!body.query.trim()||body.query.length>512||!campaignOperation(body.operation)
    ||!integer(body.expected_revision,129)||body.expected_revision<1||!integer(body.budget,48)||body.budget<1)
    invalid('Invalid campaign advance.');
  const v=await read(api.post<CampaignRound>(CAMPAIGNS+'/'+id+'/advance',body,options(signal)),getAuthToken(),'Campaign advance held; reload custody.');
  if(!v||!HASH.test(v.plan_digest)||!HASH.test(v.receipt)||!integer(v.round,128)||v.round<1||!integer(v.spent,body.budget)
    ||!integer(v.created_at)||typeof v.pool_truncated!=='boolean'||typeof v.replayed!=='boolean'
    ||v.network_authorized!==false||v.training_permission!==false||!Array.isArray(v.targets)||v.targets.length>24
    ||v.targets.some(x=>!x||!HASH.test(x.target_id)||!navigationUrl(x.url)||!integer(x.position,23)
       ||!integer(x.cost,3)||x.cost<1||x.network_authorized!==false)
    ||new Set(v.targets.map(x=>x.target_id)).size!==v.targets.length
    ||new Set(v.targets.map(x=>x.position)).size!==v.targets.length
    ||v.targets.reduce((s,x)=>s+x.cost,0)>v.spent)invalid('Invalid campaign round custody.');
  campaignValid(v.campaign,id);return v;
}
export async function inspectResearchCampaign(id:string,after=0,limit=16,signal?:AbortSignal){
  if(!HASH.test(id)||!integer(after,128)||!integer(limit,64)||limit<1)invalid('Invalid campaign history cursor.');
  const v=await read(api.get<{campaign:ResearchCampaign;rounds:{ordinal:number;spent:number;plan_digest:string;
      created_at:number;pool_truncated:boolean}[];next_cursor:number|null;network_authorized:false;training_permission:false}>(
      CAMPAIGNS+'/'+id+'?after='+after+'&limit='+limit,options(signal)),getAuthToken(),'Campaign history unavailable.');
  if(!v||v.network_authorized!==false||v.training_permission!==false||!Array.isArray(v.rounds)||v.rounds.length>limit
    ||v.rounds.some((x,i)=>!x||!integer(x.ordinal,128)||x.ordinal<=(i?v.rounds[i-1].ordinal:after)
      ||!integer(x.spent,48)||!HASH.test(x.plan_digest)||!integer(x.created_at)||typeof x.pool_truncated!=='boolean')
    ||v.next_cursor!==null&&(!integer(v.next_cursor,128)||v.next_cursor<=after))invalid('Invalid campaign history.');
  campaignValid(v.campaign,id);return v;
}
export async function closeResearchCampaign(id:string,expectedRevision:number,signal?:AbortSignal){
  if(!HASH.test(id)||!integer(expectedRevision,130)||expectedRevision<1)invalid('Invalid campaign close.');
  const v=await read(api.post<ResearchCampaign&{replayed:boolean}>(CAMPAIGNS+'/'+id+'/close',
    {expected_revision:expectedRevision},options(signal)),getAuthToken(),'Campaign close held.');
  campaignValid(v,id);
  if(v.state!=='closed'||typeof v.replayed!=='boolean')invalid('Campaign close not confirmed.');
  return v;
}
export type ResearchFleet={
  fleet_id:string;revision:number;created_at:number;expires_at:number;budget:number;remaining:number;
  state:'active'|'closed'|'exhausted'|'expired';members:{campaign_id:string;weight:number;rounds:number;
  spent:number;campaign_revision:number|null;campaign_remaining:number|null;eligible:boolean}[];
  network_authorized:false;training_permission:false
};
export type FleetPulse={fleet:ResearchFleet;operation:string;campaign_id:string;state:'complete'|'held';
  allocated:number;spent:number;round:number|null;plan_digest:string|null;code:string|null;
  targets:CampaignRound['targets'];replayed:boolean;network_authorized:false;receipt:string};
const FLEETS=ROOT+'/navigation/fleets';
function fleetValid(v:ResearchFleet,id?:string){
  if(!v||!HASH.test(v.fleet_id)||id!==undefined&&v.fleet_id!==id||!integer(v.revision,1282)||v.revision<1
    ||!integer(v.created_at)||!integer(v.expires_at)||v.expires_at<=v.created_at||v.expires_at-v.created_at>2592000
    ||!integer(v.budget,40960)||v.budget<1||!integer(v.remaining,v.budget)
    ||!['active','closed','exhausted','expired'].includes(v.state)||v.network_authorized!==false||v.training_permission!==false
    ||!Array.isArray(v.members)||v.members.length>10||new Set(v.members.map(m=>m.campaign_id)).size!==v.members.length
    ||v.members.some(m=>!m||!HASH.test(m.campaign_id)||!integer(m.weight,16)||m.weight<1
      ||!integer(m.rounds,1280)||!integer(m.spent,4096)||typeof m.eligible!=='boolean'
      ||m.campaign_revision!==null&&(!integer(m.campaign_revision,130)||m.campaign_revision<1)
      ||m.campaign_remaining!==null&&!integer(m.campaign_remaining,4096))
    ||v.members.reduce((s,m)=>s+m.spent,0)>v.budget-v.remaining)invalid('Invalid research fleet custody.');
  return v;
}
export async function createResearchFleet(body:{operation:string;members:{campaign_id:string;weight:number}[];
  budget:number;retention_seconds:number;acknowledged:true},signal?:AbortSignal){
  if(!campaignOperation(body.operation)||!Array.isArray(body.members)||body.members.length<1||body.members.length>10
    ||new Set(body.members.map(m=>m.campaign_id)).size!==body.members.length||body.members.some(m=>!HASH.test(m.campaign_id)
      ||!integer(m.weight,16)||m.weight<1)||!integer(body.budget,40960)||body.budget<1
    ||!integer(body.retention_seconds,2592000)||body.retention_seconds<900||body.acknowledged!==true)
    invalid('Explicit finite research fleet required.');
  const v=await read(api.post<ResearchFleet&{replayed:boolean}>(FLEETS,body,options(signal)),getAuthToken(),'Research fleet creation held.');
  fleetValid(v);
  if(v.budget!==body.budget||typeof v.replayed!=='boolean')invalid('Fleet identity differs.');
  return v;
}
export async function pulseResearchFleet(id:string,body:{operation:string;objectives:{campaign_id:string;query:string}[];
  expected_revision:number;budget:number},signal?:AbortSignal){
  if(!HASH.test(id)||!campaignOperation(body.operation)||!integer(body.expected_revision,1282)||body.expected_revision<1
    ||!integer(body.budget,48)||body.budget<1||!Array.isArray(body.objectives)||body.objectives.length<1||body.objectives.length>10
    ||new Set(body.objectives.map(m=>m.campaign_id)).size!==body.objectives.length||body.objectives.some(m=>!HASH.test(m.campaign_id)
      ||typeof m.query!=='string'||!m.query.trim()||m.query.length>512))invalid('Invalid fleet pulse.');
  const v=await read(api.post<FleetPulse>(FLEETS+'/'+id+'/pulse',body,options(signal)),getAuthToken(),'Fleet pulse held; inspect or reconcile.');
  if(!v||!HASH.test(v.operation)||!HASH.test(v.campaign_id)||!HASH.test(v.receipt)||!['complete','held'].includes(v.state)
    ||!integer(v.allocated,body.budget)||v.allocated<1||!integer(v.spent,v.allocated)||typeof v.replayed!=='boolean'
    ||v.network_authorized!==false||!Array.isArray(v.targets)||v.targets.length>24
    ||v.targets.some(x=>!x||!HASH.test(x.target_id)||!navigationUrl(x.url)||!integer(x.position,23)||!integer(x.cost,3)||x.cost<1
      ||x.network_authorized!==false)||new Set(v.targets.map(x=>x.target_id)).size!==v.targets.length
    ||v.targets.reduce((s,x)=>s+x.cost,0)>v.spent
    ||v.state==='complete'&&(!HASH.test(v.plan_digest??'')||!integer(v.round??0,128)||v.round===0)
    ||v.state==='held'&&(v.spent!==0||v.targets.length!==0||v.plan_digest!==null||v.round!==null||!v.code))
    invalid('Invalid fleet pulse receipt.');
  fleetValid(v.fleet,id);return v;
}
export async function inspectResearchFleet(id:string,after?:string,limit=16,signal?:AbortSignal){
  if(!HASH.test(id)||after!==undefined&&!HASH.test(after)||!integer(limit,64)||limit<1)invalid('Invalid fleet inspection cursor.');
  const v=await read(api.get<{fleet:ResearchFleet;jobs:{operation:string;campaign:string;state:'leased'|'complete'|'held';
    spent:number;round:number|null;plan_digest:string|null;code:string|null;created:number;updated:number}[];
    next_cursor:string|null;network_authorized:false}>(FLEETS+'/'+id+'?limit='+limit+(after?'&after='+after:''),options(signal)),
    getAuthToken(),'Research fleet unavailable.');
  if(!v||v.network_authorized!==false||!Array.isArray(v.jobs)||v.jobs.length>limit
    ||v.next_cursor!==null&&!HASH.test(v.next_cursor)||v.jobs.some(j=>!j||!HASH.test(j.operation)||!HASH.test(j.campaign)
      ||!['leased','complete','held'].includes(j.state)||!integer(j.spent,48)||!integer(j.created)||!integer(j.updated)))
    invalid('Invalid fleet history.');
  fleetValid(v.fleet,id);return v;
}
export async function reconcileResearchFleet(id:string,signal?:AbortSignal){
  if(!HASH.test(id))invalid('Invalid fleet identity.');
  const v=await read(api.post<{fleet:ResearchFleet;reconciled:boolean;operation?:string;state?:'complete'|'held';spent?:number;
    network_authorized:false}>(FLEETS+'/'+id+'/reconcile',{},options(signal)),getAuthToken(),'Fleet recovery held.');
  if(!v||typeof v.reconciled!=='boolean'||v.network_authorized!==false
    ||v.reconciled&&(!HASH.test(v.operation??'')||!['complete','held'].includes(v.state??'')||!integer(v.spent??-1,48)))
    invalid('Invalid fleet recovery receipt.');
  fleetValid(v.fleet,id);return v;
}
export async function closeResearchFleet(id:string,revision:number,signal?:AbortSignal){
  if(!HASH.test(id)||!integer(revision,1282)||revision<1)invalid('Invalid fleet close.');
  const v=await read(api.post<ResearchFleet&{replayed:boolean}>(FLEETS+'/'+id+'/close',{expected_revision:revision},options(signal)),
    getAuthToken(),'Fleet closure held.');
  fleetValid(v,id);
  if(v.state!=='closed'||typeof v.replayed!=='boolean')invalid('Fleet closure not confirmed.');
  return v;
}
export type MatrixWitness={session_id:string;source_id:string;version:number;snapshot_digest:string;
  valid_until:number;captured_at:number;policy_version:number};
export type ArchiveMatrix={schema:'skeleton.dragon.archive-matrix.v1';objective_count:number;scanned_sessions:number;
  held_sessions:number;verified_source_checks:number;matching_payloads:number;result_truncated:boolean;
  objectives:{objective_id:string;estimated_coverage:number}[];
  payloads:{payload:string;score:number;witness_count:number;witnesses:MatrixWitness[];
    objectives:{objective_id:string;matched_terms:number;term_frequency:number;coverage:number;score:number;best_witness:MatrixWitness}[];
    independent_corroboration_verified:false}[];
  feature_work:{requests:number;hits:number;misses:number;evictions:number;resident_entries:number;estimated_feature_bytes:number;persistent:false};
  next_cursor:string|null;as_of_unix:number;approximate_routing:true;page_local_ranking:true;history_only:true;
  network_authorized:false;source_text_returned:false;model_context_permission:false;training_permission:false;
  coverage_is_estimated:true;receipt:string};
function matrixWitness(v:MatrixWitness){return !!v&&ID.test(v.session_id)&&HASH.test(v.source_id)&&HASH.test(v.snapshot_digest)
  &&integer(v.version)&&v.version>0&&Number.isFinite(v.valid_until)&&Number.isFinite(v.captured_at)&&integer(v.policy_version);}
export async function getArchiveMatrix(queries:string[],limit=32,cursor?:string,sessionIds?:string[],signal?:AbortSignal){
  if(!Array.isArray(queries)||queries.length<1||queries.length>10||new Set(queries).size!==queries.length
     ||queries.some(q=>typeof q!=='string'||!q.trim()||q.length>512)||!integer(limit,128)||limit<1
     ||cursor!==undefined&&cursor.length>193||sessionIds!==undefined&&(!Array.isArray(sessionIds)||sessionIds.length<1
       ||sessionIds.length>100||new Set(sessionIds).size!==sessionIds.length||sessionIds.some(s=>!ID.test(s))))
    invalid('Invalid historical objective matrix.');
  const v=await read(api.post<ArchiveMatrix>(ROOT+'/companion/archive-matrix',{queries,limit,cursor:cursor??null,session_ids:sessionIds??null},options(signal)),
    getAuthToken(),'Historical archive matrix unavailable.');
  if(!v||v.schema!=='skeleton.dragon.archive-matrix.v1'||v.objective_count!==queries.length||!integer(v.scanned_sessions,32)
    ||!integer(v.held_sessions,v.scanned_sessions)||!integer(v.verified_source_checks,32*64)||!integer(v.matching_payloads,32*64)
    ||!HASH.test(v.receipt)||v.history_only!==true||v.network_authorized!==false||v.source_text_returned!==false
    ||v.model_context_permission!==false||v.training_permission!==false||v.coverage_is_estimated!==true||v.approximate_routing!==true
    ||v.page_local_ranking!==true||typeof v.result_truncated!=='boolean'||!Number.isFinite(v.as_of_unix)
    ||!v.feature_work||v.feature_work.persistent!==false||!integer(v.feature_work.requests,32*64)
    ||v.feature_work.hits+v.feature_work.misses!==v.feature_work.requests
    ||!Array.isArray(v.objectives)||v.objectives.length!==queries.length||v.objectives.some(q=>!q||!HASH.test(q.objective_id)||!navigationUnit(q.estimated_coverage))
    ||new Set(v.objectives.map(q=>q.objective_id)).size!==queries.length||!Array.isArray(v.payloads)||v.payloads.length>limit
    ||new Set(v.payloads.map(p=>p.payload)).size!==v.payloads.length||v.payloads.some(p=>!p||!HASH.test(p.payload)||!navigationUnit(p.score)
      ||!integer(p.witness_count,32*64)||p.witness_count<1||p.independent_corroboration_verified!==false
      ||!Array.isArray(p.witnesses)||!p.witnesses.length||p.witnesses.length>4||!p.witnesses.every(matrixWitness)
      ||!Array.isArray(p.objectives)||p.objectives.length>queries.length||p.objectives.some(q=>!q
        ||!v.objectives.some(o=>o.objective_id===q.objective_id)||!integer(q.matched_terms,32)||q.matched_terms<1
        ||!integer(q.term_frequency,256)||!navigationUnit(q.coverage)||!navigationUnit(q.score)||!matrixWitness(q.best_witness))))
    invalid('Invalid historical archive matrix receipt.');
  return v;
}
export type BulkMigrationCandidate={session_id:string;version:number;manifest:string;expected_bytes:number;expires_at:number;physical_layout_verified:false};
export type BulkMigrationReceipt={manifest:string;sha256:string;bytes:number;chunks:number;
  layout:'content_defined_v1';switched:boolean;replayed:boolean;readback_verified:true;garbage_remaining:number;
  unreferenced_chunks_collected:number;canonical_primary_replaced:false;physical_secure_erasure:false};
function validateBulkMigrationReceipt(v:BulkMigrationReceipt):BulkMigrationReceipt{
  if(!v||!HASH.test(v.manifest)||!HASH.test(v.sha256)||!integer(v.bytes,4*1024*1024)||v.bytes<1
    ||!integer(v.chunks,512)||v.chunks<1||v.layout!=='content_defined_v1'||v.readback_verified!==true
    ||typeof v.switched!=='boolean'||typeof v.replayed!=='boolean'||v.switched===v.replayed
    ||!integer(v.garbage_remaining)||!integer(v.unreferenced_chunks_collected,128)
    ||v.canonical_primary_replaced!==false||v.physical_secure_erasure!==false) invalid('Invalid archive migration receipt.');
  return v;
}
export async function listBulkMigrationCandidates(after?:string,limit=32,signal?:AbortSignal){
  if(after!==undefined&&!ID.test(after)||!integer(limit,64)||limit<1)invalid('Invalid archive migration cursor.');
  const v=await read(api.get<{candidates:BulkMigrationCandidate[];next_cursor:string|null;source_authorized:false;network_executed:false}>(
      ROOT+'/companion/bulk-migration-candidates?limit='+limit+(after?'&after='+encodeURIComponent(after):''),options(signal)),
    getAuthToken(),'Archive migration inventory unavailable.');
  if(!v||v.source_authorized!==false||v.network_executed!==false||!Array.isArray(v.candidates)||v.candidates.length>limit
    ||v.next_cursor!==null&&!ID.test(v.next_cursor)||v.candidates.some(x=>!x||!ID.test(x.session_id)||!HASH.test(x.manifest)
       ||!integer(x.version)||x.version<1||!integer(x.expected_bytes,4*1024*1024)||x.expected_bytes<1
       ||!Number.isFinite(x.expires_at)||x.physical_layout_verified!==false))invalid('Invalid archive migration inventory.');
  return v;
}
export async function migrateBulkArchive(id:string,body:CrawlCommand&{retention_acknowledged:true},signal?:AbortSignal){
  if(!ID.test(id)||body.retention_acknowledged!==true||!integer(body.expected_version)||body.expected_version<1)
    invalid('Explicit archive migration required.');
  const v=await read(api.post<{ok:true;session_id:string;version:number;migration:BulkMigrationReceipt;
    source_authorized:false;network_executed:false}>(ROOT+'/sessions/'+encodeURIComponent(id)+'/migrate-bulk-copy',body,options(signal)),
    getAuthToken(),'Archive migration held; replay the current exact copy.');
  if(!v||v.ok!==true||v.session_id!==id||v.version!==body.expected_version||v.source_authorized!==false||v.network_executed!==false)
    invalid('Archive migration identity differs.');
  validateBulkMigrationReceipt(v.migration);return v;
}
export async function compactColdPrimary(id:string,body:CrawlCommand&{acknowledged:true},signal?:AbortSignal){
  if(!ID.test(id)||body.acknowledged!==true||!integer(body.expected_version)||body.expected_version<1)
    invalid('Explicit dual-plane archive compaction required.');
  const v=await read(api.post<{session_id:string;version:number;network_executed:false;source_authorized:false;
    migration:{primary:BulkMigrationReceipt;backup:BulkMigrationReceipt;both_payloads_readback_verified:true;
       independent_readback_verified:true;qualification_digest:string;cross_store_atomic:false;
       canonical_primary_replaced:false;source_authorized:false}}>(ROOT+'/sessions/'+encodeURIComponent(id)+'/compact-cold-primary',
    body,options(signal)),getAuthToken(),'Dual-plane archive compaction held; reload current custody.');
  if(!v||v.session_id!==id||v.version!==body.expected_version||v.network_executed!==false||v.source_authorized!==false
    ||!v.migration||v.migration.both_payloads_readback_verified!==true||v.migration.independent_readback_verified!==true
    ||!HASH.test(v.migration.qualification_digest)||v.migration.cross_store_atomic!==false
    ||v.migration.canonical_primary_replaced!==false||v.migration.source_authorized!==false)
    invalid('Invalid independent archive compaction receipt.');
  const first=validateBulkMigrationReceipt(v.migration.primary),second=validateBulkMigrationReceipt(v.migration.backup);
  if(first.manifest!==second.manifest||first.sha256!==second.sha256||first.bytes!==second.bytes)
    invalid('Archive replica witnesses differ.');
  return v;
}
export async function migrateBulkArchiveBatch(sessions:(CrawlCommand&{session_id:string})[],retentionAcknowledged:true,signal?:AbortSignal){
  if(retentionAcknowledged!==true||!Array.isArray(sessions)||sessions.length<1||sessions.length>8
    ||new Set(sessions.map(x=>x.session_id)).size!==sessions.length||sessions.some(x=>!ID.test(x.session_id)
       ||!integer(x.expected_version)||x.expected_version<1||!x.idempotency_key))invalid('Explicit bounded archive migration batch required.');
  const v=await read(api.post<{outcomes:{session_id:string;state:'verified'|'held';result?:BulkMigrationReceipt;code?:string}[];
      verified:number;held:number;atomic_batch:false;source_authorized:false;network_executed:false}>(
      ROOT+'/companion/migrate-bulk-batch',{sessions,retention_acknowledged:true},options(signal)),
    getAuthToken(),'Batch migration not confirmed; replay the same current copies.');
  if(!v||v.atomic_batch!==false||v.source_authorized!==false||v.network_executed!==false||!Array.isArray(v.outcomes)
     ||v.outcomes.length!==sessions.length||!integer(v.verified,8)||!integer(v.held,8)||v.verified+v.held!==sessions.length
     ||v.outcomes.some((x,i)=>!x||x.session_id!==sessions[i].session_id||!['verified','held'].includes(x.state)))
    invalid('Invalid batch migration outcome.');
  for(const x of v.outcomes){if(x.state==='verified'){if(!x.result)invalid('Migration receipt missing.');validateBulkMigrationReceipt(x.result);}else if(!x.code)invalid('Migration hold reason missing.');}
  return v;
}
export type ArchiveIntelligenceReport={
  snapshot_digest:string;grant_digest:string;qualified_sources:number;unique_texts:number;
  logical_utf8_bytes:number;unique_text_utf8_bytes:number;exact_duplicate_bytes_estimate:number;
  unique_chunk_bytes_estimate:number;shared_chunk_count:number;chunk_window_truncated:boolean;
  groups:{text_digest:string;source_ids:string[];text_bytes:number;copies:number;valid_until:number}[];
  similarity_pairs:{left:string;right:string;similarity:number;classification:'near_duplicate'|'related'}[];
  pair_window_truncated:boolean;history_only:true;network_authorized:false;training_permission:false;
  physical_storage_modified:false;receipt:string;
};
export async function getArchiveIntelligence(sessionId:string,compareSession?:string,signal?:AbortSignal){
  if(!ID.test(sessionId)||compareSession!==undefined&&(!ID.test(compareSession)||compareSession===sessionId))
    invalid('Invalid archive analysis session.');
  const v=await read(api.get<{schema:'skeleton.dragon.archive-intelligence.v1';sessions:string[];reports:ArchiveIntelligenceReport[];
      revision_comparison:null|{matched_locator_families:number;left_only:number;right_only:number;comparisons:unknown[]};
      history_only:true;source_text_returned:false;physical_storage_modified:false;network_authorized:false;
      training_permission:false;receipt:string}>(ROOT+'/companion/archive-intelligence?session_id='+encodeURIComponent(sessionId)
      +(compareSession?'&compare_session='+encodeURIComponent(compareSession):''),options(signal)),getAuthToken(),'Archive intelligence unavailable.');
  if(!v||v.schema!=='skeleton.dragon.archive-intelligence.v1'||v.history_only!==true||v.source_text_returned!==false
    ||v.physical_storage_modified!==false||v.network_authorized!==false||v.training_permission!==false||!HASH.test(v.receipt)
    ||!Array.isArray(v.sessions)||v.sessions.join(',')!==[sessionId,...(compareSession?[compareSession]:[])].join(',')
    ||!Array.isArray(v.reports)||v.reports.length!==v.sessions.length
    ||v.reports.some(p=>!p||!HASH.test(p.snapshot_digest)||!HASH.test(p.grant_digest)||!HASH.test(p.receipt)
       ||p.history_only!==true||p.network_authorized!==false||p.training_permission!==false||p.physical_storage_modified!==false
       ||!integer(p.qualified_sources,64)||!integer(p.unique_texts,p.qualified_sources)||!integer(p.logical_utf8_bytes,64*96000)
       ||!integer(p.unique_text_utf8_bytes,p.logical_utf8_bytes)||p.exact_duplicate_bytes_estimate!==p.logical_utf8_bytes-p.unique_text_utf8_bytes
       ||!Array.isArray(p.groups)||p.groups.length!==p.unique_texts
       ||p.groups.some(g=>!g||!HASH.test(g.text_digest)||!Array.isArray(g.source_ids)||g.source_ids.some(id=>!HASH.test(id))
          ||g.copies!==g.source_ids.length||!integer(g.text_bytes,96000)||!Number.isFinite(g.valid_until))
       ||!Array.isArray(p.similarity_pairs)||p.similarity_pairs.length>32
       ||p.similarity_pairs.some(x=>!x||!HASH.test(x.left)||!HASH.test(x.right)||!navigationUnit(x.similarity))))
    invalid('Archive analysis witness invalid.');
  return v;
}
export type NavigationPortfolioTarget = {id:string;url:string;host:string;score:number;votes:number;
  features:{exact:number;concept:number;trigram:number;lineage:number;score:number};
  jeeves:number;dragon:number;joint:number;lineage_support:number;reviewed:false;network_authorized:false};
export type NavigationPortfolio = {targets:NavigationPortfolioTarget[];distinct_hosts:number;covered_concepts:number;
  index_backfill_pending:boolean;lane_truncated:boolean;network_authorized:false;selection_is_advisory:true;receipt:string};
export async function getNavigationPortfolio(query:string,limit=12,signal?:AbortSignal):Promise<NavigationPortfolio> {
  if(!query.trim()||query.length>512||!integer(limit,24)||limit<1) invalid('Invalid navigation research objective.');
  const v=await read(api.get<NavigationPortfolio>(ROOT+'/navigation/federation/portfolio?query='+encodeURIComponent(query)
    +'&limit='+limit,options(signal)),getAuthToken(),'Navigation portfolio unavailable.');
  if(!v||v.network_authorized!==false||v.selection_is_advisory!==true||!HASH.test(v.receipt)
    ||!Array.isArray(v.targets)||v.targets.length>limit||!integer(v.distinct_hosts,v.targets.length)
    ||!integer(v.covered_concepts,128)||typeof v.index_backfill_pending!=='boolean'||typeof v.lane_truncated!=='boolean'
    ||v.targets.some(t=>!t||!HASH.test(t.id)||!navigationUrl(t.url)||t.network_authorized!==false||t.reviewed!==false
      ||!t.features||[t.score,t.jeeves,t.dragon,t.lineage_support,t.features.score].some(n=>!Number.isFinite(n)||n<0||n>1)
      ||!Number.isFinite(t.joint)||t.joint<-.2||t.joint>1)) invalid('Invalid advisory navigation portfolio.');
  return v;
}
export type NavigationNeighbor = {id:string;url:string;host:string;relation:string;supporting_grants:number;network_authorized:false};
export async function getNavigationTopology(target:string,direction:'children'|'parents',after?:string,signal?:AbortSignal) {
  if(!HASH.test(target)||!['children','parents'].includes(direction)||after&&!HASH.test(after)) invalid('Invalid navigation topology cursor.');
  const v=await read(api.get<{neighbors:NavigationNeighbor[];next_cursor:string|null;
    network_authorized:false;historical_topology_complete:false}>(ROOT+'/navigation/federation/targets/'+target
      +'/topology?direction='+direction+(after?'&after='+after:''),options(signal)),getAuthToken(),'Navigation topology unavailable.');
  if(!v||v.network_authorized!==false||v.historical_topology_complete!==false||!Array.isArray(v.neighbors)
    ||v.neighbors.length>32||v.neighbors.some(n=>!n||!HASH.test(n.id)||!navigationUrl(n.url)
      ||!integer(n.supporting_grants)||n.supporting_grants<1||n.network_authorized!==false)
    ||v.next_cursor!==null&&!HASH.test(v.next_cursor)) invalid('Invalid navigation topology.');
  return v;
}
export async function retainNavigationBatch(body:{sessions:{session_id:string;expected_snapshot_digest:string}[];
    rights_reference:string;retention_seconds:number;acknowledged:true},signal?:AbortSignal) {
  if(body.acknowledged!==true||!Array.isArray(body.sessions)||body.sessions.length<1||body.sessions.length>16
    ||body.sessions.some(x=>!ID.test(x.session_id)||!HASH.test(x.expected_snapshot_digest))
    ||new Set(body.sessions.map(x=>x.session_id)).size!==body.sessions.length
    ||!integer(body.retention_seconds,315360000)||body.retention_seconds<900||!body.rights_reference.trim())
    invalid('Invalid independent metadata retention batch.');
  const v=await read(api.post<{outcomes:{session_id:string;state:'held'|'published';code?:string;receipt?:unknown}[];
    published:number;held:number;atomic_batch:false;network_authorized:false}>(ROOT+'/navigation/federation/batch',
      body,options(signal)),getAuthToken(),'Batch publication not confirmed; retry the same checkpoint identities.');
  if(!v||v.network_authorized!==false||v.atomic_batch!==false||!Array.isArray(v.outcomes)||v.outcomes.length!==body.sessions.length
    ||!integer(v.published,16)||!integer(v.held,16)||v.published+v.held!==v.outcomes.length
    ||v.outcomes.some((x,i)=>!x||x.session_id!==body.sessions[i].session_id||!['held','published'].includes(x.state)))
    invalid('Invalid navigation batch receipt.');
  return v;
}
export async function getNavigationInventory(id: string, cursor?: { snapshot_digest: string; after: number },
  signal?: AbortSignal): Promise<NavigationInventory> {
  if (cursor && (!HASH.test(cursor.snapshot_digest) || !integer(cursor.after, 1000000000)))
    invalid('Invalid navigation checkpoint cursor.');
  const url = ROOT + '/sessions/' + identifier(id) + '/navigation?limit=32'
    + (cursor ? '&snapshot_digest=' + cursor.snapshot_digest + '&after=' + cursor.after : '');
  const value = await read(api.get<NavigationInventory>(url, options(signal)), getAuthToken(),
    'The navigation inventory could not be loaded.');
  if (!value || value.ok !== true || value.session_id !== id || value.read_only !== true
    || value.network_authorized !== false || !HASH.test(value.snapshot_digest)
    || (cursor && value.snapshot_digest !== cursor.snapshot_digest)
    || !validNavigationSummary(value.summary) || !Array.isArray(value.targets)
    || value.targets.length > 32 || JSON.stringify(value).length > 512 * 1024)
    invalid('The crawler navigation page is invalid.');
  let ordinal = cursor?.after ?? 0;
  for (const target of value.targets) {
    if (!target || !navigationUrl(target.url) || !integer(target.ordinal, 1000000000)
      || target.ordinal <= ordinal || !integer(target.depth, 4)
      || (target.parent_url !== null && !navigationUrl(target.parent_url))
      || !Array.isArray(target.parents) || target.parents.length > 4 || !target.parents.every(navigationUrl)
      || !NAVIGATION_KINDS.has(target.kind) || !Array.isArray(target.relations)
      || !target.relations.length || target.relations.length > NAVIGATION_KINDS.size
      || !target.relations.every(kind => NAVIGATION_KINDS.has(kind))
      || !target.relations.includes(target.kind) || !integer(target.observations, 1000000000)
      || target.observations < 1 || typeof target.pending !== 'boolean'
      || !['visited', 'active', 'depth_held', 'pending', 'observed_only'].includes(target.phase)
      || target.navigation_authorized !== false) invalid('The crawler returned an invalid navigation target.');
    ordinal = target.ordinal;
  }
  if (value.next_after !== null && (!value.targets.length || value.next_after !== ordinal))
    invalid('The crawler returned an invalid navigation cursor.');
  return value;
}
export const PUBLISHER_INTAKE_METHODS = ['public_api', 'publisher_feed', 'open_dataset_manifest', 'licensed_public_export'] as const;
export type PublisherIntakeMethod = typeof PUBLISHER_INTAKE_METHODS[number];
export type PublisherIntake = {
  idempotency_key: string; endpoint: string; method: PublisherIntakeMethod;
  consent: true; rights_acknowledged: true; publisher_permission_acknowledged: true;
  independent_resource_acknowledged: true;
};
export async function createPublisherIntake(body: PublisherIntake, signal?: AbortSignal): Promise<CrawlSession> {
  let endpoint: URL;
  try { endpoint = new URL(body.endpoint); } catch {
    throw new ChatClientError('Enter one complete publisher-approved HTTPS resource.', { kind: 'validation' });
  }
  if (!PUBLISHER_INTAKE_METHODS.includes(body.method) || endpoint.protocol !== 'https:'
    || endpoint.username || endpoint.password || endpoint.search || endpoint.hash || endpoint.port
    || body.endpoint.length > 2048 || endpoint.href !== body.endpoint
    || body.consent !== true || body.rights_acknowledged !== true
    || body.publisher_permission_acknowledged !== true || body.independent_resource_acknowledged !== true) {
    throw new ChatClientError('Confirm separate access permission for a canonical public HTTPS resource without credentials or query parameters.', { kind: 'validation' });
  }
  const value = await read(api.post<{session: CrawlSession}>(ROOT + '/publisher-intake', body, options(signal)), getAuthToken(), 'Publisher intake was not confirmed. Retry the same request to check its outcome.');
  return session(value.session);
}
export async function createCrawl(body: CrawlCreate, signal?: AbortSignal): Promise<CrawlSession> {
  if (body.frontier_strategy !== undefined && !['fifo', 'balanced', 'coverage', 'companion', 'companion_curiosity', 'companion_scholar', 'companion_guardian'].includes(body.frontier_strategy)) throw new ChatClientError('Choose a canonical bounded frontier scheduling strategy.', { kind: 'validation' });
  if (body.discover_sitemaps !== undefined && typeof body.discover_sitemaps !== 'boolean') throw new ChatClientError('Sitemap discovery must be explicitly enabled or disabled.', { kind: 'validation' });
  if (body.seeds.length < 1 || body.seeds.length > 16 || new Set(body.seeds).size !== body.seeds.length || body.consent !== true || body.rights_acknowledged !== true) throw new ChatClientError('Provide distinct seed URLs and acknowledge capture rights.', { kind: 'validation' });
  for (const seed of body.seeds) { let url: URL; try { url = new URL(seed); } catch { throw new ChatClientError('Enter complete http or https seed URLs, one per line.', { kind: 'validation' }); } if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || seed.length > 2048) throw new ChatClientError('Use http or https URLs without embedded credentials.', { kind: 'validation' }); }
  const value = await read(api.post<{ session: CrawlSession }>(ROOT + '/sessions', body, options(signal)), getAuthToken(), 'The crawl could not be created. Retry the same request to check its outcome.'); return session(value.session);
}
export async function runCrawl(id: string, body: CrawlCommand & { max_steps: number; navigation_advice?: NavigationAdvice }, signal?: AbortSignal): Promise<CrawlSession> {
  const value = await read(api.post<{ session: CrawlSession }>(ROOT + '/sessions/' + identifier(id) + '/run', body, options(signal)), getAuthToken(), 'The bounded slice did not return a confirmed result. Refresh or retry the same request.'); return session(value.session, id);
}
export async function controlCrawl(id: string, body: CrawlCommand & { action: 'pause' | 'resume' | 'cancel' }, signal?: AbortSignal): Promise<CrawlSession> {
  const value = await read(api.post<{ session: CrawlSession }>(ROOT + '/sessions/' + identifier(id) + '/control', body, options(signal)), getAuthToken(), 'The crawler control was not confirmed. Refresh before another command.'); return session(value.session, id);
}
export async function listCrawlSources(id: string, cursor?: string, signal?: AbortSignal): Promise<{ sources: CapturedSource[]; next_cursor: string | null }> {
  const value = await read(api.get<{ sources: CapturedSource[]; next_cursor: string | null }>(ROOT + '/sessions/' + identifier(id) + '/sources?limit=32' + (cursor ? '&cursor=' + identifier(cursor) : ''), options(signal)), getAuthToken(), 'Captured sources could not be loaded.');
  if (!Array.isArray(value.sources) || value.sources.length > 32 || value.next_cursor !== null && !ID.test(value.next_cursor)) invalid('The source page is invalid.'); value.sources.forEach(row => source(row)); return value;
}
export async function getCrawlSource(id: string, sourceId: string, signal?: AbortSignal): Promise<CapturedSource> {
  const value = await read(api.get<{ source: CapturedSource }>(ROOT + '/sessions/' + identifier(id) + '/sources/' + identifier(sourceId), options(signal)), getAuthToken(), 'The captured source could not be read.'); return source(value.source, sourceId);
}
export async function configureCrawlSourceUse(id: string, sourceId: string, body: CrawlCommand & { enabled: boolean; max_age_seconds: number }, signal?: AbortSignal): Promise<{ session: CrawlSession; source: CapturedSource }> {
  if (!HASH.test(sourceId) || !integer(body.expected_version) || body.expected_version < 1 || typeof body.enabled !== 'boolean'
    || !integer(body.max_age_seconds, 86400) || body.max_age_seconds < 60 || typeof body.idempotency_key !== 'string'
    || !body.idempotency_key || body.idempotency_key !== body.idempotency_key.trim() || body.idempotency_key.length > 128) {
    throw new ChatClientError('Choose a current source and a capture-age limit between 60 and 86,400 seconds.', { kind: 'validation' });
  }
  const value = await read(api.post<{ session: CrawlSession; source: CapturedSource }>(ROOT + '/sessions/' + identifier(id) + '/sources/' + identifier(sourceId) + '/use', body, options(signal)), getAuthToken(), 'The source-use change was not confirmed. Retry the same saved change or refresh current settings.');
  session(value.session, id); source(value.source, sourceId);
  if (!value.source.use_policy || !value.source.freshness || value.source.text !== undefined) invalid('The source-use change returned an incomplete receipt.');
  return value;
}
export async function exportCrawlSource(id: string, sourceId: string, format: 'json' | 'markdown', signal?: AbortSignal): Promise<SourceExport> {
  const token = getAuthToken();
  const value = await read(api.get<SourceExport>(ROOT + '/sessions/' + identifier(id) + '/sources/' + identifier(sourceId) + '/export?format=' + format, options(signal)), getAuthToken(), 'The source export could not be authorized.');
  if (!value || value.session_id !== id || value.source_id !== sourceId || typeof value.content !== 'string' || new TextEncoder().encode(value.content).byteLength > 2 * 1024 * 1024 || !HASH.test(value.content_digest) || typeof value.filename !== 'string' || !['application/json', 'text/markdown'].includes(value.media_type.split(';')[0].trim())) invalid('The source export is invalid.');
  if (await digestStringAsync(CryptoDigestAlgorithm.SHA256, value.content) !== value.content_digest) invalid('The source export content changed.'); if (signal?.aborted || token !== getAuthToken()) throw new ChatClientError('Your account changed or the export was detached.', { kind: 'authorization' }); return value;
}

export type CrawlEvent = { sequence: number; kind: string; at: number; url?: string | null; source_id?: string | null; reason?: string | null };
export async function getCrawlEvents(id: string, signal?: AbortSignal): Promise<{ events: CrawlEvent[]; history_truncated: boolean }> {
  const value = await read(api.get<{ session_id: string; events: CrawlEvent[]; history_truncated: boolean }>(ROOT + '/sessions/' + identifier(id) + '/events?after_sequence=0&limit=64', options(signal)), getAuthToken(), 'Crawler event history could not be loaded.');
  if (value.session_id !== id || !Array.isArray(value.events) || value.events.length > 64 || typeof value.history_truncated !== 'boolean') invalid('The crawler event page is invalid.');
  let previous = 0;
  for (const event of value.events) { if (!event || !integer(event.sequence) || event.sequence <= previous || typeof event.kind !== 'string' || event.kind.length > 128 || typeof event.at !== 'number' || !Number.isFinite(event.at) || event.url != null && (typeof event.url !== 'string' || event.url.length > 4096) || event.reason != null && (typeof event.reason !== 'string' || event.reason.length > 4096)) invalid('The crawler event sequence is invalid.'); previous = event.sequence; }
  return value;
}
export async function eraseCrawl(id: string, body: CrawlCommand, signal?: AbortSignal): Promise<void> {
  const token = getAuthToken(); const current = new AbortController(); const stop = () => current.abort(); signal?.addEventListener('abort', stop, { once: true }); const timer = setTimeout(stop, 30000);
  try {
    if (signal?.aborted) throw new ChatClientError('Request detached.', { kind: 'cancelled' });
    const response = await fetch(API_BASE + ROOT + '/sessions/' + identifier(id), { method: 'DELETE', headers: authHeaders({ 'Content-Type': 'application/json' }), body: JSON.stringify(body), signal: current.signal });
    if (token !== getAuthToken()) throw new ChatClientError('Your account changed.', { kind: 'authorization' });
    const text = await response.text(); if (text.length > 65536) invalid('The crawler deletion receipt exceeds its bound.');
    let value: { session_id?: string; status?: string; version?: number; detail?: unknown }; try { value = JSON.parse(text); } catch { invalid('The crawler deletion receipt is invalid.'); }
    if (!response.ok) throw chatApiError({ ok: false, status: response.status, data: value, error: null, rid: response.headers.get('x-request-id') }, 'Source erasure was not confirmed. Retry the same command.');
    if (value.session_id !== id || value.status !== 'deleted' || !integer(value.version)) invalid('The crawler deletion receipt belongs to another session.');
  } finally { clearTimeout(timer); signal?.removeEventListener('abort', stop); }
}


export type CrawlTextPage = {
  session_id: string; source_id: string; version: number; offset: number; end: number; total_chars: number;
  text: string; next_offset: number | null; content_digest: string; chunk_digest: string;
  offset_unit: 'unicode_code_points'; source_classification: string;
};
export type CrawlSearchHit = {
  source_id: string; canonical_url: string; title: string; content_hash: string; preserved_text_hash: string;
  passage_hash: string; start: number; end: number; text: string; lexical_score: number;
  review_state: string; authority: string; instruction_risks: { risk: string; start: number; end: number; detail: string }[];
};
export type CrawlSearchPage = { schema_version: string; run_id: string; session_id: string; version: number; query: string; hits: CrawlSearchHit[]; evidence_digest: string };
export async function authorizeCrawlAutomation(id: string, body: CrawlCommand & { enabled: boolean; max_slices: number; max_seconds: number; navigation_discourse?: boolean }, signal?: AbortSignal): Promise<CrawlSession> {
  if (typeof body.enabled !== 'boolean' || !integer(body.max_slices, 64) || body.max_slices < 1 || !integer(body.max_seconds, 3600) || body.max_seconds < 15) throw new ChatClientError('Choose 1–64 bounded slices and 15–3,600 seconds.', { kind: 'validation' });
  const value = await read(api.post<{ session: CrawlSession }>(ROOT + '/sessions/' + identifier(id) + '/automation', body, options(signal)), getAuthToken(), 'Automatic capture was not confirmed. Retry the same saved request or refresh its state.');
  return session(value.session, id);
}
export async function getCrawlText(id: string, sourceId: string, offset = 0, digest?: string, signal?: AbortSignal): Promise<CrawlTextPage> {
  if (!integer(offset, 2097152) || digest !== undefined && !HASH.test(digest)) invalid('The source text cursor is invalid.');
  const token = getAuthToken();
  const value = await read(api.get<CrawlTextPage>(ROOT + '/sessions/' + identifier(id) + '/sources/' + identifier(sourceId) + '/text?offset=' + offset + '&max_chars=8000' + (digest ? '&expected_content_digest=' + digest : ''), options(signal)), token, 'The preserved source passage could not be read.');
  if (!value || value.session_id !== id || value.source_id !== sourceId || !integer(value.version) || value.offset !== offset || value.offset_unit !== 'unicode_code_points'
    || !integer(value.end, 2097152) || !integer(value.total_chars, 2097152) || value.end < offset || value.end > value.total_chars
    || typeof value.text !== 'string' || Array.from(value.text).length !== value.end - offset || new TextEncoder().encode(value.text).byteLength > 64000
    || !HASH.test(value.content_digest) || digest && value.content_digest !== digest || !HASH.test(value.chunk_digest)
    || value.next_offset !== null && (value.next_offset !== value.end || value.end >= value.total_chars)
    || value.next_offset === null && value.end !== value.total_chars || typeof value.source_classification !== 'string') invalid('The preserved source text page is invalid.');
  const measured = await digestStringAsync(CryptoDigestAlgorithm.SHA256, value.text);
  if (signal?.aborted || token !== getAuthToken()) throw new ChatClientError('The source read was detached or your account changed.', { kind: 'authorization' });
  if (measured !== value.chunk_digest) invalid('The preserved source text bytes changed.');
  return value;
}
export async function searchCrawlSources(id: string, query: string, signal?: AbortSignal): Promise<CrawlSearchPage> {
  const text = query.trim(); if (!text || text.length > 512) throw new ChatClientError('Enter a source query of 1–512 characters.', { kind: 'validation' });
  const token = getAuthToken();
  const value = await read(api.get<CrawlSearchPage>(ROOT + '/sessions/' + identifier(id) + '/search?query=' + encodeURIComponent(text) + '&limit=8', options(signal)), getAuthToken(), 'The captured source search could not be read.');
  if (!value || value.session_id !== id || value.query !== text || typeof value.schema_version !== 'string' || !integer(value.version) || !HASH.test(value.evidence_digest) || !Array.isArray(value.hits) || value.hits.length > 8) invalid('The source search returned an invalid scope.');
  for (const hit of value.hits) {
    if (!hit || !ID.test(hit.source_id) || typeof hit.canonical_url !== 'string' || hit.canonical_url.length > 4096 || typeof hit.title !== 'string'
      || !HASH.test(hit.content_hash) || !HASH.test(hit.preserved_text_hash) || !HASH.test(hit.passage_hash) || !integer(hit.start, 2097152) || !integer(hit.end, 2097152)
      || hit.end <= hit.start || typeof hit.text !== 'string' || Array.from(hit.text).length !== hit.end - hit.start || hit.text.length > 16000
      || typeof hit.lexical_score !== 'number' || !Number.isFinite(hit.lexical_score) || typeof hit.review_state !== 'string' || typeof hit.authority !== 'string'
      || !Array.isArray(hit.instruction_risks) || hit.instruction_risks.length > 32 || hit.instruction_risks.some(risk => !risk || typeof risk.risk !== 'string' || risk.risk.length > 256 || typeof risk.detail !== 'string' || risk.detail.length > 4096 || !integer(risk.start, 16000) || !integer(risk.end, 16000) || risk.end < risk.start)) invalid('A source search passage is invalid.');
    if (await digestStringAsync(CryptoDigestAlgorithm.SHA256, hit.text) !== hit.passage_hash) invalid('The captured search passage bytes changed.');
    if (signal?.aborted || token !== getAuthToken()) throw new ChatClientError('The source search was detached or your account changed.', { kind: 'authorization' });
  }
  return value;
}


// Dragon Atlas is a read-only, owner-scoped research inspection. Its
// hashes are integrity identifiers, never reviewed-knowledge authorization.
export type CrawlAtlasObjective = {
  objective_id: string;
  question: string;
  dimension: 'fact' | 'method' | 'timeline' | 'source' | 'counterexample' | 'implementation';
  stage: 'discovery' | 'collection' | 'verification' | 'review';
  priority: number;
  minimum_reviewable_passages: number;
  minimum_attested_groups: number;
  max_source_age_seconds: number;
  required_terms: string[];
  blocked_terms: string[];
};
export type CrawlAtlasEffort = {
  task_type: 'source_policy' | 'passage_integrity' | 'source_provenance' |
    'claim_contradiction' | 'claim_corroboration' | 'objective_gap' | 'human_fact_review';
  estimated_minutes: number;
  estimate_basis: 'operator_estimate';
};
export type CrawlAtlasRequest = {
  objectives: CrawlAtlasObjective[];
  retrieval_mode: 'fusion' | 'lexical_bm25';
  review_effort?: CrawlAtlasEffort[];
  review_budget_minutes?: number;
};
export type CrawlAtlasStage = {
  ordinal: number; name: string; receipt_digest: string; chain_digest: string;
};
export type CrawlAtlasReviewTask = {
  task_id: string; type: string; objective_id: string | null;
  source_id: string | null; priority: number; predecessors: string[];
  current_status: 'pending_human_review'; automatically_approvable: false;
};
export type CrawlPilotQualification = {
  schema_version: 'skeleton.dragon.campaign_pilot_qualification.v1';
  atlas_digest: string; snapshot_digest: string; source_policy_digest: string;
  run_sequence: number; pilot_status: 'ready_for_human_review' | 'held_for_repair';
  pilot_check_count: number;
  checks: { code: string; status: 'qualified' | 'held'; next_action: string | null }[];
  blocked_checks: string[]; operator_actions: string[];
  external_release_checks: { code: string; status: 'not_qualified' }[];
  source_only: true; read_only: true; human_review_required: true;
  network_used: false; model_invoked: false; source_text_included: false;
  training_authorized: false; publication_authorized: false; release_authorized: false;
  release_status: 'held_until_independent_exact_head_and_device_evidence';
  recheck_mongo_authority_before_any_followup: true; qualification_digest: string;
};
export type CrawlAtlasReport = {
  schema_version: 'skeleton.dragon.campaign_atlas_dashboard.v1';
  session_id: string; run_id: string; run_sequence: number;
  snapshot_digest: string; mandate_digest: string; atlas_digest: string;
  issued_at: number; dashboard_digest: string; stages: CrawlAtlasStage[];
  source_policy: {
    digest: string; sources_seen: number; included_source_count: number;
    excluded_source_count: number; complete_current_policy_required: true;
  };
  objectives: {
    objective_id: string; dimension: string; stage: string; priority: number;
  }[];
  query_lattice: { digest: string; queries: number; source_authority: string };
  retrieval: {
    digest: string; mode: 'fusion' | 'lexical_bm25';
    candidate_passages: number; retained_hits: number; distinct_hosts: number;
    evidence: {
      source_id: string; canonical_url: string; passage_hash: string;
      start: number; end: number; score: number;
      objective_ids: string[]; review_required: true;
    }[];
  };
  lexical_ranking: null | {
    ranking_digest: string; indexed_passages: number; scored_passages: number;
    scored_query_receipts: number; indexed_terms: number;
    ai_embedding_used: false; model_confidence_certified: false;
  };
  context: {
    digest: string; source_references: number; serialized_bytes: number;
    raw_source_text_redacted: true; fresh_policy_recheck_required: true;
  };
  numeric_signals: {
    report_digest: string; observed_quantities: number;
    cross_source_review_candidates: number; unit_families: string[];
    candidates: {
      objective_id: string; left_source_id: string; right_source_id: string;
      left_span_start: number; right_span_start: number;
      unit_family: string; normalized_left: string; normalized_right: string;
      relative_gap: number; human_review_required: true;
      factual_contradiction_established: false;
    }[];
    facts_verified: false;
  };
  temporal_signals: {
    report_digest: string; date_mentions: number; date_groups: number;
    groups: {
      objective_id: string; date: string; source_count: number;
      date_not_verified_as_remote_update: true;
    }[];
    remote_freshness_verified: false;
  };
  evidence_graph: {
    graph_digest: string; vertices: number; arcs: number; retained_passages: number;
    sources: number; held_sources: number; graph_is_factual_proof: false;
    objective_neighborhoods: {
      objective_id: string; source_count: number; passage_count: number;
      host_count: number; claim_count: number; independence_attested: false;
    }[];
  };
  review_operations: {
    agenda_digest: string; replay_digest: string; tasks_total: number;
    pending_tasks: number; blocked_tasks: number; ready_task_ids: string[];
    task_types: Record<string, number>;
    recommended_queue: CrawlAtlasReviewTask[];
    human_review_recorded: false; durable_review_mutations: false;
  };
  review_portfolio: null | {
    portfolio_digest: string; estimated_minutes: number; budget_minutes: number;
    selected_count: number; task_ids: string[]; persistence_performed: false;
    effort_is_observed: false;
  };
  jeeves_handoff: {
    manifest_digest: string; citation_count: number; task_count: number;
    body_excluded: true; network_called: false; dispatch_granted: false;
    requires_fresh_source_policy: true;
  };
  citation_manifest: {
    manifest_digest: string; exact_anchored_references: number;
    body_redacted: true; publication_permission: false;
  };
  forensics: {
    report_digest: string; frame_set_digest: string; atlas_digest: string;
    source_policy_digest: string; retrieval_digest: string;
    stages: CrawlAtlasStage[];
    selected_passages: number; selected_sources: number;
    security_held_passages: number; security_held_sources: number;
    active_content_held_sources: number; privacy_held_sources: number;
    cross_host_sentence_echoes: number; source_reuse_components: number;
    possible_polarity_collisions: number; low_information_passages: number;
    capture_age_held_sources: number; overlap_excess_characters: number;
    concentrated_objectives: string[]; review_tasks: number;
    provenance_held_sources: number; grounding_deficit_objectives: number;
    reference_reused_sources: number; consent_renewal_review_due: boolean;
    urgent_research_gaps: number; context_selected_utf8_bytes: number;
    context_budget_exceeded: boolean;
    extraction_held_sources: number; query_unsupported_objectives: number;
    origin_review_sources: number; selection_source_dominance_objectives: number;
    risk_ablated_objectives: number; script_coverage_review_objectives: number;
    critical_review_tasks: number;
    review_queue: {
      task_id: string; risk: 'critical' | 'high' | 'medium' | 'low';
      reason: string; source_ids: string[]; objective_ids: string[];
      model_may_decide: false;
    }[];
    source_bodies_redacted: true; human_review_required: true;
    publication_granted: false; training_permission: false;
    network_or_model_invoked: false;
  };
  operations: {
    report_digest: string; source_snapshot_digest: string; run_sequence: number;
    stages: CrawlAtlasStage[];
    retained_event_count: number; historical_events_incomplete: boolean;
    event_clock_integrity_review: boolean; pending_dispatch: boolean;
    uncertain_bytes: number; inspected_origins: number;
    unresolved_robots_origins: number; stale_robots_origins: number;
    observed_resource_samples: number; hypothetical_work_candidates: number;
    capacity_holds: string[]; critical_operator_steps: number;
    operator_runbook: {
      code: string; priority: 'critical' | 'high' | 'medium' | 'advisory';
      requires_backend_authority: true; automatically_executed: false;
    }[];
    physical_worker_fenced: false; mongo_checkpoint_confirmed: false;
    live_robots_permission_granted: false; network_executed: false;
    source_text_redacted: true; read_only: true;
    automatic_recovery_authorized: false;
  };
  evidence_family_stress: {
    stress_digest: string; policy_digest: string; retrieval_digest: string;
    robustness_digest: string; similarity_digest: string;
    selected_source_records: number; exact_content_families: number;
    possible_near_duplicate_clusters: number;
    flagged_objectives: string[]; objectives_with_similarity_holds: string[];
    objectives: {
      objective_id: string; target_attested_groups: number;
      selected_passages: number; selected_source_records: number;
      exact_content_families: number; possible_near_duplicate_clusters: number;
      possible_mirror_collapse: number; unscored_sources: number;
      worst_host_loss_clusters: number;
      hypothetical_target_shortfall: number; observed_hosts: number;
      concern: string; independent_evidence_attested: false;
    }[];
    limitations: string[];
    claim_correctness_verified: false;
    source_text_exported: false; model_or_network_invoked: false;
    human_review_required: true;
  };
  source_similarity: {
    audit_digest: string; retrieval_digest: string; policy_digest: string;
    selected_sources: number; compared_sources: number; held_sources: number;
    eligible_pairs: number; candidate_pairs: number;
    cross_host_candidates: number; skipped_oversize: number;
    skipped_short: number; jaccard_threshold: number;
    containment_threshold: number;
    candidate_leads: {
      left_host: string; right_host: string;
      jaccard: number; smaller_set_containment: number;
      length_ratio: number; relation: 'exact_content' | 'near_duplicate_review';
      cross_host: boolean;
      human_lineage_review_required: true; shared_origin_established: false;
    }[];
    clusters: {
      observed_hosts: string[]; source_count: number;
      direct_candidate_edges: number; all_pairs_verified: false;
      independent_origin_verified: false;
    }[];
    source_bodies_redacted: true; network_used: false;
    training_or_publication_granted: false; lineage_verified: false;
  };
  retrieval_robustness: {
    audit_digest: string; retrieval_digest: string;
    selected_passages: number; selected_sources: number; selected_hosts: number;
    distinct_content_families: number; cross_host_exact_copy_groups: number;
    exact_copy_families: {
      content_sha256: string; source_count: number; host_count: number;
      hosts: string[]; selected_passages: number;
      independence_verified: false;
    }[];
    flagged_objectives: string[];
    objectives: {
      objective_id: string; selected_passages: number;
      distinct_selected_sources: number; distinct_selected_hosts: number;
      distinct_content_families: number; cross_host_exact_content_reuse: boolean;
      dominant_host: string | null; dominant_host_fraction: number;
      remaining_passages_after_host_loss: number;
      remaining_sources_after_host_loss: number;
      risk: 'no_selected_evidence' | 'single_host' |
        'host_concentrated' | 'multiple_observed_hosts' |
        'same_content_on_multiple_hosts';
      independence_confirmed: false;
    }[];
    host_ablation: {
      removed_host: string; removed_selected_passages: number;
      surviving_selected_passages: number; surviving_unique_sources: number;
      surviving_distinct_content_families: number;
      objectives_without_evidence: string[];
      objectives_left_with_one_host: string[];
      reranking_executed: false;
    }[];
    objective_reuse: {
      left_objective_id: string; right_objective_id: string;
      shared_source_count: number; shared_host_count: number;
      shared_content_family_count: number;
      source_jaccard: number; independence_proven: false;
    }[];
    limitations: string[]; source_bodies_excluded: true;
    verified_independence: false; network_or_reranking_executed: false;
  };
  canonical_routes: {
    route_digest: string; node_count: number; committed_parent_arcs: number;
    components: number; unreachable_pending: number; unknown_parent_urls: number;
    host_load: {
      host: string; discovered_nodes: number; pending_urls: number;
      ready_urls: number; robots_status: string; observed_fairness_share: number;
    }[];
    network_authority: false;
  };
  slice_simulation: {
    simulation_digest: string; projected_request_slots: number;
    projected_byte_reserve: number; remaining_requests: number;
    remaining_bytes: number; steps: {
      url: string; action: 'robots_preflight_only' | 'page_fetch_candidate';
      host: string; ready_at: number; conservative_byte_cap: number;
      robots_preflight_required: boolean;
    }[];
    held_urls: [string, string][]; blockers: string[];
    physical_worker_authorized: false; network_committed: false;
    real_robots_admission_executed: false;
  };
  dispatch_recovery: {
    ledger_digest: string; retained_event_count: number;
    event_history_incomplete: boolean; pending_dispatch: boolean;
    uncertain_bytes: number; hosts: {
      host: string; fault_grade: string; dispatch_intents: number;
      retries: number; transport_failures: number; interrupted: number;
    }[];
    recovery_queue: {
      code: string; severity: string; supporting_sequences: number[];
      requires_operator_resolution: boolean; auto_execute: false;
    }[];
    physical_worker_join_confirmed: false; mongo_commit_confirmed: false;
    uncertain_bytes_refunded: false;
  };
  scorecard: {
    digest: string; dimensions: {
      name: string; numerator: number; denominator: number;
      ratio: number; grade: string; limitations: string[];
    }[];
    alerts: string[]; advisory_priority: number; decision: 'human_review_hold';
  };
  pilot_qualification?: CrawlPilotQualification;
  read_only: true; network_executed: false;
  publication_granted: false; training_permission: false; review_required: true;
};
const ATLAS_OBJECTIVE_ID = /^[a-z][a-z0-9_-]{2,63}$/;
const ATLAS_TERM = /^[a-z0-9_-]{2,48}$/;
const ATLAS_DIMENSIONS = new Set(['fact', 'method', 'timeline', 'source', 'counterexample', 'implementation']);
const ATLAS_STAGES = new Set(['discovery', 'collection', 'verification', 'review']);
const ATLAS_EFFORT_TYPES = new Set([
  'source_policy', 'passage_integrity', 'source_provenance',
  'claim_contradiction', 'claim_corroboration', 'objective_gap', 'human_fact_review',
]);
function safeAtlasRequest(request: CrawlAtlasRequest): void {
  if (!request || !Array.isArray(request.objectives) || request.objectives.length < 1
      || request.objectives.length > 8 || !['fusion', 'lexical_bm25'].includes(request.retrieval_mode)) {
    throw new ChatClientError('Choose a bounded objective and retrieval algorithm.', { kind: 'validation', retryable: false });
  }
  const seen = new Set<string>();
  for (const item of request.objectives) {
    if (!item || !ATLAS_OBJECTIVE_ID.test(item.objective_id) || seen.has(item.objective_id)
        || typeof item.question !== 'string' || item.question !== item.question.trim()
        || item.question.length < 3 || item.question.length > 512
        || !ATLAS_DIMENSIONS.has(item.dimension) || !ATLAS_STAGES.has(item.stage)
        || typeof item.priority !== 'number' || !Number.isFinite(item.priority)
        || item.priority < 0 || item.priority > 1
        || !Number.isSafeInteger(item.minimum_reviewable_passages) || item.minimum_reviewable_passages < 1
        || item.minimum_reviewable_passages > 32
        || !Number.isSafeInteger(item.minimum_attested_groups) || item.minimum_attested_groups < 1
        || item.minimum_attested_groups > 16
        || !Number.isSafeInteger(item.max_source_age_seconds) || item.max_source_age_seconds < 60
        || item.max_source_age_seconds > 86400
        || !Array.isArray(item.required_terms) || item.required_terms.length > 16
        || !Array.isArray(item.blocked_terms) || item.blocked_terms.length > 16
        || [...item.required_terms, ...item.blocked_terms].some(term => !ATLAS_TERM.test(term))
        || item.required_terms.some(term => item.blocked_terms.includes(term))
        || new Set(item.required_terms).size !== item.required_terms.length
        || new Set(item.blocked_terms).size !== item.blocked_terms.length) {
      throw new ChatClientError('Research goals need valid bounded questions, terms and targets.', { kind: 'validation', retryable: false });
    }
    seen.add(item.objective_id);
  }
  if (request.review_effort) {
    if (!Array.isArray(request.review_effort) || request.review_effort.length > 7
        || new Set(request.review_effort.map(row => row.task_type)).size !== request.review_effort.length
        || request.review_effort.some(row => !ATLAS_EFFORT_TYPES.has(row.task_type)
          || row.estimate_basis !== 'operator_estimate'
          || !Number.isSafeInteger(row.estimated_minutes) || row.estimated_minutes < 1
          || row.estimated_minutes > 180)) {
      throw new ChatClientError('Use explicit finite review-effort estimates.', { kind: 'validation', retryable: false });
    }
  }
  if (request.review_budget_minutes !== undefined && (!integer(request.review_budget_minutes, 1440)
      || request.review_budget_minutes < 1)) {
    throw new ChatClientError('Choose a finite human-review time budget.', { kind: 'validation', retryable: false });
  }
}
function checkedPilotQualification(value: CrawlPilotQualification, atlas: CrawlAtlasReport): boolean {
  if (!value || value.schema_version !== 'skeleton.dragon.campaign_pilot_qualification.v1'
    || value.atlas_digest !== atlas.atlas_digest
    || value.snapshot_digest !== atlas.snapshot_digest
    || value.source_policy_digest !== atlas.source_policy.digest
    || value.run_sequence !== atlas.run_sequence
    || !HASH.test(value.qualification_digest)
    || value.pilot_check_count !== 10
    || !Array.isArray(value.checks) || value.checks.length !== 10
    || !Array.isArray(value.blocked_checks) || value.blocked_checks.length > 10
    || !Array.isArray(value.operator_actions) || value.operator_actions.length > 10
    || !Array.isArray(value.external_release_checks) || value.external_release_checks.length !== 10
    || !value.external_release_checks.every(item =>
      item && /^[a-z0-9_]{3,90}$/.test(item.code) && item.status === 'not_qualified')
    || !value.checks.every(item =>
      item && /^[a-z0-9_]{3,90}$/.test(item.code)
      && (item.status === 'qualified' && item.next_action === null
        || item.status === 'held' && typeof item.next_action === 'string'
        && /^[a-z0-9_]{3,90}$/.test(item.next_action)))
    || new Set(value.checks.map(item => item.code)).size !== 10
    || value.blocked_checks.join('|')
      !== value.checks.filter(item => item.status === 'held').map(item => item.code).join('|')
    || value.operator_actions.join('|')
      !== value.checks.filter(item => item.status === 'held').map(item => item.next_action).join('|')
    || value.pilot_status !== (value.blocked_checks.length ? 'held_for_repair' : 'ready_for_human_review')
    || value.source_only !== true || value.read_only !== true
    || value.human_review_required !== true || value.network_used !== false
    || value.model_invoked !== false || value.source_text_included !== false
    || value.training_authorized !== false || value.publication_authorized !== false
    || value.release_authorized !== false
    || value.release_status !== 'held_until_independent_exact_head_and_device_evidence'
    || value.recheck_mongo_authority_before_any_followup !== true
    || JSON.stringify(value).length > 16000) return false;
  return true;
}
function checkedAtlasReport(value: CrawlAtlasReport, sessionId: string, requestedMode: CrawlAtlasRequest['retrieval_mode']): CrawlAtlasReport {
  if (!value || value.schema_version !== 'skeleton.dragon.campaign_atlas_dashboard.v1'
      || value.session_id !== sessionId || typeof value.run_id !== 'string'
      || !HASH.test(value.snapshot_digest) || !HASH.test(value.mandate_digest)
      || !HASH.test(value.atlas_digest) || !HASH.test(value.dashboard_digest)
      || !integer(value.run_sequence) || typeof value.issued_at !== 'number'
      || !Number.isFinite(value.issued_at) || value.retrieval?.mode !== requestedMode
      || !Array.isArray(value.stages) || value.stages.length !== 26
      || !value.stages.every((row, index) => row.ordinal === index
        && typeof row.name === 'string' && row.name.length < 100
        && HASH.test(row.receipt_digest) && HASH.test(row.chain_digest))
      || !value.source_policy || !HASH.test(value.source_policy.digest)
      || !integer(value.source_policy.sources_seen, 64)
      || !integer(value.source_policy.included_source_count, 64)
      || !integer(value.source_policy.excluded_source_count, 64)
      || value.source_policy.included_source_count + value.source_policy.excluded_source_count
         !== value.source_policy.sources_seen
      || !value.context?.raw_source_text_redacted
      || !value.context?.fresh_policy_recheck_required
      || !value.review_operations || value.review_operations.human_review_recorded !== false
      || value.review_operations.durable_review_mutations !== false
      || !Array.isArray(value.review_operations.recommended_queue)
      || value.review_operations.recommended_queue.length > 32
      || value.review_operations.recommended_queue.some(task =>
        !task || typeof task.task_id !== 'string' || task.automatically_approvable !== false
        || task.current_status !== 'pending_human_review')
      || !value.citation_manifest?.body_redacted
      || value.citation_manifest.publication_permission !== false
      || !value.jeeves_handoff?.body_excluded
      || value.jeeves_handoff.network_called !== false
      || value.jeeves_handoff.dispatch_granted !== false
      || !value.forensics
      || !HASH.test(value.forensics.report_digest)
      || !HASH.test(value.forensics.frame_set_digest)
      || value.forensics.atlas_digest !== value.atlas_digest
      || value.forensics.source_policy_digest !== value.source_policy.digest
      || value.forensics.retrieval_digest !== value.retrieval.digest
      || !Array.isArray(value.forensics.stages)
      || value.forensics.stages.length !== FORENSIC_STAGE_NAMES.length
      || value.forensics.stages.some((entry, index) =>
        !entry || entry.ordinal !== index
        || entry.name !== FORENSIC_STAGE_NAMES[index]
        || !HASH.test(entry.receipt_digest) || !HASH.test(entry.chain_digest))
      || !integer(value.forensics.selected_passages, 32)
      || !integer(value.forensics.selected_sources, 32)
      || !integer(value.forensics.security_held_passages, 32)
      || !integer(value.forensics.security_held_sources, 32)
      || !integer(value.forensics.active_content_held_sources, 32)
      || !integer(value.forensics.privacy_held_sources, 32)
      || !integer(value.forensics.cross_host_sentence_echoes, 256)
      || !integer(value.forensics.source_reuse_components, 32)
      || !integer(value.forensics.possible_polarity_collisions, 256)
      || !integer(value.forensics.low_information_passages, 32)
      || !integer(value.forensics.capture_age_held_sources, 32)
      || !integer(value.forensics.overlap_excess_characters, 48000)
      || !integer(value.forensics.provenance_held_sources, 32)
      || !integer(value.forensics.grounding_deficit_objectives, 32)
      || !integer(value.forensics.reference_reused_sources, 32)
      || typeof value.forensics.consent_renewal_review_due !== 'boolean'
      || !integer(value.forensics.urgent_research_gaps, 32)
      || !integer(value.forensics.context_selected_utf8_bytes, 196608)
      || typeof value.forensics.context_budget_exceeded !== 'boolean'
      || !integer(value.forensics.extraction_held_sources, 32)
      || !integer(value.forensics.query_unsupported_objectives, 32)
      || !integer(value.forensics.origin_review_sources, 32)
      || !integer(value.forensics.selection_source_dominance_objectives, 32)
      || !integer(value.forensics.risk_ablated_objectives, 32)
      || !integer(value.forensics.script_coverage_review_objectives, 32)
      || !integer(value.forensics.review_tasks, 256)
      || !integer(value.forensics.critical_review_tasks, 256)
      || value.forensics.critical_review_tasks > value.forensics.review_tasks
      || !Array.isArray(value.forensics.concentrated_objectives)
      || value.forensics.concentrated_objectives.length > 8
      || value.forensics.concentrated_objectives.some(x => typeof x !== 'string' || x.length > 64)
      || !Array.isArray(value.forensics.review_queue)
      || value.forensics.review_queue.length > 24
      || value.forensics.review_queue.length > value.forensics.review_tasks
      || value.forensics.review_queue.some(item =>
        !item || typeof item.task_id !== 'string' || item.task_id.length !== 24
        || !['critical', 'high', 'medium', 'low'].includes(item.risk)
        || typeof item.reason !== 'string' || item.reason.length > 128
        || !Array.isArray(item.source_ids) || item.source_ids.length > 32
        || item.source_ids.some(id => !HASH.test(id))
        || !Array.isArray(item.objective_ids) || item.objective_ids.length > 8
        || item.objective_ids.some(id => typeof id !== 'string' || id.length > 64)
        || item.model_may_decide !== false)
      || value.forensics.source_bodies_redacted !== true
      || value.forensics.human_review_required !== true
      || value.forensics.publication_granted !== false
      || value.forensics.training_permission !== false
      || value.forensics.network_or_model_invoked !== false
      || !value.operations
       || !HASH.test(value.operations.report_digest)
       || value.operations.source_snapshot_digest !== value.snapshot_digest
       || value.operations.run_sequence !== value.run_sequence
       || !Array.isArray(value.operations.stages)
       || value.operations.stages.length !== OPERATION_STAGE_NAMES.length
       || value.operations.stages.some((entry, index) =>
         !entry || entry.ordinal !== index || entry.name !== OPERATION_STAGE_NAMES[index]
         || !HASH.test(entry.receipt_digest) || !HASH.test(entry.chain_digest))
       || !integer(value.operations.retained_event_count, 64)
       || typeof value.operations.historical_events_incomplete !== 'boolean'
       || typeof value.operations.event_clock_integrity_review !== 'boolean'
       || typeof value.operations.pending_dispatch !== 'boolean'
       || !integer(value.operations.uncertain_bytes, 33_554_432)
       || !integer(value.operations.inspected_origins, 32)
       || !integer(value.operations.unresolved_robots_origins, 32)
       || !integer(value.operations.stale_robots_origins, 32)
       || !integer(value.operations.observed_resource_samples, 32)
       || !integer(value.operations.hypothetical_work_candidates, 4)
       || !Array.isArray(value.operations.capacity_holds)
       || value.operations.capacity_holds.length > 32
       || value.operations.capacity_holds.some(code => typeof code !== 'string'
         || !/^[a-z][a-z0-9_]{2,95}$/.test(code))
       || !integer(value.operations.critical_operator_steps, 48)
       || !Array.isArray(value.operations.operator_runbook)
       || value.operations.operator_runbook.length > 16
       || value.operations.operator_runbook.some(item =>
         !item || typeof item.code !== 'string'
         || !/^[a-z][a-z0-9_]{2,95}$/.test(item.code)
         || !['critical', 'high', 'medium', 'advisory'].includes(item.priority)
         || item.requires_backend_authority !== true
         || item.automatically_executed !== false)
       || value.operations.physical_worker_fenced !== false
       || value.operations.mongo_checkpoint_confirmed !== false
       || value.operations.live_robots_permission_granted !== false
       || value.operations.network_executed !== false
       || value.operations.source_text_redacted !== true
       || value.operations.read_only !== true
       || value.operations.automatic_recovery_authorized !== false
       || !value.evidence_family_stress
      || !HASH.test(value.evidence_family_stress.stress_digest)
      || value.evidence_family_stress.policy_digest !== value.source_policy.digest
      || value.evidence_family_stress.retrieval_digest !== value.retrieval.digest
      || value.evidence_family_stress.robustness_digest
         !== value.retrieval_robustness?.audit_digest
      || value.evidence_family_stress.similarity_digest
         !== value.source_similarity?.audit_digest
      || !integer(value.evidence_family_stress.selected_source_records, 32)
      || !integer(value.evidence_family_stress.exact_content_families, 32)
      || !integer(value.evidence_family_stress.possible_near_duplicate_clusters, 32)
      || value.evidence_family_stress.exact_content_families
         > value.evidence_family_stress.selected_source_records
      || value.evidence_family_stress.possible_near_duplicate_clusters
         > value.evidence_family_stress.exact_content_families
      || !Array.isArray(value.evidence_family_stress.objectives)
      || value.evidence_family_stress.objectives.length !== value.objectives?.length
      || value.evidence_family_stress.objectives.some(item =>
        !item || typeof item.objective_id !== 'string'
        || item.independent_evidence_attested !== false
        || !integer(item.selected_source_records, 32)
        || !integer(item.exact_content_families, 32)
        || !integer(item.possible_near_duplicate_clusters, 32)
        || !integer(item.unscored_sources, 32)
        || !integer(item.hypothetical_target_shortfall, 16)
        || !integer(item.target_attested_groups, 16)
        || item.target_attested_groups < 1
        || item.possible_near_duplicate_clusters > item.exact_content_families
        || item.exact_content_families > item.selected_source_records)
      || !Array.isArray(value.evidence_family_stress.flagged_objectives)
      || value.evidence_family_stress.flagged_objectives.length > 8
      || !Array.isArray(value.evidence_family_stress.objectives_with_similarity_holds)
      || value.evidence_family_stress.objectives_with_similarity_holds.length > 8
      || !Array.isArray(value.evidence_family_stress.limitations)
      || value.evidence_family_stress.limitations.length < 5
      || value.evidence_family_stress.claim_correctness_verified !== false
      || value.evidence_family_stress.source_text_exported !== false
      || value.evidence_family_stress.model_or_network_invoked !== false
      || value.evidence_family_stress.human_review_required !== true
      || !value.source_similarity || !HASH.test(value.source_similarity.audit_digest)
      || value.source_similarity.retrieval_digest !== value.retrieval.digest
      || value.source_similarity.policy_digest !== value.source_policy.digest
      || !integer(value.source_similarity.selected_sources, 32)
      || !integer(value.source_similarity.compared_sources, 32)
      || !integer(value.source_similarity.held_sources, 32)
      || value.source_similarity.compared_sources + value.source_similarity.held_sources
         !== value.source_similarity.selected_sources
      || !integer(value.source_similarity.eligible_pairs, 496)
      || !integer(value.source_similarity.candidate_pairs, 496)
      || value.source_similarity.candidate_pairs > value.source_similarity.eligible_pairs
      || !integer(value.source_similarity.cross_host_candidates, 496)
      || value.source_similarity.cross_host_candidates > value.source_similarity.candidate_pairs
      || !integer(value.source_similarity.skipped_oversize, 32)
      || !integer(value.source_similarity.skipped_short, 32)
      || !Number.isFinite(value.source_similarity.jaccard_threshold)
      || value.source_similarity.jaccard_threshold < 0.5
      || value.source_similarity.jaccard_threshold > 1
      || !Number.isFinite(value.source_similarity.containment_threshold)
      || value.source_similarity.containment_threshold < 0.5
      || value.source_similarity.containment_threshold > 1
      || value.source_similarity.source_bodies_redacted !== true
      || value.source_similarity.network_used !== false
      || value.source_similarity.training_or_publication_granted !== false
      || value.source_similarity.lineage_verified !== false
      || !Array.isArray(value.source_similarity.candidate_leads)
      || value.source_similarity.candidate_leads.length > 16
      || value.source_similarity.candidate_leads.length > value.source_similarity.candidate_pairs
      || value.source_similarity.candidate_leads.some(item =>
        !item || !['exact_content', 'near_duplicate_review'].includes(item.relation)
        || item.human_lineage_review_required !== true
        || item.shared_origin_established !== false
        || !Number.isFinite(item.jaccard) || item.jaccard < 0 || item.jaccard > 1
        || !Number.isFinite(item.smaller_set_containment)
        || item.smaller_set_containment < 0 || item.smaller_set_containment > 1
        || !Number.isFinite(item.length_ratio)
        || item.length_ratio < 0 || item.length_ratio > 1)
      || !Array.isArray(value.source_similarity.clusters)
      || value.source_similarity.clusters.length > 16
      || value.source_similarity.clusters.some(item =>
        !item || item.all_pairs_verified !== false
        || item.independent_origin_verified !== false
        || !integer(item.source_count, 32) || item.source_count < 2
        || !integer(item.direct_candidate_edges, 496)
        || !Array.isArray(item.observed_hosts) || item.observed_hosts.length > 32)
      || !value.retrieval_robustness
      || !HASH.test(value.retrieval_robustness.audit_digest)
      || value.retrieval_robustness.retrieval_digest !== value.retrieval.digest
      || !integer(value.retrieval_robustness.selected_passages, 32)
      || !integer(value.retrieval_robustness.selected_sources, 64)
      || !integer(value.retrieval_robustness.selected_hosts, 32)
      || !integer(value.retrieval_robustness.distinct_content_families, 32)
      || value.retrieval_robustness.distinct_content_families
         > value.retrieval_robustness.selected_sources
      || !integer(value.retrieval_robustness.cross_host_exact_copy_groups, 32)
      || !Array.isArray(value.retrieval_robustness.exact_copy_families)
      || value.retrieval_robustness.exact_copy_families.length > 32
      || value.retrieval_robustness.exact_copy_families.some(family =>
        !family || !HASH.test(family.content_sha256)
        || family.independence_verified !== false
        || !integer(family.source_count, 32) || family.source_count < 2
        || !integer(family.host_count, 32)
        || !Array.isArray(family.hosts) || family.hosts.length !== family.host_count)
      || value.retrieval_robustness.source_bodies_excluded !== true
      || value.retrieval_robustness.verified_independence !== false
      || value.retrieval_robustness.network_or_reranking_executed !== false
      || !Array.isArray(value.retrieval_robustness.objectives)
      || value.retrieval_robustness.objectives.length !== value.objectives?.length
      || value.retrieval_robustness.objectives.some(row =>
        !row || row.independence_confirmed !== false
        || !Number.isFinite(row.dominant_host_fraction)
        || row.dominant_host_fraction < 0 || row.dominant_host_fraction > 1)
      || !Array.isArray(value.retrieval_robustness.host_ablation)
      || value.retrieval_robustness.host_ablation.length > 32
      || value.retrieval_robustness.host_ablation.some(row =>
        !row || row.reranking_executed !== false)
      || !Array.isArray(value.retrieval_robustness.objective_reuse)
      || value.retrieval_robustness.objective_reuse.length > 28
      || value.retrieval_robustness.objective_reuse.some(row =>
        !row || row.independence_proven !== false
        || !Number.isFinite(row.source_jaccard)
        || row.source_jaccard < 0 || row.source_jaccard > 1)
      || !Array.isArray(value.retrieval_robustness.flagged_objectives)
      || value.retrieval_robustness.flagged_objectives.length > 8
      || !Array.isArray(value.retrieval_robustness.limitations)
      || value.retrieval_robustness.limitations.length < 5
      || value.retrieval_robustness.limitations.length > 12
      || value.canonical_routes?.network_authority !== false
      || value.slice_simulation?.network_committed !== false
      || value.slice_simulation.physical_worker_authorized !== false
      || value.dispatch_recovery?.mongo_commit_confirmed !== false
      || value.dispatch_recovery.physical_worker_join_confirmed !== false
      || value.dispatch_recovery.uncertain_bytes_refunded !== false
      || value.scorecard?.decision !== 'human_review_hold'
      || !Array.isArray(value.scorecard.alerts) || value.scorecard.alerts.length > 256
      || value.pilot_qualification !== undefined && !checkedPilotQualification(value.pilot_qualification, value)
      || value.read_only !== true || value.network_executed !== false
      || value.publication_granted !== false || value.training_permission !== false
      || value.review_required !== true || JSON.stringify(value).length > 512 * 1024) {
    invalid('The current Dragon research inspection is incomplete or violates source authority.');
  }
  return value;
}
export async function getCrawlAtlas(
  id: string, request: CrawlAtlasRequest, signal?: AbortSignal,
): Promise<CrawlAtlasReport> {
  safeAtlasRequest(request);
  const previousToken = getAuthToken();
  const payload = await read(
    api.post<{ report: CrawlAtlasReport }>(
      ROOT + '/sessions/' + identifier(id) + '/research/atlas',
      request, options(signal),
    ),
    previousToken, 'The Dragon research inspection could not be verified.',
  );
  if (signal?.aborted || previousToken !== getAuthToken()) {
    throw new ChatClientError('The research inspection was detached or your account changed.', { kind: 'authorization', retryable: false });
  }
  const report = checkedAtlasReport(payload.report, id, request.retrieval_mode);
  if (report.pilot_qualification) {
    // Both the status envelope and this exact-byte digest are source-only:
    // neither is a substitute for the backend's authenticated Mongo re-read.
    const receipt = report.pilot_qualification;
    let canonical: string;
    try { canonical = canonicalPilotReceipt(pilotReceiptBody(receipt)); }
    catch { invalid('Pilot receipt has an invalid canonical payload.'); }
    const observed = await digestStringAsync(CryptoDigestAlgorithm.SHA256, canonical);
    if (signal?.aborted || previousToken !== getAuthToken()) {
      throw new ChatClientError('The pilot receipt was detached from your session.',
        { kind: 'authorization', retryable: false });
    }
    if (observed !== receipt.qualification_digest) {
      invalid('The exact Dragon pilot qualification receipt did not verify.');
    }
  }
  return report;
}

export type DeepArchiveMarker={partition:number;snapshot_digest:string;accepted_at:number;state:'pending'|'archived';released:boolean};
export type DeepArchiveRecord={session_id:string;version:number;archive:DeepArchiveMarker|null;grant_recorded:boolean;index_recorded:boolean;integrity_held:boolean};
export type DeepArchiveCatalog={schema:'skeleton.dragon.deep-catalog.v1';records:DeepArchiveRecord[];next_cursor:string|null;partitions:1024;partition_capacity:1024;reservation_ceiling:1048576;storage_capacity_verified:false};
export type DeepArchiveHit={session_id:string;source_id:string;version:number;snapshot_digest:string;preserved_text_hash:string;captured_at:number;valid_until:number;matched_terms:number;term_frequency:number};
export type DeepArchiveSearch={schema:'skeleton.dragon.deep-search.v1';scanned:number;held:number;matches:DeepArchiveHit[];matching_payloads:number;next_cursor:string|null;as_of_unix:number;earliest_expiry:number|null;approximate_routing:true;page_local_ranking:true;history_only:true;source_text_returned:false;model_context_permission:false;wiki_approval:false};
const deepMarker=(x:DeepArchiveMarker)=>!!x&&integer(x.partition,1023)&&HASH.test(x.snapshot_digest)&&Number.isFinite(x.accepted_at)&&x.accepted_at>=0&&['pending','archived'].includes(x.state)&&typeof x.released==='boolean'&&(!x.released||x.state==='archived');
export async function archiveToDeep(id:string,body:CrawlCommand&{retention_acknowledged:true},signal?:AbortSignal){
 const p=await read(api.post<{schema:string;session_id:string;version:number;archive:DeepArchiveMarker;outcome:string;network_executed:false;source_permission_extended:false}>(ROOT+'/sessions/'+identifier(id)+'/deep-archive',body,options(signal)),getAuthToken(),'Deep archive transfer unavailable.');
 if(!p||p.schema!=='skeleton.dragon.deep-command.v1'||p.session_id!==id||!integer(p.version)||p.version<1||!deepMarker(p.archive)||!['archived','held','superseded','capacity_held'].includes(p.outcome)||p.network_executed!==false||p.source_permission_extended!==false)invalid('Invalid deep archive transfer receipt.');
 return p;
}
export async function getDeepArchive(cursor?:string,signal?:AbortSignal):Promise<DeepArchiveCatalog>{
 if(cursor!==undefined&&!ID.test(cursor))invalid('Invalid deep archive cursor.');
 const p=await read(api.get<DeepArchiveCatalog>(ROOT+'/companion/deep-archive?limit=32'+(cursor?'&cursor='+encodeURIComponent(cursor):''),options(signal)),getAuthToken(),'Deep archive catalogue unavailable.');
 if(!p||p.schema!=='skeleton.dragon.deep-catalog.v1'||p.partitions!==1024||p.partition_capacity!==1024||p.reservation_ceiling!==1048576||p.storage_capacity_verified!==false||!Array.isArray(p.records)||p.records.length>32||p.records.some((x,i)=>!x||!ID.test(x.session_id)||!integer(x.version)||x.version<1||typeof x.integrity_held!=='boolean'||typeof x.grant_recorded!=='boolean'||typeof x.index_recorded!=='boolean'||(x.integrity_held?x.archive!==null||x.grant_recorded||x.index_recorded:!x.archive||!deepMarker(x.archive))||i>0&&p.records[i-1].session_id>=x.session_id||cursor!==undefined&&x.session_id<=cursor)||p.next_cursor!==null&&(p.records.length!==32||p.next_cursor!==p.records[p.records.length-1].session_id))invalid('Invalid deep archive catalogue.');
 return p;
}
export function validateDeepArchiveSearch(p:DeepArchiveSearch):DeepArchiveSearch{
 if(!p||p.schema!=='skeleton.dragon.deep-search.v1'||!integer(p.scanned,32)||!integer(p.held,p.scanned)||!integer(p.matching_payloads,2048)||!Array.isArray(p.matches)||p.matches.length!==Math.min(32,p.matching_payloads)||!Number.isFinite(p.as_of_unix)||p.as_of_unix<0||p.earliest_expiry!==null&&(!Number.isFinite(p.earliest_expiry)||p.earliest_expiry<=p.as_of_unix)||p.matches.length>0&&p.earliest_expiry===null||new Set(p.matches.map(x=>x?.preserved_text_hash)).size!==p.matches.length||p.matches.some(x=>!x||!ID.test(x.session_id)||!HASH.test(x.source_id)||!HASH.test(x.snapshot_digest)||!HASH.test(x.preserved_text_hash)||!integer(x.version)||x.version<1||!integer(x.matched_terms,32)||x.matched_terms<1||!integer(x.term_frequency,256)||!Number.isFinite(x.captured_at)||!Number.isFinite(x.valid_until)||x.valid_until<=p.as_of_unix)||p.next_cursor!==null&&(typeof p.next_cursor!=='string'||p.next_cursor.length>1024)||p.approximate_routing!==true||p.page_local_ranking!==true||p.history_only!==true||p.source_text_returned!==false||p.model_context_permission!==false||p.wiki_approval!==false)invalid('Invalid scoped historical archive search.');
 return p;
}
export async function searchDeepArchive(query:string,cursor?:string,signal?:AbortSignal):Promise<DeepArchiveSearch>{
 if(!query.trim()||query.length>512||cursor!==undefined&&cursor.length>1024)invalid('Invalid deep archive search.');
 return validateDeepArchiveSearch(await read(api.get<DeepArchiveSearch>(ROOT+'/companion/deep-search?query='+encodeURIComponent(query)+(cursor?'&cursor='+encodeURIComponent(cursor):''),options(signal)),getAuthToken(),'Deep archive search unavailable.'));
}
