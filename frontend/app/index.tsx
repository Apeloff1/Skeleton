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
 *      checks pass; first-timers tap "Enter Product".
 *
 * Layers 1–3 remain as crash-loop fallbacks. The user is always one tap
 * away from /product or /safe-mode.
 */
import { useEffect, useState } from 'react';
import { View, ActivityIndicator, StyleSheet } from 'react-native';
import { Redirect } from 'expo-router';
import { bootGuard, traceStep, traceStepSync } from '../utils/bootTracer';
import LaunchCascade from '../components/LaunchCascade';
import { accessibleStatusProps } from '../src/accessibility/runtime';
import { useI18n } from '../src/i18n';

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
  const { t } = useI18n();

  useEffect(() => {
    let cancelled = false;
    // Only the first completed decision wins, including the timeout path.
    // A late storage read may never flip an already shown launcher to safe mode.
    const decideOnce = (next: Exclude<Decision, null>) => {
      if (cancelled || _entryDecision) return;
      _entryDecision = next;
      setDecision(next);
    };

    if (_entryDecision) {
      setDecision(_entryDecision);
      return () => { cancelled = true; };
    }

    void (async () => {
      try {
        // Tracing is advisory and must not delay crash-loop admission.
        void traceStep('entry_mounted').catch(() => {});
        const mode = await bootGuardWithTimeout(1500);
        const target = mode === 'safe-mode' ? 'safe-mode' : 'cascade';
        decideOnce(target);
        void traceStep(target === 'safe-mode' ? 'entry_→safe_mode' : 'entry_→cascade').catch(() => {});
      } catch {
        decideOnce('cascade');
      }
    })();

    // A blocked native storage call cannot freeze the launcher indefinitely.
    const safety = setTimeout(() => decideOnce('cascade'), 2000);
    return () => {
      cancelled = true;
      clearTimeout(safety);
    };
  }, []);

  if (decision === null) {
    return (
      <View
        style={styles.loader}
        {...accessibleStatusProps(t('status.startup_check'))}
      >
        <ActivityIndicator
          size="small"
          color="#a78bfa"
          accessibilityElementsHidden
        />
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
