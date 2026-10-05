/**
 * Jeeves-flavoured TTS wrapper.
 * ------------------------------------------------------------------
 * Sits atop the lightweight expo-speech wrapper in `tts.ts` and adds
 * persona-aware behaviour by calling the backend persona endpoints:
 *
 *   GET  /api/jeeves/catchphrase?context=<ctx>   → random flourish
 *   POST /api/jeeves/speak  (used when audio_b64 desired; we still fall back
 *                            to expo-speech for the heavy lifting on-device)
 *
 * Why this approach?
 *   - Backend OpenAI TTS is *gorgeous* but expensive + slow.
 *   - On-device expo-speech is instant and free.
 *   - We get the best of both worlds: persona TEXT from backend (which contains
 *     biography-aware catchphrases and mannerism speed hints), then speak it
 *     locally using mannerism-mapped rate/pitch.
 *
 * Public API:
 *   await jeevesSpeak(text, { context: 'story_time' })
 *   await jeevesCatchphrase('greeting')   → returns string
 *   await getRandomQuote() → string
 */
import { ttsSpeak, ttsStop } from './tts';
import { useSettings } from '../../state/settingsStore';
import { speakCinematic, stopCinematic } from '../../src/utils/cinematicVoice';

const BACKEND = process.env.EXPO_PUBLIC_BACKEND_URL || '';

// Per-context expressive tone for the cinematic HD voice. Falls back to the
// user's chosen Jeeves tone (default "butler") when a context isn't mapped.
const CONTEXT_TONE: Record<string, string> = {
  greeting: 'warm', lesson: 'butler', lesson_intro: 'storyteller',
  encouragement: 'triumphant', gentle_correction: 'gentle', alert: 'dramatic',
  debug: 'calm', joke: 'witty', sign_off: 'warm', quiz_nudge: 'witty',
  celebration: 'triumphant', code_walkthrough: 'calm', story_time: 'storyteller',
  thinking: 'calm', frustration_relief: 'gentle', transition: 'butler',
  definition: 'narrator', warning_clarification: 'dramatic', quote: 'solemn',
};

// ─── Local cache so we don't hammer the backend on every page ───
const _catchphraseCache: Record<string, string[]> = {};
const _mannerismCache: Record<string, { speed: number; pitch_hint: string; emoji: string; voice: string }> = {};
let _mannerismsLoaded = false;

export type JeevesContext =
  | 'greeting' | 'lesson' | 'lesson_intro' | 'encouragement'
  | 'gentle_correction' | 'alert' | 'debug' | 'joke'
  | 'sign_off' | 'quiz_nudge' | 'celebration'
  | 'code_walkthrough' | 'story_time' | 'thinking'
  | 'frustration_relief' | 'transition' | 'definition'
  | 'warning_clarification' | 'quote';

/** Load and cache vocal mannerism map (single fetch, persists for session). */
async function _loadMannerisms(): Promise<void> {
  if (_mannerismsLoaded) return;
  try {
    const r = await fetch(`${BACKEND}/api/jeeves/persona/vocal_mannerisms`);
    const j = await r.json();
    if (j && typeof j === 'object') {
      Object.entries(j).forEach(([ctx, m]: [string, any]) => {
        _mannerismCache[ctx] = {
          speed: typeof m?.speed === 'number' ? m.speed : 1.0,
          pitch_hint: m?.pitch_hint || '',
          emoji: m?.emoji || '',
          voice: m?.voice || 'fable',
        };
      });
      _mannerismsLoaded = true;
    }
  } catch {
    // silent fail — fall back to defaults
  }
}

/** Fetch a random Jeeves catchphrase for a context. Cached after first call. */
export async function jeevesCatchphrase(context: JeevesContext = 'lesson'): Promise<string> {
  // Use the cached list if we have ≥3 entries (cycle through them locally)
  if (_catchphraseCache[context] && _catchphraseCache[context].length > 0) {
    const list = _catchphraseCache[context];
    return list[Math.floor(Math.random() * list.length)];
  }
  try {
    // First call: populate cache from full persona (one round trip).
    if (!_catchphraseCache[context]) {
      try {
        const rAll = await fetch(`${BACKEND}/api/jeeves/persona/catchphrases`);
        const all = await rAll.json();
        if (all && typeof all === 'object') {
          Object.entries(all).forEach(([k, v]) => {
            if (Array.isArray(v)) _catchphraseCache[k] = v as string[];
          });
        }
      } catch {}
    }
    if (_catchphraseCache[context]?.length) {
      const list = _catchphraseCache[context];
      return list[Math.floor(Math.random() * list.length)];
    }
    const r = await fetch(`${BACKEND}/api/jeeves/catchphrase?context=${encodeURIComponent(context)}`);
    const j = await r.json();
    return String(j?.phrase || '');
  } catch {
    return '';
  }
}

/** Get a famous quote that Jeeves adores. */
export async function getRandomQuote(): Promise<{ author: string; quote: string } | null> {
  try {
    const r = await fetch(`${BACKEND}/api/jeeves/quote/random`);
    const j = await r.json();
    return j?.quote || null;
  } catch {
    return null;
  }
}

export interface JeevesSpeakOptions {
  context?: JeevesContext;
  /** Prepend a context-appropriate catchphrase (default true). */
  prependCatchphrase?: boolean;
  /** Append a sign-off catchphrase (default false). */
  appendSignoff?: boolean;
  readCode?: boolean;
  onProgress?: (idx: number, total: number, text: string) => void;
  onComplete?: () => void;
}

/**
 * Speak text with Jeeves persona flair.
 * - Prepends a catchphrase for the given context.
 * - Looks up the mannerism (speed) and applies it via the settings store
 *   temporarily — actual playback uses on-device TTS for speed & reliability.
 */
export async function jeevesSpeak(text: string, opts: JeevesSpeakOptions = {}): Promise<void> {
  const context = opts.context || 'lesson';
  await _loadMannerisms();

  const parts: string[] = [];
  if (opts.prependCatchphrase !== false) {
    const cp = await jeevesCatchphrase(context);
    if (cp) parts.push(cp);
  }
  if (text) parts.push(text);
  if (opts.appendSignoff) {
    const sig = await jeevesCatchphrase('sign_off');
    if (sig) parts.push(sig);
  }
  const spoken = parts.join('  ');

  // 🎙️ Cinematic HD voice — route through the immersive backend (storyteller
  // cadence + tone control) when enabled. Falls back to on-device speech if
  // the network/TTS call fails so the app never goes silent.
  const academyState: any = useSettings.getState().academy;
  if (academyState?.cinematicVoice !== false) {
    const tone = CONTEXT_TONE[context] || academyState?.jeevesTone || 'butler';
    const res = await speakCinematic(spoken, { tone });
    if (res.ok) {
      opts.onComplete?.();
      return;
    }
    // fall through to on-device speech on failure
  }

  // Pull mannerism for the requested context
  const m = _mannerismCache[context];
  if (m) {
    // Temporarily nudge TTS rate based on mannerism
    const original = useSettings.getState().academy;
    const newRate = Math.max(0.5, Math.min(2.0, (original.ttsRate || 1.0) * (m.speed || 1.0)));
    useSettings.setState({ academy: { ...original, ttsRate: newRate } });
    // After playback we restore the rate via onComplete
    ttsSpeak(spoken, {
      readCode: opts.readCode,
      onProgress: opts.onProgress,
      onComplete: () => {
        // restore
        useSettings.setState({ academy: original });
        opts.onComplete?.();
      },
    });
    return;
  }

  // No mannerism — speak as-is
  ttsSpeak(spoken, {
    readCode: opts.readCode,
    onProgress: opts.onProgress,
    onComplete: opts.onComplete,
  });
}

/** Stop any current Jeeves narration. */
export function jeevesStop(): void {
  ttsStop();
  stopCinematic();
}

/**
 * Returns the active Jeeves enabled flag from settings.
 * Defaults to `true` if the setting doesn't exist (graceful migration).
 */
export function isJeevesEnabled(): boolean {
  const s: any = useSettings.getState().academy;
  return s?.jeevesPersonaEnabled !== false;
}
