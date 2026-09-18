/**
 * Root layout for Expo Router.
 *
 * Each route stays behind its own screen guard while global providers and
 * lightweight application hosts are mounted once. Expensive diagnostics and
 * backend heartbeat work are kept off the cold render path.
 */
import { useEffect } from 'react';
import { View, StyleSheet, LogBox } from 'react-native';
import { Slot, usePathname } from 'expo-router';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';
import theme from '../theme/tokens';
import { ErrorBoundary } from '../components/ErrorBoundary';
import ScreenGuard from '../components/withScreenGuard';
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

installCrashTrace();
installMemoryGuard();
traceStepSync('layout_module_eval');

const SHOW_DEV_LOG_OVERLAY = __DEV__ || process.env.EXPO_PUBLIC_DEV_LOG_OVERLAY === '1';
const HEARTBEAT_START_DELAY_MS = 1_500;

function DiagnosticsOverlay() {
  if (!SHOW_DEV_LOG_OVERLAY) return null;
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const DevLogOverlay = require('../components/DevLogOverlay').default;
  return <DevLogOverlay />;
}

export default function RootLayout() {
  const pathname = usePathname();
  const { version: skinVersion } = useActiveSkin();

  useEffect(() => {
    if (__DEV__) {
      LogBox.ignoreLogs(['props.pointerEvents is deprecated. Use style.pointerEvents']);
    }

    installGlobalGuards();
    installAppStateGuard();
    installGlobalErrorHandlers();

    // Device connectivity is observed immediately by StabilityBanner. Delay
    // server polling so it does not compete with the launcher for cold-start
    // CPU, timers, or network sockets.
    const heartbeatTimer = setTimeout(() => {
      try { startTunnelHeartbeat(); } catch {}
    }, HEARTBEAT_START_DELAY_MS);

    loadFeatureFlags().catch(() => {});
    initSkin().catch(() => {});
    traceStep('layout_mounted').catch(() => {});

    return () => clearTimeout(heartbeatTimer);
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
          <StabilityBanner />
          <ToastHost />
          <ActionSheetHost />
          <DiagnosticsOverlay />
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
