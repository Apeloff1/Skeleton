import React from 'react';
import { View, Text, StyleSheet, TouchableOpacity, Switch, TextInput } from 'react-native';
import Slider from '@react-native-community/slider';
import { Ionicons } from '@expo/vector-icons';

const C = {
  bg: '#0F172A', card: '#1E293B', border: '#334155',
  text: '#F8FAFC', muted: '#94A3B8', accent: '#3B82F6',
};

// ───────────────────────────────────────────────────────────────────
export function Section({ title, hint, children }: { title: string; hint?: string; children: React.ReactNode }) {
  return (
    <View style={s.section}>
      <Text style={s.sectionTitle}>{title.toUpperCase()}</Text>
      {hint ? <Text style={s.sectionHint}>{hint}</Text> : null}
      <View style={s.sectionBody}>{children}</View>
    </View>
  );
}

// ───────────────────────────────────────────────────────────────────
export function SwitchRow({
  label, hint, value, onValueChange, icon, color,
}: {
  label: string; hint?: string; value: boolean; onValueChange: (v: boolean) => void;
  icon?: string; color?: string;
}) {
  const c = color || C.accent;
  return (
    <View style={s.row}>
      {icon ? <Ionicons name={icon as any} size={20} color={c} style={{ marginRight: 12 }} /> : null}
      <View style={{ flex: 1 }}>
        <Text style={s.rowLabel}>{label}</Text>
        {hint ? <Text style={s.rowHint}>{hint}</Text> : null}
      </View>
      <Switch value={value} onValueChange={onValueChange}
        trackColor={{ false: '#475569', true: c + 'AA' }}
        thumbColor={value ? c : '#94A3B8'} />
    </View>
  );
}

// ───────────────────────────────────────────────────────────────────
export function SliderRow({
  label, hint, value, onChange, min = 0, max = 1, step = 0.01, color, valueLabel,
}: {
  label: string; hint?: string; value: number; onChange: (v: number) => void;
  min?: number; max?: number; step?: number; color?: string; valueLabel?: string;
}) {
  const c = color || C.accent;
  return (
    <View style={[s.row, { flexDirection: 'column', alignItems: 'stretch' }]}>
      <View style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 6 }}>
        <View style={{ flex: 1 }}>
          <Text style={s.rowLabel}>{label}</Text>
          {hint ? <Text style={s.rowHint}>{hint}</Text> : null}
        </View>
        <View style={[s.valuePill, { backgroundColor: c + '22', borderColor: c + '55' }]}>
          <Text style={[s.valuePillText, { color: c }]}>
            {valueLabel !== undefined ? valueLabel : value.toFixed(step < 0.1 ? 2 : 1)}
          </Text>
        </View>
      </View>
      <Slider
        minimumValue={min}
        maximumValue={max}
        step={step}
        value={value}
        onValueChange={onChange}
        minimumTrackTintColor={c}
        maximumTrackTintColor="#334155"
        thumbTintColor={c}
      />
    </View>
  );
}

// ───────────────────────────────────────────────────────────────────
export function TextRow({
  label, hint, value, onChange, placeholder, multiline, numberOfLines = 4, color,
}: {
  label: string; hint?: string; value: string; onChange: (v: string) => void;
  placeholder?: string; multiline?: boolean; numberOfLines?: number; color?: string;
}) {
  return (
    <View style={[s.row, { flexDirection: 'column', alignItems: 'stretch' }]}>
      <Text style={s.rowLabel}>{label}</Text>
      {hint ? <Text style={s.rowHint}>{hint}</Text> : null}
      <TextInput
        style={[s.input, multiline ? { minHeight: 24 * numberOfLines, textAlignVertical: 'top' } : null]}
        value={value}
        onChangeText={onChange}
        placeholder={placeholder}
        placeholderTextColor="#64748B"
        multiline={multiline}
        numberOfLines={numberOfLines}
      />
    </View>
  );
}

// ───────────────────────────────────────────────────────────────────
export function ChoiceRow({
  label, hint, value, onChange, options, color,
}: {
  label: string; hint?: string; value: string; onChange: (v: any) => void;
  options: { value: string; label: string }[]; color?: string;
}) {
  const c = color || C.accent;
  return (
    <View style={[s.row, { flexDirection: 'column', alignItems: 'stretch' }]}>
      <Text style={s.rowLabel}>{label}</Text>
      {hint ? <Text style={s.rowHint}>{hint}</Text> : null}
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
        {options.map(o => {
          const active = o.value === value;
          return (
            <TouchableOpacity
              key={o.value}
              style={[s.chip, active && { backgroundColor: c + '22', borderColor: c }]}
              onPress={() => onChange(o.value)}
              activeOpacity={0.7}
            >
              <Text style={[s.chipText, active && { color: c, fontWeight: '700' }]}>{o.label}</Text>
            </TouchableOpacity>
          );
        })}
      </View>
    </View>
  );
}

// ───────────────────────────────────────────────────────────────────
export function ActionButton({
  label, icon, onPress, color, kind = 'primary',
}: {
  label: string; icon?: string; onPress: () => void; color?: string;
  kind?: 'primary' | 'danger' | 'ghost';
}) {
  const bg = kind === 'danger' ? '#EF4444' : kind === 'ghost' ? 'transparent' : (color || C.accent);
  const border = kind === 'ghost' ? C.border : bg;
  const text = kind === 'ghost' ? C.text : '#fff';
  return (
    <TouchableOpacity
      style={[s.button, { backgroundColor: bg, borderColor: border }]}
      onPress={onPress}
      activeOpacity={0.7}
    >
      {icon ? <Ionicons name={icon as any} size={16} color={text} style={{ marginRight: 8 }} /> : null}
      <Text style={[s.buttonText, { color: text }]}>{label}</Text>
    </TouchableOpacity>
  );
}

const s = StyleSheet.create({
  section: { marginBottom: 16 },
  sectionTitle: { fontSize: 11, fontWeight: '700', color: C.muted, letterSpacing: 1, marginHorizontal: 16, marginBottom: 4 },
  sectionHint: { fontSize: 11, color: C.muted, marginHorizontal: 16, marginBottom: 10, lineHeight: 16 },
  sectionBody: { backgroundColor: C.card, borderRadius: 12, marginHorizontal: 12, borderWidth: 1, borderColor: C.border },

  row: { flexDirection: 'row', alignItems: 'center', paddingVertical: 12, paddingHorizontal: 14, borderBottomWidth: 1, borderBottomColor: C.border },
  rowLabel: { fontSize: 14, color: C.text, fontWeight: '600' },
  rowHint: { fontSize: 11, color: C.muted, marginTop: 2, lineHeight: 15 },
  valuePill: { paddingHorizontal: 10, paddingVertical: 3, borderRadius: 8, borderWidth: 1 },
  valuePillText: { fontSize: 12, fontWeight: '800' },

  input: {
    marginTop: 8, backgroundColor: '#0B1222', color: C.text, fontSize: 14,
    paddingHorizontal: 12, paddingVertical: 10, borderRadius: 8,
    borderWidth: 1, borderColor: C.border,
  },

  chip: { backgroundColor: '#0B1222', paddingHorizontal: 12, paddingVertical: 7, borderRadius: 8, borderWidth: 1, borderColor: C.border, marginTop: 8 },
  chipText: { color: C.muted, fontSize: 12, fontWeight: '600' },

  button: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
    paddingVertical: 11, paddingHorizontal: 16, borderRadius: 10, borderWidth: 1 },
  buttonText: { fontSize: 14, fontWeight: '700' },
});
