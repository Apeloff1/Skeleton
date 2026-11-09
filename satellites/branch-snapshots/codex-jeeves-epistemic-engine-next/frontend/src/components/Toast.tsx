/**
 * src/components/Toast.tsx — Toast / non-modal notification system (Cat-4)
 *
 * Replaces ad-hoc Alert.alert / inline error banners with a single
 * controllable toast container. Honours system "reduce motion" preference.
 */
import { NATIVE_DRIVER } from '../utils/platformStyles';
import React from 'react';
import {
  View, Text, StyleSheet, Animated, Easing, Platform,
  AccessibilityInfo, TouchableOpacity, useWindowDimensions,
} from 'react-native';

type ToastKind = 'info' | 'success' | 'warning' | 'error';
type ToastEntry = { id: number; kind: ToastKind; msg: string; ttl: number };

interface ToastApi {
  show: (msg: string, kind?: ToastKind, ttl?: number) => void;
  hide: (id: number) => void;
}

const ToastCtx = React.createContext<ToastApi | null>(null);

let _id = 0;

export function useToast() {
  const ctx = React.useContext(ToastCtx);
  if (!ctx) {
    // Soft fallback so screens don't crash if provider missing.
    return {
      show: (msg: string) => console.log('[toast]', msg),
      hide: () => {},
    };
  }
  return ctx;
}

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = React.useState<ToastEntry[]>([]);
  const [reduceMotion, setReduceMotion] = React.useState(false);
  const { width } = useWindowDimensions();

  React.useEffect(() => {
    AccessibilityInfo.isReduceMotionEnabled().then(setReduceMotion).catch(() => {});
    const sub = AccessibilityInfo.addEventListener('reduceMotionChanged', setReduceMotion);
    return () => { try { (sub as any)?.remove?.(); } catch {} };
  }, []);

  const api = React.useMemo<ToastApi>(() => ({
    show: (msg, kind = 'info', ttl = 3200) => {
      const id = ++_id;
      setToasts(prev => [...prev, { id, kind, msg, ttl }]);
      setTimeout(() => setToasts(prev => prev.filter(t => t.id !== id)), ttl);
    },
    hide: (id) => setToasts(prev => prev.filter(t => t.id !== id)),
  }), []);

  return (
    <ToastCtx.Provider value={api}>
      {children}
      <View style={[styles.container, { pointerEvents: 'box-none' }]}>
        {toasts.map((t) => (
          <ToastView key={t.id} entry={t} reduceMotion={reduceMotion} width={width} onPress={() => api.hide(t.id)} />
        ))}
      </View>
    </ToastCtx.Provider>
  );
}

function ToastView({
  entry, reduceMotion, width, onPress,
}: { entry: ToastEntry; reduceMotion: boolean; width: number; onPress: () => void }) {
  const opacity = React.useRef(new Animated.Value(reduceMotion ? 1 : 0)).current;
  const translateY = React.useRef(new Animated.Value(reduceMotion ? 0 : -24)).current;

  React.useEffect(() => {
    if (reduceMotion) return;
    Animated.parallel([
      Animated.timing(opacity, { toValue: 1, duration: 220, easing: Easing.out(Easing.cubic), useNativeDriver: NATIVE_DRIVER }),
      Animated.timing(translateY, { toValue: 0, duration: 220, easing: Easing.out(Easing.cubic), useNativeDriver: NATIVE_DRIVER }),
    ]).start();
  }, [opacity, translateY, reduceMotion]);

  const bg =
    entry.kind === 'error' ? '#7f1d1d' :
    entry.kind === 'warning' ? '#854d0e' :
    entry.kind === 'success' ? '#14532d' :
    '#1e293b';

  return (
    <Animated.View style={[styles.toast, { backgroundColor: bg, maxWidth: Math.min(width - 32, 480), transform: [{ translateY }], opacity }]}>
      <TouchableOpacity onPress={onPress} accessibilityRole="button" accessibilityLabel={`Dismiss notification: ${entry.msg}`}>
        <Text style={styles.text}>{entry.msg}</Text>
      </TouchableOpacity>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  container: {
    position: 'absolute', top: Platform.OS === 'ios' ? 60 : 30, left: 0, right: 0,
    alignItems: 'center', zIndex: 9999,
  },
  toast: {
    paddingVertical: 12, paddingHorizontal: 18, borderRadius: 14, marginBottom: 8,
    ...(Platform.OS === 'ios'
      ? { shadowColor: '#000', shadowOpacity: 0.2, shadowRadius: 8, shadowOffset: { width: 0, height: 4 } }
      : { elevation: 4 }),
  },
  text: { color: '#fff', fontSize: 14, fontWeight: '600', textAlign: 'center' },
});
