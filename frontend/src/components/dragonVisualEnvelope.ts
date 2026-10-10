import {DRAGON_VISUAL_DECODER_VERSION,type LocalVisualAnalysis} from "./dragonVisualObservationPipeline";

export const DRAGON_VISUAL_SCHEMA="dragon.visual-observations.v1" as const;
export type DragonVisualEnvelope = {
 schema:typeof DRAGON_VISUAL_SCHEMA; owner:string; jobId:string; recordingDigest:string;
 consentId:string; consentScopeDigest:string; retentionUntil:number;
 decoderVersion:typeof DRAGON_VISUAL_DECODER_VERSION;
 frames:LocalVisualAnalysis["frames"]; observations:LocalVisualAnalysis["observations"];
 payloadFingerprint:string;
};
const stable=(x:unknown):string=>{
 if(Array.isArray(x))return `[${x.map(stable).join(",")}]`;
 if(x&&typeof x==="object")return `{${Object.entries(x as Record<string,unknown>).sort(([a],[b])=>a.localeCompare(b)).map(([k,v])=>JSON.stringify(k)+":"+stable(v)).join(",")}}`;
 return JSON.stringify(x);
};
export const DRAGON_CANONICAL_WIRE="dragon.canonical-decimal.v1" as const;
const decimalWire=(x:number):string=>{if(!Number.isFinite(x))throw new Error("canonical decimal requires finite number");if(Object.is(x,-0)||x===0)return "0";const s=String(x);if(!/[eE]/.test(s))return s;const [m,e0]=s.toLowerCase().split("e"),e=Number(e0),neg=m.startsWith("-"),u=neg?m.slice(1):m,[a,b=""]=u.split("."),digits=a+b,pos=a.length+e;let out=pos<=0?"0."+"0".repeat(-pos)+digits:pos>=digits.length?digits+"0".repeat(pos-digits.length):digits.slice(0,pos)+"."+digits.slice(pos);out=out.replace(/^0+(?=\d)/,"").replace(/\.?0+$/,"");return (neg?"-":"")+(out||"0")};
const hex=(b:ArrayBuffer)=>Array.from(new Uint8Array(b)).map(x=>x.toString(16).padStart(2,"0")).join("");
export async function buildDragonVisualEnvelope(input:{
 owner:string;jobId:string;recordingDigest:string;consentId:string;consentScopeDigest:string;
 retentionUntil:number;analysis:LocalVisualAnalysis;
}):Promise<DragonVisualEnvelope>{
 if(!globalThis.crypto?.subtle)throw new Error("SHA-256 unavailable");
 if(input.analysis.decoderVersion!==DRAGON_VISUAL_DECODER_VERSION)throw new Error("Unsupported Dragon visual decoder version");
 const body={wire:DRAGON_CANONICAL_WIRE,schema:DRAGON_VISUAL_SCHEMA,owner:input.owner,job_id:input.jobId,
  recording_digest:input.recordingDigest,consent_id:input.consentId,
  consent_scope_digest:input.consentScopeDigest,decoder_version:input.analysis.decoderVersion,retention_until:decimalWire(input.retentionUntil),
  frames:input.analysis.frames.map(x=>[x.frameId,x.frameDigest,String(x.capturedAtMs),x.sourceLocator]),
  observations:input.analysis.observations.map(x=>[x.frameId,x.frameDigest,decimalWire(x.luminanceMean),decimalWire(x.edgeDensity),decimalWire(x.motionEnergy),decimalWire(x.sceneChange)])};
 const payloadFingerprint=hex(await crypto.subtle.digest("SHA-256",new TextEncoder().encode(stable(body))));
 return {schema:DRAGON_VISUAL_SCHEMA,owner:input.owner,jobId:input.jobId,
  recordingDigest:input.recordingDigest,consentId:input.consentId,
  consentScopeDigest:input.consentScopeDigest,retentionUntil:input.retentionUntil,
  decoderVersion:input.analysis.decoderVersion,frames:input.analysis.frames,
  observations:input.analysis.observations,payloadFingerprint};
}
