/**
 * lazyMount — shared helpers to keep heavy modules OUT of the boot-time
 * bundle evaluation.
 *
 * WHY: expo-router's `require.context` eagerly evaluates EVERY route file at
 * startup. Any module a route file statically imports (three.js, expo-gl, big
 * factory modals…) is therefore evaluated at boot too — which OOM-crashes
 * mid-tier devices. Wrapping those imports in `React.lazy` defers their
 * evaluation until the component actually renders.
 *
 * Usage in a route file:
 *   const Heavy = lazyDefault(() => import('../path/Heavy'));      // default export
 *   const Named = lazyNamed(() => import('../path/mod'), 'Named'); // named export
 *   ...
 *   {show && <LazyMount><Heavy .../></LazyMount>}
 */
import React from 'react';
import { View, ActivityIndicator, StyleSheet } from 'react-native';

export const lazyDefault = (loader: () => Promise<any>) => React.lazy(loader);

export const lazyNamed = (loader: () => Promise<any>, key: string) =>
  React.lazy(() => loader().then((m: any) => ({ default: m[key] })));

export const LazyMount: React.FC<{ children: React.ReactNode; fallback?: React.ReactNode }> = ({
  children,
  fallback,
}) => (
  <React.Suspense
    fallback={
      fallback ?? (
        <View style={styles.fallback}>
          <ActivityIndicator color="#A78BFA" />
        </View>
      )
    }
  >
    {children}
  </React.Suspense>
);

const styles = StyleSheet.create({
  fallback: { flex: 1, alignItems: 'center', justifyContent: 'center', minHeight: 180 },
});
