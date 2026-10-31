/** Explicit animation completion semantics and user comfort settings. */
export type CompanionMotion='full'|'gentle'|'off';
export interface CompanionPreferences {motion:CompanionMotion;sound:boolean;haptics:boolean;autonomousSuggestions:boolean;privacy:'local-only'|'approved-research';lowPower:boolean;screenReaderDetail:boolean}
export const DEFAULT_COMPANION_PREFERENCES:CompanionPreferences={motion:'gentle',sound:false,haptics:false,autonomousSuggestions:false,privacy:'local-only',lowPower:false,screenReaderDetail:true};
export function animationParameters(preferences:CompanionPreferences,phase:string){
 const duration=preferences.motion==='off'?0:preferences.motion==='gentle'?1300:650;
 return {duration,animate:duration>0,fireIntensity:preferences.motion==='full'&&phase==='burning'?1:preferences.motion==='off'?0:.45};
}
export function canSuggestCrawl(preferences:CompanionPreferences,explicitApproval:boolean){
 return preferences.privacy==='approved-research'&&preferences.autonomousSuggestions&&explicitApproval;
}
/** Battery saver, the OS reduced-motion setting and an explicit low-power choice all stop animation. */
export function effectiveMotion(preferences:CompanionPreferences,systemReduced:boolean,batterySaver:boolean):CompanionMotion{
 if(systemReduced||preferences.lowPower||batterySaver)return'off';
 return preferences.motion;
}
