/**
 * 🎙️ CINEMATIC VOICE — plays Jeeves & narration through the immersive
 * tts-1-hd backend (storyteller cadence + augmented tone control) so the
 * voice has real "innlevelse" instead of the robotic on-device speech.
 *
 * Endpoints:
 *   POST /api/jeeves-voice/voice/speak   → { audio_base64, voice, speed, tone }
 *   GET  /api/jeeves-voice/voice/preview → audition a tone
 *   GET  /api/jeeves-voice/voice/tones   → tone catalog
 */
import { Platform } from 'react-native';
import { createAudioPlayer, setAudioModeAsync, type AudioPlayer } from 'expo-audio';

const BACKEND = process.env.EXPO_PUBLIC_BACKEND_URL || '';

let current: AudioPlayer | null = null;
let webUrl: string | null = null;

export type Tone = {
  id: string;
  label: string;
  voice: string;
  speed: number;
};

export function stopCinematic() {
  try { current?.remove(); } catch {}
  current = null;
  if (webUrl) { try { URL.revokeObjectURL(webUrl); } catch {} webUrl = null; }
}

function base64ToBytes(b64: string): Uint8Array {
  const bin = typeof atob === 'function' ? atob(b64) : Buffer.from(b64, 'base64').toString('binary');
  const len = bin.length;
  const bytes = new Uint8Array(len);
  for (let i = 0; i < len; i++) bytes[i] = bin.charCodeAt(i);
  return bytes;
}

/** Turn a base64 mp3 into a playable URI (blob on web, cache file on native). */
async function uriFromBase64(b64: string): Promise<string> {
  if (Platform.OS === 'web') {
    const blob = new Blob([base64ToBytes(b64)], { type: 'audio/mpeg' });
    webUrl = URL.createObjectURL(blob);
    return webUrl;
  }
  // Native: write to cache and play the file.
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const FS = require('expo-file-system/legacy');
  const uri = `${FS.cacheDirectory}cinematic-${Date.now()}.mp3`;
  await FS.writeAsStringAsync(uri, b64, { encoding: 'base64' });
  return uri;
}

async function playBase64(b64: string): Promise<AudioPlayer> {
  stopCinematic();
  try {
    await setAudioModeAsync({ playsInSilentMode: true, shouldPlayInBackground: false });
  } catch {}
  const uri = await uriFromBase64(b64);
  const player = createAudioPlayer({ uri });
  current = player;
  try { const p: any = player.play(); if (p?.catch) p.catch(() => {}); } catch {}
  return player;
}

export type SpeakResult =
  | { ok: true; voice: string; speed: number; tone: string; spoken: string }
  | { ok: false; spoken?: string; error: string };

/**
 * Speak text with the cinematic HD voice. Returns metadata; resolves once
 * playback has STARTED (audio continues in the background).
 */
export async function speakCinematic(
  text: string,
  opts: { tone?: string; voice?: string; speed?: number; emotionalState?: string } = {},
): Promise<SpeakResult> {
  if (!text?.trim()) return { ok: false, error: 'empty text' };
  try {
    const r = await fetch(`${BACKEND}/api/jeeves-voice/voice/speak`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        text,
        tone: opts.tone || 'butler',
        voice: opts.voice,
        speed: opts.speed,
        emotional_state: opts.emotionalState,
      }),
    });
    const j = await r.json();
    if (j?.status === 'success' && j.audio_base64) {
      await playBase64(j.audio_base64);
      return { ok: true, voice: j.voice, speed: j.speed, tone: j.tone, spoken: j.spoken_text };
    }
    return { ok: false, spoken: j?.spoken_text, error: j?.error || 'no audio' };
  } catch (e: any) {
    return { ok: false, error: String(e?.message || e) };
  }
}

/** Audition a tone with a short sample line. */
export async function previewTone(tone: string): Promise<SpeakResult> {
  try {
    const r = await fetch(`${BACKEND}/api/jeeves-voice/voice/preview?tone=${encodeURIComponent(tone)}`);
    const j = await r.json();
    if (j?.status === 'success' && j.audio_base64) {
      await playBase64(j.audio_base64);
      return { ok: true, voice: j.voice, speed: j.speed, tone: j.tone, spoken: j.sample_text };
    }
    return { ok: false, spoken: j?.sample_text, error: j?.error || 'no audio' };
  } catch (e: any) {
    return { ok: false, error: String(e?.message || e) };
  }
}

export async function fetchTones(): Promise<Tone[]> {
  try {
    const r = await fetch(`${BACKEND}/api/jeeves-voice/voice/tones`);
    const j = await r.json();
    return Array.isArray(j?.tones) ? j.tones : [];
  } catch {
    return [];
  }
}

export type TrailerClip = { label: string; tone: string; audio_base64?: string; spoken_text?: string; status: string };

/** 🎬 Build a 3-beat voiced trailer and play the beats back-to-back. */
export async function playTrailer(
  body: { pid?: string; title?: string; theme?: string; lore?: string; tagline?: string },
): Promise<{ ok: boolean; title?: string; clips?: TrailerClip[]; error?: string }> {
  try {
    const r = await fetch(`${BACKEND}/api/jeeves-voice/trailer`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const j = await r.json();
    const clips: TrailerClip[] = j?.clips || [];
    if (clips.length) {
      await playClipsSequential(clips.map(c => c.audio_base64).filter(Boolean) as string[]);
    }
    return { ok: clips.length > 0, title: j?.title, clips };
  } catch (e: any) {
    return { ok: false, error: String(e?.message || e) };
  }
}

/** Play an ordered list of base64 mp3 clips one after another. */
export async function playClipsSequential(clips: string[]): Promise<void> {
  stopCinematic();
  try { await setAudioModeAsync({ playsInSilentMode: true, shouldPlayInBackground: false }); } catch {}
  for (const b64 of clips) {
    const uri = await uriFromBase64(b64);
    const player = createAudioPlayer({ uri });
    current = player;
    try { const p: any = player.play(); if (p?.catch) p.catch(() => {}); } catch {}
    // Wait for this clip to finish before the next beat.
    await new Promise<void>((resolve) => {
      let done = false;
      const finish = () => { if (!done) { done = true; resolve(); } };
      const sub = player.addListener('playbackStatusUpdate', (st: any) => {
        if (st?.didJustFinish || (st?.duration && st?.currentTime >= st.duration - 0.05)) finish();
      });
      // Safety timeout so a missed event never hangs the chain.
      setTimeout(() => { try { sub?.remove?.(); } catch {} finish(); }, 15000);
    });
  }
}
