/**
 * OfflineBanner — slim top-of-screen banner shown when the device is
 * offline. Lives inside _layout.tsx so it's visible everywhere.
 *
 *   • Side-effect: registers `setOfflineState()` with safeFetch so any
 *     in-flight retries can short-circuit when we go offline (prevents
 *     the 2s · 4s · 8s backoff from burning CPU when there's no network).
 *   • UX: Tapping the banner forces a backend health probe and toasts the
 *     result — gives users a way to "retry now" without waiting for the
 *     auto heartbeat.
 *
 * 2026-02 — Added tap-to-retry comfort + a subtle breathing dot animation.
 */
import { NATIVE_DRIVER } from '../src/utils/platformStyles';
import React, { useEffect, useRef } from 'react';
import { Text, StyleSheet, Animated, Pressable, Platform } from 'react-native';
import { useNetworkStatus } from '../utils/useNetworkStatus';
import { setOfflineState } from '../utils/safeFetch';
import { toast } from './Toast';
import { isReduceMotionOn } from '../utils/haptics';

const BACKEND = process.env.EXPO_PUBLIC_BACKEND_URL || '';

async function probeOnline(): Promise<boolean> {
  if (!BACKEND) return false;
  try {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), 4000);
    const res = await fetch(`${BACKEND}/api/health`, { signal: ctrl.signal });
    clearTimeout(t);
    return res.ok;
  } catch {
    return false;
  }
}

export default function OfflineBanner() {
  const { online } = useNetworkStatus();
  const opacity   = useRef(new Animated.Value(0)).current;
  const dotPulse  = useRef(new Animated.Value(1)).current;
  const probing   = useRef(false);

  useEffect(() => {
    try { setOfflineState(!online); } catch { /* swallow */ }
    Animated.timing(opacity, {
      toValue: online ? 0 : 1,
      duration: 180,
      useNativeDriver: NATIVE_DRIVER,
    }).start();
  }, [online, opacity]);

  // Soft breathing pulse on the indicator dot while offline.
  // Skipped entirely when Reduce-Motion is on so vestibular-sensitive
  // users don't see an oscillating element.
  useEffect(() => {
    if (online || isReduceMotionOn()) {
      dotPulse.setValue(1);
      return;
    }
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(dotPulse, { toValue: 0.5, duration: 700, useNativeDriver: Platform.OS !== 'web' }),
        Animated.timing(dotPulse, { toValue: 1.0, duration: 700, useNativeDriver: Platform.OS !== 'web' }),
      ]),
    );
    loop.start();
    return () => loop.stop();
  }, [online, dotPulse]);

  const retry = async () => {
    if (probing.current) return;
    probing.current = true;
    toast.info('Checking connection…', { durationMs: 1200 });
    const ok = await probeOnline();
    probing.current = false;
    if (ok) {
      // setOfflineState toggles safeFetch; useNetworkStatus will pick this up
      // on its next heartbeat. Toast the user immediately for snappy feedback.
      try { setOfflineState(false); } catch { /* swallow */ }
      toast.success('Back online');
    } else {
      toast.error('Still offline · check Wi-Fi or data');
    }
  };

  if (online) return null;

  return (
    <Animated.View style={[styles.barWrap, { opacity }]}>
      <Pressable
        onPress={retry}
        style={styles.bar}
        accessibilityLabel="Retry connection"
        testID="offline-banner-retry"
      >
        <Animated.View style={[styles.dot, { opacity: dotPulse }]} />
        <Text style={styles.text}>Offline · retries paused · tap to retry</Text>
      </Pressable>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  barWrap: {
    position: 'absolute',
    top: 0, left: 0, right: 0,
    zIndex: 999,
    elevation: 8,
  },
  bar: {
    backgroundColor: '#7f1d1d',
    paddingHorizontal: 14,
    paddingVertical: 6,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  dot:  { width: 8, height: 8, borderRadius: 4, backgroundColor: '#fecaca' },
  text: { color: '#fecaca', fontSize: 11, fontWeight: '700', letterSpacing: 0.4 },
});
