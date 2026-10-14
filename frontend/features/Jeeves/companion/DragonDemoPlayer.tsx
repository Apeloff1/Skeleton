/** Isolated player for an integrity-checked, self-contained Dragon demo.
 * No app cookies, origin navigation, requests or bridge commands are granted.
 * Playing is a practice attempt, NOT a reviewed playtest receipt or XP event.
 */
import React from 'react';
import {Modal,Pressable,SafeAreaView,StyleSheet,Text,View} from 'react-native';
import WebView from 'react-native-webview';
import type {DemoView} from './useDragonAcademy';

const safeNavigation=(url:string)=>url==='about:blank'||url==='about:blank/'||
 url.startsWith('data:text/html');

export default function DragonDemoPlayer({
 demo,onClose,
}:{demo:DemoView|null;onClose:()=>void}){
 return <Modal visible={!!demo} onRequestClose={onClose}
  animationType="slide" presentationStyle="fullScreen">
  <SafeAreaView style={s.root}>
   <View style={s.header}>
    <View style={s.title}>
     <Text style={s.heading}>Dragon's little game lab</Text>
     <Text style={s.caption}>Offline experiment · not a verified playtest</Text>
    </View>
    <Pressable accessibilityRole="button" accessibilityLabel="Close game demo"
     onPress={onClose} style={s.close}><Text style={s.closeText}>✕ Close</Text></Pressable>
   </View>
   {demo&&<WebView
    key={demo.attemptId}
    source={{html:demo.html,baseUrl:'about:blank'}}
    originWhitelist={['about:blank','data:*']}
    onShouldStartLoadWithRequest={request=>safeNavigation(request.url)}
    javaScriptEnabled
    domStorageEnabled={false}
    incognito
    setSupportMultipleWindows={false}
    javaScriptCanOpenWindowsAutomatically={false}
    thirdPartyCookiesEnabled={false}
    sharedCookiesEnabled={false}
    allowFileAccess={false}
    allowUniversalAccessFromFileURLs={false}
    mixedContentMode="never"
    allowsBackForwardNavigationGestures={false}
    style={s.game}
   />}
   <Text style={s.footer}>Generated from reviewed knowledge. Use the on-screen controls on mobile. Your interaction does not automatically change Dragon XP.</Text>
  </SafeAreaView>
 </Modal>;
}
const s=StyleSheet.create({
 root:{flex:1,backgroundColor:'#09151a'},header:{backgroundColor:'#101827',
  flexDirection:'row',alignItems:'center',paddingHorizontal:15,paddingVertical:13,gap:12},
 title:{flex:1},heading:{fontSize:16,fontWeight:'900',color:'#f8fafc'},
 caption:{fontSize:10,color:'#cbd5e1',marginTop:3},
 close:{paddingHorizontal:13,paddingVertical:10,borderRadius:11,backgroundColor:'#374151'},
 closeText:{color:'#fff',fontSize:12,fontWeight:'800'},game:{flex:1,backgroundColor:'#09151a'},
 footer:{padding:9,color:'#cbd5e1',fontSize:10,lineHeight:15,backgroundColor:'#101827'},
});
