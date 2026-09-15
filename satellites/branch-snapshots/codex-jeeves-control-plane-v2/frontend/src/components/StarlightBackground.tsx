/**
 * StarlightBackground
 * -------------------------------------------------------------------
 * Full-screen animated backdrop of slowly-twinkling stars at fixed
 * positions. Each star independently pulses opacity + scale so the
 * field feels alive without distracting motion. Pure RN Animated API —
 * absolute-positioned, pointerEvents='none'.
 */
import { NATIVE_DRIVER } from '../utils/platformStyles';
import React, { useEffect, useMemo, useRef } from 'react';
import { View, Animated, Easing, Dimensions, StyleSheet, Platform } from 'react-native';

interface StarlightProps {
  count?: number;          // total stars (default 64)
  tints?: string[];        // pool of colours for variety
}

const { width: W, height: H } = Dimensions.get('window');

const Twinkle: React.FC<{
  x: number; y: number; size: number; durationMs: number;
  delay: number; minOpacity: number; maxOpacity: number; color: string;
}> = ({ x, y, size, durationMs, delay, minOpacity, maxOpacity, color }) => {
  const opacity = useRef(new Animated.Value(minOpacity)).current;
  const scale   = useRef(new Animated.Value(0.85)).current;

  useEffect(() => {
    // 2026-06 — native-crash hardening (same fix as StarfallBackground):
    // the old `.start(cb => pulse())` recursion recreated Animated nodes on
    // the JS thread forever; with 56 concurrent stars this churned the
    // native bridge and OOM-crashed mid-tier Android (Exynos S20). Use a
    // single native `Animated.loop` instead — zero per-iteration JS work.
    const cycle = Animated.sequence([
      Animated.parallel([
        Animated.timing(opacity, { toValue: maxOpacity, duration: durationMs / 2, easing: Easing.inOut(Easing.sin), useNativeDriver: NATIVE_DRIVER }),
        Animated.timing(scale,   { toValue: 1.15,        duration: durationMs / 2, easing: Easing.inOut(Easing.sin), useNativeDriver: NATIVE_DRIVER }),
      ]),
      Animated.parallel([
        Animated.timing(opacity, { toValue: minOpacity, duration: durationMs / 2, easing: Easing.inOut(Easing.sin), useNativeDriver: NATIVE_DRIVER }),
        Animated.timing(scale,   { toValue: 0.85,        duration: durationMs / 2, easing: Easing.inOut(Easing.sin), useNativeDriver: NATIVE_DRIVER }),
      ]),
    ]);
    const anim = Animated.sequence([Animated.delay(delay), Animated.loop(cycle)]);
    try { anim.start(); } catch { /* decorative — never crash */ }
    return () => {
      try { anim.stop(); } catch {}
      try { opacity.stopAnimation(); } catch {}
      try { scale.stopAnimation(); } catch {}
    };
  }, [opacity, scale, durationMs, delay, minOpacity, maxOpacity]);

  return (
    <Animated.View
      style={[
        styles.star,
        {
          left: x,
          top: y,
          width: size,
          height: size,
          backgroundColor: color,
          // Soft glow on iOS/web only — Android shadow compositing on 56
          // moving views is GPU-expensive and contributed to device crashes.
          ...(Platform.OS === 'web'
            // @ts-ignore — web-only style key
            ? { boxShadow: `0px 0px 4px ${color}` }
            : Platform.OS === 'ios' ? { shadowColor: color } : {}),
          opacity,
          transform: [{ scale }],
        },
      ]}
    />
  );
};

export const StarlightBackground: React.FC<StarlightProps> = ({
  count = 64,
  tints = ['#fef3c7', '#BFDBFE', '#c4b5fd', '#fde68a', '#f9a8d4'],
}) => {
  const stars = useMemo(() => {
    const arr: { x: number; y: number; size: number; dur: number; delay: number; minO: number; maxO: number; color: string }[] = [];
    for (let i = 0; i < count; i++) {
      const sizeRoll = Math.random();
      arr.push({
        x: Math.random() * W,
        y: Math.random() * H,
        size: 1.2 + sizeRoll * 2.6,
        dur: 1800 + Math.random() * 3400,                 // 1.8s – 5.2s pulse cycle
        delay: Math.random() * 2400,
        minO: 0.10 + Math.random() * 0.18,                 // floor
        maxO: 0.55 + Math.random() * 0.45,                 // peak
        color: tints[i % tints.length],
      });
    }
    return arr;
  }, [count, tints]);

  return (
    <View style={[styles.container, { pointerEvents: 'none' }]}>
      {stars.map((s, i) => (
        <Twinkle
          key={i}
          x={s.x}
          y={s.y}
          size={s.size}
          durationMs={s.dur}
          delay={s.delay}
          minOpacity={s.minO}
          maxOpacity={s.maxO}
          color={s.color}
        />
      ))}
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    ...StyleSheet.absoluteFillObject,
    overflow: 'hidden',
  },
  star: {
    position: 'absolute',
    borderRadius: 999,
    ...(Platform.OS === 'web' ? {} : {
      shadowOffset: { width: 0, height: 0 },
      shadowOpacity: 0.8,
      shadowRadius: 4,
    }),
  },
});

export default StarlightBackground;
