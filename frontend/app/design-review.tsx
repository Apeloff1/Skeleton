/**
 * Design Review — scoped, explicit bridge between game KB and existing
 * design-spec compiler. Reads KB, keeps editable brief in memory, only
 * compiles on user action, never overwrites project content automatically.
 */
import React from 'react';
import { ActivityIndicator, SafeAreaView, ScrollView, StyleSheet,
  Text, TextInput, TouchableOpacity, View } from 'react-native';
import { useRouter, useLocalSearchParams } from 'expo-router';
import * as Clipboard from 'expo-clipboard';
import api from '../src/utils/apiClient';
import { validProjectId, projectHref } from '../src/product/worldWorkspace';
import { createReviewBrief, DESIGN_FOCUS, normalizeDesignReview } from '../src/product/designReview';
import type { DesignFocus, DesignReview } from '../src/product/designReview';

export default function DesignReviewRoute() {
  const router=useRouter();
  const params=useLocalSearchParams<{game?:string|string[]}>();
  const gameId=validProjectId(Array.isArray(params.game)?params.game[0]:params.game);
  const [kb,setKb]=React.useState<unknown>(null);
  const [sourceState,setSourceState]=React.useState<'loading'|'ready'|'error'>('loading');
  const [focus,setFocus]=React.useState<DesignFocus>('gameplay');
  const [includeSource,setIncludeSource]=React.useState(false);
  const [brief,setBrief]=React.useState('');
  const [dirty,setDirty]=React.useState(false);
  const [busy,setBusy]=React.useState(false);
  const [report,setReport]=React.useState<DesignReview|null>(null);
  const [previous,setPrevious]=React.useState<DesignReview|null>(null);
  const [error,setError]=React.useState('');
  const [copied,setCopied]=React.useState('');
  const serial=React.useRef(0);

  const load=React.useCallback(async (signal?:AbortSignal)=>{
    if(!gameId)return;
    const version=++serial.current;
    setSourceState('loading');
    try {
      const r=await api.get<any>(`/api/pipeline/${encodeURIComponent(gameId)}/kb`,
        {timeoutMs:12000,retries:0,signal});
      if(signal?.aborted||version!==serial.current)return;
      if(!r.ok||!r.data||r.data.error||!Array.isArray(r.data.artifacts)){
        setSourceState('error');return;
      }
      setKb(r.data);setSourceState('ready');
    }catch{if(!signal?.aborted&&version===serial.current)setSourceState('error');}
  },[gameId]);

  React.useEffect(()=>{
    const controller=new AbortController();
    serial.current++;
    setKb(null);setBrief('');setReport(null);setPrevious(null);setDirty(false);
    void load(controller.signal);
    return ()=>{serial.current++;controller.abort();};
  },[load]);

  const generated=React.useMemo(()=>createReviewBrief(gameId,kb,focus,includeSource),
    [gameId,kb,focus,includeSource]);

  React.useEffect(()=>{
    if(!dirty)setBrief(generated);
  },[generated,dirty]);

  const compile=React.useCallback(async()=>{
    const proposal=brief.trim();
    if(busy||proposal.length<8||proposal.length>6000)return;
    setBusy(true);setError('');setCopied('');
    const current=++serial.current;
    try {
      const result=await api.post<any>('/api/design-spec/compile',{brief:proposal},
        {timeoutMs:30000,retries:0});
      if(current!==serial.current)return;
      const normalized=result.ok ? normalizeDesignReview(result.data):null;
      if(!normalized){setError('The design compiler did not return a valid review. No project data was changed.');return;}
      setPrevious(report);
      setReport(normalized);
    }catch{if(current===serial.current)setError('Could not reach the design compiler. Your brief is still available.');}
    finally{if(current===serial.current)setBusy(false);}
  },[brief,busy,report]);

  const setDraft=(text:string)=>{setBrief(text.slice(0,6000));setDirty(true);setReport(null);setError('');};
  const reopen=(href:string)=>router.push(href as never);
  const copyBrief=async()=>{
    try{await Clipboard.setStringAsync(brief);setCopied('Review brief copied. Paste it into Jeeves when ready.');}
    catch{setCopied('Clipboard unavailable. Select the text directly to copy.');}
  };
  if(!gameId)return <SafeAreaView style={s.safe}><View style={s.panel}>
    <Text style={s.heading}>Select a real game</Text>
    <Text style={s.copy}>Design review needs a valid game context. It cannot guess a demo or another user project.</Text>
    <TouchableOpacity style={s.primary} accessibilityRole="button" onPress={()=>reopen('/my-builds')}>
      <Text style={s.primaryText}>Choose a build →</Text>
    </TouchableOpacity>
  </View></SafeAreaView>;
  return <SafeAreaView style={s.safe}><ScrollView keyboardShouldPersistTaps="handled"
    contentContainerStyle={s.page}>
    <TouchableOpacity onPress={()=>reopen(projectHref('/world-workbench',gameId)!)} accessibilityRole="button" style={s.back}>
      <Text style={s.link}>‹ World Workbench</Text>
    </TouchableOpacity>
    <View style={s.panel}>
      <Text style={s.kicker}>GAME DESIGN REVIEW</Text>
      <Text style={s.title}>Turn project evidence into a buildable design</Text>
      <Text style={s.copy}>Game: {gameId}</Text>
      <Text style={s.copy}>This bridge compiles only when you press the button. It does not mutate your game or automatically send existing knowledge to a model.</Text>
      {sourceState==='loading'?<ActivityIndicator color="#A78BFA"/>:null}
      {sourceState==='error'?<View style={s.warningPanel}><Text style={s.warning}>Project knowledge unavailable. You may still write a brief manually, but there is no verified project context.</Text>
        <TouchableOpacity style={s.secondary} onPress={()=>void load()}><Text style={s.secondaryText}>Retry source load</Text></TouchableOpacity>
      </View>:null}
      {sourceState==='ready'?<Text style={s.success}>Game knowledge loaded. Source notes are excluded until you opt in.</Text>:null}
    </View>
    <View style={s.panel}>
      <Text style={s.heading}>1 · Choose the review lens</Text>
      <View style={s.row}>{DESIGN_FOCUS.map(item=>
        <TouchableOpacity key={item.id} testID={`design-focus-${item.id}`} accessibilityRole="button"
          accessibilityState={{selected:focus===item.id}} onPress={()=>{setFocus(item.id);setDirty(false);setReport(null);}}
          style={[s.chip,focus===item.id&&s.activeChip]}>
          <Text style={s.chipText}>{item.title}</Text>
        </TouchableOpacity>)}</View>
      <TouchableOpacity accessibilityRole="checkbox" accessibilityState={{checked:includeSource}}
        testID="design-include-sources" style={s.secondary} onPress={()=>{setIncludeSource(v=>!v);setDirty(false);setReport(null);}}>
        <Text style={s.secondaryText}>{includeSource?'☑':'☐'} Include short, explicitly unverified knowledge summaries</Text>
      </TouchableOpacity>
      <Text style={s.copy}>Changing the lens or source inclusion regenerates the initial suggestion. Edit it before compiling.</Text>
    </View>
    <View style={s.panel}>
      <Text style={s.heading}>2 · Edit the brief</Text>
      <TextInput testID="design-review-brief" accessibilityLabel="Editable game design brief"
        multiline autoCapitalize="sentences" value={brief} onChangeText={setDraft}
        placeholder="Describe the core gameplay loop, audience, platform and constraints…"
        placeholderTextColor="#6D7790" style={s.input} maxLength={6000}/>
      <Text style={s.meta}>{brief.length}/6000 characters · {dirty?'Edited by you':'Generated starting point'}</Text>
      <View style={s.row}>
        <TouchableOpacity testID="design-review-reset" style={s.secondary} accessibilityRole="button"
          onPress={()=>{setBrief(generated);setDirty(false);setReport(null);setError('');}}>
          <Text style={s.secondaryText}>Restore suggestion</Text>
        </TouchableOpacity>
        <TouchableOpacity testID="design-review-compile" style={[s.primary,(busy||brief.trim().length<8)&&s.disabled]}
          accessibilityRole="button" disabled={busy||brief.trim().length<8} onPress={()=>void compile()}>
          <Text style={s.primaryText}>{busy?'Compiling…':'Compile design review →'}</Text>
        </TouchableOpacity>
      </View>
      {busy?<ActivityIndicator color="#A78BFA"/>:null}
      {!!error?<Text accessibilityRole="alert" style={s.warning}>{error}</Text>:null}
    </View>
    {report?<View style={s.panel} testID="design-review-result">
      <Text style={s.heading}>3 · Compiler verdict</Text>
      <Text style={[s.heading,{color:report.ready?'#84DFA2':'#FFD08A'}]}>{report.ready?'READY':'REVIEW REQUIRED'} {report.coherence!==null?`· coherence ${report.coherence}/100`:''}</Text>
      <Text style={s.copy}>Compiler status: {report.status} · Model: {report.model||'not disclosed'}</Text>
      {previous?.coherence!==null && previous?.coherence!==undefined && report.coherence!==null?
        <Text style={s.copy}>Previous review: {previous.coherence}/100 · current: {report.coherence}/100 (not a benchmark)</Text>:null}
      <Text style={s.heading}>{report.title}</Text>
      {report.logline?<Text style={s.copy}>{report.logline}</Text>:null}
      {report.coreLoop?<Text style={s.copy}>Core loop: {report.coreLoop}</Text>:null}
      <Text style={s.copy}>Scope: {report.scope||'not specified'} · Projected files: {report.targetFiles===null?'not supplied':String(report.targetFiles)}</Text>
      <Text style={s.subhead}>Coherence gaps ({report.gaps.length})</Text>
      {report.gaps.length?report.gaps.map((item,i)=><Text key={i} style={s.warning}>• {item}</Text>):<Text style={s.copy}>No gaps reported by compiler; review independently before shipping.</Text>}
      <Text style={s.subhead}>Mechanics and systems</Text>
      {report.mechanics.map((item,i)=><Text key={`m${i}`} style={s.copy}>• {item}</Text>)}
      {report.systems.map((item,i)=><Text key={`s${i}`} style={s.copy}>• {item}</Text>)}
      <Text style={s.subhead}>Implementation risks</Text>
      {report.risks.length?report.risks.map((item,i)=><Text key={i} style={s.warning}>• {item}</Text>):
        <Text style={s.copy}>No risks returned; this does not prove the plan is risk-free.</Text>}
      <TouchableOpacity accessibilityRole="button" style={s.secondary}
        onPress={()=>{setDraft(brief+'\n\nRevision request: Address the listed gaps and risks, with concrete constraints and acceptance criteria.');setReport(null);}}>
        <Text style={s.secondaryText}>Revise the brief based on this review</Text>
      </TouchableOpacity>
    </View>:null}
    <View style={s.panel}>
      <Text style={s.heading}>4 · Continue without losing your game</Text>
      <Text style={s.copy}>Copying is explicit. No transcript, model response or private project content is written to generic navigation storage.</Text>
      <View style={s.row}>
        <TouchableOpacity testID="design-review-copy" accessibilityRole="button" style={s.secondary} onPress={()=>void copyBrief()}>
          <Text style={s.secondaryText}>Copy brief for Jeeves</Text>
        </TouchableOpacity>
        <TouchableOpacity accessibilityRole="button" style={s.secondary} onPress={()=>reopen('/jeeves-chat')}>
          <Text style={s.secondaryText}>Open Jeeves chat →</Text>
        </TouchableOpacity>
        <TouchableOpacity accessibilityRole="button" style={s.secondary} onPress={()=>reopen(projectHref('/game-kb',gameId)!)}>
          <Text style={s.secondaryText}>Review game KB →</Text>
        </TouchableOpacity>
        <TouchableOpacity testID="design-review-to-studio" accessibilityRole="button" style={s.primary}
          onPress={()=>reopen(projectHref('/studio',gameId)!)}>
          <Text style={s.primaryText}>Continue in Studio →</Text>
        </TouchableOpacity>
      </View>
      {!!copied?<Text accessibilityLiveRegion="polite" style={s.success}>{copied}</Text>:null}
    </View>
  </ScrollView></SafeAreaView>;
}
const s=StyleSheet.create({
  safe:{flex:1,backgroundColor:'#090B13'},
  page:{padding:18,gap:14,paddingBottom:55,maxWidth:1000,width:'100%',alignSelf:'center'},
  panel:{backgroundColor:'#121A2B',borderWidth:1,borderColor:'#2B3952',borderRadius:16,padding:17,gap:12},
  back:{minHeight:44,justifyContent:'center'},link:{color:'#BCAEFF',fontWeight:'800',fontSize:13},
  kicker:{color:'#BCAEFF',fontWeight:'900',fontSize:11,letterSpacing:1.4},
  title:{color:'#F8FAFC',fontSize:24,fontWeight:'900'},
  heading:{color:'#F8FAFC',fontSize:16,fontWeight:'800'},
  subhead:{color:'#E0E8FA',fontSize:13,fontWeight:'800',marginTop:8},
  copy:{color:'#ADBBD0',fontSize:12,lineHeight:19},
  warning:{color:'#F7BF8D',fontSize:12,lineHeight:20},
  warningPanel:{gap:9},
  success:{color:'#91E7AD',fontSize:12},
  meta:{color:'#8C9AB2',fontSize:11},
  row:{flexDirection:'row',flexWrap:'wrap',gap:9,alignItems:'center'},
  chip:{padding:11,backgroundColor:'#202A3B',borderRadius:11,borderWidth:1,borderColor:'#42516C'},
  activeChip:{borderColor:'#A78BFA',backgroundColor:'#302B53'},
  chipText:{color:'#F4F0FF',fontSize:12,fontWeight:'800'},
  input:{minHeight:155,maxHeight:320,borderColor:'#3A4A62',borderWidth:1,color:'#F2F5FA',
    borderRadius:12,padding:14,textAlignVertical:'top',backgroundColor:'#0B1220',fontSize:13},
  primary:{backgroundColor:'#6752D4',borderRadius:11,minHeight:44,paddingHorizontal:14,paddingVertical:12,justifyContent:'center'},
  primaryText:{color:'#FFFFFF',fontSize:12,fontWeight:'900'},
  secondary:{borderWidth:1,borderColor:'#56637C',borderRadius:11,minHeight:44,paddingHorizontal:13,paddingVertical:12,justifyContent:'center'},
  secondaryText:{color:'#E0E6F7',fontSize:12,fontWeight:'800'},
  disabled:{opacity:0.45},
});