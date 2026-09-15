import { useState } from 'react';
import { View, Text, StyleSheet, ScrollView, SafeAreaView, TouchableOpacity } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useSettings, getJeevesSystemPrefix, JEEVES_DNA_GROUPS } from '../../state/settingsStore';
import { Section, SwitchRow, SliderRow, TextRow, ChoiceRow, ActionButton } from '../../features/Settings/components';
import DnaCockpit from '../../features/Settings/DnaCockpit';
import { actionSheet } from '../../components/ActionSheet';
import { toast } from '../../components/Toast';

export default function JeevesSettings() {
  const router = useRouter();
  const j = useSettings(s => s.jeeves);
  const set = useSettings(s => s.setJeeves);
  const add = useSettings(s => s.addBulkOrder);
  const remove = useSettings(s => s.removeBulkOrder);
  const clear = useSettings(s => s.clearBulkOrders);
  const resetJ = useSettings(s => s.resetJeeves);
  const setJeevesDna = useSettings(s => s.setJeevesDna);
  const resetJeevesDna = useSettings(s => s.resetJeevesDna);
  const resetJeevesDnaGroup = useSettings(s => s.resetJeevesDnaGroup);
  const [newOrder, setNewOrder] = useState('');
  const [previewOpen, setPreviewOpen] = useState(false);

  const personas = [
    { value: 'precise', label: 'Precise' },
    { value: 'creative', label: 'Creative' },
    { value: 'educator', label: 'Educator' },
    { value: 'debugger', label: 'Debugger' },
    { value: 'strict', label: 'Strict' },
  ];

  const presets = [
    { label: 'Production-ready', rules: 'Full error handling, typed APIs, unit tests, no TODOs. Always log to observability.' },
    { label: 'Quick-prototype', rules: 'Skip tests. Optimize for iteration speed. Hard-code where sensible.' },
    { label: 'Security-first', rules: 'Validate all input. Principle of least privilege. Dependency SBOMs. No secrets in code.' },
    { label: 'Accessibility', rules: 'WCAG 2.2 AA minimum. Screen-reader labels on every control. Captions on media.' },
  ];

  return (
    <SafeAreaView style={s.container}>
      <View style={s.header}>
        <TouchableOpacity onPress={() => router.back()} style={s.headerBtn}>
          <Ionicons name="arrow-back" size={24} color="#F8FAFC" />
        </TouchableOpacity>
        <Text style={s.headerTitle}>Jeeves Settings</Text>
        <TouchableOpacity onPress={() => {
          actionSheet.show({
            title: 'Reset Jeeves?',
            message: 'Reset Jeeves settings to defaults?',
            options: [
              { label: 'Cancel', kind: 'cancel' },
              { label: 'Reset', kind: 'destructive', onPress: () => { resetJ(); toast.warn('Jeeves reset'); } },
            ],
          });
        }} style={s.headerBtn}>
          <Ionicons name="refresh" size={22} color="#EF4444" />
        </TouchableOpacity>
      </View>
      <ScrollView contentContainerStyle={{ paddingBottom: 40 }}>

        <Section title="3 Directives (Blurbs)" hint="These three blurbs are prepended to every Jeeves request when enforce is on. Use them to steer the agent or lock in constraints.">
          <TextRow label="Vision" hint="What's the big picture / goal?" value={j.blurbVision} onChange={v => set({ blurbVision: v })} multiline numberOfLines={3}
            placeholder="Build a bulletproof, teaching-oriented code platform..." />
          <TextRow label="Style" hint="Code style / approach / tone" value={j.blurbStyle} onChange={v => set({ blurbStyle: v })} multiline numberOfLines={3}
            placeholder="Functional-first. Typed. Small pure fns. No classes unless needed..." />
          <TextRow label="Rules (must obey)" hint="Hard constraints — agent refuses to break these" value={j.blurbRules} onChange={v => set({ blurbRules: v })} multiline numberOfLines={3}
            placeholder="Never leak secrets. Always error-handle. Generate tests. Never mock real APIs..." />
          <SwitchRow icon="shield-checkmark" color="#8B5CF6" label="Enforce on every request" hint="Auto-prepends all 3 blurbs to every Jeeves call"
            value={j.enforceOnEveryRequest} onValueChange={v => set({ enforceOnEveryRequest: v })} />
        </Section>

        <Section title="Quick presets — tap to append to Rules">
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, padding: 12 }}>
            {presets.map(p => (
              <TouchableOpacity key={p.label} style={s.presetChip} onPress={() => set({ blurbRules: j.blurbRules ? `${j.blurbRules} ${p.rules}` : p.rules })}>
                <Text style={s.presetChipText}>{p.label}</Text>
              </TouchableOpacity>
            ))}
          </View>
        </Section>

        <Section title="Bulk Orders Queue" hint="Queued directives that Jeeves must execute in order. Each request consumes the full queue.">
          <View style={{ padding: 12 }}>
            {j.bulkOrders.length === 0 ? (
              <Text style={{ color: '#64748B', fontSize: 12, fontStyle: 'italic', paddingVertical: 8 }}>No orders queued.</Text>
            ) : (
              j.bulkOrders.map((o, i) => (
                <View key={i} style={s.orderItem}>
                  <Text style={s.orderIndex}>{i + 1}</Text>
                  <Text style={s.orderText} numberOfLines={3}>{o}</Text>
                  <TouchableOpacity onPress={() => remove(i)} style={{ padding: 6 }}>
                    <Ionicons name="close-circle" size={20} color="#EF4444" />
                  </TouchableOpacity>
                </View>
              ))
            )}
            <TextRow label="Add order" value={newOrder} onChange={setNewOrder} placeholder="e.g. Refactor all `any` types to proper interfaces" multiline numberOfLines={2} />
            <View style={{ flexDirection: 'row', gap: 10, marginTop: 10 }}>
              <View style={{ flex: 1 }}>
                <ActionButton icon="add" label="Add to queue" color="#8B5CF6" onPress={() => { if (newOrder.trim()) { add(newOrder.trim()); setNewOrder(''); } }} />
              </View>
              {j.bulkOrders.length > 0 && (
                <View style={{ flex: 1 }}>
                  <ActionButton icon="trash" label="Clear all" kind="danger" onPress={() => {
                    actionSheet.show({
                      title: 'Clear bulk orders?',
                      message: `Clear all ${j.bulkOrders.length} orders?`,
                      options: [
                        { label: 'Cancel', kind: 'cancel' },
                        { label: 'Clear', kind: 'destructive', onPress: () => { clear(); toast.warn('Bulk orders cleared'); } },
                      ],
                    });
                  }} />
                </View>
              )}
            </View>
          </View>
        </Section>

        <Section title="Persona & tone">
          <ChoiceRow label="Agent persona" hint="Steers Jeeves's tone and depth" color="#8B5CF6"
            value={j.agentPersona} onChange={v => set({ agentPersona: v })} options={personas} />
          <SliderRow color="#8B5CF6" label="Creativity" hint="Temperature 0.0-1.0 — lower = more deterministic"
            value={j.creativity} onChange={v => set({ creativity: v })} min={0} max={1} step={0.05} />
          <SliderRow color="#8B5CF6" label="Verbosity" hint="1=terse answer only → 5=long-form with rationale"
            value={j.verbosity} onChange={v => set({ verbosity: Math.round(v) })} min={1} max={5} step={1} valueLabel={`${j.verbosity}/5`} />
        </Section>

        {/* 100-slider Jeeves Mastery cockpit — collapsible to keep render cheap. */}
        <DnaCockpit
          title="Jeeves Mastery"
          groups={JEEVES_DNA_GROUPS}
          dna={j.masteryDna}
          onChange={setJeevesDna}
          onResetGroup={resetJeevesDnaGroup}
          onResetAll={resetJeevesDna}
          accent="#8B5CF6"
          previewEndpoint="/api/dna/preview/jeeves"
        />

        <View style={{ padding: 16 }}>
          <ActionButton icon={previewOpen ? 'eye-off' : 'eye'} label={previewOpen ? 'Hide preview' : 'Preview what Jeeves will receive'} color="#8B5CF6" onPress={() => setPreviewOpen(v => !v)} />
          {previewOpen && (
            <View style={s.preview}>
              <Text style={s.previewText} selectable>
                {getJeevesSystemPrefix() || '(empty — toggle Enforce or fill any blurb)'}
              </Text>
            </View>
          )}
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#141414' },
  header: { flexDirection: 'row', alignItems: 'center', padding: 12, backgroundColor: '#262626', borderBottomWidth: 1, borderBottomColor: '#404040' },
  headerBtn: { width: 44, height: 44, justifyContent: 'center', alignItems: 'center' },
  headerTitle: { flex: 1, textAlign: 'center', fontSize: 18, fontWeight: '700', color: '#F8FAFC' },
  presetChip: { backgroundColor: '#8B5CF622', borderColor: '#8B5CF666', borderWidth: 1, paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8 },
  presetChipText: { color: '#A78BFA', fontSize: 11, fontWeight: '700' },
  orderItem: { flexDirection: 'row', alignItems: 'center', backgroundColor: '#0B1222', padding: 10, borderRadius: 8, marginBottom: 6, borderWidth: 1, borderColor: '#262626' },
  orderIndex: { color: '#8B5CF6', fontWeight: '800', width: 22, textAlign: 'center' },
  orderText: { flex: 1, color: '#F8FAFC', fontSize: 12, lineHeight: 16 },
  preview: { backgroundColor: '#0B1222', padding: 12, borderRadius: 10, marginTop: 12, borderWidth: 1, borderColor: '#8B5CF666' },
  previewText: { color: '#F8FAFC', fontSize: 12, lineHeight: 18, fontFamily: 'Courier' },
});
