/**
 * Unified connectivity banner for device-network and backend-tunnel state.
 *
 * This component also mirrors the device connectivity state into safeFetch so
 * retry loops can short-circuit while the device is offline. Keeping that side
 * effect here lets the root layout mount a single network observer instead of
 * two competing banner implementations.
 */
import React from 'react';
import { Animated, Platform, StyleSheet, Text } from 'react-native';
import { useNetworkStatus } from '../hooks/useNetworkStatus';
import { useTunnelStatus } from '../hooks/useTunnelStatus';
import { useReduceMotion } from '../hooks/useReduceMotion';
import { useFeatureFlag, FLAG } from '../feature-flags';
import { setOfflineState } from '../../utils/safeFetch';

type Variant = 'down' | 'offline' | 'degraded' | null;

function decideVariant(net: 'online' | 'offline' | 'unknown', tunnel: string): Variant {
  if (net === 'offline') return 'offline';
  if (tunnel === 'down') return 'down';
  if (tunnel === 'degraded') return 'degraded';
  return null;
}

const MESSAGES: Record<Exclude<Variant, null>, { text: string; bg: string; fg: string }> = {
  down: { text: 'Server unreachable — retrying…', bg: '#7f1d1d', fg: '#fee2e2' },
  offline: { text: 'Offline — changes will sync when you reconnect', bg: '#7c2d12', fg: '#fff7ed' },
  degraded: { text: 'Server is slow — some actions may be delayed', bg: '#854d0e', fg: '#fef3c7' },
};

export const StabilityBanner: React.FC<{ defaultEnabled?: boolean }> = ({ defaultEnabled = true }) => {
  const enabled = useFeatureFlag(FLAG.HUB_NETWORK_BANNER, defaultEnabled);
  const net = useNetworkStatus();
  const { status: tunnel } = useTunnelStatus();
  const reduce = useReduceMotion();
  const translateY = React.useRef(new Animated.Value(-44)).current;

  React.useEffect(() => {
    try {
      if (net === 'offline') setOfflineState(true);
      else if (net === 'online') setOfflineState(false);
    } catch { /* connectivity must never block rendering */ }
  }, [net]);

  const variant: Variant = enabled ? decideVariant(net, tunnel) : null;

  React.useEffect(() => {
    const target = variant ? 0 : -44;
    if (reduce) {
      translateY.setValue(target);
      return;
    }
    Animated.timing(translateY, {
      toValue: target,
      duration: 220,
      useNativeDriver: Platform.OS !== 'web',
    }).start();
  }, [variant, reduce, translateY]);

  if (!variant) return null;
  const message = MESSAGES[variant];

  return (
    <Animated.View
      style={[
        styles.wrap,
        { backgroundColor: message.bg, transform: [{ translateY }] },
        { pointerEvents: 'none' },
      ]}
    >
      <Text style={[styles.txt, { color: message.fg }]} numberOfLines={1}>
        {message.text}
      </Text>
    </Animated.View>
  );
};

const styles = StyleSheet.create({
  wrap: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    paddingTop: Platform.OS === 'ios' ? 38 : 12,
    paddingBottom: 8,
    paddingHorizontal: 16,
    zIndex: 9999,
    alignItems: 'center',
  },
  txt: { fontSize: 12, fontWeight: '600', letterSpacing: 0.3 },
});

export default StabilityBanner;
