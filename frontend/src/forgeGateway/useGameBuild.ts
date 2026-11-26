/**
 * Start a gateway build and follow it to completion. Polling stops on unmount,
 * on a terminal status, or when the caller resets; a retried start reuses the
 * same idempotency key so it can never create a duplicate build.
 */
import React from 'react';
import { getGameBuild, startGameBuild } from './client';
import {
  type BuildSummary, type BuildView, type Playtest,
  gatewayErrorMessage, isTerminal, newIdempotencyKey, nextPollDelay, summarise,
} from './model';

export type GameBuildState =
  | { kind: 'idle' }
  | { kind: 'starting' }
  | { kind: 'tracking'; executionId: string; summary: BuildSummary; transientError: string | null }
  | { kind: 'done'; executionId: string; summary: BuildSummary; view: BuildView }
  | { kind: 'error'; message: string; status: number; retryable: boolean };

const sleep = (ms: number, signal: AbortSignal) => new Promise<void>((resolve) => {
  const timer = setTimeout(resolve, ms);
  signal.addEventListener('abort', () => { clearTimeout(timer); resolve(); }, { once: true });
});

export function useGameBuild(initialExecutionId?: string | null) {
  const [state, setState] = React.useState<GameBuildState>({ kind: 'idle' });
  const controller = React.useRef<AbortController | null>(null);
  const pendingKey = React.useRef<string | null>(null);

  const stop = React.useCallback(() => { controller.current?.abort(); controller.current = null; }, []);
  React.useEffect(() => stop, [stop]);

  const follow = React.useCallback(async (executionId: string) => {
    stop();
    const ctl = new AbortController();
    controller.current = ctl;
    let attempt = 0;
    let failures = 0;
    setState({ kind: 'tracking', executionId, summary: summarise(null), transientError: null });
    while (!ctl.signal.aborted) {
      const res = await getGameBuild(executionId, ctl.signal);
      if (ctl.signal.aborted) return;
      if (res.ok && res.data) {
        failures = 0;
        const summary = summarise(res.data);
        if (isTerminal(res.data.status)) {
          setState({ kind: 'done', executionId, summary, view: res.data });
          return;
        }
        setState({ kind: 'tracking', executionId, summary, transientError: null });
      } else if (res.status === 404 || res.status === 401 || res.status === 403) {
        setState({ kind: 'error', status: res.status, retryable: false, message: gatewayErrorMessage(res.status, res.error) });
        return;
      } else {
        failures += 1;
        const message = gatewayErrorMessage(res.status, res.error);
        if (failures >= 8) { setState({ kind: 'error', status: res.status, retryable: true, message }); return; }
        setState((prev) => prev.kind === 'tracking' ? { ...prev, transientError: `${message} Still checking…` } : prev);
      }
      await sleep(nextPollDelay(attempt++), ctl.signal);
    }
  }, [stop]);

  const start = React.useCallback(async (brief: string, playtest: Playtest) => {
    stop();
    const ctl = new AbortController();
    controller.current = ctl;
    pendingKey.current = pendingKey.current ?? newIdempotencyKey();
    setState({ kind: 'starting' });
    const res = await startGameBuild({ brief, playtest, idempotencyKey: pendingKey.current, signal: ctl.signal });
    if (ctl.signal.aborted) return null;
    if (!res.ok || !res.data?.execution_id) {
      const retryable = res.status === 0 || res.status >= 500 || res.status === 429;
      if (!retryable) pendingKey.current = null;
      setState({ kind: 'error', status: res.status, retryable, message: gatewayErrorMessage(res.status, res.error) });
      return null;
    }
    pendingKey.current = null;
    void follow(res.data.execution_id);
    return res.data.execution_id;
  }, [follow, stop]);

  const reset = React.useCallback(() => { stop(); pendingKey.current = null; setState({ kind: 'idle' }); }, [stop]);

  React.useEffect(() => {
    if (initialExecutionId) void follow(initialExecutionId);
  }, [initialExecutionId, follow]);

  return { state, start, follow, reset };
}
