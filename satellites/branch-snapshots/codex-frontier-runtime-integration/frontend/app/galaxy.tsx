/**
 * /galaxy — dedicated lightweight route that mounts the Galaxy Studio
 *  Factory modal in isolation.
 *
 *  Why: the previous nav pattern was `/menu` → tap card → push `/` (heavy
 *  2 520-line editor) → editor opens modal via Zustand. That was a
 *  20-30 s cold-start trap on headless web preview AND on first-launch
 *  real devices.
 *
 *  This route avoids the editor entirely: it just renders a minimal
 *  Screen + the GalaxyStudioFactoryModal at visible=true. Closing
 *  pops back to wherever the user came from.
 */
import React from 'react';
import { View, StyleSheet } from 'react-native';
import { useRouter, useNavigation } from 'expo-router';
import { lazyDefault, LazyMount } from '../src/utils/lazyMount';
const GalaxyStudioFactoryModal = lazyDefault(() => import('../features/GalaxyStudioFactory/GalaxyStudioFactoryModal'));
import theme from '../theme/tokens';

export default function GalaxyRoute() {
  const router = useRouter();
  const navigation = useNavigation();
  const close = React.useCallback(() => {
    // If we have history (e.g. arrived via /menu), pop. Otherwise, on a
    // direct deep-link load (`/galaxy`), navigate to a safe landing page
    // so the close button is never a no-op.
    try {
      // expo-router exposes canGoBack on the underlying React Navigation nav.
      const canGoBack = (navigation as any)?.canGoBack?.();
      if (canGoBack) {
        router.back();
      } else {
        router.replace('/menu' as any);
      }
    } catch {
      try { router.replace('/menu' as any); } catch {}
    }
  }, [router, navigation]);

  return (
    <View style={styles.root} testID="galaxy-studio-route">
      <LazyMount><GalaxyStudioFactoryModal visible={true} onClose={close} /></LazyMount>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: theme.colors.bg },
});
