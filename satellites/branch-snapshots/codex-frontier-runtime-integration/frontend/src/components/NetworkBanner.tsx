/**
 * src/components/NetworkBanner.tsx — slim, theme-aware offline indicator.
 *
 * Renders a 1-line banner at the very top of the wrapped screen when the
 * device drops offline. Visibility is **gated by the dynamic feature flag
 * ``hub.network_banner``** so it can be killed remotely without shipping a
 * new build.
 *
 * Uses ``useNetworkStatus`` for the actual NetInfo subscription and
 * ``useReduceMotion`` so we honour the OS Reduce-Motion preference.
 */
import React from 'react';
import { Text, StyleSheet, Platform, Animated, Easing } from 'react-native';
import { useNetworkStatus } from '../hooks/useNetworkStatus';
import { useReduceMotion } from '../hooks/useReduceMotion';
import { useFeatureFlag, FLAG } from '../feature-flags';

interface Props {
  /** Default behaviour if the feature-flag lookup hasn't returned yet. */
  defaultEnabled?: boolean;
}

export const NetworkBanner: React.FC<Props> = ({ defaultEnabled = true }) => {
  const enabled = useFeatureFlag(FLAG.HUB_NETWORK_BANNER, defaultEnabled);
  const status  = useNetworkStatus();
  const reduce  = useReduceMotion();
  const translateY = React.useRef(new Animated.Value(-40)).current;
  const offline = status === 'offline';

  React.useEffect(() => {
    if (!enabled) return;
    const to = offline ? 0 : -40;
    if (reduce) { translateY.setValue(to); return; }
    Animated.timing(translateY, {
      toValue: to,
      duration: 220,
      easing: Easing.out(Easing.quad),
      useNativeDriver: Platform.OS !== 'web',
    }).start();
  }, [offline, enabled, reduce, translateY]);

  if (!enabled || !offline) return null;

  return (
    <Animated.View style={[styles.wrap, { transform: [{ translateY }] }, { pointerEvents: 'none' }]}>
      <Text style={styles.txt} numberOfLines={1}>
        Offline — changes will sync when you reconnect
      </Text>
    </Animated.View>
  );
};

const styles = StyleSheet.create({
  wrap: {
    position: 'absolute',
    top: 0, left: 0, right: 0,
    paddingTop: Platform.OS === 'ios' ? 38 : 12,
    paddingBottom: 8,
    paddingHorizontal: 16,
    backgroundColor: '#7c2d12',  // warm amber/red, high contrast
    zIndex: 9999,
    alignItems: 'center',
  },
  txt: {
    color: '#fff7ed',
    fontSize: 12,
    fontWeight: '600',
    letterSpacing: 0.3,
  },
});

export default NetworkBanner;
