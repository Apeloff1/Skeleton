/**
 * /rosetta — Full Rosetta Challenge Runner.
 *
 * Generate → see source code in lang A → translate to lang B → submit → verdict.
 */
import { useState, useCallback } from 'react';
import {
  View, Text, TextInput, ScrollView, TouchableOpacity, ActivityIndicator,
  StyleSheet, StatusBar, SafeAreaView, KeyboardAvoidingView, Platform,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { jeevesSpeak } from '../features/Academy/jeevesTts';

const BACKEND = process.env.EXPO_PUBLIC_BACKEND_URL || '';
const USER_ID = 'default_user';
const LANGS = ['Python','JavaScript','TypeScript','Go','Rust','C','C++'];
const DIFFICULTIES = ['easy', 'medium', 'hard', 'expert'];

type Challenge = {
  challenge_id: string;
  concept: string;
  concept_name: string;
  difficulty: string;
  source_language: string;
  target_language: string;
  source_code: string;
  hint: string;
};

type Verdict = {
  passed?: boolean;
  correct?: boolean;
  score?: number;
  output?: string;
  error?: string;
  expected?: string;
  xp_awarded?: number;
  feedback?: string;
};

export default function RosettaScreen() {
  const router = useRouter();
  const [difficulty, setDifficulty] = useState('medium');
  const [sourceLang, setSourceLang] = useState<string | undefined>(undefined);
  const [targetLang, setTargetLang] = useState<string | undefined>(undefined);
  const [challenge, setChallenge] = useState<Challenge | null>(null);
  const [userCode, setUserCode] = useState('');
  const [generating, setGenerating] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [verdict, setVerdict] = useState<Verdict | null>(null);
  const [err, setErr] = useState('');
  const [xp, setXp] = useState(0);

  const generate = useCallback(async () => {
    setGenerating(true); setErr(''); setVerdict(null); setChallenge(null); setUserCode('');
    try {
      const qs = new URLSearchParams({ difficulty });
      if (sourceLang) qs.set('source_lang', sourceLang);
      if (targetLang) qs.set('target_lang', targetLang);
      const r = await fetch(`${BACKEND}/api/rosetta-challenge/generate?${qs.toString()}`);
      const j = await r.json();
      if (j?.error) {
        setErr(j.error + (j.concept ? ` (concept: ${j.concept})` : ''));
      } else {
        setChallenge(j);
        setUserCode(j.hint || '');
      }
    } catch (e: any) {
      setErr(String(e?.message || e).slice(0, 200));
    } finally {
      setGenerating(false);
    }
  }, [difficulty, sourceLang, targetLang]);

  const submit = useCallback(async () => {
    if (!challenge) return;
    setSubmitting(true); setErr(''); setVerdict(null);
    try {
      const qs = new URLSearchParams({
        challenge_id: challenge.challenge_id,
        user_id: USER_ID,
        target_language: challenge.target_language,
        user_code: userCode,
      });
      const r = await fetch(`${BACKEND}/api/rosetta-challenge/submit?${qs.toString()}`, { method: 'POST' });
      const j = await r.json();
      setVerdict(j);
      if (j?.xp_awarded) setXp(v => v + j.xp_awarded);
      const passed = !!j?.passed;
      jeevesSpeak(
        passed
          ? `Verdict: passed. ${j.xp_awarded || 0} XP awarded.`
          : `Verdict: not quite. ${j?.feedback ? '' : 'Inspect the feedback below.'}`,
        { context: passed ? 'celebration' : 'gentle_correction', prependCatchphrase: false },
      );
    } catch (e: any) {
      setErr(String(e?.message || e).slice(0, 200));
    } finally {
      setSubmitting(false);
    }
  }, [challenge, userCode]);

  const passed = verdict?.passed || verdict?.correct;

  return (
    <SafeAreaView style={s.root}>
      <StatusBar barStyle="light-content" backgroundColor="#0A0A0A" />

      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <View style={s.header}>
          <TouchableOpacity onPress={() => router.back()} style={s.backBtn} hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}>
            <Ionicons name="chevron-back" size={22} color="#8B5CF6" />
          </TouchableOpacity>
          <View style={{ flex: 1 }}>
            <Text style={s.title}>🗿 Rosetta Challenge</Text>
            <Text style={s.subtitle}>Translate code across languages · +{xp} XP</Text>
          </View>
        </View>

        <ScrollView contentContainerStyle={{ padding: 12, paddingBottom: 80 }}>
          {/* Difficulty selector */}
          <Text style={s.sectionLabel}>Difficulty</Text>
          <View style={s.chipWrap}>
            {DIFFICULTIES.map(d => (
              <TouchableOpacity key={d} style={[s.chip, difficulty === d && s.chipActive]} onPress={() => setDifficulty(d)}>
                <Text style={[s.chipText, difficulty === d && s.chipTextActive]}>{d}</Text>
              </TouchableOpacity>
            ))}
          </View>

          {/* Lang picker */}
          <Text style={s.sectionLabel}>From → To  (leave blank for random)</Text>
          <View style={s.langRow}>
            <View style={{ flex: 1 }}>
              <Text style={s.langLabel}>Source</Text>
              <ScrollView horizontal showsHorizontalScrollIndicator={false}>
                <View style={{ flexDirection: 'row', gap: 4 }}>
                  <TouchableOpacity style={[s.langChip, !sourceLang && s.langChipActive]} onPress={() => setSourceLang(undefined)}>
                    <Text style={[s.langChipText, !sourceLang && s.langChipTextActive]}>any</Text>
                  </TouchableOpacity>
                  {LANGS.map(l => (
                    <TouchableOpacity key={l} style={[s.langChip, sourceLang === l && s.langChipActive]} onPress={() => setSourceLang(l)}>
                      <Text style={[s.langChipText, sourceLang === l && s.langChipTextActive]}>{l}</Text>
                    </TouchableOpacity>
                  ))}
                </View>
              </ScrollView>
            </View>
          </View>
          <View style={s.langRow}>
            <View style={{ flex: 1 }}>
              <Text style={s.langLabel}>Target</Text>
              <ScrollView horizontal showsHorizontalScrollIndicator={false}>
                <View style={{ flexDirection: 'row', gap: 4 }}>
                  <TouchableOpacity style={[s.langChip, !targetLang && s.langChipActive]} onPress={() => setTargetLang(undefined)}>
                    <Text style={[s.langChipText, !targetLang && s.langChipTextActive]}>any</Text>
                  </TouchableOpacity>
                  {LANGS.map(l => (
                    <TouchableOpacity key={l} style={[s.langChip, targetLang === l && s.langChipActive]} onPress={() => setTargetLang(l)}>
                      <Text style={[s.langChipText, targetLang === l && s.langChipTextActive]}>{l}</Text>
                    </TouchableOpacity>
                  ))}
                </View>
              </ScrollView>
            </View>
          </View>

          <TouchableOpacity
            onPress={generate}
            disabled={generating}
            style={[s.generateBtn, generating && { opacity: 0.5 }]}
          >
            {generating ? <ActivityIndicator color="#0A0A0A" /> : (
              <>
                <Ionicons name="shuffle" size={16} color="#0A0A0A" />
                <Text style={s.generateText}>Generate Challenge</Text>
              </>
            )}
          </TouchableOpacity>

          {err ? (
            <View style={s.errBox}>
              <Ionicons name="warning" size={14} color="#f87171" />
              <Text style={s.errText}>{err}</Text>
            </View>
          ) : null}

          {challenge && (
            <>
              <View style={s.challengeHead}>
                <Text style={s.conceptName}>{challenge.concept_name}</Text>
                <View style={s.diffBadge}><Text style={s.diffText}>{challenge.difficulty}</Text></View>
              </View>
              <Text style={s.flowText}>
                <Text style={s.flowLang}>{challenge.source_language}</Text>
                {' → '}
                <Text style={[s.flowLang, { color: '#8B5CF6' }]}>{challenge.target_language}</Text>
              </Text>

              <Text style={s.sourceHeader}>Source ({challenge.source_language})</Text>
              <ScrollView horizontal style={s.sourceBox}>
                <Text style={s.sourceCode}>{challenge.source_code}</Text>
              </ScrollView>

              <Text style={s.sourceHeader}>Your translation ({challenge.target_language})</Text>
              <TextInput
                value={userCode}
                onChangeText={setUserCode}
                multiline
                style={s.editor}
                placeholder={`Write ${challenge.target_language} code…`}
                placeholderTextColor="#475569"
                autoCapitalize="none"
                autoCorrect={false}
                spellCheck={false}
                textAlignVertical="top"
              />

              <TouchableOpacity
                onPress={submit}
                disabled={submitting || !userCode.trim()}
                style={[s.submitBtn, (submitting || !userCode.trim()) && { opacity: 0.4 }]}
              >
                {submitting ? <ActivityIndicator color="#0A0A0A" /> : (
                  <>
                    <Ionicons name="checkmark-circle" size={16} color="#0A0A0A" />
                    <Text style={s.submitText}>Submit</Text>
                  </>
                )}
              </TouchableOpacity>

              {verdict && (
                <View style={[s.verdictBox, { borderColor: passed ? '#10B981' : '#f87171', backgroundColor: (passed ? '#10B981' : '#f87171') + '15' }]}>
                  <View style={s.verdictHead}>
                    <Ionicons name={passed ? 'trophy' : 'sad-outline'} size={20} color={passed ? '#10B981' : '#f87171'} />
                    <Text style={[s.verdictTitle, { color: passed ? '#10B981' : '#f87171' }]}>
                      {passed ? 'Passed!' : 'Not quite'}
                    </Text>
                    {verdict.xp_awarded ? <Text style={s.verdictXp}>+{verdict.xp_awarded} XP</Text> : null}
                  </View>
                  {verdict.score != null && <Text style={s.verdictText}>Score: {verdict.score}</Text>}
                  {!!verdict.feedback && <Text style={s.verdictText}>{verdict.feedback}</Text>}
                  {!!verdict.output && (
                    <View style={s.verdictBlock}>
                      <Text style={s.verdictBlockHead}>Your output</Text>
                      <Text style={s.verdictCode}>{verdict.output}</Text>
                    </View>
                  )}
                  {!!verdict.expected && (
                    <View style={s.verdictBlock}>
                      <Text style={s.verdictBlockHead}>Expected</Text>
                      <Text style={s.verdictCode}>{verdict.expected}</Text>
                    </View>
                  )}
                  {!!verdict.error && (
                    <View style={s.verdictBlock}>
                      <Text style={s.verdictBlockHead}>Error</Text>
                      <Text style={s.verdictCode}>{verdict.error}</Text>
                    </View>
                  )}
                </View>
              )}
            </>
          )}
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#0A0A0A' },
  header: {
    flexDirection: 'row', alignItems: 'center', gap: 12,
    paddingHorizontal: 14, paddingVertical: 10,
    borderBottomColor: '#1F1F1F', borderBottomWidth: 1,
  },
  backBtn: { width: 32, height: 32, alignItems: 'center', justifyContent: 'center' },
  title: { color: '#f1f5f9', fontSize: 16, fontWeight: '900' },
  subtitle: { color: '#94a3b8', fontSize: 11, marginTop: 2 },
  sectionLabel: { color: '#94a3b8', fontSize: 11, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 1, marginTop: 12, marginBottom: 6 },
  chipWrap: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  chip: { paddingHorizontal: 12, paddingVertical: 6, borderRadius: 14, backgroundColor: '#141414', borderWidth: 1, borderColor: '#1F1F1F' },
  chipActive: { backgroundColor: '#8B5CF633', borderColor: '#8B5CF6' },
  chipText: { color: '#94a3b8', fontSize: 11, fontWeight: '600' },
  chipTextActive: { color: '#8B5CF6', fontWeight: '700' },
  langRow: { marginTop: 8 },
  langLabel: { color: '#64748b', fontSize: 10, marginBottom: 4 },
  langChip: { paddingHorizontal: 10, paddingVertical: 5, borderRadius: 10, backgroundColor: '#141414', borderWidth: 1, borderColor: '#1F1F1F', marginRight: 4 },
  langChipActive: { backgroundColor: '#8B5CF622', borderColor: '#8B5CF6' },
  langChipText: { color: '#94a3b8', fontSize: 10 },
  langChipTextActive: { color: '#8B5CF6', fontWeight: '700' },
  generateBtn: {
    marginTop: 12, paddingVertical: 12, borderRadius: 10,
    backgroundColor: '#8B5CF6', alignItems: 'center',
    flexDirection: 'row', justifyContent: 'center', gap: 8,
  },
  generateText: { color: '#0A0A0A', fontSize: 14, fontWeight: '900', letterSpacing: 0.5 },
  errBox: {
    flexDirection: 'row', alignItems: 'center', gap: 6,
    backgroundColor: '#f8717122', borderColor: '#f87171', borderWidth: 1,
    padding: 10, borderRadius: 8, marginTop: 8,
  },
  errText: { color: '#fecaca', fontSize: 11, flex: 1 },
  challengeHead: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginTop: 18 },
  conceptName: { color: '#f1f5f9', fontSize: 18, fontWeight: '900' },
  diffBadge: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: 8, backgroundColor: '#8B5CF622', borderColor: '#8B5CF6', borderWidth: 1 },
  diffText: { color: '#8B5CF6', fontSize: 10, fontWeight: '700', textTransform: 'uppercase' },
  flowText: { color: '#cbd5e1', fontSize: 13, marginTop: 4, marginBottom: 8 },
  flowLang: { color: '#a78bfa', fontWeight: '700' },
  sourceHeader: { color: '#94a3b8', fontSize: 11, fontWeight: '700', textTransform: 'uppercase', marginTop: 12, marginBottom: 4 },
  sourceBox: { backgroundColor: '#141414', borderRadius: 10, borderWidth: 1, borderColor: '#1F1F1F', padding: 10, maxHeight: 180 },
  sourceCode: { color: '#a3e635', fontSize: 12, fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace', lineHeight: 16 },
  editor: {
    minHeight: 160, maxHeight: 280,
    color: '#f1f5f9', fontSize: 13, lineHeight: 18,
    padding: 12, backgroundColor: '#141414', borderRadius: 10,
    borderWidth: 1, borderColor: '#1F1F1F',
    fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace',
  },
  submitBtn: {
    marginTop: 12, paddingVertical: 12, borderRadius: 10,
    backgroundColor: '#10B981', alignItems: 'center',
    flexDirection: 'row', justifyContent: 'center', gap: 8,
  },
  submitText: { color: '#0A0A0A', fontSize: 14, fontWeight: '900', letterSpacing: 0.5 },
  verdictBox: { marginTop: 14, padding: 12, borderRadius: 12, borderWidth: 1 },
  verdictHead: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 6 },
  verdictTitle: { fontSize: 16, fontWeight: '900', flex: 1 },
  verdictXp: { color: '#fbbf24', fontWeight: '900', fontSize: 12 },
  verdictText: { color: '#cbd5e1', fontSize: 12, lineHeight: 16, marginVertical: 2 },
  verdictBlock: { marginTop: 8, paddingTop: 8, borderTopColor: '#1F1F1F', borderTopWidth: 1 },
  verdictBlockHead: { color: '#94a3b8', fontSize: 10, textTransform: 'uppercase', fontWeight: '700', marginBottom: 4 },
  verdictCode: { color: '#fde68a', fontSize: 11, fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace' },
  retryBtn: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6,
    marginTop: 12, padding: 10, borderRadius: 8,
    backgroundColor: '#F59E0B22', borderColor: '#F59E0B', borderWidth: 1,
  },
  retryText: { color: '#F59E0B', fontSize: 12, fontWeight: '700' },
});
