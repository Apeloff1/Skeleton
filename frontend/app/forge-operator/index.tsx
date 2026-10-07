/**
 * /forge-operator — Pack F forge operator hub.
 * Deep link a tab with ?tab=compose|plans|walk|eras|beats|report|recovery.
 */
import React from 'react';
import { SafeAreaView, StyleSheet } from 'react-native';
import { useLocalSearchParams } from 'expo-router';
import OperatorScreen from '../../src/forgeOperator/components/OperatorScreen';
import { parseOperatorTab } from '../../src/forgeOperator/operatorTabs';
import { C } from '../../src/skeletonForge/components/theme';

export default function ForgeOperatorRoute() {
  const params = useLocalSearchParams<{ tab?: string }>();
  return (
    <SafeAreaView style={st.root}>
      <OperatorScreen initialTab={parseOperatorTab(params.tab)} />
    </SafeAreaView>
  );
}

const st = StyleSheet.create({ root: { flex: 1, backgroundColor: C.bg } });
