/**
 * Skeleton Forge cockpit layout: accessible tab bar + the active panel.
 * Pure — every panel's data arrives via props so the whole screen renders
 * deterministically in tests; ForgeCockpitScreen wires the live hooks.
 */
import React from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import {
  COCKPIT_TAB_HINTS, COCKPIT_TAB_LABELS, COCKPIT_TABS, tabA11yLabel, type CockpitTab, type TabBadge,
} from '../cockpitScreen';
import CockpitConsole, { type CockpitConsoleProps } from './CockpitConsole';
import ComposePanel, { type ComposePanelProps } from './ComposePanel';
import EraViewer, { type EraViewerProps } from './EraViewer';
import ForgeRunPanel, { type ForgeRunPanelProps } from './ForgeRunPanel';
import QuestionnaireFlow, { type QuestionnaireFlowProps } from './QuestionnaireFlow';
import { C, TONE_COLOR, TOUCH } from './theme';

export interface ForgeCockpitViewProps {
  tab: CockpitTab;
  onTab: (tab: CockpitTab) => void;
  badges: Record<CockpitTab, TabBadge>;
  questionnaire: QuestionnaireFlowProps;
  compose: ComposePanelProps;
  run: ForgeRunPanelProps;
  eras: EraViewerProps;
  console: CockpitConsoleProps;
  /** Optional offline/backend banner shown above every tab. */
  notice?: string | null;
  testID?: string;
}

export function CockpitTabBar({ tab, onTab, badges }: Pick<ForgeCockpitViewProps, 'tab' | 'onTab' | 'badges'>) {
  return (
    <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={st.tabs} accessibilityRole="tablist">
      {COCKPIT_TABS.map((t) => {
        const active = t === tab;
        const badge = badges[t];
        return (
          <Pressable
            key={t}
            testID={`cockpit-tab-${t}`}
            onPress={() => onTab(t)}
            accessibilityRole="tab"
            accessibilityLabel={tabA11yLabel(t, badge)}
            accessibilityState={{ selected: active }}
            aria-selected={active}
            style={({ pressed }) => [st.tab, active && st.tabActive, pressed && { opacity: 0.75 }]}
          >
            <Text style={[st.tabTxt, active && st.tabTxtActive]}>{COCKPIT_TAB_LABELS[t]}</Text>
            {badge.text ? (
              <View style={[st.badge, { borderColor: TONE_COLOR[badge.tone] }]} importantForAccessibility="no-hide-descendants">
                <Text style={[st.badgeTxt, { color: TONE_COLOR[badge.tone] }]}>{badge.text}</Text>
              </View>
            ) : null}
          </Pressable>
        );
      })}
    </ScrollView>
  );
}

export default function ForgeCockpitView(props: ForgeCockpitViewProps) {
  const { tab, notice, testID } = props;
  return (
    <View style={st.root} testID={testID}>
      <View style={st.header}>
        <Text style={st.title} accessibilityRole="header">Skeleton Forge</Text>
        <Text style={st.subtitle}>{COCKPIT_TAB_HINTS[tab]}</Text>
      </View>
      <CockpitTabBar tab={tab} onTab={props.onTab} badges={props.badges} />
      {notice ? (
        <View style={st.notice} accessibilityRole="alert" testID="cockpit-notice">
          <Text style={st.noticeTxt}>{notice}</Text>
        </View>
      ) : null}
      <ScrollView contentContainerStyle={st.body} keyboardShouldPersistTaps="handled" testID={`cockpit-panel-${tab}`}>
        {tab === 'build' ? <QuestionnaireFlow {...props.questionnaire} /> : null}
        {tab === 'compose' ? <ComposePanel {...props.compose} /> : null}
        {tab === 'run' ? <ForgeRunPanel {...props.run} /> : null}
        {tab === 'eras' ? <EraViewer {...props.eras} /> : null}
        {tab === 'console' ? <CockpitConsole {...props.console} /> : null}
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
    minHeight: TOUCH, paddingHorizontal: 14, borderRadius: 999, borderWidth: 1, borderColor: C.borderStrong,
    flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: C.cardAlt,
  },
  tabActive: { borderColor: C.green, backgroundColor: C.green + '1f' },
  tabTxt: { color: C.text, fontWeight: '700', fontSize: 13 },
  tabTxtActive: { color: C.textStrong },
  badge: { borderWidth: 1, borderRadius: 999, paddingHorizontal: 6, minWidth: 20, alignItems: 'center' },
  badgeTxt: { fontSize: 11, fontWeight: '800' },
  notice: { marginHorizontal: 16, borderWidth: 1, borderColor: C.amber, borderRadius: 10, padding: 10, backgroundColor: C.amber + '14' },
  noticeTxt: { color: C.amber, fontSize: 13, fontWeight: '600' },
  body: { padding: 16, paddingBottom: 48 },
});
