import type { AtelierReceipt, Family } from './atelierAsset';
import {PlaybackMeter,seekTime,type PlaybackStats} from './atelierPlaybackMeter';
import { completeStep, inspectClip, resetLive, setIntent, startDirector, type Director } from './atelierDirector';

type ThreeModule = typeof import('three');
type Loader = typeof import('three/addons/loaders/GLTFLoader.js');
type Gltf = Parameters<Parameters<InstanceType<Loader['GLTFLoader']>['parse']>[2]>[0];
export type AtelierCamera='perspective'|'side'|'overhead'|'front';
export type AtelierQuality='detail'|'balanced'|'economy';
export interface AtelierStage {
  setIntent: (airborne:boolean,reduced:boolean) => void;
  inspect:(family:Family,clip:string)=>void;
  inspectGrowth:()=>void;
  followEvents:()=>void;
  setCamera:(camera:AtelierCamera)=>void;
  setQuality:(quality:AtelierQuality)=>void;
  seek:(fraction:number)=>void;
  playManual:()=>void;
  snapshot:()=>Promise<Blob>;
  diagnostics:()=>PlaybackStats;
  dispose: () => void;
}
function disposeModel(gltf:Gltf) {
  const resources = new Set<{dispose:()=>void}>();
  const sources = new Set<{close:()=>void}>();
  for (const scene of gltf.scenes) {
    scene.traverse((object: Record<string, any>)=>{
      if (object.geometry?.dispose) resources.add(object.geometry);
      if (object.skeleton?.dispose) resources.add(object.skeleton);
      const materials = Array.isArray(object.material)?object.material:[object.material];
      for(const material of materials) {
        if (!material?.dispose) continue;
        resources.add(material);
        for(const value of Object.values(material)) {
          const candidate=value as {isTexture?:boolean;dispose?:()=>void;source?:{data?:{close?:()=>void}}}|null;
          if (candidate?.isTexture && candidate.dispose) {
            resources.add(candidate as {dispose:()=>void});
            const data=candidate.source?.data;
            if (data?.close) sources.add(data as {close:()=>void});
          }
        }
      }
    });
  }
  for(const resource of resources){try{resource.dispose();}catch{}}
  for(const source of sources){try{source.close();}catch{}}
}
async function loadEmbedded(Three:ThreeModule,loader:Loader,bytes:ArrayBuffer):Promise<Gltf> {
  const manager=new Three.LoadingManager();
  manager.setURLModifier((uri:string)=>{
    if (!uri.startsWith('blob:')) throw new Error('External glTF load blocked');
    return uri;
  });
  return new Promise((resolve,reject)=>new loader.GLTFLoader(manager).parse(bytes,'',resolve,reject));
}
/** Local file bytes have already been hash-verified. No assets or telemetry leave this surface. */
export async function createAtelierStage(canvas:HTMLCanvasElement,bytes:ArrayBuffer,receipt:AtelierReceipt,signal:AbortSignal,status:(message:string)=>void):Promise<AtelierStage> {
  const [Three,loader]=await Promise.all([import('three'),import('three/addons/loaders/GLTFLoader.js')]);
  if(signal.aborted) throw new Error('Prototype closed');
  const gltf=await loadEmbedded(Three,loader,bytes);
  if(signal.aborted){disposeModel(gltf);throw new Error('Prototype closed');}
  let renderer:InstanceType<ThreeModule['WebGLRenderer']>|undefined;
  let teardown: (()=>void)|undefined;
  try {
    const actual = new Map<string, any>();
    for(const clip of gltf.animations) {
      if(typeof clip.name!=='string'||!Number.isFinite(clip.duration)||clip.duration<=0||actual.has(clip.name)) throw new Error('Invalid decoded animation catalogue');
      actual.set(clip.name,clip);
    }
    if(actual.size!==receipt.clips.length||receipt.clips.some(name=>!actual.has(name))) throw new Error('Decoded clips differ from custody receipt');
    const scene=new Three.Scene();
    scene.background=new Three.Color(0x101c26);
    const root=new Three.Group();
    const bounds=new Three.Box3().setFromObject(gltf.scene);
    const center=bounds.getCenter(new Three.Vector3()), size=bounds.getSize(new Three.Vector3());
    const extent=Math.max(size.x,size.y,size.z);
    if(!Number.isFinite(extent)||extent<=0||![center.x,center.y,center.z].every(Number.isFinite)) throw new Error('Invalid model bounds');
    root.add(gltf.scene);
    root.scale.setScalar(2.6/extent);
    root.position.copy(center).multiplyScalar(-2.6/extent);
    scene.add(root);
    const floor=new Three.Mesh(new Three.CircleGeometry(4,80),new Three.MeshStandardMaterial({color:0x162c29,roughness:.92}));
    floor.rotation.x=-Math.PI/2;floor.position.y=-1.42;floor.receiveShadow=true;scene.add(floor);
    gltf.scene.traverse((object:Record<string,any>)=>{if(object.isMesh){object.castShadow=true;object.receiveShadow=true;}});
    const ambient=new Three.HemisphereLight(0xd4ffe9,0x30364e,1.75);scene.add(ambient);
    const key=new Three.DirectionalLight(0xffead3,3.1);key.position.set(3,5,4);key.castShadow=true;key.shadow.mapSize.set(1024,1024);scene.add(key);
    const rim=new Three.DirectionalLight(0x9dfde9,2.2);rim.position.set(-4,2,-3);scene.add(rim);
    const camera=new Three.PerspectiveCamera(38,1,.02,60);camera.position.set(3.9,2.55,4.4);camera.lookAt(0,0,0);
    renderer=new Three.WebGLRenderer({canvas,antialias:true,alpha:false,powerPreference:'high-performance'});
    const graphics=renderer;
    graphics.outputColorSpace=Three.SRGBColorSpace;
    graphics.toneMapping=Three.ACESFilmicToneMapping;
    graphics.shadowMap.enabled=true;
    graphics.shadowMap.type=Three.PCFSoftShadowMap;
    const mixer=new Three.AnimationMixer(gltf.scene);
    let director:Director=startDirector(receipt.families);
    let manual=false;
    let manualPaused=false;
    const meter=new PlaybackMeter();
    let desired={airborne:false,reduced:false};
    let quality:AtelierQuality='balanced';
    let action:any=null;
    let retired:{action:any;deadline:number}[]=[];
    let disposed=false,failed=false,frame=0,last=0,elapsed=0;
    const resize=()=>{
      if(disposed||failed)return;
      const width=Math.max(1,Math.min(1200,canvas.clientWidth||640)),height=Math.max(1,Math.min(720,canvas.clientHeight||360));
      graphics.setPixelRatio(Math.min(quality==='detail'?2:quality==='balanced'?1.5:1,window.devicePixelRatio||1));
      graphics.setSize(width,height,false);camera.aspect=width/height;camera.updateProjectionMatrix();
    };
    const draw=()=>{if(!disposed&&!failed)graphics.render(scene,camera);};
    // A driver/render failure must stop the loop instead of silently dropping frames.
    const halt=(reason:string)=>{if(disposed||failed)return;failed=true;if(frame)cancelAnimationFrame(frame);frame=0;last=0;status(reason);};
    const apply=(next:Director)=>{
      const changed=!action||director.step.serial!==next.step.serial;
      director=next;
      if(changed){
        const previous=action;
        action=mixer.clipAction(actual.get(next.step.clip));
        // A catalogue clip may recur; never stop its reused live action.
        retired=retired.filter(entry=>entry.action!==action);
        action.reset().setEffectiveWeight(1).setEffectiveTimeScale(1);
        action.setLoop(next.step.repeat?Three.LoopRepeat:Three.LoopOnce,next.step.repeat?Infinity:1);
        action.clampWhenFinished=!next.step.repeat;
        action.play();
        if(previous&&previous!==action){
          if(next.reduced)previous.stop();
          else {action.crossFadeFrom(previous,.22,false);retired.push({action:previous,deadline:elapsed+.24});}
        }
      }
      if(next.reduced||manualPaused){for(const entry of retired)entry.action.stop();retired=[];action.paused=true;mixer.update(0);}
      else action.paused=false;
      status((manual?'Manual clip inspection (not crawl telemetry)':'Recorded-event 3D presentation')+' · '+next.step.family+' · '+next.step.clip);
      draw();
    };
    const onFinished=(event:{action:unknown})=>{
      if(!disposed&&!failed&&!manual&&event.action===action)apply(completeStep(director,receipt.families,director.step.serial));
    };
    mixer.addEventListener('finished',onFinished);
    const tick=(now:number)=>{
      frame=0;
      if(disposed||failed||document.hidden||director.reduced||manualPaused)return;
      if(!last)last=now;
      try{
      if(now>last){
        const dt=Math.min(.05,(now-last)/1000);last=now;elapsed+=dt;
        mixer.update(dt);
        retired=retired.filter(entry=>{if(entry.deadline>elapsed)return true;if(entry.action!==action)entry.action.stop();return false;});
        const start=performance.now();draw();meter.observe(now,performance.now()-start);
      }
      frame=requestAnimationFrame(tick);
      }catch{halt('Full model playback failed. Close the inspector to release resources.');}
    };
    const stop=()=>{if(frame)cancelAnimationFrame(frame);frame=0;last=0;meter.reset();};
    const resume=()=>{if(!disposed&&!failed&&!document.hidden&&!director.reduced&&!manualPaused&&!frame)frame=requestAnimationFrame(tick);};
    const visibility=()=>{stop();if(!document.hidden){try{draw();resume();}catch{halt('Viewport resume failed. Close the inspector to release resources.');}}};
    const lost=(event:Event)=>{event.preventDefault();halt('WebGL context lost. Close and reload the verified model.');};
    const onResize=()=>{try{resize();draw();}catch{halt('Viewport resize failed. Close the inspector to release resources.');}};
    const observer=typeof ResizeObserver==='undefined'?null:new ResizeObserver(onResize);
    teardown=()=>{
      if(disposed)return;disposed=true;stop();observer?.disconnect();window.removeEventListener('resize',onResize);
      document.removeEventListener('visibilitychange',visibility);canvas.removeEventListener('webglcontextlost',lost);
      mixer.removeEventListener('finished',onFinished);mixer.stopAllAction();mixer.uncacheRoot(gltf.scene);
      // Preserve cleanup through failures in individual Three resources.
      for(const release of [()=>floor.geometry.dispose(),()=>floor.material.dispose(),()=>key.shadow.dispose?.(),()=>disposeModel(gltf),()=>graphics.dispose()]){try{release();}catch{}}
    };
    observer?.observe(canvas);window.addEventListener('resize',onResize);document.addEventListener('visibilitychange',visibility);
    canvas.addEventListener('webglcontextlost',lost);
    resize();
    apply(director);
    // The caller applies reduced-motion and actual event intent before starting the clock.
    return {
      setIntent:(airborne,reduced)=>{
        if(disposed||failed)return;
        desired={airborne,reduced};
        if(manual)apply({...director,reduced});
        else apply(setIntent(director,receipt.families,airborne,reduced));
        if(reduced||manualPaused)stop();else resume();
      },
      inspect:(family,clip)=>{
        if(disposed||failed)return;
        const next=inspectClip(director,receipt.families,family,clip,desired.reduced);
        if(director.step.clip===receipt.growthClip){mixer.stopAllAction();retired=[];action=null;}
        manual=true;manualPaused=false;meter.reset();apply(next);resume();
      },
      inspectGrowth:()=>{
        if(disposed||failed||!receipt.growthClip)return;
        // Growth is an explicitly selected visual study, never selected by the live director.
        const serial=director.cursor>=Number.MAX_SAFE_INTEGER-1?0:director.cursor+1;
        manual=true;manualPaused=true;meter.reset();mixer.stopAllAction();retired=[];action=null;
        apply({...director,cursor:serial,airborne:false,reduced:desired.reduced,step:{family:'ground',clip:receipt.growthClip,repeat:false,serial}});stop();
      },
      followEvents:()=>{
        if(disposed||failed||!manual)return;
        if(director.step.clip===receipt.growthClip){mixer.stopAllAction();retired=[];action=null;}
        manual=false;manualPaused=false;meter.reset();apply(resetLive(director,receipt.families,desired.airborne,desired.reduced));resume();
      },
      setCamera:(preset)=>{
        if(disposed||failed)return;
        const viewpoints:Record<AtelierCamera,readonly [number,number,number]>={perspective:[3.9,2.55,4.4],side:[6,1.15,0],overhead:[0,6.6,.02],front:[0,1.4,6]};
        const coordinates=viewpoints[preset];if(!coordinates)return;
        camera.position.set(...coordinates);camera.lookAt(0,0,0);draw();
      },
      setQuality:(preset)=>{
        if(disposed||failed||!['detail','balanced','economy'].includes(preset)||preset===quality)return;
        quality=preset;graphics.shadowMap.enabled=quality!=='economy';
        key.castShadow=quality!=='economy';
        const size=quality==='detail'?2048:1024;
        if(key.shadow.mapSize.x!==size){
          key.shadow.map?.dispose();key.shadow.map=null;key.shadow.mapSize.set(size,size);
        }
        // Shadow layout and sampling changed, so rebuild material programs.
        scene.traverse((object:Record<string,any>)=>{
          const materials=Array.isArray(object.material)?object.material:[object.material];
          for(const material of materials)if(material)material.needsUpdate=true;
        });
        resize();draw();
      },
      seek:(fraction)=>{
        if(disposed||failed||!manual||!action)return;
        const duration=actual.get(director.step.clip).duration;
        const time=seekTime(duration,fraction);
        manualPaused=true;stop();
        for(const entry of retired)entry.action.stop();retired=[];
        action.stopFading();action.setEffectiveWeight(1);action.paused=false;action.time=time;
        mixer.update(0);action.paused=true;draw();
        status('Manual pose inspection · '+director.step.clip+' · '+time.toFixed(3)+' s');
      },
      playManual:()=>{
        if(disposed||failed||!manual||!action||desired.reduced)return;
        manualPaused=false;action.paused=false;meter.reset();resume();
      },
      snapshot:()=>{
        if(disposed||failed||!manual)return Promise.reject(new Error('Select a manual original-model clip before capturing'));
        // Capture synchronously after a fresh render; do not keep the framebuffer resident.
        draw();
        return new Promise<Blob>((resolve,reject)=>canvas.toBlob(blob=>{
          if(disposed||failed||!blob){reject(new Error('Viewport capture unavailable'));return;}
          resolve(blob);
        },'image/png'));
      },
      diagnostics:()=>meter.read(),
      dispose:teardown,
    };
  } catch(error) {
    if(teardown)teardown();else {try{renderer?.dispose();}finally{disposeModel(gltf);}}
    throw error;
  }
}
