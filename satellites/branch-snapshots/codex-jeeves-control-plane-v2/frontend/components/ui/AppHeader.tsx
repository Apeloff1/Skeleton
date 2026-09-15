/**
 * <AppHeader> — slim glassy header with back / title / actions.
 */
import React from 'react';
import { View, Text, Pressable, StyleSheet, ViewStyle, StyleProp } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import theme from '../../theme/tokens';

interface AppHeaderProps {
  title?: string;
  subtitle?: string;
  onBack?: () => void;
  backIcon?: keyof typeof Ionicons.glyphMap;
  right?: React.ReactNode;
  style?: StyleProp<ViewStyle>;
  /** Render the title centered (modal style) vs left-aligned. */
  centered?: boolean;
}

export const AppHeader: React.FC<AppHeaderProps> = ({
  title, subtitle, onBack, backIcon = 'arrow-back', right, style, centered,
}) => (
  <View style={[styles.row, style]}>
    {onBack ? (
      <Pressable onPress={onBack} style={styles.btn} hitSlop={theme.hitSlop.md} accessibilityRole="button" accessibilityLabel="Go back">
        <Ionicons name={backIcon} size={22} color={theme.colors.text} />
      </Pressable>
    ) : <View style={styles.btn} />}
    <View style={[styles.titleWrap, centered && { alignItems: 'center' }]}>
      {title ? <Text style={styles.title} numberOfLines={1}>{title}</Text> : null}
      {subtitle ? <Text style={styles.subtitle} numberOfLines={1}>{subtitle}</Text> : null}
    </View>
    <View style={styles.rightSlot}>
      {right}
    </View>
  </View>
);

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row', alignItems: 'center',
    paddingHorizontal: theme.spacing.md,
    paddingVertical: theme.spacing.sm,
    gap: theme.spacing.sm,
  },
  btn: {
    width: 44, height: 44,
    justifyContent: 'center', alignItems: 'center',
    borderRadius: theme.radii.md,
  },
  rightSlot: {
    minWidth: 44,
    minHeight: 44,
    flexDirection: 'row',
    justifyContent: 'flex-end',
    alignItems: 'center',
  },
  titleWrap: { flex: 1, justifyContent: 'center' },
  title: { ...theme.typography.h3, color: theme.colors.text },
  subtitle: {
    ...theme.typography.caption,
    color: theme.colors.textMuted,
    fontWeight: '500',
    marginTop: 1,
  },
});

export default AppHeader;
