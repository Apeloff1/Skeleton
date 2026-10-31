import { CryptoDigestAlgorithm, digestStringAsync } from 'expo-crypto';
import { API_BASE } from '../utils/apiBase';
import { authHeaders, getAuthToken } from '../auth/gameforgeAuth';
import api from '../utils/apiClient';
import {
  getConversationTurn, startConversationTurn,
  validateConversationMessage, validateConversationThread,
  type ConversationRequestOptions, type ConversationThread,
  type ConversationTurn, type ConversationTurnMemoryPolicy, type ConversationMessage,
} from './governedConversationClient';
import { ChatClientError, asChatError, chatAbortError, chatApiError } from './chatErrors';
import { normalizeChatCooperation, validateChatCooperationReceipts, validateChatCooperationSummary, type ChatCooperationPolicy } from './chatCooperation';
import { validateChatModel, type ChatModelRuntimeFacts } from './chatModelCatalog';

export { ChatClientError } from './chatErrors';

export type ChatModel = {
  id: string;
  provider_id: string;
  model_id: string;
  label: string;
  available: boolean;
  selectable: boolean;
  active: boolean;
  fallback?: boolean;
  credential_free: boolean;
  supports_temperature?: boolean;
  execution_mode?: string;
  model_family?: string;
  tokenizer?: string;
  limits_source?: string;
  context_window?: number | null;
  max_output_tokens?: number | null;
  default_output_tokens?: number | null;
  capabilities: string[];
  readiness: { code: string; message: string; action?: string | null } | null;
  activation?: Record<string, unknown> | null;
} & ChatModelRuntimeFacts;

export type ChatModelCatalog = {
  schema_version: string | number;
  available: boolean;
  automatic_available?: boolean;
  engine?: string | Record<string, unknown>;
  active: { provider_id: string; model_id: string } | null;
  models: ChatModel[];
  readiness: ChatModel['readiness'];
};

export async function getChatModels(input: ConversationRequestOptions = {}): Promise<ChatModelCatalog> {
  const token = getAuthToken();
  const result = await api.get<ChatModelCatalog>('/api/ai/models', {
    signal: input.signal, headers: authHeaders(input.headers), retries: 0, timeoutMs: 15000, maxResponseChars: 256 * 1024,
  });
  if (token !== getAuthToken()) throw new ChatClientError('Your account changed. Refresh the configured models for the current account.', { kind: 'authorization', retryable: false });
  if (!result.ok || !result.data) throw chatApiError(result, 'Could not load available models.');
  const catalog = result.data;
  if (!catalog || typeof catalog.available !== 'boolean' || !Array.isArray(catalog.models) || catalog.models.length > 256
    || catalog.automatic_available !== undefined && typeof catalog.automatic_available !== 'boolean') {
    throw new ChatClientError('Model catalog is invalid.', { code: 'invalid_catalog' });
  }
  const seen = new Set<string>();
  for (const model of catalog.models) {
    validateChatModel(model);
    if (seen.has(model.id)) {
      throw new ChatClientError('Model catalog contains an invalid entry.', { code: 'invalid_catalog' });
    }
    seen.add(model.id);
  }
  if (catalog.available && !catalog.models.some(model => model.available && model.selectable)) throw new ChatClientError('The model readiness summary has no available text model.', { code: 'invalid_catalog' });
  return catalog;
}

export type ChatTurnInput = {
  message: string;
  idempotencyKey: string;
  context?: string;
  memoryPolicy?: ConversationTurnMemoryPolicy;
  attachmentRefs?: string[];
  model?: ChatModel | null;
  maxOutputTokens?: number;
  temperature?: number;
  cooperation?: ChatCooperationPolicy;
} & ConversationRequestOptions;

export async function submitChatTurn(thread: ConversationThread, input: ChatTurnInput): Promise<ConversationTurn> {
  if (!input.message.trim() || input.message.length > 100000 || (input.context?.length ?? 0) > 100000) {
    throw new ChatClientError('Message or context is empty or too large.', { kind: 'validation' });
  }
  if ((input.attachmentRefs?.length ?? 0) > 4
    || new Set(input.attachmentRefs ?? []).size !== (input.attachmentRefs?.length ?? 0)
    || input.attachmentRefs?.some(ref => typeof ref !== 'string' || !/^chat-attachment:\/\/[0-9a-f-]{36}$/.test(ref))) {
    throw new ChatClientError('Attachment references are invalid.', { kind: 'validation' });
  }
  if (input.model && (!input.model.selectable || !input.model.available)) {
    throw new ChatClientError('The selected model is not ready. Choose another model.', {
      kind: 'unavailable', code: 'model_unavailable', retryable: false,
    });
  }
  const limit = input.maxOutputTokens ?? input.model?.default_output_tokens ?? undefined;
  if (limit !== undefined && (!Number.isSafeInteger(limit) || limit < 1 || limit > (input.model?.max_output_tokens ?? 1000000))) {
    throw new ChatClientError('Output limit exceeds the selected model capacity.', { kind: 'validation' });
  }
  const turn = await startConversationTurn(thread, {
    ...input, deferred: true, providerId: input.model?.provider_id,
    modelId: input.model?.model_id, maxOutputTokens: limit,
    ...(input.cooperation ? { cooperation: normalizeChatCooperation(input.cooperation) } : {}),
  });
  return validateChatTurn(turn, thread.thread_id, input.idempotencyKey);
}

export function validateChatTurn(turn: ConversationTurn, threadId: string, key: string): ConversationTurn {
  if (!turn || typeof turn !== 'object' || typeof turn.success !== 'boolean') {
    throw new ChatClientError('Chat returned an invalid turn.', { code: 'invalid_turn' });
  }
  const wire = turn as ConversationTurn & { thread_id?: string; idempotency_key?: string };
  if (turn.cooperation != null) {
    validateChatCooperationSummary(turn.cooperation);
    validateChatCooperationReceipts(turn.cooperation, turn.engine_provider_receipts);
    if (turn.terminal && turn.success && !turn.cooperation.complete) throw new ChatClientError('The completed answer has an unfinished review record.', { code: 'incomplete_cooperation_evidence' });
  }
  if (turn.thread) validateConversationThread(turn.thread, threadId);
  for (const message of [turn.user_message, turn.assistant_message, turn.terminal_message]) if (message) validateConversationMessage(message, threadId);
  if ((wire.thread_id && wire.thread_id !== threadId)
    || (wire.idempotency_key && wire.idempotency_key !== key)
    || (turn.thread && turn.thread.thread_id !== threadId)
    || (turn.user_message && (turn.user_message.thread_id !== threadId || turn.user_message.idempotency_key !== key))
    || (turn.assistant_message && turn.assistant_message.thread_id !== threadId)
    || (turn.terminal_message && turn.terminal_message.thread_id !== threadId)
    || (turn.assistant_message && turn.user_message
      && turn.assistant_message.causal_user_message_id !== turn.user_message.message_id)) {
    throw new ChatClientError('Chat turn identity does not match this conversation.', { code: 'foreign_turn' });
  }
  return turn.assistant_message && !turn.terminal
    ? { ...turn, terminal: true, state: 'completed' } : turn;
}

export type ChatSseFrame = { event: string; data: string; id: string | null; retry: number | null };
const MAX_FRAME_CHARS = 1048576;
const MAX_PROVISIONAL_CHARS = 1000000;

/** Handles CR, LF, CRLF, multiline data and frames split anywhere by transport. */
export class ChatSseParser {
  private line = '';
  private data: string[] = [];
  private event = '';
  private id: string | null = null;
  private retry: number | null = null;
  private chars = 0;
  private skipLf = false;
  private firstCharacter = true;

  constructor(private emit: (frame: ChatSseFrame) => void) {}

  push(chunk: string): void {
    for (const character of chunk) {
      if (this.firstCharacter) {
        this.firstCharacter = false;
        if (character === '\uFEFF') continue;
      }
      if (this.skipLf) {
        this.skipLf = false;
        if (character === '\n') continue;
      }
      if (character === '\r' || character === '\n') {
        this.consumeLine();
        this.skipLf = character === '\r';
      } else {
        this.line += character;
        this.chars += 1;
        if (this.chars > MAX_FRAME_CHARS) {
          throw new ChatClientError('Stream frame exceeds the supported size.', { code: 'stream_limit' });
        }
      }
    }
  }

  private consumeLine(): void {
    const line = this.line;
    this.line = '';
    if (!line) {
      if (this.data.length || this.retry !== null) this.emit({ event: this.event || 'message', data: this.data.join('\n'), id: this.id, retry: this.retry });
      this.data = []; this.event = ''; this.id = null; this.retry = null; this.chars = 0;
      return;
    }
    if (line.startsWith(':')) {
      this.chars -= line.length;
      return;
    }
    const colon = line.indexOf(':');
    const field = colon < 0 ? line : line.slice(0, colon);
    let value = colon < 0 ? '' : line.slice(colon + 1);
    if (value.startsWith(' ')) value = value.slice(1);
    if (field === 'data') this.data.push(value);
    else if (field === 'event') this.event = value;
    else if (field === 'id' && !value.includes('\u0000')) this.id = value;
    else if (field === 'retry' && /^\d+$/.test(value)) this.retry = Math.min(10000, Number(value));
  }
}

export type ChatEngineProgress = {
  sequence: number; type: string; payload: Record<string, unknown>;
};
export type ChatStreamConnection = 'streaming' | 'reconnecting' | 'polling' | 'resyncing';
export type FollowChatTurnOptions = ConversationRequestOptions & {
  lastEventId?: number;
  executionId?: string | null;
  operationId?: string | null;
  provisionalText?: string;
  onConnection?: (state: ChatStreamConnection) => void;
  onCursor?: (sequence: number) => void;
  onProgress?: (event: ChatEngineProgress) => void;
  onText?: (text: string) => void;
  onTurn?: (turn: ConversationTurn) => void;
  timeoutMs?: number;
};

function object(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : null;
}

function canonical(value: unknown, depth = 0): string {
  if (depth > 48) throw new ChatClientError('Stream event nesting is too deep.', { code: 'stream_limit' });
  if (Array.isArray(value)) return '[' + value.map(item => canonical(item, depth + 1)).join(',') + ']';
  if (value && typeof value === 'object') {
    const source = value as Record<string, unknown>;
    return '{' + Object.keys(source).sort().map(key => JSON.stringify(key) + ':' + canonical(source[key], depth + 1)).join(',') + '}';
  }
  return JSON.stringify(value) ?? 'null';
}

export function waitForChatDelay(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) { reject(chatAbortError()); return; }
    const onAbort = () => { clearTimeout(timer); signal?.removeEventListener('abort', onAbort); reject(chatAbortError()); };
    const timer = setTimeout(() => { signal?.removeEventListener('abort', onAbort); resolve(); }, ms);
    signal?.addEventListener('abort', onAbort, { once: true });
  });
}

/** Read-only observation. Accepted work is never resubmitted by reconnect. */
async function followTurnTransport(threadId: string, key: string, input: FollowChatTurnOptions, transport: {
  eventsPath: string | null;
  getTurn: () => Promise<ConversationTurn>;
  validate: (turn: ConversationTurn) => ConversationTurn;
}): Promise<ConversationTurn> {
  const sessionToken = getAuthToken();
  const requireSession = () => {
    if (sessionToken !== getAuthToken()) throw new ChatClientError('Your account changed. Reopen the saved conversation.', { kind: 'authorization', code: 'account_changed', retryable: false });
  };
  let cursor = input.lastEventId ?? 0;
  if (!Number.isSafeInteger(cursor) || cursor < 0) throw new ChatClientError('Stream cursor is invalid.');
  // An in-memory event sequence without its verified digest is not a usable
  // persisted cursor. Replay from zero rather than invent a hash or bypass
  // the server's exact-cursor contract.
  let cursorDigest: string | null = null;
  let provisional = input.provisionalText ?? '';
  if (cursor > 0) {
    cursor = 0;
    provisional = '';
    input.onCursor?.(0);
    input.onText?.('');
  }
  const seen = new Map<number, string>();
  const eventIds = new Map<string, number>();
  const started = Date.now();
  const timeout = Math.max(1000, Math.min(input.timeoutMs ?? 3600000, 86400000));
  let usePolling = transport.eventsPath === null;
  let retries = 0;
  let retryMs = 500;
  const probe = async (): Promise<ConversationTurn> => {
    requireSession();
    const turn = transport.validate(await transport.getTurn());
    requireSession();
    input.onTurn?.(turn);
    return turn;
  };

  while (Date.now() - started < timeout) {
    requireSession();
    if (input.signal?.aborted) throw chatAbortError();
    if (usePolling) {
      input.onConnection?.(retries ? 'reconnecting' : 'polling');
      try {
        const turn = await probe();
        if (turn.terminal) return turn;
        retries = 0;
      } catch (error) {
        const failure = asChatError(error);
        if (input.signal?.aborted || failure.kind === 'cancelled') throw chatAbortError();
        if (!failure.retryable || ++retries > 6) throw failure;
      }
      await waitForChatDelay(Math.min(10000, 1000 * 2 ** Math.min(retries, 4)), input.signal);
      continue;
    }
    input.onConnection?.(retries ? 'reconnecting' : 'streaming');
    const controller = new AbortController();
    const abort = () => controller.abort();
    input.signal?.addEventListener('abort', abort, { once: true });
    let idleTimer: ReturnType<typeof setTimeout>;
    const renewIdle = () => { clearTimeout(idleTimer); idleTimer = setTimeout(abort, 45000); };
    renewIdle();
    let reader: ReadableStreamDefaultReader<Uint8Array> | undefined;
    let final: ConversationTurn | null = null;
    let expectedDetach = false;
    let pageAdvanced = false;
    try {
      const headers = authHeaders({ Accept: 'text/event-stream', ...input.headers });
      if (cursor && cursorDigest) headers['Last-Event-ID'] = `${cursor}:${cursorDigest}`;
      const path = transport.eventsPath! + '?idempotency_key=' + encodeURIComponent(key)
        + '&after_sequence=' + cursor
        + (cursorDigest === null ? '' : '&last_event_digest=' + encodeURIComponent(cursorDigest));
      const response = await fetch(API_BASE + path, { headers, signal: controller.signal, credentials: 'same-origin' });
      requireSession();
      if (!response.ok) {
        let detail: unknown = null;
        try { detail = await response.json(); } catch {}
        throw chatApiError({ ok: false, status: response.status, data: detail, error: null, rid: response.headers.get('x-request-id') }, 'Chat stream is unavailable.');
      }
      if (!response.body || typeof response.body.getReader !== 'function' || typeof TextDecoder === 'undefined') {
        usePolling = true;
        continue;
      }
      if (!response.headers.get('content-type')?.includes('text/event-stream')) {
        throw new ChatClientError('Chat stream returned an unsupported content type.', { code: 'invalid_stream' });
      }
      reader = response.body.getReader();
      const decoder = new TextDecoder('utf-8', { fatal: true });
      const frames: ChatSseFrame[] = [];
      const parser = new ChatSseParser(frame => {
        if (frames.length >= 256) throw new ChatClientError('Stream batch is too large.', { code: 'stream_limit' });
        frames.push(frame);
      });
      const applyFrame = async (frame: ChatSseFrame): Promise<void> => {
        requireSession();
        if (final) throw new ChatClientError('Chat stream emitted an event after its terminal frame.', { code: 'post_terminal_event' });
        if (frame.retry !== null) retryMs = Math.max(250, frame.retry);
        if (!frame.data) return;
        let raw: unknown;
        try { raw = JSON.parse(frame.data); } catch { throw new ChatClientError('Chat stream contains malformed JSON.', { code: 'invalid_stream' }); }
        const record = object(raw);
        if (!record) throw new ChatClientError('Chat stream contains an invalid event.', { code: 'invalid_stream' });
        if (frame.event === 'chat.detach') {
          expectedDetach = true;
          return;
        }
        if (frame.event === 'chat.final') {
          final = transport.validate(record as unknown as ConversationTurn);
          if (!final.terminal) throw new ChatClientError('Final chat frame is not terminal.', { code: 'invalid_terminal' });
          input.onTurn?.(final);
          return;
        }
        if (frame.event === 'chat.error' || frame.event === 'chat.resync_required') {
          throw new ChatClientError(typeof record.message === 'string' ? record.message : 'Chat observation must be refreshed.', {
            kind: frame.event === 'chat.resync_required' ? 'protocol' : 'unavailable',
            code: typeof record.code === 'string' ? record.code : 'resync_required',
          });
        }
        if (!frame.event.startsWith('engine.')) return;
        // Current product events bind both sequence and digest in the wire ID.
        // Numeric IDs from the previous transport version still require the
        // same record digest, exact identity and uninterrupted chain below.
        const cursorMatch = frame.id?.match(/^(\d+)(?::([0-9a-f]{64}))?$/);
        if (!cursorMatch) throw new ChatClientError('Engine stream is missing a durable cursor.', { code: 'invalid_cursor' });
        const sequence = Number(cursorMatch[1]);
        if (!Number.isSafeInteger(sequence) || sequence < 1
          || (record.sequence !== undefined && record.sequence !== sequence)
          || (record.execution_id !== undefined && input.executionId && record.execution_id !== input.executionId)
          || (record.operation_id !== undefined && input.operationId && record.operation_id !== input.operationId)) {
          throw new ChatClientError('Engine stream identity is invalid.', { code: 'foreign_event' });
        }
        const eventId = record.event_id;
        if (typeof eventId !== 'string' || !eventId || eventId.length > 512
          || (typeof record.type === 'string' && frame.event !== 'engine.' + record.type)) {
          throw new ChatClientError('Engine event identifier or type is invalid.', { code: 'invalid_event' });
        }
        const digest = record.event_digest;
        if (typeof digest !== 'string' || !/^[0-9a-f]{64}$/.test(digest)
          || cursorMatch[2] !== undefined && cursorMatch[2] !== digest) {
          throw new ChatClientError('Engine event digest is invalid.', { code: 'invalid_event_digest' });
        }
        const previousSequence = eventIds.get(eventId);
        if (previousSequence !== undefined && previousSequence !== sequence) throw new ChatClientError('Engine event identity was reused.', { code: 'conflicting_event' });
        const fingerprint = await digestStringAsync(CryptoDigestAlgorithm.SHA256, canonical({ event: frame.event, data: record }));
        requireSession();
        if (input.signal?.aborted) throw chatAbortError();
        if (sequence <= cursor) {
          if (seen.get(sequence) !== fingerprint) throw new ChatClientError('Engine stream replay conflicts with the accepted cursor.', { code: 'conflicting_event' });
          return;
        }
        if (sequence !== cursor + 1) throw new ChatClientError('Engine stream has a sequence gap.', { code: 'stream_gap' });
        if (record.previous_event_digest !== cursorDigest) {
          throw new ChatClientError('Engine event digest chain changed.', { code: 'conflicting_event_digest' });
        }
        const type = typeof record.type === 'string' ? record.type : frame.event.slice(7);
        const payload: Record<string, unknown> = { ...(object(record.payload) ?? record),
          ...(typeof record.to_state === 'string' ? { state: record.to_state } : {}) };
        if (type === 'output.started' || type === 'output.reset') {
          provisional = '';
          input.onText?.('');
        }
        if (type === 'output.delta') {
          const delta = typeof payload.delta === 'string' ? payload.delta : typeof payload.text === 'string' ? payload.text : null;
          if (delta === null || provisional.length + delta.length > MAX_PROVISIONAL_CHARS) {
            throw new ChatClientError('Streamed response exceeds the supported size.', { code: 'stream_limit' });
          }
          provisional += delta;
          input.onText?.(provisional);
        }
        input.onProgress?.({ sequence, type, payload });
        eventIds.set(eventId, sequence);
        while (eventIds.size > 256) eventIds.delete(eventIds.keys().next().value!);
        seen.set(sequence, fingerprint);
        while (seen.size > 256) seen.delete(seen.keys().next().value!);
        cursor = sequence;
        cursorDigest = digest;
        pageAdvanced = true;
        input.onCursor?.(cursor);
        retries = 0;
      };
      while (!final) {
        const chunk = await reader.read();
        requireSession();
        if (input.signal?.aborted) throw chatAbortError();
        if (chunk.done) {
          parser.push(decoder.decode());
          for (const frame of frames.splice(0)) await applyFrame(frame);
          break;
        }
        renewIdle();
        if (chunk.value.byteLength > 4 * MAX_FRAME_CHARS) throw new ChatClientError('Stream chunk exceeds the supported size.', { code: 'stream_limit' });
        try { parser.push(decoder.decode(chunk.value, { stream: true })); }
        catch (error) {
          if (error instanceof ChatClientError) throw error;
          throw new ChatClientError('Chat stream contains invalid UTF-8.', { code: 'invalid_stream' });
        }
        for (const frame of frames.splice(0)) await applyFrame(frame);
      }
      if (final) return final;
      if (pageAdvanced) {
        // Even a severed response may have more durable events. Continue
        // from the exact chain digest instead of trusting a terminal probe
        // that might skip a remaining bounded journal page.
        retries = 0;
        continue;
      }
      const turn = await probe();
      if (turn.terminal) return turn;
      if (expectedDetach) {
        // An empty completed page is normal while inference is running.
        // Avoid reconnect loops and do not exhaust transport retries.
        retries = 0;
        retryMs = Math.max(retryMs, 1000);
      } else {
        retries += 1;
      }
    } catch (error) {
      if (input.signal?.aborted) throw chatAbortError();
      const failure = asChatError(error);
      if (failure.kind === 'authorization' || failure.kind === 'validation') throw failure;
      if (failure.kind === 'protocol' || failure.status === 404) {
        input.onConnection?.('resyncing');
        provisional = ''; input.onText?.('');
        const turn = await probe();
        if (turn.terminal) return turn;
        usePolling = true;
      } else {
        retries += 1;
        if (retries > 6) {
          const turn = await probe();
          if (turn.terminal) return turn;
          throw failure;
        }
      }
    } finally {
      clearTimeout(idleTimer!);
      input.signal?.removeEventListener('abort', abort);
      controller.abort();
      try { await reader?.cancel(); } catch {}
    }
    if (!usePolling) await waitForChatDelay(Math.min(10000, retryMs * 2 ** Math.min(retries, 4)), input.signal);
  }
  throw new ChatClientError('This reply is still running. Reconnect to follow its progress.', {
    kind: 'timeout', code: 'observation_timeout', retryable: true,
  });
}


export async function followChatTurn(threadId: string, key: string, input: FollowChatTurnOptions = {}): Promise<ConversationTurn> {
  return followTurnTransport(threadId, key, input, {
    eventsPath: '/api/ai/chat/turns/' + encodeURIComponent(threadId) + '/events',
    getTurn: () => getConversationTurn(threadId, key, input),
    validate: turn => validateChatTurn(turn, threadId, key),
  });
}

export type RegenerationTurn = ConversationTurn & {
  idempotency_key?: string;
  regenerated_from?: string;
  message?: ConversationMessage;
};

function regenerationPath(threadId: string, messageId: string): string {
  return '/api/v1/conversations/' + encodeURIComponent(threadId)
    + '/messages/' + encodeURIComponent(messageId) + '/regenerate';
}

export function validateRegenerationTurn(turn: RegenerationTurn, threadId: string, messageId: string, key: string): ConversationTurn {
  if (!turn || typeof turn.success !== 'boolean' || turn.regenerated_from !== messageId
    || (turn.idempotency_key !== undefined && turn.idempotency_key !== key)
    || !turn.thread || turn.thread.thread_id !== threadId) {
    throw new ChatClientError('Regeneration returned an invalid identity.', { code: 'foreign_regeneration' });
  }
  const assistant = turn.assistant_message ?? turn.message;
  if (assistant && (assistant.thread_id !== threadId || assistant.author_type !== 'assistant'
    || assistant.supersedes_message_id !== messageId)) {
    throw new ChatClientError('Regenerated reply has invalid lineage.', { code: 'foreign_regeneration' });
  }
  return { ...turn, ...(assistant ? { assistant_message: assistant } : {}) };
}

async function regenerationRequest(
  method: 'get' | 'post', threadId: string, messageId: string, key: string,
  suffix: string, body: Record<string, unknown> | null, input: ConversationRequestOptions,
): Promise<ConversationTurn> {
  const options = { ...input, headers: authHeaders(input.headers), retries: 0,
    idempotencyKey: key + (suffix === '/cancel' ? ':cancel' : ''), timeoutMs: 20000 };
  const path = regenerationPath(threadId, messageId) + suffix;
  const result = method === 'get'
    ? await api.get<RegenerationTurn>(path + '?idempotency_key=' + encodeURIComponent(key), options)
    : await api.post<RegenerationTurn>(path, body, options);
  if (!result.ok || !result.data) throw chatApiError(result, 'Could not update regeneration.');
  return validateRegenerationTurn(result.data, threadId, messageId, key);
}

export async function startRegenerationTurn(
  thread: ConversationThread, messageId: string,
  input: { idempotencyKey: string; model?: ChatModel | null; maxOutputTokens?: number; temperature?: number } & ConversationRequestOptions,
): Promise<ConversationTurn> {
  if (input.model && (!input.model.available || !input.model.selectable)) {
    throw new ChatClientError('The selected model is not ready.', { kind: 'unavailable', code: 'model_unavailable', retryable: false });
  }
  return regenerationRequest('post', thread.thread_id, messageId, input.idempotencyKey, '', {
    idempotency_key: input.idempotencyKey, expected_thread_version: thread.version,
    provider_id: input.model?.provider_id, model_id: input.model?.model_id,
    max_output_tokens: input.maxOutputTokens ?? input.model?.default_output_tokens ?? undefined,
    temperature: input.temperature, response_mode: 'deferred',
  }, input);
}

export async function getRegenerationTurn(threadId: string, messageId: string, key: string, input: ConversationRequestOptions = {}): Promise<ConversationTurn> {
  return regenerationRequest('get', threadId, messageId, key, '/turn', null, input);
}

export async function resumeRegenerationTurn(threadId: string, messageId: string, key: string, input: ConversationRequestOptions = {}): Promise<ConversationTurn> {
  return regenerationRequest('post', threadId, messageId, key, '/resume', {
    idempotency_key: key, response_mode: 'deferred',
  }, input);
}

export async function cancelRegenerationTurn(threadId: string, messageId: string, key: string, input: ConversationRequestOptions = {}): Promise<ConversationTurn> {
  return regenerationRequest('post', threadId, messageId, key, '/cancel', {
    idempotency_key: key, reason: 'user_cancelled',
  }, input);
}

export async function followRegenerationTurn(threadId: string, messageId: string, key: string, input: FollowChatTurnOptions = {}): Promise<ConversationTurn> {
  return followTurnTransport(threadId, key, input, {
    // This route currently exposes actual status; it does not fabricate token frames.
    eventsPath: null,
    getTurn: () => getRegenerationTurn(threadId, messageId, key, input),
    validate: turn => validateRegenerationTurn(turn as RegenerationTurn, threadId, messageId, key),
  });
}
