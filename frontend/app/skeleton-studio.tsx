/**
 * /skeleton-studio — first-run, account, projects, build status, and settings
 * for the Skeleton forge. The questionnaire and forge run stay on the
 * existing cockpit owners.
 */
import React from 'react';
import { SafeAreaView, StyleSheet } from 'react-native';
import { useRouter } from 'expo-router';
import FoundationScreen from '../src/skeletonForge/components/foundation/FoundationScreen';
import { C } from '../src/skeletonForge/components/theme';

export default function SkeletonStudioRoute() {
  const router = useRouter();
  return (
    <SafeAreaView style={st.root}>
      <FoundationScreen
        onSetup={() => router.push('/setup' as never)}
        onOpenCockpit={() => router.push('/skeleton-forge' as never)}
      />
    </SafeAreaView>
  );
}

const st = StyleSheet.create({ root: { flex: 1, backgroundColor: C.bg } });
