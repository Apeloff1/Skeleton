/**
 * Forge-operator layout: accessible tab bar + active panel.
 * Presentational — OperatorScreen owns state and hooks.
 */
import React from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { C, TOUCH } from '../../skeletonForge/components/theme';
import {
  OPERATOR_TAB_HINTS,
  OPERATOR_TAB_LABELS,
  OPERATOR_TABS,
  tabA11yLabel,
  type OperatorTab,
} from '../operatorTabs';
import BeatsPanel, { type BeatsPanelProps } from './BeatsPanel';
import CockpitPanel, { type CockpitPanelProps } from './CockpitPanel';
import ComposeRunPanel, { type ComposeRunPanelProps } from './ComposeRunPanel';
import ErasPanel, { type ErasPanelProps } from './ErasPanel';
import PlansPanel, { type PlansPanelProps } from './PlansPanel';
import WalkPanel, { type WalkPanelProps } from './WalkPanel';
import RecoveryPanel, { type RecoveryPanelProps } from './RecoveryPanel';
import RunReportPanel, { type RunReportPanelProps } from './RunReportPanel';

export interface OperatorViewProps {
  tab: OperatorTab;
  onTab: (tab: OperatorTab) => void;
  compose: ComposeRunPanelProps;
  plans: PlansPanelProps;
  walk: WalkPanelProps;
  eras: ErasPanelProps;
  beats: BeatsPanelProps;
  cockpit: CockpitPanelProps;
  report: RunReportPanelProps;
  recovery: RecoveryPanelProps;
  notice?: string | null;
  testID?: string;
}

export function OperatorTabBar({ tab, onTab }: Pick<OperatorViewProps, 'tab' | 'onTab'>) {
  return (
    <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={st.tabs} accessibilityRole="tablist">
      {OPERATOR_TABS.map((t) => {
        const active = t === tab;
        return (
          <Pressable
            key={t}
            testID={`operator-tab-${t}`}
            onPress={() => onTab(t)}
            accessibilityRole="tab"
            accessibilityLabel={tabA11yLabel(t)}
            accessibilityState={{ selected: active }}
            aria-selected={active}
            style={({ pressed }) => [st.tab, active && st.tabActive, pressed && { opacity: 0.75 }]}
          >
            <Text style={[st.tabTxt, active && st.tabTxtActive]}>{OPERATOR_TAB_LABELS[t]}</Text>
          </Pressable>
        );
      })}
    </ScrollView>
  );
}

export default function OperatorView(props: OperatorViewProps) {
  const { tab, notice, testID } = props;
  return (
    <View style={st.root} testID={testID}>
      <View style={st.header}>
        <Text style={st.title} accessibilityRole="header">
          Forge Operator
        </Text>
        <Text style={st.subtitle}>{OPERATOR_TAB_HINTS[tab]}</Text>
      </View>
      <OperatorTabBar tab={tab} onTab={props.onTab} />
      {notice ? (
        <View style={st.notice} accessibilityRole="alert" testID="operator-notice">
          <Text style={st.noticeTxt}>{notice}</Text>
        </View>
      ) : null}
      <ScrollView contentContainerStyle={st.body} keyboardShouldPersistTaps="handled" testID={`operator-panel-${tab}`}>
        {tab === 'compose' ? <ComposeRunPanel {...props.compose} /> : null}
        {tab === 'plans' ? <PlansPanel {...props.plans} /> : null}
        {tab === 'walk' ? <WalkPanel {...props.walk} /> : null}
        {tab === 'eras' ? <ErasPanel {...props.eras} /> : null}
        {tab === 'beats' ? <BeatsPanel {...props.beats} /> : null}
        {tab === 'cockpit' ? <CockpitPanel {...props.cockpit} /> : null}
        {tab === 'report' ? <RunReportPanel {...props.report} /> : null}
        {tab === 'recovery' ? <RecoveryPanel {...props.recovery} /> : null}
      </ScrollView>
    </View>
  );
}

const st = StyleSheet.create({
  root: { flex: 1, backgroundColor: C.bg },
  header: { paddingHorizontal: 16, paddingTop: 14, paddingBottom: 6 },
  title: { color: C.textStrong, fontSize: 22, fontWeight: '900' },
  subtitle: { color: C.mute, fontSize: 13, marginTop: 2 },
  tabs: { paddingHorizontal: 12, paddingVertical: 8, gap: 8 },
  tab: {
    minHeight: TOUCH,
    paddingHorizontal: 14,
    borderRadius: 999,
    borderWidth: 1,
    borderColor: C.borderStrong,
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: C.cardAlt,
  },
  tabActive: { borderColor: C.green, backgroundColor: C.green + '1f' },
  tabTxt: { color: C.text, fontWeight: '700', fontSize: 13 },
  tabTxtActive: { color: C.textStrong },
  notice: {
    marginHorizontal: 16,
    borderWidth: 1,
    borderColor: C.amber,
    borderRadius: 10,
    padding: 10,
    backgroundColor: C.amber + '14',
  },
  noticeTxt: { color: C.amber, fontSize: 13, fontWeight: '600' },
  body: { padding: 16, paddingBottom: 48 },
});
