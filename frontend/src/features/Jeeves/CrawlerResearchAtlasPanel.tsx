/** Source-bound, read-only Dragon research and human-review workbench.
 * No call from this component can start capture, approve claims or publish.
 * Consent and source use remain under the authenticated crawler authority.
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { ActivityIndicator, StyleSheet, Text, TextInput, TouchableOpacity, View } from 'react-native';
import { getAuthToken } from '../../auth/gameforgeAuth';
import {
  getCrawlAtlas, type CrawlAtlasObjective, type CrawlAtlasRequest,
  type CrawlAtlasEffort, type CrawlAtlasReport, type CrawlSession,
} from '../../product/crawlerClient';
import s, { colors as C } from './CrawlerWorkspace.styles';
import {
  NEW_ATLAS_DRAFT, MAX_ATLAS_OBJECTIVES,
  compileAtlasCampaign, enqueueAtlasObjective, removeAtlasObjective,
  type AtlasObjectiveDraft,
} from './atlasCampaignPlan';

type Dimension = CrawlAtlasObjective['dimension'];
type Stage = CrawlAtlasObjective['stage'];
type Mode = CrawlAtlasRequest['retrieval_mode'];
const DIMENSIONS: Dimension[] = ['fact', 'method', 'timeline', 'source', 'counterexample', 'implementation'];
const STAGES: Stage[] = ['discovery', 'collection', 'verification', 'review'];
const MODES: Mode[] = ['fusion', 'lexical_bm25'];
const REVIEW_TYPES: CrawlAtlasEffort['task_type'][] = [
  'source_policy', 'passage_integrity', 'source_provenance',
  'claim_contradiction', 'claim_corroboration', 'objective_gap', 'human_fact_review',
];
const readable = (x: string) => x.replaceAll('_', ' ');
const minutes = (x: string, max: number) => /^\d+$/.test(x) && Number(x) >= 1 && Number(x) <= max;
const styles = StyleSheet.create({
  textField: { backgroundColor: C.bg, borderWidth: 1, borderColor: C.edge,
    borderRadius: 9, minHeight: 48, minWidth: 0, color: C.text,
    fontSize: 14, paddingHorizontal: 12, paddingVertical: 11 },
  selected: { backgroundColor: '#312747', borderColor: C.accent },
  metric: { flexBasis: 140, flexGrow: 1, padding: 11, borderWidth: 1,
    borderColor: C.edge, borderRadius: 9, backgroundColor: C.bg, gap: 4 },
  metricValue: { color: C.text, fontSize: 22, fontWeight: '700' },
  section: { paddingTop: 12, borderTopWidth: 1, borderColor: C.edge, gap: 9 },
  estimate: { flexGrow: 1, flexBasis: 120, gap: 5, minWidth: 0 },
});
function Choice({ text, selected, disabled, onPress }: {
  text: string; selected: boolean; disabled: boolean; onPress: () => void;
}) {
  return <TouchableOpacity accessibilityRole="button" accessibilityLabel={'Choose ' + readable(text)}
    accessibilityState={{ selected, disabled }} onPress={onPress}
    disabled={disabled} style={[s.button, selected && styles.selected, disabled && s.disabled]}>
    <Text style={s.buttonText}>{readable(text)}</Text>
  </TouchableOpacity>;
}
function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return <View style={styles.section}><Text style={s.label}>{title}</Text>{children}</View>;
}
function Metric({ title, value, caption }: { title: string; value: number; caption?: string }) {
  return <View style={styles.metric}><Text style={s.small}>{title}</Text>
    <Text style={styles.metricValue}>{value.toLocaleString()}</Text>
    {!!caption && <Text style={s.small}>{caption}</Text>}</View>;
}

export default function CrawlerResearchAtlasPanel({ session }: { session: CrawlSession }) {
  const [question, setQuestion] = useState('');
  const [dimension, setDimension] = useState<Dimension>('method');
  const [stage, setStage] = useState<Stage>('verification');
  const [mode, setMode] = useState<Mode>('fusion');
  const [priority, setPriority] = useState(NEW_ATLAS_DRAFT.priority);
  const [passageTarget, setPassageTarget] = useState(NEW_ATLAS_DRAFT.passageTarget);
  const [independenceTarget, setIndependenceTarget] = useState(NEW_ATLAS_DRAFT.independenceTarget);
  const [maxAgeMinutes, setMaxAgeMinutes] = useState(NEW_ATLAS_DRAFT.maxAgeMinutes);
  const [requiredTerms, setRequiredTerms] = useState(NEW_ATLAS_DRAFT.requiredTerms);
  const [blockedTerms, setBlockedTerms] = useState(NEW_ATLAS_DRAFT.blockedTerms);
  const [queuedGoals, setQueuedGoals] = useState<CrawlAtlasObjective[]>([]);
  const [report, setReport] = useState<CrawlAtlasReport | null>(null);
  const [currentGoals, setCurrentGoals] = useState<CrawlAtlasObjective[] | null>(null);
  const [minutesPerTask, setMinutesPerTask] = useState('12');
  const [budget, setBudget] = useState('120');
  const [working, setWorking] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const revision = session.session_id + ':' + session.version;
  const revisionRef = useRef(revision);
  revisionRef.current = revision;
  const authRef = useRef(getAuthToken());
  const epoch = useRef(0);
  const request = useRef<AbortController | null>(null);
  const busy = useRef(false);

  const clear = useCallback(() => {
    epoch.current++;
    request.current?.abort();
    request.current = null;
    busy.current = false;
    setWorking(false); setReport(null); setCurrentGoals(null); setError(''); setNotice('');
  }, []);
  useEffect(() => {
    clear();
    return () => { epoch.current++; request.current?.abort(); request.current = null; };
  }, [revision, clear]);
  useEffect(() => {
    // Research goals are per-capture. A different authenticated session must
    // not inherit questions or query filters from the previous source scope.
    setQueuedGoals([]);
    setQuestion('');
  }, [session.session_id]);

  // Clear any source identities from a previous signed-in account. Async
  // responses are independently fenced against a concurrent account change.
  const authChanged = authRef.current !== getAuthToken();
  useEffect(() => {
    if (authChanged) {
      authRef.current = getAuthToken();
      clear();
      setQueuedGoals([]);
      setQuestion('');
    }
  }, [authChanged, clear]);

  const analyze = useCallback(async (allocate: boolean) => {
    if (busy.current) return;
    let goals: CrawlAtlasObjective[];
    try {
      const draft: AtlasObjectiveDraft = {
        question, dimension, stage, priority, requiredTerms, blockedTerms,
        passageTarget, independenceTarget, maxAgeMinutes,
      };
      if (allocate) {
        if (!currentGoals) throw new RangeError('Analyze an exact objective set before planning review.');
        goals = [...currentGoals];
      } else {
        goals = compileAtlasCampaign(queuedGoals, draft);
      }
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : 'Research objective input was invalid.');
      return;
    }
    if (!session.consent_current) {
      setError('A current capture consent grant is required.');
      return;
    }
    if (allocate && (!report || !report.review_operations.tasks_total)) {
      setError('Analyze captured sources before planning review work.');
      return;
    }
    if (allocate && (!minutes(minutesPerTask, 180) || !minutes(budget, 1440))) {
      setError('Use 1–180 estimated minutes per task and 1–1,440 minutes total.');
      return;
    }
    const estimates: CrawlAtlasEffort[] = allocate
      ? REVIEW_TYPES.filter(type => Object.prototype.hasOwnProperty.call(
          report?.review_operations.task_types ?? {}, type,
        )).map(task_type => ({
          task_type, estimated_minutes: Number(minutesPerTask),
          estimate_basis: 'operator_estimate',
        }))
      : [];
    if (allocate && !estimates.length) {
      setError('The current source snapshot contains no eligible review task types.');
      return;
    }
    const payload: CrawlAtlasRequest = {
      objectives: goals, retrieval_mode: mode,
      ...(allocate ? {
        review_effort: estimates, review_budget_minutes: Number(budget),
      } : {}),
    };
    const controller = new AbortController();
    request.current?.abort(); request.current = controller;
    const submittedAt = ++epoch.current;
    const sessionRevision = revisionRef.current;
    const auth = getAuthToken();
    busy.current = true;
    setWorking(true); setError(''); setNotice('');
    try {
      const data = await getCrawlAtlas(session.session_id, payload, controller.signal);
      if (controller.signal.aborted || submittedAt !== epoch.current ||
          sessionRevision !== revisionRef.current || auth !== getAuthToken()) return;
      setReport(data);
      setCurrentGoals(goals);
      setNotice(allocate
        ? 'A bounded review plan was calculated, but no human was assigned and nothing was approved.'
        : 'Source-bound research completed. All external statements require human review.');
    } catch (exc) {
      if (controller.signal.aborted || submittedAt !== epoch.current ||
          sessionRevision !== revisionRef.current || auth !== getAuthToken()) return;
      setReport(null); setCurrentGoals(null);
      setError(exc instanceof Error ? exc.message : 'The Atlas inspection could not be verified.');
    } finally {
      if (submittedAt === epoch.current) {
        request.current = null; busy.current = false; setWorking(false);
      }
    }
  }, [session.session_id, session.consent_current, question, dimension,
    stage, mode, priority, requiredTerms, blockedTerms, passageTarget,
    independenceTarget, maxAgeMinutes, queuedGoals,
    currentGoals, report, minutesPerTask, budget]);

  const changeQuestion = (x: string) => { clear(); setQuestion(x); };
  const changeDimension = (x: Dimension) => { clear(); setDimension(x); };
  const changeStage = (x: Stage) => { clear(); setStage(x); };
  const changeMode = (x: Mode) => { clear(); setMode(x); };
  const draft: AtlasObjectiveDraft = {
    question, dimension, stage, priority, requiredTerms, blockedTerms,
    passageTarget, independenceTarget, maxAgeMinutes,
  };
  const enqueue = () => {
    try {
      const next = enqueueAtlasObjective(queuedGoals, draft);
      clear();
      setQueuedGoals(next);
      setQuestion('');
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : 'Research objective is invalid.');
    }
  };
  const removeGoal = (id: string) => {
    try {
      const next = removeAtlasObjective(queuedGoals, id);
      clear();
      setQueuedGoals(next);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : 'The objective is no longer in this campaign.');
    }
  };
  const ready = !working && !authChanged && session.consent_current &&
    (queuedGoals.length > 0 || question.trim().length >= 3);

  return <View style={s.card}>
    <Text style={s.heading}>Dragon research Atlas</Text>
    <Text style={s.small}>Research retained captures, evaluate discrepancies and plan human review. Atlas does not fetch additional websites or authorize Jeeves to execute source instructions.</Text>
    <Text style={s.label}>Research question</Text>
    <TextInput accessibilityLabel="Question for captured research sources"
      value={question} onChangeText={changeQuestion} editable={!working}
      maxLength={512} multiline style={styles.textField}
      placeholder="Which methods are described by these captures?"
      placeholderTextColor={C.muted} />
    <Text style={s.label}>Dimension</Text>
    <View style={s.row}>{DIMENSIONS.map(x => <Choice key={x} text={x}
      selected={dimension === x} disabled={working}
      onPress={() => changeDimension(x)} />)}</View>
    <Text style={s.label}>Research stage</Text>
    <View style={s.row}>{STAGES.map(x => <Choice key={x} text={x}
      selected={stage === x} disabled={working}
      onPress={() => changeStage(x)} />)}</View>
    <Section title={'Research campaign objectives · ' + queuedGoals.length + '/' + MAX_ATLAS_OBJECTIVES}>
      <Text style={s.small}>Queue up to eight distinct operator-authored questions. An unqueued question is included when you analyze; it is never silently discarded.</Text>
      {queuedGoals.map(item =>
        <View key={item.objective_id} style={s.check}>
          <Text style={s.message}>{item.question}</Text>
          <Text style={s.small}>{readable(item.dimension)} · {readable(item.stage)} · priority {item.priority.toFixed(3)} · {item.minimum_reviewable_passages} passages · {item.minimum_attested_groups} source group(s)</Text>
          <TouchableOpacity accessibilityRole="button"
            accessibilityLabel={'Remove research objective ' + item.objective_id}
            style={s.button} disabled={working}
            onPress={() => removeGoal(item.objective_id)}>
            <Text style={s.buttonText}>Remove objective</Text>
          </TouchableOpacity>
        </View>)}
      <Text style={s.label}>Objective priority (0–1)</Text>
      <TextInput accessibilityLabel="Objective priority" style={styles.textField}
        keyboardType="decimal-pad" maxLength={5} editable={!working}
        value={priority} onChangeText={value => { clear(); setPriority(value); }} />
      <View style={s.row}>
        <View style={styles.estimate}>
          <Text style={s.small}>Minimum reviewable passages (1–32)</Text>
          <TextInput accessibilityLabel="Minimum reviewable passages" style={styles.textField}
            keyboardType="number-pad" value={passageTarget} maxLength={2}
            editable={!working} onChangeText={value => { clear(); setPassageTarget(value); }} />
        </View>
        <View style={styles.estimate}>
          <Text style={s.small}>Independent source groups (1–16)</Text>
          <TextInput accessibilityLabel="Minimum attested source groups" style={styles.textField}
            keyboardType="number-pad" value={independenceTarget} maxLength={2}
            editable={!working} onChangeText={value => { clear(); setIndependenceTarget(value); }} />
        </View>
        <View style={styles.estimate}>
          <Text style={s.small}>Source capture age limit (1–1440 minutes)</Text>
          <TextInput accessibilityLabel="Maximum source capture age minutes"
            style={styles.textField} keyboardType="number-pad"
            value={maxAgeMinutes} maxLength={4} editable={!working}
            onChangeText={value => { clear(); setMaxAgeMinutes(value); }} />
        </View>
      </View>
      <Text style={s.label}>Required query terms (optional, lowercase)</Text>
      <TextInput accessibilityLabel="Required normalized query terms"
        style={styles.textField} value={requiredTerms} maxLength={1024}
        placeholder="archive, methodology" placeholderTextColor={C.muted}
        autoCapitalize="none" editable={!working}
        onChangeText={value => { clear(); setRequiredTerms(value); }} />
      <Text style={s.label}>Excluded query terms (optional, lowercase)</Text>
      <TextInput accessibilityLabel="Excluded normalized query terms"
        style={styles.textField} value={blockedTerms} maxLength={1024}
        placeholder="advertisement, spam" placeholderTextColor={C.muted}
        autoCapitalize="none" editable={!working}
        onChangeText={value => { clear(); setBlockedTerms(value); }} />
      <TouchableOpacity accessibilityRole="button"
        accessibilityState={{ disabled: working || queuedGoals.length >= MAX_ATLAS_OBJECTIVES || question.trim().length < 3 }}
        disabled={working || queuedGoals.length >= MAX_ATLAS_OBJECTIVES || question.trim().length < 3}
        style={[s.button, (working || queuedGoals.length >= MAX_ATLAS_OBJECTIVES || question.trim().length < 3) && s.disabled]}
        onPress={enqueue}>
        <Text style={s.buttonText}>Add question to research campaign</Text>
      </TouchableOpacity>
    </Section>
    <Text style={s.label}>Retrieval algorithm</Text>
    <View style={s.row}>{MODES.map(x => <Choice key={x}
      text={x === 'fusion' ? 'Reciprocal rank fusion' : 'BM25 proximity'}
      selected={mode === x} disabled={working}
      onPress={() => changeMode(x)} />)}</View>
    <View style={s.row}>
      <TouchableOpacity accessibilityRole="button"
        accessibilityLabel="Analyze currently captured evidence"
        accessibilityState={{ disabled: !ready }} disabled={!ready}
        style={[s.button, !ready && s.disabled]}
        onPress={() => { void analyze(false); }}>
        <Text style={s.buttonText}>Analyze current capture</Text>
      </TouchableOpacity>
      {report && <TouchableOpacity accessibilityRole="button" onPress={clear} style={s.button}>
        <Text style={s.buttonText}>Clear findings</Text>
      </TouchableOpacity>}
      {working && <ActivityIndicator color={C.accent} />}
    </View>
    {!session.consent_current && <Text style={s.error}>Capture consent is no longer current. No research inspection is authorized.</Text>}
    {!!error && <Text style={s.error} accessibilityRole="alert">{error}</Text>}
    {!!notice && <Text style={s.small} accessibilityLiveRegion="polite">{notice}</Text>}
    {!authChanged && report && <>
      <Section title="Research pilot qualification · release held">
        <Text style={s.small}>This pilot is source-only and never authorizes capture, publishing, model training or product release.</Text>
        {report.pilot_qualification ? <>
          <Text style={s.label}>Pilot: {readable(report.pilot_qualification.pilot_status)}</Text>
          <Text style={s.small}>Receipt {report.pilot_qualification.qualification_digest.slice(0, 16)} · {report.pilot_qualification.checks.filter(item => item.status === 'qualified').length}/{report.pilot_qualification.pilot_check_count} source-only checks qualified</Text>
          {report.pilot_qualification.checks.filter(item => item.status === 'held').map(item =>
            <Text style={s.error} key={item.code}>{readable(item.code)} · {readable(item.next_action || 'human_review_required')}</Text>)}
          <Text style={s.small}>External release checks: {report.pilot_qualification.external_release_checks.length} unqualified. Complete exact-head CI, independent device/recovery testing and human source review before any release claim.</Text>
          <Text style={s.small}>The result expires on source, consent, policy, identity or head changes; re-run Atlas before relying on it.</Text>
        </> : <Text style={s.error}>Pilot qualification receipt unavailable. Release remains held.</Text>}
      </Section>
      <Text style={s.heading}>Evidence inspection</Text>
      <Text style={s.small}>Snapshot {report.snapshot_digest.slice(0, 16)} · {report.stages.length} audit stages · sequence {report.run_sequence} · {report.objectives.length} operator objectives</Text>
      <View style={styles.section}>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 9 }}>
          <Metric title="Allowed sources" value={report.source_policy.included_source_count}
            caption={report.source_policy.excluded_source_count + ' excluded'} />
          <Metric title="Retained passages" value={report.retrieval.retained_hits}
            caption={report.retrieval.distinct_hosts + ' hosts'} />
          <Metric title="Evidence vertices" value={report.evidence_graph.vertices}
            caption={report.evidence_graph.arcs + ' edges'} />
          <Metric title="Review tasks" value={report.review_operations.tasks_total}
            caption={report.review_operations.blocked_tasks + ' blocked'} />
        </View>
      </View>
      <Section title="Quality and verification holds">
        <Text style={s.small}>Advisory priority {report.scorecard.advisory_priority.toFixed(3)} measures workflow gaps, not factual accuracy.</Text>
        {report.scorecard.dimensions.slice(0, 12).map(item =>
          <Text key={item.name} style={s.small}>{readable(item.name)} · {item.numerator}/{item.denominator} · {readable(item.grade)}</Text>)}
        {report.scorecard.alerts.slice(0, 8).map((item, i) =>
          <Text key={i} style={s.error}>{readable(item)}</Text>)}
      </Section>
      <Section title="Forensic source-integrity and privacy review">
        <Text style={s.small}>
          {report.forensics.stages.length} forensic stages · {report.forensics.selected_passages} anchored passages · {report.forensics.selected_sources} distinct sources · {report.forensics.review_tasks} pending review signals
        </Text>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 9 }}>
          <Metric title="Injection / text holds" value={report.forensics.security_held_passages}
            caption={report.forensics.security_held_sources + ' source(s)'} />
          <Metric title="Active content" value={report.forensics.active_content_held_sources}
            caption="Unsafe rendering signals" />
          <Metric title="Privacy review" value={report.forensics.privacy_held_sources}
            caption="Sensitive values redacted" />
          <Metric title="Critical review tasks" value={report.forensics.critical_review_tasks}
            caption={report.forensics.review_tasks + ' total signals'} />
        </View>
        <Text style={s.small}>
          {report.forensics.cross_host_sentence_echoes} cross-host sentence echoes · {report.forensics.source_reuse_components} possible source-reuse clusters · {report.forensics.possible_polarity_collisions} possible polarity collisions
        </Text>
        <Text style={s.small}>
          {report.forensics.low_information_passages} low-information passages · {report.forensics.capture_age_held_sources} capture-age holds · {report.forensics.concentrated_objectives.length} objectives with concentrated hosts
        </Text>
        <Text style={s.small}>
          {report.forensics.provenance_held_sources} source provenance holds · {report.forensics.grounding_deficit_objectives} lexical objective deficits · {report.forensics.reference_reused_sources} sources reused across objectives · {report.forensics.urgent_research_gaps} urgent research gaps
        </Text>
        <Text style={s.small}>
          {report.forensics.context_selected_utf8_bytes} selected UTF-8 bytes · {report.forensics.context_budget_exceeded ? 'context limit review required' : 'within audit context limits'} · {report.forensics.consent_renewal_review_due ? 'consent renewal review due' : 'mandate window not near expiry'}
        </Text>
        <Text style={s.small}>
          {report.forensics.extraction_held_sources} extraction holds · {report.forensics.origin_review_sources} URL-origin holds · {report.forensics.query_unsupported_objectives} query-supported objectives missing evidence
        </Text>
        <Text style={s.small}>
          {report.forensics.selection_source_dominance_objectives} source-dominated objectives · {report.forensics.risk_ablated_objectives} objectives emptied by hypothetical risk holds · {report.forensics.script_coverage_review_objectives} language-script coverage reviews
        </Text>
        <Text style={s.small}>All indicators are unverified review signals, not confirmed attacks, factual errors or rights decisions. The original source text remains restricted by current authenticated capture policy.</Text>
        {report.forensics.review_queue.slice(0, 12).map(item =>
          <View key={item.task_id} style={s.check}>
            <Text style={item.risk === 'critical' ? s.error : s.message}>
              {readable(item.reason)} · {readable(item.risk)} risk
            </Text>
            <Text style={s.small}>
              {item.source_ids.length} source(s) · {item.objective_ids.length} objective(s) · task {item.task_id.slice(0, 12)} · human review only
            </Text>
          </View>)}
        {!report.forensics.review_tasks && <Text style={s.small}>No additional forensic holds in the currently selected passages. Absence of findings does not establish safety or truth.</Text>}
      </Section>
      <Section title="Operational preflight and recovery barriers">
        <Text style={s.small}>
          {report.operations.stages.length} integrity gates · {report.operations.retained_event_count} event receipts · {report.operations.inspected_origins} canonical origins · {report.operations.hypothetical_work_candidates} hypothetical candidates
        </Text>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 9 }}>
          <Metric title="Unresolved robots" value={report.operations.unresolved_robots_origins}
            caption={report.operations.stale_robots_origins + ' stale cache(s)'} />
          <Metric title="Uncertain bytes" value={report.operations.uncertain_bytes}
            caption={report.operations.pending_dispatch ? 'Unsettled request' : 'No pending dispatch'} />
          <Metric title="Recovery priorities" value={report.operations.critical_operator_steps}
            caption="Operator action only" />
          <Metric title="Resource samples" value={report.operations.observed_resource_samples}
            caption="Measured host telemetry" />
        </View>
        <Text style={s.small}>
          {report.operations.historical_events_incomplete ? 'Event history incomplete' : 'Retained event window intact'} · {report.operations.event_clock_integrity_review ? 'Clock integrity review due' : 'No timestamp anomaly found in retained events'} · {report.operations.capacity_holds.length} capacity hold(s)
        </Text>
        {report.operations.operator_runbook.slice(0, 12).map((item, i) =>
          <Text key={item.code + i} style={item.priority === 'critical' ? s.error : s.small}>
            {readable(item.priority)} · {readable(item.code)} · needs backend authorization
          </Text>)}
        <Text style={s.small}>No worker was fenced, no Mongo checkpoint was confirmed and no network access was granted. A new authenticated canonical admission is mandatory before any action.</Text>
      </Section>
      <Section title="Evidence-family collapse and apparent support">
        <Text style={s.small}>
          {report.evidence_family_stress.selected_source_records} selected source records · {report.evidence_family_stress.exact_content_families} unique captured-text families · {report.evidence_family_stress.possible_near_duplicate_clusters} possible lexical family clusters
        </Text>
        <Text style={s.small}>
          These are sensitivity scenarios, not independently attested witnesses. Distinct content may still share origin, and similarity alone does not establish copied authorship.
        </Text>
        {report.evidence_family_stress.objectives.slice(0, 8).map(item =>
          <View key={item.objective_id} style={s.check}>
            <Text style={s.message}>{item.objective_id} · {readable(item.concern)}</Text>
            <Text style={s.small}>
              Records {item.selected_source_records} → exact text families {item.exact_content_families} → possible near-copy clusters {item.possible_near_duplicate_clusters}
            </Text>
            <Text style={s.small}>
              Operator source-group target: {item.target_attested_groups} · hypothetical cluster shortfall: {item.hypothetical_target_shortfall} · verified independent groups: none
            </Text>
            <Text style={s.small}>
              Under worst observed host removal: {item.worst_host_loss_clusters} clusters · {item.unscored_sources} sources still need a similarity review
            </Text>
          </View>)}
        <Text style={s.small}>
          {report.evidence_family_stress.flagged_objectives.length} objectives with potential dependence or missing selected evidence · all require human review before using claims.
        </Text>
      </Section>
      <Section title="Near-duplicate source provenance and copy review">
        <Text style={s.small}>
          {report.source_similarity.compared_sources} of {report.source_similarity.selected_sources} policy-eligible source(s) compared · {report.source_similarity.held_sources} held because too short or too large
        </Text>
        <Text style={s.small}>
          {report.source_similarity.candidate_pairs} similarity-review lead(s) across {report.source_similarity.eligible_pairs} examined pair(s) · {report.source_similarity.cross_host_candidates} crossed host boundaries
        </Text>
        <Text style={s.small}>These matches use bounded Unicode-normalized text shingles, not factual verification. A cluster may connect sources indirectly without every pair being similar.</Text>
        {report.source_similarity.candidate_leads.map((item, index) =>
          <View key={item.left_host + ':' + item.right_host + ':' + index} style={s.check}>
            <Text style={s.message}>
              {item.left_host} ↔ {item.right_host} · {readable(item.relation)}
            </Text>
            <Text style={s.small}>
              {(item.jaccard * 100).toFixed(1)}% four-gram Jaccard · {(item.smaller_set_containment * 100).toFixed(1)}% smaller-source containment · requires human lineage review
            </Text>
          </View>)}
        {report.source_similarity.clusters.map((item, index) =>
          <Text key={index} style={s.small}>
            Review cluster: {item.source_count} sources / {item.observed_hosts.length} hosts / {item.direct_candidate_edges} direct pair matches · not independently verified
          </Text>)}
      </Section>
      <Section title="Source concentration and evidence fragility">
        <Text style={s.small}>
          {report.retrieval_robustness.selected_sources} selected sources on {report.retrieval_robustness.selected_hosts} host(s) · {report.retrieval_robustness.distinct_content_families} distinct exact-content families · {report.retrieval_robustness.flagged_objectives.length} exposure-review objectives
        </Text>
        <Text style={s.small}>Host removal models only the currently selected evidence. It does not refetch, rerank or prove source independence.</Text>
        <Text style={s.small}>
          {report.retrieval_robustness.cross_host_exact_copy_groups} exact-content copy group(s) appearing across separate hosts. Exact copies count as one textual evidence family, not independent confirmation.
        </Text>
        {report.retrieval_robustness.exact_copy_families.slice(0, 12).map(group =>
          <Text key={group.content_sha256} style={s.small}>
            Exact-copy family {group.content_sha256.slice(0, 12)}: {group.source_count} source records, {group.host_count} hosts, {group.selected_passages} passages · unreviewed relationship
          </Text>)}
        {report.retrieval_robustness.objectives.slice(0, 8).map(item =>
          <View key={item.objective_id} style={s.check}>
            <Text style={s.message}>{item.objective_id} · {readable(item.risk)}</Text>
            <Text style={s.small}>
              {item.selected_passages} passages · {item.distinct_selected_sources} sources · {item.distinct_selected_hosts} hosts · {item.distinct_content_families} unique text families
            </Text>
            <Text style={s.small}>
              Most represented host: {item.dominant_host ?? 'none'} ({(item.dominant_host_fraction * 100).toFixed(1)}% of passages)
            </Text>
            <Text style={s.small}>
              Under worst observed single-host loss: {item.remaining_passages_after_host_loss} retained passages from {item.remaining_sources_after_host_loss} sources
            </Text>
          </View>)}
        {report.retrieval_robustness.host_ablation.slice(0, 12).map(item =>
          <Text key={item.removed_host} style={s.small}>
            Exclude {item.removed_host}: {item.surviving_selected_passages} selected passages remain across {item.surviving_distinct_content_families} exact-content families · {item.objectives_without_evidence.length} objectives have no surviving selected evidence
          </Text>)}
        {report.retrieval_robustness.objective_reuse.filter(
          item => item.shared_source_count > 0,
        ).slice(0, 8).map(item =>
          <Text key={item.left_objective_id + ':' + item.right_objective_id} style={s.small}>
            {item.left_objective_id} and {item.right_objective_id} share {item.shared_source_count} selected source(s), {item.shared_content_family_count} exact-content families; reuse is not independent corroboration
          </Text>)}
        <Text style={s.small}>These are review-priority diagnostics. External claims remain unverified even when multiple hosts agree.</Text>
      </Section>
      <Section title="Quantitative and chronological leads">
        <Text style={s.small}>{report.numeric_signals.observed_quantities} numeric mention(s) · {report.numeric_signals.cross_source_review_candidates} differences · {report.temporal_signals.date_mentions} date mentions</Text>
        {report.numeric_signals.candidates.slice(0, 8).map((item, i) =>
          <Text key={i} style={s.small}>{item.normalized_left} vs {item.normalized_right} {readable(item.unit_family)} · {(100 * item.relative_gap).toFixed(1)}% · unverified contextual difference</Text>)}
        {report.temporal_signals.groups.slice(0, 8).map((item, i) =>
          <Text key={i} style={s.small}>{item.date} · {item.source_count} source(s) · not a verified remote update</Text>)}
      </Section>
      <Section title="Dependency-gated human review">
        {report.review_operations.recommended_queue.slice(0, 12).map(item =>
          <View key={item.task_id} style={s.check}>
            <Text style={s.message}>{readable(item.type)}</Text>
            <Text style={s.small}>Priority {item.priority.toFixed(2)} · {item.predecessors.length} prerequisite(s) · {item.objective_id ?? 'source use'}</Text>
            <Text style={s.small}>Reference {item.task_id.slice(0, 18)} · no action executed</Text>
          </View>)}
        {!report.review_operations.recommended_queue.length &&
          <Text style={s.small}>There are no current review tasks.</Text>}
      </Section>
      <Section title="Bounded human-review workload">
        <Text style={s.small}>Provide your own estimates for the task types above. Scheduling never approves a source.</Text>
        <View style={s.row}>
          <View style={styles.estimate}>
            <Text style={s.small}>Minutes per task</Text>
            <TextInput accessibilityLabel="Estimated human minutes per review task"
              style={styles.textField} value={minutesPerTask}
              onChangeText={setMinutesPerTask} maxLength={3}
              keyboardType="number-pad" editable={!working} />
          </View>
          <View style={styles.estimate}>
            <Text style={s.small}>Total review minutes</Text>
            <TextInput accessibilityLabel="Total human review time budget"
              style={styles.textField} value={budget} onChangeText={setBudget}
              maxLength={4} keyboardType="number-pad" editable={!working} />
          </View>
        </View>
        <TouchableOpacity accessibilityRole="button"
          accessibilityState={{ disabled: working || !report.review_operations.tasks_total }}
          disabled={working || !report.review_operations.tasks_total}
          style={[s.button, (working || !report.review_operations.tasks_total) && s.disabled]}
          onPress={() => { void analyze(true); }}>
          <Text style={s.buttonText}>Calculate finite review plan</Text>
        </TouchableOpacity>
        {report.review_portfolio && <Text style={s.small}>
          {report.review_portfolio.selected_count} proposed tasks, {report.review_portfolio.estimated_minutes} of {report.review_portfolio.budget_minutes} estimated minutes. Nothing persisted.
        </Text>}
      </Section>
      <Section title="Frontier safety and fault custody">
        <Text style={s.small}>{report.canonical_routes.node_count} canonical URLs · {report.canonical_routes.unreachable_pending} unreachable pending · {report.slice_simulation.projected_request_slots} hypothetical requests</Text>
        <Text style={s.small}>{report.dispatch_recovery.retained_event_count} retained events · {report.dispatch_recovery.uncertain_bytes} uncertain reserved bytes · no automatic recovery</Text>
        {report.dispatch_recovery.recovery_queue.slice(0, 8).map((item, i) =>
          <Text key={i} style={s.small}>{readable(item.severity)}: {readable(item.code)}</Text>)}
      </Section>
      <Section title="Jeeves and citation custody">
        <Text style={s.small}>{report.jeeves_handoff.citation_count} metadata-only citation anchors · {report.jeeves_handoff.task_count} held review tasks</Text>
        <Text style={s.small}>No source bodies were sent to a model. Every future source read needs a fresh consent and current policy check.</Text>
      </Section>
    </>}
  </View>;
}
