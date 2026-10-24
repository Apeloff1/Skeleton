/** Pure surveyed-control editing and operator approval model (GF-P0-118).
 *
 * Drafts never apply themselves. Every transition is an explicit operator
 * action recorded in an append-only audit trail; approval needs a valid,
 * submitted draft and a named operator; rejection and revert keep history.
 */

export type SightingInput = {
  sighting_id: string;
  control_point_id: string;
  true_bearing_deg: number;
  distance_m: number;
  uncertainty_m: number;
};

export type BaselineMetadata = {
  baseline_id: string;
  datum: 'WGS84';
  epoch: string;
  instrument: string;
  surveyor: string;
  notes: string;
};

export type SurveyStatus = 'draft' | 'submitted' | 'approved' | 'rejected';

export type SurveyAuditEntry = {
  seq: number;
  action: 'edit' | 'submit' | 'approve' | 'reject' | 'revert' | 'withdraw';
  actor: string;
  at_ms: number;
  status_after: SurveyStatus;
  reason?: string;
};

export type SurveyedControlState = {
  status: SurveyStatus;
  baseline: BaselineMetadata;
  sightings: SightingInput[];
  /** Last approved snapshot; the only thing downstream may treat as baseline. */
  approved: { baseline: BaselineMetadata; sightings: SightingInput[] } | null;
  audit: SurveyAuditEntry[];
};

export type SurveyIssue = { field: string; message: string };

export const MAX_SIGHTINGS = 64;
const ID = /^[A-Za-z0-9_.:-]{1,64}$/;
const EPOCH = /^\d{4}-\d{2}-\d{2}$/;

export function emptyBaseline(): BaselineMetadata {
  return { baseline_id: '', datum: 'WGS84', epoch: '', instrument: '', surveyor: '', notes: '' };
}

export function initialSurveyState(): SurveyedControlState {
  return { status: 'draft', baseline: emptyBaseline(), sightings: [], approved: null, audit: [] };
}

export function validateSighting(s: SightingInput, index: number): SurveyIssue[] {
  const p = `sightings[${index}]`;
  const issues: SurveyIssue[] = [];
  if (!ID.test(s.sighting_id || '')) issues.push({ field: `${p}.sighting_id`, message: 'Sighting ID is required (letters, digits, _.:-).' });
  if (!ID.test(s.control_point_id || '')) issues.push({ field: `${p}.control_point_id`, message: 'Control point ID is required.' });
  if (!(Number.isFinite(s.true_bearing_deg) && s.true_bearing_deg >= 0 && s.true_bearing_deg < 360)) issues.push({ field: `${p}.true_bearing_deg`, message: 'True bearing must be between 0 and 360 degrees.' });
  if (!(Number.isFinite(s.distance_m) && s.distance_m > 0 && s.distance_m <= 100000)) issues.push({ field: `${p}.distance_m`, message: 'Distance must be greater than 0 and at most 100 km.' });
  if (!(Number.isFinite(s.uncertainty_m) && s.uncertainty_m >= 0 && s.uncertainty_m <= 1000)) issues.push({ field: `${p}.uncertainty_m`, message: 'Uncertainty must be between 0 and 1000 m.' });
  return issues;
}

export function validateSurvey(state: Pick<SurveyedControlState, 'baseline' | 'sightings'>): SurveyIssue[] {
  const b = state.baseline;
  const issues: SurveyIssue[] = [];
  if (!ID.test(b.baseline_id || '')) issues.push({ field: 'baseline.baseline_id', message: 'Baseline ID is required.' });
  if (b.datum !== 'WGS84') issues.push({ field: 'baseline.datum', message: 'Only WGS84 control is supported.' });
  if (!EPOCH.test(b.epoch || '') || Number.isNaN(Date.parse(b.epoch))) issues.push({ field: 'baseline.epoch', message: 'Survey epoch must be a date like 2026-10-24.' });
  if (!(b.instrument || '').trim()) issues.push({ field: 'baseline.instrument', message: 'Instrument is required.' });
  if (!(b.surveyor || '').trim()) issues.push({ field: 'baseline.surveyor', message: 'Surveyor is required.' });
  if (!state.sightings.length) issues.push({ field: 'sightings', message: 'Add at least one sighting.' });
  if (state.sightings.length > MAX_SIGHTINGS) issues.push({ field: 'sightings', message: `At most ${MAX_SIGHTINGS} sightings.` });
  const ids = new Set<string>();
  state.sightings.forEach((s, i) => {
    issues.push(...validateSighting(s, i));
    if (ids.has(s.sighting_id)) issues.push({ field: `sightings[${i}].sighting_id`, message: 'Sighting IDs must be unique.' });
    ids.add(s.sighting_id);
  });
  return issues;
}

export type SurveyAction =
  | { type: 'edit_baseline'; patch: Partial<Omit<BaselineMetadata, 'datum'>> }
  | { type: 'upsert_sighting'; sighting: SightingInput }
  | { type: 'remove_sighting'; sighting_id: string }
  | { type: 'submit' }
  | { type: 'withdraw' }
  | { type: 'approve' }
  | { type: 'reject'; reason: string }
  | { type: 'revert' };

export type SurveyResult = { state: SurveyedControlState; error: string | null };

function log(state: SurveyedControlState, entry: Omit<SurveyAuditEntry, 'seq'>): SurveyAuditEntry[] {
  return [...state.audit, { ...entry, seq: state.audit.length + 1 }];
}

/** Apply one operator action. Invalid transitions return the unchanged state plus an error. */
export function applySurveyAction(
  state: SurveyedControlState, action: SurveyAction, actor: string, at_ms: number,
): SurveyResult {
  const who = (actor || '').trim();
  if (!who) return { state, error: 'An operator name is required for every survey action.' };
  const fail = (error: string): SurveyResult => ({ state, error });
  const editable = state.status !== 'submitted';

  switch (action.type) {
    case 'edit_baseline':
    case 'upsert_sighting':
    case 'remove_sighting': {
      if (!editable) return fail('Withdraw the submission before editing.');
      let { baseline, sightings } = state;
      if (action.type === 'edit_baseline') {
        const { datum: _ignored, ...patch } = action.patch as Partial<BaselineMetadata>;
        baseline = { ...baseline, ...patch, datum: 'WGS84' };
      } else if (action.type === 'upsert_sighting') {
        const at = sightings.findIndex(s => s.sighting_id === action.sighting.sighting_id);
        if (at < 0 && sightings.length >= MAX_SIGHTINGS) return fail(`At most ${MAX_SIGHTINGS} sightings.`);
        sightings = at < 0 ? [...sightings, { ...action.sighting }]
          : sightings.map((s, i) => (i === at ? { ...action.sighting } : s));
      } else {
        if (!sightings.some(s => s.sighting_id === action.sighting_id)) return fail('That sighting is not in this draft.');
        sightings = sightings.filter(s => s.sighting_id !== action.sighting_id);
      }
      const next = { ...state, baseline, sightings, status: 'draft' as const };
      return { state: { ...next, audit: log(state, { action: 'edit', actor: who, at_ms, status_after: 'draft' }) }, error: null };
    }
    case 'submit': {
      if (!editable) return fail('Already waiting for approval.');
      if (state.status === 'approved' && !hasUnapprovedChanges(state)) return fail('Nothing changed since the last approval.');
      const issues = validateSurvey(state);
      if (issues.length) return fail(`Fix ${issues.length} issue${issues.length === 1 ? '' : 's'} before submitting.`);
      return { state: { ...state, status: 'submitted', audit: log(state, { action: 'submit', actor: who, at_ms, status_after: 'submitted' }) }, error: null };
    }
    case 'withdraw': {
      if (state.status !== 'submitted') return fail('Nothing is waiting for approval.');
      return { state: { ...state, status: 'draft', audit: log(state, { action: 'withdraw', actor: who, at_ms, status_after: 'draft' }) }, error: null };
    }
    case 'approve': {
      if (state.status !== 'submitted') return fail('Submit the draft before approving it.');
      if (validateSurvey(state).length) return fail('The submitted draft is no longer valid.');
      const approved = { baseline: { ...state.baseline }, sightings: state.sightings.map(s => ({ ...s })) };
      return { state: { ...state, status: 'approved', approved, audit: log(state, { action: 'approve', actor: who, at_ms, status_after: 'approved' }) }, error: null };
    }
    case 'reject': {
      if (state.status !== 'submitted') return fail('Only a submitted draft can be rejected.');
      const reason = (action.reason || '').trim();
      if (!reason) return fail('Give a reason so the surveyor knows what to fix.');
      return { state: { ...state, status: 'rejected', audit: log(state, { action: 'reject', actor: who, at_ms, status_after: 'rejected', reason }) }, error: null };
    }
    case 'revert': {
      if (state.status === 'submitted') return fail('Withdraw the submission before reverting.');
      const base = state.approved;
      const next: SurveyedControlState = base
        ? { ...state, status: 'approved', baseline: { ...base.baseline }, sightings: base.sightings.map(s => ({ ...s })) }
        : { ...state, status: 'draft', baseline: emptyBaseline(), sightings: [] };
      return { state: { ...next, audit: log(state, { action: 'revert', actor: who, at_ms, status_after: next.status }) }, error: null };
    }
    default:
      return fail('Unknown survey action.');
  }
}

/** True when the working draft differs from the last approved snapshot. */
export function hasUnapprovedChanges(state: SurveyedControlState): boolean {
  if (!state.approved) return state.sightings.length > 0 || JSON.stringify(state.baseline) !== JSON.stringify(emptyBaseline());
  return JSON.stringify(state.approved.baseline) !== JSON.stringify(state.baseline)
    || JSON.stringify(state.approved.sightings) !== JSON.stringify(state.sightings);
}
