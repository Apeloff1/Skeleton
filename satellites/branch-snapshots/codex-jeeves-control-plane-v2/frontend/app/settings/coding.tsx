/**
 * Settings → Coding
 * - Metronome controls (live preview)
 * - Editor preferences (bracket-pair colors, auto-indent, snippets palette,
 *   AI explain, line numbers, tab size)
 */
import React from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity, SafeAreaView, Switch,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useSettings } from '../../state/settingsStore';
import { Metronome } from '../../components/Metronome';

export default function CodingSettings() {
  const router = useRouter();
  const coding = useSettings(s => s.coding);
  const setCoding = useSettings(s => s.setCoding);
  const reset = useSettings(s => s.resetCoding);

  return (
    <SafeAreaView style={s.container}>
      <View style={s.header}>
        <TouchableOpacity onPress={() => router.back()} style={s.hdrBtn} hitSlop={{ top: 8, left: 8, right: 8, bottom: 8 }}>
          <Ionicons name="arrow-back" size={24} color="#F8FAFC" />
        </TouchableOpacity>
        <Text style={s.hdrTitle}>Coding</Text>
        <TouchableOpacity onPress={reset} style={s.hdrBtn} hitSlop={{ top: 8, left: 8, right: 8, bottom: 8 }}>
          <Ionicons name="refresh" size={20} color="#EF4444" />
        </TouchableOpacity>
      </View>

      <ScrollView contentContainerStyle={{ padding: 14, paddingBottom: 60 }}>
        {/* ── Metronome ── */}
        <View style={s.section}>
          <View style={s.sectionHead}>
            <Ionicons name="musical-notes" size={18} color="#3B82F6" />
            <Text style={s.sectionTitle}>Metronome</Text>
            <Switch
              value={coding.metronomeEnabled}
              onValueChange={v => setCoding({ metronomeEnabled: v })}
              trackColor={{ false: '#404040', true: '#3B82F6' }}
              thumbColor={coding.metronomeEnabled ? '#3B82F6' : '#94A3B8'}
            />
          </View>
          <Text style={s.sectionSub}>
            Adds a floating metronome button to the code editor. Tap it to open
            a full control surface (BPM, time signature, sound, tap-tempo, visual pulse).
          </Text>
          {coding.metronomeEnabled && (
            <View style={{ marginTop: 12 }}>
              <Metronome compact />
            </View>
          )}
          <View style={s.row}>
            <Text style={s.rowLabel}>Auto-stop</Text>
            <View style={s.miniChipRow}>
              {[0, 5, 15, 30, 60].map(min => (
                <TouchableOpacity
                  key={min}
                  style={[s.miniChip, coding.metronomeAutoStopMin === min && s.miniChipActive]}
                  onPress={() => setCoding({ metronomeAutoStopMin: min })}
                  activeOpacity={0.7}
                >
                  <Text style={[s.miniChipText, coding.metronomeAutoStopMin === min && s.miniChipTextActive]}>
                    {min === 0 ? 'Off' : `${min}m`}
                  </Text>
                </TouchableOpacity>
              ))}
            </View>
          </View>
        </View>

        {/* ── Editor ── */}
        <View style={s.section}>
          <View style={s.sectionHead}>
            <Ionicons name="code-slash" size={18} color="#10B981" />
            <Text style={s.sectionTitle}>Editor</Text>
          </View>

          <Row label="Bracket-pair colors" hint="Colorise matching () [] {} pairs.">
            <Switch value={coding.bracketPairColors} onValueChange={v => setCoding({ bracketPairColors: v })}
              trackColor={{ false: '#404040', true: '#10B981' }}
              thumbColor={coding.bracketPairColors ? '#059669' : '#94A3B8'} />
          </Row>
          <Row label="Auto-indent on Enter" hint="Preserve indentation from the previous line.">
            <Switch value={coding.autoIndent} onValueChange={v => setCoding({ autoIndent: v })}
              trackColor={{ false: '#404040', true: '#10B981' }}
              thumbColor={coding.autoIndent ? '#059669' : '#94A3B8'} />
          </Row>
          <Row label="Snippets palette" hint="Quick-insert language templates from a button in the toolbar.">
            <Switch value={coding.showSnippetsPalette} onValueChange={v => setCoding({ showSnippetsPalette: v })}
              trackColor={{ false: '#404040', true: '#10B981' }}
              thumbColor={coding.showSnippetsPalette ? '#059669' : '#94A3B8'} />
          </Row>
          <Row label="AI Explain selection" hint="Long-press code → ask Jeeves to explain.">
            <Switch value={coding.aiExplainEnabled} onValueChange={v => setCoding({ aiExplainEnabled: v })}
              trackColor={{ false: '#404040', true: '#10B981' }}
              thumbColor={coding.aiExplainEnabled ? '#059669' : '#94A3B8'} />
          </Row>
          <Row label="Line numbers" hint="Show gutter line numbers.">
            <Switch value={coding.showLineNumbers} onValueChange={v => setCoding({ showLineNumbers: v })}
              trackColor={{ false: '#404040', true: '#10B981' }}
              thumbColor={coding.showLineNumbers ? '#059669' : '#94A3B8'} />
          </Row>
          <View style={s.row}>
            <View style={{ flex: 1 }}>
              <Text style={s.rowLabel}>Tab size</Text>
              <Text style={s.rowHint}>Spaces per indent level.</Text>
            </View>
            <View style={s.miniChipRow}>
              {[2, 4].map(n => (
                <TouchableOpacity
                  key={n}
                  style={[s.miniChip, coding.tabSize === n && s.miniChipActive]}
                  onPress={() => setCoding({ tabSize: n as any })}
                  activeOpacity={0.7}
                >
                  <Text style={[s.miniChipText, coding.tabSize === n && s.miniChipTextActive]}>{n}</Text>
                </TouchableOpacity>
              ))}
            </View>
          </View>
        </View>

        <Text style={s.footer}>
          Settings persist locally. Re-open the code editor for editor changes
          (bracket-pair colors, line numbers, tab size) to take full effect.
        </Text>
      </ScrollView>
    </SafeAreaView>
  );
}

const Row: React.FC<{ label: string; hint?: string; children: React.ReactNode }> = ({ label, hint, children }) => (
  <View style={s.row}>
    <View style={{ flex: 1 }}>
      <Text style={s.rowLabel}>{label}</Text>
      {hint ? <Text style={s.rowHint}>{hint}</Text> : null}
    </View>
    {children}
  </View>
);

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#141414' },
  header: { flexDirection: 'row', alignItems: 'center', padding: 12, backgroundColor: '#262626', borderBottomWidth: 1, borderBottomColor: '#404040' },
  hdrBtn: { width: 44, height: 44, justifyContent: 'center', alignItems: 'center' },
  hdrTitle: { flex: 1, textAlign: 'center', fontSize: 17, fontWeight: '700', color: '#F8FAFC' },
  section: { backgroundColor: '#262626', borderRadius: 12, padding: 14, marginBottom: 14, borderWidth: 1, borderColor: '#404040' },
  sectionHead: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  sectionTitle: { color: '#F8FAFC', fontSize: 15, fontWeight: '800', flex: 1 },
  sectionSub: { color: '#94A3B8', fontSize: 12, marginTop: 4, lineHeight: 17 },
  row: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingVertical: 10, borderTopWidth: 1, borderTopColor: '#404040', marginTop: 6, gap: 12 },
  rowLabel: { color: '#F8FAFC', fontSize: 13, fontWeight: '700' },
  rowHint: { color: '#94A3B8', fontSize: 11, marginTop: 2 },
  miniChipRow: { flexDirection: 'row', gap: 6 },
  miniChip: { backgroundColor: '#141414', borderRadius: 999, paddingHorizontal: 10, paddingVertical: 5, borderWidth: 1, borderColor: '#404040' },
  miniChipActive: { backgroundColor: '#3B82F6', borderColor: '#3B82F6' },
  miniChipText: { color: '#94A3B8', fontSize: 11, fontWeight: '700' },
  miniChipTextActive: { color: '#fff' },
  footer: { color: '#64748B', fontSize: 11, lineHeight: 16, textAlign: 'center', marginTop: 8, fontStyle: 'italic' },
});
