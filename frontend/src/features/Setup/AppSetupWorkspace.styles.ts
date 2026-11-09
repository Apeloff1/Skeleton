import { StyleSheet } from 'react-native';
export const colors = { bg: '#0b1220', card: '#111a2e', edge: '#29374e', text: '#f1f5f9', muted: '#a0aec0', accent: '#c4b5fd', green: '#86efac', red: '#fca5a5' };
export default StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg }, page: { padding: 24, gap: 20, width: '100%', maxWidth: 1120, alignSelf: 'center', paddingBottom: 64 },
  row: { flexDirection: 'row', alignItems: 'center', flexWrap: 'wrap', gap: 12 }, grow: { flex: 1 },
  eyebrow: { color: colors.accent, fontSize: 12, fontWeight: '700', letterSpacing: 2 }, title: { color: colors.text, fontSize: 32, fontWeight: '800' },
  subtitle: { color: colors.muted, fontSize: 15, lineHeight: 24, maxWidth: 780 }, heading: { color: colors.text, fontSize: 19, fontWeight: '700' },
  card: { backgroundColor: colors.card, borderWidth: 1, borderColor: colors.edge, borderRadius: 16, padding: 20, gap: 12 },
  check: { borderTopWidth: 1, borderColor: colors.edge, paddingTop: 16, gap: 8 }, label: { color: colors.text, fontSize: 15, fontWeight: '700' },
  small: { color: colors.muted, fontSize: 12, lineHeight: 19 }, message: { color: colors.text, fontSize: 14, lineHeight: 22 },
  badge: { paddingHorizontal: 10, paddingVertical: 5, borderRadius: 30, backgroundColor: '#202c42' }, badgeText: { color: colors.accent, fontSize: 12, fontWeight: '700' },
  button: { borderWidth: 1, borderColor: '#635080', borderRadius: 10, minHeight: 44, paddingHorizontal: 15, paddingVertical: 11, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8 },
  buttonText: { color: colors.accent, fontSize: 13, fontWeight: '700' }, disabled: { opacity: 0.45 },
  code: { fontFamily: 'monospace', color: '#ddd6fe', fontSize: 12, lineHeight: 20, backgroundColor: colors.bg, padding: 14, borderRadius: 9 },
  error: { color: colors.red, fontSize: 13, lineHeight: 21 }, success: { color: colors.green }, twoColumns: { flexDirection: 'row', flexWrap: 'wrap', gap: 20 }, column: { flexGrow: 1, flexShrink: 1, flexBasis: 380, minWidth: 0, maxWidth: '100%' },
});
