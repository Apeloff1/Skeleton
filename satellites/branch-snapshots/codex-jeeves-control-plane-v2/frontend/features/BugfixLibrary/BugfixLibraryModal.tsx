import React, { useState, useEffect, useCallback } from 'react';
import { API_BASE } from '../../utils/apiBase';
import { View, Text, StyleSheet, TouchableOpacity, ScrollView, Modal, ActivityIndicator, SafeAreaView, TextInput } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import { apiFetch } from '../../utils/apiController';
const API = API_BASE;
const SEV_COLORS: Record<string,string> = { critical:'#EF4444', high:'#F59E0B', medium:'#3B82F6', common:'#10B981', low:'#94A3B8', advanced:'#8B5CF6' };

interface Props { visible: boolean; onClose: () => void; }

export const BugfixLibraryModal: React.FC<Props> = ({ visible, onClose }) => {
  const [categories, setCategories] = useState<any[]>([]);
  const [entries, setEntries] = useState<any[]>([]);
  const [workarounds, setWorkarounds] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [view, setView] = useState<'home'|'list'|'search'|'detail'|'workarounds'>('home');
  const [selectedCat, setSelectedCat] = useState('');
  const [selectedEntry, setSelectedEntry] = useState<any>(null);
  const [searchQ, setSearchQ] = useState('');
  const [totalBugs, setTotalBugs] = useState(0);
  const [waCats, setWaCats] = useState<any[]>([]);

  const loadHome = useCallback(async () => {
    try { setLoading(true);
      const [bRes, wRes] = await Promise.all([apiFetch(`${API}/api/academy/bugfix/categories`), apiFetch(`${API}/api/academy/workarounds/categories`)]);
      const bData = await bRes.json(); const wData = await wRes.json();
      setCategories(bData.categories||[]); setTotalBugs(bData.total||0);
      setWaCats(wData.categories||[]);
    } catch(e){console.error(e)} finally{setLoading(false)}
  }, []);

  const loadCategory = async (cat: string) => {
    setLoading(true); setSelectedCat(cat);
    const res = await apiFetch(`${API}/api/academy/bugfix?category=${cat}&limit=100`);
    const data = await res.json(); setEntries(data.entries||[]); setView('list'); setLoading(false);
  };

  const doSearch = async () => {
    if (!searchQ.trim()) return;
    setLoading(true);
    const [bRes, wRes] = await Promise.all([apiFetch(`${API}/api/academy/bugfix/search?q=${encodeURIComponent(searchQ)}`), apiFetch(`${API}/api/academy/workarounds/search?q=${encodeURIComponent(searchQ)}`)]);
    const bData = await bRes.json(); const wData = await wRes.json();
    setEntries(bData.results||[]); setWorkarounds(wData.results||[]); setView('search'); setLoading(false);
  };

  const loadWorkarounds = async (cat: string) => {
    setLoading(true); setSelectedCat(cat);
    const res = await apiFetch(`${API}/api/academy/workarounds?category=${cat}&limit=100`);
    const data = await res.json(); setWorkarounds(data.workarounds||[]); setView('workarounds'); setLoading(false);
  };

  useEffect(() => { if (visible) { setView('home'); loadHome(); } }, [visible, loadHome]);

  const handleBack = () => {
    if (selectedEntry) setSelectedEntry(null);
    else if (view !== 'home') { setView('home'); setEntries([]); setWorkarounds([]); }
    else onClose();
  };

  const renderHome = () => (
    <ScrollView style={st.content} showsVerticalScrollIndicator={false}>
      <View style={st.searchBar}>
        <Ionicons name="search" size={18} color="#94A3B8" />
        <TextInput testID="bugfix-search" style={st.searchInput} placeholder="Search errors, bugs, workarounds..." placeholderTextColor="#64748B" value={searchQ} onChangeText={setSearchQ} onSubmitEditing={doSearch} returnKeyType="search" />
      </View>
      <View style={st.statsRow}>
        <View style={st.statBox}><Text style={st.statNum}>{totalBugs}</Text><Text style={st.statLabel}>Bug/Fixes</Text></View>
        <View style={st.statBox}><Text style={st.statNum}>{waCats.reduce((a:number,c:any)=>a+c.count,0)}</Text><Text style={st.statLabel}>Workarounds</Text></View>
        <View style={st.statBox}><Text style={st.statNum}>{categories.length}</Text><Text style={st.statLabel}>Categories</Text></View>
      </View>
      <Text style={st.sectionTitle}>BUG/FIX CATEGORIES</Text>
      {categories.slice(0,15).map((c: any) => (
        <TouchableOpacity key={c.category} testID={`bf-cat-${c.category}`} style={st.catCard} onPress={() => loadCategory(c.category)}>
          <Text style={st.catName}>{c.category}</Text><Text style={st.catCount}>{c.count}</Text>
        </TouchableOpacity>
      ))}
      <Text style={st.sectionTitle}>WORKAROUND CATEGORIES</Text>
      {waCats.map((c: any) => (
        <TouchableOpacity key={c.category} testID={`wa-cat-${c.category}`} style={[st.catCard, {borderLeftColor:'#F59E0B',borderLeftWidth:3}]} onPress={() => loadWorkarounds(c.category)}>
          <Text style={st.catName}>{c.category}</Text><Text style={st.catCount}>{c.count}</Text>
        </TouchableOpacity>
      ))}
    </ScrollView>
  );

  const renderEntry = (e: any) => (
    <TouchableOpacity key={e.id} style={st.entryCard} onPress={() => setSelectedEntry(e)}>
      <View style={st.entryTop}><Text style={st.entryTitle} numberOfLines={2}>{e.title || e.issue}</Text>
        <View style={[st.sevBadge,{backgroundColor:(SEV_COLORS[e.severity]||'#888')+'25'}]}><Text style={[st.sevText,{color:SEV_COLORS[e.severity]||'#888'}]}>{e.severity||'info'}</Text></View>
      </View>
      <Text style={st.entryType}>{e.error_type||e.category}</Text>
    </TouchableOpacity>
  );

  const renderDetail = () => {
    if (!selectedEntry) return null;
    const e = selectedEntry;
    return (
      <ScrollView style={st.content} showsVerticalScrollIndicator={false}>
        <Text style={st.detailTitle}>{e.title || e.issue}</Text>
        {e.severity && <View style={[st.sevBadge,{backgroundColor:(SEV_COLORS[e.severity]||'#888')+'25',alignSelf:'flex-start',marginTop:8}]}><Text style={[st.sevText,{color:SEV_COLORS[e.severity]||'#888'}]}>{e.severity}</Text></View>}
        {e.error_type && <><Text style={st.fieldLabel}>Error Type</Text><Text style={st.fieldVal}>{e.error_type}</Text></>}
        {e.root_cause && <><Text style={st.fieldLabel}>Root Cause</Text><Text style={st.fieldVal}>{e.root_cause}</Text></>}
        {(e.fix||e.solution) && <><Text style={[st.fieldLabel,{color:'#10B981'}]}>Fix / Solution</Text><View style={st.fixBox}><Text style={st.fixText}>{e.fix||e.solution}</Text></View></>}
        {e.alternative && <><Text style={[st.fieldLabel,{color:'#3B82F6'}]}>Alternative</Text><View style={st.fixBox}><Text style={st.fixText}>{e.alternative}</Text></View></>}
        {e.prevention && <><Text style={[st.fieldLabel,{color:'#F59E0B'}]}>Prevention</Text><Text style={st.fieldVal}>{e.prevention}</Text></>}
      </ScrollView>
    );
  };

  return (
    <Modal visible={visible} animationType="slide" onRequestClose={handleBack}>
      <SafeAreaView style={st.container}>
        <View style={st.header}>
          <TouchableOpacity testID="bf-back" onPress={handleBack} style={st.headerBtn}><Ionicons name={view==='home'&&!selectedEntry?'close':'arrow-back'} size={24} color="#F8FAFC" /></TouchableOpacity>
          <Text style={st.headerTitle} numberOfLines={1}>{selectedEntry ? 'Detail' : view==='workarounds' ? `Workarounds: ${selectedCat}` : view==='list' ? selectedCat : view==='search' ? 'Search Results' : 'Bug/Fix & Workarounds'}</Text>
          <View style={{width:44}} />
        </View>
        {loading ? <View style={st.loadC}><ActivityIndicator size="large" color="#EF4444" /></View> : selectedEntry ? renderDetail() : view==='home' ? renderHome() : (
          <ScrollView style={st.content} showsVerticalScrollIndicator={false}>
            {entries.length > 0 && <><Text style={st.sectionTitle}>BUG/FIXES ({entries.length})</Text>{entries.map(renderEntry)}</>}
            {workarounds.length > 0 && <><Text style={st.sectionTitle}>WORKAROUNDS ({workarounds.length})</Text>{workarounds.map(renderEntry)}</>}
          </ScrollView>
        )}
      </SafeAreaView>
    </Modal>
  );
};

const st = StyleSheet.create({
  container:{flex:1,backgroundColor:'#0F172A'},header:{flexDirection:'row',alignItems:'center',paddingHorizontal:16,paddingVertical:12,backgroundColor:'#1E293B',borderBottomWidth:1,borderBottomColor:'#334155'},headerBtn:{width:44,height:44,justifyContent:'center',alignItems:'center'},headerTitle:{flex:1,fontSize:18,fontWeight:'700',color:'#F8FAFC',textAlign:'center'},content:{flex:1,paddingHorizontal:16},loadC:{flex:1,justifyContent:'center',alignItems:'center'},
  searchBar:{flexDirection:'row',alignItems:'center',backgroundColor:'#1E293B',borderRadius:12,paddingHorizontal:14,marginTop:16,borderWidth:1,borderColor:'#334155'},searchInput:{flex:1,color:'#F8FAFC',fontSize:14,paddingVertical:12,marginLeft:8},
  statsRow:{flexDirection:'row',justifyContent:'space-around',marginTop:16,backgroundColor:'#1E293B',borderRadius:12,paddingVertical:16},statBox:{alignItems:'center'},statNum:{fontSize:20,fontWeight:'800',color:'#F8FAFC'},statLabel:{fontSize:10,color:'#94A3B8',marginTop:2},
  sectionTitle:{fontSize:12,fontWeight:'700',color:'#64748B',letterSpacing:1,marginTop:20,marginBottom:10},
  catCard:{flexDirection:'row',justifyContent:'space-between',alignItems:'center',padding:14,backgroundColor:'#1E293B',borderRadius:10,marginBottom:6},catName:{fontSize:14,fontWeight:'600',color:'#F8FAFC',textTransform:'capitalize'},catCount:{fontSize:14,fontWeight:'700',color:'#94A3B8'},
  entryCard:{padding:14,backgroundColor:'#1E293B',borderRadius:10,marginBottom:8},entryTop:{flexDirection:'row',justifyContent:'space-between',alignItems:'flex-start'},entryTitle:{fontSize:14,fontWeight:'600',color:'#F8FAFC',flex:1,marginRight:8},entryType:{fontSize:11,color:'#64748B',marginTop:4},
  sevBadge:{paddingHorizontal:8,paddingVertical:3,borderRadius:6},sevText:{fontSize:10,fontWeight:'700',textTransform:'uppercase'},
  detailTitle:{fontSize:20,fontWeight:'800',color:'#F8FAFC',paddingTop:20},fieldLabel:{fontSize:12,fontWeight:'700',color:'#94A3B8',marginTop:16,letterSpacing:0.5},fieldVal:{fontSize:14,color:'#CBD5E1',marginTop:4,lineHeight:22},
  fixBox:{backgroundColor:'#10B98115',borderRadius:10,padding:14,marginTop:6,borderLeftWidth:3,borderLeftColor:'#10B981'},fixText:{fontSize:13,color:'#E2E8F0',lineHeight:20},
});
