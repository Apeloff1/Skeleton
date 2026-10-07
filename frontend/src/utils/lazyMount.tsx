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

type AnyComponent = React.ComponentType<any>;
type ComponentKeys<TModule> = {
  [K in keyof TModule]-?: TModule[K] extends AnyComponent ? K : never;
}[keyof TModule];
type ComponentAt<TModule, K extends keyof TModule> = Extract<TModule[K], AnyComponent>;

/** Preserve the default export's real prop contract through React.lazy. */
export function lazyDefault<TComponent extends AnyComponent>(
  loader: () => Promise<{ default: TComponent }>,
): React.LazyExoticComponent<TComponent> {
  return React.lazy(loader);
}

/** Preserve a named component export's prop contract through React.lazy. */
export function lazyNamed<TModule, K extends ComponentKeys<TModule>>(
  loader: () => Promise<TModule>,
  key: K,
): React.LazyExoticComponent<ComponentAt<TModule, K>> {
  return React.lazy(async () => {
    const module = await loader();
    return { default: module[key] as ComponentAt<TModule, K> };
  });
}

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
