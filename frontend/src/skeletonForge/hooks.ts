/**
 * Data hooks for the Skeleton cockpit. All requests are abortable and
 * ignore stale responses so fast typing never shows an older composition.
 */
import React from 'react';
import { getAuthEpoch, subscribeAuthChanges } from '../auth/gameforgeAuth';
import { composeVision, errorText, fetchBeats, fetchEras, fetchGenerations, runForge } from './client';
import { FALLBACK_BEATS } from './questionnaire';
import type { Beat, ComposeResult, EraRow, GenerationRow, RunPayload, RunRequest } from './types';

export interface ComposeState {
  result: ComposeResult | null;
  /** Vision text the current `result` belongs to. */
  vision: string;
  loading: boolean;
  error: string | null;
}

/** Debounced live compose preview for `vision`. */
export function useLiveCompose(vision: string, delayMs = 450): ComposeState & { refresh: () => void } {
  const [state, setState] = React.useState<ComposeState>({ result: null, vision: '', loading: false, error: null });
  const [nonce, setNonce] = React.useState(0);
  React.useEffect(() => {
    const text = vision.trim();
    if (!text) {
      setState({ result: null, vision: '', loading: false, error: null });
      return undefined;
    }
    const ctrl = new AbortController();
    setState((p) => ({ ...p, loading: true }));
    const t = setTimeout(async () => {
      const r = await composeVision(text, ctrl.signal);
      if (ctrl.signal.aborted) return;
      if (r.ok && r.data) setState({ result: r.data, vision: text, loading: false, error: null });
      else setState((p) => ({ ...p, loading: false, error: errorText(r) }));
    }, delayMs);
    return () => {
      clearTimeout(t);
      ctrl.abort();
    };
  }, [vision, delayMs, nonce]);
  return { ...state, refresh: () => setNonce((n) => n + 1) };
}

export interface Catalog {
  beats: Beat[];
  beatsLive: boolean;
  eras: EraRow[];
  generations: GenerationRow[];
  loading: boolean;
  error: string | null;
  reload: () => void;
}

/** Beats, eras and hardware generations; beats fall back to the offline copy. */
export function useForgeCatalog(): Catalog {
  const [beats, setBeats] = React.useState<Beat[]>(FALLBACK_BEATS);
  const [beatsLive, setBeatsLive] = React.useState(false);
  const [eras, setEras] = React.useState<EraRow[]>([]);
  const [generations, setGenerations] = React.useState<GenerationRow[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [nonce, setNonce] = React.useState(0);
  React.useEffect(() => {
    const ctrl = new AbortController();
    setLoading(true);
    (async () => {
      const [b, e, g] = await Promise.all([fetchBeats(ctrl.signal), fetchEras(ctrl.signal), fetchGenerations(ctrl.signal)]);
      if (ctrl.signal.aborted) return;
      if (b.ok && Array.isArray(b.data?.beats) && b.data!.beats.length) {
        setBeats(b.data!.beats);
        setBeatsLive(true);
      }
      if (e.ok && Array.isArray(e.data?.eras)) setEras(e.data!.eras);
      if (g.ok && Array.isArray(g.data?.generations)) setGenerations(g.data!.generations);
      const failed = [b, e, g].find((x) => !x.ok);
      setError(failed ? errorText(failed) : null);
      setLoading(false);
    })();
    return () => ctrl.abort();
  }, [nonce]);
  return { beats, beatsLive, eras, generations, loading, error, reload: () => setNonce((n) => n + 1) };
}

export type RunPhase = 'idle' | 'running' | 'done' | 'error';

export interface ForgeRunState {
  phase: RunPhase;
  payload: RunPayload | null;
  request: RunRequest | null;
  error: string | null;
  startedAt: number | null;
  finishedAt: number | null;
}

/** One active run belongs to exactly one local authentication epoch. */
export function currentForgeRun(
  startedEpoch: number, activeEpoch: number,
  requestId: number, activeRequestId: number, aborted: boolean,
): boolean {
  return !aborted && startedEpoch === activeEpoch && requestId === activeRequestId;
}

function emptyForgeRun(): ForgeRunState {
  return {
    phase: 'idle', payload: null, request: null, error: null,
    startedAt: null, finishedAt: null,
  };
}

/** Cancellable, account-scoped run with at-most-one accepted response. */
export function useForgeRun() {
  const [state, setState] = React.useState<ForgeRunState>(emptyForgeRun);
  const ctrlRef = React.useRef<AbortController | null>(null);
  const requestIdRef = React.useRef(0);

  const invalidate = React.useCallback(() => {
    requestIdRef.current += 1;
    ctrlRef.current?.abort();
    ctrlRef.current = null;
    // No completed source file or authored vision survives an account change.
    setState(emptyForgeRun());
  }, []);

  React.useEffect(() => {
    const unsubscribe = subscribeAuthChanges(invalidate);
    return () => {
      unsubscribe();
      requestIdRef.current += 1;
      ctrlRef.current?.abort();
      ctrlRef.current = null;
    };
  }, [invalidate]);

  const start = React.useCallback(async (req: RunRequest) => {
    ctrlRef.current?.abort();
    const ctrl = new AbortController();
    ctrlRef.current = ctrl;
    const requestId = ++requestIdRef.current;
    const startedEpoch = getAuthEpoch();
    setState({
      phase: 'running', payload: null, request: req, error: null,
      startedAt: Date.now(), finishedAt: null,
    });
    try {
      const r = await runForge(req, ctrl.signal);
      if (!currentForgeRun(startedEpoch, getAuthEpoch(), requestId,
        requestIdRef.current, ctrl.signal.aborted)) return;
      if (r.ok && r.data) {
        setState((p) => ({
          ...p, phase: 'done', payload: r.data, finishedAt: Date.now(),
        }));
      } else {
        setState((p) => ({
          ...p, phase: 'error', payload: null, error: errorText(r),
          finishedAt: Date.now(),
        }));
      }
    } catch {
      if (!currentForgeRun(startedEpoch, getAuthEpoch(), requestId,
        requestIdRef.current, ctrl.signal.aborted)) return;
      setState((p) => ({
        ...p, phase: 'error', payload: null,
        error: 'GameForge run could not be completed.',
        finishedAt: Date.now(),
      }));
    } finally {
      if (ctrlRef.current === ctrl) ctrlRef.current = null;
    }
  }, []);

  const cancel = React.useCallback(() => {
    requestIdRef.current += 1;
    ctrlRef.current?.abort();
    ctrlRef.current = null;
    setState((p) => (p.phase === 'running'
      ? {
        ...p, phase: 'error', payload: null, error: 'Cancelled',
        finishedAt: Date.now(),
      }
      : p));
  }, []);

  return { ...state, start, cancel };
}

/** Ticking clock while `active` (for elapsed-time readouts). */
export function useNow(active: boolean, everyMs = 500): number {
  const [now, setNow] = React.useState(() => Date.now());
  React.useEffect(() => {
    if (!active) return undefined;
    const id = setInterval(() => setNow(Date.now()), everyMs);
    return () => clearInterval(id);
  }, [active, everyMs]);
  return now;
}
