/** Dragon ORIGINALS Forge — real, editable, compositional game mechanics.
 *
 * Full 64-bit program indexes are DECIMAL STRINGS: JavaScript Number would
 * silently collapse many quintillion-scale addresses. Editable 32x4 levels
 * are submitted as exact integers, with server-side rank/unrank and causal
 * gameplay evidence. No claim of billions of finished copyrighted games.
 */
import React from 'react';
import {
  ActivityIndicator,SafeAreaView,ScrollView,StyleSheet,Text,TextInput,
  TouchableOpacity,View,
} from 'react-native';
import StudioLoginGate,{useStudioAuth} from '../src/auth/StudioLoginGate';
import {authHeaders} from '../src/auth/gameforgeAuth';
import {API_BASE} from '../utils/apiBase';

const API=(API_BASE||'').replace(/\/$/,'')+
  '/api/dragon-academy/native/production/worlds/originals';
type Mechanic={
  id:string;domain:string;cost_resource:string;reward_resource:string;
  levels:number[];
};
type Catalog={
  ok:boolean;actual_mechanic_verbs:number;
  mechanically_separable_binary_nuclei:number;
  exact_original_rule_program_address_count:string;
  mechanics:Mechanic[];playable_route_intents:string[];
  finished_unique_cleared_games:number;
};
type Option={
  id:string;mechanic?:string;domain?:string;
  level?:number;available:boolean;cost_resource:string;
  cost:number;gain_resource:string;gain:number;reason:string;
  world_effect?:string;physical_position_delta?:number[];
  requirements?:string[];
};
type State={
  resources:number[];mastery:number[];domain_evolution:number[];
  x:number;y:number;turn:number;era:number;realm:number;
  endings:string[];changed_places:string[];
  unlocked_joins:string[];history_digest:string;
};
type Program={
  schema:string;decimal_index:string;intensities:number[];
  source_digest:string;mechanics_available:number;
  parent_codex_index:string|null;is_finished_game:boolean;
};
type Proof={
  axis:string;level:number;available:boolean;
  world_effect?:string;cost?:number;gain?:number;
  witness?:string|null;
};
type Preview={
  ok:boolean;program:Program;initial_game_state:State;
  playable_actions:Option[];
  causal_gameplay_proofs:{
    available_original_mechanics:number;
    mechanic_execution_witnesses:Proof[];
  };
  fixed_win_required:boolean;prebuilt_finished_games:number;
};
type Game={ok:boolean;source_digest:string;played_actions:string[];
  current_game_state:State;available_actions:Option[];
  playable_after_endings:boolean};
type Campaign={
  intent:string;actions:string[];source_digest:string;
  ending_variants:string[];actual_cross_mechanic_joins:string[];
  actual_resource_changes:number[];world_changes:string[];
  final_turn:number;final_era:number;final_realm:number;
  final_history_digest:string;trace_digest:string;
};
type Portfolio={
  ok:boolean;sampled:number;distinct_observed_action_sequences:number;
  different_measured_final_stories:number;
  experiences:Campaign[];programs_materialized_as_finished_games:number;
};
const pretty=(text:string)=>text.replace(/_/g,' ');
const resourceNames=['stone','wood','food','wealth','lore','aether','energy'];

async function fetchCatalog():Promise<Catalog>{
  const response=await fetch(API+'/catalog',{
    method:'GET',cache:'no-store',headers:authHeaders(),
  });
  if(!response.ok)throw new Error('Original mechanics registry is unavailable.');
  return response.json() as Promise<Catalog>;
}
async function post<T>(path:string,body:object):Promise<T>{
  const response=await fetch(API+path,{
    method:'POST',cache:'no-store',
    headers:authHeaders({'Content-Type':'application/json'}),
    body:JSON.stringify(body),
  });
  if(!response.ok)throw new Error(
    response.status===403?'Creator/editor access is required.':
    response.status===422?'Gameplay configuration or original action failed verification.':
    'Original gameplay service is unavailable.');
  return response.json() as Promise<T>;
}
function Creator(){
  const {role}=useStudioAuth();
  const editor=role==='editor'||role==='admin';
  const [catalog,setCatalog]=React.useState<Catalog|null>(null);
  const [levels,setLevels]=React.useState<number[]>(Array(32).fill(0));
  const [manualIndex,setManualIndex]=React.useState('0');
  const [useIndex,setUseIndex]=React.useState(false);
  const [nucleus,setNucleus]=React.useState('1048575');
  const [parentCodex,setParentCodex]=React.useState('');
  const [preview,setPreview]=React.useState<Preview|null>(null);
  const [player,setPlayer]=React.useState<State|null>(null);
  const [options,setOptions]=React.useState<Option[]>([]);
  const [history,setHistory]=React.useState<string[]>([]);
  const [portfolio,setPortfolio]=React.useState<Portfolio|null>(null);
  const [fusionPage,setFusionPage]=React.useState(0);
  const [fusions,setFusions]=React.useState<Option[]>([]);
  const [guided,setGuided]=React.useState<Campaign|null>(null);
  const [busy,setBusy]=React.useState(false);
  const [failure,setFailure]=React.useState('');
  const [notice,setNotice]=React.useState('');
  const turn=React.useRef(0);
  React.useEffect(()=>{
    let current=true;
    fetchCatalog().then(value=>{
      if(current&&value.ok)setCatalog(value);
    }).catch(()=>{if(current)setCatalog(null);});
    return ()=>{current=false;};
  },[]);
  const invalidate=()=>{
    turn.current++;
    setPreview(null);setPlayer(null);setOptions([]);
    setHistory([]);setGuided(null);setPortfolio(null);
    setFusionPage(0);setFusions([]);
    setBusy(false);setFailure('');setNotice('');
  };
  const body=useIndex
    ?{program_index:manualIndex,parent_codex_index:parentCodex||null}
    :{program_index:'0',levels,parent_codex_index:parentCodex||null};
  const validExact=/^(0|[1-9]\d{0,19})$/.test(manualIndex)&&
    (manualIndex.length<20||
      (manualIndex.length===20&&manualIndex<'18446744073709551616'));
  const changeLevel=(index:number,value:number)=>{
    const next=[...levels];
    next[index]=value;
    setLevels(next);invalidate();
  };
  const setPreset=(value:number)=>{
    setUseIndex(false);setLevels(Array(32).fill(value));invalidate();
  };
  const fromNucleus=async()=>{
    const id=Number(nucleus);
    if(!editor||busy||!/^\d{1,8}$/.test(nucleus)||
       !Number.isInteger(id)||id<0||id>=16777216)return;
    const ticket=++turn.current;
    setBusy(true);setFailure('');
    try{
      const response=await post<{
        ok:boolean;program:Program;
        original_nucleus:number;
      }>('/nucleus',{original_nucleus:id});
      if(!response.ok||response.original_nucleus!==id||
         response.program.intensities.length!==32)
        throw new Error('Original mechanic nucleus could not be independently resolved.');
      if(ticket===turn.current){
        setUseIndex(false);setLevels(response.program.intensities);
        setNotice('Materialized original mechanic nucleus '+id+
          ', not merely another random map seed.');
        setPreview(null);setPlayer(null);setHistory([]);
      }
    }catch(e){
      if(ticket===turn.current)setFailure(
        e instanceof Error?e.message:'Original nucleus generation failed.');
    }finally{if(ticket===turn.current)setBusy(false);}
  };
  const create=async()=>{
    if(!editor||busy||(useIndex&&!validExact))return;
    const ticket=++turn.current;
    setBusy(true);setFailure('');setNotice('');
    try{
      const response=await post<Preview>('/preview',body);
      if(!response.ok||response.program.intensities.length!==32||
         response.causal_gameplay_proofs.mechanic_execution_witnesses.length!==32||
         response.program.is_finished_game)
        throw new Error('Original game mechanics did not pass causal validation.');
      if(ticket===turn.current){
        setPreview(response);setPlayer(response.initial_game_state);
        setOptions(response.playable_actions);
        setHistory([]);setPortfolio(null);setGuided(null);
        setFusionPage(0);setFusions([]);
        setLevels(response.program.intensities);
        setManualIndex(response.program.decimal_index);
      }
    }catch(e){
      if(ticket===turn.current)setFailure(
        e instanceof Error?e.message:'Originals Forge could not compile this rule program.');
    }finally{if(ticket===turn.current)setBusy(false);}
  };
  const play=async(action:string)=>{
    if(!preview||busy||!player||history.length>=128)return;
    if(![...options,...fusions].some(
        option=>option.id===action&&option.available))return;
    const ticket=++turn.current;
    setBusy(true);setFailure('');
    const moves=[...history,action];
    try{
      const response=await post<Game>('/play',{
        program_index:preview.program.decimal_index,
        parent_codex_index:preview.program.parent_codex_index,
        moves,
      });
      if(!response.ok||
         response.source_digest!==preview.program.source_digest||
         response.played_actions.join('|')!==moves.join('|'))
        throw new Error('Original rule program diverged during gameplay.');
      if(ticket===turn.current){
        setHistory(moves);setPlayer(response.current_game_state);
        setOptions(response.available_actions);setFusions([]);
        setNotice(response.current_game_state.endings.length
          ?'A story conclusion occurred; the world still allows further choices.'
          :'Real player action changed the original world.');
      }
    }catch(e){
      if(ticket===turn.current)setFailure(
        e instanceof Error?e.message:'This rule is not playable in current world state.');
    }finally{if(ticket===turn.current)setBusy(false);}
  };
  const undo=async()=>{
    if(!preview||busy||!history.length)return;
    const ticket=++turn.current;
    setBusy(true);setFailure('');
    const moves=history.slice(0,-1);
    try{
      const response=await post<Game>('/play',{
        program_index:preview.program.decimal_index,
        parent_codex_index:preview.program.parent_codex_index,
        moves,
      });
      if(!response.ok)throw new Error('Original prior state did not replay.');
      if(ticket===turn.current){
        setHistory(moves);setPlayer(response.current_game_state);
        setOptions(response.available_actions);setFusions([]);
        setNotice('');
      }
    }catch(e){if(ticket===turn.current)setFailure(
      e instanceof Error?e.message:'Failed to replay original world undo.');}
    finally{if(ticket===turn.current)setBusy(false);}
  };
  const discoverFusions=async(offset:number)=>{
    if(!preview||!player||busy||history.length>128||offset<0||offset>=1024)return;
    const ticket=++turn.current;
    setBusy(true);setFailure('');
    try{
      const response=await post<{
        ok:boolean;offset:number;returned:number;
        total_possible_directed_fusions:number;interactions:Option[];
        current_gameplay_digest:string;
      }>('/interactions',{
        program_index:preview.program.decimal_index,
        parent_codex_index:preview.program.parent_codex_index,
        moves:history,offset,limit:32,
      });
      if(!response.ok||response.offset!==offset||
         response.current_gameplay_digest!==player.history_digest||
         response.total_possible_directed_fusions!==1024)
        throw new Error('Original cross-mechanic page does not match current player state.');
      if(ticket===turn.current){
        setFusionPage(offset);setFusions(response.interactions);
      }
    }catch(e){
      if(ticket===turn.current)setFailure(
        e instanceof Error?e.message:'Could not discover actual cross-mechanic interactions.');
    }finally{if(ticket===turn.current)setBusy(false);}
  };
  const alternatives=async()=>{
    if(!preview||busy)return;
    const ticket=++turn.current;
    setBusy(true);setFailure('');
    try{
      const result=await post<Portfolio>('/campaigns',{
        program_index:preview.program.decimal_index,
        parent_codex_index:preview.program.parent_codex_index,
        branch_seed:1977,count:16,steps:24,
      });
      if(!result.ok||result.sampled!==16||
         result.experiences.length!==16)
        throw new Error('Original campaign alternatives were not replayed.');
      if(ticket===turn.current)setPortfolio(result);
    }catch(e){
      if(ticket===turn.current)setFailure(
        e instanceof Error?e.message:'Cannot replay authored game routes.');
    }finally{if(ticket===turn.current)setBusy(false);}
  };
  const guide=(item:Campaign)=>{
    if(!preview||busy)return;
    setGuided(item);
    setPlayer(preview.initial_game_state);
    setOptions(preview.playable_actions);
    setHistory([]);setFailure('');
    setNotice('Replay selected game experience: each step is still executed for real.');
  };
  const advance=()=>{
    if(!guided||history.length>=guided.actions.length)return;
    play(guided.actions[history.length]);
  };
  const counts=catalog?.exact_original_rule_program_address_count||
    '18446744073709551616';
  return <SafeAreaView style={s.root}>
    <ScrollView contentContainerStyle={s.page}>
      <Text style={s.title}>Dragon · Originals Forge</Text>
      <Text style={s.copy}>
        Design game rules, not just another level seed. Each of 32 original
        mechanics has four levels with real consequences for action
        availability, resources, world evolution and route geometry.
        Mechanic pairs create earned emergent routes.
      </Text>
      {!editor&&<Text style={s.warning}>Authenticated creator access required.</Text>}
      <View style={s.panel}>
        <Text style={s.heading}>Beyond quintillion-scale world systems</Text>
        <Text style={s.copy}>
          {catalog?.mechanically_separable_binary_nuclei.toLocaleString()||
            '16,777,216'} distinguishable original rule-enable profiles,
          {' '}{counts} indexed executable four-level rule programs.
        </Text>
        <Text style={s.hint}>
          These are potentially distinct game mechanics, not finished unique
          commercial games. Rule programs can additionally be combined with
          Dragon's 128-axis environment Codex for much larger variation.
        </Text>
        <Text style={s.heading}>Load one of 16.7 million original rule nuclei</Text>
        <TextInput value={nucleus} style={s.input}
          keyboardType="number-pad" maxLength={8}
          accessibilityLabel="Original gameplay nucleus index"
          onChangeText={setNucleus} editable={editor&&!busy}/>
        <TouchableOpacity style={[s.action,busy&&s.disabled]}
          disabled={!editor||busy} onPress={fromNucleus}>
          <Text style={s.actionText}>Materialize executable original rules</Text>
        </TouchableOpacity>
      </View>
      <View style={s.panel}>
        <Text style={s.heading}>32-mechanic composition</Text>
        <View style={s.chips}>
          {[0,1,2,3].map(level=>(
            <TouchableOpacity key={level} style={s.chip}
              onPress={()=>setPreset(level)} disabled={!editor||busy}>
              <Text style={s.copy}>All level {level}</Text>
            </TouchableOpacity>
          ))}
        </View>
        {catalog?.mechanics.map((mechanic,i)=>(
          <View key={mechanic.id} style={s.mechanic}>
            <Text style={s.copy}>
              {i+1}. {pretty(mechanic.id)} · {pretty(mechanic.domain)}
            </Text>
            <Text style={s.hint}>
              Requires {mechanic.cost_resource} · produces {mechanic.reward_resource}
            </Text>
            <View style={s.chips}>
              {[0,1,2,3].map(level=>(
                <TouchableOpacity key={level} accessibilityRole="button"
                  disabled={!editor||busy}
                  style={[s.chip,levels[i]===level&&s.selected]}
                  onPress={()=>changeLevel(i,level)}>
                  <Text style={s.copy}>
                    {['off','basic','advanced','intense'][level]}
                  </Text>
                </TouchableOpacity>
              ))}
            </View>
          </View>
        ))}
      </View>
      <View style={s.panel}>
        <Text style={s.heading}>Exact large-integer rule program</Text>
        <TouchableOpacity style={[s.chip,useIndex&&s.selected]}
          disabled={busy} onPress={()=>{setUseIndex(!useIndex);invalidate();}}>
          <Text style={s.copy}>
            {useIndex?'● Use exact decimal index':'○ Use edited mechanic levels'}
          </Text>
        </TouchableOpacity>
        {useIndex&&<TextInput style={s.input} value={manualIndex}
          maxLength={20} keyboardType="number-pad"
          accessibilityLabel="Full precise original mechanic program address"
          editable={editor&&!busy}
          onChangeText={v=>{setManualIndex(v);invalidate();}}/>}
        <Text style={s.heading}>Optional verified World Codex environmental parent</Text>
        <TextInput style={s.input} value={parentCodex}
          maxLength={900} keyboardType="number-pad"
          accessibilityLabel="Optional decimal World Codex parent address"
          editable={editor&&!busy}
          placeholder="Blank for independent original game rules"
          placeholderTextColor="#92ad9f"
          onChangeText={v=>{setParentCodex(v);invalidate();}}/>
        <TouchableOpacity style={[s.action,(!editor||busy||
          (useIndex&&!validExact))&&s.disabled]}
          disabled={!editor||busy||(useIndex&&!validExact)}
          onPress={create}>
          <Text style={s.actionText}>Compile and prove original gameplay</Text>
        </TouchableOpacity>
      </View>
      {busy&&<ActivityIndicator color="#acf4c6"/>}
      {preview&&player&&<>
        <View style={s.panel}>
          <Text style={s.heading}>Causally tested game design</Text>
          <Text style={s.copy}>
            {preview.program.mechanics_available} active original mechanics ·
            {' '}{preview.causal_gameplay_proofs.mechanic_execution_witnesses
              .filter(item=>item.available).length} actual causal replay witnesses.
          </Text>
          <Text style={s.hint}>
            Program {preview.program.decimal_index} ·
            {' '}{preview.program.source_digest.slice(0,20)}…
          </Text>
          {preview.causal_gameplay_proofs.mechanic_execution_witnesses
            .filter(item=>item.available).slice(0,8).map(item=>(
              <Text key={item.axis} style={s.hint}>
                {pretty(item.axis)} · level {item.level} ·
                {' '}resource cost {item.cost} · actual yield {item.gain}
              </Text>
            ))}
          <Text style={s.success}>
            No fixed win is required; generated actions and outcomes remain replayable.
          </Text>
        </View>
        <View style={s.panel}>
          <Text style={s.heading}>Play the actual game mechanics</Text>
          <Text style={s.copy}>
            Turn {player.turn} · location ({player.x}, {player.y}) ·
            realm {player.realm} · world era {player.era}
          </Text>
          <Text style={s.copy}>
            {resourceNames.map((item,i)=>item+': '+player.resources[i])
              .join(' · ')}
          </Text>
          <Text style={s.hint}>
            Actual world mutations: {player.changed_places.length} ·
            earned cross-mechanic links: {player.unlocked_joins.length}
          </Text>
          {!!player.endings.length&&<Text style={s.success}>
            Original story conclusions: {player.endings.map(pretty).join(' · ')}.
            Exploration can continue afterward.
          </Text>}
          {options.filter(item=>item.level!==0).map(option=>(
            <TouchableOpacity key={option.id}
              accessibilityRole="button"
              style={[s.option,(!option.available||busy)&&s.disabled]}
              disabled={!option.available||busy||history.length>=128}
              onPress={()=>play(option.id)}>
              <Text style={s.actionText}>{pretty(option.id)}</Text>
              <Text style={s.hint}>
                {option.available
                  ?('Spend '+option.cost+' '+option.cost_resource+
                    ', earn '+option.gain+' '+option.gain_resource)
                  :pretty(option.reason)}
              </Text>
            </TouchableOpacity>
          ))}
          <View style={s.chips}>
            <TouchableOpacity style={s.chip}
              disabled={!history.length||busy} onPress={undo}>
              <Text style={s.actionText}>Undo played decision</Text>
            </TouchableOpacity>
            <TouchableOpacity style={s.chip} disabled={busy}
              onPress={()=>guide({
                intent:'new_original_start',actions:[],
                source_digest:preview.program.source_digest,
                ending_variants:[],actual_cross_mechanic_joins:[],
                actual_resource_changes:[],world_changes:[],
                final_turn:0,final_era:0,final_realm:0,
                final_history_digest:player.history_digest,trace_digest:'',
              })}>
              <Text style={s.actionText}>Restart original game</Text>
            </TouchableOpacity>
          </View>
        </View>
        <View style={s.panel}>
          <Text style={s.heading}>1024 earned cross-mechanic interactions</Text>
          <Text style={s.copy}>
            Direction matters. Combining a river mechanic into a settlement
            is a different playable action from using the settlement mechanic
            to influence the river. Each interaction has real prerequisites,
            an energy cost, resource effects and an altered world route.
          </Text>
          <TouchableOpacity style={[s.action,busy&&s.disabled]}
            disabled={busy} onPress={()=>discoverFusions(fusionPage)}>
            <Text style={s.actionText}>Discover actual earned interactions</Text>
          </TouchableOpacity>
          <View style={s.chips}>
            <TouchableOpacity style={s.chip} disabled={busy||fusionPage===0}
              onPress={()=>discoverFusions(fusionPage-32)}>
              <Text style={s.copy}>Previous 32</Text>
            </TouchableOpacity>
            <Text style={s.copy}>Options {fusionPage+1}–{fusionPage+32} / 1024</Text>
            <TouchableOpacity style={s.chip}
              disabled={busy||fusionPage>=992}
              onPress={()=>discoverFusions(fusionPage+32)}>
              <Text style={s.copy}>Next 32</Text>
            </TouchableOpacity>
          </View>
          {fusions.filter(x=>x.available).map(option=>(
            <TouchableOpacity key={option.id} accessibilityRole="button"
              disabled={busy||history.length>=128}
              style={s.option} onPress={()=>play(option.id)}>
              <Text style={s.actionText}>{pretty(option.id)}</Text>
              <Text style={s.hint}>
                Cost {option.cost} {option.cost_resource} ·
                Earn {option.gain} {option.gain_resource} ·
                Actual earned-gameplay synthesis
              </Text>
            </TouchableOpacity>
          ))}
          {!!fusions.length&&!fusions.some(x=>x.available)&&
            <Text style={s.hint}>
              Nothing unlocked on this page yet. Practice the indicated
              source and destination mechanics before attempting a fusion.
            </Text>}
        </View>
        <View style={s.panel}>
          <Text style={s.heading}>Actual alternative experiences</Text>
          <TouchableOpacity style={[s.action,busy&&s.disabled]}
            disabled={busy} onPress={alternatives}>
            <Text style={s.actionText}>
              Produce 16 real journeys across this game design
            </Text>
          </TouchableOpacity>
          {portfolio&&<>
            <Text style={s.copy}>
              {portfolio.distinct_observed_action_sequences}
              {' '}different actually played action histories and
              {' '}{portfolio.different_measured_final_stories}
              {' '}measured final states among {portfolio.sampled} sampled routes.
            </Text>
            {portfolio.experiences.map((item,i)=>(
              <TouchableOpacity key={i} style={s.option}
                disabled={busy} onPress={()=>guide(item)}>
                <Text style={s.actionText}>
                  {i+1}. {pretty(item.intent)}
                </Text>
                <Text style={s.copy}>
                  {item.actions.length} verified actions ·
                  {' '}{item.world_changes.length} world changes ·
                  {' '}{item.ending_variants.length} experienced endings
                </Text>
              </TouchableOpacity>
            ))}
          </>}
          {guided&&guided.actions.length>0&&
           history.length<guided.actions.length&&
            <TouchableOpacity style={[s.action,busy&&s.disabled]}
              disabled={busy} onPress={advance}>
              <Text style={s.actionText}>
                Play next genuine alternative decision
                {' '}{history.length}/{guided.actions.length}
              </Text>
            </TouchableOpacity>}
        </View>
      </>}
      {!!failure&&<Text style={s.warning} accessibilityRole="alert">{failure}</Text>}
      {!!notice&&<Text style={s.success} accessibilityRole="alert">{notice}</Text>}
      <Text style={s.hint}>
        This is an executable original-game rules layer. Quintillion-scale
        addresses denote distinguishable formal rule programs, not completed
        levels, AAA game engines, original authored plots, or publication
        clearance. Consumer-facing releases still need actual assets,
        localization, difficulty testing, provenance and platform builds.
      </Text>
    </ScrollView>
  </SafeAreaView>;
}
export default function DragonOriginalsForge(){
  return <StudioLoginGate><Creator/></StudioLoginGate>;
}
const s=StyleSheet.create({
  root:{flex:1,backgroundColor:'#101927'},
  page:{padding:16,paddingBottom:70,gap:13,maxWidth:900,
        width:'100%',alignSelf:'center'},
  title:{fontSize:25,fontWeight:'700',color:'#f3f9f5'},
  heading:{fontSize:16,fontWeight:'700',color:'#d2ecdf'},
  copy:{fontSize:13,lineHeight:20,color:'#c5d9cf'},
  hint:{fontSize:12,lineHeight:19,color:'#abc2b5'},
  warning:{fontSize:13,color:'#ffbaa9'},
  success:{fontSize:13,color:'#adebbf'},
  input:{backgroundColor:'#1d3440',borderWidth:1,
         borderColor:'#5c756e',borderRadius:8,
         padding:11,color:'#fff'},
  panel:{padding:13,borderRadius:12,backgroundColor:'#1a2d3b',gap:8},
  mechanic:{padding:11,backgroundColor:'#213946',gap:5,borderRadius:9},
  chips:{flexDirection:'row',flexWrap:'wrap',gap:6},
  chip:{padding:10,backgroundColor:'#2a4452',borderRadius:8},
  selected:{backgroundColor:'#45885d'},
  action:{backgroundColor:'#347c59',padding:14,borderRadius:9,alignItems:'center'},
  actionText:{fontSize:13,fontWeight:'700',color:'#efffed'},
  option:{backgroundColor:'#274250',padding:11,borderRadius:8,gap:4},
  disabled:{opacity:0.42},
});
