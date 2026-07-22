/**
 * <Surface> — frosted/elevated container.
 *
 *   • Default = subtle elevated card.
 *   • variant="glass" = blurred glassmorphic surface (uses expo-blur on native,
 *     falls back to translucent backgroundColor on web).
 *   • variant="gradient" = brand gradient surface.
 */
import React from 'react';
import { View, ViewStyle, StyleProp, StyleSheet, Platform } from 'react-native';
import { BlurView } from 'expo-blur';
import { LinearGradient } from 'expo-linear-gradient';
import theme from '../../theme/tokens';

type Variant = 'solid' | 'glass' | 'gradient' | 'outline';

interface SurfaceProps {
  children: React.ReactNode;
  variant?: Variant;
  radius?: keyof typeof theme.radii;
  padding?: keyof typeof theme.spacing;
  elevation?: keyof typeof theme.elevation;
  style?: StyleProp<ViewStyle>;
  /** For variant="gradient" only — pick a gradient preset. */
  gradient?: keyof typeof theme.gradients;
  /** For variant="glass" only — blur intensity (1-100). */
  blurIntensity?: number;
  /** Tint for glass on web (where blur isn't available). */
  glassTint?: string;
}

export const Surface: React.FC<SurfaceProps> = ({
  children, variant = 'solid', radius = 'lg', padding = 'base',
  elevation = 'sm', style, gradient = 'glass', blurIntensity = 60, glassTint,
}) => {
  const base: ViewStyle = {
    borderRadius: theme.radii[radius],
    padding: theme.spacing[padding],
    overflow: 'hidden',
  };

  if (variant === 'gradient') {
    return (
      <LinearGradient
        colors={theme.gradients[gradient] as any}
        start={{ x: 0, y: 0 }}
        end={{ x: 1, y: 1 }}
        style={[base, theme.elevation[elevation], style]}
      >
        {children}
      </LinearGradient>
    );
  }

  if (variant === 'glass') {
    if (Platform.OS === 'web') {
      return (
        <View
          style={[
            base,
            {
              backgroundColor: glassTint || theme.colors.surface,
              borderWidth: 1,
              borderColor: theme.colors.border,
              // CSS backdrop-filter on web for true glass
              // @ts-ignore — web-only style
              backdropFilter: 'blur(20px) saturate(160%)',
              // @ts-ignore
              WebkitBackdropFilter: 'blur(20px) saturate(160%)',
            },
            theme.elevation[elevation],
            style,
          ]}
        >
          {children}
        </View>
      );
    }
    return (
      <View style={[base, { borderWidth: 1, borderColor: theme.colors.border }, theme.elevation[elevation], style]}>
        <BlurView
          tint="dark"
          intensity={blurIntensity}
          style={StyleSheet.absoluteFillObject}
        />
        <View style={[{ backgroundColor: glassTint || 'rgba(15,23,42,0.45)', ...StyleSheet.absoluteFillObject }, { pointerEvents: 'none' }]} />
        {children}
      </View>
    );
  }

  if (variant === 'outline') {
    return (
      <View
        style={[
          base,
          { backgroundColor: 'transparent', borderWidth: 1, borderColor: theme.colors.borderStrong },
          style,
        ]}
      >
        {children}
      </View>
    );
  }

  // solid
  return (
    <View
      style={[
        base,
        { backgroundColor: theme.colors.bgElevated, borderWidth: 1, borderColor: theme.colors.border },
        theme.elevation[elevation],
        style,
      ]}
    >
      {children}
    </View>
  );
};

export default Surface;
