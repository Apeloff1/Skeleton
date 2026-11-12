/**
 * Dragon Advanced Decision Cockpit: read-only, source-bound action planning.
 * All inputs come from the canonical owner-fenced Atlas. No model, worker,
 * egress, review mutation, source text or publication authority exists here.
 */
import React, { useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator, Share, Text, TextInput, TouchableOpacity, View,
} from 'react-native';
import { getAuthToken } from '../../auth/gameforgeAuth';
import {
  getCrawl, type CrawlAtlasObjective, type CrawlAtlasReport,
  type CrawlSession,
} from '../../product/crawlerClient';
import {
  bindPilotSnapshot, requireCurrentPilotSnapshot,
} from './crawlerPilotContinuity';
import {
  buildAdvancedDecisionBoard, formatAdvancedDecisionBrief,
  type AdvancedDecisionBoard,
} from './dragonResearchDecisionEngine';
import s, { colors as C } from './CrawlerWorkspace.styles';

type Perspective = 'objectives' | 'resilience' | 'review';
type Props = {
  session: CrawlSession;
  report: CrawlAtlasReport;
  campaign: readonly CrawlAtlasObjective[];
};
const caption = { color: C.muted, fontSize: 12, lineHeight: 19 } as const;
const heading = { color: C.text, fontSize: 17, fontWeight: '700' as const };
const subheading = { color: C.text, fontSize: 14, fontWeight: '700' as const };
const padded = {
  padding: 12, gap: 7, borderWidth: 1, borderRadius: 12,
  borderColor: C.edge, backgroundColor: C.bg,
} as const;
const riskColor = {
  critical: C.red, high: '#facc15', review: C.green,
} as const;
const labels = {
  no_selected_evidence: 'No eligible selected evidence',
  host_concentration: 'Observed source-host concentration',
  host_loss: 'Selected host-loss scenario',
  possible_content_mirror: 'Possible source-content overlap',
  source_family_shortfall: 'Hypothetical source-family shortfall',
  query_unsupported: 'Research query may not be supported',
  source_policy_excluded: 'Some sources excluded by owner policy',
  security_forensic_hold: 'Security or privacy review outstanding',
  review_not_attested: 'Independent attestation still missing',
} as const;

function Action({ title, selected = false, disabled = false, onPress, testID }: {
  title: string; selected?: boolean; disabled?: boolean;
  onPress: () => void; testID?: string;
}) {
  return <TouchableOpacity
    testID={testID} accessibilityRole="button"
    accessibilityLabel={title} accessibilityState={{ selected, disabled }}
    disabled={disabled} onPress={onPress}
    style={[s.button, selected && { borderColor: C.accent,
      backgroundColor: '#283253' }, disabled && s.disabled]}>
    <Text style={s.buttonText}>{title}</Text>
  </TouchableOpacity>;
}
function Count({ label, number, note }: {
  label: string; number: string | number; note: string;
}) {
  return <View style={{ ...padded, flexBasis: 140, flexGrow: 1, minWidth: 0 }}>
    <Text style={caption}>{label}</Text>
    <Text style={{ ...heading, fontSize: 23 }}>{String(number)}</Text>
    <Text style={caption}>{note}</Text>
  </View>;
}
function integerText(value: string, min: number, max: number): number | null {
  if (!/^(0|[1-9]\d{0,3})$/.test(value)) return null;
  const n = Number(value);
  return Number.isSafeInteger(n) && n >= min && n <= max ? n : null;
}

export default function DragonResearchDecisionCockpit({
  session, report, campaign,
}: Props) {
  const [perspective, setPerspective] = useState<Perspective>('objectives');
  const [scenarioHost, setScenarioHost] = useState<string | null>(null);
  const [allScenarios, setAllScenarios] = useState(false);
  const [reviewBudget, setReviewBudget] = useState('90');
  const [perTaskMinutes, setPerTaskMinutes] = useState('12');
  const [showMore, setShowMore] = useState(false);
  const [sharing, setSharing] = useState(false);
  const [shareError, setShareError] = useState('');
  const [shareNotice, setShareNotice] = useState('');
  const shareLock = useRef(false);
  const shareAbort = useRef<AbortController | null>(null);
  const latestRef = useRef({ session, report });
  latestRef.current = { session, report };
  const inputsKey = (scenarioHost ?? '') + '|' + reviewBudget + '|' + perTaskMinutes;
  const inputsRef = useRef(inputsKey);
  inputsRef.current = inputsKey;
  useEffect(() => {
    // A review-budget or host scenario change invalidates the share payload
    // even if the underlying Atlas source digest remains unchanged.
    shareAbort.current?.abort();
  }, [inputsKey]);
  // Changing source revision or Atlas receipt invalidates the scenario,
  // previous plan and all in-flight share operations.
  useEffect(() => {
    setScenarioHost(null); setAllScenarios(false); setShowMore(false);
    setShareError(''); setShareNotice('');
    shareAbort.current?.abort();
    return () => { shareAbort.current?.abort(); };
  }, [session.session_id, session.version, report.dashboard_digest]);

  const budget = integerText(reviewBudget, 15, 480);
  const cost = integerText(perTaskMinutes, 5, 120);
  let board: AdvancedDecisionBoard | null = null;
  let inputError = '';
  try {
    if (budget === null || cost === null) {
      throw new RangeError('Choose 15–480 review minutes and 5–120 minutes per task.');
    }
    board = buildAdvancedDecisionBoard(
      report, session, campaign, scenarioHost, budget, cost,
    );
  } catch (cause) {
    inputError = cause instanceof Error
      ? cause.message : 'The decision view could not be qualified.';
  }

  const shareBrief = async () => {
    const current = latestRef.current;
    const assessed = board;
    if (!assessed || shareLock.current || !session.consent_current) return;
    shareLock.current = true;
    const abort = new AbortController();
    shareAbort.current = abort;
    const token = getAuthToken();
    const submittedInputs = inputsKey;
    setSharing(true); setShareError(''); setShareNotice('');
    try {
      const witness = bindPilotSnapshot(
        current.session, current.report, current.session.version,
      );
      // A current session read is required even for bounded metadata.
      // It is not a fresh source-policy grant or a new Atlas inspection.
      const latest = await getCrawl(current.session.session_id, abort.signal);
      if (abort.signal.aborted || token !== getAuthToken()
        || submittedInputs !== inputsRef.current
        || latestRef.current.report.dashboard_digest !== current.report.dashboard_digest
        || latestRef.current.session.version !== current.session.version) return;
      requireCurrentPilotSnapshot(witness, current.session, latest, current.report);
      const message = formatAdvancedDecisionBrief(assessed);
      if (abort.signal.aborted || token !== getAuthToken()
        || submittedInputs !== inputsRef.current) return;
      await Share.share({
        title: 'Dragon source-only advanced research decision brief',
        message,
      });
      if (!abort.signal.aborted && token === getAuthToken()) {
        setShareNotice('Historical metadata was handed to the share interface. No source, training, review or release permission was granted.');
      }
    } catch {
      if (!abort.signal.aborted && token === getAuthToken()) {
        setShareError('The decision brief was not shared. Reinspect current owner permissions and rerun Atlas before exporting.');
      }
    } finally {
      shareLock.current = false;
      if (shareAbort.current === abort) shareAbort.current = null;
      if (token === getAuthToken()) setSharing(false);
    }
  };

  const scenarios = report.retrieval_robustness.host_ablation;
  const listed = allScenarios ? scenarios.slice(0, 32) : scenarios.slice(0, 7);
  return <View testID="dragon-advanced-cockpit" style={[s.card, { gap: 15 }]}>
    <Text style={s.eyebrow}>DRAGON / ADVANCED INTELLIGENCE</Text>
    <Text style={s.heading} accessibilityRole="header">
      Research decision cockpit
    </Text>
    <Text style={s.small}>
      Verified snapshot lineage in; deterministic operational triage out.
      This is a local review projection—not a verified claim, a model judgment
      or new web access. All source rights and reviewer decisions remain external.
    </Text>
    {inputError ? <View style={padded} testID="dragon-advanced-invalid">
      <Text style={s.error}>{inputError}</Text>
      <Text style={caption}>Correct the bounded review inputs to restore the
        decision matrix. No partial or default plan will be displayed.</Text>
      <Text style={caption}>Human review budget (15–480 minutes)</Text>
      <TextInput accessibilityLabel="Advanced human review time budget"
        keyboardType="number-pad" maxLength={3} value={reviewBudget}
        onChangeText={setReviewBudget}
        style={{ ...padded, color: C.text, minHeight: 46 }} />
      <Text style={caption}>Human minutes per review task (5–120)</Text>
      <TextInput accessibilityLabel="Advanced minutes per review task"
        keyboardType="number-pad" maxLength={3} value={perTaskMinutes}
        onChangeText={setPerTaskMinutes}
        style={{ ...padded, color: C.text, minHeight: 46 }} />
      {scenarioHost && <Action title="Clear unsupported host scenario"
        onPress={() => setScenarioHost(null)} />}
    </View> : board && <>
      <View style={s.row}>
        <Count label="Priority investigation gaps"
          number={board.criticalObjectives}
          note="No selected evidence or host-loss scenario" />
        <Count label="Additional elevated concerns"
          number={board.highObjectives}
          note="Unverified host / content / policy findings" />
        <Count label="Review time provisioned"
          number={board.budgetUsedMinutes + ' min'}
          note={board.budgetedTasks + ' immediate tasks, not assigned'} />
        <Count label="Source use held"
          number={board.sourcePolicyExcluded}
          note={board.sourcePolicyIncluded + ' included as observations'} />
      </View>

      <View style={s.row}>
        <Action title="Objective decisions" selected={perspective === 'objectives'}
          testID="dragon-advanced-objectives" onPress={() => setPerspective('objectives')} />
        <Action title="Host-loss stress" selected={perspective === 'resilience'}
          testID="dragon-advanced-resilience" onPress={() => setPerspective('resilience')} />
        <Action title="Review operations" selected={perspective === 'review'}
          testID="dragon-advanced-review" onPress={() => setPerspective('review')} />
      </View>

      {perspective === 'objectives' && <View style={{ gap: 10 }}>
        <Text style={heading}>Objective evidence decisions</Text>
        <Text style={caption}>
          Sorted by missing observed passages, source dependence and operator
          priority. Observed source counts are never independently attested groups.
        </Text>
        {board.objectiveDecisions.map(item =>
          <View key={item.objectiveId} style={padded}
            testID={'dragon-advanced-goal-' + item.objectiveId}>
            <View style={[s.row, { justifyContent: 'space-between' }]}>
              <Text style={subheading}>{item.objectiveId} · {item.dimension}</Text>
              <Text style={{ ...subheading, color: riskColor[item.severity] }}>
                {item.severity.toUpperCase()}
              </Text>
            </View>
            <Text style={caption}>
              {item.selectedPassages} selected passages
              {item.targetPassages === null ? '' : ' / ' + item.targetPassages + ' targeted'}
              {' · ' + item.observedSources + ' source records · '
                + item.observedHosts + ' observed hosts'}
            </Text>
            <Text style={caption}>
              {item.distinctContentFamilies} exact-content families · target
              {' ' + item.targetAttestedGroups} independently attested group(s)
              {' · 0 attested'}
            </Text>
            {item.apparentPassageDeficit !== null &&
              item.apparentPassageDeficit > 0 &&
              <Text style={s.error}>Observed passage deficit: {item.apparentPassageDeficit}</Text>}
            {item.reasons.map(reason =>
              <Text key={reason} style={caption}>{'• ' + labels[reason]}</Text>)}
            <Text style={caption}>
              {item.reviewTaskCount} review leads · no automated verification
            </Text>
          </View>)}
        {!board.objectiveCount && <Text style={caption}>
          No qualified operator objectives. Run a current Atlas campaign first.
        </Text>}
      </View>}

      {perspective === 'resilience' && <View style={{ gap: 10 }}>
        <Text style={heading}>Counterfactual host loss</Text>
        <Text style={caption}>
          Select one observed host to inspect the canonical Atlas ablation
          receipt. This simulation does not remove sources, rerank results,
          change permissions, or prove copied authorship.
        </Text>
        <View style={s.row}>
          <Action title="No host removed" selected={scenarioHost === null}
            onPress={() => setScenarioHost(null)} />
          {listed.map(item =>
            <Action key={item.removed_host}
              title={'Remove ' + item.removed_host}
              selected={scenarioHost === item.removed_host}
              onPress={() => setScenarioHost(item.removed_host)} />)}
          {scenarios.length > 7 &&
            <Action title={allScenarios ? 'Show fewer hosts' : 'Show all hosts'}
              onPress={() => setAllScenarios(!allScenarios)} />}
        </View>
        <View style={s.row}>
          <Count label="Observed selected passages"
            number={board.observedPassages}
            note={board.observedHosts + ' distinct observed hosts'} />
          <Count label="Exact-content families"
            number={board.sourceFamilies}
            note="Not independent corroboration" />
          <Count label="Possible mirror pairs"
            number={board.suspectedMirrors}
            note="Human lineage audit is required" />
          <Count label="Unresolved robots origins"
            number={board.unresolvedRobotsOrigins}
            note="No network authorization implied" />
        </View>
        {scenarioHost && <>
          <Text style={subheading}>
            Consequences of removing {scenarioHost}
          </Text>
          {board.objectiveDecisions.filter(item =>
            item.lostAllEvidenceUnderScenario || item.scenarioHostCountDropsToOne,
          ).map(item =>
            <Text key={item.objectiveId}
              style={item.lostAllEvidenceUnderScenario ? s.error : s.small}>
              {item.objectiveId} · {item.lostAllEvidenceUnderScenario
                ? 'no observed evidence survives' : 'one observed host remains'}
            </Text>)}
          {!board.objectiveDecisions.some(item =>
            item.lostAllEvidenceUnderScenario || item.scenarioHostCountDropsToOne,
          ) && <Text style={caption}>No objective was flagged by this particular
            host-loss receipt. Other evidence/rights limits still apply.</Text>}
        </>}
        <Text style={caption}>
          Unsettled network bytes: {board.uncertainBytes} · pending dispatch:
          {' ' + (board.pendingDispatch ? 'yes' : 'no')}.
          All observations remain subject to fresh backend checks.
        </Text>
      </View>}

      {perspective === 'review' && <View style={{ gap: 10 }}>
        <Text style={heading}>Finite human-review operations</Text>
        <Text style={caption}>
          Review slots are estimates only: no assignment, dependency completion,
          evidence approval, model training or write occurs. A predecessor is
          never silently considered complete.
        </Text>
        <View style={s.row}>
          <View style={{ flexGrow: 1, flexBasis: 142, minWidth: 0, gap: 5 }}>
            <Text style={caption}>Total operator minutes (15–480)</Text>
            <TextInput testID="dragon-advanced-review-budget"
              accessibilityLabel="Advanced human review time budget"
              keyboardType="number-pad" maxLength={3}
              style={{ ...padded, color: C.text, minHeight: 46 }}
              value={reviewBudget} onChangeText={setReviewBudget} />
          </View>
          <View style={{ flexGrow: 1, flexBasis: 142, minWidth: 0, gap: 5 }}>
            <Text style={caption}>Minutes per task (5–120)</Text>
            <TextInput testID="dragon-advanced-task-minutes"
              accessibilityLabel="Advanced minutes per review task"
              keyboardType="number-pad" maxLength={3}
              style={{ ...padded, color: C.text, minHeight: 46 }}
              value={perTaskMinutes} onChangeText={setPerTaskMinutes} />
          </View>
        </View>
        <View style={s.row}>
          <Count label="Budgeted for immediate review"
            number={board.budgetedTasks}
            note={board.budgetUsedMinutes + ' of ' + board.estimatedReviewBudgetMinutes + ' min'} />
          <Count label="Dependency-held"
            number={board.heldTasks}
            note="Must finish prerequisites with the real reviewer" />
          <Count label="Other review tasks"
            number={board.unlistedTasks}
            note="Not included in the bounded queue" />
        </View>
        {board.reviewDecisions.slice(0, showMore ? 48 : 12).map(task =>
          <View key={task.taskId} style={padded}>
            <View style={[s.row, { justifyContent: 'space-between' }]}>
              <Text style={subheading}>
                {task.risk.toUpperCase()} · {task.type.replaceAll('_', ' ')}
              </Text>
              <Text style={caption}>{task.estimatedMinutes} min</Text>
            </View>
            <Text style={caption}>
              Task {task.taskId.slice(0, 22)} · {task.objectiveId ?? 'source policy'}
            </Text>
            <Text style={task.status === 'dependency_held' ? s.error : s.small}>
              {task.status === 'budgeted_now'
                ? 'Eligible for hypothetical immediate human review'
                : task.status === 'ready_but_unbudgeted'
                  ? 'Ready but outside this operator budget'
                  : 'Held for current backend review dependencies'}
              {' · ' + task.predecessorCount + ' predecessor(s)'}
            </Text>
          </View>)}
        {board.reviewDecisions.length > 12 &&
          <Action title={showMore ? 'Show fewer review tasks' : 'Show more review tasks'}
            onPress={() => setShowMore(!showMore)} />}
        {!board.reviewDecisions.length &&
          <Text style={caption}>No recommended review tasks in this snapshot.</Text>}
      </View>}

      <View style={padded}>
        <Text style={subheading}>Owner-scoped historical brief</Text>
        <Text style={caption}>
          Share only digest-bound counts, objective IDs and bounded human-review
          estimates—never source URLs, passages, credentials or drafts.
          An authenticated current-session read is required before opening
          the device share sheet.
        </Text>
        <Action title={sharing ? 'Verifying current session…' : 'Share advanced decision brief'}
          disabled={sharing || !session.consent_current}
          testID="dragon-advanced-share" onPress={() => { void shareBrief(); }} />
        {sharing && <ActivityIndicator color={C.accent} />}
        {!!shareError && <Text style={s.error}>{shareError}</Text>}
        {!!shareNotice && <Text style={s.small}>{shareNotice}</Text>}
        <Text style={caption}>
          Receipt {board.qualificationDigest.slice(0, 16)} · source policy
          must be independently rechecked before any factual claim.
          Release authorized: NO.
        </Text>
      </View>
    </>}
  </View>;
}
