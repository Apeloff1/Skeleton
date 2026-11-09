/**
 * Rosetta Playground — Compare code across 453 languages, execute in playground
 */
import React, { useState, useEffect } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, Modal, ScrollView, FlatList, ActivityIndicator, TextInput } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import { apiFetch } from '../../utils/apiController';
const API = process.env.EXPO_PUBLIC_BACKEND_URL || '';

const EXEC_LANGS = new Set(['Python','JavaScript','TypeScript','Go','Rust','C','C++']);

interface Props { visible: boolean; onClose: () => void; }

export const RosettaPlaygroundModal: React.FC<Props> = ({ visible, onClose }) => {
  const [concepts, setConcepts] = useState<any[]>([]);
  const [selectedConcept, setSelectedConcept] = useState<string|null>(null);
  const [entries, setEntries] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [running, setRunning] = useState<string|null>(null);
  const [output, setOutput] = useState<Record<string,string>>({});

  useEffect(() => { if (visible) loadConcepts(); }, [visible]);

  const loadConcepts = async () => {
    setLoading(true);
    try {
      const r = await apiFetch(`${API}/api/dictionary/rosetta/concepts`);
      if (r.ok) { const d = await r.json(); setConcepts(d.concepts || []); }
    } catch {}
    setLoading(false);
  };

  const loadConcept = async (concept: string) => {
    setSelectedConcept(concept);
    setLoading(true);
    try {
      const r = await apiFetch(`${API}/api/dictionary/rosetta/${concept}`);
      if (r.ok) { const d = await r.json(); setEntries(d.languages || []); }
    } catch {}
    setLoading(false);
  };

  const runCode = async (lang: string, code: string) => {
    const langMap: Record<string,string> = {'Python':'python','JavaScript':'javascript','TypeScript':'typescript','Go':'go','Rust':'rust','C':'c','C++':'cpp'};
    setRunning(lang);
    try {
      const r = await apiFetch(`${API}/api/playground/run`, {
        method: 'POST', headers: {'Content-Type':'application/json'},
        body: JSON.stringify({language: langMap[lang] || lang.toLowerCase(), code})
      });
      if (r.ok) {
        const d = await r.json();
        setOutput(prev => ({...prev, [lang]: d.output || d.error || 'No output'}));
      }
    } catch { setOutput(prev => ({...prev, [lang]: 'Error connecting'})); }
    setRunning(null);
  };

  const filtered = search ? entries.filter(e => e.language.toLowerCase().includes(search.toLowerCase())) : entries;

  if (selectedConcept) {
    return (
      <Modal visible={visible} animationType="slide" onRequestClose={() => setSelectedConcept(null)}>
        <View style={st.container}>
          <View style={st.header}>
            <TouchableOpacity onPress={() => { setSelectedConcept(null); setOutput({}); }} style={st.hBtn}>
              <Ionicons name="arrow-back" size={24} color="#F8FAFC" />
            </TouchableOpacity>
            <View style={{flex:1,alignItems:'center'}}>
              <Text style={st.hTitle}>{selectedConcept.replace(/_/g,' ').replace(/\b\w/g,c=>c.toUpperCase())}</Text>
              <Text style={st.hSub}>{entries.length} languages</Text>
            </View>
            <View style={st.hBtn} />
          </View>
          <View style={st.searchRow}>
            <Ionicons name="search" size={16} color="#64748B" />
            <TextInput style={st.searchInput} placeholder="Filter languages..." placeholderTextColor="#64748B" value={search} onChangeText={setSearch} />
          </View>
          {loading ? <View style={st.loadWrap}><ActivityIndicator color="#F59E0B" size="large" /></View> : (
            <FlatList
              data={filtered}
              keyExtractor={item => item.id}
              contentContainerStyle={st.listContent}
              renderItem={({item}) => {
                const canExec = EXEC_LANGS.has(item.language);
                const hasOutput = output[item.language];
                return (
                  <View style={[st.codeCard, item.source === 'handcrafted' && st.handcrafted]}>
                    <View style={st.cardHeader}>
                      <Text style={st.langName}>{item.language}</Text>
                      <View style={st.badges}>
                        {item.source === 'handcrafted' && <View style={st.hcBadge}><Text style={st.hcText}>HANDCRAFTED</Text></View>}
                        {canExec && (
                          <TouchableOpacity style={st.runBtn} onPress={() => runCode(item.language, item.code)} disabled={running === item.language}>
                            {running === item.language ? <ActivityIndicator size="small" color="#22C55E" /> : <><Ionicons name="play" size={14} color="#22C55E" /><Text style={st.runText}>Run</Text></>}
                          </TouchableOpacity>
                        )}
                      </View>
                    </View>
                    <ScrollView horizontal style={st.codeScroll}>
                      <Text style={st.codeText}>{item.code}</Text>
                    </ScrollView>
                    <Text style={st.lineCount}>{item.code_lines} lines • {item.language_family || 'other'}</Text>
                    {hasOutput && (
                      <View style={st.outputBox}>
                        <Text style={st.outputLabel}>OUTPUT</Text>
                        <Text style={st.outputText}>{hasOutput}</Text>
                      </View>
                    )}
                  </View>
                );
              }}
              initialNumToRender={10}
              maxToRenderPerBatch={10}
            />
          )}
        </View>
      </Modal>
    );
  }

  return (
    <Modal visible={visible} animationType="slide" onRequestClose={onClose}>
      <View style={st.container}>
        <View style={st.header}>
          <TouchableOpacity testID="rp-close" onPress={onClose} style={st.hBtn}>
            <Ionicons name="close" size={24} color="#F8FAFC" />
          </TouchableOpacity>
          <View style={{flex:1,alignItems:'center'}}>
            <Text style={st.hTitle}>Rosetta Playground</Text>
            <Text style={st.hSub}>453 Languages × 15 Concepts</Text>
          </View>
          <View style={st.hBtn} />
        </View>
        {loading ? <View style={st.loadWrap}><ActivityIndicator color="#F59E0B" size="large" /></View> : (
          <FlatList
            data={concepts}
            keyExtractor={item => item.concept}
            contentContainerStyle={st.listContent}
            renderItem={({item}) => (
              <TouchableOpacity style={st.conceptCard} onPress={() => loadConcept(item.concept)}>
                <View style={st.conceptTop}>
                  <Text style={st.conceptName}>{item.concept.replace(/_/g,' ').replace(/\b\w/g, (c:string)=>c.toUpperCase())}</Text>
                  <Ionicons name="chevron-forward" size={18} color="#64748B" />
                </View>
                <Text style={st.conceptCount}>{item.languages} languages</Text>
              </TouchableOpacity>
            )}
          />
        )}
      </View>
    </Modal>
  );
};

const st = StyleSheet.create({
  container:{flex:1,backgroundColor:'#0F172A'},
  header:{flexDirection:'row',alignItems:'center',paddingHorizontal:16,paddingVertical:12,backgroundColor:'#1E293B',borderBottomWidth:1,borderBottomColor:'#334155'},
  hBtn:{width:44,height:44,justifyContent:'center',alignItems:'center'},
  hTitle:{fontSize:18,fontWeight:'700',color:'#F8FAFC'},
  hSub:{fontSize:12,color:'#94A3B8',marginTop:2},
  searchRow:{flexDirection:'row',alignItems:'center',backgroundColor:'#1E293B',marginHorizontal:12,marginTop:10,borderRadius:10,paddingHorizontal:12,gap:8},
  searchInput:{flex:1,color:'#F8FAFC',fontSize:14,paddingVertical:10},
  loadWrap:{flex:1,justifyContent:'center',alignItems:'center'},
  listContent:{paddingHorizontal:12,paddingTop:8,paddingBottom:40},
  conceptCard:{backgroundColor:'#1E293B',borderRadius:12,padding:16,marginBottom:8},
  conceptTop:{flexDirection:'row',justifyContent:'space-between',alignItems:'center'},
  conceptName:{fontSize:16,fontWeight:'700',color:'#F8FAFC'},
  conceptCount:{fontSize:12,color:'#64748B',marginTop:4},
  codeCard:{backgroundColor:'#1E293B',borderRadius:12,padding:14,marginBottom:10,borderLeftWidth:3,borderLeftColor:'#334155'},
  handcrafted:{borderLeftColor:'#F59E0B'},
  cardHeader:{flexDirection:'row',justifyContent:'space-between',alignItems:'center',marginBottom:8},
  langName:{fontSize:15,fontWeight:'700',color:'#F8FAFC'},
  badges:{flexDirection:'row',gap:8,alignItems:'center'},
  hcBadge:{backgroundColor:'#F59E0B20',paddingHorizontal:8,paddingVertical:2,borderRadius:6},
  hcText:{fontSize:9,fontWeight:'800',color:'#F59E0B',letterSpacing:0.5},
  runBtn:{flexDirection:'row',alignItems:'center',gap:4,backgroundColor:'#22C55E15',paddingHorizontal:10,paddingVertical:4,borderRadius:8},
  runText:{fontSize:12,fontWeight:'700',color:'#22C55E'},
  codeScroll:{maxHeight:200},
  codeText:{color:'#A7F3D0',fontFamily:'monospace',fontSize:12,lineHeight:18},
  lineCount:{fontSize:10,color:'#475569',marginTop:6},
  outputBox:{backgroundColor:'#0D1117',borderRadius:8,padding:10,marginTop:8},
  outputLabel:{fontSize:9,fontWeight:'800',color:'#64748B',letterSpacing:1,marginBottom:4},
  outputText:{color:'#8B949E',fontFamily:'monospace',fontSize:12},
});
