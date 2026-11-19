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
import { View, StyleSheet, Text, Pressable } from 'react-native';
import { useRouter, useNavigation } from 'expo-router';
import { lazyDefault, LazyMount } from '../src/utils/lazyMount';
const GalaxyStudioFactoryModal = lazyDefault(() => import('../src/features/GalaxyStudioFactory/GalaxyStudioFactoryModal'));
import theme from '../src/theme/tokens';
import { loadGalaxyDraft, type GalaxyDraftSnapshot } from '../src/features/GalaxyStudioFactory/draftCustody';
import { handoffFromGalaxy, type CreatorBridgeDraft, type GalaxyBridgeSelection } from '../src/skeletonForge/creatorBridge';
import { consumeCreatorBridge, storeCreatorBridge } from '../src/skeletonForge/creatorBridgeStorage';
import { recoverCreatorRoute } from '../src/skeletonForge/creatorRouteRecovery';

export default function GalaxyRoute() {
  const router = useRouter();
  const navigation = useNavigation();
  const [incoming, setIncoming] = React.useState<CreatorBridgeDraft | null>(null);
  const [savedGalaxy, setSavedGalaxy] = React.useState<GalaxyDraftSnapshot | null>(null);
  const [ready, setReady] = React.useState(false);
  const [authEpoch, setAuthEpoch] = React.useState(() => getAuthEpoch());
  const [loadedAuthEpoch, setLoadedAuthEpoch] = React.useState<number | null>(null);
  const [handoffError, setHandoffError] = React.useState<string | null>(null);
  const [recoveryError, setRecoveryError] = React.useState(false);
  const [recoveryAttempt, setRecoveryAttempt] = React.useState(0);

  React.useEffect(() => subscribeAuthChanges(() => setAuthEpoch(getAuthEpoch())), []);

  React.useEffect(() => {
    let mounted = true;
    setReady(false);
    setLoadedAuthEpoch(null);
    setIncoming(null);
    setSavedGalaxy(null);
    setHandoffError(null);
    setRecoveryError(false);
    const isCurrent = () => mounted && getAuthEpoch() === authEpoch;
    void recoverCreatorRoute(loadGalaxyDraft, () => consumeCreatorBridge('galaxy', authEpoch, isCurrent), isCurrent)
      .then(({ handoff, draft }) => {
        if (!isCurrent()) return;
        setIncoming(handoff);
        setSavedGalaxy(draft);
        setLoadedAuthEpoch(authEpoch);
        setReady(true);
      })
      .catch(() => {
        if (isCurrent()) setRecoveryError(true);
      });
    return () => { mounted = false; };
  }, [authEpoch, recoveryAttempt]);

  const continueInForge = React.useCallback(async (selection: GalaxyBridgeSelection): Promise<void> => {
    try {
      if (getAuthEpoch() !== authEpoch || loadedAuthEpoch !== authEpoch) throw new Error('Stale Galaxy editor');
      await storeCreatorBridge(handoffFromGalaxy(selection, incoming), authEpoch);
      if (getAuthEpoch() !== authEpoch) throw new Error('Account changed before navigation');
      router.replace('/skeleton-forge?tab=build' as any);
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
        await storeCreatorBridge(previous, authEpoch);
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
      {!ready && !recoveryError ? <Text accessibilityRole="progressbar" style={{ color: '#FBBF24', padding: 12 }}>Restoring saved creator state…</Text> : null}
      {recoveryError ? (
        <Pressable accessibilityRole="button" accessibilityLabel="Retry creator draft recovery"
          onPress={() => { setRecoveryError(false); setRecoveryAttempt(value => value + 1); }}>
          <Text style={{ color: '#FBBF24', padding: 12 }}>Saved creator state is unavailable. Retry recovery.</Text>
        </Pressable>
      ) : null}
      {handoffError ? <Text accessibilityRole="alert" style={{ color: '#FBBF24' }}>{handoffError}</Text> : null}
      {ready && loadedAuthEpoch === authEpoch ? (
        <LazyMount><GalaxyStudioFactoryModal key={authEpoch} visible={true} onClose={close}
          initialForgeDraft={incoming} initialGalaxyDraft={savedGalaxy}
          handoffError={handoffError} onSendToForge={continueInForge} /></LazyMount>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: theme.colors.bg },
});
