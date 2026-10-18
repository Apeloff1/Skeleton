/** Video co-watching privacy boundaries and user-controlled retention. */
export type VideoPrivacyMode='off'|'ephemeral'|'review-only';
export interface VideoPrivacySettings {
 mode:VideoPrivacyMode;
 allowTranscript:boolean;
 allowVisual:boolean;
 allowAudio:boolean;
 retainObservations:boolean;
 maxSessionMinutes:number;
}
export const DEFAULT_VIDEO_PRIVACY:VideoPrivacySettings={
 mode:'off',allowTranscript:false,allowVisual:false,allowAudio:false,
 retainObservations:false,maxSessionMinutes:30
};
export function validateVideoPrivacy(settings:VideoPrivacySettings):VideoPrivacySettings {
 if(!['off','ephemeral','review-only'].includes(settings.mode))throw new Error('Unknown video privacy mode');
 if(!Number.isSafeInteger(settings.maxSessionMinutes)||settings.maxSessionMinutes<1||settings.maxSessionMinutes>240)
  throw new Error('Invalid session duration');
 if(settings.mode==='off'&&(settings.allowTranscript||settings.allowVisual||settings.allowAudio||settings.retainObservations))
  throw new Error('Disabled video observation cannot request capture or retention');
 if(settings.mode==='ephemeral'&&settings.retainObservations)
  throw new Error('Ephemeral mode cannot retain observations');
 return {...settings};
}
export function mayProcessVideoModality(settings:VideoPrivacySettings,modality:'transcript'|'caption'|'frame_description'|'ocr'|'audio_description'):boolean{
 if(settings.mode==='off')return false;
 if(modality==='transcript'||modality==='caption')return settings.allowTranscript;
 if(modality==='frame_description'||modality==='ocr')return settings.allowVisual;
 return settings.allowAudio;
}
