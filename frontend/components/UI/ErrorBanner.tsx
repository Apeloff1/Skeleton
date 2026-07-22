// ============================================================================
// CODEDOCK - ERROR BANNER COMPONENT
// ============================================================================

import React from 'react';
import { View, Text, StyleSheet, TouchableOpacity, Animated } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { ThemeColors } from '../../constants/themes';
import { AppError } from '../../types';

interface ErrorBannerProps {
  error: AppError | null;
  onRetry: () => void;
  onDismiss: () => void;
  colors: ThemeColors;
}

export const ErrorBanner: React.FC<ErrorBannerProps> = ({ error, onRetry, onDismiss, colors }) => {
  if (!error) return null;

  return (
    <Animated.View style={[styles.container, { backgroundColor: colors.error + '15', borderColor: colors.error }]}>
      <View style={styles.content}>
        <Ionicons name="alert-circle" size={18} color={colors.error} />
        <Text style={[styles.message, { color: colors.error }]}>{error.message}</Text>
      </View>
      <View style={styles.actions}>
        {error.retry && (
          <TouchableOpacity style={[styles.retryButton, { backgroundColor: colors.error }]} onPress={onRetry}>
            <Ionicons name="refresh" size={14} color="#FFF" />
            <Text style={styles.retryText}>Retry</Text>
          </TouchableOpacity>
        )}
        <TouchableOpacity onPress={onDismiss} style={styles.dismissButton}>
          <Ionicons name="close" size={18} color={colors.error} />
        </TouchableOpacity>
      </View>
    </Animated.View>
  );
};

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 12,
    paddingVertical: 10,
    borderBottomWidth: 1,
  },
  content: {
    flexDirection: 'row',
    alignItems: 'center',
    flex: 1,
    gap: 8,
  },
  message: {
    fontSize: 13,
    fontWeight: '500',
    flex: 1,
  },
  actions: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  retryButton: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 6,
    gap: 4,
  },
  retryText: {
    color: '#FFF',
    fontSize: 12,
    fontWeight: '600',
  },
  dismissButton: {
    padding: 4,
  },
});

export default ErrorBanner;
