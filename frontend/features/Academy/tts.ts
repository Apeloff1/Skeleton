/**
 * Lightweight singleton wrapper around expo-speech with settings integration.
 * Auto-applies the user's rate/pitch/voice/identifier and supports queued playback,
 * pause/resume, and per-chunk progress callbacks for audiobook reading UI.
 */
import * as Speech from 'expo-speech';
import { useSettings } from '../../state/settingsStore';

let queue: string[] = [];
let totalChunks = 0;
let chunkIndex = 0;
let playing = false;
let paused = false;
let onDoneCb: (() => void) | null = null;
let onProgressCb: ((idx: number, total: number, text: string) => void) | null = null;

function strip(text: string, readCode: boolean): string {
  if (!text) return '';
  if (!readCode) {
    text = text.replace(/```[\s\S]*?```/g, ' (code block) ');
    text = text.replace(/`[^`]*`/g, ' code ');
  }
  // Markdown cleanup
  text = text.replace(/!\[[^\]]*\]\([^)]*\)/g, ''); // images
  text = text.replace(/\[([^\]]+)\]\([^)]*\)/g, '$1'); // links → text
  text = text.replace(/[#*_~>]/g, ' ');
  text = text.replace(/\s+/g, ' ').trim();
  return text;
}

function chunk(text: string, max = 320): string[] {
  // Shorter chunks = smoother delivery + easier pause/resume + better progress.
  const out: string[] = [];
  const sentences = text.split(/(?<=[.!?])\s+/);
  let cur = '';
  for (const s of sentences) {
    if ((cur + ' ' + s).length > max && cur) {
      out.push(cur.trim());
      cur = s;
    } else {
      cur = cur ? `${cur} ${s}` : s;
    }
  }
  if (cur) out.push(cur.trim());
  return out;
}

async function playNext() {
  if (paused) return;
  if (!queue.length) {
    playing = false;
    if (onDoneCb) { const cb = onDoneCb; onDoneCb = null; cb(); }
    return;
  }
  playing = true;
  const { academy } = useSettings.getState();
  const text = queue.shift()!;
  chunkIndex += 1;
  onProgressCb?.(chunkIndex, totalChunks, text);
  const opts: any = {
    rate: academy.ttsRate,
    pitch: academy.ttsPitch,
    language: academy.voiceLang || 'en-US',
    onDone: () => { setTimeout(playNext, 80); },
    onError: () => { setTimeout(playNext, 80); },
    onStopped: () => { playing = false; /* queue cleared elsewhere */ },
  };
  if (academy.voiceIdentifier) opts.voice = academy.voiceIdentifier;
  try {
    Speech.speak(text, opts);
  } catch {
    setTimeout(playNext, 80);
  }
}

export interface TTSOptions {
  readCode?: boolean;
  onComplete?: () => void;
  onProgress?: (idx: number, total: number, text: string) => void;
}

export function ttsSpeak(text: string, opts?: TTSOptions) {
  const { academy } = useSettings.getState();
  const readCode = opts?.readCode ?? academy.readCodeBlocks;
  const stripped = strip(text, readCode);
  if (!stripped) return;
  queue = chunk(stripped);
  totalChunks = queue.length;
  chunkIndex = 0;
  onDoneCb = opts?.onComplete || null;
  onProgressCb = opts?.onProgress || null;
  try { Speech.stop(); } catch {}
  paused = false;
  playing = true;
  playNext();
}

export function ttsStop() {
  queue = [];
  totalChunks = 0;
  chunkIndex = 0;
  onDoneCb = null;
  onProgressCb = null;
  paused = false;
  try { Speech.stop(); } catch {}
  playing = false;
}

export function ttsPause() {
  if (!playing) return;
  paused = true;
  try { Speech.stop(); } catch {}
}

export function ttsResume() {
  if (!paused) return;
  paused = false;
  playNext();
}

export function ttsIsSpeaking(): boolean {
  return playing && !paused;
}

export function ttsIsPaused(): boolean {
  return paused;
}

export function ttsProgress(): { current: number; total: number } {
  return { current: chunkIndex, total: totalChunks };
}

export async function ttsAvailableVoices() {
  try {
    return await Speech.getAvailableVoicesAsync();
  } catch {
    return [];
  }
}

/**
 * Pick the best male-leaning voice for the given language.
 * Heuristics: voice name contains "male" / a common male first name, or
 * identifier has known male tokens (Google: en-us-x-iom — usually male).
 * If nothing matches, returns the first voice that matches the language.
 */
export async function pickPreferredVoice(
  lang: string = 'en-US',
  gender: 'male' | 'female' | 'any' = 'male'
): Promise<string> {
  try {
    const voices = await ttsAvailableVoices();
    if (!voices || voices.length === 0) return '';
    const langLower = lang.toLowerCase();
    // First pass — voices in requested language
    const inLang = voices.filter((v: any) => (v.language || '').toLowerCase().startsWith(langLower.split('-')[0]));
    const candidates = inLang.length > 0 ? inLang : voices;

    if (gender === 'any') return candidates[0]?.identifier || '';

    const MALE_NAME_TOKENS = [
      'male', 'man', 'guy', 'deep',
      // Common male English first names from platform voices
      'daniel', 'fred', 'alex', 'tom', 'george', 'arthur', 'oliver',
      'james', 'john', 'michael', 'david', 'ryan', 'aaron',
      'reed', 'eddy', 'rocko', 'grandpa',
      // Google IDs commonly male
      'iom', 'itn', 'imn',
    ];
    const FEMALE_NAME_TOKENS = [
      'female', 'woman',
      'samantha', 'susan', 'victoria', 'allison', 'ava', 'karen',
      'serena', 'kate', 'fiona', 'tessa', 'nora', 'grandma',
    ];
    const wanted = gender === 'male' ? MALE_NAME_TOKENS : FEMALE_NAME_TOKENS;
    const opposite = gender === 'male' ? FEMALE_NAME_TOKENS : MALE_NAME_TOKENS;

    const scored = candidates.map((v: any) => {
      const hay = `${v.name || ''} ${v.identifier || ''}`.toLowerCase();
      let score = 0;
      for (const t of wanted) if (hay.includes(t)) score += 2;
      for (const t of opposite) if (hay.includes(t)) score -= 2;
      // Prefer enhanced/neural voices for quality
      if (hay.includes('enhanced') || hay.includes('premium') || hay.includes('neural') || hay.includes('wavenet')) score += 1;
      return { v, score };
    });
    scored.sort((a, b) => b.score - a.score);
    return scored[0]?.v?.identifier || candidates[0]?.identifier || '';
  } catch {
    return '';
  }
}
