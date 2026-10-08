import type { GameplayRecording } from "./GameplayRecorder";

export type CustodyFrame = {
  frameId: string; frameDigest: string; capturedAtMs: number; sourceLocator: string;
};
export type DecoderVisualObservation = {
  frameId: string; frameDigest: string; luminanceMean: number;
  edgeDensity: number; motionEnergy: number; sceneChange: number;
};
export type LocalVisualAnalysis = {
  frames: readonly CustodyFrame[]; observations: readonly DecoderVisualObservation[];
};

const hex = (bytes: ArrayBuffer) => Array.from(new Uint8Array(bytes))
  .map(x => x.toString(16).padStart(2, "0")).join("");

async function digest(data: Uint8Array): Promise<string> {
  return hex(await crypto.subtle.digest("SHA-256", data));
}

/** Decode low-resolution frames locally. Raw pixels never leave this function. */
export async function extractLocalVisualObservations(
  recording: GameplayRecording, sampleIntervalMs = 500, maxFrames = 240,
  signal?: AbortSignal,
): Promise<LocalVisualAnalysis> {
  if (!recording.blob.size || recording.durationMs <= 0) throw new Error("Empty gameplay recording");
  if (!Number.isInteger(sampleIntervalMs) || sampleIntervalMs < 100 || sampleIntervalMs > 10000 ||
      !Number.isInteger(maxFrames) || maxFrames < 2 || maxFrames > 1000) throw new Error("Invalid visual budget");
  if (typeof document === "undefined" || !globalThis.crypto?.subtle) throw new Error("Local visual decoding unavailable");
  const abortError=()=>new DOMException("Visual decoding aborted","AbortError");
  const ensureActive=()=>{if(signal?.aborted)throw abortError();};
  ensureActive();
  const url=URL.createObjectURL(recording.blob), video=document.createElement("video");
  video.muted=true; video.playsInline=true; video.preload="auto"; video.src=url;
  const canvas=document.createElement("canvas"); canvas.width=64; canvas.height=36;
  const ctx=canvas.getContext("2d",{willReadFrequently:true}); if(!ctx){URL.revokeObjectURL(url);throw new Error("Canvas unavailable");}
  const wait=(name:string)=>new Promise<void>((resolve,reject)=>{
    const timer=setTimeout(()=>{clean();reject(new Error("Video decode timeout"));},15000);
    const ok=()=>{clean();resolve();},bad=()=>{clean();reject(new Error("Video decode failed"));};
    const abort=()=>{clean();reject(abortError());};
    const clean=()=>{clearTimeout(timer);video.removeEventListener(name,ok);video.removeEventListener("error",bad);signal?.removeEventListener("abort",abort);};
    video.addEventListener(name,ok,{once:true});video.addEventListener("error",bad,{once:true});
    signal?.addEventListener("abort",abort,{once:true});
    if(signal?.aborted)abort();
  });
  try {
    if(video.readyState<HTMLMediaElement.HAVE_METADATA) await wait("loadedmetadata");
    const total=Math.min(recording.durationMs,video.duration*1000);
    if(!Number.isFinite(total)||total<=0) throw new Error("Invalid decoded duration");
    const count=Math.min(maxFrames,Math.ceil(total/sampleIntervalMs));
    const frames:CustodyFrame[]=[], observations:DecoderVisualObservation[]=[]; let prev:Uint8ClampedArray|null=null;
    for(let i=0;i<count;i++){
      ensureActive();
      const ms=Math.min(total-1,i*sampleIntervalMs); if(ms<0)break;
      if(Math.abs(video.currentTime-ms/1000)>.01){const p=wait("seeked");video.currentTime=ms/1000;await p;}
      ctx.drawImage(video,0,0,64,36);const px=ctx.getImageData(0,0,64,36).data;
      const rgb=new Uint8Array(64*36*3);let lum=0,edges=0,motion=0;
      for(let p=0,q=0;p<px.length;p+=4){rgb[q++]=px[p];rgb[q++]=px[p+1];rgb[q++]=px[p+2];lum+=(px[p]+px[p+1]+px[p+2])/(3*255);
        if(prev)motion+=(Math.abs(px[p]-prev[p])+Math.abs(px[p+1]-prev[p+1])+Math.abs(px[p+2]-prev[p+2]))/(3*255);}
      for(let y=0;y<36;y++)for(let x=1;x<64;x++){const p=(y*64+x)*4,l=p-4;
        if((Math.abs(px[p]-px[l])+Math.abs(px[p+1]-px[l+1])+Math.abs(px[p+2]-px[l+2]))/(3*255)>.12)edges++;}
      const frameDigest=await digest(rgb);ensureActive();const frameId=await digest(new TextEncoder().encode(frameDigest+":"+Math.round(ms)));ensureActive();
      const n=64*36,m=prev?motion/n:0,e=edges/(36*63);
      frames.push({frameId,frameDigest,capturedAtMs:Math.round(ms),sourceLocator:`local-frame://${i}`});
      observations.push({frameId,frameDigest,luminanceMean:+(lum/n).toFixed(9),edgeDensity:+e.toFixed(9),
        motionEnergy:+m.toFixed(9),sceneChange:+Math.min(1,m/.35).toFixed(9)});
      prev=new Uint8ClampedArray(px);
    }
    return {frames,observations};
  } finally {video.pause();video.removeAttribute("src");video.load();URL.revokeObjectURL(url);}
}
