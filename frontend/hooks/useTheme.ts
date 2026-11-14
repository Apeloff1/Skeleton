// ============================================================================
// CODEDOCK QUANTUM NEXUS - THEME HOOK
// Version: 4.2.0 | Refactored Architecture
// ============================================================================

import { useState, useEffect, useCallback } from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { themes, ThemeColors, ThemeType } from '../constants/themes';
import { STORAGE_KEYS } from '../constants/config';

export const useTheme = () => {
  const [theme, setThemeState] = useState<ThemeType>('dark');
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    loadTheme();
  }, []);

  const loadTheme = async () => {
    try {
      const savedTheme = await AsyncStorage.getItem(STORAGE_KEYS.THEME);
      if (savedTheme === 'light' || savedTheme === 'dark') {
        setThemeState(savedTheme);
      }
    } catch (error) {
      console.error('Failed to load theme:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const setTheme = useCallback(async (newTheme: ThemeType) => {
    try {
      await AsyncStorage.setItem(STORAGE_KEYS.THEME, newTheme);
      setThemeState(newTheme);
    } catch (error) {
      console.error('Failed to save theme:', error);
    }
  }, []);

  const toggleTheme = useCallback(async () => {
    const newTheme = theme === 'dark' ? 'light' : 'dark';
    await setTheme(newTheme);
  }, [theme, setTheme]);

  const colors: ThemeColors = themes[theme];

  return {
    theme,
    colors,
    setTheme,
    toggleTheme,
    isLoading,
    isDark: theme === 'dark',
  };
};

export default useTheme;
