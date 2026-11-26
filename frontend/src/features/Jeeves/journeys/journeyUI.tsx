import React from 'react';
import { Modal, SafeAreaView, ScrollView, StyleSheet, Text, TextInput, TouchableOpacity, View } from 'react-native';
export const colors = { bg: '#0b1220', panel: '#131e32', edge: '#33445f', text: '#e5edf9', muted: '#a2b2c9', accent: '#c4b5fd', green: '#86efac', error: '#fca5a5' };
export const human = (value: string) => value.replace(/_/g, ' ').replace(/(^|\s)\S/g, letter => letter.toUpperCase());
export function JourneyButton({ label, onPress, disabled, selected, testID }: { label: string; onPress: () => void; disabled?: boolean; selected?: boolean; testID?: string }) {
  return <TouchableOpacity testID={testID} accessibilityRole="button" accessibilityLabel={label} accessibilityState={{ disabled: !!disabled, selected: !!selected }} disabled={disabled} onPress={onPress} style={[ui.button, selected && ui.selected, disabled && ui.disabled]}><Text style={ui.buttonText}>{label}</Text></TouchableOpacity>;
}
export function JourneyField({ label, value, onChange, multiline, maxLength = 4000, disabled, testID, numeric }: { label: string; value: string; onChange: (value: string) => void; multiline?: boolean; maxLength?: number; disabled?: boolean; testID?: string; numeric?: boolean }) {
  return <View style={ui.stack}><Text style={ui.label}>{label}</Text><TextInput testID={testID} accessibilityLabel={label} value={value} onChangeText={onChange} multiline={multiline} maxLength={maxLength} editable={!disabled} keyboardType={numeric ? 'number-pad' : 'default'} placeholderTextColor={colors.muted} style={[ui.input, multiline && ui.multiline]} /></View>;
}
export function JourneyDialog({ title, close, children, footer }: { title: string; close: () => void; children: React.ReactNode; footer?: React.ReactNode }) {
  return <Modal visible animationType="slide" onRequestClose={close}><SafeAreaView style={ui.safe}><View style={ui.dialogHead}><View style={{ flex: 1 }}><Text style={ui.eyebrow}>JEEVES · GUIDED WORK</Text><Text style={ui.heading}>{title}</Text></View><JourneyButton label="Close" onPress={close} testID="journey-close" /></View><ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={ui.dialogBody}>{children}</ScrollView>{footer && <View style={ui.footer}>{footer}</View>}</SafeAreaView></Modal>;
}
export const ui = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg }, dialogHead: { padding: 18, flexDirection: 'row', alignItems: 'center', gap: 12, borderBottomWidth: 1, borderColor: colors.edge },
  dialogBody: { padding: 18, paddingBottom: 36, gap: 18, width: '100%', maxWidth: 900, alignSelf: 'center' }, footer: { borderTopWidth: 1, borderColor: colors.edge, padding: 12, gap: 8 },
  eyebrow: { color: colors.accent, fontSize: 10, fontWeight: '700', letterSpacing: 2, marginBottom: 5 }, heading: { color: colors.text, fontSize: 23, fontWeight: '700' },
  title: { color: colors.text, fontSize: 17, fontWeight: '600' }, label: { color: colors.text, fontWeight: '600', fontSize: 13 }, muted: { color: colors.muted, fontSize: 13, lineHeight: 20 },
  text: { color: colors.text, fontSize: 14, lineHeight: 22 }, success: { color: colors.green, lineHeight: 20 }, error: { color: colors.error, lineHeight: 20 },
  input: { borderWidth: 1, borderColor: colors.edge, borderRadius: 10, padding: 12, color: colors.text, fontSize: 14, backgroundColor: colors.panel, minHeight: 44 }, multiline: { minHeight: 110, textAlignVertical: 'top' },
  stack: { gap: 8 }, row: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: 8 }, card: { borderWidth: 1, borderColor: colors.edge, backgroundColor: colors.panel, borderRadius: 14, padding: 15, gap: 10 },
  button: { minHeight: 42, justifyContent: 'center', paddingHorizontal: 13, paddingVertical: 8, borderRadius: 9, borderWidth: 1, borderColor: colors.edge, backgroundColor: '#1c2b43', maxWidth: '100%' }, buttonText: { color: colors.text, fontSize: 12, fontWeight: '600', flexShrink: 1 },
  selected: { borderColor: colors.accent, backgroundColor: '#32264e' }, disabled: { opacity: .45 }, mono: { color: colors.muted, fontSize: 11, lineHeight: 17 },
});
