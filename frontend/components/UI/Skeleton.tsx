import React from 'react';
import { View, StyleSheet, ViewStyle } from 'react-native';

type LineProps = {
  width?: number | string;
  height?: number;
  radius?: number;
  style?: ViewStyle | ViewStyle[];
};

function Line({ width = '100%', height = 12, radius = 6, style }: LineProps) {
  return <View style={[styles.line, { width: width as any, height, borderRadius: radius }, style]} />;
}

function Block({ rows = 3, gap = 8, lastWidth = '70%', height = 12, style }: any) {
  return (
    <View style={style}>
      {Array.from({ length: Math.max(0, rows) }, (_, index) => (
        <View key={index} style={index > 0 ? { marginTop: gap } : undefined}>
          <Line width={index === rows - 1 ? lastWidth : '100%'} height={height} />
        </View>
      ))}
    </View>
  );
}

function Circle({ size = 40, style }: any) {
  return <View style={[styles.line, { width: size, height: size, borderRadius: size / 2 }, style]} />;
}

const Skeleton = { Line, Block, Circle };
export default Skeleton;
export { Line, Block, Circle };

const styles = StyleSheet.create({
  line: {
    backgroundColor: '#273149',
    overflow: 'hidden',
  },
});
