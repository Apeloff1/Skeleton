import React from 'react';
import { SafeAreaView, ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { useRouter } from 'expo-router';
import StudioOfficePanel from '../src/features/Office/StudioOfficePanel';
import { colors } from '../src/features/Setup/AppSetupWorkspace.styles';

export default function OfficeRoute() {
  const router = useRouter();
  return (
    <SafeAreaView style={styles.safe}>
      <ScrollView contentContainerStyle={styles.page} keyboardShouldPersistTaps="handled">
        <View style={styles.row}>
          <Text style={styles.eyebrow}>SKELETON</Text>
          <TouchableOpacity accessibilityRole="button" onPress={() => router.push('/setup' as never)} style={styles.link}><Text style={styles.linkText}>Setup</Text></TouchableOpacity>
          <TouchableOpacity accessibilityRole="button" onPress={() => router.push('/product' as never)} style={styles.link}><Text style={styles.linkText}>Product</Text></TouchableOpacity>
        </View>
        <StudioOfficePanel variant="full" />
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  page: { padding: 20, gap: 16, width: '100%', maxWidth: 1120, alignSelf: 'center', paddingBottom: 48 },
  row: { flexDirection: 'row', flexWrap: 'wrap', gap: 12, alignItems: 'center' },
  eyebrow: { color: colors.accent, fontSize: 12, fontWeight: '700', letterSpacing: 2, flexGrow: 1 },
  link: { minHeight: 44, justifyContent: 'center', paddingHorizontal: 8 },
  linkText: { color: colors.accent, fontWeight: '700' },
});
