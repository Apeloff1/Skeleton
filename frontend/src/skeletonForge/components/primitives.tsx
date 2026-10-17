/**
 * Small accessible building blocks shared by the cockpit panels.
 */
import React from 'react';
import { Pressable, StyleSheet, Text, TextInput, View, type StyleProp, type ViewStyle } from 'react-native';
import type { Tone } from '../run';
import { scaledText, useStudioA11y } from './a11yContext';
import { C, RADIUS, TONE_COLOR, TONE_GLYPH, TOUCH } from './theme';

export function Card({ children, style, label, testID }: { children: React.ReactNode; style?: StyleProp<ViewStyle>; label?: string; testID?: string }) {
  return (
    <View style={[s.card, style]} accessibilityLabel={label} testID={testID}>
      {children}
    </View>
  );
}

export function SectionTitle({ children, hint }: { children: React.ReactNode; hint?: string }) {
  const a11y = useStudioA11y();
  const scaling = a11y.allowSystemFontScaling ? undefined : false;
  return (
    <View style={s.titleRow}>
      <Text style={scaledText(s.title, a11y)} allowFontScaling={scaling} accessibilityRole="header">{children}</Text>
      {hint ? <Text style={scaledText(s.hint, a11y)} allowFontScaling={scaling}>{hint}</Text> : null}
    </View>
  );
}

export interface ChipProps {
  label: string;
  selected?: boolean;
  onPress?: () => void;
  color?: string;
  disabled?: boolean;
  role?: 'radio' | 'button' | 'tab' | 'checkbox';
  a11yLabel?: string;
  testID?: string;
}

/** Selectable pill; colour is never the only signal (✓ + aria state). */
export function Chip({ label, selected = false, onPress, color = C.blue, disabled = false, role = 'radio', a11yLabel, testID }: ChipProps) {
  const a11y = useStudioA11y();
  const checked = role === 'radio' || role === 'checkbox' ? selected : undefined;
  return (
    <Pressable
      testID={testID}
      onPress={onPress}
      disabled={disabled}
      accessibilityRole={role}
      accessibilityLabel={a11yLabel ?? label}
      accessibilityState={{ selected, disabled, checked }}
      aria-checked={checked}
      aria-selected={role === 'tab' ? selected : undefined}
      hitSlop={4}
      style={({ pressed }) => [
        s.chip,
        selected && { backgroundColor: color + '26', borderColor: color },
        pressed && !disabled && !a11y.reduceMotion && s.pressed,
        disabled && s.disabled,
      ]}
    >
      <Text style={[scaledText(s.chipTxt, a11y), selected && { color: C.textStrong }]} allowFontScaling={a11y.allowSystemFontScaling ? undefined : false}>
        {selected ? '✓ ' : ''}
        {label}
      </Text>
    </Pressable>
  );
}

export function Button({
  label, onPress, tone = 'primary', disabled = false, busy = false, a11yHint, testID, compact = false,
}: {
  label: string;
  onPress?: () => void;
  tone?: 'primary' | 'secondary' | 'danger' | 'ghost';
  disabled?: boolean;
  busy?: boolean;
  a11yHint?: string;
  testID?: string;
  compact?: boolean;
}) {
  const a11y = useStudioA11y();
  const bg = tone === 'primary' ? C.green : tone === 'danger' ? C.red : tone === 'secondary' ? C.blue : 'transparent';
  const fg = tone === 'primary' ? '#052e16' : tone === 'ghost' ? C.text : '#fff';
  return (
    <Pressable
      testID={testID}
      onPress={onPress}
      disabled={disabled || busy}
      accessibilityRole="button"
      accessibilityHint={a11yHint}
      accessibilityState={{ disabled: disabled || busy, busy }}
      aria-busy={busy}
      style={({ pressed }) => [
        s.btn,
        compact && s.btnCompact,
        { backgroundColor: bg },
        tone === 'ghost' && s.btnGhost,
        pressed && !(disabled || busy) && !a11y.reduceMotion && s.pressed,
        (disabled || busy) && s.disabled,
      ]}
    >
      <Text style={[scaledText(s.btnTxt, a11y), { color: fg }]} allowFontScaling={a11y.allowSystemFontScaling ? undefined : false}>{busy ? `${label}…` : label}</Text>
    </Pressable>
  );
}

export function StatusPill({ tone, label, testID }: { tone: Tone; label: string; testID?: string }) {
  const a11y = useStudioA11y();
  const color = TONE_COLOR[tone];
  return (
    <View style={[s.pill, { borderColor: color, backgroundColor: color + '1f' }]} accessibilityLabel={label} testID={testID}>
      <Text style={[scaledText(s.pillTxt, a11y), { color }]} allowFontScaling={a11y.allowSystemFontScaling ? undefined : false} importantForAccessibility="no">
        {TONE_GLYPH[tone]} {label}
      </Text>
    </View>
  );
}

/** Horizontal bar with an accessible value. */
export function Meter({ ratio, color = C.blue, label, height = 6 }: { ratio: number; color?: string; label: string; height?: number }) {
  const pct = Math.max(0, Math.min(1, Number.isFinite(ratio) ? ratio : 0));
  return (
    <View
      accessibilityRole="progressbar"
      accessibilityLabel={label}
      accessibilityValue={{ min: 0, max: 100, now: Math.round(pct * 100) }}
      style={[s.meter, { height }]}
    >
      <View style={{ width: `${pct * 100}%`, height, backgroundColor: color, borderRadius: height }} />
    </View>
  );
}

export function Banner({ tone, children, testID }: { tone: Tone; children: React.ReactNode; testID?: string }) {
  const a11y = useStudioA11y();
  const color = TONE_COLOR[tone];
  return (
    <View
      testID={testID}
      accessibilityRole={tone === 'bad' ? 'alert' : undefined}
      accessibilityLiveRegion="polite"
      style={[s.banner, { borderColor: color, backgroundColor: color + '14' }]}
    >
      <Text style={[scaledText(s.bannerTxt, a11y), { color: tone === 'idle' ? C.mute : color }]} allowFontScaling={a11y.allowSystemFontScaling ? undefined : false}>{children}</Text>
    </View>
  );
}

export function Field({
  label, value, onChangeText, placeholder, secure = false, disabled = false, onSubmit, testID, keyboard = 'default', hint,
}: {
  label: string;
  value: string;
  onChangeText: (value: string) => void;
  placeholder?: string;
  secure?: boolean;
  disabled?: boolean;
  onSubmit?: () => void;
  testID?: string;
  keyboard?: 'default' | 'email-address';
  hint?: string;
}) {
  const a11y = useStudioA11y();
  return (
    <View style={s.field}>
      <Text style={scaledText(s.fieldLabel, a11y)} allowFontScaling={a11y.allowSystemFontScaling ? undefined : false}>{label}</Text>
      <TextInput
        testID={testID}
        value={value}
        onChangeText={onChangeText}
        placeholder={placeholder}
        placeholderTextColor={C.dim}
        secureTextEntry={secure}
        editable={!disabled}
        autoCapitalize="none"
        autoCorrect={false}
        keyboardType={keyboard}
        returnKeyType={onSubmit ? 'go' : 'next'}
        onSubmitEditing={onSubmit}
        accessibilityLabel={label}
        accessibilityHint={hint}
        textContentType={secure ? 'password' : 'emailAddress'}
        autoComplete={secure ? 'password' : 'email'}
        style={[s.input, scaledText(s.inputText, a11y)]}
      />
    </View>
  );
}

export const s = StyleSheet.create({
  card: { backgroundColor: C.card, borderRadius: RADIUS, borderWidth: 1, borderColor: C.border, padding: 14, marginBottom: 12 },
  titleRow: { flexDirection: 'row', alignItems: 'baseline', flexWrap: 'wrap', gap: 8, marginBottom: 8, marginTop: 4 },
  title: { color: C.textStrong, fontSize: 16, fontWeight: '800' },
  hint: { color: C.mute, fontSize: 12 },
  chip: {
    minHeight: TOUCH - 8, paddingHorizontal: 12, paddingVertical: 8, borderRadius: 999, borderWidth: 1,
    borderColor: C.borderStrong, backgroundColor: C.cardAlt, justifyContent: 'center', marginRight: 8, marginBottom: 8,
  },
  chipTxt: { color: C.text, fontSize: 13, fontWeight: '600' },
  pressed: { opacity: 0.75, transform: [{ scale: 0.98 }] },
  disabled: { opacity: 0.45 },
  btn: { minHeight: TOUCH, paddingHorizontal: 18, borderRadius: 10, alignItems: 'center', justifyContent: 'center' },
  btnCompact: { minHeight: TOUCH - 8, paddingHorizontal: 12 },
  btnGhost: { borderWidth: 1, borderColor: C.borderStrong },
  btnTxt: { fontWeight: '800', fontSize: 14 },
  pill: { borderWidth: 1, borderRadius: 999, paddingHorizontal: 10, paddingVertical: 4, alignSelf: 'flex-start' },
  pillTxt: { fontSize: 12, fontWeight: '700' },
  meter: { backgroundColor: C.border, borderRadius: 6, overflow: 'hidden', width: '100%' },
  banner: { borderWidth: 1, borderRadius: 10, padding: 10, marginBottom: 10 },
  bannerTxt: { fontSize: 13, fontWeight: '600' },
  field: { marginBottom: 12 },
  fieldLabel: { color: C.text, fontSize: 13, fontWeight: '700', marginBottom: 6 },
  input: {
    minHeight: TOUCH, borderWidth: 1, borderColor: C.borderStrong, borderRadius: 10,
    backgroundColor: C.cardAlt, paddingHorizontal: 12, justifyContent: 'center',
  },
  inputText: { color: C.textStrong, fontSize: 16 },
});
