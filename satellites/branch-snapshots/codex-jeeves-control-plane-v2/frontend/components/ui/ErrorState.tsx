/**
 * <ErrorState> — premium error display with retry + copy + report path.
 *
 *  Used by:
 *    • ErrorBoundary fallback
 *    • Inline error views inside complex modals (e.g. Galaxy Studio)
 */
import React, { useState } from 'react';
import {
  View, Text, Pressable, StyleSheet, ScrollView, Clipboard as DeprecatedClipboard,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { LinearGradient } from 'expo-linear-gradient';
import theme from '../../theme/tokens';
import { Button } from './Button';

interface ErrorStateProps {
  title?: string;
  message?: string;
  error?: Error | string | null;
  onRetry?: () => void;
  onDismiss?: () => void;
  /** Hide retry button when there's nothing to retry. */
  hideRetry?: boolean;
  /** Provide a path back to safety, e.g. "Back to menu". */
  fallbackAction?: { label: string; onPress: () => void };
  /** Show technical details by default (otherwise behind a toggle). */
  showDetailsDefault?: boolean;
}

export const ErrorState: React.FC<ErrorStateProps> = ({
  title = 'Something went wrong',
  message = 'We hit an unexpected snag rendering this screen. The rest of the app is fine — you can keep going.',
  error, onRetry, hideRetry, fallbackAction, showDetailsDefault,
}) => {
  const [showDetails, setShowDetails] = useState(!!showDetailsDefault);
  const [copied, setCopied] = useState(false);

  const errText = error
    ? typeof error === 'string'
      ? error
      : (error.stack || error.message || String(error))
    : '';

  const copy = () => {
    try {
      // @ts-ignore — Clipboard is deprecated but still works as a fallback.
      DeprecatedClipboard?.setString?.(errText);
      setCopied(true);
      setTimeout(() => setCopied(false), 1600);
    } catch {}
  };

  return (
    <View style={styles.container}>
      <View style={styles.iconWrap}>
        <LinearGradient
          colors={['#EF444433', '#EF444411'] as any}
          style={StyleSheet.absoluteFillObject}
        />
        <Ionicons name="alert-circle" size={44} color={theme.colors.danger} />
      </View>
      <Text style={styles.title}>{title}</Text>
      <Text style={styles.message}>{message}</Text>

      <View style={styles.actions}>
        {!hideRetry && onRetry && (
          <Button label="Try again" icon="refresh" onPress={onRetry} variant="gradient" gradient="brand" />
        )}
        {fallbackAction && (
          <Button label={fallbackAction.label} variant="secondary" onPress={fallbackAction.onPress} />
        )}
      </View>

      {errText ? (
        <Pressable onPress={() => setShowDetails(s => !s)} style={styles.detailsToggle} hitSlop={theme.hitSlop.sm}>
          <Ionicons
            name={showDetails ? 'chevron-down' : 'chevron-forward'}
            size={12}
            color={theme.colors.textMuted}
          />
          <Text style={styles.detailsToggleText}>
            {showDetails ? 'Hide details' : 'Show details'}
          </Text>
        </Pressable>
      ) : null}

      {showDetails && errText ? (
        <View style={styles.details}>
          <ScrollView style={{ maxHeight: 160 }}>
            <Text style={styles.detailsText} selectable>{errText}</Text>
          </ScrollView>
          <Pressable onPress={copy} style={styles.copyBtn} hitSlop={theme.hitSlop.sm}>
            <Ionicons name={copied ? 'checkmark' : 'copy-outline'} size={12} color={theme.colors.textMuted} />
            <Text style={styles.copyBtnText}>{copied ? 'Copied' : 'Copy'}</Text>
          </Pressable>
        </View>
      ) : null}
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    alignItems: 'center',
    padding: theme.spacing.xl,
    gap: theme.spacing.md,
  },
  iconWrap: {
    width: 88, height: 88,
    borderRadius: 44,
    overflow: 'hidden',
    justifyContent: 'center', alignItems: 'center',
    marginBottom: theme.spacing.sm,
  },
  title: {
    ...theme.typography.h2,
    color: theme.colors.text,
    textAlign: 'center',
  },
  message: {
    ...theme.typography.body,
    color: theme.colors.textMuted,
    textAlign: 'center',
    maxWidth: 360,
    lineHeight: 22,
  },
  actions: {
    flexDirection: 'row', gap: theme.spacing.sm, flexWrap: 'wrap',
    justifyContent: 'center', marginTop: theme.spacing.sm,
  },
  detailsToggle: {
    flexDirection: 'row', alignItems: 'center', gap: 4,
    marginTop: theme.spacing.sm,
  },
  detailsToggleText: {
    color: theme.colors.textMuted, fontSize: 11, fontWeight: '700',
  },
  details: {
    width: '100%',
    backgroundColor: theme.colors.bgSubtle,
    borderRadius: theme.radii.md,
    padding: theme.spacing.md,
    borderWidth: 1,
    borderColor: theme.colors.border,
    position: 'relative',
  },
  detailsText: {
    color: theme.colors.textMuted,
    fontFamily: theme.typography.fontFamily.mono,
    fontSize: 11, lineHeight: 16,
    paddingRight: 48,
  },
  copyBtn: {
    position: 'absolute', top: 8, right: 8,
    flexDirection: 'row', alignItems: 'center', gap: 4,
    backgroundColor: theme.colors.surface,
    borderRadius: theme.radii.sm,
    paddingHorizontal: 8, paddingVertical: 4,
    borderWidth: 1, borderColor: theme.colors.border,
  },
  copyBtnText: {
    color: theme.colors.textMuted, fontSize: 10, fontWeight: '700',
  },
});

export default ErrorState;
