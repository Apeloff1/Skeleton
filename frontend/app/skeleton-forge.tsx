/**
 * /skeleton-forge — Skeleton GameForge cockpit: guided questionnaire,
 * live compose graph, build plan, forge-run panel, era viewer and console.
 * Deep link a tab with ?tab=build|compose|plan|run|eras|console.
 */
import React from 'react';
import { getAuthEpoch, subscribeAuthChanges } from '../src/auth/gameforgeAuth';
import { SafeAreaView, StyleSheet, Text } from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import ForgeCockpitScreen from '../src/skeletonForge/components/ForgeCockpitScreen';
import { parseTabParam } from '../src/skeletonForge/cockpitScreen';
import { C } from '../src/skeletonForge/components/theme';
import { handoffFromForge, handoffToStudio, forgeStateFromHandoff, type CreatorBridgeDraft } from '../src/skeletonForge/creatorBridge';
import { consumeCreatorBridge, storeCreatorBridge } from '../src/skeletonForge/creatorBridgeStorage';
import type { QuestionnaireState } from '../src/skeletonForge/questionnaire';
import { loadGalaxyDraft, type GalaxyDraftSnapshot } from '../src/features/GalaxyStudioFactory/draftCustody';

export default function SkeletonForgeRoute() {
  const params = useLocalSearchParams<{ tab?: string; handoff?: string }>();
  const router = useRouter();
  const [incoming, setIncoming] = React.useState<CreatorBridgeDraft | null>(null);
  const [savedGalaxy, setSavedGalaxy] = React.useState<GalaxyDraftSnapshot | null>(null);
  const [ready, setReady] = React.useState(false);
  const [authEpoch, setAuthEpoch] = React.useState(() => getAuthEpoch());
  const [loadedAuthEpoch, setLoadedAuthEpoch] = React.useState<number | null>(null);
  const handoffInFlight = React.useRef(false);
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
      consumeCreatorBridge('forge').catch(() => null),
      loadGalaxyDraft().catch(() => null),
    ]).then(([draft, galaxyDraft]) => {
      if (!mounted) return;
      setIncoming(draft);
      setSavedGalaxy(galaxyDraft);
    }).finally(() => {
      if (mounted && getAuthEpoch() === authEpoch) {
        setLoadedAuthEpoch(authEpoch);
        setReady(true);
      }
    });
    return () => { mounted = false; };
  }, [authEpoch]);

  const openGalaxy = React.useCallback((draft: QuestionnaireState) => {
    if (handoffInFlight.current) return;
    handoffInFlight.current = true;
    try {
      void storeCreatorBridge(handoffFromForge(draft, Date.now(), incoming))
        .then(() => router.push('/galaxy' as any))
        .catch(() => setHandoffError('Could not save the GameForge draft. Navigation cancelled to preserve your work.'))
        .finally(() => { handoffInFlight.current = false; });
    } catch {
      handoffInFlight.current = false;
      setHandoffError('Invalid GameForge draft; nothing was transferred.');
    }
  }, [router, incoming]);

  const returnToStudio = React.useCallback((draft: QuestionnaireState) => {
    if (handoffInFlight.current || !incoming?.studioProjectId || !incoming.studioProjectUpdatedAt) return;
    handoffInFlight.current = true;
    try {
      void storeCreatorBridge(handoffToStudio(draft, incoming))
        .then(() => router.replace('/skeleton-studio' as any))
        .catch(() => setHandoffError('Could not save the edited Forge questionnaire for Studio. Stay here and retry.'))
        .finally(() => { handoffInFlight.current = false; });
    } catch {
      handoffInFlight.current = false;
      setHandoffError('Could not prepare a safe, source-bound Studio return.');
    }
  }, [incoming, router]);

  return (
    <SafeAreaView style={st.root}>
      {handoffError ? <Text accessibilityRole="alert" style={{ color: C.amber }}>{handoffError}</Text> : null}
      {ready && loadedAuthEpoch === authEpoch && savedGalaxy ? (
        <Text style={{ color: C.green, fontSize: 12, paddingHorizontal: 12, paddingVertical: 5 }}
          testID="forge-saved-galaxy-instruments">
          Galaxy draft preserved on this device: {Object.keys(savedGalaxy.matrices).length} advanced matrix families and {Object.keys(savedGalaxy.extraParams).length} extra sliders. Reopen Galaxy Studio to edit them.
        </Text>
      ) : null}
      {ready && loadedAuthEpoch === authEpoch ? (
        <ForgeCockpitScreen
          initialTab={parseTabParam(params.tab)}
          galaxyHandoffId={typeof params.handoff === 'string' ? params.handoff : null}
          initialQuestionnaire={incoming ? forgeStateFromHandoff(incoming) : null}
          onOpenGalaxyStudio={openGalaxy}
          onReturnToStudio={incoming?.studioProjectId && incoming.studioProjectUpdatedAt ? returnToStudio : undefined}
        />
      ) : null}
    </SafeAreaView>
  );
}

const st = StyleSheet.create({ root: { flex: 1, backgroundColor: C.bg } });
