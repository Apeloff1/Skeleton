/**
 * /skeleton-forge — Skeleton GameForge cockpit: guided questionnaire,
 * live compose graph, build plan, forge-run panel, era viewer and console.
 * Deep link a tab with ?tab=build|compose|plan|run|eras|console.
 */
import React from 'react';
import { SafeAreaView, StyleSheet, Text } from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import ForgeCockpitScreen from '../src/skeletonForge/components/ForgeCockpitScreen';
import { parseTabParam } from '../src/skeletonForge/cockpitScreen';
import { C } from '../src/skeletonForge/components/theme';
import { handoffFromForge, forgeStateFromHandoff, type CreatorBridgeDraft } from '../src/skeletonForge/creatorBridge';
import { consumeCreatorBridge, storeCreatorBridge } from '../src/skeletonForge/creatorBridgeStorage';
import type { QuestionnaireState } from '../src/skeletonForge/questionnaire';

export default function SkeletonForgeRoute() {
  const params = useLocalSearchParams<{ tab?: string }>();
  const router = useRouter();
  const [incoming, setIncoming] = React.useState<CreatorBridgeDraft | null>(null);
  const [ready, setReady] = React.useState(false);
  const [handoffError, setHandoffError] = React.useState<string | null>(null);

  React.useEffect(() => {
    let mounted = true;
    void consumeCreatorBridge('forge')
      .then((draft) => { if (mounted) setIncoming(draft); })
      .catch(() => { if (mounted) setHandoffError('Could not restore the Galaxy draft. Existing builds were not changed.'); })
      .finally(() => { if (mounted) setReady(true); });
    return () => { mounted = false; };
  }, []);

  const openGalaxy = React.useCallback((draft: QuestionnaireState) => {
    try {
      void storeCreatorBridge(handoffFromForge(draft))
        .then(() => router.push('/galaxy' as any))
        .catch(() => setHandoffError('Could not save the GameForge draft. Navigation cancelled to preserve your work.'));
    } catch {
      setHandoffError('Invalid GameForge draft; nothing was transferred.');
    }
  }, [router]);

  return (
    <SafeAreaView style={st.root}>
      {handoffError ? <Text accessibilityRole="alert" style={{ color: C.amber }}>{handoffError}</Text> : null}
      {ready ? (
        <ForgeCockpitScreen
          initialTab={parseTabParam(params.tab)}
          initialQuestionnaire={incoming ? forgeStateFromHandoff(incoming) : null}
          onOpenGalaxyStudio={openGalaxy}
        />
      ) : null}
    </SafeAreaView>
  );
}

const st = StyleSheet.create({ root: { flex: 1, backgroundColor: C.bg } });
