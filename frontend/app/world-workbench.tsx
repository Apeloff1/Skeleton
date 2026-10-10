/**
 * World Workbench — project-focused orchestration of existing game tools.
 *
 * Read-only world evidence is projected from the canonical game KB. Forge
 * requests use the existing pipeline and never claim completion until its job
 * endpoint reports a terminal success and KB is re-read.
 */
import React from 'react';
import { ActivityIndicator, SafeAreaView, ScrollView, StyleSheet,
  Text, TouchableOpacity, View, useWindowDimensions } from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import api from '../src/utils/apiClient';
import { watchBuildJob } from '../src/product/buildJobLifecycle';
import {
  WORLD_STAGES, mapWorldEvidence, mountedWorldSystems, projectHref,
  readArtifactPreview, validProjectId, worldProjectLinks,
} from '../src/product/worldWorkspace';
import type { WorldStageKey } from '../src/product/worldWorkspace';

type State = 'loading' | 'ready' | 'offline';
const COLORS = { background:'#080A11', panel:'#111827', border:'#293247',
  text:'#F2F5FF', dim:'#A4B1C9', accent:'#A78BFA', green:'#85E5AE', amber:'#FFD28A' };

export default function WorldWorkbench() {
  const router = useRouter();
  const params = useLocalSearchParams<{ game?: string|string[]; build?: string|string[] }>();
  const gameId = validProjectId(Array.isArray(params.game) ? params.game[0] : params.game) ||
    validProjectId(Array.isArray(params.build) ? params.build[0] : params.build);
  const { width } = useWindowDimensions();
  const wide = width >= 780;

  const [kb, setKb] = React.useState<unknown>(null);
  const [state, setState] = React.useState<State>('loading');
  const [message, setMessage] = React.useState('');
  const [systems, setSystems] = React.useState<ReturnType<typeof mountedWorldSystems>>([]);
  const [contextStatus, setContextStatus] = React.useState<'loading'|'available'|'unavailable'>('loading');
  const [selection, setSelection] = React.useState<WorldStageKey>('world');
  const [jobStage, setJobStage] = React.useState<WorldStageKey | null>(null);
  const [jobMessage, setJobMessage] = React.useState('');
  const jobController = React.useRef<AbortController | null>(null);
  const loadRequest = React.useRef(0);

  const load = React.useCallback(async (signal?: AbortSignal) => {
    if (!gameId) { setState('offline'); return; }
    const requestId = ++loadRequest.current;
    const isCurrent = () => requestId === loadRequest.current && !signal?.aborted;
    setState('loading');
    setMessage('');
    // Independently failing secondary surfaces must not block the game KB.
    const [knowledge, mounted, assetContext] = await Promise.allSettled([
      api.get<any>(`/api/pipeline/${encodeURIComponent(gameId)}/kb`,
        { timeoutMs: 12_000, retries: 0, signal }),
      api.get<any>(`/api/galaxy-studio/systems/build/${encodeURIComponent(gameId)}`,
        { timeoutMs: 9_000, retries: 0, signal }),
      api.get<any>(`/api/assets/genesis/game/${encodeURIComponent(gameId)}`,
        { timeoutMs: 9_000, retries: 0, signal }),
    ]);
    if (!isCurrent()) return;
    if (mounted.status === 'fulfilled' && mounted.value.ok && mounted.value.data) {
      setSystems(mountedWorldSystems(mounted.value.data));
    } else { setSystems([]); }
    setContextStatus(assetContext.status === 'fulfilled' && assetContext.value.ok && assetContext.value.data
      ? 'available' : 'unavailable');
    if (knowledge.status === 'fulfilled' && knowledge.value.ok && knowledge.value.data
      && !knowledge.value.data.error && Array.isArray(knowledge.value.data.artifacts)) {
      setKb(knowledge.value.data);
      setState('ready');
    } else {
      setMessage('Project knowledge could not be read. Refresh to retry; no build stages were inferred.');
      setState('offline');
    }
  }, [gameId]);

  React.useEffect(() => {
    // A route reused for another game must never display the previous
    // game's knowledge or systems, even if the new game's API is offline.
    setKb(null);
    setSystems([]);
    setContextStatus('loading');
    setJobMessage('');
    setSelection('world');
    const controller = new AbortController();
    void load(controller.signal);
    return () => {
      controller.abort();
      jobController.current?.abort();
      jobController.current = null;
      loadRequest.current += 1;
    };
  }, [load]);

  const forge = React.useCallback(async (stage: WorldStageKey) => {
    if (!gameId || state !== 'ready' || jobController.current) return;
    const controller = new AbortController();
    jobController.current = controller;
    setJobStage(stage);
    setJobMessage('Submitting stage to the game pipeline…');
    try {
      const result = await api.post<any>(
        `/api/pipeline/${encodeURIComponent(gameId)}/forge/${encodeURIComponent(stage)}/async`,
        {}, { timeoutMs: 15_000, retries: 0, signal:controller.signal });
      const id = result.data?.job_id;
      if (!result.ok || typeof id !== 'string' || !id) {
        setJobMessage('The service did not accept this forge request. Nothing is confirmed changed.');
        return;
      }
      const outcome = await watchBuildJob(
        () => api.get<any>(`/api/playable/job/${encodeURIComponent(id)}`,
          { timeoutMs: 12_000, retries:0, signal:controller.signal }),
        { signal:controller.signal, intervalMs:3_000, maxChecks:120,
          onPending: count => {if(count===1 || count%8===0) setJobMessage('Forge stage queued or running…');} },
      );
      if (controller.signal.aborted) return;
      setJobMessage(outcome.message);
      if (outcome.phase === 'completed') await load();
    } catch {
      if (!controller.signal.aborted) setJobMessage('Cannot confirm forge outcome. Refresh before starting another job.');
    } finally {
      if (jobController.current === controller) jobController.current=null;
      if (!controller.signal.aborted) setJobStage(null);
    }
  }, [gameId, load, state]);

  const evidence = React.useMemo(() => mapWorldEvidence(kb), [kb]);
  const selected = evidence.find(item => item.id === selection)!;
  const available = evidence.filter(item => item.present).length;
  const links = worldProjectLinks(gameId);
  const go = (href: string) => router.push(href as never);
  const active = state==='ready';
  const worldKey = selected.rawNames[0] || '';
  const preview = worldKey ? readArtifactPreview(kb,worldKey) : null;

  if (!gameId) {
    return <SafeAreaView style={styles.safe} testID="world-workbench-no-project">
      <View style={styles.empty}>
        <Text style={styles.title}>Choose a game first</Text>
        <Text style={styles.body}>The workbench needs a real build ID to avoid mixing worlds from different projects.</Text>
        <TouchableOpacity accessibilityRole="button" style={styles.primary}
          onPress={() => go('/my-builds')}>
          <Text style={styles.primaryText}>Browse My Builds →</Text>
        </TouchableOpacity>
      </View>
    </SafeAreaView>;
  }
  return (
    <SafeAreaView style={styles.safe}>
      <ScrollView contentContainerStyle={[styles.page,wide&&styles.wide]} keyboardShouldPersistTaps="handled">
        <TouchableOpacity testID="world-workbench-back" onPress={() => go(projectHref('/studio',gameId)!)}
          accessibilityRole="button" style={styles.back}>
          <Text style={styles.link}>‹ Back to this game in Studio</Text>
        </TouchableOpacity>
        <View style={styles.hero}>
          <Text style={styles.kicker}>WORLD WORKBENCH</Text>
          <Text style={styles.title}>One game. Every world system.</Text>
          <Text style={styles.body}>Build-scoped world content, narrative, systems and assets. Work here, then continue in Studio without changing projects.</Text>
          <Text style={styles.projectId}>Game · {gameId}</Text>
          <View style={styles.metrics}>
            <View style={styles.metric}><Text style={styles.value}>{active ? `${available}/4` : '—'}</Text><Text style={styles.hint}>forge stages present</Text></View>
            <View style={styles.metric}><Text style={styles.value}>{systems.length}</Text><Text style={styles.hint}>mounted systems</Text></View>
            <View style={styles.metric}><Text style={styles.value}>{contextStatus==='available'?'Ready':contextStatus==='loading'?'…':'Unavailable'}</Text><Text style={styles.hint}>asset context</Text></View>
          </View>
        </View>
        {state==='loading' ? <View style={styles.panel}><ActivityIndicator color={COLORS.accent}/><Text style={styles.body}>Reading current game evidence…</Text></View> : null}
        {!!message && <View style={styles.panel} testID="world-read-error">
          <Text style={styles.warning}>{message}</Text>
          <TouchableOpacity testID="world-retry" accessibilityRole="button"
            style={styles.secondary} onPress={() => void load()}>
            <Text style={styles.secondaryText}>Retry evidence fetch</Text>
          </TouchableOpacity>
        </View>}
        {!!jobMessage && <View style={styles.panel} testID="world-job-status">
          <Text accessibilityLiveRegion="polite" style={styles.body}>{jobMessage}</Text>
          <TouchableOpacity accessibilityRole="button" disabled={!!jobStage}
            onPress={() => void load()} style={[styles.secondary,!!jobStage&&styles.disabled]}>
            <Text style={styles.secondaryText}>Refresh authoritative results</Text>
          </TouchableOpacity>
        </View>}
        {kb && state!=='loading' ? <View style={styles.panel}>
          <View style={styles.row}>
            <Text style={styles.heading}>Game knowledge evidence</Text>
            <TouchableOpacity testID="world-refresh" accessibilityRole="button" onPress={() => void load()}>
              <Text style={styles.link}>Refresh</Text>
            </TouchableOpacity>
          </View>
          <Text style={styles.body}>Select an area to inspect server-reported artifacts. A missing artifact means there is no confirmed evidence, not that creation automatically failed.</Text>
          <View style={styles.stageGrid}>
            {evidence.map(item => (
              <TouchableOpacity key={item.id} testID={`world-stage-${item.id}`}
                accessibilityRole="button" accessibilityState={{ selected:selection===item.id }}
                onPress={() => setSelection(item.id)}
                style={[styles.stage,wide&&styles.stageWide,selection===item.id&&styles.stageSelected]}>
                <Text style={styles.stageTitle}>{item.title}</Text>
                <Text style={[styles.label,{color:item.present?COLORS.green:COLORS.amber}]}>{item.present?'Artifacts present':'Missing or unconfirmed'}</Text>
                <Text style={styles.hint}>{item.available}/{item.total} artifacts</Text>
              </TouchableOpacity>
            ))}
          </View>
          <View style={styles.detail}>
            <Text style={styles.heading}>{selected.title}</Text>
            <Text style={styles.body}>{WORLD_STAGES.find(s=>s.id===selected.id)?.purpose}</Text>
            {selected.rawNames.map((name,i)=><Text key={name+i} style={styles.file}>• {name}</Text>)}
            {selected.summaries.map((value,i)=><Text key={i} style={styles.body}>{value}</Text>)}
            {!selected.present ? <Text style={styles.warning}>No confirmed artifact is available for this area.</Text> : null}
            {preview ? <View style={styles.preview}><Text style={styles.previewText} selectable>{preview}</Text></View> : null}
            <View style={styles.actions}>
              <TouchableOpacity testID="world-forge-stage" accessibilityRole="button"
                disabled={!active||!!jobStage} onPress={() => void forge(selected.id)}
                style={[styles.primary,(!active||!!jobStage)&&styles.disabled]}>
                <Text style={styles.primaryText}>{jobStage===selected.id?'Forging…':selected.present?'Re-forge stage':'Forge missing stage'} →</Text>
              </TouchableOpacity>
              <TouchableOpacity testID="world-open-kb" accessibilityRole="button"
                onPress={()=>go(projectHref('/game-kb',gameId)!)} style={styles.secondary}>
                <Text style={styles.secondaryText}>Edit and approve in KB</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View> : null}

        <View style={styles.panel}>
          <Text style={styles.heading}>Connected creative tools</Text>
          <Text style={styles.body}>Each tool receives the same game ID using its native parameter. The tools themselves remain authoritative for generated output.</Text>
          <View style={styles.toolGrid}>
            {links.map(link=>(
              <TouchableOpacity key={link.id} testID={`world-tool-${link.id}`}
                accessibilityRole="button" accessibilityLabel={`Open ${link.title} for this game`}
                onPress={()=>go(link.href)} style={[styles.tool,wide&&styles.toolWide]}>
                <Text style={styles.toolTitle}>{link.title} →</Text>
                <Text style={styles.body}>{link.description}</Text>
              </TouchableOpacity>
            ))}
          </View>
          <TouchableOpacity accessibilityRole="button" onPress={()=>go('/worlds-gallery')} style={styles.secondary}>
            <Text style={styles.secondaryText}>Browse all saved worlds (not project-filtered) →</Text>
          </TouchableOpacity>
        </View>

        <View style={styles.panel}>
          <Text style={styles.heading}>Design review with Jeeves and the compiler</Text>
          <Text style={styles.body}>Create an editable brief from known game evidence. Source summaries are opt-in; the design compiler runs only after an explicit confirmation.</Text>
          <TouchableOpacity testID="world-design-review" accessibilityRole="button"
            style={styles.primary} onPress={()=>go(projectHref('/design-review',gameId)!)}>
            <Text style={styles.primaryText}>Review game design →</Text>
          </TouchableOpacity>
        </View>
        <View style={styles.panel}>
          <Text style={styles.heading}>Mounted systems</Text>
          <Text style={styles.body}>Actual systems returned by Systems Forge for this build. This count is independent of pipeline stage completion.</Text>
          {systems.length ? systems.map(s=><Text key={s.key} style={styles.file}>• {s.label}</Text>):
            <Text style={styles.warning}>No mounted systems could be confirmed. Open Systems Forge to inspect or add them.</Text>}
          <TouchableOpacity accessibilityRole="button" style={styles.secondary}
            onPress={()=>go(projectHref('/systems-forge',gameId)!)}>
            <Text style={styles.secondaryText}>Manage build systems →</Text>
          </TouchableOpacity>
        </View>

        <View style={styles.panel}>
          <Text style={styles.heading}>Next: playable and export</Text>
          <Text style={styles.body}>Return to Studio to verify the remaining pipeline stages before packaging. A forged world alone does not mean the build is shippable.</Text>
          <TouchableOpacity testID="world-to-studio" accessibilityRole="button" style={styles.primary}
            onPress={()=>go(projectHref('/studio',gameId)!)}>
            <Text style={styles.primaryText}>Continue game build →</Text>
          </TouchableOpacity>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}
const styles=StyleSheet.create({
  safe:{flex:1,backgroundColor:COLORS.background},
  page:{padding:18,paddingBottom:65,gap:14},
  wide:{width:'100%',maxWidth:1180,alignSelf:'center'},
  back:{minHeight:44,justifyContent:'center'},link:{color:'#B9ACFF',fontWeight:'800',fontSize:13},
  hero:{backgroundColor:'#1A1B33',borderColor:'#4C4970',borderWidth:1,borderRadius:20,padding:19,gap:9},
  kicker:{color:'#AFAAFF',fontSize:11,fontWeight:'900',letterSpacing:1.4},
  title:{color:COLORS.text,fontSize:26,fontWeight:'900'},
  body:{color:COLORS.dim,fontSize:12,lineHeight:19},
  projectId:{color:'#CFD7EB',fontSize:11,fontFamily:'monospace',marginTop:5},
  metrics:{flexDirection:'row',flexWrap:'wrap',gap:8,marginTop:12},
  metric:{backgroundColor:'#252A45',padding:11,borderRadius:12,flexGrow:1,minWidth:90},
  value:{color:COLORS.text,fontSize:19,fontWeight:'900'},
  hint:{color:'#9AA6BC',fontSize:11,marginTop:4},
  panel:{backgroundColor:COLORS.panel,borderColor:COLORS.border,borderWidth:1,borderRadius:17,padding:16,gap:12},
  row:{flexDirection:'row',justifyContent:'space-between',alignItems:'center',gap:8},
  heading:{color:COLORS.text,fontSize:17,fontWeight:'800',flexShrink:1},
  stageGrid:{flexDirection:'row',gap:9,flexWrap:'wrap'},
  stage:{width:'100%',backgroundColor:'#1C2536',borderWidth:1,borderColor:'#344052',borderRadius:12,padding:12},
  stageWide:{width:'48%',flexGrow:1},
  stageSelected:{borderColor:COLORS.accent,backgroundColor:'#292747'},
  stageTitle:{color:COLORS.text,fontWeight:'800',fontSize:14},
  label:{fontSize:11,marginTop:5,fontWeight:'700'},
  detail:{borderTopWidth:1,borderColor:COLORS.border,paddingTop:12,gap:8},
  file:{color:'#CCE7F1',fontSize:12,marginTop:2,fontFamily:'monospace'},
  preview:{borderRadius:10,backgroundColor:'#090E18',padding:11,maxHeight:240,overflow:'hidden'},
  previewText:{color:'#B8E6C6',fontSize:11,fontFamily:'monospace'},
  warning:{color:COLORS.amber,fontSize:12,lineHeight:20},
  actions:{flexDirection:'row',flexWrap:'wrap',gap:9},
  primary:{backgroundColor:'#6952D5',paddingHorizontal:15,paddingVertical:13,borderRadius:11,minHeight:47,justifyContent:'center'},
  primaryText:{color:'#FFFFFF',fontSize:12,fontWeight:'900'},
  secondary:{borderRadius:11,borderColor:'#49526D',borderWidth:1,paddingHorizontal:13,paddingVertical:12,minHeight:44,justifyContent:'center'},
  secondaryText:{color:'#DCE4F5',fontSize:12,fontWeight:'800'},
  disabled:{opacity:0.43},
  toolGrid:{flexDirection:'row',gap:9,flexWrap:'wrap'},
  tool:{width:'100%',padding:13,borderRadius:12,borderWidth:1,borderColor:'#394259',backgroundColor:'#182236',gap:6},
  toolWide:{width:'48%',flexGrow:1},
  toolTitle:{color:'#EAE6FF',fontWeight:'800',fontSize:14},
  empty:{padding:24,gap:12},
});
