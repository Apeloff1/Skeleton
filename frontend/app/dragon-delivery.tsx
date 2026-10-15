/** Canonical, authenticated Dragon delivery workbench route. */
import React from 'react';
import {ScrollView,StyleSheet,Text,View} from 'react-native';
import StudioLoginGate from '../src/auth/StudioLoginGate';
import api from '../src/utils/apiClient';
import {authHeaders} from '../src/auth/gameforgeAuth';
import DragonDeliveryWorkbench from '../features/Jeeves/companion/DragonDeliveryWorkbench';
import {type NativeTarget,normalizeNativeTargets} from '../features/Jeeves/companion/dragonNativeTargets';

function DeliveryScreen(){
 const [targets,setTargets]=React.useState<NativeTarget[]>([]);
 const [error,setError]=React.useState('');
 React.useEffect(()=>{
  let live=true;
  void api.get<Record<string,unknown>>('/api/dragon-academy/native/targets',{
   headers:authHeaders(),timeoutMs:12000,retries:0,
  }).then(result=>{
   if(!live)return;
   if(!result.ok||result.data?.ok!==true){
    setError('Native target catalog is not available.');return;
   }
   setTargets(normalizeNativeTargets(result.data.targets));
  }).catch(()=>{if(live)setError('Native target catalog is not available.');});
  return()=>{live=false;};
 },[]);
 return <ScrollView style={s.root} contentContainerStyle={s.content}>
   <Text style={s.title}>Dragon knowledge and native design</Text>
   <Text style={s.notice}>Reviewed source evidence and original design planning are available here. Native source delivery requires current independently approved evidence, consented practice lessons and the shared resource runtime. Generated source is not a compiled or released game.</Text>
   {!!error&&<Text accessibilityRole="alert" style={s.warning}>{error}</Text>}
   <DragonDeliveryWorkbench targets={targets}/>
 </ScrollView>;
}
export default function DragonDeliveryRoute(){
 return <StudioLoginGate><DeliveryScreen/></StudioLoginGate>;
}
const s=StyleSheet.create({
 root:{flex:1,backgroundColor:'#091916'},
 content:{padding:16,paddingBottom:48,gap:13},
 title:{color:'#e0f9eb',fontSize:23,fontWeight:'800'},
 notice:{fontSize:13,color:'#a8c8bd',lineHeight:20},
 warning:{fontSize:13,color:'#ffd6a0'},
});
