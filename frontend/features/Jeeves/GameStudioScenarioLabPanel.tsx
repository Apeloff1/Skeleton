import React, { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Image, Text, TouchableOpacity, View } from 'react-native';
import {
  getStudioMirrorViews, getStudioScenarioDrafts,
  getStudioEngineTestManifest, getStudioSalesReferences, runStudioEngineProbePage,
  getStudioShadowAudit, getMultifactorCapabilities,
  getMultifactorPlan, getMultifactorExperiments,
  type StudioMirrorViews, type StudioScenarioDiscovery,
  type StudioEngineTestManifest, type StudioSalesCatalog, type StudioEngineProbePage,
  type StudioCampaign, type StudioShadowAuditResult,
  type MultifactorControlManifest, type MultifactorExperimentPlan,
  type MultifactorVerifiedExperiments,
} from '../../src/product/gameStudioLearningClient';
import { getAuthToken } from '../../src/auth/gameforgeAuth';

/**
 * Spectator simulations are sampled, read-only, concurrent reference-game
 * executions, NOT frames from the current learner's actual training episode.
 * An approved real libretro framebuffer is a distinct, existing UI path.
 */
export default function GameStudioScenarioLabPanel({
  campaign, editor,
}: { campaign: StudioCampaign; editor: string }) {
  const [watch, setWatch] = useState(false);
  const [lanes, setLanes] = useState(10);
  const [steps, setSteps] = useState(12);
  const [views, setViews] = useState<StudioMirrorViews | null>(null);
  const [drafts, setDrafts] = useState<StudioScenarioDiscovery | null>(null);
  const [tests, setTests] = useState<StudioEngineTestManifest | null>(null);
  const [sales, setSales] = useState<StudioSalesCatalog | null>(null);
  const [probePages, setProbePages] = useState<StudioEngineProbePage[]>([]);
  const [probePending, setProbePending] = useState(false);
  const [shadowAngle, setShadowAngle] = useState('explore');
  const [shadow, setShadow] = useState<StudioShadowAuditResult | null>(null);
  const [shadowPending, setShadowPending] = useState(false);
  const [factors, setFactors] = useState<MultifactorControlManifest | null>(null);
  const [factorPlan, setFactorPlan] = useState<MultifactorExperimentPlan | null>(null);
  const [factorEvidence, setFactorEvidence] = useState<MultifactorVerifiedExperiments | null>(null);
  const [factorOffset, setFactorOffset] = useState(0);
  const [factorSteps, setFactorSteps] = useState(4);
  const [factorPending, setFactorPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const sample = useRef(0);
  const tenantToken = useRef(getAuthToken());
  const owner = useRef(campaign.campaign_id);

  useEffect(() => {
    sample.current = 0;
    setWatch(false);
    setViews(null);
    setDrafts(null);
    setTests(null);
    setProbePages([]);
    setShadow(null);
    setFactors(null);
    setFactorPlan(null);
    setFactorEvidence(null);
    setFactorOffset(0);
    owner.current = campaign.campaign_id;
    tenantToken.current = getAuthToken();
  }, [campaign.campaign_id]);

  useEffect(() => {
    if (!watch) return;
    let closed = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let running: AbortController | undefined;
    const campaignId = campaign.campaign_id;
    const token = tenantToken.current;
    const refresh = async () => {
      if (closed || token !== getAuthToken() || owner.current !== campaignId) return;
      running = new AbortController();
      setLoading(true);
      try {
        const result = await getStudioMirrorViews(
          campaignId, sample.current, lanes, steps, { signal: running.signal },
        );
        if (closed || token !== getAuthToken() || owner.current !== campaignId) return;
        setViews(result);
        setError(null);
        sample.current = (sample.current + 1) % 256;
      } catch (issue) {
        if (!closed && !running.signal.aborted) {
          setError(issue instanceof Error ? issue.message : 'The sampled simulator views could not be loaded.');
        }
      } finally {
        if (!closed) {
          setLoading(false);
          timer = setTimeout(() => { void refresh(); }, campaign.status === 'running' ? 9000 : 15000);
        }
      }
    };
    void refresh();
    return () => {
      closed = true;
      if (timer) clearTimeout(timer);
      running?.abort();
      setLoading(false);
    };
  }, [watch, campaign.campaign_id, campaign.status, lanes, steps]);

  const loadDrafts = async () => {
    setError(null);
    try {
      const result = await getStudioScenarioDrafts(campaign.campaign_id);
      if (owner.current === campaign.campaign_id && tenantToken.current === getAuthToken()) setDrafts(result);
    } catch (issue) {
      setError(issue instanceof Error ? issue.message : 'Cannot review scenario draft evidence.');
    }
  };
  const loadTests = async () => {
    setError(null);
    try {
      const result = await getStudioEngineTestManifest(editor);
      if (owner.current === campaign.campaign_id && tenantToken.current === getAuthToken()) setTests(result);
    } catch (issue) {
      setError(issue instanceof Error ? issue.message : 'Cannot read this engine test plan.');
    }
  };
  const probeEngine = async () => {
    if (probePending) return;
    const last = probePages[probePages.length - 1];
    const offset = last ? last.actions.next_offset : 0;
    if (offset === null) return;
    setProbePending(true);
    setError(null);
    try {
      const result = await runStudioEngineProbePage(editor, offset);
      if (owner.current !== campaign.campaign_id || tenantToken.current !== getAuthToken()) return;
      setProbePages(current => [...current, result]);
    } catch (issue) {
      setError(issue instanceof Error ? issue.message : 'The engine action probe failed.');
    } finally {
      setProbePending(false);
    }
  };
  const loadShadow = async (maxCycles: number) => {
    if (shadowPending) return;
    setShadowPending(true);
    setShadow(null);
    setError(null);
    try {
      const result = await getStudioShadowAudit(
        campaign.campaign_id, shadowAngle, maxCycles,
      );
      if (owner.current !== campaign.campaign_id ||
          tenantToken.current !== getAuthToken()) return;
      setShadow(result);
    } catch (issue) {
      setError(issue instanceof Error ? issue.message : 'Shadow scrutiny was not verified.');
    } finally {
      setShadowPending(false);
    }
  };
  const inspectFactors = async (task: 'catalog' | 'plan' | 'execute') => {
    if (factorPending) return;
    setFactorPending(true);
    setError(null);
    try {
      if (task === 'catalog') {
        const result=await getMultifactorCapabilities(campaign.campaign_id);
        if (owner.current === campaign.campaign_id && tenantToken.current===getAuthToken()) setFactors(result);
      } else if (task === 'plan') {
        const result=await getMultifactorPlan(campaign.campaign_id,factorOffset);
        if (owner.current === campaign.campaign_id && tenantToken.current===getAuthToken()) setFactorPlan(result);
      } else {
        const result=await getMultifactorExperiments(
          campaign.campaign_id,factorOffset,factorSteps,
        );
        if (owner.current === campaign.campaign_id && tenantToken.current===getAuthToken()) setFactorEvidence(result);
      }
    } catch (issue) {
      setError(issue instanceof Error ? issue.message : 'Multi-factor simulation evidence unavailable.');
    } finally {
      setFactorPending(false);
    }
  };
  const loadSales = async () => {
    setError(null);
    try {
      const result = await getStudioSalesReferences();
      if (owner.current === campaign.campaign_id && tenantToken.current === getAuthToken()) setSales(result);
    } catch (issue) {
      setError(issue instanceof Error ? issue.message : 'Sales-informed design references unavailable.');
    }
  };
  const button = (label: string, action: () => void, active = false) => (
    <TouchableOpacity
      accessibilityRole="button"
      onPress={action}
      style={{ paddingHorizontal: 12, paddingVertical: 9, borderRadius: 8,
        borderWidth: 1, borderColor: active ? '#6daefa' : '#8d98a4',
        backgroundColor: active ? '#233c62' : 'transparent' }}
    ><Text style={{ color: active ? '#fff' : '#c4d2df', fontWeight: '600' }}>{label}</Text></TouchableOpacity>
  );
  const heading = { color: '#f0f3fb', fontSize: 15, fontWeight: '700' as const };
  const muted = { color: '#b5c2d3', fontSize: 12 };
  const group = { flexDirection: 'row' as const, flexWrap: 'wrap' as const, gap: 8 };
  return (
    <View style={{ gap: 14, padding: 13, borderWidth: 1, borderColor: '#526173', borderRadius: 12 }}>
      <Text style={heading}>Advanced scenario laboratory · {editor.replace(/_/g, ' ')}</Text>
      <Text style={muted}>
        Ten mirror-room runs: exploration, progress, safety, economy, adversary, boundary,
        temporal, causal, perturbation and recovery. Each run undergoes ten scrutiny checks
        and produces ten source-derived numeric analysis bands.
        The concurrent views below execute real source-bound reference simulations while Jeeves trains,
        but they are spectator samples, not the actual learner's episode frames or a native GPU renderer.
      </Text>
      <View style={group}>
        {button(watch ? 'Stop spectator lanes' : 'Watch parallel simulations', () => setWatch(current => !current), watch)}
        {[2, 4, 6, 10].map(value => <React.Fragment key={value}>{button(value + ' angles', () => { setViews(null); setLanes(value); }, lanes === value)}</React.Fragment>)}
        {[8, 12, 24].map(value => <React.Fragment key={value}>{button(value + ' steps', () => { setViews(null); setSteps(value); }, steps === value)}</React.Fragment>)}
      </View>
      {loading && <View style={{ flexDirection: 'row', gap: 8 }}>
        <ActivityIndicator /><Text style={muted}>Executing bounded simulation snapshots…</Text>
      </View>}
      {!!error && <Text accessibilityRole="alert" style={{ color: '#f6a9a9' }}>{error}</Text>}
      {views && (
        <View style={{ gap: 8 }}>
          <Text style={muted} accessibilityLiveRegion="polite">
            {views.lanes.length} observed runs · {views.workers_used} concurrent workers ·
            {views.scrutiny_checked_runs * views.scrutiny_checks_per_run} passed scrutiny checks ·
            campaign committed round {views.campaign_cursor} · sample {views.sample}
          </Text>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }}>
            {views.lanes.map(lane => {
              const last = lane.frames[lane.frames.length - 1];
              const uri = last?.data_uri;
              const validImage = typeof uri === 'string'
                && uri.startsWith('data:image/png;base64,') && uri.length < 180000;
              return <View key={lane.angle} style={{
                width: 220, maxWidth: '100%', padding: 9,
                backgroundColor: '#162235', borderRadius: 9, gap: 5,
              }}>
                <Text style={heading}>{lane.angle.toUpperCase()}</Text>
                {validImage
                  ? <Image accessibilityLabel={lane.angle + ' sampled source state telemetry'}
                    resizeMode="contain" source={{ uri }}
                    style={{ width: 195, height: 130, borderRadius: 5 }} />
                  : <Text style={muted}>Numeric telemetry only; native image unavailable</Text>}
                <Text style={muted}>
                  Seed {lane.seed} · {lane.steps} executed steps · reward {lane.total_reward.toFixed(2)}
                </Text>
                <Text style={muted}>
                  {lane.accepted_actions} accepted · {lane.rejected_actions} rejected ·
                  {lane.productive_state_changes} productive state changes
                </Text>
                <Text style={muted}>
                  {lane.unique_gameplay_states} distinct gameplay states ·
                  {lane.replayed_action_applications} replayed action applications
                </Text>
                <Text style={muted}>Replay {lane.snapshot_digest.slice(0, 12)} ·
                  {lane.multispectral.passed_count}/10 independently replayed audit gates
                </Text>
                <View style={{ gap: 3 }}>
                  {Object.entries(lane.multispectral.spectral_channels).map(([band, data]) => (
                    <Text key={band} style={muted}>{band}: mean {data.mean.toFixed(3)}
                      {' · '}peak {data.maximum.toFixed(3)}
                    </Text>
                  ))}
                </View>
                <Text style={muted}>Reverse audit: {lane.multispectral.reverse_checkpoints.length} source checkpoints.
                  Derived telemetry, not RGB/depth/thermal sensor measurements.
                </Text>
                <Text style={muted} numberOfLines={3}>
                  {Object.entries(lane.last_observation).slice(0, 5)
                    .map(([key, value]) => key + ': ' + value.toFixed(2)).join(' · ')}
                </Text>
              </View>;
            })}
          </View>
        </View>
      )}
      <View style={{ gap: 8 }}>
        <Text style={heading}>Multi-factor combinatorial engine laboratory</Text>
        <Text style={muted}>
          Joint source-verified item, ability, weapon, tool, movement, style, expression,
          reaction, consequence, environment, ambience, music, and other
          factor challenges. Controls missing from this engine are explicitly unavailable;
          no fabricated audio or animation is used.
        </Text>
        <View style={group}>
          {button('Inspect executable factors', () => { void inspectFactors('catalog'); })}
          {button('Design triple interactions', () => { void inspectFactors('plan'); })}
          {[2,4].map(value => <React.Fragment key={value}>
            {button(value+' source steps', () => {
              setFactorSteps(value);setFactorEvidence(null);
            },factorSteps===value)}
          </React.Fragment>)}
          {button(factorPending ? 'Replaying factor worlds…' : 'Run two audited factor worlds',
            () => { void inspectFactors('execute'); })}
          {button('Next factor bank', () => {
            if (!factors || !factors.total_executable_axes) return;
            setFactorOffset(current => (current+8<factors.total_executable_axes ? current+8 : 0));
            setFactorPlan(null);setFactorEvidence(null);
          })}
        </View>
        {factors && <View style={{ gap: 3 }}>
          <Text style={muted}>
            {factors.total_executable_axes} executable axes · {factors.unsupported_category_count}
            unsupported categories · selected bank {factorOffset+1}–{Math.min(factorOffset+8,factors.total_executable_axes)}
          </Text>
          {factors.categories.map(item => <Text key={item.category} style={muted}>
            {item.status === 'executable_logic' ? '✓' : '—'} {item.category.replace(/_/g,' ')}
            {' · '}{item.status==='executable_logic'
              ? item.registered_controls.slice(0,4).join(', ') : 'no executable controls in this engine'}
          </Text>)}
        </View>}
        {factorPlan && <View style={{ gap: 3 }}>
          <Text style={heading}>Three-way verified design · {factorPlan.scenarios.length} legal variants</Text>
          <Text style={muted}>
            {factorPlan.covered_interactions}/{factorPlan.valid_interaction_opportunities} declared
            interaction witnesses covered ({(factorPlan.coverage_fraction*100).toFixed(1)}%);
            this is sampled covering design, not a full Cartesian proof.
          </Text>
          {factorPlan.coverage_by_interaction_order.map(order => (
            <Text key={order.interaction_order} style={muted}>
              {order.interaction_order}-way coverage:
              {' '}{order.selected_plan_witnesses}/{order.source_legal_offered_witnesses}
              {' offered interaction witnesses; '}{order.all_factors_active_witnesses}
              {' with every involved factor active'}
            </Text>
          ))}
          {factorPlan.scenarios.map(entry => <Text key={entry.index} style={muted}>
            #{entry.index+1} {entry.changed_axes.join(' + ')} ·
            {entry.new_coverage_witnesses} newly covered interactions
          </Text>)}
        </View>}
        {factorEvidence && <View style={{ gap: 4 }}>
          <Text style={heading}>Executed matched-seed experiments · {factorEvidence.scenarios_executed}</Text>
          <Text style={muted}>Read-only game execution: baseline versus combined source;
            each source undergoes its own audit. Separate operator-admitted CLI
            performs Q training and exports replay-verified neural candidate data.
          </Text>
          {factorEvidence.experiments.map(row => <View key={row.index} style={{
            padding: 7,borderColor:'#526173',borderWidth:1,borderRadius:7,gap:3,
          }}>
            <Text style={muted}>Combined: {row.axes.join(' + ')}</Text>
            <Text style={muted}>Selected engine actions: {row.all_selected_actions_accepted
              ? 'all accepted by the game' : 'some unavailable or rejected in this initial state'}
            </Text>
            {!!row.unexecuted_action_categories.length &&
              <Text style={{ color: '#f6c6a5' }}>Unexecuted modality controls:
                {' '}{row.unexecuted_action_categories.join(', ')}
              </Text>}
            <Text style={muted}>Observed reward difference {row.reward_delta.toFixed(3)} ·
              baseline {row.control_productive_changes} vs modified {row.variant_productive_changes} state changes
            </Text>
            {row.factor_ablation_receipts.map((ablation,i) =>
              <Text key={i} style={muted}>Remove {ablation.removed_axes.join(', ')}
                {' → reward contrast '}{ablation.reward_difference_to_joint.toFixed(3)}
              </Text>)}
            {row.pairwise_interaction_witness &&
              <Text style={muted}>Interaction {row.pairwise_interaction_witness.axes.join(' × ')}
                {' · measured difference-of-differences '}
                {row.pairwise_interaction_witness.difference_of_differences.toFixed(3)}
              </Text>}
            {row.factorial_scrutiny && <View style={{ gap: 3 }}>
              <Text style={heading}>
                Exhaustive source-intervention lattice · {row.factorial_scrutiny.source_replayed_corner_count}
                {' corner runs · '}{row.factorial_scrutiny.audited_checks_count} checked controls
              </Text>
              <Text style={muted}>
                {row.factorial_scrutiny.complete_seed_cubes}/{row.factorial_scrutiny.seed_count_requested}
                {' complete matched-seed cubes · '}
                {row.factorial_scrutiny.whole_joint_variant_examined
                  ? 'all factors of this joint variant tested'
                  : 'only selected factors of this variant examined'}
              </Text>
              {!!row.factorial_scrutiny.other_active_axes_not_examined.length &&
                <Text style={{ color: '#f6c6a5' }}>
                  Remaining active factors: {row.factorial_scrutiny.other_active_axes_not_examined.join(', ')}
                </Text>}
              {row.factorial_scrutiny.worst_seed_joint_return_delta!==null &&
                <Text style={muted}>Worst matched-seed return change:
                  {' '}{row.factorial_scrutiny.worst_seed_joint_return_delta.toFixed(3)}
                </Text>}
              {row.factorial_scrutiny.sensitivity.map((effect,index) => (
                <Text key={index} style={muted}>
                  {effect.order}-way {effect.factors.join(' × ')}:
                  {' '}{effect.mean.toFixed(4)} mean interaction effect
                  {' ('}{effect.min.toFixed(4)} to {effect.max.toFixed(4)}{')'}
                  {effect.sign_reversal_between_seeds ? ' · direction reverses across seeds' : ''}
                </Text>
              ))}
              {!!row.factorial_scrutiny.constraint_violations.length &&
                <Text style={{ color: '#f6c6a5' }}>
                  {row.factorial_scrutiny.constraint_violations.length}
                  {' illegal intermediate states; source-causal proof is incomplete.'}
                </Text>}
              <Text style={muted}>
                {row.factorial_scrutiny.reversed_order_independent_replays}
                {' independently reordered world executions · '}
                {row.factorial_scrutiny.reordered_action_scrutiny_runs}
                {' permuted action-sequence audits'}
              </Text>
              <Text style={muted}>
                {row.factorial_scrutiny.observed_action_order_mechanics_difference_count}
                {' contexts with order-dependent outcomes · '}
                {row.factorial_scrutiny.observed_action_order_regression_count}
                {' observed sequence regressions'}
              </Text>
              <Text style={muted}>
                Robust positive reward gain on tested seeds and action orders:
                {' '}{row.factorial_scrutiny.robust_joint_gain_under_tested_orders
                  ? 'yes, bounded evidence only' : 'not established'}
              </Text>
              {row.factorial_scrutiny.adversarial_reexamination_priority.recommended &&
                <Text style={{ color: '#f6c6a5' }}>
                  Further adversarial scrutiny recommended:
                  {' '}{row.factorial_scrutiny.adversarial_reexamination_priority.reasons
                    .map(reason => reason.replace(/_/g,' ')).join('; ')}
                  {' · priority '}{row.factorial_scrutiny.adversarial_reexamination_priority.score}/100
                </Text>}
              <Text selectable style={muted}>
                Independent lattice digest: {row.factorial_scrutiny.digest.slice(0,24)}
              </Text>
            </View>}
          </View>)}
        </View>}
      </View>
      <View style={{ gap: 8 }}>
        <Text style={heading}>Shadow-clone convergence room</Text>
        <Text style={muted}>Choose a parent perspective. Each cycle forks a real checkpoint into an isolated shadow, independently replays both branches, increases scrutiny, and records hash-chained step evidence. Ten consecutive cycles without new verified knowledge are required; a resource stop is inconclusive.</Text>
        <View style={group}>
          {['explore','progress','safety','economy','adversary','boundary',
            'temporal','causal','perturbation','recovery'].map(value =>
            <React.Fragment key={value}>
              {button(value, () => { setShadowAngle(value); setShadow(null); }, shadowAngle === value)}
            </React.Fragment>)}
        </View>
        <View style={group}>
          {button(shadowPending ? 'Scrutinizing shadow clones…' : 'Audit 12 cycles', () => { void loadShadow(12); })}
          {button('Audit up to 16 cycles', () => { void loadShadow(16); })}
        </View>
        {shadow && shadow.simulations.map(sim => (
          <View key={sim.angle} style={{ padding: 9, borderWidth: 1, borderColor: '#526173', borderRadius: 8, gap: 7 }}>
            <Text style={heading}>Shadow {sim.angle} · {sim.cycles_executed} audited cycles</Text>
            <Text style={muted} accessibilityLiveRegion="polite">
              {sim.observed_unique_semantic_behaviors} distinct verified behaviors ·
              {sim.observed_zero_novelty_streak}/10 consecutive dry cycles ·
              peak scrutiny +{sim.peak_additional_scrutiny_checks} gates
            </Text>
            <Text style={{ color: sim.saturation_within_tested_bounds ? '#b4e7cb' : '#f6c6a5' }}>
              {sim.saturation_within_tested_bounds
                ? 'No new behavior or policy gain detected for ten audited cycles within the tested bounds.'
                : 'Inconclusive: ' + sim.stop_reason.replace(/_/g, ' ')}
            </Text>
            <Text style={muted}>This viewer performs read-only source replay. It does not update live Q or neural weights. Separate operator-authorized training can audit policy-value convergence.</Text>
            {sim.receipts.map(receipt => (
              <View key={receipt.digest} style={{ paddingVertical: 5, gap: 2 }}>
                <Text style={muted}>
                  Cycle {receipt.cycle} · +{receipt.new_semantic_evidence_count} learned behaviors ·
                  dry streak {receipt.zero_novelty_streak} · {receipt.base_audits_passed}+{receipt.additional_checks_passed} passed audits
                </Text>
                <Text selectable style={muted}>
                  Fork {receipt.fork.fork_at_step} · parent {receipt.fork.parent_next_action}
                  {' → shadow '}{receipt.fork.shadow_alternative_action} ·
                  evidence {receipt.digest.slice(0,16)}
                </Text>
                <Text style={muted}>
                  Source-replayed steps {receipt.completed_cycle_game_steps} ·
                  scrutiny {receipt.scrutiny_checks.map(item => item.name).join(', ')}
                </Text>
                {receipt.cycle >= sim.cycles_executed - 1 && (
                  <View style={{ paddingLeft: 8, gap: 3 }}>
                    <Text style={muted}>Detailed primary and shadow source receipts</Text>
                    {[['primary',receipt.primary_step_receipts],
                      ['shadow',receipt.shadow_step_receipts]].map(([kind,steps]) => (
                      <View key={kind as string}>
                        <Text style={muted}>{String(kind).toUpperCase()}</Text>
                        {(steps as typeof receipt.primary_step_receipts).map(step => (
                          <Text selectable key={step.index} style={muted}>
                            #{step.index} {step.action} · {step.accepted ? 'accepted' : 'rejected'}
                            {' · reward '}{step.reward_total.toFixed(5)}
                            {' · state '}{Object.entries(step.observation_after)
                              .map(([k,v]) => k + '=' + v.toFixed(3)).join(', ')}
                            {' · transition '}{step.transition_digest.slice(0,16)}
                          </Text>
                        ))}
                      </View>
                    ))}
                  </View>
                )}
              </View>
            ))}
          </View>
        ))}
      </View>
      <View style={group}>
        {button('Draft from committed evidence', () => { void loadDrafts(); })}
        {button('Per-engine exhaustive checklist', () => { void loadTests(); })}
        {button(probePending ? 'Executing action replay…' : 'Run next 8 engine actions', () => { void probeEngine(); })}
        {button('Sales-informed design references', () => { void loadSales(); })}
      </View>
      {drafts && <View style={{ gap: 7 }}>
        <Text style={heading}>AI scenario hypotheses · {drafts.measured_committed_rounds} recorded rounds</Text>
        <Text style={muted}>
          {drafts.already_explored_rule_variants} previously explored source variants ·
          {drafts.repeated_scenarios_skipped} redundant candidate drafts avoided.
          Suggested changes begin locally before expanding to extreme rule values.
          No project mutation or production model promotion occurs here.
        </Text>
        {drafts.scenarios.map(row => (
          <View key={row.proposal.proposal_id} style={{ padding: 8, gap: 4, borderWidth: 1, borderColor: '#526173', borderRadius: 7 }}>
            <Text style={heading}>{row.proposal.proposal_id}</Text>
            <Text style={muted}>{row.proposal.reason} · {row.support}</Text>
            <Text selectable style={muted}>
              {row.proposal.operations.map(op => op.path + ' → ' + String(op.value)).join(', ')}
            </Text>
            <Text style={muted}>Source {row.variant_source_digest.slice(0, 14)} · Independent validation required</Text>
          </View>
        ))}
        {!drafts.scenarios.length && <Text style={muted}>No new feasible draft in the declared source bounds.</Text>}
      </View>}
      {tests && <View style={{ gap: 7 }}>
        <Text style={heading}>{tests.engine} · {tests.registered_action_count} declared actions · {tests.field_axes.length} rule axes</Text>
        <Text style={muted}>Exhaustive registered-control checklist, NOT exhaustive combinations of all game states. Status: {tests.execution_status}; verified passes: {tests.verified_passes}.</Text>
        {tests.field_axes.map(field => <Text key={field.name} style={muted}>
          {field.name}: {field.cases.map(x => String(x)).join(' / ')} · {field.checks.length} required field checks
        </Text>)}
        {tests.mandatory_checks.map(item => <Text key={item.id} style={muted}>☐ {item.id.replace(/_/g, ' ')}</Text>)}
        <Text selectable style={muted}>Registered actions: {tests.registered_actions.join(', ')}</Text>
      </View>}
      {!!probePages.length && <View style={{ gap: 8 }}>
        <Text style={heading}>Actual engine action probes · {probePages.reduce((sum, page) => sum + page.actions.count, 0)} executed</Text>
        <Text style={muted}>Each command is separately reset, executed and independently replayed. Invalid-in-initial-state actions are recorded as rejected, not successful gameplay. The full engine remains uncertified.</Text>
        {probePages.map(page => <View key={page.actions.start} style={{ gap: 3 }}>
          <Text style={heading}>Actions {page.actions.start + 1}–{page.actions.start + page.actions.count} of {page.actions.registered_action_count}</Text>
          {page.actions.action_probes.map(probe => <Text key={probe.action} style={muted}>
            {probe.accepted_in_initial_state ? '✓ accepted' : '◌ rejected in initial state'} · {probe.action} · independently replayed
          </Text>)}
        </View>)}
        {probePages[probePages.length - 1].actions.next_offset === null
          && <Text style={muted}>All declared actions visited. This does not establish complete state, native hardware or game quality coverage.</Text>}
      </View>}
      {sales && <View style={{ gap: 8 }}>
        <Text style={heading}>Ranked game design research · commercial signals, not game-quality labels</Text>
        {sales.entries.filter(item => item.editor === editor).concat(
          sales.entries.filter(item => item.editor !== editor).slice(0, 5)
        ).slice(0, 7).map(entry => <View key={entry.chart + entry.reference} style={{ gap: 2 }}>
          <Text style={muted}>{entry.reference} · rank #{entry.rank} · {entry.chart}</Text>
          <Text style={muted}>{entry.motif}</Text>
        </View>)}
        <Text style={muted}>Source charts: Nintendo worldwide lifetime units (June 2026); 2025 US dollar-sales ranking (Circana). Never compare different sales units or copy proprietary gameplay assets.</Text>
      </View>}
    </View>
  );
}
