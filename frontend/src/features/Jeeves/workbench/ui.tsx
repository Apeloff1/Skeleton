import React from 'react';
import {
  Alert,
  Modal,
  Platform,
  SafeAreaView,
  ScrollView,
  StyleSheet,
  Switch,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import type { WorkbenchStore } from './WorkbenchStore';
import type { Project, Workbench } from './types';

export const palette = {
  background: '#0b1220',
  panel: '#111b2e',
  elevated: '#17243b',
  border: '#2b3b55',
  text: '#e5edf8',
  muted: '#98a9c1',
  accent: '#b7a0ff',
  green: '#91e8b3',
  amber: '#f7ce7a',
  red: '#f6a5ad',
};

export type IconName = keyof typeof Ionicons.glyphMap;

export interface PanelProps {
  store: WorkbenchStore;
  state: Workbench;
  project: Project;
  now: number;
}

export function Action({
  label,
  icon,
  onPress,
  disabled = false,
  selected = false,
  danger = false,
  compact = false,
}: {
  label: string;
  icon?: IconName;
  onPress: () => void;
  disabled?: boolean;
  selected?: boolean;
  danger?: boolean;
  compact?: boolean;
}) {
  const color = danger ? palette.red : selected ? palette.accent : palette.text;
  return (
    <TouchableOpacity
      onPress={onPress}
      disabled={disabled}
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityState={{ disabled, selected }}
      style={[styles.action, selected && styles.selected, disabled && styles.disabled, compact && styles.compact]}
    >
      {icon && <Ionicons name={icon} size={compact ? 15 : 18} color={color} />}
      <Text style={[styles.actionText, { color }]}>{label}</Text>
    </TouchableOpacity>
  );
}

export function Field({
  label,
  value,
  onChange,
  placeholder,
  multiline = false,
  maxLength = 2000,
  hint,
  numeric = false,
  error,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  multiline?: boolean;
  maxLength?: number;
  hint?: string;
  numeric?: boolean;
  error?: string;
}) {
  return (
    <View style={styles.fieldGroup}>
      <Text style={styles.label}>{label}</Text>
      {hint && <Text style={styles.muted}>{hint}</Text>}
      <TextInput
        value={value}
        onChangeText={onChange}
        placeholder={placeholder}
        placeholderTextColor={palette.muted}
        multiline={multiline}
        maxLength={maxLength}
        keyboardType={numeric ? 'numeric' : 'default'}
        accessibilityLabel={label}
        style={[styles.input, multiline && styles.multiline, !!error && styles.errorBorder]}
      />
      {multiline && <Text style={styles.small}>{value.length.toLocaleString()} / {maxLength.toLocaleString()}</Text>}
      {error && <Text accessibilityRole="alert" style={styles.error}>{error}</Text>}
    </View>
  );
}

export function Choice<T extends string>({
  label,
  value,
  values,
  onChange,
  labels,
}: {
  label: string;
  value: T;
  values: readonly T[];
  onChange: (value: T) => void;
  labels?: Partial<Record<T, string>>;
}) {
  return (
    <View style={styles.fieldGroup}>
      <Text style={styles.label}>{label}</Text>
      <View style={styles.wrap}>
        {values.map(option => (
          <Action
            key={option}
            label={labels?.[option] || option}
            onPress={() => onChange(option)}
            selected={value === option}
            compact
          />
        ))}
      </View>
    </View>
  );
}

export function Toggle({ label, value, onChange, hint }: {
  label: string;
  value: boolean;
  onChange: (value: boolean) => void;
  hint?: string;
}) {
  return (
    <View style={styles.toggle}>
      <View style={styles.flex}>
        <Text style={styles.label}>{label}</Text>
        {hint && <Text style={styles.muted}>{hint}</Text>}
      </View>
      <Switch
        value={value}
        onValueChange={onChange}
        accessibilityLabel={label}
        trackColor={{ false: palette.border, true: '#65518b' }}
        thumbColor={value ? palette.accent : palette.muted}
      />
    </View>
  );
}

export function Section({ title, subtitle, children, action }: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
  action?: React.ReactNode;
}) {
  return (
    <View style={styles.section}>
      <View style={styles.sectionHeading}>
        <View style={styles.flex}>
          <Text style={styles.sectionTitle}>{title}</Text>
          {subtitle && <Text style={styles.muted}>{subtitle}</Text>}
        </View>
        {action}
      </View>
      {children}
    </View>
  );
}

export function Empty({ icon, title, message, action }: {
  icon: IconName;
  title: string;
  message: string;
  action?: React.ReactNode;
}) {
  return (
    <View style={styles.empty}>
      <Ionicons name={icon} size={36} color={palette.accent} />
      <Text style={styles.sectionTitle}>{title}</Text>
      <Text style={[styles.muted, styles.centered]}>{message}</Text>
      {action}
    </View>
  );
}

export function Badge({ text, tone = 'muted' }: {
  text: string;
  tone?: 'muted' | 'accent' | 'green' | 'amber' | 'red';
}) {
  return <Text style={[styles.badge, { color: palette[tone] }]}>{text}</Text>;
}

export function Metric({ label, value, detail }: { label: string; value: string | number; detail?: string }) {
  return (
    <View style={styles.metric}>
      <Text style={styles.metricValue}>{value}</Text>
      <Text style={styles.label}>{label}</Text>
      {detail && <Text style={styles.small}>{detail}</Text>}
    </View>
  );
}

export function Editor({ visible, title, close, children, footer }: {
  visible: boolean;
  title: string;
  close: () => void;
  children: React.ReactNode;
  footer?: React.ReactNode;
}) {
  return (
    <Modal visible={visible} animationType="slide" onRequestClose={close}>
      <SafeAreaView style={styles.safe}>
        <View style={styles.editorHeader}>
          <Text style={styles.sectionTitle}>{title}</Text>
          <Action icon="close" label="Close editor" onPress={close} />
        </View>
        <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={styles.editorBody}>
          {children}
        </ScrollView>
        {footer && <View style={styles.editorFooter}>{footer}</View>}
      </SafeAreaView>
    </Modal>
  );
}

export function LinksPicker({ label, selected, options, onChange }: {
  label: string;
  selected: string[];
  options: { id: string; title: string }[];
  onChange: (ids: string[]) => void;
}) {
  return (
    <View style={styles.fieldGroup}>
      <Text style={styles.label}>{label}</Text>
      {!options.length && <Text style={styles.small}>No matching records yet.</Text>}
      <ScrollView style={styles.linksList} nestedScrollEnabled>
        {options.map(option => (
          <TouchableOpacity
            key={option.id}
            onPress={() => onChange(selected.includes(option.id) ? selected.filter(id => id !== option.id) : [...selected, option.id])}
            accessibilityRole="checkbox"
            accessibilityLabel={option.title}
            accessibilityState={{ checked: selected.includes(option.id) }}
            style={styles.linkChoice}
          >
            <Ionicons name={selected.includes(option.id) ? 'checkbox' : 'square-outline'} size={20} color={palette.accent} />
            <Text style={[styles.text, styles.flex]}>{option.title}</Text>
          </TouchableOpacity>
        ))}
      </ScrollView>
    </View>
  );
}

export function confirmAction(title: string, message: string, action: () => void): void {
  if (Platform.OS === 'web') {
    if (globalThis.confirm(`${title}\n\n${message}`)) action();
  } else {
    Alert.alert(title, message, [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Continue', style: 'destructive', onPress: action },
    ]);
  }
}

export const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: palette.background },
  flex: { flex: 1 },
  text: { color: palette.text, fontSize: 14, lineHeight: 21 },
  muted: { color: palette.muted, fontSize: 13, lineHeight: 20 },
  small: { color: palette.muted, fontSize: 11, lineHeight: 17 },
  label: { color: palette.text, fontSize: 13, fontWeight: '700', lineHeight: 20 },
  error: { color: palette.red, fontSize: 13, lineHeight: 20 },
  row: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  wrap: { flexDirection: 'row', alignItems: 'center', flexWrap: 'wrap', gap: 8 },
  stack: { gap: 14 },
  action: { minHeight: 42, paddingHorizontal: 13, paddingVertical: 10, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 7, backgroundColor: palette.panel, borderWidth: 1, borderColor: palette.border, borderRadius: 10 },
  actionText: { fontSize: 12, fontWeight: '600' },
  selected: { backgroundColor: '#302442', borderColor: '#715697' },
  disabled: { opacity: 0.4 },
  compact: { minHeight: 36, paddingHorizontal: 10, paddingVertical: 7 },
  fieldGroup: { gap: 7 },
  input: { color: palette.text, backgroundColor: palette.panel, borderWidth: 1, borderColor: palette.border, borderRadius: 10, padding: 13, fontSize: 14, minHeight: 44 },
  multiline: { minHeight: 120, textAlignVertical: 'top', lineHeight: 21 },
  errorBorder: { borderColor: palette.red },
  toggle: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 16, paddingVertical: 7 },
  section: { backgroundColor: palette.panel, borderWidth: 1, borderColor: palette.border, borderRadius: 16, padding: 18, gap: 14 },
  sectionHeading: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 12 },
  sectionTitle: { color: palette.text, fontSize: 18, lineHeight: 25, fontWeight: '700' },
  empty: { alignItems: 'center', paddingVertical: 36, paddingHorizontal: 24, gap: 16 },
  centered: { textAlign: 'center' },
  badge: { fontSize: 10, fontWeight: '700', paddingHorizontal: 8, paddingVertical: 4, borderRadius: 6, backgroundColor: palette.elevated, alignSelf: 'flex-start', overflow: 'hidden' },
  metric: { backgroundColor: palette.elevated, borderRadius: 12, padding: 16, minWidth: 130, flexGrow: 1, gap: 5 },
  metricValue: { color: palette.accent, fontSize: 27, fontWeight: '800' },
  editorHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', padding: 18, gap: 12, borderBottomWidth: 1, borderColor: palette.border },
  editorBody: { width: '100%', maxWidth: 850, alignSelf: 'center', padding: 22, gap: 18, paddingBottom: 36 },
  editorFooter: { padding: 16, borderTopWidth: 1, borderColor: palette.border, gap: 8 },
  linksList: { maxHeight: 220, borderWidth: 1, borderColor: palette.border, borderRadius: 10 },
  linkChoice: { flexDirection: 'row', alignItems: 'center', gap: 10, padding: 12, borderBottomWidth: StyleSheet.hairlineWidth, borderColor: palette.border },
  card: { backgroundColor: palette.elevated, borderRadius: 12, borderWidth: 1, borderColor: palette.border, padding: 15, gap: 10 },
  divider: { height: 1, backgroundColor: palette.border, marginVertical: 5 },
});
