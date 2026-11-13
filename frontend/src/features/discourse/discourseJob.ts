/** Account-scoped Discourse job admission and bounded polling.
 *
 * Every HTTP request goes through the shared authenticated apiClient, which
 * fences account-session changes and forwards AbortSignal. Cancelling the
 * observer NEVER claims to cancel an already admitted server job.
 */

export interface DiscourseCandidate {
  model: string;
  content: string;
  provider?: string;
  critique?: string;
  quality?: number;
  fidelity?: number;
  score?: number;
  rationale?: string;
}

export interface DiscourseResult {
  winner_index: number;
  winner_model: string;
  winner_content: string;
  winner_score?: number;
  judge_model: string;
  judge_why?: string;
  judge_status?: string;
  deliberation_mode?: string;
  provider_diverse?: boolean;
  independent_judge?: boolean;
  selection_source?: string;
  panel: string[];
  candidates: DiscourseCandidate[];
}

interface WireResult<T> {
  ok: boolean;
  status: number;
  data: T | null;
  error: string | null;
}

interface RequestOptions {
  signal?: AbortSignal;
  timeoutMs?: number;
  retries?: number;
}

export interface DiscourseTransport {
  get<T>(path: string, options?: RequestOptions): Promise<WireResult<T>>;
  post<T>(path: string, body: unknown, options?: RequestOptions): Promise<WireResult<T>>;
}

export interface PollOptions {
  signal?: AbortSignal;
  onProgress?: (progress: { status: 'submitting' | 'running'; jobId: string | null; attempts: number }) => void;
  maxWaitMs?: number;
  pollIntervalMs?: number;
}

export type DiscourseOutcome =
  | { ok: true; jobId: string; result: DiscourseResult }
  | { ok: false; jobId: string | null; error: string; recoverable: boolean };

interface JobWire {
  status?: unknown;
  job_id?: unknown;
  error?: unknown;
  winner_index?: unknown;
  winner_model?: unknown;
  winner_content?: unknown;
  winner_score?: unknown;
  judge_model?: unknown;
  judge_why?: unknown;
  judge_status?: unknown;
  deliberation_mode?: unknown;
  provider_diverse?: unknown;
  independent_judge?: unknown;
  selection_source?: unknown;
  panel?: unknown;
  candidates?: unknown;
}

const JOB_ID_PATTERN = /^[a-f0-9]{32}$/;
export const MAX_DISCOURSE_WAIT_MS = 240_000;
const MAX_OBSERVATIONS = 120;
const MAX_TRANSIENT_ERRORS = 3;

function failure(error: string, jobId: string | null = null, recoverable = false): DiscourseOutcome {
  return { ok: false, jobId, error, recoverable };
}

function boundedMessage(value: unknown, fallback: string): string {
  return typeof value === 'string' && value.trim().length
    ? value.trim().slice(0, 256)
    : fallback;
}

// The API is trusted for account authority, not for render-safe JSON types.
// Backend output is capped at 12k Unicode codepoints; 24k UTF-16 units also
// accommodates astral characters without rejecting valid model responses.
function safeOptionalText(value: unknown, maxUnits: number): boolean {
  return value == null || (typeof value === 'string' && value.length <= maxUnits);
}

function safeOptionalScore(value: unknown): boolean {
  return value == null || (
    typeof value === 'number' && Number.isFinite(value) &&
    value >= 0 && value <= 100
  );
}

function validResult(record: JobWire): DiscourseResult | null {
  const rows = record.candidates;
  if (
    !Array.isArray(rows) || rows.length < 1 || rows.length > 5 ||
    !Number.isInteger(record.winner_index) ||
    (record.winner_index as number) < 0 ||
    (record.winner_index as number) >= rows.length ||
    typeof record.winner_model !== 'string' || !record.winner_model ||
    record.winner_model.length > 2048 ||
    typeof record.winner_content !== 'string' || !record.winner_content.trim() ||
    record.winner_content.length > 24_000 ||
    typeof record.judge_model !== 'string' || !record.judge_model ||
    record.judge_model.length > 2048 ||
    !safeOptionalScore(record.winner_score) ||
    !safeOptionalText(record.judge_why, 2_000) ||
    !Array.isArray(record.panel) || !record.panel.length || record.panel.length > 5 ||
    !record.panel.every((item: unknown) =>
      typeof item === 'string' && item.length > 0 && item.length <= 2048
    ) ||
    !rows.every((item: unknown) => {
      if (!item || typeof item !== 'object') return false;
      const candidate = item as DiscourseCandidate;
      return typeof candidate.model === 'string' && candidate.model.length > 0 &&
        candidate.model.length <= 2048 &&
        typeof candidate.content === 'string' && candidate.content.length <= 24_000 &&
        safeOptionalScore(candidate.quality) && safeOptionalScore(candidate.fidelity) &&
        safeOptionalScore(candidate.score) &&
        safeOptionalText(candidate.critique, 4_000);
    }) ||
    rows[record.winner_index as number].model !== record.winner_model ||
    rows[record.winner_index as number].content !== record.winner_content
  ) return null;
  return record as unknown as DiscourseResult;
}

function delayWithAbort(ms: number, signal?: AbortSignal): Promise<boolean> {
  if (signal?.aborted) return Promise.resolve(false);
  return new Promise(resolve => {
    let settled = false;
    const finish = (completed: boolean) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      signal?.removeEventListener('abort', abort);
      resolve(completed);
    };
    const abort = () => finish(false);
    const timer = setTimeout(() => finish(true), ms);
    signal?.addEventListener('abort', abort, { once: true });
    if (signal?.aborted) finish(false);
  });
}

/** Re-observe a known private job without ever submitting a replacement. */
export async function pollDiscourseJob(
  transport: DiscourseTransport, jobId: string, options: PollOptions = {},
): Promise<DiscourseOutcome> {
  if (typeof jobId !== 'string' || !JOB_ID_PATTERN.test(jobId)) {
    return failure('invalid_job_receipt');
  }
  const maxWait = typeof options.maxWaitMs === 'number' &&
    Number.isFinite(options.maxWaitMs) && options.maxWaitMs >= 100
    ? Math.min(MAX_DISCOURSE_WAIT_MS, options.maxWaitMs) : MAX_DISCOURSE_WAIT_MS;
  const interval = typeof options.pollIntervalMs === 'number' &&
    Number.isFinite(options.pollIntervalMs) && options.pollIntervalMs >= 10
    ? Math.min(10_000, options.pollIntervalMs) : 1_500;
  const deadline = Date.now() + maxWait;
  let transientErrors = 0;

  for (let attempts = 1; attempts <= MAX_OBSERVATIONS; attempts++) {
    if (options.signal?.aborted) return failure('observation_cancelled', jobId, true);
    const remaining = deadline - Date.now();
    if (remaining <= 0) return failure('job_observation_timeout', jobId, true);
    options.onProgress?.({ status: 'running', jobId, attempts });
    let response: WireResult<JobWire>;
    try {
      response = await transport.get<JobWire>(
        '/api/discourse/result/' + jobId,
        {
          signal: options.signal,
          timeoutMs: Math.max(100, Math.min(8_000, remaining)),
          retries: 0,
        },
      );
    } catch {
      response = { ok: false, status: 0, data: null, error: 'network_error' };
    }
    if (options.signal?.aborted) return failure('observation_cancelled', jobId, true);
    if (!response.ok) {
      if (![0, 429, 502, 503, 504].includes(response.status)) {
        return failure(boundedMessage(response.error, 'job_observation_rejected'), jobId);
      }
      transientErrors++;
      if (transientErrors > MAX_TRANSIENT_ERRORS) {
        return failure('job_observation_temporarily_unavailable', jobId, true);
      }
    } else {
      transientErrors = 0;
      const record = response.data;
      if (!record || typeof record !== 'object') return failure('invalid_job_record', jobId);
      if (record.status === 'done') {
        // Never display a terminal receipt for another job, or a terminal
        // failure masquerading as a successful durable deliberation.
        if (record.job_id !== jobId || record.error != null) {
          return failure('invalid_terminal_result', jobId);
        }
        const result = validResult(record);
        return result
          ? { ok: true, jobId, result }
          : failure('invalid_terminal_result', jobId);
      }
      if (record.status === 'error') {
        return failure(boundedMessage(record.error, 'deliberation_failed'), jobId);
      }
      if (record.status === 'unconfirmed') {
        // No replay: the original worker may still be completing elsewhere.
        return failure('job_worker_continuity_unknown', jobId, true);
      }
      if (record.status !== 'running' && record.status !== 'queued') {
        return failure('unknown_job_state', jobId);
      }
    }
    const waitMs = Math.min(interval, Math.max(0, deadline - Date.now()));
    if (waitMs <= 0) return failure('job_observation_timeout', jobId, true);
    if (!(await delayWithAbort(waitMs, options.signal))) {
      return failure('observation_cancelled', jobId, true);
    }
  }
  return failure('job_observation_limit', jobId, true);
}

/** Admit once. Never auto-retry uncertain POSTs after a network interruption. */
export async function submitDiscourseJob(
  transport: DiscourseTransport,
  body: { task: string; prompt: string; discord: boolean },
  options: PollOptions = {},
): Promise<DiscourseOutcome> {
  if (options.signal?.aborted) return failure('observation_cancelled', null, true);
  if (
    !body || body.task !== 'creative' ||
    typeof body.prompt !== 'string' ||
    body.prompt.trim().length < 4 || body.prompt.length > 20_000 ||
    typeof body.discord !== 'boolean'
  ) return failure('invalid_prompt_or_options');
  options.onProgress?.({ status: 'submitting', jobId: null, attempts: 0 });
  let admitted: WireResult<JobWire>;
  try {
    admitted = await transport.post<JobWire>(
      '/api/discourse/deliberate/async', body,
      { signal: options.signal, timeoutMs: 12_000, retries: 0 },
    );
  } catch {
    admitted = { ok: false, status: 0, data: null, error: 'network_error' };
  }
  // If the POST returned a valid job receipt, preserve it even if the UI
  // detached at the same instant. An admitted server job is still running.
  if (options.signal?.aborted) {
    const knownId = admitted.data?.job_id;
    return failure(
      'observation_cancelled',
      typeof knownId === 'string' && JOB_ID_PATTERN.test(knownId) ? knownId : null,
      true,
    );
  }
  if (!admitted.ok) {
    if (admitted.status === 0) {
      return failure('admission_unconfirmed_do_not_retry', null, false);
    }
    return failure(boundedMessage(admitted.data?.error || admitted.error, 'admission_rejected'));
  }
  if (!admitted.data || admitted.data.error) {
    return failure(boundedMessage(admitted.data?.error, 'admission_rejected'));
  }
  const jobId = admitted.data.job_id;
  if (
    admitted.data.status !== 'running' ||
    typeof jobId !== 'string' ||
    !JOB_ID_PATTERN.test(jobId)
  ) return failure('invalid_admission_receipt');
  return pollDiscourseJob(transport, jobId, options);
}


/** Recovery lists contain identifiers and statuses only: never prompts or text. */
export interface DiscourseJobSummary {
  jobId: string;
  status: 'running' | 'done' | 'error';
  createdAt: string;
  workerContinuityVerified: false;
}
export type JobDiscovery =
  | { ok: true; jobs: DiscourseJobSummary[] }
  | { ok: false; error: string };

export async function discoverDiscourseJobs(
  transport: DiscourseTransport, options: { signal?: AbortSignal } = {},
): Promise<JobDiscovery> {
  if (options.signal?.aborted) return { ok: false, error: 'observation_cancelled' };
  let response: WireResult<{ jobs?: unknown }>;
  try {
    response = await transport.get<{ jobs?: unknown }>(
      '/api/discourse/jobs?limit=5',
      { signal: options.signal, timeoutMs: 8_000, retries: 0 },
    );
  } catch {
    response = { ok: false, status: 0, data: null, error: 'network_error' };
  }
  if (options.signal?.aborted) return { ok: false, error: 'observation_cancelled' };
  if (!response.ok) {
    return { ok: false, error: boundedMessage(response.error, 'job_discovery_unavailable') };
  }
  const rows = response.data?.jobs;
  if (!Array.isArray(rows) || rows.length > 5) {
    return { ok: false, error: 'invalid_job_discovery_response' };
  }
  const jobs: DiscourseJobSummary[] = [];
  const seen = new Set<string>();
  for (const row of rows) {
    if (!row || typeof row !== 'object') continue;
    const item = row as Record<string, unknown>;
    const id = item.job_id;
    const status = item.status;
    const stamp = item.created_at;
    if (
      typeof id !== 'string' || !JOB_ID_PATTERN.test(id) || seen.has(id)
      || (status !== 'running' && status !== 'done' && status !== 'error')
      || typeof stamp !== 'string' || stamp.length < 1 || stamp.length > 80
      || item.worker_continuity_verified !== false
    ) continue;
    seen.add(id);
    jobs.push({
      jobId: id, status, createdAt: stamp,
      workerContinuityVerified: false,
    });
  }
  return { ok: true, jobs };
}
