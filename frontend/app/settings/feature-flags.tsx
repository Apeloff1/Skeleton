/**
 * /settings/feature-flags — runtime toggle UI for the FEATURE_FLAGS registry.
 *
 *   • Live category grouping (Experimental · Telemetry · Safety · Developer).
 *   • Free-text search across label / desc / key.
 *   • "MODIFIED" badge on any flag deviating from its default.
 *   • Reset-all + per-flag reset via long-press action sheet.
 *   • Toast feedback on every toggle for fingertip confidence.
 *
 * Toggling writes through to AsyncStorage and broadcasts to every
 * useFeatureFlag(key) subscriber so other screens react immediately.
 */
import { NATIVE_DRIVER } from '../../src/utils/platformStyles';
import React, { useEffect, useMemo, useState, useCallback } from 'react';
import {
  View, Text, ScrollView, Switch, StyleSheet, SafeAreaView,
  TouchableOpacity, TextInput, Pressable, LayoutAnimation,
  Platform, UIManager, Animated, Easing,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import {
  FEATURE_FLAGS, FlagSpec, FlagCategory,
  getFeatureFlag, setFeatureFlag, loadFeatureFlags,
  getModifiedFlagKeys, resetAllFlags, resetFeatureFlag,
} from '../../utils/featureFlags';
import { withScreenGuard } from '../../components/withScreenGuard';
import { toast } from '../../components/Toast';
import { actionSheet } from '../../components/ActionSheet';
import * as haptics from '../../utils/haptics';

// LayoutAnimation needs an opt-in on Android.
if (Platform.OS === 'android' && UIManager.setLayoutAnimationEnabledExperimental) {
  UIManager.setLayoutAnimationEnabledExperimental(true);
}

const CATEGORY_ORDER: FlagCategory[] = ['Experimental', 'Telemetry', 'Safety', 'Developer'];
const CATEGORY_META: Record<FlagCategory, { icon: keyof typeof Ionicons.glyphMap; tint: string; blurb: string }> = {
  Experimental: { icon: 'flask',         tint: '#a78bfa', blurb: 'Preview features that may change' },
  Telemetry:    { icon: 'pulse',         tint: '#3B82F6', blurb: 'Logging & performance traces' },
  Safety:       { icon: 'shield-half',   tint: '#fbbf24', blurb: 'Crash recovery & auto-heal' },
  Developer:    { icon: 'construct',     tint: '#10b981', blurb: 'Debug tools & audits' },
};

/** Tiny animated pill that fades+lifts in on mount. Used for "MODIFIED" badges
 *  so the change is visually confirmed when a user toggles a flag. */
function ModifiedBadge() {
  const op = React.useRef(new Animated.Value(0)).current;
  const ty = React.useRef(new Animated.Value(-4)).current;
  useEffect(() => {
    if (haptics.isReduceMotionOn()) { op.setValue(1); ty.setValue(0); return; }
    Animated.parallel([
      Animated.timing(op, { toValue: 1, duration: 220, easing: Easing.out(Easing.quad), useNativeDriver: NATIVE_DRIVER }),
      Animated.timing(ty, { toValue: 0, duration: 220, easing: Easing.out(Easing.quad), useNativeDriver: NATIVE_DRIVER }),
    ]).start();
  }, [op, ty]);
  return (
    <Animated.View style={[styles.modBadge, { opacity: op, transform: [{ translateY: ty }] }]}>
      <Text style={styles.modBadgeTxt}>MODIFIED</Text>
    </Animated.View>
  );
}

function FeatureFlagsScreen() {
  const router = useRouter();
  // Bump on every flag change to force re-render of the synchronous getFeatureFlag reads.
  const [bump, force] = useState(0);
  const [ready, setReady] = useState(false);
  const [query, setQuery] = useState('');
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());

  useEffect(() => {
    loadFeatureFlags().then(() => { setReady(true); force(n => n + 1); });
  }, []);

  /** Group every visible flag by its declared category. */
  const grouped = useMemo(() => {
    const q = query.trim().toLowerCase();
    const visible = FEATURE_FLAGS.filter(f => f.visible !== false);
    const out: Record<FlagCategory, FlagSpec[]> = {
      Experimental: [], Telemetry: [], Safety: [], Developer: [],
    };
    for (const f of visible) {
      if (q && !(
        f.label.toLowerCase().includes(q) ||
        f.key.toLowerCase().includes(q) ||
        (f.desc || '').toLowerCase().includes(q)
      )) continue;
      const cat = (f.category as FlagCategory) || 'Experimental';
      out[cat].push(f);
    }
    return out;
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query, bump]);

  const totalVisible = useMemo(
    () => FEATURE_FLAGS.filter(f => f.visible !== false).length,
    [],
  );
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const modifiedKeys = useMemo(() => getModifiedFlagKeys(), [bump, ready]);

  const onToggle = useCallback(async (f: FlagSpec, v: boolean) => {
    haptics.tap();
    await setFeatureFlag(f.key, v);
    force(n => n + 1);
    const restored = v === f.default;
    if (restored) {
      toast.info(`${f.label} reset to default`);
    } else if (v) {
      toast.success(`${f.label} enabled`);
    } else {
      toast.warn(`${f.label} disabled`);
    }
  }, []);

  const onRowLongPress = useCallback((f: FlagSpec) => {
    const current = getFeatureFlag(f.key);
    const isModified = current !== f.default;
    actionSheet.show({
      title: f.label,
      message: `${f.key} · default = ${f.default ? 'on' : 'off'} · current = ${current ? 'on' : 'off'}`,
      options: [
        {
          label: current ? 'Disable' : 'Enable',
          kind: 'primary',
          onPress: () => onToggle(f, !current),
        },
        ...(isModified ? [{
          label: `Reset to default (${f.default ? 'on' : 'off'})`,
          onPress: async () => {
            await resetFeatureFlag(f.key);
            force(n => n + 1);
            toast.success(`${f.label} reset`);
          },
        }] : []),
        { label: 'Cancel', kind: 'cancel' as const },
      ],
    });
  }, [onToggle]);

  const onResetAll = useCallback(() => {
    if (modifiedKeys.length === 0) {
      toast.info('All flags are already at their defaults');
      return;
    }
    actionSheet.show({
      title: 'Reset all feature flags?',
      message: `${modifiedKeys.length} flag${modifiedKeys.length === 1 ? '' : 's'} will revert to their declared defaults.`,
      options: [
        {
          label: `Reset ${modifiedKeys.length} flag${modifiedKeys.length === 1 ? '' : 's'}`,
          kind: 'destructive',
          onPress: async () => {
            await resetAllFlags();
            force(n => n + 1);
            toast.success('All flags reset to defaults');
          },
        },
        { label: 'Cancel', kind: 'cancel' },
      ],
    });
  }, [modifiedKeys.length]);

  const toggleCollapse = useCallback((cat: string) => {
    haptics.tap();
    // Smooth height crossfade when expanding/collapsing the category.
    if (!haptics.isReduceMotionOn()) {
      LayoutAnimation.configureNext(
        LayoutAnimation.create(220, LayoutAnimation.Types.easeInEaseOut, LayoutAnimation.Properties.opacity),
      );
    }
    setCollapsed(prev => {
      const next = new Set(prev);
      if (next.has(cat)) next.delete(cat); else next.add(cat);
      return next;
    });
  }, []);

  return (
    <SafeAreaView style={styles.safe}>
      {/* Header */}
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.canGoBack() ? router.back() : router.replace('/settings')} hitSlop={12}>
          <Ionicons name="chevron-back" size={26} color="#e2e8f0" />
        </TouchableOpacity>
        <View style={{ flex: 1 }}>
          <Text style={styles.badge}>Settings</Text>
          <Text style={styles.title}>Feature Flags</Text>
          <Text style={styles.sub}>
            {totalVisible} flag{totalVisible === 1 ? '' : 's'}
            {modifiedKeys.length > 0 ? ` · ${modifiedKeys.length} modified` : ''}
            {' '}· toggles apply instantly app-wide
          </Text>
        </View>
        <TouchableOpacity
          onPress={onResetAll}
          hitSlop={10}
          style={[styles.resetBtn, modifiedKeys.length === 0 && { opacity: 0.4 }]}
          accessibilityLabel="Reset all feature flags to defaults"
          testID="feature-flags-reset-all"
        >
          <Ionicons name="refresh" size={14} color="#fbbf24" />
          <Text style={styles.resetTxt}>Reset</Text>
        </TouchableOpacity>
      </View>

      <ScrollView style={styles.scroll} contentContainerStyle={{ padding: 16, paddingBottom: 60 }}>
        {!ready ? (
          <Text style={styles.dim}>Loading flags…</Text>
        ) : (
          CATEGORY_ORDER.map(cat => {
            const flags = grouped[cat] || [];
            if (flags.length === 0) return null;
            const meta = CATEGORY_META[cat];
            const isCollapsed = collapsed.has(cat);
            const catModifiedCount = flags.filter(f => getFeatureFlag(f.key) !== f.default).length;

            return (
              <View key={cat} style={styles.section}>
                <Pressable
                  onPress={() => toggleCollapse(cat)}
                  style={styles.sectionHead}
                  accessibilityLabel={`Toggle ${cat} category`}
                >
                  <View style={[styles.catBadge, { backgroundColor: meta.tint + '22', borderColor: meta.tint }]}>
                    <Ionicons name={meta.icon} size={14} color={meta.tint} />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.catTitle}>{cat}</Text>
                    <Text style={styles.catBlurb}>
                      {meta.blurb} · {flags.length} flag{flags.length === 1 ? '' : 's'}
                      {catModifiedCount > 0 ? ` · ${catModifiedCount} modified` : ''}
                    </Text>
                  </View>
                  <Ionicons
                    name={isCollapsed ? 'chevron-down' : 'chevron-up'}
                    size={18}
                    color="#64748b"
                  />
                </Pressable>

                {!isCollapsed && flags.map(f => {
                  const value = getFeatureFlag(f.key);
                  const isModified = value !== f.default;
                  return (
                    <Pressable
                      key={f.key}
                      style={[styles.row, isModified && styles.rowModified]}
                      onLongPress={() => onRowLongPress(f)}
                      delayLongPress={350}
                      accessibilityLabel={`Feature flag ${f.label}`}
                      testID={`feature-flag-${f.key}`}
                    >
                      <View style={{ flex: 1, minWidth: 0, paddingRight: 12 }}>
                        <View style={styles.labelRow}>
                          <Text style={styles.label} numberOfLines={1}>{f.label}</Text>
                          {isModified && <ModifiedBadge />}
                        </View>
                        <Text style={styles.key} numberOfLines={1}>{f.key}</Text>
                        {f.desc ? <Text style={styles.desc}>{f.desc}</Text> : null}
                      </View>
                      <Switch
                        value={value}
                        onValueChange={(v) => onToggle(f, v)}
                        thumbColor={value ? '#a78bfa' : '#475569'}
                        trackColor={{ true: '#2E1B5B', false: '#262626' }}
                        testID={`feature-flag-switch-${f.key}`}
                      />
                    </Pressable>
                  );
                })}
              </View>
            );
          })
        )}

        {/* Search-empty-state */}
        {ready && query && CATEGORY_ORDER.every(c => (grouped[c] || []).length === 0) && (
          <View style={styles.emptyWrap}>
            <Ionicons name="search-outline" size={28} color="#475569" />
            <Text style={styles.dim}>No flags match &quot;{query}&quot;</Text>
            <TouchableOpacity onPress={() => setQuery('')} style={styles.clearBtn}>
              <Text style={styles.clearTxt}>Clear search</Text>
            </TouchableOpacity>
          </View>
        )}

        <Text style={styles.foot}>
          Flags persist in AsyncStorage under @feature/&lt;key&gt;.
          {'\n'}Long-press a row for per-flag actions. Wipe via /safe-mode → {'"'}Wipe all{'"'} to reset everything.
        </Text>
      </ScrollView>

      <View style={styles.searchWrap}>
        <Ionicons name="search" size={16} color="#64748b" />
        <TextInput
          style={styles.searchInput}
          value={query}
          onChangeText={setQuery}
          placeholder="Search flags…"
          placeholderTextColor="#475569"
          autoCorrect={false}
          autoCapitalize="none"
          testID="feature-flags-search"
        />
        {query.length > 0 && (
          <TouchableOpacity onPress={() => setQuery('')} hitSlop={10}>
            <Ionicons name="close-circle" size={16} color="#475569" />
          </TouchableOpacity>
        )}
      </View>
    </SafeAreaView>
  );
}

export default withScreenGuard(FeatureFlagsScreen, 'FeatureFlagsRoute');

const styles = StyleSheet.create({
  safe:    { flex: 1, backgroundColor: '#0A0A0A' },
  header:  { flexDirection: 'row', alignItems: 'center', gap: 12, paddingHorizontal: 16, paddingTop: 12, paddingBottom: 14, borderBottomWidth: 1, borderBottomColor: '#262626' },
  badge:   { color: '#a78bfa', fontSize: 10, fontWeight: '800', letterSpacing: 1.4, textTransform: 'uppercase' },
  title:   { fontSize: 20, fontWeight: '800', color: '#f8fafc' },
  sub:     { fontSize: 11, color: '#94a3b8', marginTop: 2 },
  resetBtn:{ flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: '#fbbf2422', paddingHorizontal: 10, paddingVertical: 6, borderRadius: 999, borderWidth: 1, borderColor: '#fbbf2444' },
  resetTxt:{ color: '#fbbf24', fontSize: 11, fontWeight: '800', letterSpacing: 0.4 },

  searchWrap: { flexDirection: 'row', alignItems: 'center', gap: 8, marginHorizontal: 16, marginVertical: 12, paddingHorizontal: 12, height: 38, borderRadius: 10, backgroundColor: '#141414', borderWidth: 1, borderColor: '#262626' },
  searchInput:{ flex: 1, color: '#e2e8f0', fontSize: 13 },

  scroll:  { flex: 1 },

  section: { marginTop: 16, marginBottom: 4 },
  sectionHead: { flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 8, paddingHorizontal: 4 },
  catBadge:{ width: 26, height: 26, borderRadius: 8, alignItems: 'center', justifyContent: 'center', borderWidth: 1 },
  catTitle:{ color: '#f8fafc', fontSize: 14, fontWeight: '800', letterSpacing: 0.3 },
  catBlurb:{ color: '#64748b', fontSize: 10, marginTop: 1 },

  row:     { flexDirection: 'row', alignItems: 'center', backgroundColor: '#141414', borderRadius: 12, padding: 14, marginBottom: 10, borderWidth: 1, borderColor: '#262626' },
  rowModified: { borderColor: '#a78bfa55', backgroundColor: '#1e1b4b22' },
  labelRow:{ flexDirection: 'row', alignItems: 'center', gap: 8 },
  label:   { color: '#e2e8f0', fontSize: 14, fontWeight: '700', flexShrink: 1 },
  modBadge:{ backgroundColor: '#a78bfa22', borderColor: '#a78bfa66', borderWidth: 1, paddingHorizontal: 6, paddingVertical: 2, borderRadius: 6 },
  modBadgeTxt:{ color: '#a78bfa', fontSize: 8.5, fontWeight: '900', letterSpacing: 0.6 },
  key:     { color: '#64748b', fontSize: 10.5, fontFamily: 'monospace', marginTop: 2 },
  desc:    { color: '#94a3b8', fontSize: 12, marginTop: 6, lineHeight: 17 },

  dim:     { color: '#64748b', fontSize: 13, textAlign: 'center', paddingTop: 24 },
  emptyWrap:{ alignItems: 'center', gap: 10, paddingTop: 24, paddingBottom: 8 },
  clearBtn:{ paddingHorizontal: 14, paddingVertical: 8, backgroundColor: '#262626', borderRadius: 8 },
  clearTxt:{ color: '#a78bfa', fontSize: 12, fontWeight: '700' },

  foot:    { color: '#475569', fontSize: 11, marginTop: 20, lineHeight: 16, fontStyle: 'italic' },
});
