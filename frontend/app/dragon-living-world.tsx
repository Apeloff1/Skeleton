/** Dragon Living World Forge: non-winning, postgame and moving mazes.
 *
 * Actual gameplay choices are revalidated server-side by deterministic
 * original state transitions. Real 5×5 terrain shows current realm and
 * dynamic environmental phase. No Minecraft/Ark/Fallout/Mario IP imported.
 */
import React from 'react';
import {
  ActivityIndicator,Platform,SafeAreaView,ScrollView,StyleSheet,
  Text,TextInput,TouchableOpacity,View,
} from 'react-native';
import * as FileSystem from 'expo-file-system/legacy';
import StudioLoginGate,{useStudioAuth} from '../src/auth/StudioLoginGate';
import {authHeaders} from '../src/auth/gameforgeAuth';
import {API_BASE} from '../utils/apiBase';

const API=(API_BASE||'').replace(/\/$/,'')+
  '/api/dragon-academy/native/production/worlds';
type WorldStyle={
  rules:string[];default_lifecycle:string;fixed_goal_required:boolean;
  playability_is_not_win_condition:boolean;
};
type Catalog={
  ok:boolean;styles:Record<string,WorldStyle>;
  lifecycles:string[];world_style_count:number;
  addressable_world_ids:number;variants_per_world_id:number;
  addressable_world_variant_slots:number;
};
type Choice={
  name:string;available:boolean;reason:string;
  to?:number[];world_ending?:boolean;continues_after?:boolean;
  movement_model?:string;
};
type GameState={
  schema:string;world_id:number;variation:number;
  style:string;lifecycle:string;fixed_winning_condition_exists:boolean;
  playable:boolean;has_completed_ending:boolean;postgame_active:boolean;
  player:{
    realm:number;x:number;y:number;turn:number;chapter:number;era:number;
    energy:number;health:number;food:number;wood:number;ore:number;
    crystal:number;shelter:number;research:number;trade:number;allies:number;
    faction_civic:number;faction_wild:number;discovered?:string[];
    discoveries:string[];endings_seen:string[];world_changes:string[];
    portal_key:boolean;history_digest:string;
  };
  tile:{biome:string;landmark:string;weather:string};
  environment:{weather:string;season:string;maze_phase:number;time_of_day:string};
  options:Choice[];
};
type Tile={x:number;y:number;realm:number;biome:string;landmark:string;weather:string};
type Preview={
  ok:boolean;world:{
    world_fingerprint:string;style:string;lifecycle:string;rules:string[];
    realms:number;shifting_routes:boolean;allows_continuation:boolean;
  };
  player:GameState;tiles:Tile[];
};
type Alternative={
  slot:number;objective:string;actions:string[];
  original_endings:string[];completed_world:boolean;
  remains_playable:boolean;chapters_seen:number;
  trace_digest:string;sample_budget:number;
  persistent_changes:string[];realms_visited:number[];
};
type Portfolio={
  ok:boolean;sampled:number;distinct_replayed_action_sequences:number;
  samples:Alternative[];world_has_ending:boolean;claim:string;
};
type Play={ok:boolean;played_moves:string[];
  current:GameState;surroundings:Tile[]};

const fallbackStyles=[
  'creative_sandbox','survival_sandbox','open_world_story',
  'post_story_wasteland','multiple_world_platform','mutable_labyrinth',
  'rotating_tower','colony_simulation','branching_campaign',
  'hardcore_roguelike','endless_expedition',
];
const label=(id:string)=>id.replace(/_/g,' ');
async function apiPost<T>(route:string,data:object):Promise<T>{
  const response=await fetch(API+route,{
    method:'POST',cache:'no-store',
    headers:authHeaders({'Content-Type':'application/json'}),
    body:JSON.stringify(data),
  });
  if(!response.ok)throw new Error(
    response.status===403?'Only authenticated editors may author living worlds.':
    response.status===422?'This world, ending, door or resource choice is not currently legal.':
    'Original living-world runtime is unavailable.');
  return response.json() as Promise<T>;
}
async function retrieveCatalog():Promise<Catalog>{
  const response=await fetch(API+'/catalog',{
    headers:authHeaders(),cache:'no-store',
  });
  if(!response.ok)throw new Error('Living-world style registry is unavailable.');
  return response.json() as Promise<Catalog>;
}
const biomeColor:Record<string,string>={
  woodland:'#326454',desert:'#725c37',coast:'#356a81',
  mountain:'#59616b',ruins:'#5c4a66',wetlands:'#436c5e',
  caverns:'#3e4258',skylands:'#6188a6',orbital:'#453f6d',
  crystal_fields:'#64538a',tundra:'#6e8792',garden:'#4f7552',
};

function LivingWorldEditor(){
  const {role}=useStudioAuth();
  const editor=role==='admin'||role==='editor';
  const [catalog,setCatalog]=React.useState<Catalog|null>(null);
  const [worldNumber,setWorldNumber]=React.useState('1977');
  const [variation,setVariation]=React.useState(0);
  const [style,setStyle]=React.useState('mutable_labyrinth');
  const [lifecycle,setLifecycle]=React.useState<string>('unending');
  const [preview,setPreview]=React.useState<Preview|null>(null);
  const [game,setGame]=React.useState<GameState|null>(null);
  const [terrain,setTerrain]=React.useState<Tile[]>([]);
  const [history,setHistory]=React.useState<string[]>([]);
  const [portfolio,setPortfolio]=React.useState<Portfolio|null>(null);
  const [guided,setGuided]=React.useState<Alternative|null>(null);
  const [busy,setBusy]=React.useState(false);
  const [failure,setFailure]=React.useState('');
  const [notice,setNotice]=React.useState('');
  const runId=React.useRef(0);
  React.useEffect(()=>{
    let active=true;
    retrieveCatalog().then(data=>{
      if(active&&data.ok)setCatalog(data);
    }).catch(()=>{if(active)setCatalog(null);});
    return ()=>{active=false;};
  },[]);
  const id=Number(worldNumber);
  const valid=/^\d{1,7}$/.test(worldNumber)&&Number.isSafeInteger(id)&&
    id>=0&&id<1_600_000;
  const config={world_id:id,variation,style,lifecycle};
  const reset=()=>{
    runId.current++;
    setBusy(false);setGame(null);setPreview(null);setTerrain([]);
    setHistory([]);setPortfolio(null);setGuided(null);
    setFailure('');setNotice('');
  };
  const changeStyle=(next:string)=>{
    setStyle(next);
    setLifecycle(catalog?.styles[next]?.default_lifecycle||
      'unending');
    reset();
  };
  const load=async()=>{
    if(!editor||busy||!valid)return;
    const ticket=++runId.current;
    setBusy(true);setFailure('');setNotice('');
    try{
      const snapshot=await apiPost<Preview>('/preview',config);
      if(!snapshot.ok||!snapshot.world?.world_fingerprint||
         snapshot.player?.world_id!==id||
         !Array.isArray(snapshot.tiles)||snapshot.tiles.length!==25)
        throw new Error('Living-world preview has inconsistent original source.');
      if(ticket===runId.current){
        setPreview(snapshot);setGame(snapshot.player);
        setTerrain(snapshot.tiles);setHistory([]);setPortfolio(null);
        setGuided(null);
      }
    }catch(caught){
      if(ticket===runId.current)setFailure(
        caught instanceof Error?caught.message:'Could not construct living world.');
    }finally{if(ticket===runId.current)setBusy(false);}
  };
  const move=async(action:string)=>{
    if(!editor||busy||!game||!preview||history.length>=192)return;
    if(!game.options.some(x=>x.name===action&&x.available))return;
    const next=[...history,action];
    const ticket=++runId.current;
    setBusy(true);setFailure('');
    try{
      const result=await apiPost<Play>('/play',{
        ...config,moves:next,
      });
      if(!result.ok||
         result.played_moves.join('|')!==next.join('|')||
         result.current.world_id!==id)
        throw new Error('World action receipt diverged from source');
      if(ticket===runId.current){
        setHistory(next);setGame(result.current);
        setTerrain(result.surroundings);
        if(result.current.has_completed_ending){
          setNotice(result.current.postgame_active
            ? 'Story ending reached. Your choices persist, and this world remains playable.'
            : 'Campaign completed. Restart to experience a different outcome.');
        }else setNotice('');
      }
    }catch(caught){
      if(ticket===runId.current)setFailure(
        caught instanceof Error?caught.message:'This world choice cannot be played.');
    }finally{if(ticket===runId.current)setBusy(false);}
  };
  const rewind=async()=>{
    if(busy||!preview||history.length===0)return;
    const ticket=++runId.current;
    setBusy(true);setFailure('');
    const remaining=history.slice(0,-1);
    try{
      const response=await apiPost<Play>('/play',{
        ...config,moves:remaining,
      });
      if(!response.ok||
         response.played_moves.join('|')!==remaining.join('|'))
        throw new Error('Original choice replay did not match.');
      if(ticket===runId.current){
        setHistory(remaining);setGame(response.current);
        setTerrain(response.surroundings);setNotice('');
      }
    }catch(caught){
      if(ticket===runId.current)setFailure(
        caught instanceof Error?caught.message:'Could not rewind this world choice.');
    }finally{if(ticket===runId.current)setBusy(false);}
  };
  const inspect=async()=>{
    if(!editor||busy||!preview)return;
    const ticket=++runId.current;
    setBusy(true);setFailure('');
    try{
      const sampled=await apiPost<Portfolio>('/alternatives',config);
      if(!sampled.ok||sampled.samples.length>10||
         sampled.sampled!==sampled.samples.length)
        throw new Error('Route portfolio is not bounded or replay-proven.');
      if(ticket===runId.current)setPortfolio(sampled);
    }catch(caught){
      if(ticket===runId.current)setFailure(
        caught instanceof Error?caught.message:'Route analysis failed.');
    }finally{if(ticket===runId.current)setBusy(false);}
  };
  const beginExample=(alternative:Alternative)=>{
    if(!preview||busy)return;
    setGuided(alternative);setGame(preview.player);
    setTerrain(preview.tiles);setHistory([]);
    setNotice('Follow an original replay-proven route. Every step remains a real game decision.');
    setFailure('');
  };
  const advance=()=>{
    if(!guided||!game||busy||history.length>=guided.actions.length)return;
    const action=guided.actions[history.length];
    move(action);
  };
  const save=async()=>{
    if(!game||!preview||busy||!FileSystem.documentDirectory)return;
    const exported={
      schema:'skeleton.ai.dragon.living_world_local_save.v1',
      world_id:id,variation,style,lifecycle,history,
      final_digest:game.player.history_digest,
      original_world_fingerprint:preview.world.world_fingerprint,
    };
    try{
      const raw=JSON.stringify(exported);
      if(raw.length>20_000)throw new Error('World history exceeds local save limit.');
      const path=FileSystem.documentDirectory+
        'dragon-living-world-'+id+'-'+variation+'.json';
      await FileSystem.writeAsStringAsync(path,raw);
      setNotice('Local original-world history saved for verified replay.');
    }catch(caught){
      setFailure(caught instanceof Error?caught.message:'Cannot save original world.');
    }
  };
  const restore=async()=>{
    if(busy||!valid||!FileSystem.documentDirectory)return;
    const ticket=++runId.current;
    setBusy(true);setFailure('');
    try{
      const path=FileSystem.documentDirectory+
        'dragon-living-world-'+id+'-'+variation+'.json';
      const raw=await FileSystem.readAsStringAsync(path);
      if(raw.length>20_000)throw new Error('Saved original world exceeded limit.');
      const saved=JSON.parse(raw) as {
        schema:string;world_id:number;variation:number;
        style:string;lifecycle:string;history:string[];
        final_digest:string;original_world_fingerprint:string;
      };
      if(saved.schema!=='skeleton.ai.dragon.living_world_local_save.v1'||
         saved.world_id!==id||saved.variation!==variation||
         saved.style!==style||saved.lifecycle!==lifecycle||
         !Array.isArray(saved.history)||saved.history.length>192||
         saved.original_world_fingerprint!==preview?.world.world_fingerprint)
        throw new Error('Saved original world belongs to another source design.');
      const response=await apiPost<Play>('/play',{
        ...config,moves:saved.history,
      });
      if(!response.ok||
         response.current.player.history_digest!==saved.final_digest)
        throw new Error('Saved choices failed independent gameplay replay.');
      if(ticket===runId.current){
        setHistory(saved.history);setGame(response.current);
        setTerrain(response.surroundings);
        setNotice('Original choices and endings restored after server verification.');
      }
    }catch(caught){
      if(ticket===runId.current)setFailure(
        caught instanceof Error?caught.message:'Saved world cannot be restored.');
    }finally{if(ticket===runId.current)setBusy(false);}
  };
  const styleNames=catalog?Object.keys(catalog.styles):fallbackStyles;
  return <SafeAreaView style={s.root}>
    <ScrollView contentContainerStyle={s.page}>
      <Text style={s.title}>Dragon · Living Worlds</Text>
      <Text style={s.copy}>
        Build worlds that do not need to end. Explore, farm, survive, build
        settlements, shift labyrinth walls, travel between realms or reach
        different persistent story conclusions and keep playing afterward.
        Your choices really change the world state.
      </Text>
      {!editor&&<Text style={s.warning}>Creator/editor access required.</Text>}
      {catalog&&<View style={s.panel}>
        <Text style={s.heading}>
          {catalog.world_style_count} game-world styles ·
          {' '}{catalog.addressable_world_ids.toLocaleString()} world addresses
        </Text>
        <Text style={s.copy}>
          {catalog.addressable_world_variant_slots.toLocaleString()}
          {' '}possible lazily generated variation slots, not
          prebuilt games or independently reviewed original narratives.
        </Text>
      </View>}
      <Text style={s.heading}>Original world address (0–1,599,999)</Text>
      <TextInput style={s.input} value={worldNumber} maxLength={7}
        keyboardType="number-pad" accessibilityLabel="Original world address"
        editable={editor&&!busy}
        onChangeText={v=>{setWorldNumber(v);reset();}}/>
      <Text style={s.heading}>Variation</Text>
      <View style={s.chips}>{Array.from({length:10},(_,n)=>(
        <TouchableOpacity key={n} disabled={!editor||busy}
          style={[s.chip,variation===n&&s.selected]}
          onPress={()=>{setVariation(n);reset();}}>
          <Text style={s.text}>{n+1}</Text>
        </TouchableOpacity>
      ))}</View>
      <Text style={s.heading}>Select world style</Text>
      <View style={s.chips}>{styleNames.map(name=>(
        <TouchableOpacity key={name} disabled={!editor||busy}
          style={[s.chip,style===name&&s.selected]}
          onPress={()=>changeStyle(name)}>
          <Text style={s.text}>{label(name)}</Text>
        </TouchableOpacity>
      ))}</View>
      <Text style={s.heading}>Lifecycle / whether a win is necessary</Text>
      <View style={s.chips}>{(catalog?.lifecycles||
        ['unending','postgame','multiple_endings','optional_endings',
         'mandatory_completion','restartable_runs','permadeath']).map(name=>(
        <TouchableOpacity key={name} disabled={!editor||busy}
          style={[s.chip,lifecycle===name&&s.selected]}
          onPress={()=>{setLifecycle(name);reset();}}>
          <Text style={s.text}>{label(name)}</Text>
        </TouchableOpacity>
      ))}</View>
      <TouchableOpacity style={[s.action,(!editor||busy||!valid)&&s.disabled]}
        disabled={!editor||busy||!valid} onPress={load}>
        <Text style={s.actionText}>Generate living and changing world</Text>
      </TouchableOpacity>
      {busy&&<ActivityIndicator color="#a9f4c0"/>}
      {preview&&game&&<>
        <View style={s.panel}>
          <Text style={s.heading}>
            {label(game.style)} · {label(game.lifecycle)}
          </Text>
          <Text style={s.copy}>
            {preview.world.realms} worlds/realms ·
            {' '}{preview.world.rules.map(label).join(' · ')}
          </Text>
          <Text style={s.copy}>
            {game.playable?'Active game':'Run finished'} ·
            {' '}{game.fixed_winning_condition_exists
              ?'Optional or achievable story conclusions':'No fixed winning condition'}
          </Text>
          {game.postgame_active&&<Text style={s.success}>
            Postgame active — original story outcome persists while exploration continues.
          </Text>}
          <Text style={s.hint}>
            Current conditions: {game.environment.weather} ·
            {' '}{game.environment.season} · {game.environment.time_of_day}
            {' · '}moving-maze phase {game.environment.maze_phase+1}/8
          </Text>
          <Text style={s.hint}>
            World identity: {preview.world.world_fingerprint.slice(0,20)}…
          </Text>
        </View>
        <View style={s.panel}>
          <Text style={s.heading}>Actual terrain · realm {game.player.realm+1}</Text>
          {Array.from({length:5},(_,row)=>(
            <View key={row} style={s.mapRow}>
              {terrain.slice(row*5,row*5+5).map((tile,i)=>(
                <View key={row+'-'+i} style={[s.tile,{
                  backgroundColor:biomeColor[tile.biome]||'#3b5060',
                },row===2&&i===2&&s.here]}>
                  <Text style={s.tileText}>{row===2&&i===2?'●':
                    tile.landmark!=='ordinary_land'?'◇':'·'}</Text>
                </View>
              ))}
            </View>
          ))}
          <Text style={s.hint}>
            Position ({game.player.x}, {game.player.y}) ·
            changing labyrinth corridors are listed below.
            Terrain tiles are deterministic original coordinates.
          </Text>
        </View>
        <View style={s.panel}>
          <Text style={s.heading}>Player, resources and consequences</Text>
          <Text style={s.copy}>
            Turn {game.player.turn} · HP {game.player.health} ·
            stamina {game.player.energy} · food {game.player.food}
          </Text>
          <Text style={s.copy}>
            Wood {game.player.wood} · ore {game.player.ore} ·
            crystals {game.player.crystal} · settlements {game.player.shelter}
            {' · '}research {game.player.research}
          </Text>
          <Text style={s.copy}>
            Civic support {game.player.faction_civic} ·
            wild support {game.player.faction_wild} ·
            allies {game.player.allies}
          </Text>
          <Text style={s.hint}>
            World changed by: {game.player.world_changes.length
              ?game.player.world_changes.map(label).join(', ')
              :'Your world-changing actions are still ahead'}
          </Text>
          <Text style={s.heading}>Experienced conclusions</Text>
          <Text style={s.copy}>
            {game.player.endings_seen.length
              ?game.player.endings_seen.map(label).join(' · ')
              :'No ending required or experienced yet'}
          </Text>
        </View>
        <View style={s.panel}>
          <Text style={s.heading}>Take a real world action</Text>
          {game.options.map(option=>(
            <TouchableOpacity key={option.name} accessibilityRole="button"
              disabled={!option.available||busy||history.length>=192}
              style={[s.option,(!option.available||busy)&&s.disabled]}
              onPress={()=>move(option.name)}>
              <Text style={s.actionText}>
                {option.world_ending?'Story ending: ':''}
                {label(option.name)}
              </Text>
              <Text style={s.hint}>
                {option.available
                  ?(option.continues_after?'Continue free-roaming after this ending':
                    option.movement_model||'A consequential real game decision')
                  :label(option.reason)}
              </Text>
            </TouchableOpacity>
          ))}
          <View style={s.chips}>
            <TouchableOpacity style={s.chip} onPress={rewind}
              disabled={busy||!history.length}>
              <Text style={s.actionText}>Undo decision</Text>
            </TouchableOpacity>
            <TouchableOpacity style={s.chip}
              onPress={()=>{setHistory([]);setGame(preview.player);setTerrain(preview.tiles);
                setGuided(null);setNotice('');setFailure('');}}
              disabled={busy}>
              <Text style={s.actionText}>Restart this world</Text>
            </TouchableOpacity>
          </View>
          <Text style={s.hint}>
            {history.length}/192 actions in this bounded local replay.
            Save and restore revalidate every action before accepting state.
          </Text>
          {Platform.OS!=='web'&&<View style={s.chips}>
            <TouchableOpacity style={s.chip} onPress={save} disabled={busy}>
              <Text style={s.actionText}>Save original history</Text>
            </TouchableOpacity>
            <TouchableOpacity style={s.chip} onPress={restore} disabled={busy}>
              <Text style={s.actionText}>Restore verified history</Text>
            </TouchableOpacity>
          </View>}
        </View>
        <View style={s.panel}>
          <Text style={s.heading}>Alternatives are actual gameplay</Text>
          <TouchableOpacity style={[s.action,busy&&s.disabled]}
            disabled={busy} onPress={inspect}>
            <Text style={s.actionText}>Generate ten individually replayed routes</Text>
          </TouchableOpacity>
          {portfolio&&<>
            <Text style={s.copy}>
              {portfolio.distinct_replayed_action_sequences} distinct observed
              action histories in {portfolio.sampled} sampled routes.
              {portfolio.world_has_ending
                ?' Different story conclusions may be possible.':
                  ' None requires a win or final boss.'}
            </Text>
            {portfolio.samples.map(route=>(
              <TouchableOpacity key={route.slot} style={s.option}
                disabled={busy} onPress={()=>beginExample(route)}>
                <Text style={s.actionText}>
                  {route.slot+1}. {label(route.objective)}
                </Text>
                <Text style={s.copy}>
                  {route.actions.length} playable steps ·
                  {route.realms_visited.length} visited realms
                  {route.original_endings.length
                    ?' · '+route.original_endings.map(label).join(', ')
                    :' · ongoing world'}
                </Text>
                <Text style={s.hint}>
                  {route.persistent_changes.map(label).join(', ')||
                    'Exploration and resources change through genuine moves'}
                </Text>
              </TouchableOpacity>
            ))}
          </>}
          {guided&&<TouchableOpacity
            style={[s.action,busy&&s.disabled]}
            disabled={busy||history.length>=guided.actions.length}
            onPress={advance}>
            <Text style={s.actionText}>
              Play alternative {history.length}/{guided.actions.length} decisions
            </Text>
          </TouchableOpacity>}
        </View>
      </>}
      {!!failure&&<Text accessibilityRole="alert" style={s.warning}>{failure}</Text>}
      {!!notice&&<Text accessibilityRole="alert" style={s.success}>{notice}</Text>}
      <Text style={s.hint}>
        This is a functional original abstract-world game runtime, not
        a 3D voxel renderer, creature-AI simulation, or a clone of any
        commercial IP. Sixteen million indexed slots are potential
        dynamically generated original game variants, not certified shipped
        games. Player enjoyment and global legal uniqueness require separate
        testing and rights review.
      </Text>
    </ScrollView>
  </SafeAreaView>;
}
export default function DragonLivingWorldForge(){
  return <StudioLoginGate><LivingWorldEditor/></StudioLoginGate>;
}
const s=StyleSheet.create({
  root:{flex:1,backgroundColor:'#111b27'},
  page:{padding:15,paddingBottom:80,gap:12,maxWidth:860,width:'100%',alignSelf:'center'},
  title:{fontSize:25,fontWeight:'700',color:'#f4faf5'},
  heading:{fontSize:16,fontWeight:'700',color:'#d4f1e2'},
  text:{fontSize:12,color:'#e6f2e9'},
  copy:{fontSize:13,lineHeight:20,color:'#c4dad1'},
  hint:{fontSize:12,lineHeight:18,color:'#a6c0b4'},
  warning:{fontSize:13,color:'#ffbfaf'},
  success:{fontSize:13,color:'#b6f1c4'},
  input:{padding:12,borderRadius:9,backgroundColor:'#223744',
         color:'#fff',borderWidth:1,borderColor:'#547969'},
  chips:{flexDirection:'row',flexWrap:'wrap',gap:6},
  chip:{padding:10,borderRadius:9,backgroundColor:'#294451'},
  selected:{backgroundColor:'#43845d'},
  action:{padding:14,borderRadius:10,backgroundColor:'#357f56',alignItems:'center'},
  actionText:{fontSize:13,fontWeight:'700',color:'#f1fff4'},
  disabled:{opacity:0.38},
  panel:{padding:13,borderRadius:11,backgroundColor:'#1a3040',gap:8},
  option:{padding:11,borderRadius:9,backgroundColor:'#294557',gap:3},
  mapRow:{flexDirection:'row',gap:4,justifyContent:'center'},
  tile:{width:48,height:40,alignItems:'center',justifyContent:'center',
        borderRadius:5},
  tileText:{fontSize:20,fontWeight:'700',color:'#f4faee'},
  here:{borderWidth:3,borderColor:'#c7eda2'},
});
