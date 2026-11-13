import React from 'react';
import { View, Text, Pressable, StyleSheet } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

export default function RetryBanner({ error, message, onRetry, retryLabel = 'Retry', style }: any) {
  return (
    <View accessibilityRole="alert" style={[styles.root, style]}>
      <View style={styles.iconWrap}>
        <Ionicons name="warning-outline" size={20} color="#F59E0B" />
      </View>
      <Text style={styles.message}>{error || message || 'Something went wrong.'}</Text>
      {onRetry ? (
        <Pressable accessibilityRole="button" onPress={onRetry} style={styles.retry}>
          <Ionicons name="refresh" size={15} color="#EDE9FE" />
          <Text style={styles.retryText}>{retryLabel}</Text>
        </Pressable>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  root: {
    minHeight: 56,
    paddingHorizontal: 12,
    paddingVertical: 10,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: '#5B4630',
    backgroundColor: '#241D17',
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  iconWrap: {
    width: 30,
    height: 30,
    borderRadius: 15,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#3A2B18',
  },
  message: {
    flex: 1,
    color: '#FDE68A',
    fontSize: 13,
    lineHeight: 18,
  },
  retry: {
    minHeight: 34,
    paddingHorizontal: 10,
    borderRadius: 9,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 5,
    backgroundColor: '#5B21B6',
  },
  retryText: {
    color: '#EDE9FE',
    fontSize: 12,
    fontWeight: '700',
  },
});
