import pin from './emeraldAssetPin.json';
import type { EmeraldCue, EmeraldProjection } from './emeraldCapture';

interface AssetEntry {path:string; bytes:number; sha256:string}
interface Manifest {schema:number; assetSet:string; scripts:string[]; files:AssetEntry[]}
interface Pose {
  x:number; y:number; width:number; heading:number; view:string; presentation?:string;
  flip?:boolean; frame:number; channels?:Record<string,number>; smokeSerial:number;
  hx:number; hy:number; bank:number; altitude:number; flapMix:number;
  shadow:{x:number;y:number;scale:number;opacity:number};
}
interface Director {start(state:string):void;setReduced(reduced:boolean):void;accept(phase:string,seq:number,key:string):boolean;
  update(dt:number,rect:{x:number;y:number;w:number;h:number},w:number,h:number):Pose | null}
interface Surface {update(dt:number,pose:Pose):boolean;paint(ctx:CanvasRenderingContext2D,x:number,y:number,w:number,angle:number,shadow?:boolean,opacity?:number):void;dispose():void}
interface Ground {update(channels:Record<string,number>,full?:boolean):boolean;paint:Surface['paint']}
interface Vendor {
  EmeraldLiveRaptor?:{Director:new (opts:{seed:number;skipIntro:boolean;reduced:boolean})=>Director};
  EmeraldLeatherRenderer?:{Renderer:new (url:string)=>Surface};
  EmeraldGround?:{Renderer:new (url:string,wasm:string)=>Ground};
  EmeraldRasterBase64?:string;
}
const ROOT='/emerald/v1/';
const SCRIPTS=['choreography.js','repertoire.js','raptor_director.js','anatomical_mesh.js','leather.js','leather_renderer.js','ground_surface.js'];
const IMAGES=['ground.png','dorsal_master.png','side.webp','side_shadow.png','launch.webp','launch_shadow.png','landing.webp','landing_shadow.png'];
const SHA=/^[a-f0-9]{64}$/;
const hex=(bytes:ArrayBuffer)=>Array.from(new Uint8Array(bytes),x=>x.toString(16).padStart(2,'0')).join('');
async function read(path:string,limit:number,signal?:AbortSignal):Promise<ArrayBuffer>{
  const response=await fetch(ROOT+path,{signal,redirect:'error',credentials:'omit',cache:'force-cache'});
  if(!response.ok||!response.body)throw Error('Emerald asset unavailable');
  const reader=response.body.getReader();let size=0;const pieces:Uint8Array[]=[];
  try {
    while(true){const chunk=await reader.read();if(chunk.done)break;size+=chunk.value.byteLength;
      if(size>limit)throw Error('Emerald asset exceeds size limit');pieces.push(chunk.value);}
  } finally {await reader.cancel().catch(()=>{});reader.releaseLock();}
  const output=new Uint8Array(size);let offset=0;for(const p of pieces){output.set(p,offset);offset+=p.byteLength;}return output.buffer;
}
async function manifest():Promise<Manifest>{
  if(!globalThis.crypto?.subtle)throw Error('Secure asset verification unavailable');
  const data=await read('manifest.integration.json',65536);
  if(hex(await crypto.subtle.digest('SHA-256',data))!==pin.web.manifestSha256)throw Error('Emerald manifest mismatch');
  const m=JSON.parse(new TextDecoder().decode(data)) as Manifest;
  if(m.schema!==1||m.assetSet!==pin.assetSet||m.files.length!==pin.web.entries||
    JSON.stringify(m.scripts)!==JSON.stringify(SCRIPTS))throw Error('Emerald manifest contract mismatch');
  const seen=new Set<string>();
  for(const f of m.files){
    if(!/^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$/.test(f.path)||seen.has(f.path)||!SHA.test(f.sha256)||!Number.isSafeInteger(f.bytes)||f.bytes<1||f.bytes>64*1024*1024)throw Error('Invalid Emerald asset entry');
    seen.add(f.path);
  }
  if(![...SCRIPTS,...IMAGES].every(n=>seen.has(n)))throw Error('Required asset missing');
  return m;
}
let vendorPromise:Promise<Manifest>|undefined;
function vendor():Promise<Manifest>{
  if(vendorPromise)return vendorPromise;
  vendorPromise=(async()=>{
    const m=await manifest();
    // Executable vendor code is only loaded by fixed same-origin path with integrity pinned by the source manifest.
    for(const name of SCRIPTS){
      const entry=m.files.find(f=>f.path===name)!;
      const sri=btoa(String.fromCharCode(...Uint8Array.from(entry.sha256.match(/../g)!,x=>parseInt(x,16))));
      await new Promise<void>((resolve,reject)=>{
        const script=document.createElement('script');script.src=ROOT+name;script.integrity='sha256-'+sri;script.crossOrigin='anonymous';script.async=false;
        script.onload=()=>{script.remove();resolve();};script.onerror=()=>{script.remove();reject(Error('Emerald script integrity or policy failure'));};
        document.head.appendChild(script);
      });
    }
    const w=globalThis as unknown as Vendor;
    if(!w.EmeraldLiveRaptor||!w.EmeraldLeatherRenderer||!w.EmeraldGround||!w.EmeraldRasterBase64)throw Error('Emerald renderer missing');
    return m;
  })().catch(err=>{vendorPromise=undefined;throw err;});
  return vendorPromise;
}
async function image(entry:AssetEntry,signal:AbortSignal):Promise<{url:string;image:HTMLImageElement}>{
  const bytes=await read(entry.path,entry.bytes,signal);
  if(bytes.byteLength!==entry.bytes||hex(await crypto.subtle.digest('SHA-256',bytes))!==entry.sha256)throw Error('Emerald image integrity failure');
  const url=URL.createObjectURL(new Blob([bytes],{type:entry.path.endsWith('.webp')?'image/webp':'image/png'}));
  try {const im=new Image();im.src=url;await im.decode();if(signal.aborted)throw Error('aborted');return {url,image:im};}
  catch(e){URL.revokeObjectURL(url);throw e;}
}
export interface MountedEmerald {setProjection(value:EmeraldProjection):void;setReduced(value:boolean):void;dispose():void}
export async function mountEmerald(canvas:HTMLCanvasElement,signal:AbortSignal,onFailure:(error:Error)=>void):Promise<MountedEmerald>{
  const m=await vendor();const images=new Map<string,{url:string;image:HTMLImageElement}>();
  let disposed=false;let surface:Surface|undefined;let raf=0;
  try {
    for(const name of IMAGES){if(signal.aborted)throw Error('aborted');images.set(name,await image(m.files.find(f=>f.path===name)!,signal));}
    const w=globalThis as unknown as Required<Vendor>;
    const ctx=canvas.getContext('2d',{alpha:true});if(!ctx)throw Error('Canvas unavailable');
    surface=new w.EmeraldLeatherRenderer.Renderer(images.get('dorsal_master.png')!.url);
    const ground=new w.EmeraldGround.Renderer(images.get('ground.png')!.url,w.EmeraldRasterBase64);
    const newDirector=()=>{const value=new w.EmeraldLiveRaptor.Director({seed:0x75ca33,skipIntro:false,reduced});value.start('ground');return value;};
    let reduced=false;let director=newDirector();
    let projection:EmeraldProjection|undefined;let last=0,seen=0,smokeSerial=0;let disconnected=true;
    const smoke:{x:number;y:number;vx:number;vy:number;age:number;radius:number}[]=[];
    let previousCue:EmeraldCue|undefined;
    const atlas=(k:string,frame:number,x:number,y:number,width:number,angle:number,flip:boolean,shadow:boolean,opacity=1)=>{
      const im=images.get(k+(shadow?'_shadow.png':'.webp'))?.image;if(!im)return;
      const sw=shadow?468:936,sh=shadow?246:492,limit=k==='side'?51:30;
      const i=Math.max(0,Math.min(limit,Math.round(frame)));
      const height=width*492/936;ctx.save();ctx.translate(x,y);ctx.rotate(angle);if(flip)ctx.scale(-1,1);ctx.globalAlpha=opacity;
      ctx.drawImage(im,i%6*sw,Math.floor(i/6)*sh,sw,sh,-width/2,-height/2,width,height);ctx.restore();
    };
    const paintStatic=(im:HTMLImageElement,x:number,y:number,width:number,angle:number)=>{
      ctx.save();ctx.translate(x,y);ctx.rotate(angle);const h=width*im.naturalHeight/im.naturalWidth;ctx.drawImage(im,-width/2,-h/2,width,h);ctx.restore();
    };
    const draw=(ms:number)=>{
      if(disposed||signal.aborted)return;raf=requestAnimationFrame(draw);
      if(document.hidden){last=0;return;}
      if(last&&ms-last<30)return;const dt=last?Math.min(.1,(ms-last)/1000):1/30;last=ms;
      try{
        const width=Math.max(1,canvas.clientWidth),height=Math.max(1,canvas.clientHeight);
        const dpr=Math.min(2,window.devicePixelRatio||1),pw=Math.round(width*dpr),ph=Math.round(height*dpr);
        if(canvas.width!==pw||canvas.height!==ph){canvas.width=pw;canvas.height=ph;}
        ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,width,height);
        const live=projection?.availability==='live'||projection?.availability==='inactive'&&projection?.cue?.captured===true;
        const detached=!projection||projection.availability==='stale'||projection.availability==='waiting';
        if(detached&&!disconnected){director=newDirector();smokeSerial=0;smoke.length=0;previousCue=undefined;}
        disconnected=detached;
        const rect={x:width*.25,y:height*.45,w:width*.5,h:height*.28};
        const cue=projection?.cue;
        if(!detached&&cue&&cue.sequence>seen){seen=cue.sequence;
          if(cue.phase==='index'&&!cue.captured)throw Error('Invalid completion cue');
          director.accept(cue.phase,cue.sequence,cue.target);previousCue=cue;
        }
        if(!live&&projection?.availability!=='inactive'){smoke.length=0;previousCue=undefined;}
        director.setReduced(reduced);
        if(projection?.target&&live){
          ctx.save();ctx.strokeStyle=projection.target.captured?'#e6c773':'#55c7ab';ctx.lineWidth=2;ctx.shadowColor=ctx.strokeStyle;ctx.shadowBlur=12;
          ctx.strokeRect(rect.x,rect.y,rect.w,rect.h);ctx.shadowBlur=0;ctx.fillStyle='#ad314d';ctx.translate(rect.x+rect.w/2,rect.y);ctx.rotate(Math.PI/4);ctx.fillRect(-5,-5,10,10);ctx.restore();
        }
        const p=director.update(dt,rect,width,height);
        if(!p)return;
        if(reduced||detached){
          paintStatic(images.get('ground.png')!.image,width/2,height*.60,Math.min(width*.78,height*1.55),0);smoke.length=0;return;
        }
        const shadow=p.shadow;const sx=p.x+shadow.x,sy=p.y+shadow.y;
        const k=p.presentation||p.view;
        if(k==='dorsal'){
          if(!surface!.update(dt,p))throw Error('Emerald surface unavailable');
          surface!.paint(ctx,sx,sy,p.width*shadow.scale,p.heading,true,shadow.opacity);
          surface!.paint(ctx,p.x,p.y,p.width,p.heading);
        }else if(k==='ground'){
          if(ground.update(p.channels||{},true)){ground.paint(ctx,sx,sy,p.width*shadow.scale,0,true,shadow.opacity);ground.paint(ctx,p.x,p.y,p.width,0);}
          else paintStatic(images.get('ground.png')!.image,p.x,p.y,p.width,0);
        }else if(k==='launch'||k==='landing'||k==='side'){
          const i=k==='landing'?30-p.frame:p.frame;
          atlas(k,i,sx,sy,p.width*shadow.scale,p.heading,!!p.flip,true,shadow.opacity);
          atlas(k,i,p.x,p.y,p.width,p.heading,!!p.flip,false);
        }
        if(p.smokeSerial!==smokeSerial){
          smokeSerial=p.smokeSerial;
          if(previousCue?.captured&&live){
            const nx=p.x+p.hx*p.width*.33,ny=p.y+p.hy*p.width*.33;
            for(let i=0;i<9;i++)smoke.push({x:nx,y:ny,vx:p.hx*(10+i*2)+(i-4)*1.6,vy:p.hy*(10+i*2)-7,age:-i*.035,radius:3+i*.5});
          }
        }
        for(let i=smoke.length-1;i>=0;i--){const s=smoke[i];s.age+=dt;if(s.age>1.4){smoke.splice(i,1);continue;}if(s.age<0)continue;s.x+=s.vx*dt;s.y+=s.vy*dt;
          const rad=s.radius+s.age*12;const gradient=ctx.createRadialGradient(s.x,s.y,0,s.x,s.y,rad);gradient.addColorStop(0,'rgba(201,218,211,'+(.45*(1-s.age/1.4))+')');gradient.addColorStop(1,'rgba(201,218,211,0)');ctx.fillStyle=gradient;ctx.fillRect(s.x-rad,s.y-rad,rad*2,rad*2);}
      }catch(err){dispose();onFailure(err instanceof Error?err:Error('Emerald rendering failed'));}
    };
    function dispose(){if(disposed)return;disposed=true;cancelAnimationFrame(raf);surface?.dispose();for(const item of images.values())URL.revokeObjectURL(item.url);images.clear();}
    if(signal.aborted){dispose();throw Error('aborted');}
    raf=requestAnimationFrame(draw);
    return {setProjection(value){projection=value;},setReduced(value){reduced=value;if(value)smoke.length=0;},dispose};
  }catch(err){disposed=true;cancelAnimationFrame(raf);surface?.dispose();for(const item of images.values())URL.revokeObjectURL(item.url);throw err;}
}
