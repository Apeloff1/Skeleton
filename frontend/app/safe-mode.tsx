/**
 * /safe-mode — Recovery screen shown after repeated unclean boots.
 *
 * Displays:
 *   • Last successful boot timestamp
 *   • The recorded boot trace (steps the app reached before crashing)
 *   • Crash count
 *   • Explicit retry, non-destructive startup reset, and confirmed data wipe
 *
 * This is the ultimate safety net: even if /hub crashes on every launch,
 * the user always has a way to recover without uninstall/reinstall.
 */
import { useEffect, useState } from 'react';
import { View, Text, ScrollView, TouchableOpacity, StyleSheet, SafeAreaView, Platform, Alert } from 'react-native';
import { useRouter } from 'expo-router';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { clearMirror, safeRemoveItem, pauseSafeStorageForWipe, resumeSafeStorageAfterWipe } from '../src/utils/safeStorage';
import {
  getLastTrace, getCrashCount, getLastCleanBoot,
  resetBootState, TraceStep,
} from '../src/utils/bootTracer';
import {
  FEATURE_FLAGS, getFeatureFlag, loadFeatureFlags,
  resetAllFlags, getModifiedFlagKeys,
} from '../src/utils/featureFlags';

export default function SafeModeRoute() {
  const router = useRouter();
  const [trace, setTrace] = useState<TraceStep[]>([]);
  const [crashCount, setCrashCount] = useState(0);
  const [lastClean, setLastClean] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [recoveryError, setRecoveryError] = useState<string | null>(null);
  /** Re-render trigger for flag changes so the diagnostic panel stays fresh. */
  const [, setFlagsBump] = useState(0);

  useEffect(() => {
    let mounted = true;
    // Diagnostic reads are independent and bounded by bootTracer. A stalled
    // flag hydration must not hide the recovery screen or surface an
    // unhandled rejection during an already degraded startup.
    void Promise.all([getLastTrace(), getCrashCount(), getLastCleanBoot()])
      .then(([history, count, clean]) => {
        if (!mounted) return;
        setTrace(history);
        setCrashCount(count);
        setLastClean(clean);
      }).catch(() => {});
    void Promise.resolve().then(() => loadFeatureFlags())
      .then(() => { if (mounted) setFlagsBump(n => n + 1); })
      .catch(() => {});
    return () => { mounted = false; };
  }, []);

  const onResetFlags = async () => {
    await resetAllFlags();
    setFlagsBump(n => n + 1);
  };

  const tryProduct = () => {
    // A manual retry is not proof of success. Product marks the boot clean
    // after a committed render; a repeated crash retains the earlier count.
    router.replace('/product');
  };

  const resetWelcome = async () => {
    if (busy) return;
    setBusy(true);
    setRecoveryError(null);
    try {
      const acknowledged = await safeRemoveItem('@codedock:welcome_seen:v1', 1_000);
      if (!acknowledged) throw new Error('welcome key deletion unconfirmed');
      clearMirror();
      router.replace('/welcome');
    } catch {
      setRecoveryError('Welcome reset was not confirmed. Local storage may be unavailable; other settings and projects were not intentionally removed.');
    } finally {
      setBusy(false);
    }
  };

  const resetStartup = async () => {
    if (busy) return;
    setBusy(true);
    setRecoveryError(null);
    try {
      const removed = await resetBootState();
      if (!removed) throw new Error('storage not confirmed');
      setCrashCount(0);
      setTrace([]);
      setLastClean(null);
      setRecoveryError('Startup evidence reset. Your projects and settings were preserved.');
    } catch {
      setRecoveryError('Startup reset was not confirmed; no success has been assumed.');
    } finally {
      setBusy(false);
    }
  };

  const performWipe = async () => {
    if (busy) return;
    setBusy(true);
    setRecoveryError(null);
    let releaseFence = true;
    try {
      // Prevent any wrapper-owned project/settings writes from interleaving
      // with deletion. A timed-out write still owns its key until native I/O
      // finishes, so a wipe is refused when a safe drain is unavailable.
      if (!(await pauseSafeStorageForWipe())) {
        throw new Error('native mutations still pending');
      }
      if (!(await resetBootState())) throw new Error('boot trace still pending');

      const clearOperation = AsyncStorage.clear();
      const cleared = await new Promise<{ done: boolean; ok: boolean }>(resolve => {
        let settled = false;
        const finish = (done: boolean, ok: boolean) => {
          if (settled) return;
          settled = true;
          clearTimeout(timer);
          resolve({ done, ok });
        };
        const timer = setTimeout(() => finish(false, false), 2_000);
        void clearOperation.then(
          () => finish(true, true),
          () => finish(true, false),
        );
      });
      if (!cleared.done) {
        // The native clear operation cannot be cancelled by a JS deadline.
        // Keep the mutation fence held until the true native completion, or
        // a delayed clear could destroy newly saved state after a false reset.
        releaseFence = false;
        void clearOperation.then(
          () => { clearMirror(); },
          () => undefined,
        ).finally(() => resumeSafeStorageAfterWipe());
        throw new Error('native clear outcome unknown');
      }
      if (!cleared.ok) throw new Error('native clear rejected');
      clearMirror();
      router.replace('/welcome');
    } catch {
      setRecoveryError('Data wipe could not be confirmed. Remain in Safe Mode and check device storage.');
    } finally {
      if (releaseFence) resumeSafeStorageAfterWipe();
      setBusy(false);
    }
  };

  const confirmWipe = () => {
    if (busy) return;
    const warning = 'Permanently delete ALL locally stored projects, work, settings and recovery logs on this device? This cannot be undone.';
    if (Platform.OS === 'web') {
      if (typeof window !== 'undefined' && window.confirm(warning)) void performWipe();
      return;
    }
    Alert.alert('Delete all local app data?', warning, [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Delete all', style: 'destructive', onPress: () => { void performWipe(); } },
    ]);
  };

  const lastCleanStr = lastClean
    ? new Date(lastClean).toLocaleString()
    : 'never';

  return (
    <SafeAreaView style={styles.safe}>
      <View style={styles.header}>
        <Text style={styles.badge}>Safe Mode</Text>
        <Text style={styles.title}>CodeDock detected repeated crashes</Text>
        <Text style={styles.sub}>
          The app has crashed {crashCount} time{crashCount === 1 ? '' : 's'} in a row before reaching the product shell.
          You can try again, reset just the welcome state, or wipe everything.
        </Text>
      </View>

      <ScrollView style={styles.scroll} contentContainerStyle={{ padding: 16 }}>
        <Text style={styles.sectionLabel}>Last clean boot</Text>
        <Text style={styles.mono}>{lastCleanStr}</Text>

        <Text style={styles.sectionLabel}>Boot trace (last {trace.length} steps)</Text>
        {trace.length === 0 ? (
          <Text style={styles.dim}>No trace recorded yet.</Text>
        ) : (
          trace.slice().reverse().map((t, i) => (
            <View key={i} style={styles.row}>
              <Text style={styles.mono} numberOfLines={2}>{t.step}</Text>
              <Text style={styles.dim}>{new Date(t.ts).toLocaleTimeString()}</Text>
            </View>
          ))
        )}

        {recoveryError ? <Text accessibilityRole="alert" style={styles.recoveryMessage}>{recoveryError}</Text> : null}
        <TouchableOpacity
          onPress={resetStartup}
          disabled={busy}
          style={styles.inlineBtn}
          accessibilityLabel="Reset only startup and crash recovery state"
        >
          <Text style={styles.inlineBtnText}>Reset startup only (keep projects)</Text>
        </TouchableOpacity>
        <Text style={styles.sectionLabel}>Tip</Text>
        <Text style={styles.dim}>
          The trace above shows what step the app reached before crashing.
          Share this list with the developer to help diagnose the failure. Resetting startup evidence does not remove saved projects.
        </Text>

        {/* P4 — Feature-flag diagnostic snapshot. Read-only listing so the
            user can prove which flags differ from defaults before deciding
            to wipe / reset. Reset button surfaces inline. */}
        <Text style={styles.sectionLabel}>
          Feature flags ({getModifiedFlagKeys().length} modified)
        </Text>
        {FEATURE_FLAGS.filter(f => f.visible !== false).map(f => {
          const v = getFeatureFlag(f.key);
          const modified = v !== f.default;
          return (
            <View key={f.key} style={styles.row}>
              <Text style={[styles.mono, { flex: 1 }]} numberOfLines={1}>
                {modified ? '✦ ' : ''}{f.key}
              </Text>
              <Text style={[styles.dim, { color: v ? '#10B981' : '#94a3b8' }]}>
                {v ? 'on' : 'off'}
              </Text>
            </View>
          );
        })}
        {getModifiedFlagKeys().length > 0 && (
          <TouchableOpacity
            onPress={onResetFlags}
            style={styles.inlineBtn}
            accessibilityLabel="Reset feature flags to defaults"
          >
            <Text style={styles.inlineBtnText}>Reset feature flags</Text>
          </TouchableOpacity>
        )}
        <TouchableOpacity
          onPress={() => router.push('/boot-log')}
          style={styles.inlineBtn}
          accessibilityLabel="View full boot log"
          testID="sm-view-boot-log"
        >
          <Text style={styles.inlineBtnText}>📋 View full boot log</Text>
        </TouchableOpacity>
      </ScrollView>

      <View style={styles.footer}>
        <TouchableOpacity style={[styles.btn, styles.btnAlt]} onPress={resetWelcome} disabled={busy}>
          <Text style={styles.btnAltText}>Reset welcome</Text>
        </TouchableOpacity>
        <TouchableOpacity style={[styles.btn, styles.btnDanger]} onPress={confirmWipe} disabled={busy}>
          <Text style={styles.btnAltText}>Delete all…</Text>
        </TouchableOpacity>
        <TouchableOpacity style={styles.btn} onPress={tryProduct} disabled={busy}>
          <Text style={styles.btnText}>Try Product</Text>
        </TouchableOpacity>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe:    { flex: 1, backgroundColor: '#0A0A0A' },
  header:  { paddingHorizontal: 20, paddingTop: 24, paddingBottom: 16, borderBottomWidth: 1, borderBottomColor: '#262626' },
  badge:   { color: '#fbbf24', fontSize: 11, fontWeight: '800', letterSpacing: 1.4, textTransform: 'uppercase', marginBottom: 6 },
  title:   { fontSize: 22, fontWeight: '700', color: '#f8fafc' },
  sub:     { fontSize: 13, color: '#cbd5e1', marginTop: 8, lineHeight: 19 },

  scroll:  { flex: 1 },
  sectionLabel: { color: '#a78bfa', fontSize: 11, fontWeight: '800', letterSpacing: 1, textTransform: 'uppercase', marginTop: 18, marginBottom: 6 },
  mono:    { color: '#e2e8f0', fontSize: 12, fontFamily: Platform.select({ ios: 'Menlo', android: 'monospace' }) },
  dim:     { color: '#94a3b8', fontSize: 12, marginTop: 2, lineHeight: 17 },
  row:     { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingVertical: 4, gap: 12, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: '#262626' },

  footer:  { flexDirection: 'row', paddingHorizontal: 16, paddingVertical: 12, gap: 8, borderTopWidth: 1, borderTopColor: '#262626' },
  btn:     { flex: 1, backgroundColor: '#a78bfa', paddingVertical: 13, borderRadius: 10, alignItems: 'center' },
  btnText: { color: '#0A0A0A', fontSize: 14, fontWeight: '800' },
  btnAlt:  { backgroundColor: '#262626' },
  btnDanger:{ backgroundColor: '#7f1d1d' },
  btnAltText:{ color: '#e2e8f0', fontSize: 13, fontWeight: '700' },
  inlineBtn:{ marginTop: 14, alignSelf: 'flex-start', backgroundColor: '#262626', borderColor: '#a78bfa55', borderWidth: 1, paddingHorizontal: 14, paddingVertical: 9, borderRadius: 8 },
  inlineBtnText:{ color: '#a78bfa', fontSize: 12, fontWeight: '800', letterSpacing: 0.4 },
  recoveryMessage: { color: '#fbbf24', fontSize: 13, marginTop: 12, lineHeight: 18 },
});
