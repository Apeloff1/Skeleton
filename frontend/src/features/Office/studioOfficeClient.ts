/**
 * Studio office client. The engine owns the golden brief; this module never
 * sends a replacement brief. Seal and tenant travel as headers, matching the
 * forge build route.
 */

export type OfficeCharter = {
  charter_id: string;
  mandate: string;
  tools: string[];
  autonomy: 'act' | 'advise' | string;
  budget: { max_tool_calls: number; deadline_s: number };
};

export type OfficeStep = {
  index: number;
  tool: string;
  status: string;
  thought: string;
  output?: Record<string, unknown>;
};

export type OfficeRun = {
  schema_version?: string;
  run_id: string;
  charter_id?: string;
  status: string;
  mandate?: string;
  autonomy?: string;
  heartbeat_seq?: number;
  steps?: OfficeStep[];
  result?: Record<string, unknown> | null;
  error?: { code?: string; codes?: unknown } | null;
  status_ref?: string;
  stream_ref?: string;
  brief_id?: string | null;
  playtest?: string | null;
};

export type OfficePhase = 'idle' | 'loading' | 'ready' | 'error';

export type OfficeSnapshot = {
  seal: string;
  tenant: string;
  phase: OfficePhase;
  error: string;
  charters: OfficeCharter[];
  chartersPhase: OfficePhase;
  run: OfficeRun | null;
  trace: string[];
};

export type OfficeHeadline = {
  tone: 'empty' | 'loading' | 'error' | 'running' | 'ok' | 'degraded' | 'failed';
  title: string;
  detail: string;
};

const TERMINAL = new Set(['succeeded', 'failed', 'cancelled']);

export function officeUrl(base: string, path: string): string {
  const root = String(base || '').replace(/\/+$/, '');
  const suffix = path.startsWith('/') ? path : `/${path}`;
  return `${root}${suffix}`;
}

export function officeHeaders(seal: string, tenant: string): Record<string, string> {
  const headers: Record<string, string> = {
    'content-type': 'application/json',
    'x-skeleton-tenant': tenant.trim() || 'default',
  };
  const token = seal.trim();
  if (token) headers['x-gf-seal'] = token;
  return headers;
}

/** The server selects the ash-tunnels brief. Do not send a brief body. */
export function goldenRequestBody(frames = 4): Record<string, unknown> {
  return { frames, live: false };
}

export function parseOfficeSse(buffer: string): { events: Record<string, unknown>[]; rest: string } {
  const chunks = buffer.split('\n\n');
  const rest = chunks.pop() ?? '';
  const events: Record<string, unknown>[] = [];
  for (const chunk of chunks) {
    const data = chunk
      .split('\n')
      .filter((line) => line.startsWith('data:'))
      .map((line) => line.slice(5).trim())
      .join('\n');
    if (!data) continue;
    try {
      const parsed = JSON.parse(data) as Record<string, unknown>;
      if (parsed && typeof parsed === 'object') events.push(parsed);
    } catch {
      events.push({ type: 'operation.failed', payload: { code: 'stream_unreadable' } });
    }
  }
  return { events, rest };
}

function codesFrom(run: OfficeRun | null): string[] {
  const result = run?.result;
  const fromResult = result && Array.isArray(result.codes) ? result.codes.filter((item) => typeof item === 'string') : [];
  const fromError = run?.error && Array.isArray(run.error.codes) ? run.error.codes.filter((item) => typeof item === 'string') : [];
  return [...fromResult, ...fromError].slice(0, 12) as string[];
}

export function officeHeadline(snapshot: Pick<OfficeSnapshot, 'phase' | 'error' | 'run'>): OfficeHeadline {
  if (snapshot.phase === 'error') {
    return { tone: 'error', title: 'Office request failed', detail: snapshot.error || 'The office returned an error.' };
  }
  const run = snapshot.run;
  if (!run) {
    if (snapshot.phase === 'loading') {
      return { tone: 'loading', title: 'Starting office run', detail: 'Waiting for the forge charter to accept the run.' };
    }
    return { tone: 'empty', title: 'No office run yet', detail: 'Load charters, then run the ash-tunnels golden brief or pick an office.' };
  }
  if (!TERMINAL.has(run.status) || snapshot.phase === 'loading') {
    const last = run.steps && run.steps.length ? run.steps[run.steps.length - 1] : null;
    return {
      tone: 'running',
      title: `${run.charter_id || 'office'} · ${run.status}`,
      detail: last?.thought || 'Waiting for the next tool step.',
    };
  }
  if (run.status === 'cancelled') {
    return { tone: 'failed', title: 'Run cancelled', detail: 'The office stopped before claiming a result.' };
  }
  if (run.status === 'failed') {
    const code = run.error?.code || 'failed';
    const codes = codesFrom(run);
    return {
      tone: 'failed',
      title: code === 'doctor_red' ? 'Doctor is red' : `Run failed · ${code}`,
      detail: codes.length ? `Doctor codes: ${codes.join(', ')}` : 'The office did not invent a successful build.',
    };
  }
  const result = run.result || {};
  if (result.core_loop_ok === true) {
    return { tone: 'ok', title: 'CORE_LOOP_OK', detail: 'Godot booted the project and printed the core-loop marker.' };
  }
  if (result.degraded === true || result.godot_ran === false) {
    const reason = typeof result.degraded_reason === 'string' ? result.degraded_reason : 'missing-godot-binary';
    return {
      tone: 'degraded',
      title: 'Godot did not run',
      detail: `Degraded playtest auto path (${reason}). The compiler marker is not an engine boot.`,
    };
  }
  return { tone: 'ok', title: 'Run succeeded', detail: 'The office finished with the tool output on the trace.' };
}

export function traceFromRun(run: OfficeRun | null): string[] {
  if (!run?.steps) return [];
  return run.steps.map((step) => step.thought).filter((thought) => Boolean(thought));
}

type FetchLike = (input: string, init?: RequestInit) => Promise<Response>;

const emptySnapshot = (): OfficeSnapshot => ({
  seal: '',
  tenant: 'default',
  phase: 'idle',
  error: '',
  charters: [],
  chartersPhase: 'idle',
  run: null,
  trace: [],
});

export class OfficeController {
  readonly base: string;
  private readonly fetchImpl: FetchLike;
  private snapshot: OfficeSnapshot = emptySnapshot();
  private readonly listeners = new Set<() => void>();
  private watchToken = 0;

  constructor(options: { base: string; fetchImpl?: FetchLike }) {
    this.base = options.base;
    this.fetchImpl = options.fetchImpl || ((input, init) => fetch(input, init));
  }

  subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  getSnapshot = () => this.snapshot;

  setSeal(seal: string) {
    this.patch({ seal });
  }

  setTenant(tenant: string) {
    this.patch({ tenant: tenant.trim() || 'default' });
  }

  async loadCharters() {
    this.patch({ chartersPhase: 'loading', error: '' });
    const response = await this.request('/api/v1/game/office/charters');
    if (!response.ok) {
      this.patch({ chartersPhase: 'error', error: response.error, charters: [] });
      return;
    }
    const charters = Array.isArray(response.body.charters) ? response.body.charters as OfficeCharter[] : [];
    this.patch({ chartersPhase: 'ready', charters, error: '' });
  }

  async startGolden() {
    await this.start('/api/v1/game/office/golden', goldenRequestBody());
  }

  async startCharter(charterId: string, params: Record<string, unknown> = {}) {
    await this.start('/api/v1/game/office/runs', { charter_id: charterId, ...params });
  }

  async cancel() {
    const run = this.snapshot.run;
    if (!run?.run_id) return;
    const response = await this.request(`/api/v1/game/office/runs/${encodeURIComponent(run.run_id)}/cancel`, { method: 'POST', body: '{}' });
    if (!response.ok) {
      this.patch({ phase: 'error', error: response.error });
      return;
    }
    this.patch({ phase: 'ready', run: response.body as OfficeRun, trace: traceFromRun(response.body as OfficeRun), error: '' });
  }

  private async start(path: string, body: Record<string, unknown>) {
    if (!this.snapshot.seal.trim()) {
      this.patch({ phase: 'error', error: 'Paste the forge seal. The office does not accept an unauthenticated mutation.' });
      return;
    }
    const token = ++this.watchToken;
    this.patch({ phase: 'loading', error: '', trace: [] });
    const response = await this.request(path, { method: 'POST', body: JSON.stringify(body) });
    if (token !== this.watchToken) return;
    if (!response.ok) {
      this.patch({ phase: 'error', error: response.error });
      return;
    }
    const run = response.body as OfficeRun;
    this.patch({ run, trace: traceFromRun(run) });
    await this.follow(run.run_id, token);
  }

  private async follow(runId: string, token: number) {
    const stream = await this.request(`/api/v1/game/office/runs/${encodeURIComponent(runId)}/stream`);
    if (token !== this.watchToken) return;
    if (stream.ok && stream.raw && stream.raw.body) {
      await this.readStream(stream.raw, token);
      return;
    }
    await this.poll(runId, token);
  }

  private async readStream(response: Response, token: number) {
    const reader = response.body?.getReader();
    if (!reader) {
      await this.poll(this.snapshot.run?.run_id || '', token);
      return;
    }
    const decoder = new TextDecoder();
    let buffer = '';
    while (token === this.watchToken) {
      const chunk = await reader.read();
      if (chunk.done) break;
      buffer += decoder.decode(chunk.value, { stream: true });
      const parsed = parseOfficeSse(buffer);
      buffer = parsed.rest;
      if (parsed.events.length) {
        const trace = [...this.snapshot.trace];
        for (const event of parsed.events) {
          const payload = event.payload;
          const thought = payload && typeof payload === 'object' ? String((payload as { thought?: string }).thought || (payload as { message?: string }).message || '') : '';
          if (thought) trace.push(thought);
        }
        this.patch({ trace: trace.slice(-40) });
      }
    }
    if (token === this.watchToken && this.snapshot.run?.run_id) await this.poll(this.snapshot.run.run_id, token);
  }

  private async poll(runId: string, token: number) {
    if (!runId) return;
    for (let attempt = 0; attempt < 40 && token === this.watchToken; attempt += 1) {
      const response = await this.request(`/api/v1/game/office/runs/${encodeURIComponent(runId)}`);
      if (token !== this.watchToken) return;
      if (!response.ok) {
        this.patch({ phase: 'error', error: response.error });
        return;
      }
      const run = response.body as OfficeRun;
      this.patch({ phase: TERMINAL.has(run.status) ? 'ready' : 'loading', run, trace: traceFromRun(run), error: '' });
      if (TERMINAL.has(run.status)) return;
      await new Promise((resolve) => setTimeout(resolve, 250));
    }
  }

  private async request(path: string, init: { method?: string; body?: string } = {}) {
    try {
      const raw = await this.fetchImpl(officeUrl(this.base, path), {
        method: init.method || 'GET',
        headers: officeHeaders(this.snapshot.seal, this.snapshot.tenant),
        body: init.body,
      });
      if (path.endsWith('/stream')) {
        if (!raw.ok) {
          const text = await raw.text();
          return { ok: false as const, error: officeFailure(raw.status, text ? { detail: text.slice(0, 240) } : {}), body: {}, raw };
        }
        return { ok: true as const, error: '', body: {}, raw };
      }
      const text = await raw.text();
      let body: Record<string, unknown> = {};
      if (text) {
        try { body = JSON.parse(text) as Record<string, unknown>; } catch { body = { detail: text.slice(0, 240) }; }
      }
      if (!raw.ok) return { ok: false as const, error: officeFailure(raw.status, body), body, raw };
      return { ok: true as const, error: '', body, raw };
    } catch {
      return { ok: false as const, error: 'Office unreachable on the Skeleton engine port.', body: {}, raw: undefined };
    }
  }

  private patch(next: Partial<OfficeSnapshot>) {
    this.snapshot = { ...this.snapshot, ...next };
    for (const listener of this.listeners) listener();
  }
}

export function officeFailure(status: number, body: Record<string, unknown>): string {
  const detail = body.detail ?? body.error ?? body.message;
  if (detail && typeof detail === 'object' && detail && 'error' in detail) {
    const code = String((detail as { error?: string }).error || '');
    if (code === 'charter_denied') return 'Charter denied. The forge run charter did not admit this actor.';
    if (code === 'office_loopback_only') return 'The office refused a non-loopback client.';
    if (code) return code;
  }
  if (status === 401) return 'Charter seal missing or rejected.';
  if (status === 403) return 'Charter denied.';
  if (typeof detail === 'string' && detail) return detail;
  return `Office returned HTTP ${status}.`;
}
