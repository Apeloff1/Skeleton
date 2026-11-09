import React, { useState, useEffect, useCallback } from 'react';
import { API_BASE } from '../../utils/apiBase';
import { View, Text, StyleSheet, TouchableOpacity, ScrollView, Modal, ActivityIndicator, SafeAreaView } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import { apiFetch } from '../../utils/apiController';
const API = API_BASE;

const TIER_COLORS: Record<string, string> = { starter:'#94A3B8', bronze:'#CD7F32', silver:'#C0C0C0', gold:'#FFD700', platinum:'#E5E4E2', diamond:'#B9F2FF', legendary:'#FF6B6B' };
const DIFF_COLORS: Record<string, string> = { beginner:'#10B981', intermediate:'#3B82F6', advanced:'#F59E0B', expert:'#EF4444', master:'#8B5CF6' };

interface Props { visible: boolean; onClose: () => void; }

export const DailyChallengesModal: React.FC<Props> = ({ visible, onClose }) => {
  const [challenge, setChallenge] = useState<any>(null);
  const [streak, setStreak] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [currentQ, setCurrentQ] = useState(0);
  const [selectedAns, setSelectedAns] = useState<string|null>(null);
  const [result, setResult] = useState<any>(null);
  const [score, setScore] = useState(0);
  const [correct, setCorrect] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [done, setDone] = useState(false);
  const [tips, setTips] = useState<any[]>([]);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      const [cRes, sRes, tRes] = await Promise.all([
        apiFetch(`${API}/api/daily/challenge?user_id=default_user`),
        apiFetch(`${API}/api/daily/streak/default_user`),
        apiFetch(`${API}/api/daily/learning-tips`),
      ]);
      const cData = await cRes.json(); const sData = await sRes.json(); const tData = await tRes.json();
      setChallenge(cData.challenge); setStreak(sData); setTips(tData.tips || []);
      if (cData.already_started) setDone(true);
    } catch(e) { console.error(e); } finally { setLoading(false); }
  }, []);

  useEffect(() => { if (visible) { setPlaying(false); setDone(false); setScore(0); setCorrect(0); setCurrentQ(0); load(); } }, [visible, load]);

  const startChallenge = () => { setPlaying(true); setCurrentQ(0); setScore(0); setCorrect(0); setSelectedAns(null); setResult(null); };

  const checkAnswer = async (quizId: string, answer: string) => {
    setSelectedAns(answer);
    try {
      const res = await apiFetch(`${API}/api/academy/quiz/${quizId}/answer?answer=${encodeURIComponent(answer)}`, { method: 'POST' });
      const data = await res.json(); setResult(data);
      if (data.is_correct) { setScore(s => s + (data.points_earned||10)); setCorrect(c => c + 1); }
    } catch(e) { console.error(e); }
  };

  const nextQ = async () => {
    const next = currentQ + 1;
    if (next >= (challenge?.quizzes?.length || 10)) {
      await apiFetch(`${API}/api/daily/challenge/submit?user_id=default_user&score=${score}&correct=${correct}&total=${challenge?.quizzes?.length||10}`, { method: 'POST' });
      setDone(true); setPlaying(false); load();
    } else { setCurrentQ(next); setSelectedAns(null); setResult(null); }
  };

  const tierColor = TIER_COLORS[streak?.streak_tier || 'starter'] || '#94A3B8';
  const quiz = challenge?.quizzes?.[currentQ];

  const renderHome = () => (
    <ScrollView style={s.content} showsVerticalScrollIndicator={false}>
      <View style={s.streakCard}>
        <Ionicons name="flame" size={40} color={tierColor} />
        <Text style={[s.streakNum, { color: tierColor }]}>{streak?.current_streak || 0}</Text>
        <Text style={s.streakLabel}>Day Streak</Text>
        <View style={[s.tierBadge, { backgroundColor: tierColor + '25' }]}>
          <Text style={[s.tierText, { color: tierColor }]}>{(streak?.streak_tier || 'starter').toUpperCase()}</Text>
        </View>
        <Text style={s.bestStreak}>Best: {streak?.best_streak || 0} days</Text>
      </View>
      {!done ? (
        <TouchableOpacity testID="start-daily-btn" style={s.startBtn} onPress={startChallenge}>
          <Ionicons name="flash" size={20} color="#FFF" />
          <Text style={s.startBtnText}>Start Today&apos;s Challenge</Text>
        </TouchableOpacity>
      ) : (
        <View style={s.doneCard}>
          <Ionicons name="checkmark-circle" size={32} color="#10B981" />
          <Text style={s.doneText}>Today&apos;s challenge complete!</Text>
        </View>
      )}
      <Text style={s.sectionTitle}>LEARNING SCIENCE</Text>
      {tips.slice(0, 5).map((t: any) => (
        <View key={t.id} style={s.tipCard}>
          <Text style={s.tipTitle}>{t.title}</Text>
          <Text style={s.tipDesc}>{t.description}</Text>
        </View>
      ))}
    </ScrollView>
  );

  const renderQuiz = () => {
    if (!quiz) return null;
    const dc = DIFF_COLORS[quiz.difficulty] || '#888';
    return (
      <ScrollView style={s.content} showsVerticalScrollIndicator={false}>
        <View style={s.qHeader}><Text style={s.qProgress}>Q{currentQ+1}/{challenge?.quizzes?.length}</Text><View style={s.scoreChip}><Ionicons name="star" size={14} color="#F59E0B" /><Text style={s.scoreText}>{score}</Text></View></View>
        <View style={s.progressBg}><View style={[s.progressFill, { width: `${(currentQ / (challenge?.quizzes?.length||10)) * 100}%` }]} /></View>
        <View style={[s.diffBadge, { backgroundColor: dc + '25' }]}><Text style={[s.diffText, { color: dc }]}>{quiz.difficulty}</Text></View>
        <Text style={s.qText}>{quiz.question}</Text>
        {(quiz.options||[]).map((opt: string, i: number) => {
          let optS = s.optBtn; let tc = '#E2E8F0';
          if (result && selectedAns) { if (opt === result.correct_answer) { optS = {...s.optBtn,...s.optCorrect}; tc='#10B981'; } else if (opt === selectedAns && !result.is_correct) { optS = {...s.optBtn,...s.optWrong}; tc='#EF4444'; } }
          return (<TouchableOpacity key={i} testID={`daily-opt-${i}`} style={optS} onPress={() => !result && checkAnswer(quiz.id, opt)} disabled={!!result}>
            <View style={s.optLetter}><Text style={s.optLetterT}>{String.fromCharCode(65+i)}</Text></View>
            <Text style={[s.optText, { color: tc }]}>{opt}</Text>
          </TouchableOpacity>);
        })}
        {result && <TouchableOpacity testID="daily-next" style={s.nextBtn} onPress={nextQ}><Text style={s.nextBtnT}>{currentQ+1 >= (challenge?.quizzes?.length||10) ? 'Finish' : 'Next'}</Text><Ionicons name="arrow-forward" size={18} color="#FFF" /></TouchableOpacity>}
      </ScrollView>
    );
  };

  return (
    <Modal visible={visible} animationType="slide" onRequestClose={onClose}>
      <SafeAreaView style={s.container}>
        <View style={s.header}>
          <TouchableOpacity testID="daily-close" onPress={onClose} style={s.headerBtn}><Ionicons name={playing?'arrow-back':'close'} size={24} color="#F8FAFC" /></TouchableOpacity>
          <Text style={s.headerTitle}>{playing ? 'Daily Challenge' : 'Challenges & Streaks'}</Text>
          <View style={{ width: 44 }} />
        </View>
        {loading ? <View style={s.loadC}><ActivityIndicator size="large" color="#F59E0B" /></View> : playing ? renderQuiz() : renderHome()}
      </SafeAreaView>
    </Modal>
  );
};

const s = StyleSheet.create({
  container:{flex:1,backgroundColor:'#0F172A'},header:{flexDirection:'row',alignItems:'center',paddingHorizontal:16,paddingVertical:12,backgroundColor:'#1E293B',borderBottomWidth:1,borderBottomColor:'#334155'},headerBtn:{width:44,height:44,justifyContent:'center',alignItems:'center'},headerTitle:{flex:1,fontSize:18,fontWeight:'700',color:'#F8FAFC',textAlign:'center'},content:{flex:1,paddingHorizontal:16},loadC:{flex:1,justifyContent:'center',alignItems:'center'},
  streakCard:{alignItems:'center',padding:28,backgroundColor:'#1E293B',borderRadius:16,marginTop:16},streakNum:{fontSize:48,fontWeight:'900',marginTop:8},streakLabel:{fontSize:14,color:'#94A3B8'},tierBadge:{paddingHorizontal:12,paddingVertical:4,borderRadius:8,marginTop:8},tierText:{fontSize:12,fontWeight:'800'},bestStreak:{fontSize:12,color:'#64748B',marginTop:4},
  startBtn:{flexDirection:'row',alignItems:'center',justifyContent:'center',gap:8,backgroundColor:'#F59E0B',paddingVertical:16,borderRadius:12,marginTop:16},startBtnText:{fontSize:16,fontWeight:'700',color:'#FFF'},
  doneCard:{alignItems:'center',padding:20,backgroundColor:'#1E293B',borderRadius:12,marginTop:16},doneText:{fontSize:16,fontWeight:'700',color:'#10B981',marginTop:8},
  sectionTitle:{fontSize:12,fontWeight:'700',color:'#64748B',letterSpacing:1,marginTop:24,marginBottom:12},
  tipCard:{padding:14,backgroundColor:'#1E293B',borderRadius:10,marginBottom:8},tipTitle:{fontSize:14,fontWeight:'700',color:'#F8FAFC'},tipDesc:{fontSize:12,color:'#94A3B8',marginTop:4,lineHeight:18},
  qHeader:{flexDirection:'row',justifyContent:'space-between',alignItems:'center',paddingTop:12},qProgress:{fontSize:14,fontWeight:'600',color:'#94A3B8'},scoreChip:{flexDirection:'row',alignItems:'center',gap:4,backgroundColor:'#F59E0B20',paddingHorizontal:10,paddingVertical:4,borderRadius:12},scoreText:{fontSize:14,fontWeight:'700',color:'#F59E0B'},
  progressBg:{height:4,backgroundColor:'#334155',borderRadius:2,marginTop:8},progressFill:{height:4,backgroundColor:'#F59E0B',borderRadius:2},
  diffBadge:{paddingHorizontal:8,paddingVertical:3,borderRadius:6,alignSelf:'flex-start',marginTop:12},diffText:{fontSize:10,fontWeight:'700',textTransform:'uppercase'},
  qText:{fontSize:20,fontWeight:'700',color:'#F8FAFC',lineHeight:28,marginTop:16,marginBottom:20},
  optBtn:{flexDirection:'row',alignItems:'center',padding:16,backgroundColor:'#1E293B',borderRadius:12,marginBottom:10,borderWidth:1,borderColor:'#334155'},optCorrect:{borderColor:'#10B981',backgroundColor:'#10B98120'},optWrong:{borderColor:'#EF4444',backgroundColor:'#EF444420'},
  optLetter:{width:32,height:32,borderRadius:8,backgroundColor:'#334155',justifyContent:'center',alignItems:'center',marginRight:12},optLetterT:{fontSize:14,fontWeight:'700',color:'#94A3B8'},optText:{flex:1,fontSize:15,fontWeight:'500'},
  nextBtn:{flexDirection:'row',alignItems:'center',justifyContent:'center',gap:8,backgroundColor:'#3B82F6',paddingVertical:14,borderRadius:12,marginTop:16},nextBtnT:{fontSize:16,fontWeight:'700',color:'#FFF'},
});
