/**
 * Storage adapter for learning progress.
 *
 * An in-memory authoritative snapshot plus a serialized write queue prevents
 * concurrent chapter/bookmark updates from reverting newer local changes.
 * Loading is guarded against unmount and against edits made while loading.
 */
import { useState, useEffect, useCallback, useRef } from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { STORAGE_KEYS } from '../constants/config';
import type { BibleProgress } from '../types';

const DEFAULT_BIBLE_PROGRESS: BibleProgress = {
  completedChapters: {},
  bookmarks: [],
  exerciseResults: {},
  totalTimeSpent: 0,
  streak: 0,
};

function parseBibleProgress(raw: string): BibleProgress {
  const value: unknown = JSON.parse(raw);
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error('Invalid saved learning progress');
  }
  const saved = value as Partial<BibleProgress>;
  return {
    completedChapters: saved.completedChapters &&
      typeof saved.completedChapters === 'object' && !Array.isArray(saved.completedChapters)
      ? saved.completedChapters : {},
    bookmarks: Array.isArray(saved.bookmarks)
      ? saved.bookmarks.filter((item): item is string => typeof item === 'string') : [],
    exerciseResults: saved.exerciseResults &&
      typeof saved.exerciseResults === 'object' && !Array.isArray(saved.exerciseResults)
      ? saved.exerciseResults : {},
    totalTimeSpent: typeof saved.totalTimeSpent === 'number' &&
      Number.isFinite(saved.totalTimeSpent) && saved.totalTimeSpent >= 0 ? saved.totalTimeSpent : 0,
    streak: typeof saved.streak === 'number' &&
      Number.isFinite(saved.streak) && saved.streak >= 0 ? saved.streak : 0,
  };
}

export const useStorage = () => {
  const [tutorialCompleted, setTutorialCompletedState] = useState(false);
  const [advancedUnlocked, setAdvancedUnlockedState] = useState(false);
  const [bibleProgress, setBibleProgressState] = useState<BibleProgress>(DEFAULT_BIBLE_PROGRESS);
  const [isLoading, setIsLoading] = useState(true);
  const mountedRef = useRef(true);
  const mutationEpochRef = useRef(0);
  const progressRef = useRef<BibleProgress>(DEFAULT_BIBLE_PROGRESS);
  const writeQueueRef = useRef<Promise<void>>(Promise.resolve());
  const hydrationRef = useRef<Promise<void>>(Promise.resolve());

  // A rejected storage write must not poison the next queued write.
  const enqueueWrite = useCallback((key: string, value: string) => {
    const next = writeQueueRef.current.then(() => AsyncStorage.setItem(key, value));
    writeQueueRef.current = next.catch(error => {
      console.error('Failed to persist storage change:', error);
    });
    return next;
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    let cancelled = false;
    const initialEpoch = mutationEpochRef.current;

    const loadAllData = async () => {
      try {
        const [tutorial, advanced, bible] = await Promise.all([
          AsyncStorage.getItem(STORAGE_KEYS.TUTORIAL_COMPLETED),
          AsyncStorage.getItem(STORAGE_KEYS.ADVANCED_UNLOCKED),
          AsyncStorage.getItem(STORAGE_KEYS.BIBLE_PROGRESS),
        ]);
        if (cancelled || !mountedRef.current || mutationEpochRef.current !== initialEpoch) return;

        setTutorialCompletedState(tutorial === 'true');
        setAdvancedUnlockedState(advanced === 'true');
        if (bible) {
          const progress = parseBibleProgress(bible);
          progressRef.current = progress;
          setBibleProgressState(progress);
        }
      } catch (error) {
        console.error('Failed to load storage:', error);
      } finally {
        if (!cancelled && mountedRef.current) setIsLoading(false);
      }
    };
    hydrationRef.current = loadAllData();

    return () => {
      cancelled = true;
      mountedRef.current = false;
    };
  }, []);

  const setTutorialCompleted = useCallback(async (value: boolean) => {
    await hydrationRef.current;
    if (!mountedRef.current) return;
    mutationEpochRef.current++;
    if (mountedRef.current) setTutorialCompletedState(value);
    try {
      await enqueueWrite(STORAGE_KEYS.TUTORIAL_COMPLETED, String(value));
    } catch {
      // The queue logs the failure; future writes are still allowed.
    }
  }, [enqueueWrite]);

  const setAdvancedUnlocked = useCallback(async (value: boolean) => {
    await hydrationRef.current;
    if (!mountedRef.current) return;
    mutationEpochRef.current++;
    if (mountedRef.current) setAdvancedUnlockedState(value);
    try {
      await enqueueWrite(STORAGE_KEYS.ADVANCED_UNLOCKED, String(value));
    } catch {
      // The queue logs the failure; future writes are still allowed.
    }
  }, [enqueueWrite]);

  const updateBibleProgress = useCallback(async (updates: Partial<BibleProgress>) => {
    await hydrationRef.current;
    if (!mountedRef.current) return;
    mutationEpochRef.current++;
    const next = { ...progressRef.current, ...updates };
    progressRef.current = next;
    if (mountedRef.current) setBibleProgressState(next);
    try {
      await enqueueWrite(STORAGE_KEYS.BIBLE_PROGRESS, JSON.stringify(next));
    } catch {
      // Keep the latest local snapshot; a later write can repair persistence.
    }
  }, [enqueueWrite]);

  const markChapterComplete = useCallback(async (chapterId: string) => {
    await updateBibleProgress({
      completedChapters: { ...progressRef.current.completedChapters, [chapterId]: true },
    });
  }, [updateBibleProgress]);

  const toggleBookmark = useCallback(async (chapterId: string) => {
    const bookmarks = progressRef.current.bookmarks;
    await updateBibleProgress({
      bookmarks: bookmarks.includes(chapterId)
        ? bookmarks.filter(id => id !== chapterId)
        : [...bookmarks, chapterId],
    });
  }, [updateBibleProgress]);

  const markExerciseComplete = useCallback(async (exerciseId: string, passed: boolean) => {
    await updateBibleProgress({
      exerciseResults: { ...progressRef.current.exerciseResults, [exerciseId]: passed },
    });
  }, [updateBibleProgress]);

  return {
    tutorialCompleted, setTutorialCompleted,
    advancedUnlocked, setAdvancedUnlocked,
    bibleProgress, updateBibleProgress,
    markChapterComplete, toggleBookmark, markExerciseComplete,
    isLoading,
  };
};

export default useStorage;
