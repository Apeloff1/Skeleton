/**
 * Mobile Optimization Hook v11.4
 * Performance optimizations, lazy loading, and resource management
 */

import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { Dimensions, PixelRatio, Platform, InteractionManager } from 'react-native';

interface ScreenMetrics {
  width: number;
  height: number;
  isSmallScreen: boolean;
  isMediumScreen: boolean;
  isLargeScreen: boolean;
  isTablet: boolean;
  fontScale: number;
  pixelDensity: number;
}

interface OptimizationState {
  isReady: boolean;
  isInteracting: boolean;
  shouldLazyLoad: boolean;
  maxListItems: number;
  imageQuality: 'low' | 'medium' | 'high';
}

const getScreenMetrics = (): ScreenMetrics => {
  const { width, height } = Dimensions.get('window');
  const fontScale = PixelRatio.getFontScale();
  const pixelDensity = PixelRatio.get();
  const smallerDim = Math.min(width, height);

  return {
    width,
    height,
    isSmallScreen: smallerDim < 375,
    isMediumScreen: smallerDim >= 375 && smallerDim < 428,
    isLargeScreen: smallerDim >= 428,
    isTablet: smallerDim >= 600,
    fontScale,
    pixelDensity,
  };
};

export function useMobileOptimization() {
  const [metrics, setMetrics] = useState<ScreenMetrics>(getScreenMetrics);
  const [optimization, setOptimization] = useState<OptimizationState>({
    isReady: false,
    isInteracting: false,
    shouldLazyLoad: true,
    maxListItems: 50,
    imageQuality: 'medium',
  });

  const interactionRef = useRef<ReturnType<typeof InteractionManager.runAfterInteractions> | null>(null);

  // Update metrics on dimension change
  useEffect(() => {
    const subscription = Dimensions.addEventListener('change', () => {
      setMetrics(getScreenMetrics());
    });

    return () => subscription.remove();
  }, []);

  // Calculate optimization settings based on device
  useEffect(() => {
    const pixelDensity = PixelRatio.get();
    const { isSmallScreen, isTablet } = metrics;

    // Determine image quality based on pixel density and screen size
    let imageQuality: 'low' | 'medium' | 'high' = 'medium';
    if (pixelDensity <= 2 || isSmallScreen) {
      imageQuality = 'low';
    } else if (pixelDensity >= 3 && isTablet) {
      imageQuality = 'high';
    }

    // Determine max list items based on device capability
    let maxListItems = 50;
    if (isSmallScreen) {
      maxListItems = 30;
    } else if (isTablet) {
      maxListItems = 100;
    }

    setOptimization(prev => ({
      ...prev,
      imageQuality,
      maxListItems,
      isReady: true,
    }));
  }, [metrics]);

  // Run after interactions complete (prevents jank)
  const runAfterInteraction = useCallback(<T,>(callback: () => T): Promise<T> => {
    return new Promise((resolve) => {
      interactionRef.current = InteractionManager.runAfterInteractions(() => {
        resolve(callback());
      });
    });
  }, []);

  // Debounced heavy operations
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const debounce = useCallback((callback: () => void, delay: number = 300) => {
    if (debounceRef.current) {
      clearTimeout(debounceRef.current);
    }
    debounceRef.current = setTimeout(callback, delay);
  }, []);

  // Throttled operations
  const throttleRef = useRef<number>(0);
  const throttle = useCallback((callback: () => void, limit: number = 100) => {
    const now = Date.now();
    if (now - throttleRef.current >= limit) {
      throttleRef.current = now;
      callback();
    }
  }, []);

  // Responsive sizing helpers
  const responsiveSize = useMemo(() => ({
    // Scale sizes based on screen width
    width: (size: number) => (metrics.width / 375) * size,
    height: (size: number) => (metrics.height / 812) * size,
    font: (size: number) => {
      const scaledSize = (metrics.width / 375) * size;
      return Math.round(PixelRatio.roundToNearestPixel(scaledSize));
    },
    // Clamp values between min and max
    clamp: (value: number, min: number, max: number) => Math.min(Math.max(value, min), max),
  }), [metrics]);

  // Touch target sizes (minimum 44pt for iOS, 48dp for Android)
  const touchTargets = useMemo(() => ({
    minimum: Platform.OS === 'ios' ? 44 : 48,
    comfortable: Platform.OS === 'ios' ? 50 : 56,
    large: Platform.OS === 'ios' ? 60 : 64,
  }), []);

  // Spacing scale (8pt grid)
  const spacing = useMemo(() => ({
    xs: 4,
    sm: 8,
    md: 16,
    lg: 24,
    xl: 32,
    xxl: 48,
  }), []);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (interactionRef.current) {
        interactionRef.current.cancel();
      }
      if (debounceRef.current) {
        clearTimeout(debounceRef.current);
      }
    };
  }, []);

  return {
    metrics,
    optimization,
    runAfterInteraction,
    debounce,
    throttle,
    responsiveSize,
    touchTargets,
    spacing,
  };
}
