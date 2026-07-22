// ============================================================================
// CODEDOCK QUANTUM NEXUS - STORAGE HOOK
// Version: 4.2.0 | Refactored Architecture
// ============================================================================

import { useState, useEffect, useCallback } from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { STORAGE_KEYS } from '../constants/config';
import { BibleProgress } from '../types';

const DEFAULT_BIBLE_PROGRESS: BibleProgress = {
  completedChapters: {},
  bookmarks: [],
  exerciseResults: {},
  totalTimeSpent: 0,
  streak: 0,
};

export const useStorage = () => {
  const [tutorialCompleted, setTutorialCompletedState] = useState(false);
  const [advancedUnlocked, setAdvancedUnlockedState] = useState(false);
  const [bibleProgress, setBibleProgressState] = useState<BibleProgress>(DEFAULT_BIBLE_PROGRESS);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    loadAllData();
  }, []);

  const loadAllData = async () => {
    try {
      const [tutorial, advanced, bible] = await Promise.all([
        AsyncStorage.getItem(STORAGE_KEYS.TUTORIAL_COMPLETED),
        AsyncStorage.getItem(STORAGE_KEYS.ADVANCED_UNLOCKED),
        AsyncStorage.getItem(STORAGE_KEYS.BIBLE_PROGRESS),
      ]);

      setTutorialCompletedState(tutorial === 'true');
      setAdvancedUnlockedState(advanced === 'true');
      
      if (bible) {
        setBibleProgressState({ ...DEFAULT_BIBLE_PROGRESS, ...JSON.parse(bible) });
      }
    } catch (error) {
      console.error('Failed to load storage:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const setTutorialCompleted = useCallback(async (value: boolean) => {
    try {
      await AsyncStorage.setItem(STORAGE_KEYS.TUTORIAL_COMPLETED, String(value));
      setTutorialCompletedState(value);
    } catch (error) {
      console.error('Failed to save tutorial status:', error);
    }
  }, []);

  const setAdvancedUnlocked = useCallback(async (value: boolean) => {
    try {
      await AsyncStorage.setItem(STORAGE_KEYS.ADVANCED_UNLOCKED, String(value));
      setAdvancedUnlockedState(value);
    } catch (error) {
      console.error('Failed to save advanced status:', error);
    }
  }, []);

  const updateBibleProgress = useCallback(async (updates: Partial<BibleProgress>) => {
    try {
      const newProgress = { ...bibleProgress, ...updates };
      await AsyncStorage.setItem(STORAGE_KEYS.BIBLE_PROGRESS, JSON.stringify(newProgress));
      setBibleProgressState(newProgress);
    } catch (error) {
      console.error('Failed to save bible progress:', error);
    }
  }, [bibleProgress]);

  const markChapterComplete = useCallback(async (chapterId: string) => {
    const newCompletedChapters = { ...bibleProgress.completedChapters, [chapterId]: true };
    await updateBibleProgress({ completedChapters: newCompletedChapters });
  }, [bibleProgress, updateBibleProgress]);

  const toggleBookmark = useCallback(async (chapterId: string) => {
    const bookmarks = bibleProgress.bookmarks.includes(chapterId)
      ? bibleProgress.bookmarks.filter(b => b !== chapterId)
      : [...bibleProgress.bookmarks, chapterId];
    await updateBibleProgress({ bookmarks });
  }, [bibleProgress, updateBibleProgress]);

  const markExerciseComplete = useCallback(async (exerciseId: string, passed: boolean) => {
    const newResults = { ...bibleProgress.exerciseResults, [exerciseId]: passed };
    await updateBibleProgress({ exerciseResults: newResults });
  }, [bibleProgress, updateBibleProgress]);

  return {
    tutorialCompleted,
    setTutorialCompleted,
    advancedUnlocked,
    setAdvancedUnlocked,
    bibleProgress,
    updateBibleProgress,
    markChapterComplete,
    toggleBookmark,
    markExerciseComplete,
    isLoading,
  };
};

export default useStorage;
