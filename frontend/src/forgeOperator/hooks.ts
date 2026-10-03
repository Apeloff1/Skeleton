/**
 * Data hooks for the forge-operator surface. All network calls go through
 * forgeOperator/client (not skeletonForge/client) so seal headers and engine
 * routes stay in one place. Abortable; ignores stale responses.
 */
import React from 'react';
import {
  composeVision,
  fetchBeats,
  fetchEras,
  operatorErrorFromApi,
  planBuild,
  walkPreview,
  runAppForge,
  engineRun,
  type SealHeaders,
} from './client';
import { operatorErrorFromException, type OperatorError } from './errors';
import type {
  Beat,
  BuildPlan,
  ComposeResult,
  EngineRunPayload,
  EngineRunRequest,
  EraRow,
  MaterialiseTarget,
  PlaytestMode,
  RepairMode,
  WalkPreview,
} from './types';
import type { RunPayload, RunRequest } from '../skeletonForge/types';

export type RunPhase = 'idle' | 'running' | 'done' | 'error';
export type RunSource = 'app' | 'engine' | null;

function errMessage(err: OperatorError | null): string | null {
  if (!err) return null;
  return err.message ? `${err.message} — ${err.hint}` : err.hint;
}

export interface ComposeState {
  result: ComposeResult | null;
  vision: string;
  loading: boolean;
  error: string | null;
}

/** Debounced live compose via POST /api/skeleton/compose. */
export function useOperatorCompose(vision: string, delayMs = 450): ComposeState & { refresh: () => void } {
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
      try {
        const r = await composeVision(text, { signal: ctrl.signal });
        if (ctrl.signal.aborted) return;
        if (r.ok && r.data) setState({ result: r.data, vision: text, loading: false, error: null });
        else {
          const op = operatorErrorFromApi(r, { sealed: false });
          setState((p) => ({ ...p, loading: false, error: errMessage(op) ?? `HTTP ${r.status}` }));
        }
      } catch (e) {
        if (ctrl.signal.aborted) return;
        setState((p) => ({ ...p, loading: false, error: errMessage(operatorErrorFromException(e)) }));
      }
    }, delayMs);
    return () => {
      clearTimeout(t);
      ctrl.abort();
    };
  }, [vision, delayMs, nonce]);
  return { ...state, refresh: () => setNonce((n) => n + 1) };
}

export interface OperatorCatalog {
  eras: EraRow[];
  beats: Beat[];
  loading: boolean;
  error: string | null;
  reload: () => void;
}

export function useOperatorCatalog(): OperatorCatalog {
  const [eras, setEras] = React.useState<EraRow[]>([]);
  const [beats, setBeats] = React.useState<Beat[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [nonce, setNonce] = React.useState(0);
  React.useEffect(() => {
    const ctrl = new AbortController();
    setLoading(true);
    (async () => {
      const [e, b] = await Promise.all([
        fetchEras({ signal: ctrl.signal }),
        fetchBeats({ signal: ctrl.signal }),
      ]);
      if (ctrl.signal.aborted) return;
      if (e.ok && Array.isArray(e.data?.eras)) setEras(e.data!.eras);
      if (b.ok && Array.isArray(b.data?.beats)) setBeats(b.data!.beats);
      const failed = [e, b].find((x) => !x.ok);
      setError(failed ? errMessage(operatorErrorFromApi(failed, { sealed: false })) : null);
      setLoading(false);
    })();
    return () => ctrl.abort();
  }, [nonce]);
  return { eras, beats, loading, error, reload: () => setNonce((n) => n + 1) };
}

export interface OperatorRunState {
  phase: RunPhase;
  source: RunSource;
  appPayload: RunPayload | null;
  enginePayload: EngineRunPayload | null;
  appRequest: RunRequest | null;
  engineRequest: EngineRunRequest | null;
  error: string | null;
  operatorError: OperatorError | null;
  startedAt: number | null;
  finishedAt: number | null;
}

export type AppRunOpts = {
  vision: string;
  era?: string | null;
  archetype?: string;
  target?: string;
  answers?: Record<string, string>;
};

export type EngineRunOpts = {
  vision: string;
  era?: string;
  archetype?: string;
  target: MaterialiseTarget;
  playtest: PlaytestMode;
  repair_mode: RepairMode;
  answers?: Record<string, string>;
  seal?: SealHeaders | null;
};

/** Owns one in-flight app or engine forge run. */
export function useOperatorRun() {
  const [state, setState] = React.useState<OperatorRunState>({
    phase: 'idle',
    source: null,
    appPayload: null,
    enginePayload: null,
    appRequest: null,
    engineRequest: null,
    error: null,
    operatorError: null,
    startedAt: null,
    finishedAt: null,
  });
  const ctrlRef = React.useRef<AbortController | null>(null);

  const cancel = React.useCallback(() => {
    ctrlRef.current?.abort();
    setState((p) =>
      p.phase === 'running'
        ? { ...p, phase: 'error', error: 'Cancelled', operatorError: null, finishedAt: Date.now() }
        : p,
    );
  }, []);

  const reset = React.useCallback(() => {
    ctrlRef.current?.abort();
    setState({
      phase: 'idle',
      source: null,
      appPayload: null,
      enginePayload: null,
      appRequest: null,
      engineRequest: null,
      error: null,
      operatorError: null,
      startedAt: null,
      finishedAt: null,
    });
  }, []);

  const startApp = React.useCallback(async (opts: AppRunOpts) => {
    ctrlRef.current?.abort();
    const ctrl = new AbortController();
    ctrlRef.current = ctrl;
    const req: RunRequest = {
      vision: opts.vision,
      era: opts.era ?? null,
      archetype: opts.archetype || 'auto',
      target: opts.target || 'godot',
      answers: opts.answers || {},
      include_files: false,
    };
    setState({
      phase: 'running',
      source: 'app',
      appPayload: null,
      enginePayload: null,
      appRequest: req,
      engineRequest: null,
      error: null,
      operatorError: null,
      startedAt: Date.now(),
      finishedAt: null,
    });
    try {
      const r = await runAppForge(req, { signal: ctrl.signal });
      if (ctrl.signal.aborted) return;
      if (r.ok && r.data) {
        setState((p) => ({ ...p, phase: 'done', appPayload: r.data, finishedAt: Date.now() }));
      } else {
        const op = operatorErrorFromApi(r, { sealed: false });
        setState((p) => ({
          ...p,
          phase: 'error',
          error: errMessage(op) ?? `HTTP ${r.status}`,
          operatorError: op,
          finishedAt: Date.now(),
        }));
      }
    } catch (e) {
      if (ctrl.signal.aborted) return;
      const op = operatorErrorFromException(e);
      setState((p) => ({ ...p, phase: 'error', error: errMessage(op), operatorError: op, finishedAt: Date.now() }));
    }
  }, []);

  const startEngine = React.useCallback(async (opts: EngineRunOpts) => {
    ctrlRef.current?.abort();
    const ctrl = new AbortController();
    ctrlRef.current = ctrl;
    const req: EngineRunRequest = {
      vision: opts.vision,
      era: opts.era,
      archetype: opts.archetype,
      target: opts.target,
      playtest: opts.playtest,
      repair_mode: opts.repair_mode,
      answers: opts.answers,
      include_files: false,
    };
    const seal = opts.seal ?? null;
    const sealPresent = !!(seal?.seal && String(seal.seal).trim());
    setState({
      phase: 'running',
      source: 'engine',
      appPayload: null,
      enginePayload: null,
      appRequest: null,
      engineRequest: req,
      error: null,
      operatorError: null,
      startedAt: Date.now(),
      finishedAt: null,
    });
    try {
      const r = await engineRun(req, seal, { signal: ctrl.signal });
      if (ctrl.signal.aborted) return;
      if (r.ok && r.data) {
        setState((p) => ({ ...p, phase: 'done', enginePayload: r.data, finishedAt: Date.now() }));
      } else {
        const op = operatorErrorFromApi(r, { sealed: true, sealPresent });
        setState((p) => ({
          ...p,
          phase: 'error',
          error: errMessage(op) ?? `HTTP ${r.status}`,
          operatorError: op,
          finishedAt: Date.now(),
        }));
      }
    } catch (e) {
      if (ctrl.signal.aborted) return;
      const op = operatorErrorFromException(e);
      setState((p) => ({ ...p, phase: 'error', error: errMessage(op), operatorError: op, finishedAt: Date.now() }));
    }
  }, []);

  React.useEffect(() => () => ctrlRef.current?.abort(), []);
  return { ...state, startApp, startEngine, cancel, reset };
}

export function useOperatorPlan() {
  const [plan, setPlan] = React.useState<BuildPlan | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const ctrlRef = React.useRef<AbortController | null>(null);

  const run = React.useCallback(async (vision: string, era?: string | null) => {
    ctrlRef.current?.abort();
    const ctrl = new AbortController();
    ctrlRef.current = ctrl;
    setLoading(true);
    setError(null);
    try {
      const r = await planBuild({ vision: vision || undefined, era: era || null }, { signal: ctrl.signal });
      if (ctrl.signal.aborted) return;
      if (r.ok && r.data) {
        setPlan(r.data);
        setLoading(false);
      } else {
        setPlan(null);
        setError(errMessage(operatorErrorFromApi(r, { sealed: false })) ?? `HTTP ${r.status}`);
        setLoading(false);
      }
    } catch (e) {
      if (ctrl.signal.aborted) return;
      setPlan(null);
      setError(errMessage(operatorErrorFromException(e)));
      setLoading(false);
    }
  }, []);

  React.useEffect(() => () => ctrlRef.current?.abort(), []);
  return { plan, loading, error, run };
}

/** Ticking clock while `active` (for elapsed-time readouts). */
export function useNow(active: boolean, everyMs = 500): number {
  const [now, setNow] = React.useState(() => Date.now());
  React.useEffect(() => {
    if (!active) return undefined;
    setNow(Date.now());
    const id = setInterval(() => setNow(Date.now()), everyMs);
    return () => clearInterval(id);
  }, [active, everyMs]);
  return now;
}

export function useOperatorWalk() {
  const [preview, setPreview] = React.useState<WalkPreview | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const ctrlRef = React.useRef<AbortController | null>(null);

  const run = React.useCallback(async (vision: string, era?: string | null) => {
    ctrlRef.current?.abort();
    const ctrl = new AbortController();
    ctrlRef.current = ctrl;
    setLoading(true);
    setError(null);
    try {
      const r = await walkPreview({ vision: vision || undefined, era: era || null }, { signal: ctrl.signal });
      if (ctrl.signal.aborted) return;
      if (r.ok && r.data) {
        setPreview(r.data);
        setLoading(false);
      } else {
        setPreview(null);
        setError(errMessage(operatorErrorFromApi(r, { sealed: false })) ?? `HTTP ${r.status}`);
        setLoading(false);
      }
    } catch (e) {
      if (ctrl.signal.aborted) return;
      setPreview(null);
      setError(errMessage(operatorErrorFromException(e)));
      setLoading(false);
    }
  }, []);

  React.useEffect(() => () => ctrlRef.current?.abort(), []);
  return { preview, loading, error, run };
}
