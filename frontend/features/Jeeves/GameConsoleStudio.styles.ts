import { StyleSheet } from 'react-native';
import theme from '../../theme/tokens';
const C = theme.colors;
const { spacing: p, radii: r, typography: t } = theme;
export default StyleSheet.create({
  workspace: { gap: p.base, width: '100%' }, canvasRow: { flexDirection: 'row', gap: p.base, alignItems: 'flex-start' },
  canvasColumn: { flex: 1, minWidth: 220, gap: p.md }, inspector: { width: 300, gap: p.md, flexShrink: 0 }, compactInspector: { width: '100%' },
  toolbar: { flexDirection: 'row', flexWrap: 'wrap', gap: p.sm, alignItems: 'center' },
  canvas: { borderWidth: 1, borderColor: C.borderStrong, borderRadius: r.md, backgroundColor: C.bg, overflow: 'hidden', width: '100%' },
  canvasCaption: { padding: p.md, borderTopWidth: 1, borderTopColor: C.border, gap: p.xs, backgroundColor: C.surface },
  pixelCanvas: { width: 288, height: 288, maxWidth: '100%', borderWidth: 1, borderColor: C.borderStrong, borderRadius: r.sm, overflow: 'hidden', alignSelf: 'center' },
  swatches: { flexDirection: 'row', flexWrap: 'wrap', gap: p.sm }, swatch: { width: 38, height: 38, borderRadius: r.sm, borderWidth: 2, borderColor: C.borderStrong, alignItems: 'center', justifyContent: 'center' },
  swatchSelected: { borderColor: C.primaryHover }, swatchIndex: { ...t.caption, color: C.text, backgroundColor: C.overlay, paddingHorizontal: 3, borderRadius: r.xs },
  tileSheet: { flexDirection: 'row', flexWrap: 'wrap', gap: p.sm }, tile: { width: 60, gap: p.xs, padding: p.xs, borderRadius: r.sm, borderWidth: 1, borderColor: C.border },
  tileName: { ...t.caption, color: C.textMuted, textAlign: 'center' }, sliderRow: { gap: p.xs }, slider: { width: '100%', height: 32 },
  smallInput: { ...t.monoSm, color: C.text, minWidth: 52, minHeight: 38, backgroundColor: C.bg, borderWidth: 1, borderColor: C.borderStrong, borderRadius: r.sm, paddingHorizontal: p.sm },
  objectList: { maxHeight: 260 }, object: { padding: p.md, borderWidth: 1, borderColor: C.border, borderRadius: r.sm, gap: p.xs, backgroundColor: C.surface },
  property: { gap: p.xs, paddingVertical: p.xs }, rangeLabel: { ...t.caption, color: C.textMuted },
  hint: { ...t.caption, color: C.textDim, lineHeight: 18 }, legend: { flexDirection: 'row', alignItems: 'center', gap: p.sm }, legendDot: { width: 12, height: 12, borderRadius: r.xs },
  colorPreview: { width: '100%', height: 42, borderRadius: r.sm, borderWidth: 1, borderColor: C.borderStrong },
  source: { ...t.mono, color: C.text, minHeight: 360, padding: p.base, lineHeight: 22, textAlignVertical: 'top', borderWidth: 1, borderColor: C.border, borderRadius: r.md, backgroundColor: C.bg },
  responsiveCards: { flexDirection: 'row', flexWrap: 'wrap', gap: p.md }, card: { flex: 1, minWidth: 200, gap: p.sm, padding: p.base, borderRadius: r.md, borderWidth: 1, borderColor: C.border, backgroundColor: C.surface },
});
