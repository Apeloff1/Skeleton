/**
 * /organism — lightweight preview of the factory spine using Galaxy tokens.
 */
import React from 'react';
import { View, StyleSheet, ScrollView, Text } from 'react-native';
import { OrganismPreviewPanel } from '../features/GalaxyStudioFactory/OrganismPreviewPanel';
import theme from '../theme/tokens';

export default function OrganismRoute() {
  return (
    <View style={styles.root} testID="organism-preview-route">
      <ScrollView contentContainerStyle={styles.pad}>
        <Text style={styles.title}>Organism</Text>
        <Text style={styles.sub}>Same Galaxy Studio surface. Factory features that were off-screen.</Text>
        <OrganismPreviewPanel />
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: theme.colors.bg },
  pad: { padding: 16, paddingTop: 28 },
  title: { color: theme.colors.text, fontSize: 22, fontWeight: '800', marginBottom: 4 },
  sub: { color: theme.colors.textMuted, fontSize: 13, marginBottom: 16 },
});
