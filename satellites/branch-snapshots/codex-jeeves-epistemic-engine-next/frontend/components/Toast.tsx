/**
 * Toast — imperative, app-wide notification surface.
 *
 *   • <ToastHost /> is mounted once at the top of _layout.tsx.
 *   • Call `toast.show('Saved!')` / `toast.success(...)` from anywhere
 *     (no React context required). Internally uses a tiny pub/sub bus.
 *   • Auto-dismisses after `durationMs` (default 2500).
 *   • Reanimated slide+fade animation. Multiple toasts queue gracefully.
 *
 * Variants:
 *   info     — neutral slate
 *   success  — emerald check
 *   warn     — amber pulse
 *   error    — crimson alert
 *
 * Designed to replace scattered Alert.alert() calls for non-blocking
 * feedback ("Saved", "Copied to clipboard", "Offline").
 */
import React, { useEffect, useState } from 'react';
import { View, Text, StyleSheet, Pressable, Platform } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import Animated, {
  useSharedValue, useAnimatedStyle, withTiming, withSpring,
} from 'react-native-reanimated';

export type ToastVariant = 'info' | 'success' | 'warn' | 'error';

interface ToastEntry {
  id:        string;
  message:   string;
  variant:   ToastVariant;
  durationMs:number;
  action?:   { label: string; onPress: () => void };
}

type Listener = (entries: ToastEntry[]) => void;

class ToastBus {
  private entries: ToastEntry[] = [];
  private listeners = new Set<Listener>();

  show(message: string, opts: Partial<Omit<ToastEntry, 'id' | 'message'>> = {}): string {
    const id = `t_${Date.now().toString(36)}_${Math.random().toString(36).slice(2,6)}`;
    const entry: ToastEntry = {
      id,
      message,
      variant:    opts.variant    ?? 'info',
      durationMs: opts.durationMs ?? 2500,
      action:     opts.action,
    };
    this.entries = [...this.entries.slice(-2), entry]; // max 3 visible
    this.emit();
    if (entry.durationMs > 0) {
      setTimeout(() => this.dismiss(id), entry.durationMs);
    }
    return id;
  }

  dismiss(id: string): void {
    const before = this.entries.length;
    this.entries = this.entries.filter(e => e.id !== id);
    if (this.entries.length !== before) this.emit();
  }

  subscribe(l: Listener): () => void {
    this.listeners.add(l);
    l(this.entries);
    return () => { this.listeners.delete(l); };
  }

  private emit() {
    for (const l of this.listeners) { try { l(this.entries.slice()); } catch { /* swallow */ } }
  }
}

const bus = new ToastBus();

export const toast = {
  show:    (msg: string, opts?: Partial<Omit<ToastEntry, 'id' | 'message'>>) => bus.show(msg, opts),
  info:    (msg: string, opts?: Partial<Omit<ToastEntry, 'id' | 'message' | 'variant'>>) =>
            bus.show(msg, { ...(opts || {}), variant: 'info' }),
  success: (msg: string, opts?: Partial<Omit<ToastEntry, 'id' | 'message' | 'variant'>>) =>
            bus.show(msg, { ...(opts || {}), variant: 'success' }),
  warn:    (msg: string, opts?: Partial<Omit<ToastEntry, 'id' | 'message' | 'variant'>>) =>
            bus.show(msg, { ...(opts || {}), variant: 'warn' }),
  error:   (msg: string, opts?: Partial<Omit<ToastEntry, 'id' | 'message' | 'variant'>>) =>
            bus.show(msg, { ...(opts || {}), variant: 'error' }),
  dismiss: (id: string) => bus.dismiss(id),
};

const VARIANT_STYLE: Record<ToastVariant, { bg: string; border: string; fg: string; icon: keyof typeof Ionicons.glyphMap }> = {
  info:    { bg: '#1e293b', border: '#334155', fg: '#e2e8f0', icon: 'information-circle' },
  success: { bg: '#064e3b', border: '#10b981', fg: '#a7f3d0', icon: 'checkmark-circle' },
  warn:    { bg: '#451a03', border: '#f59e0b', fg: '#fde68a', icon: 'warning' },
  error:   { bg: '#450a0a', border: '#ef4444', fg: '#fecaca', icon: 'close-circle' },
};

function ToastRow({ entry }: { entry: ToastEntry }) {
  const v = VARIANT_STYLE[entry.variant];
  const ty = useSharedValue(40);
  const op = useSharedValue(0);

  useEffect(() => {
    ty.value = withSpring(0,  { damping: 16, stiffness: 180 });
    op.value = withTiming(1,  { duration: 160 });
    return () => {
      op.value = withTiming(0, { duration: 140 });
    };
  }, [entry.id]);  // eslint-disable-line react-hooks/exhaustive-deps

  const animStyle = useAnimatedStyle(() => ({
    transform: [{ translateY: ty.value }],
    opacity:   op.value,
  }));

  return (
    <Animated.View style={[styles.row, { backgroundColor: v.bg, borderColor: v.border }, animStyle]}>
      <Ionicons name={v.icon} size={18} color={v.border} />
      <Text style={[styles.msg, { color: v.fg }]} numberOfLines={2}>{entry.message}</Text>
      {entry.action ? (
        <Pressable
          onPress={() => { try { entry.action!.onPress(); } catch { /* swallow */ } toast.dismiss(entry.id); }}
          hitSlop={8}
        >
          <Text style={[styles.actionText, { color: v.border }]}>{entry.action.label}</Text>
        </Pressable>
      ) : (
        <Pressable onPress={() => toast.dismiss(entry.id)} hitSlop={8}>
          <Ionicons name="close" size={16} color={v.fg} />
        </Pressable>
      )}
    </Animated.View>
  );
}

export function ToastHost() {
  const [entries, setEntries] = useState<ToastEntry[]>([]);

  useEffect(() => {
    return bus.subscribe(setEntries);
  }, []);

  if (entries.length === 0) return null;

  return (
    <View style={[styles.host, { pointerEvents: 'box-none' }]}>
      {entries.map(e => <ToastRow key={e.id} entry={e} />)}
    </View>
  );
}

const styles = StyleSheet.create({
  host: {
    position: 'absolute',
    left: 12, right: 12, bottom: 24,
    gap: 8,
    zIndex: 1000,
    elevation: 16,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    paddingHorizontal: 14,
    paddingVertical: 11,
    borderRadius: 12,
    borderWidth: 1,
    ...(Platform.OS === 'web' ? {
      // @ts-ignore — web-only style key
      boxShadow: '0 4px 8px rgba(0,0,0,0.35)',
    } : {
      shadowColor: '#000',
      shadowOffset: { width: 0, height: 4 },
      shadowOpacity: 0.35,
      shadowRadius: 8,
      elevation: 6,
    }),
  },
  msg: {
    flex: 1,
    fontSize: 13,
    fontWeight: '600',
  },
  actionText: {
    fontSize: 12,
    fontWeight: '800',
    letterSpacing: 0.5,
    textTransform: 'uppercase',
    paddingHorizontal: 4,
  },
});

export default toast;
