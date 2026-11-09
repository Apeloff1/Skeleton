/**
 * Cockpit console hook: sends verbs to POST /api/skeleton/cockpit, keeps a
 * bounded newest-first transcript and ignores responses from superseded
 * commands.
 */
import React from 'react';
import { errorText, sendCockpit } from './client';
import { checkCommand, pushEntry, summarizeCockpit, type ConsoleEntry } from './cockpit';

export interface CockpitConsoleState {
  entries: ConsoleEntry[];
  busy: boolean;
  submit: (raw: string) => Promise<ConsoleEntry | null>;
  clear: () => void;
}

export function useCockpitConsole(max = 40): CockpitConsoleState {
  const [entries, setEntries] = React.useState<ConsoleEntry[]>([]);
  const [busy, setBusy] = React.useState(false);
  const seq = React.useRef(0);
  const ctrlRef = React.useRef<AbortController | null>(null);

  const submit = React.useCallback(async (raw: string) => {
    const check = checkCommand(raw);
    if (!check.ok) return null;
    ctrlRef.current?.abort();
    const ctrl = new AbortController();
    ctrlRef.current = ctrl;
    const id = ++seq.current;
    setBusy(true);
    const r = await sendCockpit(check.command, ctrl.signal);
    if (ctrl.signal.aborted) return null;
    const ok = !!(r.ok && r.data);
    const entry: ConsoleEntry = {
      id,
      command: check.command,
      ok,
      summary: ok ? summarizeCockpit(check.command, r.data) : errorText(r),
      result: ok ? r.data : null,
      at: Date.now(),
    };
    setEntries((log) => pushEntry(log, entry, max));
    setBusy(false);
    return entry;
  }, [max]);

  const clear = React.useCallback(() => setEntries([]), []);
  React.useEffect(() => () => ctrlRef.current?.abort(), []);
  return { entries, busy, submit, clear };
}
