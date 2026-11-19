/**
 * Dragon Original Route World — actually playable free-roam multimodal game.
 *
 * Server replays every action from the original bounded game-world graph.
 * The phone cannot forge teleportation, magic gates, money, weather, stamina,
 * secrets or progression. This editor never compiles source or promotes AI.
 */
import React from 'react';
import {
  ActivityIndicator,Platform,SafeAreaView,ScrollView,StyleSheet,Text,
  TextInput,TouchableOpacity,View,
} from 'react-native';
import * as FileSystem from 'expo-file-system/legacy';
import * as Sharing from 'expo-sharing';

import StudioLoginGate,{useStudioAuth} from '../src/auth/StudioLoginGate';
import {authHeaders} from '../src/auth/gameforgeAuth';
import {API_BASE} from '../utils/apiBase';

const API=(API_BASE||'').replace(/\/$/,'')+
  '/api/dragon-academy/native/production/routes';
type Weather='clear'|'rain'|'windy'|'storm'|'snow'|'high_tide';
const WEATHER:readonly Weather[]=['clear','rain','windy','storm','snow','high_tide'];

type NextRoute={
  edge:string;to:string;mode:string;family:string;shape:string[];
  time_minutes:number;waiting_minutes:number;price:number;fatigue:number;
  fuel:number;oxygen:number;mana:number;
  danger:number;scenic:number;access:string;available:boolean;
};
type GameState={
  world_position:string;goal:string;completed:boolean;
  visited_places:string[];played_edges:string[];known_tokens:string[];
  remaining_cash:number;remaining_energy:number;
  remaining_fuel:number;remaining_oxygen:number;remaining_mana:number;
  elapsed_minutes:number;
  clock_minute:number;options:NextRoute[];
};
type WinningRoute={
  edges:string[];places:string[];modes:string[];shapes:string[];
  objective:string;elapsed_minutes:number;money_spent:number;
  risk:number;energy_used:number;fuel_used:number;oxygen_used:number;
  mana_used:number;secret_edges:number;unlockable_edges:number;
  loops:number;sights:number;digest:string;
};
type WorldPreview={
  ok:boolean;world_digest:string;
  world:{places:number;routes:number;dead_end_places:string[];
    secret_routes:number;locked_routes:number;timed_routes:number;
    weather_routes:number;families:string[];real_cycle_edges:number};
  routes:{routes:WinningRoute[];truncated:boolean;examined_states:number;claims:string};
  player:GameState;source_only:boolean;
};

function label(text:string){return text.replace(/_/g,' ');}
function duration(minutes:number):string{
  if(!Number.isFinite(minutes)||minutes<0)return 'unverified duration';
  if(minutes>=525600){
    const years=Math.floor(minutes/525600);
    const days=Math.floor((minutes%525600)/1440);
    return years+' years'+(days?' '+days+' days':'');
  }
  if(minutes>=1440)return Math.floor(minutes/1440)+' days '+
    Math.floor((minutes%1440)/60)+' hours';
  if(minutes>=60)return Math.floor(minutes/60)+'h '+(minutes%60)+'m';
  return minutes+' min';
}
async function post<T>(route:string,body:object):Promise<T>{
  const response=await fetch(API+route,{
    method:'POST',
    headers:authHeaders({'Content-Type':'application/json'}),
    cache:'no-store',
    body:JSON.stringify(body),
  });
  if(!response.ok)throw new Error(
    response.status===422?'The planned route is unavailable or exceeds the original game constraints.':
    response.status===403?'Editor permission and original-content approval are required.':
    'The Dragon route-world service is unavailable.');
  return response.json() as Promise<T>;
}
async function saveOriginalSource(blob:Blob):Promise<void>{
  if(!blob.size||blob.size>1_500_000)
    throw new Error('The original C99 source archive exceeds its size limit.');
  const filename='dragon-original-world-routes.zip';
  if(Platform.OS==='web'){
    const url=URL.createObjectURL(blob);
    try{
      const element=document.createElement('a');
      element.href=url;element.download=filename;
      document.body.appendChild(element);element.click();element.remove();
    }finally{setTimeout(()=>URL.revokeObjectURL(url),15_000);}
    return;
  }
  if(!FileSystem.documentDirectory)
    throw new Error('Local device export storage is unavailable.');
  const base64=await new Promise<string>((resolve,reject)=>{
    const reader=new FileReader();
    reader.onerror=()=>reject(new Error('Cannot read original game source ZIP.'));
    reader.onload=()=>{
      if(typeof reader.result!=='string')return reject(new Error('Source ZIP encoding failed.'));
      const comma=reader.result.indexOf(',');
      if(comma<0)return reject(new Error('Source ZIP data missing.'));
      resolve(reader.result.slice(comma+1));
    };
    reader.readAsDataURL(blob);
  });
  const location=FileSystem.documentDirectory+filename;
  await FileSystem.writeAsStringAsync(location,base64,{
    encoding:FileSystem.EncodingType.Base64,
  });
  if(await Sharing.isAvailableAsync())await Sharing.shareAsync(location,{
    mimeType:'application/zip',dialogTitle:'Original Dragon C99 World Game',
  });
}

function RouteWorldEditor(){
  const {role}=useStudioAuth();
  const editor=role==='admin'||role==='editor';
  const [seed,setSeed]=React.useState('1977');
  const [weather,setWeather]=React.useState<Weather>('clear');
  const [hour,setHour]=React.useState(8);
  const [review,setReview]=React.useState<WorldPreview|null>(null);
  const [game,setGame]=React.useState<GameState|null>(null);
  const [moves,setMoves]=React.useState<string[]>([]);
  const [follow,setFollow]=React.useState<WinningRoute|null>(null);
  const [working,setWorking]=React.useState(false);
  const [attested,setAttested]=React.useState(false);
  const [approved,setApproved]=React.useState(false);
  const [success,setSuccess]=React.useState('');
  const [failure,setFailure]=React.useState('');
  const generation=React.useRef(0);
  const numericSeed=Number(seed);
  const validSeed=/^\d{1,10}$/.test(seed)&&Number.isInteger(numericSeed)&&
    numericSeed>=0&&numericSeed<=0xffffffff;
  const parameters={seed:numericSeed,weather,hour};

  const reset=()=>{
    generation.current++;
    setReview(null);setGame(null);setMoves([]);setFollow(null);
    setSuccess('');setFailure('');setApproved(false);
  };
  const analyze=async()=>{
    if(!editor||working||!validSeed)return;
    const epoch=++generation.current;
    setWorking(true);setFailure('');setSuccess('');
    setReview(null);setGame(null);setMoves([]);setFollow(null);
    try{
      const result=await post<WorldPreview>('/preview',{
        ...parameters,max_routes:10,search_budget:1200,include_long:true,
      });
      if(!result.ok||!result.source_only||!result.world_digest||
         !result.player||!Array.isArray(result.routes?.routes)||
         result.routes.routes.length>12)throw new Error('Invalid original world proof.');
      if(epoch===generation.current){
        setReview(result);setGame(result.player);
      }
    }catch(error){
      if(epoch===generation.current)setFailure(
        error instanceof Error?error.message:'Cannot generate original route world.');
    }finally{if(epoch===generation.current)setWorking(false);}
  };
  const play=async(edge:string,history=moves)=>{
    if(!editor||working||!review||!validSeed||
       !/^[a-z][a-z0-9_]{0,39}$/.test(edge)||history.length>=80)return;
    const epoch=++generation.current;
    setWorking(true);setFailure('');
    try{
      const path=[...history,edge];
      const current=await post<GameState&{ok:boolean}>('/play',{
        ...parameters,moves:path,
      });
      if(!current.ok||current.played_edges.join('|')!==path.join('|'))
        throw new Error('Original-world move verification failed.');
      if(epoch===generation.current){
        setMoves(path);setGame(current);
        if(current.completed){
          setSuccess('Reached the original world goal. Explore another route on restart!');
        }else setSuccess('');
      }
    }catch(error){
      if(epoch===generation.current)setFailure(
        error instanceof Error?error.message:'This path could not be traversed.');
    }finally{if(epoch===generation.current)setWorking(false);}
  };
  const restart=()=>{
    generation.current++;setGame(review?.player??null);
    setMoves([]);setFollow(null);setFailure('');setSuccess('');
  };
  const replayRecommended=async(choice:WinningRoute)=>{
    if(!review||working||!Array.isArray(choice.edges)||!choice.edges.length)return;
    // Play the real route one decision at a time. No jumping directly to the
    // success state: the server verifies every edge and resource consumed.
    restart();setFollow(choice);
  };
  const stepRecommended=()=>{
    if(!follow||working||!game)return;
    const next=follow.edges[moves.length];
    if(typeof next!=='string')return;
    play(next);
  };
  const exportWorld=async()=>{
    if(!editor||!attested||!approved||!validSeed||working||!review)return;
    setWorking(true);setFailure('');setSuccess('');
    try{
      const response=await fetch(API+'/source-bundle',{
        method:'POST',
        headers:authHeaders({'Content-Type':'application/json'}),
        cache:'no-store',
        body:JSON.stringify({
          ...parameters,original_work_attested:true,approved:true,
        }),
      });
      if(!response.ok)throw new Error('Source export rights, permission or limits failed.');
      const blob=await response.blob();
      await saveOriginalSource(blob);
      setSuccess('Original playable native C99 route-world project exported as SOURCE.');
    }catch(error){
      setFailure(error instanceof Error?error.message:'Source export failed.');
    }finally{setWorking(false);}
  };
  return (
    <SafeAreaView style={s.root}>
      <ScrollView contentContainerStyle={s.page}>
        <Text style={s.title}>Dragon · World Routes</Text>
        <Text style={s.copy}>
          Create a genuinely playable world of streets, public transport,
          mountains, sea lanes, aircraft, magic and orbital travel.
          Explore dead ends, collect clues, unlock secrets, chase shortcuts,
          take scenic or impractical detours, and free-roam to the goal.
        </Text>
        {!editor&&<Text style={s.warning}>
          Only authenticated editors/admins can generate or export original worlds.
        </Text>}
        <Text style={s.heading}>Original world seed</Text>
        <TextInput style={s.input} accessibilityLabel="Original game world seed"
          value={seed} onChangeText={v=>{setSeed(v);reset();}}
          keyboardType="number-pad" maxLength={10}
          editable={!working&&editor}/>
        <Text style={s.heading}>Climate and travel conditions</Text>
        <View style={s.chips}>
          {WEATHER.map(item=>(
            <TouchableOpacity key={item} accessibilityRole="button"
              accessibilityState={{selected:weather===item}}
              disabled={working||!editor}
              onPress={()=>{setWeather(item);reset();}}
              style={[s.chip,weather===item&&s.selected]}>
              <Text style={s.text}>{label(item)}</Text>
            </TouchableOpacity>
          ))}
        </View>
        <Text style={s.heading}>Game starts at {hour}:00</Text>
        <View style={s.chips}>
          {[0,6,8,12,18,22].map(time=>(
            <TouchableOpacity key={time} accessibilityRole="button"
              accessibilityState={{selected:hour===time}}
              onPress={()=>{setHour(time);reset();}}
              disabled={working||!editor}
              style={[s.chip,hour===time&&s.selected]}>
              <Text style={s.text}>{time}:00</Text>
            </TouchableOpacity>
          ))}
        </View>
        <TouchableOpacity accessibilityRole="button"
          disabled={!editor||working||!validSeed} style={[s.action,
            (!editor||working||!validSeed)&&s.disabled]}
          onPress={analyze}>
          <Text style={s.actionText}>Generate and analyze playable route world</Text>
        </TouchableOpacity>
        {working&&<ActivityIndicator color="#9ce8be"/>}
        {review&&game&&<>
          <View style={s.panel}>
            <Text style={s.heading}>Real original world — {review.world.places} places</Text>
            <Text style={s.copy}>
              {review.world.routes} traversable segments · {review.world.families.length}
              {' '}travel families · {review.world.secret_routes} secret segments
              {' · '}{review.world.timed_routes} timetable routes
            </Text>
            <Text style={s.copy}>
              {review.world.dead_end_places.length} structural dead ends ·
              {' '}{review.world.real_cycle_edges} cycle-forming connections
            </Text>
            <Text style={s.hint}>
              Distinct paths are measured in this generated world, not
              harvested from another game. Vehicle physics and human enjoyment
              require separate evidence.
            </Text>
          </View>
          <View style={s.panel}>
            <Text style={s.heading}>
              {game.completed?'Goal reached!':'Explore '+label(game.world_position)}
            </Text>
            <Text style={s.copy}>
              {duration(game.elapsed_minutes)} elapsed · {game.remaining_cash} currency ·
              {' '}{game.remaining_energy} stamina · {game.remaining_fuel} fuel ·
              {' '}{game.remaining_oxygen} oxygen · {game.remaining_mana} mana
            </Text>
            <Text style={s.hint}>
              Inventory: {game.known_tokens.map(label).join(', ')}
            </Text>
            <Text style={s.hint}>
              Travelled: {game.visited_places.map(label).join(' → ')}
            </Text>
            {!game.completed&&game.options.map(option=>(
              <TouchableOpacity key={option.edge} accessibilityRole="button"
                disabled={working||!option.available}
                onPress={()=>play(option.edge)}
                style={[s.route,(!option.available||working)&&s.disabled]}>
                <Text style={s.actionText}>{label(option.mode)} → {label(option.to)}</Text>
                <Text style={s.copy}>
                  {duration(option.time_minutes)} + {duration(option.waiting_minutes)} wait ·
                  {' '}{option.price} fare · {option.fatigue} fatigue ·
                  {' '}{option.fuel} fuel · {option.oxygen} O₂ · {option.mana} mana
                </Text>
                <Text style={s.hint}>
                  {option.available?option.shape.map(label).join(' / '):
                    'Locked: '+label(option.access)}
                </Text>
              </TouchableOpacity>
            ))}
            {follow&&<TouchableOpacity accessibilityRole="button"
              disabled={working||game.completed}
              style={[s.action,working&&s.disabled]}
              onPress={stepRecommended}>
              <Text style={s.actionText}>
                Follow chosen route: {Math.min(moves.length,follow.edges.length)}
                /{follow.edges.length} actual decisions
              </Text>
            </TouchableOpacity>}
            <TouchableOpacity accessibilityRole="button" style={s.chip}
              onPress={restart} disabled={working}>
              <Text style={s.actionText}>Restart original world</Text>
            </TouchableOpacity>
          </View>
          <View style={s.panel}>
            <Text style={s.heading}>
              {review.routes.routes.length} measured winning itineraries
            </Text>
            <Text style={s.hint}>
              Search examined {review.routes.examined_states} bounded states.
              {review.routes.truncated?' Some searches reached their budget.':''}
              Other valid routes may remain undiscovered.
            </Text>
            {review.routes.routes.map((route,index)=>(
              <TouchableOpacity key={route.digest+index} accessibilityRole="button"
                style={s.route} disabled={working}
                onPress={()=>replayRecommended(route)}>
                <Text style={s.actionText}>
                  {index+1}. {label(route.objective)} · {duration(route.elapsed_minutes)}
                </Text>
                <Text style={s.copy}>
                  {route.edges.length} segments · {route.money_spent} fare ·
                  {' '}{route.risk} risk · {route.sights} scenic ·
                  {' '}{route.fuel_used} fuel · {route.oxygen_used} O₂ ·
                  {' '}{route.mana_used} mana
                </Text>
                <Text style={s.hint}>
                  {route.modes.map(label).join(' → ')}
                </Text>
              </TouchableOpacity>
            ))}
          </View>
        </>}
        <TouchableOpacity accessibilityRole="checkbox"
          accessibilityState={{checked:attested}} style={s.chip}
          disabled={!editor||working}
          onPress={()=>{setAttested(!attested);setApproved(false);}}>
          <Text style={s.copy}>
            {attested?'☑':'☐'} I attest that this is original homebrew,
            not a copied game world or unlicensed commercial level.
          </Text>
        </TouchableOpacity>
        <TouchableOpacity accessibilityRole="checkbox"
          accessibilityState={{checked:approved}} style={s.chip}
          disabled={!editor||working||!attested||!review}
          onPress={()=>setApproved(!approved)}>
          <Text style={s.copy}>
            {approved?'☑':'☐'} Approve source-only native C99 original-world export
          </Text>
        </TouchableOpacity>
        <TouchableOpacity accessibilityRole="button" style={[
          s.action,(!editor||working||!approved||!attested||!review)&&s.disabled,
        ]} disabled={!editor||working||!approved||!attested||!review}
          onPress={exportWorld}>
          <Text style={s.actionText}>
            Export actual playable C99 travel game (SOURCE ZIP)
          </Text>
        </TouchableOpacity>
        {!!failure&&<Text accessibilityRole="alert" style={s.warning}>{failure}</Text>}
        {!!success&&<Text accessibilityRole="alert" style={s.success}>{success}</Text>}
        <Text style={s.hint}>
          Game paths and playable C99 abstract travel are implemented.
          Physical flight, swimming, orbital dynamics and third-party platform
          certification are not implied. Original-content attestation is not
          independent legal clearance.
        </Text>
      </ScrollView>
    </SafeAreaView>
  );
}
export default function DragonRouteWorld(){
  return <StudioLoginGate><RouteWorldEditor/></StudioLoginGate>;
}
const s=StyleSheet.create({
  root:{flex:1,backgroundColor:'#0e1520'},
  page:{padding:18,paddingBottom:80,gap:12,width:'100%',maxWidth:840,alignSelf:'center'},
  title:{fontSize:25,fontWeight:'700',color:'#eef8f3'},
  heading:{fontSize:16,fontWeight:'700',color:'#d3efe0'},
  text:{fontSize:13,color:'#edf6f2'},
  copy:{fontSize:13,lineHeight:20,color:'#c2d4d0'},
  hint:{fontSize:12,lineHeight:19,color:'#aabcb7'},
  warning:{fontSize:14,color:'#ffc0ab'},
  success:{fontSize:14,color:'#aff1c6'},
  chips:{flexDirection:'row',flexWrap:'wrap',gap:8},
  chip:{padding:12,borderRadius:9,backgroundColor:'#233c47'},
  selected:{backgroundColor:'#386d55'},
  input:{backgroundColor:'#1b2d38',borderColor:'#55756c',borderWidth:1,
         padding:12,borderRadius:10,color:'#fff'},
  action:{padding:14,backgroundColor:'#327856',borderRadius:10,alignItems:'center'},
  actionText:{fontSize:14,fontWeight:'700',color:'#eaffee'},
  disabled:{opacity:0.38},
  panel:{backgroundColor:'#182e3a',padding:14,borderRadius:12,gap:9},
  route:{backgroundColor:'#244151',padding:12,borderRadius:10,gap:4},
});
