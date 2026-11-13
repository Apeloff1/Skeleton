import React from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';
import { motionHint, textHint, type A11yPlatformSnapshot } from '../../foundation/a11y';
import type { MotionPref, StudioPrefs, TextSizePref } from '../../foundation/model';
import { scaledText, useStudioA11y } from '../a11yContext';
import { Button, Chip, SectionTitle } from '../primitives';
import { C } from '../theme';

const MOTION: { id: MotionPref; label: string }[] = [
  { id: 'system', label: 'Match device' },
  { id: 'on', label: 'Reduce motion' },
  { id: 'off', label: 'Allow motion' },
];

const SIZES: { id: TextSizePref; label: string }[] = [
  { id: 'system', label: 'Match device' },
  { id: 'small', label: 'Small' },
  { id: 'default', label: 'Default' },
  { id: 'large', label: 'Large' },
  { id: 'xlarge', label: 'Extra large' },
];

export function SettingsScreen({
  prefs, platform, onChange, onReplay, onBack,
}: {
  prefs: StudioPrefs;
  platform: A11yPlatformSnapshot;
  onChange: (prefs: StudioPrefs) => void;
  onReplay: () => void;
  onBack: () => void;
}) {
  const a11y = useStudioA11y();
  return (
    <ScrollView contentContainerStyle={st.body} testID="studio-settings">
      <SectionTitle>Settings</SectionTitle>
      <Text style={st.copy}>These preferences stay on this device. Match device follows the platform when it reports a setting.</Text>

      <Text style={st.group} accessibilityRole="header">Reduced motion</Text>
      <View accessibilityRole="radiogroup" accessibilityLabel="Reduced motion">
        <View style={st.chips}>
          {MOTION.map((option) => (
            <Chip
              key={option.id}
              label={option.label}
              selected={prefs.reducedMotion === option.id}
              onPress={() => onChange({ ...prefs, reducedMotion: option.id })}
              testID={`studio-motion-${option.id}`}
            />
          ))}
        </View>
      </View>
      <Text style={st.hint}>{motionHint(prefs, platform)}</Text>

      <Text style={st.group} accessibilityRole="header">Text size</Text>
      <View accessibilityRole="radiogroup" accessibilityLabel="Text size">
        <View style={st.chips}>
          {SIZES.map((option) => (
            <Chip
              key={option.id}
              label={option.label}
              selected={prefs.textSize === option.id}
              onPress={() => onChange({ ...prefs, textSize: option.id })}
              testID={`studio-text-${option.id}`}
            />
          ))}
        </View>
      </View>
      <Text style={st.hint}>{textHint(prefs, platform)}</Text>
      <Text style={scaledText(st.preview, a11y)} allowFontScaling={a11y.allowSystemFontScaling ? undefined : false} accessibilityLabel="Text size preview">The quick forge builds a game from your brief.</Text>

      <View style={st.row}>
        <Button label="Replay the introduction" tone="secondary" onPress={onReplay} testID="studio-replay" a11yHint="Shows the three first-run steps again" />
        <Button label="Back to projects" tone="ghost" onPress={onBack} testID="studio-back" />
      </View>
    </ScrollView>
  );
}

const st = StyleSheet.create({
  body: { padding: 16, paddingBottom: 48, gap: 8 },
  copy: { color: C.text, fontSize: 15, lineHeight: 22 },
  group: { color: C.textStrong, fontSize: 15, fontWeight: '800', marginTop: 12 },
  chips: { flexDirection: 'row', flexWrap: 'wrap' },
  hint: { color: C.mute, fontSize: 13, lineHeight: 18 },
  preview: { color: C.textStrong, fontSize: 16, lineHeight: 24, marginVertical: 8 },
  row: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 8 },
});
