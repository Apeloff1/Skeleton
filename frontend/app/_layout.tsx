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
import Head from 'expo-router/head';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';
import theme from '../theme/tokens';
import { ErrorBoundary } from '../components/ErrorBoundary';
import { NonCriticalHostBoundary } from '../components/NonCriticalHostBoundary';
import ScreenGuard from '../components/withScreenGuard';
import { ToastHost } from '../components/Toast';
import { ActionSheetHost } from '../components/ActionSheet';
import { traceStep, traceStepSync, installCrashTrace } from '../utils/bootTracer';
import { installMemoryGuard, uninstallMemoryGuard, registerMemoryShedder } from '../utils/memoryGuard';
import { clearMemCache } from '../utils/resilientNet';
import { shedSafeStorageMirror } from '../utils/safeStorage';
import { purgeThermalCachesIfPresent } from '../utils/thermalGuard';
import { installGlobalGuards } from '../utils/globalGuards';
import { installAppStateGuard, uninstallAppStateGuard } from '../utils/safeTimers';
import { loadFeatureFlags } from '../utils/featureFlags';
import { FeatureFlagProvider } from '../src/feature-flags';
import { StabilityBanner } from '../src/components/StabilityBanner';
import { installGlobalErrorHandlers } from '../src/utils/globalErrors';
import { startTunnelHeartbeat, stopTunnelHeartbeat } from '../src/utils/tunnelHeartbeat';
import { initSkin, useActiveSkin } from '../src/utils/skinStore';
import { LocaleProvider } from '../src/i18n';

// Auxiliary diagnostics may not make importing the app itself fatal.
try { installCrashTrace(); } catch {}
try { installMemoryGuard(); } catch {}
try { traceStepSync('layout_module_eval'); } catch {}

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
  // Subscribe to palette changes without destroying screens, providers or in-flight work.
  useActiveSkin();

  useEffect(() => {
    if (__DEV__) {
      LogBox.ignoreLogs(['props.pointerEvents is deprecated. Use style.pointerEvents']);
    }

    // These observers are independent: failure to install one must not
    // prevent the others or crash the initial React commit.
    try { installGlobalGuards(); } catch {}
    try { installMemoryGuard(); } catch {}
    try { installAppStateGuard(); } catch {}
    try { installGlobalErrorHandlers(); } catch {}

    // Drop only regenerable in-memory caches on OS memory pressure; never
    // clear durable project, checkpoint, or learned model state.
    const disposeNetworkShedder = registerMemoryShedder('network-cache', clearMemCache);
    const disposeThermalShedder = registerMemoryShedder(
      'thermal-cache', purgeThermalCachesIfPresent,
    );
    const disposeStorageMirror = registerMemoryShedder(
      'native-read-mirror', shedSafeStorageMirror,
    );

    // Device connectivity is observed immediately by StabilityBanner. Delay
    // server polling so it does not compete with the launcher for cold-start
    // CPU, timers, or network sockets.
    const heartbeatTimer = setTimeout(() => {
      try { startTunnelHeartbeat(); } catch {}
    }, HEARTBEAT_START_DELAY_MS);

    loadFeatureFlags().catch(() => {});
    initSkin().catch(() => {});
    traceStep('layout_mounted').catch(() => {});

    return () => {
      clearTimeout(heartbeatTimer);
      stopTunnelHeartbeat();
      disposeNetworkShedder();
      disposeThermalShedder();
      disposeStorageMirror();
      // React dev remounts must release the native observers as well as
      // their timers. Root effect re-installs both guards on next mount.
      uninstallAppStateGuard();
      uninstallMemoryGuard();
    };
  }, []);

  useEffect(() => {
    try { (globalThis as any).__lastPathname = pathname || '/'; } catch {}
    traceStep(`route:${pathname || '/'}`).catch(() => {});
  }, [pathname]);

  return (
    // Last resort: protects even locale and flag providers. The inner error
    // boundary below continues to handle errors scoped to an active route.
    <ErrorBoundary>
      <SafeAreaProvider>
      <Head>
        <title>Skeleton — Jeeves AI Game Studio</title>
        <meta
          name="description"
          content="A local-first game studio with Jeeves AI chat, Dragon source review, world editing, human and AI play, and bounded training."
        />
      </Head>
      <LocaleProvider>
        <FeatureFlagProvider>
          <View style={[styles.root, { backgroundColor: theme.colors.bg }]}>
          <StatusBar style="light" />
          <ErrorBoundary>
            <ScreenGuard key={pathname || '/'} name={pathname || '/'}>
              <Slot />
            </ScreenGuard>
          </ErrorBoundary>
          <NonCriticalHostBoundary name="connectivity">
            <StabilityBanner />
          </NonCriticalHostBoundary>
          <NonCriticalHostBoundary name="toast">
            <ToastHost />
          </NonCriticalHostBoundary>
          <NonCriticalHostBoundary name="action_sheet">
            <ActionSheetHost />
          </NonCriticalHostBoundary>
          <NonCriticalHostBoundary name="dev_overlay">
            <DiagnosticsOverlay />
          </NonCriticalHostBoundary>
          </View>
        </FeatureFlagProvider>
      </LocaleProvider>
      </SafeAreaProvider>
    </ErrorBoundary>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: theme.colors.bg,
  },
});
