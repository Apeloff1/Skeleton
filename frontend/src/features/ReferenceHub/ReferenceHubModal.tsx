import React, { useState, useEffect, useCallback } from 'react';
import { API_BASE } from '../../utils/apiBase';
import { View, Text, StyleSheet, TouchableOpacity, ScrollView, Modal, ActivityIndicator, SafeAreaView } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import { apiFetch } from '../../utils/apiController';
const API = API_BASE;

const SECTIONS = [
  { id: 'cheatsheets', title: 'Cheat Sheets', icon: 'document-text', color: '#3B82F6', endpoint: '/api/enhance/cheatsheets', key: 'cheatsheets' },
  { id: 'snippets', title: 'Code Snippets', icon: 'code-slash', color: '#10B981', endpoint: '/api/enhance/snippets?limit=50', key: 'snippets' },
  { id: 'interview', title: 'Interview Prep', icon: 'briefcase', color: '#F59E0B', endpoint: '/api/enhance/interview-prep?limit=50', key: 'questions' },
  { id: 'flashcards', title: 'Flashcard Decks', icon: 'albums', color: '#8B5CF6', endpoint: '/api/enhance/flashcards', key: 'decks' },
  { id: 'glossary', title: 'Tech Glossary', icon: 'book', color: '#EC4899', endpoint: '/api/enhance/glossary', key: 'terms' },
  { id: 'complexity', title: 'Complexity Reference', icon: 'speedometer', color: '#2563EB', endpoint: '/api/enhance/complexity-reference', key: 'reference' },
  { id: 'http', title: 'HTTP Status Codes', icon: 'globe', color: '#EF4444', endpoint: '/api/enhance/http-status-codes', key: 'codes' },
  { id: 'careers', title: 'Career Roadmaps', icon: 'map', color: '#3B82F6', endpoint: '/api/enhance/career-roadmap', key: 'roadmaps' },
  { id: 'projects', title: 'Project Ideas', icon: 'rocket', color: '#F97316', endpoint: '/api/enhance/project-ideas', key: 'projects' },
];

interface Props { visible: boolean; onClose: () => void; }

export const ReferenceHubModal: React.FC<Props> = ({ visible, onClose }) => {
  const [view, setView] = useState<'home'|'section'>('home');
  const [loading, setLoading] = useState(false);
  const [activeSection, setActiveSection] = useState<any>(null);
  const [data, setData] = useState<any[]>([]);
  const [stats, setStats] = useState<any>(null);

  const loadStats = useCallback(async () => {
    try { const res = await apiFetch(`${API}/api/enhance/platform-stats`); setStats(await res.json()); } catch {}
  }, []);

  useEffect(() => { if (visible) { setView('home'); loadStats(); } }, [visible, loadStats]);

  const openSection = async (section: any) => {
    setLoading(true); setActiveSection(section);
    try { const res = await apiFetch(`${API}${section.endpoint}`); const d = await res.json(); setData(d[section.key]||[]); } catch {}
    setView('section'); setLoading(false);
  };

  const handleBack = () => { if (view === 'section') { setView('home'); setData([]); } else onClose(); };

  const renderItem = (item: any, i: number) => {
    const sec = activeSection?.id;
    if (sec === 'cheatsheets') return <View key={i} style={st.itemCard}><Text style={st.itemTitle}>{item.title}</Text><Text style={st.itemSub}>{item.total_items} items</Text>{(item.items||[]).slice(0,5).map((it:string,j:number)=><Text key={j} style={st.itemBullet}>• {it}</Text>)}</View>;
    if (sec === 'snippets') return <View key={i} style={st.itemCard}><View style={st.itemRow}><Text style={st.itemTitle}>{item.title}</Text><Text style={st.langBadge}>{item.language}</Text></View><Text style={st.codeText} numberOfLines={3}>{item.code}</Text></View>;
    if (sec === 'interview') return <View key={i} style={st.itemCard}><Text style={st.itemTitle}>{item.question}</Text><Text style={st.itemSub}>{item.difficulty} • {item.category}</Text><Text style={st.itemDesc}>{item.answer}</Text></View>;
    if (sec === 'flashcards') return <View key={i} style={st.itemCard}><Text style={st.itemTitle}>{item.title}</Text><Text style={st.itemSub}>{item.total_cards} cards • {item.domain}</Text>{(item.cards||[]).slice(0,3).map((c:any,j:number)=><View key={j} style={st.flashRow}><Text style={st.flashFront}>{c.front}</Text><Text style={st.flashBack}>{c.back}</Text></View>)}</View>;
    if (sec === 'glossary') return <View key={i} style={st.itemCard}><Text style={st.itemTitle}>{item.term}</Text><Text style={st.itemDesc}>{item.definition}</Text></View>;
    if (sec === 'complexity') return <View key={i} style={st.itemCard}><Text style={st.itemTitle}>{item.operation}</Text><View style={st.compRow}><Text style={st.compCell}>Best: {item.best}</Text><Text style={st.compCell}>Avg: {item.average}</Text><Text style={st.compCell}>Worst: {item.worst}</Text></View></View>;
    if (sec === 'http') return <View key={i} style={st.itemCard}><View style={st.itemRow}><Text style={[st.httpCode,{color:item.code<300?'#10B981':item.code<400?'#3B82F6':item.code<500?'#F59E0B':'#EF4444'}]}>{item.code}</Text><Text style={st.itemTitle}>{item.message}</Text></View></View>;
    if (sec === 'careers') return <View key={i} style={st.itemCard}><Text style={st.itemTitle}>{item.role}</Text><Text style={st.itemSub}>{item.experience} • {item.domain}</Text>{(item.skills||[]).map((sk:string,j:number)=><Text key={j} style={st.itemBullet}>• {sk}</Text>)}</View>;
    if (sec === 'projects') return <View key={i} style={st.itemCard}><Text style={st.itemTitle}>{item.title}</Text><Text style={st.itemSub}>{item.difficulty} • {item.domain}</Text><Text style={st.itemDesc}>{item.description}</Text></View>;
    return <View key={i} style={st.itemCard}><Text style={st.itemTitle}>{JSON.stringify(item).slice(0,100)}</Text></View>;
  };

  return (
    <Modal visible={visible} animationType="slide" onRequestClose={handleBack}>
      <SafeAreaView style={st.container}>
        <View style={st.header}>
          <TouchableOpacity testID="ref-back" onPress={handleBack} style={st.headerBtn}><Ionicons name={view==='home'?'close':'arrow-back'} size={24} color="#F8FAFC" /></TouchableOpacity>
          <Text style={st.headerTitle}>{activeSection && view==='section' ? activeSection.title : 'Reference Hub'}</Text>
          <View style={{width:44}} />
        </View>
        {loading ? <View style={st.loadC}><ActivityIndicator size="large" color="#3B82F6" /></View> : view === 'home' ? (
          <ScrollView style={st.content} showsVerticalScrollIndicator={false}>
            {stats && <View style={st.platformCard}><Text style={st.platformTitle}>{stats.platform} — {stats.version}</Text><Text style={st.platformSub}>{stats.features?.length || 0} features</Text></View>}
            {SECTIONS.map(sec => (
              <TouchableOpacity key={sec.id} testID={`ref-${sec.id}`} style={[st.secCard, {borderLeftColor:sec.color}]} onPress={() => openSection(sec)}>
                <View style={[st.secIcon,{backgroundColor:sec.color+'20'}]}><Ionicons name={sec.icon as any} size={22} color={sec.color} /></View>
                <Text style={st.secTitle}>{sec.title}</Text>
                <Ionicons name="chevron-forward" size={18} color="#6B7280" />
              </TouchableOpacity>
            ))}
          </ScrollView>
        ) : (
          <ScrollView style={st.content} showsVerticalScrollIndicator={false}>{data.map((item,i) => renderItem(item,i))}<View style={{height:40}} /></ScrollView>
        )}
      </SafeAreaView>
    </Modal>
  );
};

const st = StyleSheet.create({
  container:{flex:1,backgroundColor:'#0F172A'},header:{flexDirection:'row',alignItems:'center',paddingHorizontal:16,paddingVertical:12,backgroundColor:'#1E293B',borderBottomWidth:1,borderBottomColor:'#334155'},headerBtn:{width:44,height:44,justifyContent:'center',alignItems:'center'},headerTitle:{flex:1,fontSize:18,fontWeight:'700',color:'#F8FAFC',textAlign:'center'},content:{flex:1,paddingHorizontal:16},loadC:{flex:1,justifyContent:'center',alignItems:'center'},
  platformCard:{padding:20,backgroundColor:'#1E293B',borderRadius:16,marginTop:16,alignItems:'center'},platformTitle:{fontSize:18,fontWeight:'800',color:'#F8FAFC'},platformSub:{fontSize:12,color:'#94A3B8',marginTop:4},
  secCard:{flexDirection:'row',alignItems:'center',padding:14,backgroundColor:'#1E293B',borderRadius:12,marginTop:8,borderLeftWidth:4},secIcon:{width:40,height:40,borderRadius:10,justifyContent:'center',alignItems:'center',marginRight:12},secTitle:{flex:1,fontSize:15,fontWeight:'600',color:'#F8FAFC'},
  itemCard:{padding:14,backgroundColor:'#1E293B',borderRadius:10,marginTop:8},itemRow:{flexDirection:'row',justifyContent:'space-between',alignItems:'center'},itemTitle:{fontSize:14,fontWeight:'700',color:'#F8FAFC'},itemSub:{fontSize:11,color:'#94A3B8',marginTop:4},itemDesc:{fontSize:12,color:'#CBD5E1',marginTop:6,lineHeight:18},itemBullet:{fontSize:12,color:'#94A3B8',marginTop:2},
  langBadge:{fontSize:10,fontWeight:'700',color:'#3B82F6',backgroundColor:'#3B82F620',paddingHorizontal:6,paddingVertical:2,borderRadius:4},
  codeText:{fontSize:11,color:'#94A3B8',fontFamily:'monospace',marginTop:6,lineHeight:16},
  flashRow:{flexDirection:'row',marginTop:6},flashFront:{fontSize:12,fontWeight:'700',color:'#F59E0B',width:100},flashBack:{fontSize:12,color:'#CBD5E1',flex:1},
  compRow:{flexDirection:'row',gap:12,marginTop:6},compCell:{fontSize:11,color:'#94A3B8',backgroundColor:'#33415530',paddingHorizontal:8,paddingVertical:3,borderRadius:4},
  httpCode:{fontSize:18,fontWeight:'800',marginRight:12},
  sectionTitle:{fontSize:12,fontWeight:'700',color:'#64748B',letterSpacing:1,marginTop:16,marginBottom:8},
});
