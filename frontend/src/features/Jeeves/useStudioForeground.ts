import { useEffect, useState } from 'react';
import { AppState, Platform } from 'react-native';
import { useIsFocused } from '@react-navigation/native';

function foreground(): boolean {
  return AppState.currentState !== 'background' && AppState.currentState !== 'inactive'
    && (Platform.OS !== 'web' || typeof document === 'undefined' || document.visibilityState !== 'hidden');
}

/** Expensive work is only continued while the operator can see this workspace. */
export function useStudioForeground(): boolean {
  const focused = useIsFocused();
  const [active, setActive] = useState(foreground);
  useEffect(() => {
    const update = () => setActive(foreground());
    const subscription = AppState.addEventListener('change', update);
    if (Platform.OS === 'web' && typeof document !== 'undefined') document.addEventListener('visibilitychange', update);
    update();
    return () => {
      subscription.remove();
      if (Platform.OS === 'web' && typeof document !== 'undefined') document.removeEventListener('visibilitychange', update);
    };
  }, []);
  return active && focused;
}
