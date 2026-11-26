import { StyleSheet } from 'react-native';
import { colors } from '../Setup/AppSetupWorkspace.styles';

export { colors };

export default StyleSheet.create({
  card: { backgroundColor: colors.card, borderWidth: 1, borderColor: colors.edge, borderRadius: 16, padding: 16, gap: 12, width: '100%' },
  row: { flexDirection: 'row', alignItems: 'center', flexWrap: 'wrap', gap: 8 },
  stack: { flexDirection: 'column', alignItems: 'stretch' },
  columns: { flexDirection: 'row', alignItems: 'flex-start', flexWrap: 'wrap', gap: 12 },
  column: { flexGrow: 1, flexShrink: 1, flexBasis: 280, minWidth: 0, gap: 8 },
  eyebrow: { color: colors.accent, fontSize: 12, fontWeight: '700', letterSpacing: 1.4 },
  title: { color: colors.text, fontSize: 22, fontWeight: '800' },
  body: { color: colors.text, fontSize: 14, lineHeight: 21 },
  muted: { color: colors.muted, fontSize: 12, lineHeight: 18 },
  input: { minHeight: 44, borderWidth: 1, borderColor: colors.edge, borderRadius: 10, color: colors.text, paddingHorizontal: 12, paddingVertical: 10, backgroundColor: colors.bg },
  button: { borderWidth: 1, borderColor: '#635080', borderRadius: 10, minHeight: 44, paddingHorizontal: 14, paddingVertical: 10, alignItems: 'center', justifyContent: 'center' },
  buttonText: { color: colors.accent, fontSize: 13, fontWeight: '700' },
  charter: { borderWidth: 1, borderColor: colors.edge, borderRadius: 12, padding: 12, gap: 6, backgroundColor: colors.bg },
  badge: { paddingHorizontal: 8, paddingVertical: 4, borderRadius: 20, backgroundColor: '#202c42' },
  badgeText: { color: colors.accent, fontSize: 11, fontWeight: '700' },
  trace: { fontFamily: 'monospace', color: '#ddd6fe', fontSize: 12, lineHeight: 18, backgroundColor: colors.bg, padding: 12, borderRadius: 9 },
  error: { color: colors.red, fontSize: 13, lineHeight: 20 },
  ok: { color: colors.green, fontSize: 16, fontWeight: '800' },
  degraded: { color: '#fde68a', fontSize: 16, fontWeight: '800' },
  failed: { color: colors.red, fontSize: 16, fontWeight: '800' },
});
