import { CryptoDigestAlgorithm, digest } from 'expo-crypto';
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { ActivityIndicator, AppState, Platform, Text, TextInput, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { ChatClientError } from '../../src/product/chatErrors';
import { getAuthToken } from '../../src/auth/gameforgeAuth';
import { type LearningProject, learningRequestKey } from '../../src/product/gameLearningClient';
import {
  controlGamePlay, exportGameRecording, getGamePlay, getGameRecording, inputGamePlay, listGamePlays, listGameRecordings, replayGameRecording,
  startGamePlay, startGameRecording, stopGameRecording, withdrawGameRecording, type GamePlay, type GameRecording, type GameResourceProfile,
} from '../../src/product/gamePlayClient';
import GameLearningFrame from './GameLearningFrame';
import { saveLearningExport } from './gameLearningFiles';
import s, { gameLearningColors as C } from './GameLearningWorkspace.styles';

const ENDED = new Set(['stopped', 'completed', 'failed', 'cancelled', 'interrupted', 'mismatch']);
function human(value: string) { return value.replace(/_/g, ' ').replace(/\b\w/g, letter => letter.toUpperCase()); }
function Button({ label, press, disabled, primary }: { label: string; press: () => void; disabled?: boolean; primary?: boolean }) {
  return <TouchableOpacity accessibilityRole="button" accessibilityState={{ disabled }} disabled={disabled} onPress={press}
    style={[s.button, primary && s.primaryButton, disabled && s.disabled]}><Text style={s.buttonText}>{label}</Text></TouchableOpacity>;
}
function keyAction(key: string, actions: string[]) {
  const maps: Record<string, string[]> = {
    ArrowUp: ['up', 'move_up'], w: ['up', 'move_up'], ArrowDown: ['down', 'move_down'], s: ['down', 'move_down'],
    ArrowLeft: ['left', 'move_left'], a: ['left', 'move_left'], ArrowRight: ['right', 'move_right'], d: ['right', 'move_right'],
    ' ': ['jump', 'a', 'button_a', 'interact', 'fire'], z: ['a', 'button_a', 'fire', 'interact'], x: ['b', 'button_b', 'jump'],
    Enter: ['start', 'interact', 'confirm'], Shift: ['select', 'run'], c: ['c', 'button_c'],
    e: ['interact'], j: ['attack', 'fire'], k: ['fire', 'shoot', 'attack'], f: ['fish'], h: ['hoe'], p: ['plant'], v: ['harvest'], t: ['water'], r: ['rest'], Tab: ['tool_next'],
    '1': ['fish'], '2': ['hoe'], '3': ['water'], '4': ['plant'], '5': ['harvest'],
  };
  return maps[key]?.find(value => actions.includes(value));
}
function padActions(pad: Gamepad, actions: string[], tool?: string) {
  const active = new Set<string>();
  const add = (candidates: string[], pressed: boolean) => { const action = candidates.find(value => actions.includes(value)); if (action && pressed) active.add(action); };
  const down = (index: number) => !!pad.buttons[index]?.pressed;
  add(['left', 'move_left'], down(14) || (pad.axes[0] ?? 0) < -0.45);
  add(['right', 'move_right'], down(15) || (pad.axes[0] ?? 0) > 0.45);
  add(['up', 'move_up'], down(12) || (pad.axes[1] ?? 0) < -0.45);
  add(['down', 'move_down'], down(13) || (pad.axes[1] ?? 0) > 0.45);
  add(['a', 'button_a', 'interact', 'jump', 'fire'], down(0)); add(['b', 'button_b', 'attack', 'fire', 'jump'], down(1));
  add(['x', 'button_x', ...(tool ? [tool] : []), 'interact'], down(2)); add(['y', 'button_y', 'tool_next'], down(3));
  add(['l', 'button_l'], down(4)); add(['r', 'button_r'], down(5)); add(['select'], down(8)); add(['start', 'confirm'], down(9));
  return active;
}

/** Live controls are authenticated input to the canonical runtime, never local gameplay. */
export default function GamePlayViewport({ project, sourceId, seed, disabled, onRecordingsChange, initialPlay, resourceProfile }: {
  project: LearningProject; sourceId?: string; seed: number; disabled?: boolean;
  onRecordingsChange?: (recordings: GameRecording[]) => void;
  initialPlay?: GamePlay | null; resourceProfile?: GameResourceProfile;
}) {
  const [savedPlays, setSavedPlays] = useState<GamePlay[]>([]);
  const [play, setPlay] = useState<GamePlay | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [keyboard, setKeyboard] = useState(false);
  const [gamepad, setGamepad] = useState(false);
  const [sound, setSound] = useState(false);
  const [soundNotice, setSoundNotice] = useState<string | null>(null);
  const [held, setHeld] = useState<string[]>([]);
  const [gamepadTool, setGamepadTool] = useState('fish');
  const [recordings, setRecordings] = useState<GameRecording[]>([]);
  const [recording, setRecording] = useState<GameRecording | null>(null);
  const [consent, setConsent] = useState(false);
  const [label, setLabel] = useState('');
  const [rating, setRating] = useState(0);
  const [note, setNote] = useState('');
  const [connection, setConnection] = useState('');
  const [withdrawal, setWithdrawal] = useState<string | null>(null);
  const live = useRef<GamePlay | null>(null);
  const audioContext = useRef<AudioContext | null>(null);
  const audioSources = useRef(new Set<AudioBufferSourceNode>());
  const audioCursor = useRef(0); const audioTime = useRef(0); const audioSession = useRef('');
  const mounted = useRef(true);
  const owner = useRef({ token: getAuthToken(), projectId: project.project_id });
  const requests = useRef(new Set<AbortController>());
  const heldSources = useRef(new Map<string, Set<string>>());
  const inputSequence = useRef(0);
  const inputQueue = useRef<{ action: string; held: boolean }[]>([]);
  const serial = useRef<Promise<void>>(Promise.resolve());
  const callbacks = useRef(onRecordingsChange); callbacks.current = onRecordingsChange;
  const mutation = useRef(false);
  const flush = useRef<() => void>(() => undefined);
  const startAttempt = useRef<{ fingerprint: string; key: string } | null>(null);
  const recordAttempt = useRef<{ fingerprint: string; key: string } | null>(null);
  const replayAttempt = useRef<{ fingerprint: string; key: string } | null>(null);
  const openedPlay = useRef('');
  const projectRef = useRef(project); projectRef.current = project;
  const account = getAuthToken();
  const safe = useCallback(() => mounted.current && owner.current.token === getAuthToken() && owner.current.projectId === projectRef.current.project_id, []);
  const accept = useCallback((value: GamePlay, intentional = false) => {
    if (!safe()) return;
    const previous = live.current;
    if (previous && previous.play_id !== value.play_id && !intentional) return;
    if (previous && previous.play_id === value.play_id) {
      if (!intentional && value.stream_id !== previous.stream_id) { setError('The session changed. Reopen it before sending more controls.'); return; }
      if (!intentional && value.control_version < previous.control_version) return;
      if (!intentional && value.frame_sequence <= previous.frame_sequence) value = { ...value, frame_sequence: previous.frame_sequence, latest_frame: previous.latest_frame };
      if (!value.control_token && value.controller_epoch === previous.controller_epoch && value.control_version === previous.control_version && value.controller === previous.controller) value = { ...value, control_token: previous.control_token };
      // Reads never grant a new controller lease; preserve only this controller's unchanged epoch.
      if (!value.control_token && value.controller === 'human' && previous.controller === 'human' && value.controller_epoch === previous.controller_epoch) value = { ...value, control_token: previous.control_token };
    }
    if (!previous || previous.play_id !== value.play_id || previous.controller_epoch !== value.controller_epoch) {
      inputSequence.current = 0; inputQueue.current = []; heldSources.current.clear(); setHeld([]);
    }
    live.current = value; setPlay(value); setSavedPlays(current => current.some(item => item.play_id === value.play_id) ? current.map(item => item.play_id === value.play_id ? value : item) : [value, ...current].slice(0, 32));
  }, [safe]);
  useEffect(() => { if (!initialPlay || initialPlay.project_id !== projectRef.current.project_id || openedPlay.current === initialPlay.play_id || !safe()) return; openedPlay.current = initialPlay.play_id; if (live.current?.play_id !== initialPlay.play_id) requests.current.forEach(request => request.abort()); accept(initialPlay, true); setKeyboard(Platform.OS === 'web' && initialPlay.controller === 'human'); }, [initialPlay, accept, safe]);
  const stopSound = useCallback(() => {
    audioSources.current.forEach(source => { try { source.stop(); } catch { /* The source already ended. */ } }); audioSources.current.clear();
    audioTime.current = 0; audioCursor.current = 0; audioSession.current = '';
    void audioContext.current?.suspend().catch(() => undefined);
  }, []);
  const toggleSound = () => {
    if (sound) { setSound(false); stopSound(); return; }
    try {
      if (Platform.OS !== 'web' || typeof window.AudioContext !== 'function') throw new Error('Browser audio playback is unavailable on this device.');
      if (!audioContext.current) audioContext.current = new window.AudioContext();
      void audioContext.current.resume().then(() => { if (safe()) { setSound(true); setSoundNotice(null); } }).catch(() => { if (safe()) setSoundNotice('Allow audio playback in your browser, then enable sound again.'); });
    } catch (caught) { setSoundNotice(caught instanceof Error ? caught.message : 'Sound is unavailable.'); }
  };
  const loadRecordings = useCallback(async (signal?: AbortSignal) => {
    const values = await listGameRecordings(projectRef.current.project_id, { signal });
    if (safe() && !signal?.aborted) { setRecordings(values); callbacks.current?.(values); }
  }, [safe]);
  const run = useCallback(async (operation: (signal: AbortSignal) => Promise<void>) => {
    if (mutation.current || !safe()) return;
    mutation.current = true; setBusy(true); setError(null);
    const controller = new AbortController(); requests.current.add(controller);
    try { await serial.current; await operation(controller.signal); }
    catch (caught) { if (safe() && !controller.signal.aborted) setError(caught instanceof Error ? caught.message : 'The play action could not be completed.'); }
    finally { requests.current.delete(controller); mutation.current = false; if (safe()) { setBusy(false); if (inputQueue.current.length) flush.current(); } }
  }, [safe]);
  const drain = useCallback(() => {
    serial.current = serial.current.then(async () => {
      while (inputQueue.current.length && safe() && !mutation.current) {
        const event = inputQueue.current.shift()!; const current = live.current;
        if (!current?.control_token || current.controller !== 'human' || current.status !== 'running') { inputQueue.current = []; break; }
        const controller = new AbortController(); requests.current.add(controller);
        try { const value = await inputGamePlay(current, event.action, event.held, inputSequence.current + 1, { signal: controller.signal }); if (controller.signal.aborted || !safe() || live.current?.play_id !== current.play_id || live.current.stream_id !== current.stream_id || live.current.controller_epoch !== current.controller_epoch) continue; inputSequence.current++; accept(value); }
        catch (caught) {
          if (controller.signal.aborted || !safe() || live.current?.play_id !== current.play_id || live.current.stream_id !== current.stream_id || live.current.controller_epoch !== current.controller_epoch) continue;
          inputQueue.current = []; heldSources.current.clear(); if (safe()) { if (live.current) { live.current = { ...live.current, control_token: undefined }; setPlay(live.current); } setHeld([]); setKeyboard(false); setGamepad(false); setError(caught instanceof Error ? caught.message : 'Input could not be delivered.'); }
          break;
        } finally { requests.current.delete(controller); }
      }
    });
  }, [accept, safe]);
  flush.current = drain;
  const hold = useCallback((action: string, pressed: boolean, source: string) => {
    if (!safe() || pressed && mutation.current || !live.current?.control_token || live.current.controller !== 'human' || live.current.status !== 'running' || !live.current.actions.includes(action)) return;
    const sources = heldSources.current.get(action) || new Set<string>(); const wasHeld = sources.size > 0;
    if (pressed) sources.add(source); else sources.delete(source);
    if (sources.size) heldSources.current.set(action, sources); else heldSources.current.delete(action);
    const isHeld = sources.size > 0; setHeld([...heldSources.current.keys()]);
    if (isHeld !== wasHeld && inputQueue.current.length < 128) { inputQueue.current.push({ action, held: isHeld }); drain(); }
  }, [drain, safe]);
  const release = useCallback(() => {
    const actions = [...heldSources.current.keys()]; heldSources.current.clear(); setHeld([]);
    for (const action of actions) inputQueue.current.push({ action, held: false }); drain();
  }, [drain]);
  const control = useCallback((action: 'pause' | 'resume' | 'stop' | 'reset' | 'takeover', controller?: 'human' | 'ai') => {
    release(); void run(async signal => {
      await serial.current; const current = live.current; if (!current) return;
      const value = await controlGamePlay(current, action, { controller, policyId: controller === 'ai' ? projectRef.current.policy_id || undefined : undefined }, { signal });
      inputQueue.current = []; heldSources.current.clear(); if (!signal.aborted) { accept(value, true); setHeld([]); }
    });
  }, [accept, release, run]);
  useEffect(() => {
    mounted.current = true; const controller = new AbortController();
    void listGamePlays(projectRef.current.project_id, { signal: controller.signal }).then(async values => {
      if (safe() && !controller.signal.aborted) setSavedPlays(live.current ? [live.current, ...values.filter(value => value.play_id !== live.current?.play_id)] : values);
      const previous = values.find(value => !ENDED.has(value.status) || value.resume_available);
      if (previous && !live.current && safe() && !controller.signal.aborted) { const restored = await getGamePlay(previous.play_id, { signal: controller.signal }); if (!live.current) accept(restored, true); }
    }).catch(caught => { if (!controller.signal.aborted && safe()) setError(caught.message); });
    void loadRecordings(controller.signal).catch(caught => { if (!controller.signal.aborted && safe()) setError(caught.message); });
    return () => {
      controller.abort(); mounted.current = false; stopSound(); void audioContext.current?.close().catch(() => undefined); audioContext.current = null; requests.current.forEach(request => request.abort()); inputQueue.current = [];
      const current = live.current;
      if (current?.status === 'running' && owner.current.token === getAuthToken()) void controlGamePlay(current, 'pause').catch(() => undefined);
    };
  }, [accept, loadRecordings, safe, stopSound]);
  useEffect(() => {
    if (owner.current.token === account) return;
    requests.current.forEach(request => request.abort()); live.current = null; setPlay(null); setSavedPlays([]); setRecordings([]); setRecording(null);
    heldSources.current.clear(); inputQueue.current = []; setHeld([]); setKeyboard(false); setGamepad(false); setConsent(false); setLabel(''); setNote(''); setRating(0); setSound(false); stopSound(); setSoundNotice(null);
    owner.current = { token: account, projectId: project.project_id }; startAttempt.current = null; recordAttempt.current = null; replayAttempt.current = null;
  }, [account, project.project_id, stopSound]);
  useEffect(() => {
    if (!play || ENDED.has(play.status)) return;
    let active = true; let timer: ReturnType<typeof setTimeout>; const controller = new AbortController();
    const poll = async () => {
      if (!active || !safe()) return;
      try { const value = await getGamePlay(play.play_id, { signal: controller.signal }); if (active) { accept(value); setConnection(''); } }
      catch (caught) { if (active && !controller.signal.aborted && safe()) {
        setConnection(caught instanceof Error ? caught.message : 'The live view is reconnecting.');
        if (caught instanceof ChatClientError && [401, 403, 404, 409, 410].includes(caught.status)) {
          inputQueue.current = []; heldSources.current.clear(); setHeld([]); setKeyboard(false); setGamepad(false);
          if (live.current) { live.current = { ...live.current, control_token: undefined, latest_frame: null, status: 'failed' }; setPlay(live.current); }
          active = false;
        }
      } }
      if (active) timer = setTimeout(() => { void poll(); }, 250);
    };
    timer = setTimeout(() => { void poll(); }, 250);
    return () => { active = false; clearTimeout(timer); controller.abort(); };
  }, [play?.play_id, play?.status, accept, safe]);
  useEffect(() => {
    const timer = setInterval(() => {
      if (!safe() || mutation.current || !heldSources.current.size || inputQueue.current.length || live.current?.capabilities?.held_buttons === false || live.current?.capabilities?.input_mode === 'one_turn_per_press') return;
      for (const action of heldSources.current.keys()) inputQueue.current.push({ action, held: true }); drain();
    }, 400);
    return () => clearInterval(timer);
  }, [drain, safe]);
  useEffect(() => {
    if (!disabled || live.current?.status !== 'running') return;
    control('pause');
  }, [disabled, control]);
  useEffect(() => {
    const leave = () => { release(); setKeyboard(false); setGamepad(false); setSound(false); stopSound(); if (live.current?.status === 'running') control('pause'); };
    const visibility = () => { if (document.visibilityState === 'hidden') leave(); };
    const subscription = AppState.addEventListener('change', state => { if (state !== 'active') leave(); });
    if (Platform.OS === 'web') { window.addEventListener('blur', leave); document.addEventListener('visibilitychange', visibility); }
    return () => { subscription.remove(); if (Platform.OS === 'web') { window.removeEventListener('blur', leave); document.removeEventListener('visibilitychange', visibility); } };
  }, [control, release, stopSound]);
  useEffect(() => {
    if (Platform.OS !== 'web' || !keyboard) return;
    const event = (value: KeyboardEvent, pressed: boolean) => {
      const target = value.target as HTMLElement | null;
      if (pressed && (target?.matches('input,textarea,select,[contenteditable="true"]') || value.ctrlKey || value.metaKey || value.altKey)) return;
      const source = 'keyboard:' + value.code;
      const actualBindings = live.current?.keyboard_bindings;
      const action = pressed ? actualBindings ? Object.entries(actualBindings).find(([action, key]) => live.current?.actions.includes(action) && (key === value.code || key === value.key))?.[0] : keyAction(value.key.length === 1 ? value.key.toLowerCase() : value.key, live.current?.actions || []) : [...heldSources.current].find(([, sources]) => sources.has(source))?.[0]; if (!action) return;
      value.preventDefault(); if (pressed && value.repeat) return; hold(action, pressed, 'keyboard:' + value.code);
    };
    const down = (value: KeyboardEvent) => event(value, true); const up = (value: KeyboardEvent) => event(value, false);
    window.addEventListener('keydown', down); window.addEventListener('keyup', up);
    return () => { window.removeEventListener('keydown', down); window.removeEventListener('keyup', up); release(); };
  }, [hold, keyboard, release]);
  useEffect(() => {
    if (Platform.OS !== 'web' || !gamepad || typeof navigator.getGamepads !== 'function') return;
    let frameId = 0; const previous = new Set<string>();
    const poll = () => {
      const pad = Array.from(navigator.getGamepads()).find(value => !!value?.connected);
      const active = pad ? padActions(pad, live.current?.actions || [], gamepadTool) : new Set<string>();
      for (const action of previous) if (!active.has(action)) hold(action, false, 'gamepad');
      for (const action of active) if (!heldSources.current.get(action)?.has('gamepad')) hold(action, true, 'gamepad');
      previous.clear(); active.forEach(action => previous.add(action)); frameId = requestAnimationFrame(poll);
    };
    frameId = requestAnimationFrame(poll);
    return () => { cancelAnimationFrame(frameId); previous.forEach(action => hold(action, false, 'gamepad')); };
  }, [gamepad, gamepadTool, hold]);
  useEffect(() => {
    if (!recording) return;
    let active = true; let timer: ReturnType<typeof setTimeout>; const controller = new AbortController();
    const poll = async () => {
      try {
        const value = await getGameRecording(recording.recording_id, { signal: controller.signal });
        if (!active || !safe()) return;
        if (['completed', 'withdrawn', 'failed'].includes(value.status)) { setRecording(null); await loadRecordings(controller.signal); return; }
        setRecording(value);
      } catch (caught) { if (active && !controller.signal.aborted && safe()) setError(caught instanceof Error ? caught.message : 'The recording status could not be loaded.'); }
      if (active) timer = setTimeout(() => { void poll(); }, 750);
    };
    timer = setTimeout(() => { void poll(); }, 750);
    return () => { active = false; clearTimeout(timer); controller.abort(); };
  }, [recording?.recording_id, safe, loadRecordings]);
  useEffect(() => {
    if (!sound || !safe() || !play || play.status !== 'running') { stopSound(); return; }
    const context = audioContext.current; const raw = play.latest_frame?.audio;
    if (!context || !raw || typeof raw !== 'object') return;
    const audio = raw as Record<string, unknown>;
    let active = true;
    void (async () => { try {
      const channels = audio.channels; const frames = audio.sample_frames; const total = audio.total_sample_frames; const rate = audio.sample_rate; const encoded = audio.samples_base64;
      if (audio.format !== 's16le' || channels !== 1 && channels !== 2 || typeof frames !== 'number' || !Number.isSafeInteger(frames) || frames < 0 || frames > 16384
        || typeof total !== 'number' || !Number.isSafeInteger(total) || total < frames || typeof rate !== 'number' || !Number.isFinite(rate) || rate < 8000 || rate > 192000
        || typeof encoded !== 'string' || encoded.length > 90000 || !/^[A-Za-z0-9+/]*={0,2}$/.test(encoded) || typeof atob !== 'function') throw new Error('The returned audio does not match the supported bounded PCM format.');
      const session = play.play_id + ':' + play.stream_id;
      if (audioSession.current !== session) { stopSound(); audioSession.current = session; void context.resume(); }
      const rawBytes = atob(encoded); if (rawBytes.length !== frames * channels * 2) throw new Error('The audio byte count does not match its measured samples.');
      if (audio.sample_start_frame !== undefined && audio.sample_start_frame !== total - frames) throw new Error('The audio cursor does not match its retained samples.');
      if (typeof audio.sample_digest === 'string') {
        const bytes = Uint8Array.from(rawBytes, character => character.charCodeAt(0));
        const hash = await digest(CryptoDigestAlgorithm.SHA256, bytes as unknown as BufferSource);
        if (Array.from(new Uint8Array(hash), byte => byte.toString(16).padStart(2, '0')).join('') !== audio.sample_digest) throw new Error('The audio sample content check failed.');
      }
      if (!active || !safe() || live.current?.stream_id !== play.stream_id || live.current?.play_id !== play.play_id || live.current?.frame_sequence !== play.frame_sequence) return;
      if (!frames || total === audioCursor.current) return;
      if (total < audioCursor.current) { stopSound(); audioSession.current = session; void context.resume(); }
      const first = total - frames; const start = Math.max(first, audioCursor.current); const count = total - start;
      if (audioCursor.current && first > audioCursor.current) setSoundNotice('Some audio samples were missed. Playing the latest actual sound.');
      if (count < 1) return;
      const buffer = context.createBuffer(channels, count, rate);
      for (let channel = 0; channel < channels; channel++) { const target = buffer.getChannelData(channel); for (let index = 0; index < count; index++) {
        const offset = (start - first + index) * channels * 2 + channel * 2; let sample = rawBytes.charCodeAt(offset) | rawBytes.charCodeAt(offset + 1) << 8;
        if (sample & 32768) sample -= 65536; target[index] = sample / 32768;
      } }
      const source = context.createBufferSource(); source.buffer = buffer; source.connect(context.destination);
      source.onended = () => { audioSources.current.delete(source); source.disconnect(); };
      const when = Math.max(context.currentTime + 0.02, audioTime.current);
      if (when > context.currentTime + 1) { audioSources.current.forEach(previous => { try { previous.stop(); } catch { /* Already stopped. */ } }); audioSources.current.clear(); audioTime.current = context.currentTime + 0.02; setSoundNotice('Audio was resynchronized to the latest actual samples.'); }
      const scheduled = Math.max(context.currentTime + 0.02, audioTime.current); audioSources.current.add(source); source.start(scheduled); audioTime.current = scheduled + count / rate; audioCursor.current = total;
    } catch (caught) { if (active && safe()) { stopSound(); setSound(false); setSoundNotice(caught instanceof Error ? caught.message : 'This audio frame could not be played.'); } } })();
    return () => { active = false; };
  }, [play?.latest_frame, play?.stream_id, play?.status, play?.play_id, sound, safe, stopSound]);
  const humanControls = play?.controller === 'human' && !!play.control_token && play.status === 'running' && !busy && !disabled;
  const playCapacityReady = !!resourceProfile && resourceProfile.available !== false && resourceProfile.max_live_plays > 0;
  const start = (controller: 'human' | 'ai') => { void run(async signal => {
    if (!playCapacityReady) throw new Error(resourceProfile?.readiness?.message || 'No live play capacity is currently available.');
    const current = projectRef.current; const config = { sourceId, seed, controller, policyId: controller === 'ai' ? current.policy_id || undefined : undefined };
    const fingerprint = JSON.stringify({ projectId: current.project_id, version: current.version, config });
    if (startAttempt.current?.fingerprint !== fingerprint) startAttempt.current = { fingerprint, key: learningRequestKey('play') };
    const value = await startGamePlay(current, config, { signal }, startAttempt.current.key); startAttempt.current = null;
    if (!signal.aborted) { accept(value, true); setKeyboard(Platform.OS === 'web' && controller === 'human'); setRecording(null); }
  }); };
  return <View style={s.section}>
    <View style={s.between}><Text accessibilityRole="header" style={s.sectionTitle}>Play the game</Text><Text style={s.badge}>{play ? human(play.status) : 'Not started'}</Text></View>
    <Text style={s.description}>Play the actual project, or watch its current learned candidate. Use the virtual pad; on the web, enable keyboard input or a connected gamepad.</Text>
    {!!error && <View style={s.alert}><Text accessibilityRole="alert" style={s.error}>{error}</Text><Button label="Dismiss" press={() => setError(null)} /></View>}
    {!!savedPlays.length && <><Text style={s.label}>Saved play sessions</Text><View style={s.chips}>{savedPlays.slice(0, 8).map((value, index) => <TouchableOpacity key={value.play_id} accessibilityRole="radio" accessibilityState={{ checked: play?.play_id === value.play_id }} disabled={busy} onPress={() => { release(); setKeyboard(false); setGamepad(false); void run(async signal => { const canonical = await getGamePlay(value.play_id, { signal }); if (!signal.aborted) accept(canonical, true); }); }} style={[s.chip, play?.play_id === value.play_id && s.selected]}><Text style={s.chipText}>Session {index + 1} · {human(value.status)}</Text></TouchableOpacity>)}</View></>}
    {!playCapacityReady && <Text style={s.unavailable}>{resourceProfile?.readiness?.message || 'Waiting for an observed live play resource profile.'}</Text>}<View style={s.observation}>{play?.latest_frame ? <GameLearningFrame frame={play.latest_frame} /> : <><Ionicons name="game-controller-outline" size={36} color={C.textDim} /><Text style={s.muted}>{play ? 'Waiting for the engine’s first frame.' : 'Start a play session to receive real engine frames.'}</Text></>}</View>
    {play && <View style={s.metrics}>{[['Steps', play.steps], ['Reward', play.reward.toLocaleString(undefined, { maximumFractionDigits: 3 })], ['Controller', human(play.controller)]].map(([name, value]) => <View style={s.metric} key={name}><Text style={s.metricValue}>{value}</Text><Text style={s.metricLabel}>{name}</Text></View>)}</View>}
    {(() => { const native = play?.latest_frame?.native_measurement; if (!native || typeof native !== 'object' || Array.isArray(native)) return null; const evidence = native as Record<string, unknown>; const values = evidence.values; if (!values || typeof values !== 'object' || Array.isArray(values) || !/^[a-f0-9]{64}$/.test(String(evidence.memory_digest)) || !/^[a-f0-9]{64}$/.test(String(evidence.layout_digest))) return null; const labels: Record<string, string> = { player_x: 'Player X', player_y: 'Player Y', health: 'Measured health', won: 'Goal reached', tick: 'Native tick', camera_x: 'Camera X', camera_y: 'Camera Y', graph_phase: 'Animation phase', goal_x: 'Goal X', goal_y: 'Goal Y', goal_visible: 'Goal visible' }; const entries = Object.entries(values as Record<string, unknown>).filter(([key, value]) => labels[key] && typeof value === 'number' && Number.isFinite(value)); return <View style={s.section}><Text accessibilityRole="header" style={s.sectionTitle}>Measured native gameplay</Text><View style={s.metrics}>{entries.map(([key, value]) => <View key={key} style={s.metric}><Text style={s.metricValue}>{key === 'won' || key === 'goal_visible' ? value === 1 ? 'Yes' : 'No' : Number(value).toLocaleString()}</Text><Text style={s.metricLabel}>{labels[key]}</Text></View>)}</View>{typeof evidence.measurement_scope === 'string' && <Text style={s.dim}>{evidence.measurement_scope}</Text>}</View>; })()}
    {!!play?.latest_frame?.hud && <View style={s.metrics}>{Object.entries(play.latest_frame.hud as Record<string, unknown>).filter(([key, value]) => ['health', 'energy', 'coins', 'day', 'season', 'weather', 'fish_caught', 'harvested'].includes(key) && (typeof value === 'number' && Number.isFinite(value) || typeof value === 'string')).map(([key, value]) => <View key={key} style={s.metric}><Text style={s.metricValue}>{typeof value === 'number' ? value.toLocaleString(undefined, { maximumFractionDigits: 1 }) : human(String(value))}</Text><Text style={s.metricLabel}>{human(key)}</Text></View>)}</View>}
    {typeof play?.latest_frame?.dialogue === 'string' && <Text style={s.notice}>{play.latest_frame.dialogue}</Text>}
    {!!connection && <Text accessibilityLiveRegion="polite" style={s.unavailable}>{connection} Held inputs expire when the connection is lost.</Text>}
    {Platform.OS === 'web' && !!play?.latest_frame?.audio && <View style={s.chips}><Button label={sound ? 'Mute game sound' : 'Enable game sound'} press={toggleSound} disabled={play.status !== 'running'} />{sound && <Text style={s.muted}>Actual engine audio</Text>}</View>}
    {!!soundNotice && <Text accessibilityLiveRegion="polite" style={s.muted}>{soundNotice}</Text>}
    {!!play?.error && <Text style={s.error}>{play.error}</Text>}
    {play?.source_id && <Text style={s.muted}>Playing source: {project.sources.find(source => source.source_id === play.source_id)?.filename || 'Selected project source'}</Text>}
    {busy && <ActivityIndicator color={C.primaryHover} />}
    <View style={s.chips}>
      {(!play || ENDED.has(play.status)) ? <>{play?.resume_available && <Button label="Resume saved play" disabled={busy || disabled || !playCapacityReady} press={() => control('resume')} />}{play && <Button label="Reset saved session" disabled={busy || disabled || !playCapacityReady} press={() => control('reset')} />}<Button label="Start playing" primary disabled={busy || disabled || !playCapacityReady} press={() => start('human')} /><Button label="Watch AI play" disabled={busy || disabled || !playCapacityReady || !project.policy_id} press={() => start('ai')} /></> : <>
        <Button label={play.status === 'paused' || play.status === 'interrupted' ? 'Resume' : 'Pause'} disabled={busy || disabled || !playCapacityReady && (play.status === 'paused' || play.status === 'interrupted')} press={() => control(play.status === 'paused' || play.status === 'interrupted' ? 'resume' : 'pause')} />
        <Button label="Reset" disabled={busy || disabled || !playCapacityReady} press={() => control('reset')} />
        <Button label="End session" disabled={busy} press={() => control('stop')} />
        {play.controller === 'ai' || !play.control_token ? <Button label="Take control" disabled={busy || disabled} press={() => control('takeover', 'human')} /> : project.policy_id && <Button label="Let AI play" disabled={busy || disabled || !!recording} press={() => control('takeover', 'ai')} />}
      </>}
    </View>
    {!!humanControls && <>
      {Platform.OS === 'web' && <View style={s.chips}><Button label={keyboard ? 'Keyboard on · arrows / WASD' : 'Enable keyboard'} primary={keyboard} press={() => { release(); setKeyboard(value => !value); }} /><Button label={gamepad ? 'Gamepad on' : 'Enable gamepad'} primary={gamepad} press={() => { release(); setGamepad(value => !value); }} /></View>}
      {play.actions.includes('fish') && play.actions.includes('rest') && <><Text style={s.label}>Tools · 1 Fish · 2 Hoe · 3 Water · 4 Plant · 5 Harvest</Text>{gamepad && <><Text style={s.muted}>Gamepad X uses the selected tool. A interacts, B attacks, and Y cycles the game’s hotbar.</Text><View style={s.chips}>{['fish', 'hoe', 'water', 'plant', 'harvest'].filter(action => play.actions.includes(action)).map(action => <Button key={action} label={human(action)} primary={gamepadTool === action} press={() => setGamepadTool(action)} />)}</View></>}<Text style={s.dim}>E interact · J attack · K fire · R rest. Tool actions come from this game’s actual controls.</Text></>}
      <View style={s.chips}>{play.actions.filter(action => play.capabilities?.input_mode === 'one_turn_per_press' || !['noop', 'none', 'idle'].includes(action)).map(action => <TouchableOpacity key={action} accessibilityRole="button"
        accessibilityLabel={`${play.capabilities?.input_mode === 'one_turn_per_press' ? 'Take one turn: ' : 'Hold '}${human(action)}`} accessibilityState={{ selected: held.includes(action) }} onPressIn={() => hold(action, true, 'touch:' + action)} onPressOut={() => hold(action, false, 'touch:' + action)}
        style={[s.button, { minWidth: 64, minHeight: 56 }, held.includes(action) && s.primaryButton]}><Text style={s.buttonText}>{play.capabilities?.input_mode === 'one_turn_per_press' && ['noop', 'none', 'idle'].includes(action) ? 'Wait one turn' : human(action)}</Text></TouchableOpacity>)}</View>
      <Text style={s.dim}>{play.capabilities?.input_mode === 'one_turn_per_press' ? 'Each press takes one measured turn. Release and press again to act; leaving controls idle does not advance this scene.' : 'Hold buttons for continuous input.'} Keyboard shortcuts only act while enabled; typing in an editor remains available.</Text>
    </>}
    {disabled && <Text style={s.unsaved}>Save your project before starting or resuming play.</Text>}
    <View style={s.divider} />
    <Text style={s.sectionTitle}>Teach by demonstration</Text>
    {recording ? <><Text style={s.description}>{recording.status === 'stopping' ? 'Saving the actual demonstration…' : 'Recording your actual actions, observations, and rewards for this project.'}</Text><Text accessibilityLiveRegion="polite" style={s.muted}>{recording.step_count ?? 0} measured steps</Text>
      <TextInput value={note} onChangeText={setNote} maxLength={2000} style={s.field} placeholder="What went well? What should Jeeves improve?" placeholderTextColor={C.textDim} accessibilityLabel="Demonstration feedback" />
      <Text style={s.label}>Rate this demonstration</Text><View style={s.chips}>{[1, 2, 3, 4, 5].map(value => <Button key={value} label={`${value} ★`} primary={rating === value} press={() => setRating(value)} />)}</View>
      <Button label="Finish and save demonstration" primary disabled={busy || recording.status === 'stopping'} press={() => { void run(async signal => {
        const value = await stopGameRecording(recording, { rating: rating || undefined, note }, { signal });
        if (!signal.aborted && safe()) { setRecording(value); setRating(0); setNote(''); if (live.current) accept(await getGamePlay(live.current.play_id, { signal })); await loadRecordings(signal); setLabel(value.label || ''); }
      }); }} />
    </> : <>
      <TextInput value={label} onChangeText={setLabel} maxLength={120} style={s.field} accessibilityLabel="Demonstration label" placeholder="Label this run (optional)" placeholderTextColor={C.textDim} />
      <TouchableOpacity accessibilityRole="checkbox" accessibilityState={{ checked: consent }} onPress={() => setConsent(value => !value)} style={s.checkbox}><View style={[s.checkboxBox, consent && s.checked]}>{consent && <Ionicons name="checkmark" size={17} color={C.text} />}</View><Text style={s.checkboxText}>Save my inputs and this game’s observations and rewards for local AI learning. I have permission to use the game source.</Text></TouchableOpacity>
      <Button label="Start recording my play" primary disabled={!humanControls || !consent || busy} press={() => { void run(async signal => {
        await serial.current; const current = live.current; if (!current) return; const fingerprint = JSON.stringify({ playId: current.play_id, version: current.control_version, label });
        if (recordAttempt.current?.fingerprint !== fingerprint) recordAttempt.current = { fingerprint, key: learningRequestKey('recording') };
        const value = await startGameRecording(current, label, { signal }, recordAttempt.current.key); recordAttempt.current = null;
        if (!signal.aborted && safe()) { setRecording(value); accept(await getGamePlay(current.play_id, { signal })); await loadRecordings(signal); }
      }); }} />
    </>}
    {!!recordings.length && <View style={{ gap: 12 }}><Text style={s.label}>Saved demonstrations</Text>{recordings.slice(0, 12).map(value => <View key={value.recording_id} style={s.source}>
      <View style={s.between}><Text style={s.projectName}>{value.label || 'Gameplay demonstration'}</Text><Text style={s.muted}>{human(value.status)}</Text></View>
      <Text style={s.muted}>{value.step_count ?? value.steps ?? '—'} recorded steps{typeof value.duration_seconds === 'number' ? ` · ${value.duration_seconds.toFixed(1)} seconds` : ''}{value.feedback?.rating ? ` · ${value.feedback.rating} / 5 feedback` : ''}</Text>
      {!!value.feedback?.note && <Text style={s.description}>{value.feedback.note}</Text>}
      {['awaiting_start', 'recording'].includes(value.status) && !recording && <Button label="Finish this recording" disabled={busy} press={() => { void run(async signal => { const updated = await stopGameRecording(value, {}, { signal }); if (!signal.aborted && safe()) { setRecording(updated); await loadRecordings(signal); } }); }} />}
      {value.status === 'completed' && <Button label="Download recorded demonstration" disabled={busy} press={() => { void run(async signal => { const file = await exportGameRecording(value.recording_id, { signal }); if (!signal.aborted && safe()) await saveLearningExport(file); }); }} />}
      {value.consent && <Button label="Withdraw learning consent" disabled={busy} press={() => setWithdrawal(value.recording_id)} />}
      {withdrawal === value.recording_id && <View style={s.alert}><Text style={s.description}>This demonstration will be blocked from future learning and replay.</Text><View style={s.chips}><Button label="Keep consent" disabled={busy} press={() => setWithdrawal(null)} /><Button label="Withdraw consent" disabled={busy} press={() => { void run(async signal => { await withdrawGameRecording(value, { signal }); if (live.current && live.current.play_id === value.play_id) accept(await getGamePlay(live.current.play_id, { signal })); if (!signal.aborted && safe()) { setWithdrawal(null); if (recording?.recording_id === value.recording_id) setRecording(null); await loadRecordings(signal); } }); }} /></View></View>}
      <Button label="Replay demonstration" disabled={busy || disabled || !playCapacityReady || !!recording || value.status !== 'completed'} press={() => { release(); void run(async signal => { await serial.current; const current = projectRef.current; const fingerprint = JSON.stringify({ projectId: current.project_id, version: current.version, recordingId: value.recording_id });
        if (replayAttempt.current?.fingerprint !== fingerprint) replayAttempt.current = { fingerprint, key: learningRequestKey('replay') };
        const replay = await replayGameRecording(current, value.recording_id, { signal }, replayAttempt.current.key); replayAttempt.current = null; if (!signal.aborted) { accept(replay, true); setKeyboard(false); setGamepad(false); } }); }} />
    </View>)}</View>}
  </View>;
}
