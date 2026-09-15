/**
 * Skeleton — animated shimmer placeholder for async loading states.
 *
 *   <Skeleton width="80%" height={16} />
 *   <Skeleton.Block rows={3} gap={8} />        // shortcut for paragraph
 *   <Skeleton.Card />                          // pre-shaped feature card
 *
 * Respects the global reduce-motion preference (haptics.isReduceMotionOn)
 * by holding the shimmer stationary instead of animating.
 */
import { NATIVE_DRIVER } from '../../src/utils/platformStyles';
import React, { useEffect, useRef } from 'react';
import { View, StyleSheet, Animated, ViewStyle, DimensionValue, Easing } from 'react-native';
import { isReduceMotionOn } from '../../utils/haptics';

interface SkeletonProps {
  width?:  DimensionValue;
  height?: number;
  radius?: number;
  style?:  ViewStyle | ViewStyle[];
}

function Skeleton({ width = '100%', height = 14, radius = 8, style }: SkeletonProps) {
  const op = useRef(new Animated.Value(0.35)).current;

  useEffect(() => {
    if (isReduceMotionOn()) {
      op.setValue(0.5);
      return;
    }
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(op, { toValue: 0.85, duration: 700, easing: Easing.inOut(Easing.quad), useNativeDriver: NATIVE_DRIVER }),
        Animated.timing(op, { toValue: 0.35, duration: 700, easing: Easing.inOut(Easing.quad), useNativeDriver: NATIVE_DRIVER }),
      ]),
    );
    loop.start();
    return () => loop.stop();
  }, [op]);

  return (
    <Animated.View
      style={[
        styles.base,
        { width, height, borderRadius: radius, opacity: op },
        style as any,
      ]}
    />
  );
}

/** Stacked paragraph (e.g. for description previews). */
function Block({ rows = 3, gap = 8, lastWidth = '60%' as DimensionValue }: { rows?: number; gap?: number; lastWidth?: DimensionValue }) {
  return (
    <View style={{ gap }}>
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} width={i === rows - 1 ? lastWidth : '100%'} height={12} />
      ))}
    </View>
  );
}

/** Pre-shaped feature card skeleton. */
function Card() {
  return (
    <View style={styles.card}>
      <Skeleton width={40} height={40} radius={10} />
      <View style={{ flex: 1, gap: 8 }}>
        <Skeleton width="70%" height={14} />
        <Skeleton width="95%" height={11} />
        <Skeleton width="50%" height={11} />
      </View>
    </View>
  );
}

Skeleton.Block = Block;
Skeleton.Card = Card;

const styles = StyleSheet.create({
  base: {
    backgroundColor: '#1e293b',
  },
  card: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    padding: 14,
    backgroundColor: '#0f172a',
    borderRadius: 12,
    borderWidth: 1,
    borderColor: '#1e293b',
    marginBottom: 10,
  },
});

export default Skeleton;
