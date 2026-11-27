import React,{useState} from 'react';
import {Pressable,StyleSheet,Text,View} from 'react-native';
import type {CreatorComparison,CreatorReferenceChange} from '../../../product/dragonCreatorComparison';

const label=(path:string)=>path.replace(/^portable_design\./,'').replace(/_/g,' ');
const display=(value:string|number|boolean|string[])=>Array.isArray(value)?value.join(', '):typeof value==='boolean'?value?'Yes':'No':String(value)||'(empty)';
export default function DragonCreatorComparison({comparison,close}:{comparison:CreatorComparison;close:()=>void}){
  const [expanded,setExpanded]=useState<number[]>([]);
  const changes=comparison.changes;
  const unchanged=!changes.fields.length&&!changes.brief.changed&&!changes.citations.order_changed&&!changes.boards.items.length;
  const references=(rows:CreatorReferenceChange[],title:string)=><View style={s.stack}>
    <Text style={s.label}>{title} · {rows.reduce((sum,row)=>sum+row.count,0)}</Text>
    {rows.map(row=><View key={row.reference_sha256} style={s.reference}>
      <Text style={s.text}>{row.title||row.source_id}{row.title_truncated?'…':''}{row.count>1?' ×'+row.count:''}</Text>
      <Text style={s.help} selectable>{row.source_id} · reference {row.revision_digest.slice(0,12)}</Text>
      <Text style={s.help} selectable>{row.url}{row.url_truncated?'…':''}</Text>
    </View>)}
  </View>;
  return <View testID="dcp-comparison" style={s.panel}>
    <View style={s.row}><Text accessibilityRole="header" style={s.title}>Revision {comparison.from.version} → revision {comparison.to.version}</Text>
      <Pressable accessibilityRole="button" accessibilityLabel="Close revision comparison" onPress={close} style={s.button}><Text style={s.text}>Close</Text></Pressable></View>
    <Text style={s.help}>Saved source comparison · your current draft is preserved.</Text>
    {comparison.observed_head_version>comparison.to.version&&<Text style={s.help}>A newer saved revision ({comparison.observed_head_version}) was observed. This comparison remains bound to revisions {comparison.from.version} and {comparison.to.version}.</Text>}
    {unchanged&&<Text testID="dcp-comparison-identical" style={s.text}>These saved revisions contain the same creator design.</Text>}
    {!!changes.fields.length&&<View testID="dcp-comparison-fields" style={s.stack}>
      <Text style={s.label}>Design changes · {changes.fields.length}</Text>
      {changes.fields.map(field=><View key={field.path} style={s.field}>
        <Text style={s.label}>{label(field.path)}</Text>
        <View style={s.row}><Text style={[s.value,s.before]} selectable>Before: {display(field.before)}{field.before_truncated?'…':''}</Text>
          <Text style={[s.value,s.after]} selectable>After: {display(field.after)}{field.after_truncated?'…':''}</Text></View>
        {(field.before_truncated||field.after_truncated)&&<Text style={s.help}>Long text is previewed here; the saved revisions retain the complete values.</Text>}
      </View>)}
    </View>}
    {changes.brief.changed&&<View testID="dcp-comparison-brief" style={s.stack}>
      <Text style={s.label}>Design brief</Text>
      <View style={s.row}><View style={[s.value,s.before]}><Text style={s.help}>Before · {changes.brief.before_characters} characters</Text><Text selectable style={s.text}>{changes.brief.before_preview||'(empty)'}{changes.brief.before_characters>240?'…':''}</Text></View>
        <View style={[s.value,s.after]}><Text style={s.help}>After · {changes.brief.after_characters} characters</Text><Text selectable style={s.text}>{changes.brief.after_preview||'(empty)'}{changes.brief.after_characters>240?'…':''}</Text></View></View>
    </View>}
    {changes.citations.order_changed&&<View testID="dcp-comparison-citations" style={s.stack}>
      <Text style={s.label}>References · {changes.citations.before_count} → {changes.citations.after_count}</Text>
      {references(changes.citations.removed,'Removed')}{references(changes.citations.added,'Added')}
      {!changes.citations.added.length&&!changes.citations.removed.length&&<Text style={s.help}>The existing references were reordered.</Text>}
      <Text style={s.help}>Citation changes do not restore review approval.</Text>
    </View>}
    {changes.boards.items.map(board=><View key={board.stage} testID={'dcp-comparison-board-'+board.stage} style={s.stack}>
      <Text style={s.label}>Stage {board.stage} · {board.kind} · {board.changed_cells} changed tiles</Text>
      <View style={s.row}>{board.cells.slice(0,expanded.includes(board.stage)?120:8).map(([row,column,before,after])=><Text key={row+':'+column} style={s.tile}>Row {row+1}, column {column+1}: {before===null?'absent':'“'+before+'”'} → {after===null?'absent':'“'+after+'”'}</Text>)}</View>
      {board.changed_cells>8&&<Pressable accessibilityRole="button" accessibilityLabel={(expanded.includes(board.stage)?'Show fewer':'Show all')+' tile changes for stage '+board.stage}
        style={s.button} onPress={()=>setExpanded(current=>current.includes(board.stage)?current.filter(stage=>stage!==board.stage):[...current,board.stage])}>
        <Text style={s.text}>{expanded.includes(board.stage)?'Show fewer tile changes':'Show all '+board.changed_cells+' tile changes'}</Text></Pressable>}
    </View>)}
  </View>;
}
const s=StyleSheet.create({panel:{gap:12,padding:12,borderRadius:12,borderWidth:1,borderColor:'#6a9990',backgroundColor:'#102b28'},
  title:{color:'#e3f8ed',fontSize:16,fontWeight:'700',flexShrink:1},label:{color:'#d4eee2',fontSize:13,fontWeight:'700',textTransform:'capitalize'},
  text:{color:'#e1f2e9',fontSize:13,lineHeight:20},help:{color:'#b4d1c5',fontSize:12,lineHeight:19,flexShrink:1},stack:{gap:7},
  row:{flexDirection:'row',flexWrap:'wrap',gap:8,alignItems:'flex-start'},field:{gap:5,paddingVertical:6},
  value:{padding:9,borderRadius:8,flexGrow:1,flexBasis:230,color:'#e1f2e9',fontSize:13,lineHeight:20},
  before:{backgroundColor:'#352728'},after:{backgroundColor:'#193c31'},reference:{paddingLeft:8,borderLeftWidth:2,borderLeftColor:'#517e6d'},
  tile:{color:'#d3e9df',fontSize:12,lineHeight:19,padding:5,backgroundColor:'#1b3c35',borderRadius:6},
  button:{alignSelf:'flex-start',paddingHorizontal:10,paddingVertical:7,borderRadius:8,borderWidth:1,borderColor:'#688b7f',backgroundColor:'#254b40'}});
