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
import { getAuthEpoch, subscribeAuthChanges } from '../src/auth/gameforgeAuth';
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
  const [authEpoch, setAuthEpoch] = React.useState(() => getAuthEpoch());
  const [loadedAuthEpoch, setLoadedAuthEpoch] = React.useState<number | null>(null);
  const [handoffError, setHandoffError] = React.useState<string | null>(null);

  React.useEffect(() => subscribeAuthChanges(() => setAuthEpoch(getAuthEpoch())), []);

  React.useEffect(() => {
    let mounted = true;
    setReady(false);
    setLoadedAuthEpoch(null);
    setIncoming(null);
    setSavedGalaxy(null);
    setHandoffError(null);
    void Promise.all([
      consumeCreatorBridge('galaxy').catch(() => null),
      loadGalaxyDraft().catch(() => null),
    ]).then(([draft, saved]) => {
      if (!mounted) return;
      setIncoming(draft);
      setSavedGalaxy(saved);
    }).finally(() => {
      if (mounted && getAuthEpoch() === authEpoch) {
        setLoadedAuthEpoch(authEpoch);
        setReady(true);
      }
    });
    return () => { mounted = false; };
  }, [authEpoch]);

  const continueInForge = React.useCallback(async (selection: GalaxyBridgeSelection): Promise<void> => {
    try {
      if (getAuthEpoch() !== authEpoch || loadedAuthEpoch !== authEpoch) {
        throw new Error('Account changed before Galaxy handoff');
      }
      await storeCreatorBridge(handoffFromGalaxy(selection, incoming));
      if (getAuthEpoch() !== authEpoch) throw new Error('Account changed before navigating to Forge');
      const handoffId = typeof selection.handoffId === 'string' &&
        /^g[a-z0-9]{1,40}x[a-z0-9]{1,20}$/.test(selection.handoffId)
        ? selection.handoffId : null;
      router.replace({
        pathname: '/skeleton-forge',
        params: { tab: 'build', ...(handoffId ? { handoff: handoffId } : {}) },
      } as any);
    } catch {
      setHandoffError('Could not hand off the Galaxy draft to GameForge. Nothing was built.');
      throw new Error('Galaxy to GameForge handoff failed');
    }
  }, [router, incoming, authEpoch, loadedAuthEpoch]);

  const closing = React.useRef(false);
  const close = React.useCallback(async () => {
    if (closing.current) return;
    closing.current = true;
    try {
      if (incoming) {
        // Galaxy consumed the original one-time Forge handoff on entry.
        // Reissue a fresh, bounded return handoff before leaving, so a
        // remounted Forge route cannot silently lose its authored design.
        // Deliberately do not apply Galaxy edits on Close: only the explicit
        // "Continue this game in GameForge" action transfers changed choices.
        if (getAuthEpoch() !== authEpoch || loadedAuthEpoch !== authEpoch) {
          throw new Error('Creator account changed before returning to GameForge.');
        }
        const previous = handoffFromGalaxy(
          { title: '', vision: '', genreId: null },
          incoming,
        );
        await storeCreatorBridge(previous);
        if (getAuthEpoch() !== authEpoch) {
          throw new Error('Creator account changed before navigation.');
        }
        router.replace('/skeleton-forge?tab=build' as any);
        return;
      }
      // A direct Galaxy visit has no Forge questionnaire to restore.
      const canGoBack = (navigation as any)?.canGoBack?.();
      if (canGoBack) router.back();
      else router.replace('/menu' as any);
    } catch {
      setHandoffError('Could not preserve the original GameForge draft. Galaxy will stay open.');
    } finally {
      closing.current = false;
    }
  }, [router, navigation, incoming, authEpoch, loadedAuthEpoch]);

  return (
    <View style={styles.root} testID="galaxy-studio-route">
      {handoffError ? <Text accessibilityRole="alert" style={{ color: '#FBBF24' }}>{handoffError}</Text> : null}
      {ready && loadedAuthEpoch === authEpoch ? (
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
