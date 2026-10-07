/**
 * Root layout for Expo Router.
 *
 * Uses <Slot/> so each screen renders inside its own untouched SafeAreaView —
 * preserves the layout of /hub.tsx exactly.
 *
 * 2026-02 — Crash-hardening pass:
 *   • Each route is wrapped in <ScreenGuard key={pathname}> so a render
 *     crash inside one screen produces a recoverable "Retry / Back /
 *     Home" UI on that screen ONLY — the rest of the app stays alive.
 *     Navigating to a different route resets the guard automatically
 *     (key change → remount).
 *   • traceStep('layout_mounted') is fired so the bootTracer can prove
 *     the React tree got at least this far if a later screen crashes.
 *   • The outer <ErrorBoundary> is kept as a final safety net for
 *     crashes that escape the per-screen guard (e.g. in providers).
 */
import { useEffect } from 'react';
import { View, StyleSheet, LogBox } from 'react-native';
import { Slot, usePathname } from 'expo-router';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';
import theme from '../theme/tokens';
import { ErrorBoundary } from '../components/ErrorBoundary';
import ScreenGuard from '../components/withScreenGuard';
import OfflineBanner from '../components/OfflineBanner';
import { ToastHost } from '../components/Toast';
import { ActionSheetHost } from '../components/ActionSheet';
import { traceStep, traceStepSync, installCrashTrace } from '../utils/bootTracer';
import { installMemoryGuard } from '../utils/memoryGuard';
import { installGlobalGuards } from '../utils/globalGuards';
import { installAppStateGuard } from '../utils/safeTimers';
import { loadFeatureFlags } from '../utils/featureFlags';
import { FeatureFlagProvider } from '../src/feature-flags';
import { StabilityBanner } from '../src/components/StabilityBanner';
import { installGlobalErrorHandlers } from '../src/utils/globalErrors';
import { startTunnelHeartbeat } from '../src/utils/tunnelHeartbeat';
import { initSkin, useActiveSkin } from '../src/utils/skinStore';
import DevLogOverlay from '../components/DevLogOverlay';

// Module-eval marker — proves the root layout module was reached on the JS
// thread (fires before React even renders). Install the durable crash trap
// here, the earliest reliable point in app startup.
installCrashTrace();
installMemoryGuard();
traceStepSync('layout_module_eval');

export default function RootLayout() {
  const pathname = usePathname();
  const { version: skinVersion } = useActiveSkin();
  traceStepSync('layout_render');

  useEffect(() => {
    // Silence a deprecation warning emitted by a 3rd-party RN/Expo internal shim
    // (props.pointerEvents). All in-app code already uses style.pointerEvents.
    LogBox.ignoreLogs(['props.pointerEvents is deprecated. Use style.pointerEvents']);
    installGlobalGuards();
    installAppStateGuard();
    // Stability hardening — JS error catcher + tunnel heartbeat.
    installGlobalErrorHandlers();
    startTunnelHeartbeat();
    // Hydrate the feature-flag mirror from AsyncStorage before any screen
    // reads via useFeatureFlag(). Non-blocking — defaults serve as a
    // fallback for the first ~50ms while AsyncStorage resolves.
    loadFeatureFlags().catch(() => {});
    initSkin().catch(() => {});
    traceStep('layout_mounted').catch(() => {});
  }, []);

  useEffect(() => {
    try { (globalThis as any).__lastPathname = pathname || '/'; } catch {}
    traceStep(`route:${pathname || '/'}`).catch(() => {});
  }, [pathname]);

  return (
    <SafeAreaProvider>
      <FeatureFlagProvider>
        <View style={[styles.root, { backgroundColor: theme.colors.bg }]} key={`skin-${skinVersion}`}>
          <StatusBar style="light" />
          <ErrorBoundary>
            <ScreenGuard key={pathname || '/'} name={pathname || '/'}>
              <Slot />
            </ScreenGuard>
          </ErrorBoundary>
          {/* Unified offline/degraded/down banner (replaces NetworkBanner
              when active — both can coexist safely). */}
          <StabilityBanner />
          <OfflineBanner />
          <ToastHost />
          <ActionSheetHost />
          {/* Always-on visual boot/diagnostics log — overlays EVERY page so
              the live trace is visible on-device without a cable. */}
          <DevLogOverlay />
        </View>
      </FeatureFlagProvider>
    </SafeAreaProvider>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: theme.colors.bg,
  },
});
