/**
 * Entry route — REDUNDANT LAUNCHER CASCADE (2026-02).
 *
 * Boot flow (post-BootLauncher rewrite, 2026-02-17):
 *   1. bootGuardWithTimeout(350) — fast crash-loop check (was 1200ms; the
 *      BootLauncher itself now runs the full health-check battery so we
 *      no longer need to pre-budget for slow AsyncStorage here).
 *   2. If safe-mode requested → redirect once.
 *   3. Otherwise mount <LaunchCascade /> INLINE. Layer 0 is the new
 *      BootLauncher (progress bar + readiness checks + decorative
 *      non-blocking Starfall). Returning users auto-advance when all
 *      checks pass; first-timers tap "Enter the Hub".
 *
 * Layers 1–3 remain as crash-loop fallbacks. The user is always one tap
 * away from /hub or /safe-mode.
 */
import { useEffect, useState } from 'react';
import { View, ActivityIndicator, StyleSheet } from 'react-native';
import { Redirect } from 'expo-router';
import { bootGuard, traceStep, traceStepSync } from '../utils/bootTracer';
import LaunchCascade from '../components/LaunchCascade';

type Decision = 'cascade' | 'safe-mode' | null;

traceStepSync('entry_module_eval');

// Module-level decision cache — the Entry component can re-mount (React
// double-invoke, fast-refresh, navigation churn). Without this, a 2nd mount
// re-runs bootGuard and could FLIP a healthy 'cascade' decision into
// 'safe-mode' (exactly the entry_→cascade THEN entry_→safe_mode flip seen in
// the field). Decide ONCE per process; re-mounts reuse it.
let _entryDecision: Decision = null;

/** Run bootGuard with a hard timeout so a hung AsyncStorage never freezes us. */
function bootGuardWithTimeout(ms: number): Promise<'safe-mode' | 'normal'> {
  return new Promise(resolve => {
    let settled = false;
    const t = setTimeout(() => {
      if (!settled) { settled = true; resolve('normal'); }
    }, ms);
    bootGuard()
      .then(v => { if (!settled) { settled = true; clearTimeout(t); resolve(v); } })
      .catch(() => { if (!settled) { settled = true; clearTimeout(t); resolve('normal'); } });
  });
}

export default function Entry() {
  const [decision, setDecision] = useState<Decision>(null);

  useEffect(() => {
    // Re-mount fast-path: reuse the decision already made this process.
    if (_entryDecision) { setDecision(_entryDecision); return; }
    (async () => {
      try {
        await traceStep('entry_mounted');
        // 1500ms (was 350ms) — on a near-full disk (seen at 98%) the single
        // AsyncStorage read can be slow; bootGuardWithTimeout still defaults
        // to 'normal' on timeout so we never block, but the wider budget lets
        // a genuine crash-loop be detected reliably before we give up.
        const mode = await bootGuardWithTimeout(1500);
        if (mode === 'safe-mode') {
          _entryDecision = 'safe-mode';
          await traceStep('entry_→safe_mode');
          setDecision('safe-mode');
          return;
        }
        _entryDecision = 'cascade';
        await traceStep('entry_→cascade');
        setDecision('cascade');
      } catch {
        // Any failure → still try cascade (never blank-screen).
        _entryDecision = 'cascade';
        setDecision('cascade');
      }
    })();

    // Belt-and-braces: if useEffect itself somehow doesn't fire, force the
    // cascade after a generous timeout (idempotent with the decision above).
    const safety = setTimeout(() => setDecision(d => d || 'cascade'), 2000);
    return () => clearTimeout(safety);
  }, []);

  if (decision === null) {
    return (
      <View style={styles.loader}>
        <ActivityIndicator size="small" color="#a78bfa" />
      </View>
    );
  }
  if (decision === 'safe-mode') {
    return <Redirect href="/safe-mode" />;
  }
  return <LaunchCascade />;
}

const styles = StyleSheet.create({
  loader: {
    flex: 1,
    backgroundColor: '#0A0A0A',
    alignItems: 'center',
    justifyContent: 'center',
  },
});
