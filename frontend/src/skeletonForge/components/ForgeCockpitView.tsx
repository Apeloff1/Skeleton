/**
 * Skeleton Forge cockpit layout: accessible tab bar + the active panel.
 * Pure — every panel's data arrives via props so the whole screen renders
 * deterministically in tests; ForgeCockpitScreen wires the live hooks.
 */
import React from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useReduceMotion } from '../../hooks/useReduceMotion';
import { gridMove, keyAction, readKey, rovingTabIndex, tabIndexProp, webKeyProps, type KeyEventLike } from '../a11y';
import {
  COCKPIT_TAB_HINTS, COCKPIT_TAB_LABELS, COCKPIT_TABS, tabA11yLabel, type CockpitTab, type TabBadge,
} from '../cockpitScreen';
import CockpitConsole, { type CockpitConsoleProps } from './CockpitConsole';
import ComposePanel, { type ComposePanelProps } from './ComposePanel';
import EraViewer, { type EraViewerProps } from './EraViewer';
import ForgeRunPanel, { type ForgeRunPanelProps } from './ForgeRunPanel';
import PlanViewer, { type PlanViewerProps } from './PlanViewer';
import QuestionnaireFlow, { type QuestionnaireFlowProps } from './QuestionnaireFlow';
import { C, TONE_COLOR, TOUCH, pressFeedback } from './theme';

/** Arrow keys move between cockpit tabs and wrap. Enter/Space stay on the tab's own press. */
export function cockpitTabMove(current: CockpitTab, event: KeyEventLike): CockpitTab | null {
  const { key, ctrl } = readKey(event);
  if (keyAction(key)) return null;
  const i = COCKPIT_TABS.indexOf(current);
  if (i < 0) return null;
  const next = gridMove(i, key, { cols: 1, count: COCKPIT_TABS.length, ctrl, wrap: true });
  if (next === null || next === i) return null;
  return COCKPIT_TABS[next];
}

export interface ForgeCockpitViewProps {
  tab: CockpitTab;
  onTab: (tab: CockpitTab) => void;
  badges: Record<CockpitTab, TabBadge>;
  questionnaire: QuestionnaireFlowProps;
  compose: ComposePanelProps;
  plan: PlanViewerProps;
  run: ForgeRunPanelProps;
  eras: EraViewerProps;
  console: CockpitConsoleProps;
  /** Optional offline/backend banner shown above every tab. */
  notice?: string | null;
  /** Overrides the OS reduce-motion preference when set. */
  reduceMotion?: boolean;
  testID?: string;
}

export function CockpitTabBar({ tab, onTab, badges, reduceMotion }: Pick<ForgeCockpitViewProps, 'tab' | 'onTab' | 'badges' | 'reduceMotion'>) {
  const systemReduce = useReduceMotion();
  const reduce = reduceMotion ?? systemReduce;
  const refs = React.useRef<Array<{ focus?: () => void } | null>>([]);
  const viaKey = React.useRef(false);
  const index = COCKPIT_TABS.indexOf(tab);
  React.useEffect(() => {
    if (!viaKey.current) return;
    viaKey.current = false;
    refs.current[index]?.focus?.();
  }, [index]);
  const onKey = (event: KeyEventLike) => {
    const next = cockpitTabMove(tab, event);
    if (!next) return;
    event.preventDefault?.();
    viaKey.current = true;
    onTab(next);
  };
  return (
    <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={st.tabs} accessibilityRole="tablist" accessibilityLabel="Forge steps">
      {COCKPIT_TABS.map((t, i) => {
        const active = t === tab;
        const badge = badges[t];
        return (
          <Pressable
            key={t}
            ref={(n) => { refs.current[i] = n; }}
            testID={`cockpit-tab-${t}`}
            onPress={() => onTab(t)}
            accessibilityRole="tab"
            accessibilityLabel={tabA11yLabel(t, badge)}
            accessibilityState={{ selected: active }}
            aria-selected={active}
            {...tabIndexProp(rovingTabIndex(i, index))}
            {...webKeyProps(onKey)}
            style={({ pressed }) => [st.tab, active && st.tabActive, pressFeedback(pressed, reduce)]}
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
  const { tab, notice, testID, reduceMotion } = props;
  return (
    <View style={st.root} testID={testID}>
      <View style={st.header}>
        <Text style={st.title} accessibilityRole="header">Skeleton Forge</Text>
        <Text style={st.subtitle}>{COCKPIT_TAB_HINTS[tab]}</Text>
      </View>
      <CockpitTabBar tab={tab} onTab={props.onTab} badges={props.badges} reduceMotion={reduceMotion} />
      {notice ? (
        <View style={st.notice} accessibilityRole="alert" testID="cockpit-notice">
          <Text style={st.noticeTxt}>{notice}</Text>
        </View>
      ) : null}
      <ScrollView contentContainerStyle={st.body} keyboardShouldPersistTaps="handled" testID={`cockpit-panel-${tab}`}>
        {tab === 'build' ? <QuestionnaireFlow {...props.questionnaire} /> : null}
        {tab === 'compose' ? <ComposePanel {...props.compose} /> : null}
        {tab === 'plan' ? <PlanViewer {...props.plan} reduceMotion={props.plan.reduceMotion ?? reduceMotion} /> : null}
        {tab === 'run' ? <ForgeRunPanel {...props.run} reduceMotion={props.run.reduceMotion ?? reduceMotion} /> : null}
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
