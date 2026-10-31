import React from 'react';
import { StyleSheet, View, type DimensionValue, type ViewStyle } from 'react-native';

type SkeletonProps = {
  width?: DimensionValue;
  height?: number;
  radius?: number;
  style?: ViewStyle | ViewStyle[];
};

type BlockProps = {
  rows?: number;
  gap?: number;
  lastWidth?: DimensionValue;
  height?: number;
  style?: ViewStyle | ViewStyle[];
};

type CircleProps = {
  size?: number;
  style?: ViewStyle | ViewStyle[];
};

function SkeletonBase({ width = '100%', height = 14, radius = 8, style }: SkeletonProps) {
  return <View style={[styles.base, { width, height, borderRadius: radius }, style]} />;
}

function Line(props: SkeletonProps) {
  return <SkeletonBase {...props} />;
}

function Block({ rows = 3, gap = 8, lastWidth = '70%', height = 12, style }: BlockProps) {
  return (
    <View style={style}>
      {Array.from({ length: Math.max(0, rows) }, (_, index) => (
        <View key={index} style={index > 0 ? { marginTop: gap } : undefined}>
          <SkeletonBase width={index === rows - 1 ? lastWidth : '100%'} height={height} />
        </View>
      ))}
    </View>
  );
}

function Circle({ size = 40, style }: CircleProps) {
  return <SkeletonBase width={size} height={size} radius={size / 2} style={style} />;
}

function Card() {
  return (
    <View style={styles.card}>
      <Circle size={40} />
      <View style={styles.cardBody}>
        <SkeletonBase width="70%" height={14} />
        <SkeletonBase width="95%" height={11} />
        <SkeletonBase width="50%" height={11} />
      </View>
    </View>
  );
}

type SkeletonComponent = typeof SkeletonBase & {
  Line: typeof Line;
  Block: typeof Block;
  Circle: typeof Circle;
  Card: typeof Card;
};

const Skeleton = SkeletonBase as SkeletonComponent;
Skeleton.Line = Line;
Skeleton.Block = Block;
Skeleton.Circle = Circle;
Skeleton.Card = Card;

export default Skeleton;
export { Line, Block, Circle, Card };

const styles = StyleSheet.create({
  base: {
    backgroundColor: '#273149',
    overflow: 'hidden',
  },
  card: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    padding: 14,
    backgroundColor: '#0F172A',
    borderRadius: 12,
    borderWidth: 1,
    borderColor: '#1E293B',
    marginBottom: 10,
  },
  cardBody: {
    flex: 1,
    gap: 8,
  },
});
