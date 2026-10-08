import type { LocalVisualAnalysis } from "./dragonVisualObservationPipeline";

export const DRAGON_VISUAL_SCHEMA="dragon.visual-observations.v1" as const;
export type DragonVisualEnvelope = {
 schema:typeof DRAGON_VISUAL_SCHEMA; owner:string; jobId:string; recordingDigest:string;
 consentId:string; consentScopeDigest:string; retentionUntil:number;
 frames:LocalVisualAnalysis["frames"]; observations:LocalVisualAnalysis["observations"];
 payloadFingerprint:string;
};
const stable=(x:unknown):string=>{
 if(Array.isArray(x))return `[${x.map(stable).join(",")}]`;
 if(x&&typeof x==="object")return `{${Object.entries(x as Record<string,unknown>).sort(([a],[b])=>a.localeCompare(b)).map(([k,v])=>JSON.stringify(k)+":"+stable(v)).join(",")}}`;
 return JSON.stringify(x);
};
const hex=(b:ArrayBuffer)=>Array.from(new Uint8Array(b)).map(x=>x.toString(16).padStart(2,"0")).join("");
export async function buildDragonVisualEnvelope(input:{
 owner:string;jobId:string;recordingDigest:string;consentId:string;consentScopeDigest:string;
 retentionUntil:number;analysis:LocalVisualAnalysis;
}):Promise<DragonVisualEnvelope>{
 if(!globalThis.crypto?.subtle)throw new Error("SHA-256 unavailable");
 const body={schema:DRAGON_VISUAL_SCHEMA,owner:input.owner,job_id:input.jobId,
  recording_digest:input.recordingDigest,consent_id:input.consentId,
  consent_scope_digest:input.consentScopeDigest,retention_until:input.retentionUntil,
  frames:input.analysis.frames.map(x=>[x.frameId,x.frameDigest,x.capturedAtMs,x.sourceLocator]),
  observations:input.analysis.observations.map(x=>[x.frameId,x.frameDigest,x.luminanceMean,x.edgeDensity,x.motionEnergy,x.sceneChange])};
 const payloadFingerprint=hex(await crypto.subtle.digest("SHA-256",new TextEncoder().encode(stable(body))));
 return {schema:DRAGON_VISUAL_SCHEMA,owner:input.owner,jobId:input.jobId,
  recordingDigest:input.recordingDigest,consentId:input.consentId,
  consentScopeDigest:input.consentScopeDigest,retentionUntil:input.retentionUntil,
  frames:input.analysis.frames,observations:input.analysis.observations,payloadFingerprint};
}
