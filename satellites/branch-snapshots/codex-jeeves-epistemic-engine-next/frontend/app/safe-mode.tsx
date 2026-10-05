/**
 * /safe-mode — Recovery screen shown after 2+ consecutive crashes.
 *
 * Displays:
 *   • Last successful boot timestamp
 *   • The recorded boot trace (steps the app reached before crashing)
 *   • Crash count
 *   • Buttons: "Try Hub again", "Reset welcome flag", "Wipe app state"
 *
 * This is the ultimate safety net: even if /hub crashes on every launch,
 * the user always has a way to recover without uninstall/reinstall.
 */
import { useEffect, useState } from 'react';
import { View, Text, ScrollView, TouchableOpacity, StyleSheet, SafeAreaView, Platform } from 'react-native';
import { useRouter } from 'expo-router';
import AsyncStorage from '@react-native-async-storage/async-storage';
import {
  getLastTrace, getCrashCount, getLastCleanBoot,
  clearCrashes, resetBootState, TraceStep,
} from '../utils/bootTracer';
import {
  FEATURE_FLAGS, getFeatureFlag, loadFeatureFlags,
  resetAllFlags, getModifiedFlagKeys,
} from '../utils/featureFlags';

export default function SafeModeRoute() {
  const router = useRouter();
  const [trace, setTrace] = useState<TraceStep[]>([]);
  const [crashCount, setCrashCount] = useState(0);
  const [lastClean, setLastClean] = useState<number | null>(null);
  /** Re-render trigger for flag changes so the diagnostic panel stays fresh. */
  const [, setFlagsBump] = useState(0);

  useEffect(() => {
    (async () => {
      setTrace(await getLastTrace());
      setCrashCount(await getCrashCount());
      setLastClean(await getLastCleanBoot());
      // Make sure flag values are hydrated for the diagnostic snapshot.
      await loadFeatureFlags();
      setFlagsBump(n => n + 1);
    })();
  }, []);

  const onResetFlags = async () => {
    await resetAllFlags();
    setFlagsBump(n => n + 1);
  };

  const tryHub = async () => {
    await clearCrashes();
    router.replace('/hub');
  };

  const resetWelcome = async () => {
    try { await AsyncStorage.removeItem('@codedock:welcome_seen:v1'); } catch {}
    await clearCrashes();
    router.replace('/welcome');
  };

  const wipeAll = async () => {
    try {
      const keys = await AsyncStorage.getAllKeys();
      // Keep only the bootTracer keys cleared, plus welcome flag
      await AsyncStorage.multiRemove(keys);
    } catch {}
    await resetBootState();
    router.replace('/welcome');
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
          The app has crashed {crashCount} time{crashCount === 1 ? '' : 's'} in a row before reaching the Hub.
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

        <Text style={styles.sectionLabel}>Tip</Text>
        <Text style={styles.dim}>
          The trace above shows what step the app reached before crashing.
          Share this list with the developer to help diagnose the failure.
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
        <TouchableOpacity style={[styles.btn, styles.btnAlt]} onPress={resetWelcome}>
          <Text style={styles.btnAltText}>Reset welcome</Text>
        </TouchableOpacity>
        <TouchableOpacity style={[styles.btn, styles.btnDanger]} onPress={wipeAll}>
          <Text style={styles.btnAltText}>Wipe all</Text>
        </TouchableOpacity>
        <TouchableOpacity style={styles.btn} onPress={tryHub}>
          <Text style={styles.btnText}>Try Hub</Text>
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
});
