/**
 * "Play" handoff for a finished Studio build.
 *
 * The app has no embedded Godot runtime, so Play is a guided handoff: the
 * exact-run source ZIP, then literal steps to open and run it in Godot 4.
 * Every state comes from playHandoff() in ../../run — this card never
 * claims a game is playable when the run did not produce one.
 */
import React from 'react';
import { StyleSheet, View } from 'react-native';
import type { PlayHandoff } from '../../run';
import { Banner, Button, Card, StatusPill } from '../primitives';
import { ScaledText as Text } from '../ScaledText';
import { C, TONE_COLOR } from '../theme';

const PILL: Record<PlayHandoff['state'], string> = {
  ready: 'Verified in Godot',
  'ready-unverified': 'Not verified',
  'needs-export': 'No source files',
  failed: 'Scene failed',
  'not-requested': 'No playable scene',
  'json-target': 'Blueprint only',
};

export function PlayHandoffCard({
  handoff, live, onExport, exportBusy = false, exportError, onBrief, onRetry,
}: {
  handoff: PlayHandoff;
  /** False when this build came from an earlier session (files not kept). */
  live: boolean;
  onExport?: () => void;
  exportBusy?: boolean;
  exportError?: string | null;
  onBrief: () => void;
  onRetry?: () => void;
}) {
  const accent = TONE_COLOR[handoff.tone];
  const canExport = handoff.action === 'export' && live && !!onExport;
  // Source files are returned once per run and never written to the device.
  // A reopened project therefore has to forge again before it can export.
  const staleExport = handoff.action === 'export' && !canExport;
  return (
    <Card
      style={[st.card, { borderLeftColor: accent }]}
      label={'Play. ' + handoff.title}
      testID="studio-play-handoff"
    >
      <View style={st.head}>
        <Text style={st.kicker} accessibilityRole="header">▶ Play</Text>
        <StatusPill tone={handoff.tone} label={PILL[handoff.state]} testID="studio-play-state" />
      </View>
      <Text style={st.title} testID="studio-play-title">{handoff.title}</Text>
      <Text style={st.copy}>{handoff.detail}</Text>
      {handoff.steps.length ? (
        <View accessibilityRole="list" accessibilityLabel="How to play" testID="studio-play-steps" style={st.steps}>
          {handoff.steps.map((step, index) => (
            <View key={index} style={st.step} accessibilityRole={'listitem' as never}>
              <View style={[st.num, { borderColor: accent }]} importantForAccessibility="no-hide-descendants">
                <Text style={[st.numTxt, { color: accent }]}>{index + 1}</Text>
              </View>
              <Text style={st.stepTxt} accessibilityLabel={'Step ' + (index + 1) + ' of ' + handoff.steps.length + '. ' + step}>{step}</Text>
            </View>
          ))}
        </View>
      ) : null}
      <View style={st.row}>
        {canExport ? (
          <Button
            label={exportBusy ? 'Preparing Godot ZIP' : handoff.actionLabel ?? 'Save Godot ZIP'}
            onPress={onExport!}
            busy={exportBusy}
            disabled={exportBusy}
            a11yHint="Saves or shares the exact source files from this run as a ZIP you open in Godot 4"
            testID="studio-play-export"
          />
        ) : null}
        {staleExport && onRetry ? (
          <Button
            label="Forge again to play"
            onPress={onRetry}
            a11yHint="Source files from an earlier session are not kept on this device"
            testID="studio-play-retry"
          />
        ) : null}
        {handoff.action === 'edit-brief' ? (
          <Button label={handoff.actionLabel ?? 'Change the brief'} tone="secondary" onPress={onBrief} testID="studio-play-brief" />
        ) : null}
      </View>
      {staleExport ? (
        <Text style={st.meta} testID="studio-play-stale">
          Source files are only kept for the session that forged them. Forge again to save a fresh ZIP.
        </Text>
      ) : null}
      {exportError && canExport ? <Banner tone="bad" testID="studio-play-export-error">{exportError}</Banner> : null}
    </Card>
  );
}

const st = StyleSheet.create({
  card: { borderLeftWidth: 4, gap: 8 },
  head: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 },
  kicker: { color: C.textStrong, fontSize: 13, fontWeight: '800', letterSpacing: 1.2, textTransform: 'uppercase' },
  title: { color: C.textStrong, fontSize: 18, lineHeight: 24, fontWeight: '800' },
  copy: { color: C.text, fontSize: 15, lineHeight: 22 },
  steps: { gap: 8, marginTop: 4 },
  step: { flexDirection: 'row', alignItems: 'flex-start', gap: 10 },
  num: { width: 26, height: 26, borderRadius: 13, borderWidth: 2, alignItems: 'center', justifyContent: 'center' },
  numTxt: { fontSize: 13, fontWeight: '800' },
  stepTxt: { flex: 1, color: C.text, fontSize: 15, lineHeight: 22 },
  row: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 4 },
  meta: { color: C.mute, fontSize: 13, lineHeight: 18 },
});
