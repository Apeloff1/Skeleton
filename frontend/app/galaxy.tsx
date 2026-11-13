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
import { View, StyleSheet, Text } from 'react-native';
import { useRouter, useNavigation } from 'expo-router';
import { lazyDefault, LazyMount } from '../src/utils/lazyMount';
const GalaxyStudioFactoryModal = lazyDefault(() => import('../src/features/GalaxyStudioFactory/GalaxyStudioFactoryModal'));
import theme from '../src/theme/tokens';
import { loadGalaxyDraft, type GalaxyDraftSnapshot } from '../src/features/GalaxyStudioFactory/draftCustody';
import { handoffFromGalaxy, type CreatorBridgeDraft, type GalaxyBridgeSelection } from '../src/skeletonForge/creatorBridge';
import { consumeCreatorBridge, storeCreatorBridge } from '../src/skeletonForge/creatorBridgeStorage';

export default function GalaxyRoute() {
  const router = useRouter();
  const navigation = useNavigation();
  const [incoming, setIncoming] = React.useState<CreatorBridgeDraft | null>(null);
  const [savedGalaxy, setSavedGalaxy] = React.useState<GalaxyDraftSnapshot | null>(null);
  const [ready, setReady] = React.useState(false);
  const [handoffError, setHandoffError] = React.useState<string | null>(null);

  React.useEffect(() => {
    let mounted = true;
    void Promise.all([
      consumeCreatorBridge('galaxy').catch(() => null),
      loadGalaxyDraft().catch(() => null),
    ]).then(([draft, saved]) => {
      if (!mounted) return;
      setIncoming(draft);
      setSavedGalaxy(saved);
    }).finally(() => { if (mounted) setReady(true); });
    return () => { mounted = false; };
  }, []);

  const continueInForge = React.useCallback(async (selection: GalaxyBridgeSelection): Promise<void> => {
    try {
      await storeCreatorBridge(handoffFromGalaxy(selection, incoming));
      router.replace('/skeleton-forge?tab=build' as any);
    } catch {
      setHandoffError('Could not hand off the Galaxy draft to GameForge. Nothing was built.');
      throw new Error('Galaxy to GameForge handoff failed');
    }
  }, [router, incoming]);

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
      {handoffError ? <Text accessibilityRole="alert" style={{ color: '#FBBF24' }}>{handoffError}</Text> : null}
      {ready ? (
        <LazyMount><GalaxyStudioFactoryModal visible={true} onClose={close}
          initialForgeDraft={incoming} initialGalaxyDraft={savedGalaxy}
          handoffError={handoffError} onSendToForge={continueInForge} /></LazyMount>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: theme.colors.bg },
});
