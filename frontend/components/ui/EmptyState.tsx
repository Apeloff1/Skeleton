/**
 * <EmptyState> — premium empty state with gradient halo icon, copy, CTA.
 *
 *  Used anywhere a list / collection is empty (My Classes, Search, Gallery,
 *  Flashcards, etc.). Avoids the "thin No data" anti-pattern.
 */
import React from 'react';
import { View, Text, StyleSheet, ViewStyle, StyleProp } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { LinearGradient } from 'expo-linear-gradient';
import theme from '../../theme/tokens';
import { Button } from './Button';

interface EmptyStateProps {
  icon?: keyof typeof Ionicons.glyphMap;
  title: string;
  message?: string;
  accentColor?: string;
  action?: { label: string; onPress: () => void; icon?: keyof typeof Ionicons.glyphMap };
  style?: StyleProp<ViewStyle>;
}

export const EmptyState: React.FC<EmptyStateProps> = ({
  icon = 'sparkles-outline', title, message, accentColor, action, style,
}) => {
  const accent = accentColor || theme.colors.primary;
  return (
    <View style={[styles.wrap, style]}>
      <View style={styles.iconWrap}>
        <LinearGradient
          colors={[accent + '33', accent + '08'] as any}
          style={StyleSheet.absoluteFillObject}
        />
        <Ionicons name={icon} size={32} color={accent} />
      </View>
      <Text style={styles.title}>{title}</Text>
      {message ? <Text style={styles.message}>{message}</Text> : null}
      {action ? (
        <Button
          label={action.label}
          icon={action.icon}
          onPress={action.onPress}
          variant="gradient"
          gradient="brand"
          size="base"
          style={{ marginTop: theme.spacing.md }}
        />
      ) : null}
    </View>
  );
};

const styles = StyleSheet.create({
  wrap: {
    alignItems: 'center',
    paddingVertical: theme.spacing['2xl'],
    paddingHorizontal: theme.spacing.lg,
    gap: theme.spacing.xs,
  },
  iconWrap: {
    width: 72, height: 72, borderRadius: 36,
    overflow: 'hidden',
    justifyContent: 'center', alignItems: 'center',
    marginBottom: theme.spacing.sm,
    borderWidth: 1,
    borderColor: theme.colors.border,
  },
  title: {
    ...theme.typography.h3,
    color: theme.colors.text,
    textAlign: 'center',
  },
  message: {
    ...theme.typography.body,
    color: theme.colors.textMuted,
    textAlign: 'center',
    maxWidth: 320,
    marginTop: 4,
    lineHeight: 20,
  },
});

export default EmptyState;
