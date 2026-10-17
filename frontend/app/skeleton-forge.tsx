/**
 * /skeleton-forge — Skeleton GameForge cockpit: guided questionnaire,
 * live compose graph, build plan, forge-run panel, era viewer and console.
 * Deep link a tab with ?tab=build|compose|plan|run|eras|console.
 */
import React from 'react';
import { SafeAreaView, StyleSheet } from 'react-native';
import { useLocalSearchParams } from 'expo-router';
import ForgeCockpitScreen from '../src/skeletonForge/components/ForgeCockpitScreen';
import { parseTabParam } from '../src/skeletonForge/cockpitScreen';
import { C } from '../src/skeletonForge/components/theme';

export default function SkeletonForgeRoute() {
  const params = useLocalSearchParams<{ tab?: string }>();
  return (
    <SafeAreaView style={st.root}>
      <ForgeCockpitScreen initialTab={parseTabParam(params.tab)} />
    </SafeAreaView>
  );
}

const st = StyleSheet.create({ root: { flex: 1, backgroundColor: C.bg } });
