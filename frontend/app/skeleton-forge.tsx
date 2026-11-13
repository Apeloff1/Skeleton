/**
 * /skeleton-forge — Skeleton GameForge cockpit: guided questionnaire,
 * live compose graph, build plan, forge-run panel, era viewer and console.
 * Deep link a tab with ?tab=build|compose|plan|run|eras|console.
 */
import React from 'react';
import { SafeAreaView, StyleSheet } from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import ForgeCockpitScreen from '../src/skeletonForge/components/ForgeCockpitScreen';
import { parseTabParam } from '../src/skeletonForge/cockpitScreen';
import { C } from '../src/skeletonForge/components/theme';

export default function SkeletonForgeRoute() {
  const params = useLocalSearchParams<{ tab?: string; handoff?: string }>();
  const router = useRouter();
  return (
    <SafeAreaView style={st.root}>
      <ForgeCockpitScreen
        initialTab={parseTabParam(params.tab)}
        galaxyHandoffId={typeof params.handoff === 'string' ? params.handoff : null}
        onOpenGalaxyStudio={() => router.push('/galaxy' as any)}
      />
    </SafeAreaView>
  );
}

const st = StyleSheet.create({ root: { flex: 1, backgroundColor: C.bg } });
