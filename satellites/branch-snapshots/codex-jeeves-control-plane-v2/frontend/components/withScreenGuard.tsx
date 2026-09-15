/**
 * withScreenGuard — per-screen ErrorBoundary wrapper with self-healing retry.
 *
 *  Wrap any route component so its render-time crashes don't escape to
 *  the root ErrorBoundary. Each screen gets:
 *    • Friendly fallback UI ("This screen hit an error — go back / retry")
 *    • Telemetry post to /api/telemetry/last-crash
 *    • Self-healing: first crash auto-retries silently after 250ms (most
 *      transient errors — late asset hydration, race conditions on first
 *      mount — succeed on the second attempt). A non-blocking toast tells
 *      the user "Auto-recovering…" without breaking flow.
 *    • If the SECOND attempt also fails, the boundary surfaces the
 *      traditional crash card with manual Retry / Back / Home buttons.
 *    • Crash history is kept in module-scope so subsequent visits to the
 *      same screen don't keep auto-retrying forever after a 'sticky' fault.
 *
 *  Usage at bottom of any route file:
 *      export default withScreenGuard(MyScreen, 'MyScreen');
 */
import React from 'react';
import { View, Text, ScrollView, TouchableOpacity, StyleSheet, Platform } from 'react-native';
import { getSessionId, recordEvent } from '../utils/modalLogger';
import { navToSafeMode } from '../utils/bootTracer';

const BACKEND = process.env.EXPO_PUBLIC_BACKEND_URL || '';

/** Track persistent failures across remounts so a "sticky" crash doesn't
 *  retry infinitely. After 2 self-heal attempts in the same session for
 *  the same screen, we skip auto-retry and surface the fallback UI. */
const _autoHealCounts = new Map<string, number>();
const MAX_AUTOHEAL_PER_SESSION = 2;

interface GuardState {
  error: Error | null;
  info:  { componentStack?: string } | null;
  remountKey: number;
  /** Whether the boundary is currently in its "self-heal pending" delay. */
  selfHealPending: boolean;
}

class ScreenGuard extends React.Component<{ name: string; children: React.ReactNode }, GuardState> {
  state: GuardState = { error: null, info: null, remountKey: 0, selfHealPending: false };
  private healTimer: ReturnType<typeof setTimeout> | null = null;

  static getDerivedStateFromError(error: Error): Partial<GuardState> {
    return { error };
  }

  componentDidCatch(error: Error, info: { componentStack?: string }) {
    this.setState({ info });
    const name = this.props.name;

    try {
      recordEvent(name, 'screen_crash', 'fatal', {
        message: error.message,
        stack:   (error.stack || '').slice(0, 4000),
        componentStack: (info.componentStack || '').slice(0, 2000),
      });
      fetch(`${BACKEND}/api/telemetry/last-crash`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          source:     'ScreenGuard',
          component:  name,
          message:    error.message,
          stack:      (error.stack || '').slice(0, 8000),
          info:       { componentStack: (info.componentStack || '').slice(0, 4000) },
          session_id: getSessionId(),
        }),
      }).catch(() => {});
    } catch { /* swallow */ }

    // ── SELF-HEAL ─────────────────────────────────────────────
    // First {MAX_AUTOHEAL_PER_SESSION} crashes per screen are silently
    // recovered after a small delay. After that, show the fallback.
    const prior = _autoHealCounts.get(name) ?? 0;
    if (prior < MAX_AUTOHEAL_PER_SESSION) {
      _autoHealCounts.set(name, prior + 1);
      this.setState({ selfHealPending: true });
      this.healTimer = setTimeout(() => {
        // Non-blocking toast — lazy-required so a Toast bus failure
        // can never block recovery itself.
        try {
          // eslint-disable-next-line @typescript-eslint/no-require-imports
          const { toast } = require('./Toast');
          toast.info('Auto-recovering…', { durationMs: 1400 });
        } catch { /* swallow */ }
        try {
          recordEvent(name, 'screen_autoheal', 'info', {
            attempt: prior + 1, message: error.message,
          });
        } catch { /* swallow */ }
        this.setState(s => ({ error: null, info: null, remountKey: s.remountKey + 1, selfHealPending: false }));
      }, 280);
    } else {
      // Auto-heal exhausted → this screen is persistently crashing. Funnel
      // to Safe Mode (shows the boot trace + recovery options) instead of
      // stranding the user on the inline crash card.
      try { navToSafeMode(`screen_crash:${name}`); } catch {}
    }
  }

  componentWillUnmount() {
    if (this.healTimer) clearTimeout(this.healTimer);
  }

  retry = () => this.setState(s => ({ error: null, info: null, remountKey: s.remountKey + 1, selfHealPending: false }));

  goBack = () => {
    try {
      // eslint-disable-next-line @typescript-eslint/no-require-imports
      const { router } = require('expo-router');
      if (router.canGoBack()) router.back();
      else router.replace('/hub');
    } catch { /* swallow */ }
  };

  goHome = () => {
    try {
      // eslint-disable-next-line @typescript-eslint/no-require-imports
      const { router } = require('expo-router');
      router.replace('/menu');
    } catch { /* swallow */ }
  };

  /** Force a manual retry AND reset the auto-heal counter so the user
   *  gets two more silent attempts if it crashes again from this point. */
  retryAndReset = () => {
    _autoHealCounts.set(this.props.name, 0);
    this.retry();
  };

  render() {
    // While self-healing is pending, render a tiny inline placeholder
    // (NOT the heavy fallback card) so the user sees minimal disruption.
    if (this.state.selfHealPending) {
      return (
        <View style={styles.healingShim}>
          <Text style={styles.healingDot}>●</Text>
          <Text style={styles.healingText}>Recovering this screen…</Text>
        </View>
      );
    }

    if (this.state.error) {
      const autoHealUsed = _autoHealCounts.get(this.props.name) ?? 0;
      return (
        <View style={styles.root}>
          <View style={styles.header}>
            <Text style={styles.badge}>{this.props.name}</Text>
            <Text style={styles.title}>This screen hit an error</Text>
            <Text style={styles.sub}>
              The rest of the app is still running. We auto-recovered {autoHealUsed} time{autoHealUsed === 1 ? '' : 's'} —
              you can retry, go back, or head home.
            </Text>
          </View>
          <ScrollView style={styles.scroll} contentContainerStyle={{ padding: 16 }}>
            <Text style={styles.label}>Error</Text>
            <Text style={styles.errName}>{this.state.error.name}: {this.state.error.message}</Text>
            <Text style={styles.label}>Stack</Text>
            <Text style={styles.trace}>{this.state.error.stack || '(no stack)'}</Text>
            {this.state.info?.componentStack ? (<>
              <Text style={styles.label}>Component tree</Text>
              <Text style={styles.trace}>{this.state.info.componentStack}</Text>
            </>) : null}
          </ScrollView>
          <View style={styles.footer}>
            <TouchableOpacity style={[styles.btn, styles.btnAlt]} onPress={this.goBack}>
              <Text style={styles.btnAltText}>Back</Text>
            </TouchableOpacity>
            <TouchableOpacity style={[styles.btn, styles.btnAlt]} onPress={this.goHome}>
              <Text style={styles.btnAltText}>Home</Text>
            </TouchableOpacity>
            <TouchableOpacity style={styles.btn} onPress={this.retryAndReset}>
              <Text style={styles.btnText}>Retry</Text>
            </TouchableOpacity>
          </View>
        </View>
      );
    }
    return <React.Fragment key={this.state.remountKey}>{this.props.children}</React.Fragment>;
  }
}

export function withScreenGuard<P extends object>(Component: React.ComponentType<P>, name: string): React.FC<P> {
  const Guarded: React.FC<P> = (props) => {
    try {
       
      // eslint-disable-next-line @typescript-eslint/no-require-imports
      const { useRenderTrace } = require('../utils/perf');
      // eslint-disable-next-line react-hooks/rules-of-hooks
      useRenderTrace(name);
    } catch { /* swallow */ }
    return (
      <ScreenGuard name={name}>
        <Component {...props} />
      </ScreenGuard>
    );
  };
  Guarded.displayName = `Guarded(${name})`;
  return Guarded;
}

/** Test helper — clear the per-screen self-heal counter (e.g. after a deploy). */
export function resetScreenGuardCounters() {
  _autoHealCounts.clear();
}

export default ScreenGuard;

const styles = StyleSheet.create({
  root:    { flex: 1, backgroundColor: '#0a0f1f' },
  header:  { paddingHorizontal: 20, paddingTop: 60, paddingBottom: 14, borderBottomWidth: 1, borderBottomColor: '#1e293b' },
  badge:   { color: '#a78bfa', fontSize: 11, fontWeight: '800', letterSpacing: 1.2, textTransform: 'uppercase', marginBottom: 6 },
  title:   { fontSize: 22, fontWeight: '700', color: '#fb7185' },
  sub:     { fontSize: 13, color: '#cbd5e1', marginTop: 6, lineHeight: 18 },
  scroll:  { flex: 1 },
  label:   { color: '#a78bfa', fontSize: 11, fontWeight: '700', marginTop: 12, marginBottom: 4, textTransform: 'uppercase', letterSpacing: 0.5 },
  errName: { color: '#fda4af', fontSize: 14, fontFamily: Platform.select({ ios: 'Menlo', android: 'monospace' }) },
  trace:   { color: '#cbd5e1', fontSize: 11, fontFamily: Platform.select({ ios: 'Menlo', android: 'monospace' }), lineHeight: 16 },
  footer:  { flexDirection: 'row', paddingHorizontal: 16, paddingVertical: 12, gap: 8, borderTopWidth: 1, borderTopColor: '#1e293b' },
  btn:     { flex: 1, backgroundColor: '#a78bfa', paddingVertical: 13, borderRadius: 10, alignItems: 'center' },
  btnText: { color: '#0a0f1f', fontSize: 14, fontWeight: '800' },
  btnAlt:  { backgroundColor: '#1e293b' },
  btnAltText: { color: '#e2e8f0', fontSize: 14, fontWeight: '700' },

  healingShim: { flex: 1, backgroundColor: '#0a0f1f', alignItems: 'center', justifyContent: 'center', gap: 10 },
  healingDot:  { color: '#a78bfa', fontSize: 14, fontWeight: '900', opacity: 0.7 },
  healingText: { color: '#64748b', fontSize: 12, fontWeight: '700', letterSpacing: 0.5, textTransform: 'uppercase' },
});
