/**
 * Three short steps. Skip and the last step both remember that first-run is done.
 * The first completion leads into a new project; a replay returns to projects.
 */
import React from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';
import { Banner, Button, Meter, SectionTitle } from '../primitives';
import { C } from '../theme';

export const ONBOARDING_STEPS = [
  {
    id: 'brief',
    title: 'Describe a game',
    body: 'You start with a short brief. The forge turns that brief into a project, and you can change the answers before anything is built.',
  },
  {
    id: 'build',
    title: 'Watch the build',
    body: 'Each project shows the forge stages. If a stage fails, the screen names what failed and the next thing to do: change the brief, run it again, or go back to your projects.',
  },
  {
    id: 'account',
    title: 'Sign in and set the app up',
    body: 'Sign in when this studio requires an account. Projects stay on this device either way. Text size and reduced motion live in Settings.',
  },
] as const;

export function OnboardingScreen({
  step, replaying, error, onNext, onSkip, onBack,
}: {
  step: number;
  replaying: boolean;
  error: string | null;
  onNext: () => void;
  onSkip: () => void;
  onBack: () => void;
}) {
  const index = Math.max(0, Math.min(ONBOARDING_STEPS.length - 1, step));
  const current = ONBOARDING_STEPS[index];
  const last = index === ONBOARDING_STEPS.length - 1;
  const primary = last ? (replaying ? 'Back to projects' : 'Create a project') : 'Next';
  return (
    <ScrollView contentContainerStyle={st.body} keyboardShouldPersistTaps="handled" testID="studio-onboarding">
      <SectionTitle hint={`Step ${index + 1} of ${ONBOARDING_STEPS.length}`}>Skeleton studio</SectionTitle>
      <Meter ratio={(index + 1) / ONBOARDING_STEPS.length} label={`Introduction, step ${index + 1} of ${ONBOARDING_STEPS.length}: ${current.title}`} />
      <View accessibilityLabel={`${current.title}. ${current.body}`}>
        <Text style={st.kicker} accessibilityRole="header">{current.title}</Text>
        <Text style={st.bodyText}>{current.body}</Text>
      </View>
      {error ? <Banner tone="bad" testID="studio-onboarding-error">{error}</Banner> : null}
      <View style={st.row}>
        <Button label="Back" tone="ghost" onPress={onBack} disabled={index === 0} testID="studio-onboarding-back" a11yHint={index === 0 ? 'Skip setup if you want to leave the introduction' : 'Previous step'} />
        <Button label="Skip setup" tone="ghost" onPress={onSkip} testID="studio-skip" a11yHint="Marks the introduction done and opens your projects" />
        <Button label={primary} onPress={onNext} testID="studio-next" a11yHint={last && !replaying ? 'Marks the introduction done and opens a new brief' : 'Continues'} />
      </View>
    </ScrollView>
  );
}

const st = StyleSheet.create({
  body: { padding: 16, paddingBottom: 40, gap: 12 },
  kicker: { color: C.textStrong, fontSize: 22, fontWeight: '800', marginTop: 8 },
  bodyText: { color: C.text, fontSize: 16, lineHeight: 24, marginTop: 8 },
  row: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 8 },
});
