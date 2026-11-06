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
  const [report, setReport] = useState<CrawlAtlasReport | null>(null);
  const [objective, setObjective] = useState<CrawlAtlasObjective | null>(null);
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
    setWorking(false); setReport(null); setObjective(null); setError(''); setNotice('');
  }, []);
  useEffect(() => {
    clear();
    return () => { epoch.current++; request.current?.abort(); request.current = null; };
  }, [revision, clear]);

  // Clear any source identities from a previous signed-in account. Async
  // responses are independently fenced against a concurrent account change.
  const authChanged = authRef.current !== getAuthToken();
  useEffect(() => {
    if (authChanged) {
      authRef.current = getAuthToken();
      clear();
    }
  }, [authChanged, clear]);

  const analyze = useCallback(async (allocate: boolean) => {
    if (busy.current) return;
    const goal: CrawlAtlasObjective | null = allocate ? objective : {
      objective_id: 'operator-research-goal', question: question.trim(),
      dimension, stage, priority: 0.9,
      minimum_reviewable_passages: 1, minimum_attested_groups: 1,
      max_source_age_seconds: 3600, required_terms: [], blocked_terms: [],
    };
    if (!session.consent_current || !goal || goal.question.length < 3) {
      setError('Supply a research question and a current capture consent grant.');
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
      objectives: [goal], retrieval_mode: mode,
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
      setObjective(goal);
      setNotice(allocate
        ? 'A bounded review plan was calculated, but no human was assigned and nothing was approved.'
        : 'Source-bound research completed. All external statements require human review.');
    } catch (exc) {
      if (controller.signal.aborted || submittedAt !== epoch.current ||
          sessionRevision !== revisionRef.current || auth !== getAuthToken()) return;
      setReport(null); setObjective(null);
      setError(exc instanceof Error ? exc.message : 'The Atlas inspection could not be verified.');
    } finally {
      if (submittedAt === epoch.current) {
        request.current = null; busy.current = false; setWorking(false);
      }
    }
  }, [session.session_id, session.consent_current, question, dimension,
    stage, mode, objective, report, minutesPerTask, budget]);

  const changeQuestion = (x: string) => { clear(); setQuestion(x); };
  const changeDimension = (x: Dimension) => { clear(); setDimension(x); };
  const changeStage = (x: Stage) => { clear(); setStage(x); };
  const changeMode = (x: Mode) => { clear(); setMode(x); };
  const ready = !working && !authChanged && session.consent_current && question.trim().length >= 3;

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
      <Text style={s.heading}>Evidence inspection</Text>
      <Text style={s.small}>Snapshot {report.snapshot_digest.slice(0, 16)} · {report.stages.length} audit stages · sequence {report.run_sequence}</Text>
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
