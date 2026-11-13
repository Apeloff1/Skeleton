export interface MirrorMetricView {
  metric_id: string;
  baseline_score: number;
  candidate_score: number;
  delta: number;
}

export interface MirrorAttemptView {
  attempt: number;
  accepted: boolean;
  baseline_before_id: string;
  candidate_id: string;
  baseline_after_id: string;
  baseline_quality_score: number;
  candidate_quality_score: number;
  effective_quality_score: number;
  baseline_detail_score: number;
  candidate_detail_score: number;
  effective_detail_score: number;
  quality_delta: number;
  detail_delta: number;
  weighted_gain: number;
  required_weighted_gain: number;
  required_strict_metric_gain: number;
  retained_scenarios: number;
  rejection_reasons: string[];
  dimensions: MirrorMetricView[];
}

export interface MirrorRoomStatus {
  schema_version: number;
  version: number;
  run_id: string | null;
  status:
    | 'idle'
    | 'running'
    | 'partial'
    | 'failed'
    | 'complete-blocked'
    | 'delivery-ready';
  attempts_completed: number;
  attempts_required: number;
  progress: number;
  accepted_upgrades: number;
  original_baseline_id: string | null;
  current_baseline_id: string | null;
  start_quality_score: number | null;
  quality_score: number | null;
  quality_lift: number | null;
  start_detail_score: number | null;
  detail_score: number | null;
  detail_lift: number | null;
  current_weighted_gain: number | null;
  required_weighted_gain: number | null;
  required_strict_metric_gain: number | null;
  retained_scenarios: number;
  gauntlet_passed: boolean;
  holdout_passed: boolean;
  delivery_ready: boolean;
  accepted_baselines: string[];
  attempts: MirrorAttemptView[];
  updated_at: number;
  digest: string;
  production_authority: false;
}

export interface MirrorTreeNode {
  name: string;
  path?: string;
  kind: string;
  children?: MirrorTreeNode[];
}

export interface MirrorRoomObservatoryPayload {
  status: MirrorRoomStatus;
  file_tree: MirrorTreeNode;
}
