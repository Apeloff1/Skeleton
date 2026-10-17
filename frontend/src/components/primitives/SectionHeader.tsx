/**
 * <SectionHeader> — punchy 2026-SOTA section divider.
 *
 *  Renders: accent rule (thin gradient bar) │ LABEL │ optional count badge.
 *  Replaces the bland "section: { textTransform: 'uppercase' }" pattern.
 */
import React from 'react';
import { View, Text, StyleSheet, ViewStyle, StyleProp } from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import theme from '../../theme/tokens';

interface SectionHeaderProps {
  label: string;
  count?: number | string;
  accentColor?: string;
  style?: StyleProp<ViewStyle>;
  /** Right-aligned slot for an inline action (e.g. "See all >"). */
  right?: React.ReactNode;
}

export const SectionHeader: React.FC<SectionHeaderProps> = ({
  label, count, accentColor, style, right,
}) => {
  const accent = accentColor || theme.colors.primary;
  return (
    <View style={[styles.row, style]}>
      <View style={styles.barWrap}>
        <LinearGradient
          colors={[accent, accent + '33'] as any}
          start={{ x: 0, y: 0 }}
          end={{ x: 1, y: 0 }}
          style={styles.bar}
        />
      </View>
      <Text style={[styles.label, { color: accent }]} numberOfLines={1}>
        {label}
      </Text>
      {count !== undefined && (
        <View style={[styles.badge, { borderColor: accent + '44', backgroundColor: accent + '14' }]}>
          <Text style={[styles.badgeText, { color: accent }]}>{count}</Text>
        </View>
      )}
      {right ? <View style={{ marginLeft: 'auto' }}>{right}</View> : null}
    </View>
  );
};

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: theme.spacing.sm,
    marginBottom: theme.spacing.sm,
    marginTop: theme.spacing.xs,
  },
  barWrap: {
    width: 18, height: 2,
    borderRadius: theme.radii.full,
    overflow: 'hidden',
  },
  bar: { flex: 1 },
  label: {
    fontSize: 11,
    fontWeight: '800',
    letterSpacing: 1.1,
    textTransform: 'uppercase',
    flexShrink: 1,
  },
  badge: {
    paddingHorizontal: 7, paddingVertical: 2,
    borderRadius: theme.radii.full,
    borderWidth: 1,
    minWidth: 22,
    alignItems: 'center',
  },
  badgeText: {
    fontSize: 10,
    fontWeight: '800',
  },
});

export default SectionHeader;
