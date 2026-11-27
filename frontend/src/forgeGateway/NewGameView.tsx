/**
 * Presentational new-game flow (prompt → live build → result). All state is
 * passed in, so it renders deterministically in tests; `app/new-game.tsx`
 * wires it to `useGameBuild`.
 */
import React from 'react';
import { Pressable, StyleSheet, TextInput, View } from 'react-native';
import { AppText } from '../foundation/AppText';
import { Stack, Row } from '../foundation/Stack';
import { color } from '../foundation/tokens';
import { MIN_TOUCH_TARGET } from '../foundation/a11y';
import { ActionButton } from '../foundation/ActionButton';
import { EXAMPLE_BRIEFS, MAX_BRIEF_CHARS, type Playtest, validateBrief } from './model';
import type { GameBuildState } from './useGameBuild';

export interface NewGameViewProps {
  state: GameBuildState;
  brief: string;
  playtest: Playtest;
  onBriefChange: (value: string) => void;
  onPlaytestChange: (value: Playtest) => void;
  onSubmit: () => void;
  onReset: () => void;
  onOpenBuilds?: () => void;
  validationError?: string | null;
  unavailableReason?: string | null;
}

const PLAYTEST_OPTIONS: readonly { value: Playtest; label: string; hint: string }[] = [
  { value: 'require', label: 'Required', hint: 'The build fails unless the game plays.' },
  { value: 'auto', label: 'If available', hint: 'Playtests when the server has Godot.' },
  { value: 'off', label: 'Skip', hint: 'Fastest, not proven.' },
];

function Progress({ percent, label }: { percent: number; label: string }) {
  return (
    <View
      accessibilityRole="progressbar"
      accessibilityLabel="Build progress"
      accessibilityValue={{ min: 0, max: 100, now: percent, text: `${percent}% · ${label}` }}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={percent}
      aria-valuetext={`${percent}% · ${label}`}
      style={styles.track}
      testID="new-game-progress"
    >
      <View style={[styles.bar, { width: `${percent}%` }]} />
    </View>
  );
}

export function NewGameView(props: NewGameViewProps) {
  const { state, brief, playtest, validationError, unavailableReason } = props;
  const [focusedPlaytest, setFocusedPlaytest] = React.useState<Playtest | null>(null);
  const busy = state.kind === 'starting' || state.kind === 'tracking';

  if (state.kind === 'tracking' || state.kind === 'done') {
    const s = state.summary;
    const succeeded = state.kind === 'done' && s.phase === 'succeeded';
    const failed = state.kind === 'done' && s.phase !== 'succeeded';
    return (
      <Stack gap="lg" testID="new-game-build">
        <AppText variant="h1">{succeeded ? `${s.title ?? 'Your game'} is ready` : failed ? 'Build failed' : 'Building your game'}</AppText>
        <Progress percent={s.percent} label={s.stage} />
        <View accessibilityLiveRegion="polite" aria-live="polite">
          <AppText color="textMuted">{`${s.percent}% · ${s.stage}`}</AppText>
          {state.kind === 'tracking' && state.transientError ? <AppText color="warning">{state.transientError}</AppText> : null}
        </View>
        {succeeded ? (
          <Stack gap="sm" testID="new-game-success">
            {s.genre ? <AppText>{`Genre: ${s.genre}`}</AppText> : null}
            <AppText>{`Proof: ${s.proof ?? 'not playtested'}`}</AppText>
            {s.playtest ? <AppText>{`Playtest: ${s.playtest}`}</AppText> : null}
            {s.stubbed.length ? <AppText color="textMuted">{`Not generated yet: ${s.stubbed.join('; ')}.`}</AppText> : null}
            <Row gap="sm">
              {props.onOpenBuilds ? <ActionButton label="Open my builds" onPress={props.onOpenBuilds} /> : null}
              <ActionButton label="Build another game" variant="secondary" onPress={props.onReset} />
            </Row>
          </Stack>
        ) : null}
        {failed ? (
          <View accessibilityRole="alert" testID="new-game-failure">
            <Stack gap="sm">
              <AppText color="danger">{s.error ?? 'The build did not finish.'}</AppText>
              <AppText color="textMuted">Try a more specific description: name the genre, the core loop and a small scope.</AppText>
              <ActionButton label="Edit and try again" onPress={props.onReset} />
            </Stack>
          </View>
        ) : null}
      </Stack>
    );
  }

  const count = `${brief.length} / ${MAX_BRIEF_CHARS} characters`;
  const fieldError = validationError ?? null;
  return (
    <Stack gap="lg" testID="new-game-form">
      <AppText variant="h1">New game</AppText>
      <AppText color="textMuted">Describe a game in a sentence or two. Skeleton builds a real Godot project and can playtest it before saving.</AppText>
      {unavailableReason ? (
        <View accessibilityRole="alert" style={styles.notice}><AppText color="warning">{unavailableReason}</AppText></View>
      ) : null}
      <Stack gap="xs">
        <AppText variant="label" nativeID="brief-label">Describe your game</AppText>
        <TextInput
          value={brief}
          onChangeText={props.onBriefChange}
          multiline
          maxLength={MAX_BRIEF_CHARS}
          editable={!busy}
          accessibilityLabel="Describe your game"
          accessibilityLabelledBy="brief-label"
          accessibilityHint="Name the genre, the setting, the core loop and keep the scope small."
          aria-invalid={fieldError ? true : undefined}
          placeholder="A small platformer about a fox on rainy rooftops…"
          placeholderTextColor={color.textSubtle}
          style={[styles.input, fieldError ? styles.inputError : null]}
          testID="new-game-brief"
        />
        <AppText variant="caption" color="textMuted">{count}</AppText>
        {fieldError ? <View accessibilityRole="alert"><AppText color="danger" testID="new-game-brief-error">{fieldError}</AppText></View> : null}
      </Stack>
      <Stack gap="xs">
        <AppText variant="h2">Start from an example</AppText>
        <Row gap="sm" wrap>
          {EXAMPLE_BRIEFS.map((example) => (
            <ActionButton key={example.label} label={example.label} variant="secondary"
              onPress={() => props.onBriefChange(example.brief)} accessibilityLabel={`Use the ${example.label} example`} />
          ))}
        </Row>
      </Stack>
      <View accessibilityRole="radiogroup" accessibilityLabel="Playtest before saving">
        <AppText variant="h2">Playtest before saving</AppText>
        {PLAYTEST_OPTIONS.map((option) => {
          const checked = playtest === option.value;
          return (
            <Pressable
              key={option.value}
              accessibilityRole="radio"
              accessibilityState={{ checked, disabled: busy }}
              aria-checked={checked}
              aria-disabled={busy || undefined}
              accessibilityLabel={`${option.label}. ${option.hint}`}
              onPress={() => props.onPlaytestChange(option.value)}
              onFocus={() => setFocusedPlaytest(option.value)}
              onBlur={() => setFocusedPlaytest(current => current === option.value ? null : current)}
              disabled={busy}
              style={[styles.radio, focusedPlaytest === option.value ? styles.focused : null]}
            >
              <View style={[styles.dot, checked ? styles.dotOn : null]} />
              <Stack gap="xs" style={styles.flex}>
                <AppText>{option.label}</AppText>
                <AppText variant="caption" color="textMuted">{option.hint}</AppText>
              </Stack>
            </Pressable>
          );
        })}
      </View>
      {state.kind === 'error' ? (
        <View accessibilityRole="alert" testID="new-game-error" style={styles.notice}>
          <AppText color="danger">{state.message}</AppText>
        </View>
      ) : null}
      <ActionButton
        label={state.kind === 'starting' ? 'Starting…' : state.kind === 'error' && state.retryable ? 'Try again' : 'Build game'}
        onPress={props.onSubmit}
        busy={state.kind === 'starting'}
        disabled={!!unavailableReason}
        accessibilityLabel="Build game"
        testID="new-game-submit"
      />
    </Stack>
  );
}

/** Same rule as the gateway, so the user sees the reason before a round trip. */
export function briefError(brief: string): string | null {
  return validateBrief(brief);
}

const styles = StyleSheet.create({
  input: {
    minHeight: 120, borderWidth: 1, borderColor: color.border, borderRadius: 10, padding: 12,
    color: color.text, backgroundColor: color.surface, textAlignVertical: 'top', fontSize: 16,
  },
  inputError: { borderColor: color.danger },
  track: { height: 12, borderRadius: 6, backgroundColor: color.surfaceRaised, overflow: 'hidden', borderWidth: 1, borderColor: color.border },
  bar: { height: '100%', backgroundColor: color.primary },
  radio: { flexDirection: 'row', alignItems: 'center', gap: 12, minHeight: MIN_TOUCH_TARGET, paddingVertical: 6 },
  focused: { outlineColor: color.focus, outlineWidth: 2, outlineStyle: 'solid' },
  dot: { width: 20, height: 20, borderRadius: 10, borderWidth: 2, borderColor: color.textMuted },
  dotOn: { borderColor: color.primary, backgroundColor: color.primary },
  flex: { flex: 1 },
  notice: { padding: 12, borderRadius: 10, borderWidth: 1, borderColor: color.border, backgroundColor: color.surfaceRaised },
});

export default NewGameView;
