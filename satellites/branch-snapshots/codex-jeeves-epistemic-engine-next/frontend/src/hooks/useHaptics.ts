/**
 * useHaptics — wraps expo-haptics with safety fallbacks (Cat-4.1)
 *
 * Calls always succeed (no-op on web / no permission). Honours system
 * reduce-motion: when on, haptics are also disabled (the W3C reduce-motion
 * spec mentions tactile feedback should follow the same preference).
 */
import React from 'react';
import { AccessibilityInfo, Platform } from 'react-native';

type Impact = 'light' | 'medium' | 'heavy' | 'soft' | 'rigid';
type Notify = 'success' | 'warning' | 'error';

export function useHaptics() {
  const [enabled, setEnabled] = React.useState(true);

  React.useEffect(() => {
    AccessibilityInfo.isReduceMotionEnabled()
      .then(rm => setEnabled(!rm))
      .catch(() => setEnabled(true));
    const sub = AccessibilityInfo.addEventListener('reduceMotionChanged', rm => setEnabled(!rm));
    return () => { try { (sub as any)?.remove?.(); } catch {} };
  }, []);

  const run = React.useCallback(async (fn: () => Promise<any>) => {
    if (!enabled) return;
    if (Platform.OS === 'web') return;
    try { await fn(); } catch {}
  }, [enabled]);

  return React.useMemo(() => ({
    impact: async (kind: Impact = 'light') => run(async () => {
      const h = await import('expo-haptics');
      const map: any = {
        light: h.ImpactFeedbackStyle.Light,
        medium: h.ImpactFeedbackStyle.Medium,
        heavy: h.ImpactFeedbackStyle.Heavy,
        soft: h.ImpactFeedbackStyle.Soft ?? h.ImpactFeedbackStyle.Light,
        rigid: h.ImpactFeedbackStyle.Rigid ?? h.ImpactFeedbackStyle.Medium,
      };
      return h.impactAsync(map[kind]);
    }),
    notify: async (kind: Notify = 'success') => run(async () => {
      const h = await import('expo-haptics');
      const map: any = {
        success: h.NotificationFeedbackType.Success,
        warning: h.NotificationFeedbackType.Warning,
        error: h.NotificationFeedbackType.Error,
      };
      return h.notificationAsync(map[kind]);
    }),
    selection: async () => run(async () => {
      const h = await import('expo-haptics');
      return h.selectionAsync();
    }),
    enabled,
  }), [enabled, run]);
}

export default useHaptics;
