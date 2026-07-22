/**
 * Certificate — printable / shareable diploma page for completed classes.
 * Reads ?class=ID&title=Title from URL params.
 */
import { useRef } from 'react';
import { View, Text, StyleSheet, ScrollView, TouchableOpacity, Share, Platform } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { LinearGradient } from 'expo-linear-gradient';
import { useUser } from '../utils/userStore';
import { openModalFromRoute } from '../utils/openModalFromRoute';
import theme from '../theme/tokens';
import { Screen, AppHeader } from '../components/ui';
import { toast } from '../components/Toast';

export default function CertificateScreen() {
  const router = useRouter();
  const params = useLocalSearchParams<{ class?: string; title?: string }>();
  const user = useUser();
  const today = new Date().toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' });
  const certIdRef = useRef(`CERT-${(params.class || 'class').toString().toUpperCase().slice(0, 4)}-${Date.now().toString(36).toUpperCase()}`);
  const certId = certIdRef.current;

  const shareCertificate = async () => {
    try {
      const message =
        `🎓 Certificate of Completion\n\n` +
        `Awarded to: ${user.profile.name || 'Explorer'}\n` +
        `Course: ${params.title || params.class || 'Class'}\n` +
        `Date: ${today}\n` +
        `Certificate ID: ${certId}\n\n` +
        `Earned through 15 weeks of original instruction, code exercises, ` +
        `assessments, and reference material at the Academy.`;
      await Share.share({
        message,
        title: 'My Certificate',
      });
    } catch (e: any) {
      if (Platform.OS === 'web') {
        // Web Share API often unavailable in iframes — fall back to clipboard.
        try {
          await navigator.clipboard.writeText(
            `Certificate ID: ${certId} · ${user.profile.name || 'Explorer'} · ${params.title || params.class}`,
          );
          toast.success('Certificate details copied');
        } catch {
          toast.warn('Share unavailable — screenshot to save');
        }
      } else {
        toast.error(`Share failed: ${e.message || 'unknown'}`);
      }
    }
  };

  return (
    <Screen edges={['top']}>
      <LinearGradient
        colors={['#F5C45122', '#92400E22', 'transparent'] as any}
        start={{ x: 0.2, y: 0 }}
        end={{ x: 0.9, y: 0.6 }}
        style={[{ position: 'absolute', top: 0, left: 0, right: 0, height: 280 }, { pointerEvents: 'none' }]}
      />
      <AppHeader title="Certificate" onBack={() => router.back()} />

      <ScrollView contentContainerStyle={{ padding: 16, paddingBottom: 80, alignItems: 'center' }}>
        <View style={s.cert}>
          <View style={s.cornerTL} />
          <View style={s.cornerTR} />
          <View style={s.cornerBL} />
          <View style={s.cornerBR} />
          <View style={s.seal}>
            <Ionicons name="ribbon" size={36} color="#F5C451" />
          </View>
          <Text style={s.heading}>CERTIFICATE</Text>
          <Text style={s.subhead}>OF COMPLETION</Text>
          <View style={s.divider} />
          <Text style={s.presented}>presented to</Text>
          <Text style={s.name}>{user.profile.name || 'Explorer'}</Text>
          <View style={s.divider} />
          <Text style={s.body}>
            for successfully completing the graduate-level study programme
          </Text>
          <Text style={s.classTitle}>{params.title || params.class || 'Class'}</Text>
          <Text style={s.body}>
            comprising 15 weeks of original instruction, code exercises,
            assessments, and reference material.
          </Text>
          <View style={s.divider} />
          <View style={s.metaRow}>
            <View style={s.metaCol}>
              <Text style={s.metaLabel}>Awarded</Text>
              <Text style={s.metaVal}>{today}</Text>
            </View>
            <View style={s.metaCol}>
              <Text style={s.metaLabel}>Certificate ID</Text>
              <Text style={s.metaVal}>{certId}</Text>
            </View>
            <View style={s.metaCol}>
              <Text style={s.metaLabel}>Signed</Text>
              <Text style={s.metaSig}>The Academy</Text>
            </View>
          </View>
        </View>
        <View style={s.actions}>
          <TouchableOpacity onPress={shareCertificate} style={[s.actionBtn, { backgroundColor: '#F5C451' }]} activeOpacity={0.85}>
            <Ionicons name="share-social" size={16} color="#fff" />
            <Text style={s.actionText}>Share Certificate</Text>
          </TouchableOpacity>
          <TouchableOpacity onPress={() => openModalFromRoute(router, 'myProgress')} style={[s.actionBtn, { backgroundColor: '#10B981' }]} activeOpacity={0.85}>
            <Ionicons name="analytics" size={16} color="#fff" />
            <Text style={s.actionText}>View all certificates</Text>
          </TouchableOpacity>
        </View>
        <Text style={s.hint}>Take a screenshot or use Share to save / send this certificate.</Text>
      </ScrollView>
    </Screen>
  );
}

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: theme.colors.bg },
  header: { flexDirection: 'row', alignItems: 'center', padding: 14, backgroundColor: theme.colors.bgElevated, borderBottomWidth: 1, borderBottomColor: theme.colors.border },
  hdrBtn: { width: 44, height: 44, justifyContent: 'center', alignItems: 'center' },
  hdrTitle: { flex: 1, textAlign: 'center', fontSize: 17, fontWeight: '700', color: theme.colors.text },
  cert: { backgroundColor: '#FAF7EE', borderRadius: 6, padding: 32, alignItems: 'center', width: '100%', maxWidth: 500, borderWidth: 8, borderColor: theme.colors.accentGold, position: 'relative', ...theme.elevation.xl },
  cornerTL: { position: 'absolute', top: 8, left: 8, width: 30, height: 30, borderTopWidth: 3, borderLeftWidth: 3, borderColor: '#92400E' },
  cornerTR: { position: 'absolute', top: 8, right: 8, width: 30, height: 30, borderTopWidth: 3, borderRightWidth: 3, borderColor: '#92400E' },
  cornerBL: { position: 'absolute', bottom: 8, left: 8, width: 30, height: 30, borderBottomWidth: 3, borderLeftWidth: 3, borderColor: '#92400E' },
  cornerBR: { position: 'absolute', bottom: 8, right: 8, width: 30, height: 30, borderBottomWidth: 3, borderRightWidth: 3, borderColor: '#92400E' },
  seal: { marginBottom: 14 },
  heading: { color: '#92400E', fontSize: 30, fontWeight: '800', letterSpacing: 6 },
  subhead: { color: '#92400E', fontSize: 12, letterSpacing: 4, marginTop: 2 },
  divider: { width: 60, height: 1, backgroundColor: '#92400E', marginVertical: 14 },
  presented: { color: '#78350F', fontSize: 12, fontStyle: 'italic' },
  name: { color: '#92400E', fontSize: 26, fontWeight: '800', marginTop: 8, letterSpacing: -0.5 },
  body: { color: '#78350F', fontSize: 11, marginTop: 6, textAlign: 'center', lineHeight: 18 },
  classTitle: { color: '#92400E', fontSize: 18, fontWeight: '800', marginTop: 6, textAlign: 'center', letterSpacing: -0.3 },
  metaRow: { flexDirection: 'row', justifyContent: 'space-between', width: '100%', marginTop: 8 },
  metaCol: { alignItems: 'center', flex: 1 },
  metaLabel: { color: '#78350F', fontSize: 8, textTransform: 'uppercase', letterSpacing: 1 },
  metaVal: { color: '#92400E', fontSize: 10, fontWeight: '700', marginTop: 2 },
  metaSig: { color: '#92400E', fontSize: 12, fontStyle: 'italic', marginTop: 2 },
  hint: { color: theme.colors.textDim, fontSize: 11, fontStyle: 'italic', marginTop: 20, textAlign: 'center' },
  actions: { flexDirection: 'row', gap: 10, marginTop: 22, width: '100%', maxWidth: 500 },
  actionBtn: { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, paddingVertical: 12, borderRadius: 10 },
  actionText: { color: '#fff', fontWeight: '800', fontSize: 12 },
});
