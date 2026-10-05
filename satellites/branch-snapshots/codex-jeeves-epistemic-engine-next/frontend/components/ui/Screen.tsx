/**
 * <Screen> — base layout primitive for all top-level routes.
 *
 *   • Applies the dark cosmic gradient background.
 *   • Respects safe-area insets (top + bottom).
 *   • Optional StatusBar handling.
 *   • Accepts a children render or a header/scroll pattern via props.
 */
import React from 'react';
import { View, ViewStyle, StyleProp, StyleSheet, StatusBar, Platform } from 'react-native';
import { SafeAreaView} from 'react-native-safe-area-context';
import { LinearGradient } from 'expo-linear-gradient';
import theme from '../../theme/tokens';

interface ScreenProps {
  children: React.ReactNode;
  /** Show animated aurora gradient background (default true). */
  gradient?: boolean;
  /** Disable safe-area top inset (e.g. when a custom header handles it). */
  edges?: ('top' | 'bottom' | 'left' | 'right')[];
  style?: StyleProp<ViewStyle>;
  /** Background override (solid color) — disables gradient. */
  background?: string;
}

export const Screen: React.FC<ScreenProps> = ({
  children, gradient = true, edges = ['top', 'bottom'], style, background,
}) => {
  const bg = background || theme.colors.bg;

  return (
    <View style={[styles.root, { backgroundColor: bg }, style]}>
      {Platform.OS !== 'web' && (
        <StatusBar
          barStyle="light-content"
          backgroundColor="transparent"
          translucent
        />
      )}
      {gradient && !background && (
        <LinearGradient
          colors={theme.gradients.cosmic as any}
          start={{ x: 0.1, y: 0 }}
          end={{ x: 0.9, y: 1 }}
          style={[StyleSheet.absoluteFillObject, { pointerEvents: 'none' }]}
        />
      )}
      <SafeAreaView style={styles.safe} edges={edges as any}>
        {children}
      </SafeAreaView>
    </View>
  );
};

const styles = StyleSheet.create({
  root: { flex: 1 },
  safe: { flex: 1 },
});

export default Screen;
