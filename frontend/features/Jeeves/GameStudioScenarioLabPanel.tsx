import React, { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Image, Text, TouchableOpacity, View } from 'react-native';
import {
  getStudioMirrorViews, getStudioScenarioDrafts,
  getStudioEngineTestManifest, getStudioSalesReferences,
  type StudioMirrorViews, type StudioScenarioDiscovery,
  type StudioEngineTestManifest, type StudioSalesCatalog,
  type StudioCampaign,
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
  const [lanes, setLanes] = useState(4);
  const [steps, setSteps] = useState(12);
  const [views, setViews] = useState<StudioMirrorViews | null>(null);
  const [drafts, setDrafts] = useState<StudioScenarioDiscovery | null>(null);
  const [tests, setTests] = useState<StudioEngineTestManifest | null>(null);
  const [sales, setSales] = useState<StudioSalesCatalog | null>(null);
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
        Six mirrored training perspectives: exploration, progress, safety, economy, adversary and boundary.
        The concurrent views below execute real source-bound reference simulations while Jeeves trains,
        but they are spectator samples, not the actual learner's episode frames or a native GPU renderer.
      </Text>
      <View style={group}>
        {button(watch ? 'Stop spectator lanes' : 'Watch parallel simulations', () => setWatch(current => !current), watch)}
        {[2, 4, 6].map(value => <React.Fragment key={value}>{button(value + ' angles', () => { setViews(null); setLanes(value); }, lanes === value)}</React.Fragment>)}
        {[8, 12, 24].map(value => <React.Fragment key={value}>{button(value + ' steps', () => { setViews(null); setSteps(value); }, steps === value)}</React.Fragment>)}
      </View>
      {loading && <View style={{ flexDirection: 'row', gap: 8 }}>
        <ActivityIndicator /><Text style={muted}>Executing bounded simulation snapshots…</Text>
      </View>}
      {!!error && <Text accessibilityRole="alert" style={{ color: '#f6a9a9' }}>{error}</Text>}
      {views && (
        <View style={{ gap: 8 }}>
          <Text style={muted} accessibilityLiveRegion="polite">
            {views.lanes.length} observed lanes · {views.workers_used} concurrent workers ·
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
                <Text style={muted}>{lane.rejected_actions} rejected commands · replay {lane.snapshot_digest.slice(0, 12)}</Text>
                <Text style={muted} numberOfLines={3}>
                  {Object.entries(lane.last_observation).slice(0, 5)
                    .map(([key, value]) => key + ': ' + value.toFixed(2)).join(' · ')}
                </Text>
              </View>;
            })}
          </View>
        </View>
      )}
      <View style={group}>
        {button('Draft from committed evidence', () => { void loadDrafts(); })}
        {button('Per-engine exhaustive checklist', () => { void loadTests(); })}
        {button('Sales-informed design references', () => { void loadSales(); })}
      </View>
      {drafts && <View style={{ gap: 7 }}>
        <Text style={heading}>AI scenario hypotheses · {drafts.measured_committed_rounds} recorded rounds</Text>
        <Text style={muted}>These are untested source-validated drafts. They do not change the project, train live weights or certify a successful scenario.</Text>
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
