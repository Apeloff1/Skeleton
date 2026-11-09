/**
 * Rosetta Challenge Arena — Translate code between languages, auto-graded
 */
import React, { useState } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, Modal, ScrollView, TextInput, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import { apiFetch } from '../../utils/apiController';
const API = process.env.EXPO_PUBLIC_BACKEND_URL || '';

const DIFFICULTIES = [
  { id: 'medium', label: 'Medium', color: '#F59E0B', icon: 'flash' as const },
  { id: 'hard', label: 'Hard', color: '#EC4899', icon: 'flame' as const },
  { id: 'expert', label: 'Expert', color: '#EF4444', icon: 'skull' as const },
];

const LANGS = [
  { id: 'Python', color: '#3B82F6' }, { id: 'JavaScript', color: '#F59E0B' },
  { id: 'TypeScript', color: '#3178C6' }, { id: 'Go', color: '#00ADD8' },
  { id: 'Rust', color: '#CE422B' }, { id: 'C', color: '#A8B9CC' }, { id: 'C++', color: '#00599C' },
];

interface Props { visible: boolean; onClose: () => void; }

export const ChallengeArenaModal: React.FC<Props> = ({ visible, onClose }) => {
  const [phase, setPhase] = useState<'setup'|'challenge'|'result'|'history'>('setup');
  const [difficulty, setDifficulty] = useState('medium');
  const [sourceLang, setSourceLang] = useState('Python');
  const [targetLang, setTargetLang] = useState('Go');
  const [challenge, setChallenge] = useState<any>(null);
  const [userCode, setUserCode] = useState('');
  const [result, setResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [history, setHistory] = useState<any[]>([]);
  const [stats, setStats] = useState({ total: 0, perfect: 0 });

  const generateChallenge = async () => {
    setLoading(true);
    try {
      const r = await apiFetch(`${API}/api/rosetta-challenge/generate?difficulty=${difficulty}&source_lang=${sourceLang}&target_lang=${targetLang}`);
      if (r.ok) {
        const d = await r.json();
        setChallenge(d);
        setUserCode(d.hint || '');
        setPhase('challenge');
        setResult(null);
      }
    } catch {}
    setLoading(false);
  };

  const submitSolution = async () => {
    if (!challenge || !userCode.trim()) return;
    setLoading(true);
    try {
      const params = new URLSearchParams({
        challenge_id: challenge.challenge_id,
        user_id: 'default_user',
        target_language: targetLang,
        user_code: userCode,
      });
      const r = await apiFetch(`${API}/api/rosetta-challenge/submit?${params}`, { method: 'POST' });
      if (r.ok) {
        const d = await r.json();
        setResult(d);
        setPhase('result');
      }
    } catch {}
    setLoading(false);
  };

  const loadHistory = async () => {
    try {
      const r = await apiFetch(`${API}/api/rosetta-challenge/history/default_user?limit=20`);
      if (r.ok) {
        const d = await r.json();
        setHistory(d.history || []);
        setStats({ total: d.total || 0, perfect: d.perfect_scores || 0 });
      }
    } catch {}
    setPhase('history');
  };

  const reset = () => { setPhase('setup'); setChallenge(null); setResult(null); setUserCode(''); };

  return (
    <Modal visible={visible} animationType="slide" onRequestClose={onClose}>
      <View style={st.container}>
        <View style={st.header}>
          <TouchableOpacity testID="arena-close" onPress={phase === 'setup' ? onClose : reset} style={st.hBtn}>
            <Ionicons name={phase === 'setup' ? 'close' : 'arrow-back'} size={24} color="#F8FAFC" />
          </TouchableOpacity>
          <Text style={st.hTitle}>Challenge Arena</Text>
          <TouchableOpacity onPress={loadHistory} style={st.hBtn}>
            <Ionicons name="time" size={22} color="#F59E0B" />
          </TouchableOpacity>
        </View>

        <ScrollView style={st.scroll} showsVerticalScrollIndicator={false}>
          {phase === 'setup' && (
            <>
              <View style={st.heroCard}>
                <Ionicons name="trophy" size={48} color="#F59E0B" />
                <Text style={st.heroTitle}>Rosetta Challenge</Text>
                <Text style={st.heroSub}>Translate code between languages. Auto-graded.</Text>
              </View>

              <Text style={st.sectionLabel}>DIFFICULTY</Text>
              <View style={st.diffRow}>
                {DIFFICULTIES.map(d => (
                  <TouchableOpacity key={d.id} style={[st.diffBtn, difficulty === d.id && { backgroundColor: d.color + '20', borderColor: d.color }]} onPress={() => setDifficulty(d.id)}>
                    <Ionicons name={d.icon} size={18} color={difficulty === d.id ? d.color : '#64748B'} />
                    <Text style={[st.diffText, difficulty === d.id && { color: d.color }]}>{d.label}</Text>
                  </TouchableOpacity>
                ))}
              </View>

              <Text style={st.sectionLabel}>SOURCE LANGUAGE</Text>
              <View style={st.langGrid}>
                {LANGS.map(l => (
                  <TouchableOpacity key={`s-${l.id}`} style={[st.langBtn, sourceLang === l.id && { backgroundColor: l.color + '20', borderColor: l.color }]} onPress={() => { setSourceLang(l.id); if (l.id === targetLang) setTargetLang(LANGS.find(x => x.id !== l.id)?.id || 'Go'); }}>
                    <Text style={[st.langText, sourceLang === l.id && { color: l.color }]}>{l.id}</Text>
                  </TouchableOpacity>
                ))}
              </View>

              <Text style={st.sectionLabel}>TARGET LANGUAGE</Text>
              <View style={st.langGrid}>
                {LANGS.filter(l => l.id !== sourceLang).map(l => (
                  <TouchableOpacity key={`t-${l.id}`} style={[st.langBtn, targetLang === l.id && { backgroundColor: l.color + '20', borderColor: l.color }]} onPress={() => setTargetLang(l.id)}>
                    <Text style={[st.langText, targetLang === l.id && { color: l.color }]}>{l.id}</Text>
                  </TouchableOpacity>
                ))}
              </View>

              <TouchableOpacity testID="arena-start" style={st.startBtn} onPress={generateChallenge} disabled={loading}>
                {loading ? <ActivityIndicator color="#FFF" /> : (
                  <><Ionicons name="flash" size={20} color="#FFF" /><Text style={st.startText}>Generate Challenge</Text></>
                )}
              </TouchableOpacity>
            </>
          )}

          {phase === 'challenge' && challenge && (
            <>
              <View style={st.challengeHeader}>
                <Text style={st.challengeConcept}>{challenge.concept_name}</Text>
                <View style={st.arrowRow}>
                  <View style={[st.langTag, { backgroundColor: LANGS.find(l => l.id === sourceLang)?.color + '20' }]}>
                    <Text style={[st.langTagText, { color: LANGS.find(l => l.id === sourceLang)?.color }]}>{sourceLang}</Text>
                  </View>
                  <Ionicons name="arrow-forward" size={20} color="#F59E0B" />
                  <View style={[st.langTag, { backgroundColor: LANGS.find(l => l.id === targetLang)?.color + '20' }]}>
                    <Text style={[st.langTagText, { color: LANGS.find(l => l.id === targetLang)?.color }]}>{targetLang}</Text>
                  </View>
                </View>
              </View>

              <Text style={st.sectionLabel}>SOURCE CODE ({sourceLang})</Text>
              <ScrollView horizontal style={st.sourceBox}>
                <Text style={st.sourceCode}>{challenge.source_code}</Text>
              </ScrollView>

              <Text style={st.sectionLabel}>YOUR {targetLang.toUpperCase()} CODE</Text>
              <TextInput
                testID="arena-editor"
                style={st.editor}
                multiline
                value={userCode}
                onChangeText={setUserCode}
                textAlignVertical="top"
                autoCapitalize="none"
                autoCorrect={false}
                spellCheck={false}
                placeholder={`Write your ${targetLang} solution here...`}
                placeholderTextColor="#475569"
              />

              <TouchableOpacity testID="arena-submit" style={st.submitBtn} onPress={submitSolution} disabled={loading}>
                {loading ? <ActivityIndicator color="#FFF" /> : (
                  <><Ionicons name="checkmark-circle" size={20} color="#FFF" /><Text style={st.submitText}>Submit Solution</Text></>
                )}
              </TouchableOpacity>
            </>
          )}

          {phase === 'result' && result && (
            <>
              <View style={[st.resultCard, { borderColor: result.score === 100 ? '#22C55E' : result.score >= 70 ? '#F59E0B' : '#EF4444' }]}>
                <Ionicons name={result.score === 100 ? 'trophy' : result.score >= 70 ? 'checkmark-circle' : 'close-circle'} size={48} color={result.score === 100 ? '#22C55E' : result.score >= 70 ? '#F59E0B' : '#EF4444'} />
                <Text style={st.scoreText}>{result.score}/100</Text>
                <Text style={st.feedbackText}>{result.feedback}</Text>
                <View style={st.xpBadge}>
                  <Ionicons name="star" size={16} color="#F59E0B" />
                  <Text style={st.xpText}>+{result.xp_awarded} XP</Text>
                </View>
              </View>

              {result.output ? (
                <View style={st.outputBox}>
                  <Text style={st.outputLabel}>OUTPUT</Text>
                  <Text style={st.outputText}>{result.output}</Text>
                </View>
              ) : null}

              {result.error ? (
                <View style={st.errorBox}>
                  <Text style={st.outputLabel}>ERRORS</Text>
                  <Text style={st.errorText}>{result.error}</Text>
                </View>
              ) : null}

              <View style={st.actionRow}>
                <TouchableOpacity style={st.retryBtn} onPress={() => setPhase('challenge')}>
                  <Ionicons name="refresh" size={18} color="#3B82F6" />
                  <Text style={st.retryText}>Retry</Text>
                </TouchableOpacity>
                <TouchableOpacity style={st.nextBtn} onPress={generateChallenge}>
                  <Ionicons name="arrow-forward" size={18} color="#FFF" />
                  <Text style={st.nextText}>Next Challenge</Text>
                </TouchableOpacity>
              </View>
            </>
          )}

          {phase === 'history' && (
            <>
              <View style={st.historyHeader}>
                <View style={st.histStat}>
                  <Text style={st.histNum}>{stats.total}</Text>
                  <Text style={st.histLabel}>Attempts</Text>
                </View>
                <View style={st.histStat}>
                  <Text style={[st.histNum, { color: '#22C55E' }]}>{stats.perfect}</Text>
                  <Text style={st.histLabel}>Perfect</Text>
                </View>
                <View style={st.histStat}>
                  <Text style={[st.histNum, { color: '#F59E0B' }]}>{stats.total ? Math.round(stats.perfect / stats.total * 100) : 0}%</Text>
                  <Text style={st.histLabel}>Rate</Text>
                </View>
              </View>
              {history.map((h, i) => (
                <View key={i} style={[st.histRow, { borderLeftColor: h.score === 100 ? '#22C55E' : h.score >= 70 ? '#F59E0B' : '#EF4444' }]}>
                  <Text style={st.histLang}>{h.target_language}</Text>
                  <Text style={[st.histScore, { color: h.score === 100 ? '#22C55E' : h.score >= 70 ? '#F59E0B' : '#EF4444' }]}>{h.score}/100</Text>
                </View>
              ))}
              {history.length === 0 && <Text style={st.emptyText}>No challenges completed yet. Start your first one!</Text>}
            </>
          )}

          <View style={{ height: 40 }} />
        </ScrollView>
      </View>
    </Modal>
  );
};

const st = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0F172A' },
  header: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16, paddingVertical: 12, backgroundColor: '#1E293B', borderBottomWidth: 1, borderBottomColor: '#334155' },
  hBtn: { width: 44, height: 44, justifyContent: 'center', alignItems: 'center' },
  hTitle: { flex: 1, fontSize: 18, fontWeight: '700', color: '#F8FAFC', textAlign: 'center' },
  scroll: { flex: 1, paddingHorizontal: 16 },
  heroCard: { alignItems: 'center', paddingVertical: 32, backgroundColor: '#1E293B', borderRadius: 16, marginTop: 16 },
  heroTitle: { fontSize: 24, fontWeight: '800', color: '#F8FAFC', marginTop: 12 },
  heroSub: { fontSize: 14, color: '#94A3B8', marginTop: 4 },
  sectionLabel: { fontSize: 11, fontWeight: '800', color: '#64748B', letterSpacing: 1.5, marginTop: 20, marginBottom: 8 },
  diffRow: { flexDirection: 'row', gap: 10 },
  diffBtn: { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, paddingVertical: 12, borderRadius: 12, borderWidth: 1.5, borderColor: '#334155', backgroundColor: '#1E293B' },
  diffText: { fontSize: 13, fontWeight: '700', color: '#94A3B8' },
  langGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  langBtn: { paddingHorizontal: 16, paddingVertical: 10, borderRadius: 10, borderWidth: 1.5, borderColor: '#334155', backgroundColor: '#1E293B' },
  langText: { fontSize: 13, fontWeight: '700', color: '#94A3B8' },
  startBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 10, backgroundColor: '#F59E0B', borderRadius: 14, paddingVertical: 16, marginTop: 24 },
  startText: { fontSize: 17, fontWeight: '800', color: '#0F172A' },
  challengeHeader: { alignItems: 'center', paddingVertical: 16 },
  challengeConcept: { fontSize: 20, fontWeight: '800', color: '#F8FAFC' },
  arrowRow: { flexDirection: 'row', alignItems: 'center', gap: 12, marginTop: 10 },
  langTag: { paddingHorizontal: 14, paddingVertical: 6, borderRadius: 10 },
  langTagText: { fontSize: 14, fontWeight: '800' },
  sourceBox: { backgroundColor: '#0D1117', borderRadius: 12, padding: 14, maxHeight: 200, borderWidth: 1, borderColor: '#21262D' },
  sourceCode: { color: '#A7F3D0', fontFamily: 'monospace', fontSize: 12, lineHeight: 18 },
  editor: { backgroundColor: '#1E293B', borderRadius: 12, padding: 14, color: '#E2E8F0', fontFamily: 'monospace', fontSize: 13, lineHeight: 20, minHeight: 180, maxHeight: 300, borderWidth: 1, borderColor: '#334155', marginTop: 4 },
  submitBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 10, backgroundColor: '#22C55E', borderRadius: 14, paddingVertical: 16, marginTop: 16 },
  submitText: { fontSize: 17, fontWeight: '800', color: '#FFF' },
  resultCard: { alignItems: 'center', paddingVertical: 32, backgroundColor: '#1E293B', borderRadius: 16, marginTop: 16, borderWidth: 2 },
  scoreText: { fontSize: 42, fontWeight: '800', color: '#F8FAFC', marginTop: 12 },
  feedbackText: { fontSize: 14, color: '#94A3B8', marginTop: 8, textAlign: 'center', paddingHorizontal: 20 },
  xpBadge: { flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 12, backgroundColor: '#F59E0B20', paddingHorizontal: 14, paddingVertical: 6, borderRadius: 10 },
  xpText: { fontSize: 16, fontWeight: '800', color: '#F59E0B' },
  outputBox: { backgroundColor: '#0D1117', borderRadius: 12, padding: 14, marginTop: 12, borderWidth: 1, borderColor: '#21262D' },
  outputLabel: { fontSize: 10, fontWeight: '800', color: '#64748B', letterSpacing: 1, marginBottom: 6 },
  outputText: { color: '#A7F3D0', fontFamily: 'monospace', fontSize: 12, lineHeight: 18 },
  errorBox: { backgroundColor: '#1C0D0D', borderRadius: 12, padding: 14, marginTop: 8, borderWidth: 1, borderColor: '#EF444430' },
  errorText: { color: '#FCA5A5', fontFamily: 'monospace', fontSize: 12, lineHeight: 18 },
  actionRow: { flexDirection: 'row', gap: 12, marginTop: 16 },
  retryBtn: { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, paddingVertical: 14, borderRadius: 12, borderWidth: 1.5, borderColor: '#3B82F6' },
  retryText: { fontSize: 15, fontWeight: '700', color: '#3B82F6' },
  nextBtn: { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, paddingVertical: 14, borderRadius: 12, backgroundColor: '#F59E0B' },
  nextText: { fontSize: 15, fontWeight: '700', color: '#FFF' },
  historyHeader: { flexDirection: 'row', gap: 12, marginTop: 16 },
  histStat: { flex: 1, backgroundColor: '#1E293B', borderRadius: 12, padding: 16, alignItems: 'center' },
  histNum: { fontSize: 28, fontWeight: '800', color: '#F8FAFC' },
  histLabel: { fontSize: 11, color: '#64748B', marginTop: 4, textTransform: 'uppercase' },
  histRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', backgroundColor: '#1E293B', borderRadius: 10, padding: 14, marginTop: 8, borderLeftWidth: 3 },
  histLang: { fontSize: 14, fontWeight: '600', color: '#F8FAFC' },
  histScore: { fontSize: 16, fontWeight: '800' },
  emptyText: { textAlign: 'center', color: '#64748B', fontSize: 14, paddingVertical: 30 },
});
