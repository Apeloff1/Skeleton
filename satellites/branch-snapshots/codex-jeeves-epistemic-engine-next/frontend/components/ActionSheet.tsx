/**
 * ActionSheet & PromptSheet — imperative, cross-platform modal surfaces.
 *
 *   Used as a drop-in replacement for:
 *     • `Alert.alert('Reset?', ..., [{cancel}, {destructive}, ...])`
 *     • `Alert.prompt(...)`  (which is iOS-only — broken on Android/web)
 *
 *   Why an imperative bus?
 *     • Same ergonomics as `toast.show(...)` — call from anywhere.
 *     • No React context plumbing required.
 *     • A single `ActionSheetHost` is mounted in _layout so the sheet is
 *       drawn ABOVE every route + the OfflineBanner + Toasts.
 *
 *   Usage:
 *       import { actionSheet, promptSheet } from '@/components/ActionSheet';
 *
 *       actionSheet.show({
 *         title: 'Reset profile?',
 *         message: 'This wipes XP, streaks, and progress. Can\'t be undone.',
 *         options: [
 *           { label: 'Cancel', kind: 'cancel' },
 *           { label: 'Reset everything', kind: 'destructive', onPress: doReset },
 *         ],
 *       });
 *
 *       promptSheet.show({
 *         title: 'Paste JSON',
 *         placeholder: 'Paste a previously-exported user snapshot',
 *         multiline: true,
 *         onSubmit: (txt) => handleImport(txt),
 *       });
 */
import React, { useEffect, useState } from 'react';
import {
  View, Text, StyleSheet, Pressable, TextInput,
  KeyboardAvoidingView, Platform,
} from 'react-native';
import Animated, {
  useSharedValue, useAnimatedStyle, withTiming, withSpring,
} from 'react-native-reanimated';

// ────────────────────────────────────────────────────────────────────
// SHARED TYPES
// ────────────────────────────────────────────────────────────────────
export type ActionKind = 'default' | 'primary' | 'cancel' | 'destructive';

export interface ActionOption {
  label:    string;
  kind?:    ActionKind;
  /** Fires after the sheet animates closed. */
  onPress?: () => void | Promise<void>;
}

export interface ActionSheetSpec {
  title?:   string;
  message?: string;
  options:  ActionOption[];
  /** Tap outside / Esc dismisses → fires this kind=cancel option if present. */
  dismissible?: boolean;
}

export interface PromptSheetSpec {
  title:        string;
  message?:     string;
  placeholder?: string;
  initialValue?:string;
  multiline?:   boolean;
  submitLabel?: string;
  cancelLabel?: string;
  onSubmit:     (text: string) => void | Promise<void>;
  onCancel?:    () => void;
}

// ────────────────────────────────────────────────────────────────────
// TINY PUB/SUB BUS
// ────────────────────────────────────────────────────────────────────
type SheetEntry =
  | { kind: 'action'; id: string; spec: ActionSheetSpec }
  | { kind: 'prompt'; id: string; spec: PromptSheetSpec };

type Listener = (entry: SheetEntry | null) => void;

class SheetBus {
  private current: SheetEntry | null = null;
  private listeners = new Set<Listener>();

  show(spec: ActionSheetSpec): string {
    const id = `as_${Date.now().toString(36)}_${Math.random().toString(36).slice(2,6)}`;
    this.current = { kind: 'action', id, spec };
    this.emit();
    return id;
  }
  prompt(spec: PromptSheetSpec): string {
    const id = `ps_${Date.now().toString(36)}_${Math.random().toString(36).slice(2,6)}`;
    this.current = { kind: 'prompt', id, spec };
    this.emit();
    return id;
  }
  dismiss() {
    if (!this.current) return;
    this.current = null;
    this.emit();
  }
  subscribe(l: Listener) {
    this.listeners.add(l);
    l(this.current);
    return () => { this.listeners.delete(l); };
  }
  private emit() {
    for (const l of this.listeners) { try { l(this.current); } catch { /* swallow */ } }
  }
}

const bus = new SheetBus();

export const actionSheet = {
  show:    (spec: ActionSheetSpec) => bus.show(spec),
  dismiss: () => bus.dismiss(),
};

export const promptSheet = {
  show:    (spec: PromptSheetSpec) => bus.prompt(spec),
  dismiss: () => bus.dismiss(),
};

// ────────────────────────────────────────────────────────────────────
// RENDER HOST
// ────────────────────────────────────────────────────────────────────
const KIND_STYLE: Record<ActionKind, { fg: string; bg: string; weight: '700'|'800' }> = {
  default:     { fg: '#e2e8f0', bg: '#1e293b', weight: '700' },
  primary:     { fg: '#0a0f1f', bg: '#a78bfa', weight: '800' },
  cancel:      { fg: '#94a3b8', bg: 'transparent', weight: '700' },
  destructive: { fg: '#fecaca', bg: '#7f1d1d', weight: '800' },
};

export function ActionSheetHost() {
  const [entry, setEntry] = useState<SheetEntry | null>(null);
  const [draft, setDraft] = useState('');

  // Animation values
  const backdrop = useSharedValue(0);
  const sheetY   = useSharedValue(120);

  useEffect(() => bus.subscribe((e) => {
    setEntry(e);
    if (e?.kind === 'prompt') setDraft(e.spec.initialValue ?? '');
  }), []);

  useEffect(() => {
    if (entry) {
      backdrop.value = withTiming(1, { duration: 180 });
      sheetY.value   = withSpring(0, { damping: 18, stiffness: 200 });
    } else {
      backdrop.value = withTiming(0, { duration: 160 });
      sheetY.value   = withTiming(120, { duration: 160 });
    }
  }, [entry, backdrop, sheetY]);

  // ESC dismiss on web for accessibility parity
  useEffect(() => {
    if (Platform.OS !== 'web' || !entry) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') handleDismiss(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [entry]);  // eslint-disable-line react-hooks/exhaustive-deps

  const backdropStyle = useAnimatedStyle(() => ({ opacity: backdrop.value }));
  const sheetStyle    = useAnimatedStyle(() => ({ transform: [{ translateY: sheetY.value }] }));

  if (!entry) return null;

  const handleDismiss = () => {
    if (entry.kind === 'action') {
      const dismissible = entry.spec.dismissible !== false;
      if (!dismissible) return;
      // Fire cancel option if present (lets caller distinguish).
      const cancel = entry.spec.options.find(o => o.kind === 'cancel');
      bus.dismiss();
      setTimeout(() => { try { cancel?.onPress?.(); } catch { /* swallow */ } }, 200);
    } else {
      const cb = entry.spec.onCancel;
      bus.dismiss();
      setTimeout(() => { try { cb?.(); } catch { /* swallow */ } }, 200);
    }
  };

  const handlePressOption = (opt: ActionOption) => {
    bus.dismiss();
    setTimeout(() => { try { opt.onPress?.(); } catch { /* swallow */ } }, 200);
  };

  const handleSubmitPrompt = () => {
    if (entry.kind !== 'prompt') return;
    const text = draft;
    const cb = entry.spec.onSubmit;
    bus.dismiss();
    setTimeout(() => { try { cb(text); } catch { /* swallow */ } }, 200);
  };

  return (
    <Animated.View style={[styles.host, backdropStyle, { pointerEvents: 'box-none' as any }]}>
      <Pressable style={styles.backdrop} onPress={handleDismiss} />
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        style={[styles.kav, { pointerEvents: 'box-none' as any }]}
      >
        <Animated.View style={[styles.sheet, sheetStyle]}>
          {/* Drag-handle */}
          <View style={styles.handle} />

          {entry.kind === 'action' ? (
            <>
              {entry.spec.title ? (
                <Text style={styles.title}>{entry.spec.title}</Text>
              ) : null}
              {entry.spec.message ? (
                <Text style={styles.message}>{entry.spec.message}</Text>
              ) : null}
              <View style={{ height: 12 }} />
              {entry.spec.options.map((opt, i) => {
                const k = KIND_STYLE[opt.kind ?? 'default'];
                return (
                  <Pressable
                    key={`${opt.label}-${i}`}
                    onPress={() => handlePressOption(opt)}
                    style={({ pressed }) => [
                      styles.optBtn,
                      { backgroundColor: k.bg, opacity: pressed ? 0.85 : 1 },
                      opt.kind === 'cancel' && styles.optCancel,
                    ]}
                    testID={`actionsheet-opt-${opt.kind || 'default'}-${i}`}
                  >
                    <Text style={[styles.optText, { color: k.fg, fontWeight: k.weight }]}>
                      {opt.label}
                    </Text>
                  </Pressable>
                );
              })}
            </>
          ) : (
            <>
              <Text style={styles.title}>{entry.spec.title}</Text>
              {entry.spec.message ? (
                <Text style={styles.message}>{entry.spec.message}</Text>
              ) : null}
              <TextInput
                value={draft}
                onChangeText={setDraft}
                placeholder={entry.spec.placeholder}
                placeholderTextColor="#64748b"
                multiline={entry.spec.multiline}
                style={[styles.input, entry.spec.multiline && styles.inputMulti]}
                autoFocus
                testID="promptsheet-input"
              />
              <View style={styles.promptBtnRow}>
                <Pressable
                  onPress={handleDismiss}
                  style={({ pressed }) => [styles.optBtn, styles.optCancel, { flex: 1, opacity: pressed ? 0.85 : 1 }]}
                  testID="promptsheet-cancel"
                >
                  <Text style={[styles.optText, { color: '#94a3b8', fontWeight: '700' }]}>
                    {entry.spec.cancelLabel || 'Cancel'}
                  </Text>
                </Pressable>
                <Pressable
                  onPress={handleSubmitPrompt}
                  style={({ pressed }) => [styles.optBtn, { backgroundColor: '#a78bfa', flex: 1, opacity: pressed ? 0.85 : 1 }]}
                  testID="promptsheet-submit"
                >
                  <Text style={[styles.optText, { color: '#0a0f1f', fontWeight: '800' }]}>
                    {entry.spec.submitLabel || 'Submit'}
                  </Text>
                </Pressable>
              </View>
            </>
          )}
        </Animated.View>
      </KeyboardAvoidingView>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  host: {
    position: 'absolute',
    top: 0, left: 0, right: 0, bottom: 0,
    zIndex: 2000,
    elevation: 32,
  },
  backdrop: {
    position: 'absolute',
    top: 0, left: 0, right: 0, bottom: 0,
    backgroundColor: 'rgba(0,0,0,0.55)',
  },
  kav: {
    position: 'absolute',
    left: 0, right: 0, bottom: 0,
  },
  sheet: {
    backgroundColor: '#0f172a',
    borderTopLeftRadius: 18,
    borderTopRightRadius: 18,
    paddingHorizontal: 18,
    paddingTop: 8,
    paddingBottom: 26,
    borderTopWidth: 1, borderColor: '#1e293b',
  },
  handle: {
    width: 38, height: 4, borderRadius: 2,
    backgroundColor: '#334155',
    alignSelf: 'center', marginBottom: 12,
  },
  title:   { color: '#f8fafc', fontSize: 17, fontWeight: '700', textAlign: 'center' },
  message: { color: '#94a3b8', fontSize: 13, lineHeight: 18, textAlign: 'center', marginTop: 6 },

  optBtn:    { paddingVertical: 13, paddingHorizontal: 16, borderRadius: 12, alignItems: 'center', marginTop: 8 },
  optCancel: { backgroundColor: 'transparent', borderWidth: 1, borderColor: '#1e293b' },
  optText:   { fontSize: 14, letterSpacing: 0.2 },

  input: {
    marginTop: 14,
    backgroundColor: '#020617',
    borderWidth: 1, borderColor: '#1e293b',
    borderRadius: 10,
    paddingHorizontal: 12, paddingVertical: 10,
    color: '#e2e8f0',
    fontSize: 13,
  },
  inputMulti: { minHeight: 110, maxHeight: 240, textAlignVertical: 'top' },
  promptBtnRow: { flexDirection: 'row', gap: 8, marginTop: 4 },
});

export default { actionSheet, promptSheet, ActionSheetHost };
