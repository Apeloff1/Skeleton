/**
 * Responsive Layout Hook v11.0.0
 * PC/Desktop Experience Adaptation
 * 
 * Provides responsive breakpoints and layout helpers for
 * optimal viewing on both mobile and PC/Desktop platforms
 */

import { useState, useEffect, useCallback } from 'react';
import { Dimensions, Platform } from 'react-native';

export interface LayoutConfig {
  // Screen dimensions
  width: number;
  height: number;
  
  // Device type detection
  isMobile: boolean;
  isTablet: boolean;
  isDesktop: boolean;
  isLandscape: boolean;
  
  // Breakpoint flags
  isSmall: boolean;   // < 576px
  isMedium: boolean;  // 576-768px
  isLarge: boolean;   // 768-992px
  isXLarge: boolean;  // 992-1200px
  isXXLarge: boolean; // > 1200px
  
  // Computed layout values
  editorWidth: number | string;
  sidebarWidth: number;
  toolbarHeight: number;
  fontSize: {
    small: number;
    base: number;
    large: number;
    xlarge: number;
    code: number;
  };
  spacing: {
    xs: number;
    sm: number;
    md: number;
    lg: number;
    xl: number;
  };
  
  // Component visibility
  showSidebar: boolean;
  showMinimap: boolean;
  showLineNumbers: boolean;
  
  // Columns for grids
  columns: number;
  modalWidth: number | string;
}

const BREAKPOINTS = {
  sm: 576,
  md: 768,
  lg: 992,
  xl: 1200,
  xxl: 1400,
};

export function useResponsiveLayout(): LayoutConfig {
  const [dimensions, setDimensions] = useState(() => {
    const { width, height } = Dimensions.get('window');
    return { width, height };
  });

  useEffect(() => {
    const subscription = Dimensions.addEventListener('change', ({ window }) => {
      setDimensions({ width: window.width, height: window.height });
    });
    return () => subscription?.remove();
  }, []);

  const { width, height } = dimensions;
  
  // Device type detection
  const isLandscape = width > height;
  const isMobile = width < BREAKPOINTS.md || Platform.OS !== 'web';
  const isTablet = width >= BREAKPOINTS.md && width < BREAKPOINTS.lg;
  const isDesktop = width >= BREAKPOINTS.lg && Platform.OS === 'web';
  
  // Breakpoint flags
  const isSmall = width < BREAKPOINTS.sm;
  const isMedium = width >= BREAKPOINTS.sm && width < BREAKPOINTS.md;
  const isLarge = width >= BREAKPOINTS.md && width < BREAKPOINTS.lg;
  const isXLarge = width >= BREAKPOINTS.lg && width < BREAKPOINTS.xl;
  const isXXLarge = width >= BREAKPOINTS.xl;
  
  // Compute responsive values
  const editorWidth = isDesktop 
    ? isXXLarge ? '70%' : '65%'
    : '100%';
    
  const sidebarWidth = isDesktop 
    ? isXXLarge ? 280 : 240 
    : 0;
    
  const toolbarHeight = isMobile ? 48 : 56;
  
  // Font sizes based on screen size
  const baseFontSize = isDesktop ? 16 : isTablet ? 15 : 14;
  const fontSize = {
    small: baseFontSize - 2,
    base: baseFontSize,
    large: baseFontSize + 2,
    xlarge: baseFontSize + 6,
    code: isDesktop ? 14 : 13,
  };
  
  // Spacing values
  const baseSpacing = isDesktop ? 8 : 6;
  const spacing = {
    xs: baseSpacing / 2,
    sm: baseSpacing,
    md: baseSpacing * 2,
    lg: baseSpacing * 3,
    xl: baseSpacing * 4,
  };
  
  // Component visibility based on screen size
  const showSidebar = isDesktop;
  const showMinimap = isDesktop && isXLarge;
  const showLineNumbers = true;
  
  // Grid columns
  const columns = isXXLarge ? 4 : isXLarge ? 3 : isLarge ? 2 : 1;
  
  // Modal width
  const modalWidth = isDesktop 
    ? isXXLarge ? '60%' : '80%'
    : '100%';

  return {
    width,
    height,
    isMobile,
    isTablet,
    isDesktop,
    isLandscape,
    isSmall,
    isMedium,
    isLarge,
    isXLarge,
    isXXLarge,
    editorWidth,
    sidebarWidth,
    toolbarHeight,
    fontSize,
    spacing,
    showSidebar,
    showMinimap,
    showLineNumbers,
    columns,
    modalWidth,
  };
}

// Platform-specific keyboard shortcut hints
export const getKeyboardShortcuts = () => {
  const isMac = Platform.OS === 'web' && typeof navigator !== 'undefined' 
    && /Mac/.test(navigator.platform);
  
  const mod = isMac ? '⌘' : 'Ctrl';
  
  return {
    run: `${mod} + Enter`,
    save: `${mod} + S`,
    new: `${mod} + N`,
    find: `${mod} + F`,
    replace: `${mod} + H`,
    undo: `${mod} + Z`,
    redo: isMac ? `${mod} + Shift + Z` : `${mod} + Y`,
    format: `${mod} + Shift + F`,
    comment: `${mod} + /`,
    indent: 'Tab',
    outdent: 'Shift + Tab',
    selectAll: `${mod} + A`,
    duplicate: `${mod} + D`,
    delete: `${mod} + Shift + K`,
    goToLine: `${mod} + G`,
    commandPalette: `${mod} + Shift + P`,
  };
};

// Responsive style helpers
export const responsiveStyles = {
  container: (layout: LayoutConfig) => ({
    flex: 1,
    flexDirection: layout.isDesktop ? 'row' as const : 'column' as const,
    maxWidth: layout.isXXLarge ? 1800 : layout.isXLarge ? 1400 : '100%',
    marginHorizontal: layout.isDesktop ? 'auto' : 0,
  }),
  
  card: (layout: LayoutConfig) => ({
    padding: layout.spacing.md,
    borderRadius: layout.isDesktop ? 12 : 8,
    marginBottom: layout.spacing.md,
  }),
  
  grid: (layout: LayoutConfig) => ({
    flexDirection: 'row' as const,
    flexWrap: 'wrap' as const,
    margin: -layout.spacing.sm,
  }),
  
  gridItem: (layout: LayoutConfig) => ({
    width: `${100 / layout.columns}%` as const,
    padding: layout.spacing.sm,
  }),
  
  heading: (layout: LayoutConfig) => ({
    fontSize: layout.fontSize.xlarge,
    fontWeight: '700' as const,
    marginBottom: layout.spacing.md,
  }),
  
  text: (layout: LayoutConfig) => ({
    fontSize: layout.fontSize.base,
    lineHeight: layout.fontSize.base * 1.5,
  }),
  
  button: (layout: LayoutConfig) => ({
    paddingVertical: layout.spacing.sm,
    paddingHorizontal: layout.spacing.md,
    borderRadius: layout.isDesktop ? 8 : 6,
    minHeight: 44,
  }),
};

export default useResponsiveLayout;
