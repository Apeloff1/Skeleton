/**
 * ErrorBoundary — top-level React error catcher.
 *
 * Wrap your app/_layout.tsx with this. On any rendered-component error:
 *   1. The error is caught and the app shows a recovery screen instead of crashing.
 *   2. The error is posted to /api/telemetry/last-crash with stack + componentStack.
 *   3. The user can tap "Reload app" to remount the entire subtree.
 */
import React from 'react';
import { View, Text, ScrollView, TouchableOpacity, StyleSheet, Platform } from 'react-native';
import { getSessionId } from '../utils/modalLogger';
import { navToSafeMode } from '../utils/bootTracer';

const BACKEND = process.env.EXPO_PUBLIC_BACKEND_URL || '';

interface State {
  error: Error | null;
  info:  { componentStack?: string } | null;
  remountKey: number;
}

export class ErrorBoundary extends React.Component<{ children: React.ReactNode }, State> {
  state: State = { error: null, info: null, remountKey: 0 };

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { error };
  }

  componentDidCatch(error: Error, info: { componentStack?: string }) {
    this.setState({ info });
    // Universal crash funnel — route to Safe Mode (shows boot trace + recovery).
    try { navToSafeMode(`error_boundary:${(error.message || '').slice(0, 60)}`); } catch {}
    // Fire-and-forget telemetry — never throw from telemetry itself.
    try {
      fetch(`${BACKEND}/api/telemetry/last-crash`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          source:     'ErrorBoundary',
          component:  (info.componentStack || '').split('\n')[1]?.trim() || null,
          message:    error.message,
          stack:      (error.stack || '').slice(0, 8000),
          info:       { componentStack: (info.componentStack || '').slice(0, 4000) },
          session_id: getSessionId(),
        }),
      }).catch(() => {});
      // Also dump the breadcrumb trail so the server can reconstruct
      // what the user was doing before the crash.
      try {
        // Lazy require to avoid pulling apiClient into the ErrorBoundary
        // critical path during normal operation.
        // eslint-disable-next-line @typescript-eslint/no-require-imports
        const { dumpTrail } = require('../src/utils/trailDump');
        dumpTrail({ rid: getSessionId() }).catch?.(() => {});
      } catch { /* swallow */ }
    } catch { /* swallow */ }
  }

  reload = () => {
    this.setState(s => ({ error: null, info: null, remountKey: s.remountKey + 1 }));
  };

  render() {
    if (this.state.error) {
      return (
        <View style={styles.root}>
          <View style={styles.header}>
            <Text style={styles.title}>App hit an unhandled error</Text>
            <Text style={styles.sub}>The crash was logged to telemetry. You can retry without restarting the app.</Text>
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
            <TouchableOpacity style={styles.btn} onPress={this.reload}>
              <Text style={styles.btnText}>Reload app</Text>
            </TouchableOpacity>
          </View>
        </View>
      );
    }
    return <React.Fragment key={this.state.remountKey}>{this.props.children}</React.Fragment>;
  }
}

const styles = StyleSheet.create({
  root:    { flex: 1, backgroundColor: '#0a0f1f' },
  header:  { paddingHorizontal: 20, paddingTop: 60, paddingBottom: 12 },
  title:   { fontSize: 22, fontWeight: '700', color: '#fb7185' },
  sub:     { fontSize: 13, color: '#cbd5e1', marginTop: 4 },
  scroll:  { flex: 1, borderTopWidth: 1, borderTopColor: '#1e293b' },
  label:   { color: '#a78bfa', fontSize: 12, fontWeight: '700', marginTop: 12, marginBottom: 4, textTransform: 'uppercase', letterSpacing: 0.5 },
  errName: { color: '#fda4af', fontSize: 14, fontFamily: Platform.select({ ios: 'Menlo', android: 'monospace' }) },
  trace:   { color: '#cbd5e1', fontSize: 11, fontFamily: Platform.select({ ios: 'Menlo', android: 'monospace' }) },
  footer:  { paddingHorizontal: 20, paddingVertical: 14, borderTopWidth: 1, borderTopColor: '#1e293b' },
  btn:     { backgroundColor: '#a78bfa', paddingVertical: 14, borderRadius: 10, alignItems: 'center' },
  btnText: { color: '#0a0f1f', fontSize: 15, fontWeight: '800' },
});

export default ErrorBoundary;
