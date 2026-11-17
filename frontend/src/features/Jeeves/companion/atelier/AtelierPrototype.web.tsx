import React,{useEffect,useRef,useState} from 'react';
import {useIsFocused} from '@react-navigation/native';
import type {AtelierPrototypeProps} from './AtelierPrototype';
import {parseReceipt,verifyFile,MAX_MODEL_BYTES} from './atelierAsset';
import {flightIntent} from './atelierDirector';
import type {AtelierStage} from './atelierStage.web';
type Selection={model:File|null;receipt:File|null;digest:string};
const initial:Selection={model:null,receipt:null,digest:''};
export default function AtelierPrototype({state,reducedMotion}:AtelierPrototypeProps) {
  const focused=useIsFocused();
  const [open,setOpen]=useState(false);
  const [selection,setSelection]=useState<Selection>(initial);
  const [status,setStatus]=useState('Original model not loaded');
  const [busy,setBusy]=useState(false);
  const canvas=useRef<HTMLCanvasElement>(null);
  const stage=useRef<AtelierStage|null>(null);
  const control=useRef<AbortController|null>(null);
  const intent=useRef({airborne:flightIntent(state),reduced:reducedMotion});
  intent.current={airborne:flightIntent(state),reduced:reducedMotion};
  const stop=()=>{
    control.current?.abort();control.current=null;
    stage.current?.dispose();stage.current=null;
  };
  useEffect(()=>()=>{control.current?.abort();stage.current?.dispose();},[]);
  useEffect(()=>{
    if(!focused){stop();setOpen(false);setSelection(initial);setBusy(false);setStatus('Original model not loaded');}
  },[focused]);
  useEffect(()=>{stage.current?.setIntent(intent.current.airborne,intent.current.reduced);},[state.phase,state.wings,reducedMotion]);
  const change=(patch:Partial<Selection>)=>{
    stop();setBusy(false);setStatus('Original model not loaded');setSelection(old=>({...old,...patch}));
  };
  const load=async()=>{
    if(!canvas.current||!selection.model||!selection.receipt||control.current)return;
    const abort=new AbortController();control.current=abort;setBusy(true);setStatus('Verifying local model and clip catalogue…');
    try{
      if(selection.receipt.size>256*1024||selection.model.size>MAX_MODEL_BYTES)throw new Error('Local asset exceeds prototype limits');
      const receipt=parseReceipt(JSON.parse(await selection.receipt.text()),selection.digest.trim());
      const bytes=await verifyFile(selection.model,receipt);
      if(abort.signal.aborted||!canvas.current)return;
      const {createAtelierStage}=await import('./atelierStage.web');
      if(abort.signal.aborted||!canvas.current)return;
      const mounted=await createAtelierStage(canvas.current,bytes,receipt,abort.signal,message=>{if(!abort.signal.aborted)setStatus(message);});
      if(abort.signal.aborted){mounted.dispose();return;}
      stage.current=mounted;mounted.setIntent(intent.current.airborne,intent.current.reduced);
    }catch(error){
      if(!abort.signal.aborted)setStatus(error instanceof Error?error.message:'Local 3D prototype unavailable');
    }finally{
      if(control.current===abort){control.current=null;setBusy(false);}
    }
  };
  const close=()=>{stop();setOpen(false);setSelection(initial);setBusy(false);setStatus('Original model not loaded');};
  return <div style={{color:'#e2e8f0',marginTop:12,padding:10,border:'1px solid #334155',borderRadius:8}}>
    <button type="button" onClick={()=>open?close():setOpen(true)}>{open?'Close 3D prototype':'Open original 3D prototype (local files)'}</button>
    {open&&<div>
      <p>Use only the original Atelier Fold GLB, admission receipt and independently trusted digest. Files remain in this browser session; the ordinary companion remains available. This is not Unreal or physical RTX qualification.</p>
      <label style={{display:'block'}}>Original model <input type="file" accept=".glb" onChange={e=>change({model:e.target.files?.[0]??null})}/></label>
      <label style={{display:'block'}}>Admission receipt <input type="file" accept=".json,application/json" onChange={e=>change({receipt:e.target.files?.[0]??null})}/></label>
      <label style={{display:'block'}}>Trusted SHA-256 <input type="text" autoComplete="off" spellCheck={false} maxLength={64} value={selection.digest} onChange={e=>change({digest:e.target.value})}/></label>
      <button type="button" disabled={busy||!selection.model||!selection.receipt||!/^[0-9a-f]{64}$/.test(selection.digest)} onClick={()=>{stop();void load();}}>Verify and render</button>
      <p role="status" aria-live="polite">{status}</p>
      <canvas ref={canvas} aria-label="Decorative local 3D dragon viewport" style={{display:'block',width:'100%',height:340,background:'#101c26'}}/>
    </div>}
  </div>;
}
