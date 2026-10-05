/**
 * src/components/Skeleton.tsx — Skeleton placeholders for hub/screen loads.
 *
 * Use INSTEAD of a bare spinner during async data fetches.
 * `<Skeleton w={120} h={16} />`     — small text line
 * `<Skeleton.Card />`                — a typical card placeholder
 * Honours system reduce-motion.
 */
import { NATIVE_DRIVER } from '../utils/platformStyles';
import React from 'react';
import {
  View, StyleSheet, Animated, Easing, AccessibilityInfo,
} from 'react-native';

interface BoxProps { w?: number | string; h?: number; rounded?: number; style?: any }

function Box({ w = '100%', h = 14, rounded = 6, style }: BoxProps) {
  const opacity = React.useRef(new Animated.Value(0.4)).current;
  const [reduceMotion, setReduceMotion] = React.useState(false);

  React.useEffect(() => {
    AccessibilityInfo.isReduceMotionEnabled().then(setReduceMotion).catch(() => {});
  }, []);

  React.useEffect(() => {
    if (reduceMotion) return;
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(opacity, { toValue: 0.8, duration: 700, easing: Easing.inOut(Easing.quad), useNativeDriver: NATIVE_DRIVER }),
        Animated.timing(opacity, { toValue: 0.4, duration: 700, easing: Easing.inOut(Easing.quad), useNativeDriver: NATIVE_DRIVER }),
      ])
    );
    loop.start();
    return () => loop.stop();
  }, [opacity, reduceMotion]);

  return (
    <Animated.View
      accessibilityRole="progressbar"
      accessibilityLabel="Loading"
      style={[
        { width: w as any, height: h, borderRadius: rounded, backgroundColor: '#1f2937', opacity },
        style,
      ]}
    />
  );
}

function Card() {
  return (
    <View style={styles.card}>
      <Box w={48} h={48} rounded={24} />
      <View style={{ flex: 1, marginLeft: 12 }}>
        <Box w="60%" h={14} />
        <View style={{ height: 8 }} />
        <Box w="40%" h={11} />
      </View>
    </View>
  );
}

function List({ count = 4 }: { count?: number }) {
  return (
    <View>
      {Array.from({ length: count }, (_, i) => <Card key={i} />)}
    </View>
  );
}

const Skeleton = Object.assign(Box, { Card, List });
export default Skeleton;
export { Skeleton };

const styles = StyleSheet.create({
  card: {
    flexDirection: 'row', alignItems: 'center',
    padding: 14, marginVertical: 6, borderRadius: 14,
    backgroundColor: '#0f172a55',
  },
});
