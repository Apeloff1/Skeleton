/**
 * Build plan viewer: structure, era linkage and status for the plan Jeeves
 * hands the forge. The enemy mix is one roving tab stop (arrow keys).
 * Actions continue the designer flow: era viewer, forge run, questionnaire.
 */
import React from 'react';
import { ActivityIndicator, StyleSheet, Text, View } from 'react-native';
import { gridMove, readKey, rovingTabIndex, tabIndexProp, useRovingIndex, webKeyProps, type KeyEventLike } from '../a11y';
import { humanize } from '../graph';
import { describePlan, formatSeconds, formatSlack, noteKindLabel, planStatus, planView } from '../plan';
import type { EraRow, RunPayload } from '../types';
import { Banner, Button, Card, Meter, SectionTitle, StatusPill } from './primitives';
import { C, TONE_COLOR } from './theme';

/** Next mix-row index for a key, or null when the key does not move. */
export function planMixKey(index: number, event: KeyEventLike, count: number): number | null {
  const { key, ctrl } = readKey(event);
  const next = gridMove(index, key, { cols: 1, count, ctrl });
  if (next === null || next === index) return null;
  return next;
}

export interface PlanViewerProps {
  payload: RunPayload | null;
  eras?: EraRow[];
  pinnedEra?: string | null;
  running?: boolean;
  error?: string | null;
  /** When true, the drafting spinner is omitted. The status text remains. */
  reduceMotion?: boolean;
  onViewEra?: (era: string) => void;
  /** Forge run: walk, materialise, playtest. */
  onViewRun?: () => void;
  onBack?: () => void;
  testID?: string;
}

export default function PlanViewer({
  payload, eras = [], pinnedEra = null, running = false, error = null, reduceMotion = false,
  onViewEra, onViewRun, onBack, testID,
}: PlanViewerProps) {
  const view = React.useMemo(() => planView(payload, eras, pinnedEra), [payload, eras, pinnedEra]);
  const status = React.useMemo(() => planStatus(payload, running, view), [payload, running, view]);
  const [mixActive, setMixActive] = useRovingIndex(view.mix.length);
  const mixRefs = React.useRef<({ focus?: () => void } | null)[]>([]);
  const mixViaKey = React.useRef(false);
  React.useEffect(() => {
    if (!mixViaKey.current) return;
    mixViaKey.current = false;
    mixRefs.current[mixActive]?.focus?.();
  }, [mixActive]);

  const summary = describePlan(view);
  const eraId = view.link.planEra ?? view.era;
  const onMixKey = (event: KeyEventLike) => {
    const next = planMixKey(mixActive, event, view.mix.length);
    if (next === null) return;
    event.preventDefault?.();
    mixViaKey.current = true;
    setMixActive(next);
  };

  return (
    <View testID={testID ?? 'plan-viewer'}>
      <SectionTitle hint="Questionnaire → plan → walk → materialise → play">🗺 Build plan</SectionTitle>
      <View accessibilityLiveRegion="polite" style={st.statusRow}>
        <StatusPill tone={status.tone} label={status.label} testID="plan-status" />
        {running && !reduceMotion ? <ActivityIndicator color={C.accent} accessibilityLabel="Drafting the plan" /> : null}
      </View>
      <Text style={st.stages}>
        {status.stages.map((s) => `${s.name} ${s.status}`).join(' · ')}
      </Text>
      {error ? <Banner tone="bad" testID="plan-error">{error}</Banner> : null}

      {!view.present ? (
        <Card>
          <Text style={st.lead}>
            {running
              ? 'Jeeves is drafting the plan. Era, room bias, enemy mix and the thermal veto land with the forge run.'
              : 'No plan yet. Finish the questionnaire and forge. The plan Jeeves writes — era, room bias, enemy mix, veto — appears here, linked to the era viewer.'}
          </Text>
          <View style={st.actions}>
            {onBack ? <Button label="Back to questionnaire" tone="secondary" compact onPress={onBack} testID="plan-back" /> : null}
            {onViewRun ? <Button label="Open forge run" tone="ghost" compact onPress={onViewRun} a11yHint="Opens the walk, materialise and playtest" testID="plan-open-run" /> : null}
          </View>
        </Card>
      ) : (
        <>
          <Card label={summary} testID="plan-summary">
            <Text style={st.kicker}>ERA LINK</Text>
            <Text style={st.era} accessibilityRole="header">{view.eraLabel}</Text>
            <Banner tone={view.link.tone} testID="plan-era-link">
              {view.link.label}
              {view.link.honoursPin === true ? ' Honours the pinned era.' : ''}
              {view.link.honoursPin === false ? ' Does not honour the pinned era.' : ''}
            </Banner>
            <Text style={st.small}>{view.adaptLabel}. {view.adaptDetail}</Text>
            <View style={st.facts}>
              <Fact k="Slack" v={formatSlack(view.slack)} testID="plan-slack" />
              <Fact k="Room bias" v={`${view.biasGlyph} ${view.biasLabel}`} />
              <Fact k="Spawn" v={view.armed === null ? '—' : view.armed ? 'armed' : 'unarmed'} />
              <Fact k="Extract" v={view.extractLate === null ? '—' : view.extractLate ? 'late' : 'early'} />
              <Fact k="Seed" v={view.seed ?? '—'} mono />
              <Fact k="Authored" v={view.authored ?? '—'} />
            </View>
            {view.slack !== null ? (
              <Meter ratio={view.slack} color={TONE_COLOR[view.adaptTone]} label={`Slack ${formatSlack(view.slack)} of collapse time left`} height={8} />
            ) : (
              <Text style={st.small}>Slack is unknown because there was no prior walk.</Text>
            )}
            <Text style={st.small} testID="plan-veto">
              {view.veto.label}
              {view.veto.budgetS !== null ? ` (${formatSeconds(view.veto.spanS)} / ${formatSeconds(view.veto.budgetS)})` : ''}
            </Text>
            {view.oracleText ? <Text style={st.small}>Oracle: {view.oracleText}</Text> : null}
            {view.briefing ? <Text style={st.brief}>{view.briefing}</Text> : null}
            <View style={st.actions}>
              {onViewEra && eraId ? (
                <Button label="Open era" tone="primary" compact onPress={() => onViewEra(eraId)} a11yHint={`Open ${view.eraLabel} in the era viewer`} testID="plan-open-era" />
              ) : null}
              {onViewRun ? (
                <Button label="Open forge run" tone="secondary" compact onPress={onViewRun} a11yHint="Opens the walk, materialise and playtest for this plan" testID="plan-open-run" />
              ) : null}
              {onBack ? <Button label="Back to questionnaire" tone="ghost" compact onPress={onBack} testID="plan-back" /> : null}
            </View>
          </Card>

          <Card>
            <Text style={st.cardTitle} accessibilityRole="header">Enemy mix</Text>
            <Text style={st.small}>{view.totalEnemies} enemies · naive combat {formatSeconds(view.naiveCombatS)}. Arrow keys move between tiers.</Text>
            <View accessibilityRole="list" accessibilityLabel={`Enemy mix, ${view.totalEnemies} enemies`} testID="plan-mix">
              {view.mix.map((row, i) => {
                const ttk = row.ttkS === null ? 'time to kill unknown' : `time to kill ${row.ttkS} seconds, subtotal ${row.subtotalS} seconds`;
                return (
                  <View
                    key={row.tier}
                    ref={(n) => { mixRefs.current[i] = n; }}
                    testID={`plan-mix-${row.tier}`}
                    accessible
                    accessibilityLabel={`${row.label}, count ${row.count}, ${ttk}`}
                    {...tabIndexProp(rovingTabIndex(i, mixActive))}
                    {...webKeyProps(onMixKey)}
                    style={[st.mixRow, i === mixActive && st.mixActive]}
                  >
                    <Text style={st.mixName} importantForAccessibility="no">{row.label}</Text>
                    <Text style={st.mixCount} importantForAccessibility="no">{row.count}</Text>
                    <Text style={st.mixMeta} importantForAccessibility="no">{row.ttkS === null ? '—' : `${row.ttkS}s`}</Text>
                  </View>
                );
              })}
            </View>
          </Card>

          {view.recipes.length ? (
            <Card label={`Recipes: ${view.recipes.map((r) => humanize(r)).join(', ')}`}>
              <Text style={st.cardTitle}>Recipes</Text>
              <Text style={st.small}>{view.recipes.map((r) => humanize(r)).join(', ')}</Text>
            </Card>
          ) : null}

          {view.notes.length ? (
            <Card>
              <Text style={st.cardTitle} accessibilityRole="header">Notes</Text>
              <View accessibilityRole="list" accessibilityLabel={`${view.notes.length} plan notes`}>
                {view.notes.map((n, i) => (
                  <Text key={`${n.kind}-${i}`} style={st.note} accessibilityLabel={`${noteKindLabel(n)}: ${n.text}`} testID={`plan-note-${i}`}>
                    {noteKindLabel(n)} · {n.text}
                  </Text>
                ))}
              </View>
            </Card>
          ) : null}
        </>
      )}
    </View>
  );
}

function Fact({ k, v, mono, testID }: { k: string; v: string; mono?: boolean; testID?: string }) {
  return (
    <View style={st.fact} accessible accessibilityLabel={`${k}: ${v}`} testID={testID}>
      <Text style={st.factK} importantForAccessibility="no">{k}</Text>
      <Text style={[st.factV, mono && st.mono]} importantForAccessibility="no" numberOfLines={1}>{v}</Text>
    </View>
  );
}

const st = StyleSheet.create({
  statusRow: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 6 },
  stages: { color: C.dim, fontSize: 11, marginBottom: 8 },
  lead: { color: C.mute, fontSize: 13, lineHeight: 19 },
  kicker: { color: C.mute, fontSize: 11, fontWeight: '800', letterSpacing: 1 },
  era: { color: C.textStrong, fontSize: 22, fontWeight: '900', marginBottom: 6 },
  small: { color: C.mute, fontSize: 12, marginTop: 4, lineHeight: 17 },
  brief: { color: C.text, fontSize: 14, marginTop: 8, lineHeight: 20 },
  facts: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 8 },
  fact: { backgroundColor: C.cardAlt, borderRadius: 8, borderWidth: 1, borderColor: C.border, paddingHorizontal: 10, paddingVertical: 6, minWidth: 92, flexGrow: 1 },
  factK: { color: C.dim, fontSize: 10, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 0.6 },
  factV: { color: C.textStrong, fontSize: 14, fontWeight: '700', marginTop: 2 },
  mono: { fontFamily: 'monospace', fontSize: 12 },
  actions: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 12 },
  cardTitle: { color: C.textStrong, fontSize: 14, fontWeight: '800' },
  mixRow: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: C.border, minHeight: 44 },
  mixActive: { backgroundColor: C.accent + '14' },
  mixName: { color: C.text, fontSize: 14, fontWeight: '700', flex: 1 },
  mixCount: { color: C.textStrong, fontSize: 16, fontWeight: '800', minWidth: 24, textAlign: 'right' },
  mixMeta: { color: C.dim, fontSize: 12, minWidth: 48, textAlign: 'right' },
  note: { color: C.text, fontSize: 12, lineHeight: 18, marginTop: 6 },
});
