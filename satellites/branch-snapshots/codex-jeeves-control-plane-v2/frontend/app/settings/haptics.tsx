/**
 * /settings/haptics — Choose haptic feedback intensity (off / light / full).
 *
 *   Lives at /settings/haptics so it's deep-linkable from the menu's
 *   Settings group, and from any "haptics not landing" toast we'd add later.
 */
import { useEffect, useState } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, ScrollView } from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import theme from '../../theme/tokens';
import { Screen, AppHeader, SectionHeader } from '../../components/ui';
import { withScreenGuard } from '../../components/withScreenGuard';
import * as haptics from '../../utils/haptics';
import type { HapticsLevel } from '../../utils/haptics';
import { toast } from '../../components/Toast';

const OPTIONS: { key: HapticsLevel; title: string; desc: string; icon: keyof typeof Ionicons.glyphMap }[] = [
  { key: 'off',   title: 'Off',   desc: 'Silent. Use when in meetings or asleep.', icon: 'volume-mute-outline' },
  { key: 'light', title: 'Light', desc: 'Selection taps only — gentle nudges on buttons & toggles.', icon: 'leaf-outline' },
  { key: 'full',  title: 'Full',  desc: 'Tap + success + warn + error. The default rich set.',       icon: 'flash-outline' },
];

function HapticsSettings() {
  const router = useRouter();
  const [level, setLevel] = useState<HapticsLevel>(haptics.getHapticsLevel());

  // Re-read on mount (in case storage was hydrated after first render).
  useEffect(() => { setLevel(haptics.getHapticsLevel()); }, []);

  const choose = async (next: HapticsLevel) => {
    await haptics.setHapticsLevel(next);
    setLevel(next);
    if (next === 'off') {
      toast.info('Haptics off');
    } else if (next === 'light') {
      haptics.tap();
      toast.success('Light haptics enabled');
    } else {
      haptics.success();
      toast.success('Full haptics enabled');
    }
  };

  return (
    <Screen edges={['top']}>
      <AppHeader
        title="Haptics"
        subtitle="Choose feedback intensity"
        onBack={() => router.back()}
      />
      <ScrollView contentContainerStyle={s.scroll}>
        <SectionHeader label="Intensity" count={OPTIONS.length} />
        {OPTIONS.map((opt) => {
          const active = level === opt.key;
          return (
            <TouchableOpacity
              key={opt.key}
              onPress={() => choose(opt.key)}
              activeOpacity={0.9}
              style={[s.row, active && s.rowActive]}
              testID={`haptics-${opt.key}`}
            >
              <View style={[s.icon, active && { backgroundColor: theme.colors.primary + '22' }]}>
                <Ionicons name={opt.icon} size={18} color={active ? theme.colors.primary : theme.colors.textMuted} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={[s.title, active && { color: theme.colors.primary }]}>{opt.title}</Text>
                <Text style={s.desc}>{opt.desc}</Text>
              </View>
              {active ? (
                <Ionicons name="checkmark-circle" size={22} color={theme.colors.primary} />
              ) : (
                <Ionicons name="ellipse-outline" size={20} color={theme.colors.textDim} />
              )}
            </TouchableOpacity>
          );
        })}

        <Text style={s.note}>
          Stored per-device. Other features that use haptics (notes, menu chips, FAB,
          file save) will respect this immediately.
        </Text>

        {haptics.isReduceMotionOn() && (
          <View style={s.rmCard}>
            <Ionicons name="accessibility" size={16} color="#10b981" />
            <View style={{ flex: 1 }}>
              <Text style={s.rmTitle}>Reduce Motion is ON</Text>
              <Text style={s.rmSub}>
                The system accessibility setting is overriding your choice — all haptics
                are silenced until Reduce Motion is turned off in your device settings.
              </Text>
            </View>
          </View>
        )}
      </ScrollView>
    </Screen>
  );
}

export default withScreenGuard(HapticsSettings, 'SettingsHaptics');

const s = StyleSheet.create({
  scroll: { paddingHorizontal: 16, paddingVertical: 12 },
  row:    {
    flexDirection: 'row', alignItems: 'center', gap: 12,
    backgroundColor: theme.colors.surface,
    borderRadius: theme.radii.md,
    borderWidth: 1, borderColor: theme.colors.border,
    padding: 14, marginBottom: 10,
  },
  rowActive: {
    borderColor: theme.colors.primary + 'AA',
    backgroundColor: theme.colors.primary + '0A',
  },
  icon:  {
    width: 36, height: 36, borderRadius: 18,
    backgroundColor: theme.colors.bgSubtle,
    alignItems: 'center', justifyContent: 'center',
  },
  title: { color: theme.colors.text, fontSize: 15, fontWeight: '700' },
  desc:  { color: theme.colors.textDim, fontSize: 12, marginTop: 3, lineHeight: 16 },
  note:  { color: theme.colors.textDim, fontSize: 12, lineHeight: 17, marginTop: 14, paddingHorizontal: 4 },
  rmCard:{
    marginTop: 14, flexDirection: 'row', gap: 10,
    backgroundColor: '#10b9811a',
    borderColor: '#10b98155', borderWidth: 1,
    borderRadius: theme.radii.md,
    padding: 12,
  },
  rmTitle: { color: '#a7f3d0', fontSize: 13, fontWeight: '800', letterSpacing: 0.3 },
  rmSub:   { color: theme.colors.textDim, fontSize: 11, lineHeight: 15, marginTop: 4 },
});
