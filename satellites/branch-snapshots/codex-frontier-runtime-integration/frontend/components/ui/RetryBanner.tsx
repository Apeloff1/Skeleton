/**
 * RetryBanner — inline retry banner with countdown and optional auto-retry.
 *
 *   <RetryBanner
 *     error="Couldn't reach jeeves-eq."
 *     onRetry={() => fetchAll()}
 *     autoMs={5000}      // optional: auto-fire after N ms (countdown shown)
 *   />
 *
 * Designed to slot above a failed list/screen without consuming the
 * whole viewport. Animates in from above when first mounted.
 */
import { NATIVE_DRIVER } from '../../src/utils/platformStyles';
import React, { useEffect, useRef, useState } from 'react';
import { Text, TouchableOpacity, StyleSheet, Animated, Easing, Platform } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { isReduceMotionOn } from '../../utils/haptics';

interface Props {
  /** Short error string — keep it human ("Couldn't reach the toolchain probe"). */
  error?: string | null;
  /** Called when the user taps "Retry" or the auto-retry timer fires. */
  onRetry: () => void;
  /** When set, banner auto-retries after this many ms (and shows a countdown). */
  autoMs?: number;
  /** Hide the banner entirely. */
  visible?: boolean;
  /** Inline label override for the action button. */
  retryLabel?: string;
}

export default function RetryBanner({
  error,
  onRetry,
  autoMs,
  visible = true,
  retryLabel = 'Retry',
}: Props) {
  const slide = useRef(new Animated.Value(Platform.OS === 'web' ? 0 : -40)).current;
  const [remaining, setRemaining] = useState<number | null>(autoMs ? Math.ceil(autoMs / 1000) : null);

  // Slide in from above on mount (skip on web — translateY+useNativeDriver
  // can hide the banner off-canvas on some web shims).
  useEffect(() => {
    if (!visible) return;
    if (Platform.OS === 'web' || isReduceMotionOn()) {
      slide.setValue(0);
      return;
    }
    Animated.timing(slide, {
      toValue: 0,
      duration: 220,
      easing: Easing.out(Easing.quad),
      useNativeDriver: NATIVE_DRIVER,
    }).start();
  }, [visible, slide]);

  // Countdown + auto-retry.
  useEffect(() => {
    if (!visible || !autoMs) { setRemaining(null); return; }
    setRemaining(Math.ceil(autoMs / 1000));
    const start = Date.now();
    const tick = setInterval(() => {
      const left = autoMs - (Date.now() - start);
      if (left <= 0) {
        clearInterval(tick);
        setRemaining(0);
        onRetry();
      } else {
        setRemaining(Math.ceil(left / 1000));
      }
    }, 250);
    return () => clearInterval(tick);
    // intentionally re-run only when autoMs / visible change
  }, [autoMs, visible, onRetry]);

  if (!visible || !error) return null;

  return (
    <Animated.View style={[styles.row, { transform: [{ translateY: slide }] }]}>
      <Ionicons name="warning" size={14} color="#fbbf24" />
      <Text style={styles.msg} numberOfLines={2}>{error}</Text>
      <TouchableOpacity onPress={onRetry} hitSlop={10} style={styles.btn} accessibilityLabel="Retry now">
        <Ionicons name="refresh" size={12} color="#0a0f1f" />
        <Text style={styles.btnTxt}>
          {retryLabel}
          {remaining !== null && remaining > 0 ? ` · ${remaining}s` : ''}
        </Text>
      </TouchableOpacity>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    backgroundColor: '#3f290033',
    borderColor: '#fbbf2455',
    borderWidth: 1,
    paddingHorizontal: 12,
    paddingVertical: 10,
    borderRadius: 10,
    marginBottom: 10,
  },
  msg: { flex: 1, color: '#fde68a', fontSize: 12, lineHeight: 17 },
  btn: {
    flexDirection: 'row', alignItems: 'center', gap: 4,
    backgroundColor: '#fbbf24',
    paddingHorizontal: 10, paddingVertical: 6,
    borderRadius: 999,
  },
  btnTxt: { color: '#0a0f1f', fontSize: 11, fontWeight: '800' },
});
