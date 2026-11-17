import React,{useEffect,useRef,useState} from 'react';
import {useIsFocused} from '@react-navigation/native';
import type {AtelierPrototypeProps} from './AtelierPrototype';
import {parsePeakReceipt,verifyFile,MAX_MODEL_BYTES,PEAK_MODEL_BYTES,FAMILIES,type Catalogue,type Family} from './atelierAsset';
import {flightIntent} from './atelierDirector';
import {acquireAtelierLease,type AtelierLease} from './atelierLease';
import type {AtelierStage,AtelierCamera,AtelierQuality} from './atelierStage.web';
import type {PlaybackStats} from './atelierPlaybackMeter';
type Selection={model:File|null;receipt:File|null};
const initial:Selection={model:null,receipt:null};
export default function AtelierPrototype({state,reducedMotion,onOpenChange}:AtelierPrototypeProps) {
  const focused=useIsFocused();
  const [open,setOpen]=useState(false);
  const notifyOpen=useRef(onOpenChange);notifyOpen.current=onOpenChange;
  useEffect(()=>{notifyOpen.current?.(open);return()=>notifyOpen.current?.(false);},[open]);
  const [selection,setSelection]=useState<Selection>(initial);
  const [status,setStatus]=useState('Original model not loaded');
  const [busy,setBusy]=useState(false);
  const [catalogue,setCatalogue]=useState<Catalogue|null>(null);
  const [family,setFamily]=useState<Family>('ground');
  const [clip,setClip]=useState('');
  const [manual,setManual]=useState(false);
  const [camera,setCamera]=useState<AtelierCamera>('perspective');
  const [quality,setQuality]=useState<AtelierQuality>('balanced');
  const [pose,setPose]=useState(0);
  const [stats,setStats]=useState<PlaybackStats|null>(null);
  const captureUrl=useRef<string|null>(null);
  const [snapshot,setSnapshot]=useState<string|null>(null);
  const captureEpoch=useRef(0);
  const revokeCapture=()=>{captureEpoch.current++;if(captureUrl.current){URL.revokeObjectURL(captureUrl.current);captureUrl.current=null;}};
  const canvas=useRef<HTMLCanvasElement>(null);
  const stage=useRef<AtelierStage|null>(null);
  const control=useRef<AbortController|null>(null);
  const resident=useRef<AtelierLease|null>(null);
  const intent=useRef({airborne:flightIntent(state),reduced:reducedMotion});
  intent.current={airborne:flightIntent(state),reduced:reducedMotion};
  const stop=()=>{
    control.current?.abort();control.current=null;
    try{stage.current?.dispose();}finally{stage.current=null;resident.current?.release();resident.current=null;}
    revokeCapture();setSnapshot(null);setPose(0);setStats(null);
    setCatalogue(null);setManual(false);setFamily('ground');setClip('');setCamera('perspective');setQuality('balanced');
  };
  useEffect(()=>()=>{revokeCapture();control.current?.abort();try{stage.current?.dispose();}finally{stage.current=null;resident.current?.release();resident.current=null;}},[]);
  useEffect(()=>{
    if(!focused){stop();setOpen(false);setSelection(initial);setBusy(false);setStatus('Original model not loaded');}
  },[focused]);
  useEffect(()=>{stage.current?.setIntent(intent.current.airborne,intent.current.reduced);},[state.phase,state.wings,reducedMotion]);
  useEffect(()=>{if(!catalogue||!focused||!open)return;const timer=setInterval(()=>{if(!document.hidden&&stage.current)setStats(stage.current.diagnostics());},1000);return()=>clearInterval(timer);},[catalogue,focused,open]);
  const capture=async()=>{const mounted=stage.current;if(!mounted)return;revokeCapture();setSnapshot(null);const epoch=captureEpoch.current;try{const blob=await mounted.snapshot();if(captureEpoch.current!==epoch||stage.current!==mounted)return;const url=URL.createObjectURL(blob);captureUrl.current=url;setSnapshot(url);}catch(error){if(captureEpoch.current===epoch)setStatus(error instanceof Error?error.message:'Capture unavailable');}};
  const change=(patch:Partial<Selection>)=>{
    stop();setBusy(false);setStatus('Original model not loaded');setSelection(old=>({...old,...patch}));
  };
  const load=async()=>{
    if(!canvas.current||!selection.model||!selection.receipt||control.current)return;
    const abort=new AbortController();control.current=abort;setBusy(true);setStatus('Verifying local model and clip catalogue…');
    let lease:AtelierLease|undefined;
    try{
      lease=acquireAtelierLease((navigator as Navigator & {deviceMemory?:number}).deviceMemory);
      if(selection.receipt.size>256*1024||selection.model.size>MAX_MODEL_BYTES)throw new Error('Local asset exceeds prototype limits');
      const receipt=parsePeakReceipt(JSON.parse(await selection.receipt.text()));
      if(abort.signal.aborted)return;
      const bytes=await verifyFile(selection.model,receipt,abort.signal);
      if(abort.signal.aborted||!canvas.current)return;
      const {createAtelierStage}=await import('./atelierStage.web');
      if(abort.signal.aborted||!canvas.current)return;
      const mounted=await createAtelierStage(canvas.current,bytes,receipt,abort.signal,message=>{if(!abort.signal.aborted)setStatus(message);});
      if(abort.signal.aborted){mounted.dispose();return;}
      try{mounted.setIntent(intent.current.airborne,intent.current.reduced);}catch(error){mounted.dispose();throw error;}
      stage.current=mounted;resident.current=lease;lease=undefined;
      setCatalogue(receipt.families);setClip(receipt.families.ground[0]);
    }catch(error){
      if(!abort.signal.aborted)setStatus(error instanceof Error?error.message:'Local 3D prototype unavailable');
    }finally{
      lease?.release();
      if(control.current===abort){control.current=null;setBusy(false);}
    }
  };
  const close=()=>{stop();setOpen(false);setSelection(initial);setBusy(false);setStatus('Original model not loaded');};
  return <div style={{color:'#e2e8f0',marginTop:12,padding:10,border:'1px solid #334155',borderRadius:8}}>
    <button type="button" onClick={()=>open?close():setOpen(true)}>{open?'Close 3D prototype':'Open original 3D prototype (local files)'}</button>
    {open&&<div>
      <p>Use only the original Atelier Fold GLB, admission receipt matching the existing repository pin (463,149,740 bytes). Files remain in this browser session; the ordinary companion remains available. This is not Unreal or physical RTX qualification.</p>
      <label style={{display:'block'}}>Original model <input type="file" accept=".glb" onChange={e=>change({model:e.target.files?.[0]??null})}/></label>
      <label style={{display:'block'}}>Admission receipt <input type="file" accept=".json,application/json" onChange={e=>change({receipt:e.target.files?.[0]??null})}/></label>
      <button type="button" disabled={busy||!selection.model||!selection.receipt||selection.model.size!==PEAK_MODEL_BYTES} onClick={()=>{stop();void load();}}>Verify and render</button>
      {catalogue&&<fieldset style={{border:'1px solid #475569',padding:8,marginTop:8}}>
        <legend>Original 3D inspection laboratory</legend>
        <p>Manual clips are visual previews only and never assert crawler activity. Detail mode retains the full admitted mesh; economy changes raster cost, not the model.</p>
        <label style={{display:'block'}}>Camera <select value={camera} onChange={e=>{const value=e.target.value as AtelierCamera;setCamera(value);stage.current?.setCamera(value);}}>
          <option value="perspective">Three-quarter</option><option value="side">Side / takeoff</option><option value="overhead">Overhead wingspan</option><option value="front">Front anatomy</option>
        </select></label>
        <label style={{display:'block'}}>Render quality <select value={quality} onChange={e=>{const value=e.target.value as AtelierQuality;setQuality(value);stage.current?.setQuality(value);}}>
          <option value="detail">Detail (up to 2× device pixel ratio)</option><option value="balanced">Balanced</option><option value="economy">Economy, no real-time shadows</option>
        </select></label>
        <label style={{display:'block'}}>Exact animation family <select value={family} onChange={e=>{const value=e.target.value as Family;if(FAMILIES.includes(value)){setFamily(value);setClip(catalogue[value][0]);}}}>
          {FAMILIES.map(name=><option key={name} value={name}>{name} ({catalogue[name].length})</option>)}
        </select></label>
        <label style={{display:'block'}}>Exported clip <select value={clip} onChange={e=>setClip(e.target.value)}>
          {catalogue[family].map(name=><option key={name} value={name}>{name}</option>)}
        </select></label>
        <button type="button" disabled={!catalogue[family].includes(clip)} onClick={()=>{if(stage.current){stage.current.inspect(family,clip);setManual(true);setPose(0);revokeCapture();setSnapshot(null);}}}>Inspect selected clip</button>
        <button type="button" disabled={!manual} onClick={()=>{stage.current?.followEvents();setManual(false);revokeCapture();setSnapshot(null);}}>Return to recorded crawler events</button>
        {manual&&<div><label style={{display:'block'}}>Inspect exact clip position ({Math.round(pose*100)}%) <input aria-label="Inspect clip position" type="range" min={0} max={1} step={0.001} value={pose} onChange={e=>{const value=Number(e.target.value);setPose(value);stage.current?.seek(value);}}/></label><button type="button" disabled={reducedMotion} onClick={()=>stage.current?.playManual()}>Resume clip playback</button><button type="button" onClick={()=>void capture()}>Capture current pose PNG</button>{snapshot&&<a href={snapshot} download="emerald-original-pose.png">Save captured viewport PNG</a>}</div>}
        {stats&&<p>Measured browser render intervals: {stats.samples} samples; mean {stats.meanIntervalMs?.toFixed(2)??'—'} ms; p95 {stats.p95IntervalMs?.toFixed(2)??'—'} ms; render submission {stats.meanRenderSubmissionMs?.toFixed(2)??'—'} ms. Not measured GPU present time or RTX evidence.</p>}
        {reducedMotion&&<p>Reduced motion is active: automatic playback is frozen; explicit pose inspection remains available.</p>}
      </fieldset>}
      <p role="status" aria-live="polite">{status}</p>
      <canvas ref={canvas} aria-label="Decorative local 3D dragon viewport" style={{display:'block',width:'100%',height:340,background:'#101c26'}}/>
    </div>}
  </div>;
}
