/**
 * TunnelStatusPill — small colored badge showing ngrok/tunnel health.
 * Uses resilientNet's heartbeat to classify as healthy / degraded / offline.
 * Drop into any screen header to keep users informed when the backend is
 * struggling — the app keeps running on cache either way.
 */
import React from 'react';
import { View, Text, StyleSheet, Pressable } from 'react-native';
import { useTunnelHealth } from '../hooks/useTunnelHealth';

interface Props {
  onPress?: () => void;
  compact?: boolean;
}

const COLORS: Record<string, { bg: string; dot: string; label: string }> = {
  healthy:  { bg: 'rgba(16,185,129,0.15)',  dot: '#10B981', label: 'Live' },
  degraded: { bg: 'rgba(245,158,11,0.18)',  dot: '#F59E0B', label: 'Syncing' },
  offline:  { bg: 'rgba(239,68,68,0.18)',   dot: '#EF4444', label: 'Cache'   },
  unknown:  { bg: 'rgba(107,114,128,0.18)', dot: '#9CA3AF', label: '...'     },
};

export const TunnelStatusPill: React.FC<Props> = ({ onPress, compact = false }) => {
  const h = useTunnelHealth();
  const c = COLORS[h.status] || COLORS.unknown;

  const rtt = h.rttMs ? `${Math.round(h.rttMs)}ms` : '';
  const ageSec = h.lastOkTs ? Math.round((Date.now() - h.lastOkTs) / 1000) : null;
  const hint =
    h.status === 'healthy' ? (rtt || 'OK')
    : h.status === 'degraded' ? `retrying${ageSec != null ? ` • ${ageSec}s` : ''}`
    : h.status === 'offline' ? 'tunnel down — using cache'
    : 'checking…';

  const body = (
    <View style={[s.pill, { backgroundColor: c.bg }]}>
      <View style={[s.dot, { backgroundColor: c.dot }]} />
      {!compact && (
        <Text style={[s.label, { color: c.dot }]} numberOfLines={1}>
          {c.label}
          <Text style={s.hint}> · {hint}</Text>
        </Text>
      )}
    </View>
  );

  if (onPress) {
    return (
      <Pressable onPress={onPress} accessibilityRole="button" accessibilityLabel={`Tunnel ${c.label}: ${hint}`}>
        {body}
      </Pressable>
    );
  }
  return body;
};

const s = StyleSheet.create({
  pill: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 12,
    gap: 6,
  },
  dot: {
    width: 8, height: 8, borderRadius: 4,
  },
  label: {
    fontSize: 11,
    fontWeight: '700',
  },
  hint: {
    fontWeight: '400',
    opacity: 0.8,
  },
});

export default TunnelStatusPill;
