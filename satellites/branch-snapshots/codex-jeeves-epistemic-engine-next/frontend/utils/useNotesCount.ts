/**
 * useNotesCount — live count of saved sticky notes (`@autosave/notes:v2`).
 *
 *   • Reads from AsyncStorage on mount, then refreshes on:
 *       - Window/App focus (web `focus` event)
 *       - Periodic poll (every 6s) so a note made in another tab/route
 *         updates the badge without explicit pub/sub plumbing.
 *   • Returns 0 immediately if storage is empty or unparseable.
 *
 *   Used by the /menu Tools section header to show a small live badge
 *   next to the Sticky-Notes feature card.
 */
import { useEffect, useState } from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { Platform } from 'react-native';

const KEY     = '@autosave/notes:v2';
const POLL_MS = 6000;

export function useNotesCount(): number {
  const [count, setCount] = useState<number>(0);

  useEffect(() => {
    let mounted = true;

    const read = async () => {
      try {
        const raw = await AsyncStorage.getItem(KEY);
        if (!mounted) return;
        if (!raw) { setCount(0); return; }
        const parsed = JSON.parse(raw);
        setCount(Array.isArray(parsed) ? parsed.length : 0);
      } catch {
        if (mounted) setCount(0);
      }
    };

    read();
    const interval = setInterval(read, POLL_MS);

    // On web, refresh whenever the tab regains focus.
    let onFocus: (() => void) | null = null;
    if (Platform.OS === 'web' && typeof window !== 'undefined') {
      onFocus = () => { read(); };
      window.addEventListener('focus', onFocus);
    }

    return () => {
      mounted = false;
      clearInterval(interval);
      if (onFocus && typeof window !== 'undefined') {
        window.removeEventListener('focus', onFocus);
      }
    };
  }, []);

  return count;
}

export default useNotesCount;
