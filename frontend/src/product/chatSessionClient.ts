import { Platform } from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { CryptoDigestAlgorithm, digestStringAsync } from 'expo-crypto';
import { API_BASE } from '../utils/apiBase';
import api, { type ApiResult } from '../utils/apiClient';
import { authHeaders, getAuthToken, resolveStorageTenantIdentity } from '../auth/gameforgeAuth';
import { ChatClientError, chatApiError } from './chatErrors';
import type { ConversationMessage, ConversationThread } from './conversationClient';
import { validateConversationProjection } from './conversationProjection';
import { createConversation, projectCanonicalHistory, MAX_CONVERSATIONS, type ChatBody, type ChatHistoryProjection, type Conversation } from '../features/Jeeves/workspace';
import type { ChatProgress, ChatResponse, WorkspaceStorage } from '../features/Jeeves/WorkspaceController';

export type ChatModel = { id: string; provider_id: string; model_id: string; label: string; available: boolean; selectable: boolean; active: boolean; credential_free: boolean; context_window: number; max_output_tokens: number; default_output_tokens: number; capabilities: string[]; readiness: { code: string; message: string; action?: string | null } };
export type ChatReadiness = {
  schema_version: string; available: boolean; configured: boolean;
  checks: Record<string, { available: boolean; code: string }>;
  models: { models: ChatModel[]; automatic_available: boolean; readiness?: { message?: string; action?: string | null } };
  capabilities: { durable_sessions: boolean; deferred: boolean; resume: boolean; transition_stream: boolean; token_deltas: boolean; attachments: boolean; crawler_context: boolean };
  actions: { id: string; label: string; href: string | null }[];
};
export type ChatCursor = { operation_id: string; last_seen_sequence: number; last_event_digest: string | null };
type Turn = {
  success: boolean; accepted?: boolean; terminal?: boolean; state?: string; turn_state?: string | null; response?: string | null;
  thread?: ConversationThread; user_message?: ConversationMessage; assistant_message?: ConversationMessage;
  operation_id?: string; engine_execution_id?: string; ai_result_id?: string; model?: string; provider?: string;
  server_resume_available?: boolean; cancellation_requested?: boolean;
};
type StreamEvent = { operation_id: string; sequence: number; event_digest: string; previous_event_digest: string | null; kind: string; to_state: string; terminal: boolean };
const ID = /^[A-Za-z0-9:_-]{1,160}$/;
const HASH = /^[a-f0-9]{64}$/;
const ROOT = '/api/ai/chat';
export class ChatTerminalError extends ChatClientError { constructor(readonly state: string) { super(state === 'cancelled' ? 'The server confirmed this turn was cancelled. Copy it into a new message if you want to try again.' : 'This turn ended without a reply. Start a new message to try again.', { kind: 'execution', code: 'chat_turn_terminal', retryable: false }); } }
function invalid(message: string): never { throw new ChatClientError(message, { kind: 'protocol', retryable: false }); }
function id(value: string): string { if (!ID.test(value)) invalid('The conversation identity is invalid.'); return encodeURIComponent(value); }
function opts(signal?: AbortSignal) { return { signal, headers: authHeaders(), timeoutMs: 30000, retries: 0 }; }
async function read<T>(operation: Promise<ApiResult<T>>, token: string, fallback: string): Promise<T> {
  const result = await operation;
  if (token !== getAuthToken()) throw new ChatClientError('Your account changed. Reopen AI chat.', { kind: 'authorization', retryable: false });
  if (!result.ok || !result.data) throw chatApiError(result, fallback); return result.data;
}
function thread(value: ConversationThread, expected?: string): ConversationThread {
  if (!value || !ID.test(value.thread_id) || expected && value.thread_id !== expected || !Number.isSafeInteger(value.version) || value.version < 1 || !Number.isSafeInteger(value.message_sequence) || value.message_sequence < 0 || typeof value.title !== 'string') invalid('The canonical conversation is invalid.'); return value;
}
function checkTurn(value: Turn, threadId: string, key: string): Turn {
  if (!value || typeof value.success !== 'boolean' || value.thread && thread(value.thread, threadId).thread_id !== threadId
    || value.user_message && (value.user_message.thread_id !== threadId || value.user_message.idempotency_key !== key)
    || value.assistant_message && (value.assistant_message.thread_id !== threadId || value.assistant_message.author_type !== 'assistant' || value.user_message && value.assistant_message.causal_user_message_id !== value.user_message.message_id)
    || JSON.stringify(value).length > 2 * 1024 * 1024) invalid('The chat result does not match the original turn.');
  return value;
}
export async function getChatReadiness(signal?: AbortSignal): Promise<ChatReadiness> {
  const value = await read(api.get<ChatReadiness>(ROOT + '/readiness', opts(signal)), getAuthToken(), 'AI chat readiness could not be observed. Open Setup to check the services.');
  if (!value || value.schema_version !== 'backend.ai.chat-readiness.v1' || typeof value.available !== 'boolean' || typeof value.configured !== 'boolean' || !value.checks || !value.models || !Array.isArray(value.models.models) || value.models.models.length > 16 || !value.capabilities || !Array.isArray(value.actions)) invalid('The AI chat readiness response is invalid.');
  for (const row of value.models.models) if (!row || typeof row.id !== 'string' || row.id.length > 512 || typeof row.provider_id !== 'string' || typeof row.model_id !== 'string' || typeof row.label !== 'string' || typeof row.selectable !== 'boolean' || typeof row.available !== 'boolean' || !Number.isSafeInteger(row.context_window) || row.context_window < 1 || !Number.isSafeInteger(row.default_output_tokens) || row.default_output_tokens < 1 || row.default_output_tokens > row.max_output_tokens || !Number.isSafeInteger(row.max_output_tokens) || row.max_output_tokens < 1 || !row.readiness || typeof row.readiness.message !== 'string') invalid('The configured model list is invalid.');
  for (const key of ['conversation_storage', 'engine', 'models', 'crawler']) if (!value.checks[key] || typeof value.checks[key].available !== 'boolean' || typeof value.checks[key].code !== 'string') invalid('The AI prerequisite checks are incomplete.');
  for (const key of ['durable_sessions', 'deferred', 'resume', 'transition_stream', 'token_deltas', 'attachments', 'crawler_context'] as const) if (typeof value.capabilities[key] !== 'boolean') invalid('The chat capability flags are invalid.');
  return value;
}
export function chatReadinessMessage(value: ChatReadiness): string {
  if (value.available) return 'The conversation store, AI engine and a configured model are ready.';
  const missing = Object.entries(value.checks).filter(([key, check]) => key !== 'crawler' && !check.available).map(([key]) => ({ conversation_storage: 'conversation storage', engine: 'AI engine', models: 'configured model' })[key] || key);
  return missing.length ? `Waiting for ${missing.join(', ')}. Open Setup for the observed prerequisites.` : 'AI chat is not ready. Check the configured model and application services.';
}
export async function verifiedChatScope(): Promise<{ key: string; token: string }> {
  const initialToken = getAuthToken();
  const identity = await resolveStorageTenantIdentity(); const token = getAuthToken();
  if (initialToken !== token) throw new ChatClientError('Your account changed while resolving chat storage. Verify it again.', { kind: 'authorization' });
  // The resolver cache scopes storage, but opening it still requires a fresh server verdict.
  const observed = await read(api.get<{ authenticated: boolean; enforced: boolean; user?: { tenant_id?: string; email?: string } }>('/api/auth/me', opts()), token, 'Your account could not be verified. No account cache was opened.');
  if (observed.authenticated !== true) throw new ChatClientError('Sign in to open your account conversations.', { kind: 'authorization' });
  if (observed.authenticated === true && (String(observed.user?.tenant_id || observed.user?.email || '').trim() !== identity.tenantId || String(observed.user?.email || observed.user?.tenant_id || '').trim() !== identity.principalId)) throw new ChatClientError('Your account identity changed. Sign in again before opening chat.', { kind: 'authorization' });
  const key = await digestStringAsync(CryptoDigestAlgorithm.SHA256, JSON.stringify([identity.tenantId, identity.principalId]));
  if (token !== getAuthToken()) throw new Error('Your account changed while opening chat.'); return { key, token };
}
/** Never reads/deletes the former global cache. Old bytes remain available to their previous app. */
export function accountChatStorage(scope: { key: string; token: string }): WorkspaceStorage {
  const current = () => { if (scope.token !== getAuthToken()) throw new Error('Account changed.'); };
  return {
    async getItem(key) { current(); if (key.includes('jeeves-chat:v2')) return null; const value = await AsyncStorage.getItem('@tutolage/jeeves-account:v2:' + scope.key); current(); if (value && value.length > 12 * 1024 * 1024) throw new Error('The chat cache exceeds its bound.'); return value; },
    async setItem(_key, value) { current(); if (value.length > 12 * 1024 * 1024) throw new Error('The chat cache exceeds its bound.'); await AsyncStorage.setItem('@tutolage/jeeves-account:v2:' + scope.key, value); current(); },
  };
}
async function getThread(threadId: string, signal?: AbortSignal): Promise<ConversationThread> {
  const result = await read(api.get<{ thread: ConversationThread }>('/api/v1/conversations/' + id(threadId), opts(signal)), getAuthToken(), 'The canonical conversation could not be loaded.'); return thread(result.thread, threadId);
}
async function messages(threadId: string, signal?: AbortSignal): Promise<ConversationMessage[]> {
  const output: ConversationMessage[] = []; const seen = new Set<string>(); let after = 0; let bytes = 0;
  for (let page = 0; page < 21; page++) {
    const result = await read(api.get<{ thread_id: string; messages: ConversationMessage[]; next_after_sequence: number | null }>('/api/v1/conversations/' + id(threadId) + '/messages?active_only=true&limit=500&after_sequence=' + after, opts(signal)), getAuthToken(), 'Canonical conversation history is unavailable.');
    if (result.thread_id !== threadId || !Array.isArray(result.messages) || result.messages.length > 500) invalid('The canonical history page is invalid.');
    for (const row of result.messages) {
      if (!row || !ID.test(row.message_id) || seen.has(row.message_id) || row.thread_id !== threadId || !Number.isSafeInteger(row.sequence) || row.sequence <= after || typeof row.idempotency_key !== 'string' || row.content != null && (typeof row.content !== 'string' || row.content.length > 100000)) invalid('The canonical history contains an invalid or repeated message.');
      bytes += new TextEncoder().encode(JSON.stringify(row)).byteLength;
      if (bytes > 8 * 1024 * 1024 || output.length >= 10000) invalid('The canonical transcript exceeds the supported 10,000-message / 8 MB bound.');
      seen.add(row.message_id); output.push(row); after = row.sequence;
    }
    if (result.next_after_sequence === null) return output;
    if (!result.messages.length || result.next_after_sequence !== after || !Number.isSafeInteger(result.next_after_sequence)) invalid('The canonical history page cursor did not advance exactly.');
  }
  invalid('The canonical transcript exceeds its page bound.');
}
export async function canonicalChatHistory(threadId: string, signal?: AbortSignal): Promise<ChatHistoryProjection> {
  let rows: ConversationMessage[] = []; let header: ConversationThread | null = null;
  for (let attempt = 0; attempt < 2; attempt++) {
    const before = await getThread(threadId, signal); rows = await messages(threadId, signal); const after = await getThread(threadId, signal);
    if (before.version === after.version && before.active_branch_id === after.active_branch_id && before.message_sequence === after.message_sequence) { header = after; break; }
  }
  if (!header) throw new ChatClientError('The conversation changed while it was being read. Refresh its current branch.', { kind: 'conflict', code: 'conversation_snapshot_changed' });
  validateConversationProjection(header, rows);
  const byId = new Map(rows.map(row => [row.message_id, row]));
  const turns = rows.filter(row => row.author_type === 'assistant').map(assistant => {
    const user = byId.get(assistant.causal_user_message_id || '');
    if (!user || user.author_type !== 'user' || !user.content || !assistant.content || user.sequence >= assistant.sequence) invalid('A canonical assistant message has no matching user turn.');
    return { session_id: threadId, client_message_id: user.idempotency_key, role_user: user.content, role_jeeves: assistant.content, status: 'complete', ts: Date.parse(user.created_at) / 1000, canonical_thread_id: threadId, canonical_user_message_id: user.message_id, canonical_assistant_message_id: assistant.message_id };
  });
  const complete = new Set(turns.map(turn => turn.canonical_user_message_id));
  const pending_turns = rows.filter(row => row.author_type === 'user' && !complete.has(row.message_id)).map(user => ({ client_message_id: user.idempotency_key, text: user.content || '', created_at: Date.parse(user.created_at), terminal: rows.some(marker => marker.author_type === 'system-derived' && (marker.causal_user_message_id || marker.parent_message_id) === user.message_id && marker.artifact_refs?.some(ref => ref.startsWith('chat-terminal:'))) }));
  return { ok: true, available: true, session_id: threadId, canonical_thread_id: threadId, turns, pending_turns, thread_title: header.title, thread_state: header.state };
}
export async function canonicalChatLibrary(signal?: AbortSignal): Promise<Conversation[]> {
  const result = await read(api.get<{ threads: ConversationThread[] }>('/api/v1/conversations?limit=30&include_archived=true', opts(signal)), getAuthToken(), 'Saved server conversations could not be loaded.');
  if (!Array.isArray(result.threads) || result.threads.length > MAX_CONVERSATIONS) invalid('The conversation library is invalid.');
  return result.threads.map(raw => {
    const header = thread(raw);
    return { ...createConversation(), id: header.thread_id, sessionId: header.thread_id, canonicalThreadId: header.thread_id, title: header.title, archived: header.state === 'archived', createdAt: Date.parse(header.created_at), updatedAt: Date.parse(header.updated_at) };
  });
}
async function getTurn(threadId: string, key: string, signal?: AbortSignal): Promise<Turn> {
  const value = await read(api.get<Turn>(ROOT + '/turns/' + id(threadId) + '?idempotency_key=' + encodeURIComponent(key), opts(signal)), getAuthToken(), 'The saved turn could not be checked.'); return checkTurn(value, threadId, key);
}
function finalResponse(value: Turn, threadId: string): ChatResponse | null {
  if (value.terminal && value.state !== 'completed' || value.success === false) throw new ChatTerminalError(value.state || 'failed');
  if (!value.assistant_message) return null;
  if (!value.user_message || !value.thread || !value.response || value.response !== value.assistant_message.content || value.response.length > 100000) invalid('The final answer is not a committed canonical message.');
  return { ok: true, persisted: true, reply: value.response, session_id: threadId, canonical_thread_id: threadId, canonical_message_id: value.assistant_message.message_id, model: value.model, operation_id: value.operation_id, ai_result_id: value.ai_result_id };
}
function wait(ms: number, signal: AbortSignal): Promise<void> { return new Promise((resolve, reject) => { if (signal.aborted) { reject(new Error('Request detached.')); return; } const stop = () => { clearTimeout(timer); reject(new Error('Request detached.')); }; const timer = setTimeout(() => { signal.removeEventListener('abort', stop); resolve(); }, ms); signal.addEventListener('abort', stop, { once: true }); }); }
function checkEvent(value: StreamEvent, cursor: ChatCursor | null): ChatCursor {
  if (!value || !ID.test(value.operation_id) || !Number.isSafeInteger(value.sequence) || value.sequence < 1 || !HASH.test(value.event_digest) || typeof value.to_state !== 'string'
    || cursor && (value.operation_id !== cursor.operation_id || value.sequence !== cursor.last_seen_sequence + 1 || value.previous_event_digest !== cursor.last_event_digest)
    || !cursor && (value.sequence !== 1 || value.previous_event_digest !== null)) invalid('The chat event cursor is discontinuous. Reopen the canonical turn before continuing.');
  return { operation_id: value.operation_id, last_seen_sequence: value.sequence, last_event_digest: value.event_digest };
}
function progress(value: Turn, threadId: string, cursor?: ChatCursor | null): ChatProgress { return { threadId, state: value.cancellation_requested ? 'cancelling' : value.state || value.turn_state || 'accepted', accepted: value.accepted === true, serverResumeAvailable: value.server_resume_available === true, ...(cursor ? { cursor } : {}) }; }
async function streamTurn(threadId: string, key: string, cursor: ChatCursor | null, signal: AbortSignal, update: (value: ChatProgress) => Promise<void>): Promise<{ cursor: ChatCursor | null; final: Turn | null }> {
  if (signal.aborted) throw new ChatClientError('Live following detached.', { kind: 'cancelled' });
  if (Platform.OS !== 'web' || typeof ReadableStream === 'undefined') return { cursor, final: null };
  const current = new AbortController(); const stop = () => current.abort(); signal.addEventListener('abort', stop, { once: true }); const timer = setTimeout(stop, 25000); const token = getAuthToken(); let reader: ReadableStreamDefaultReader<Uint8Array> | null = null;
  try {
    const headers = authHeaders({ Accept: 'text/event-stream', ...(cursor ? { 'Last-Event-ID': `${cursor.last_seen_sequence}:${cursor.last_event_digest}` } : {}) });
    const query = new URLSearchParams({ idempotency_key: key }); if (cursor) { query.set('after_sequence', String(cursor.last_seen_sequence)); query.set('last_event_digest', cursor.last_event_digest || ''); }
    const response = await fetch(API_BASE + ROOT + '/turns/' + id(threadId) + '/stream?' + query, { headers, signal: current.signal });
    if (token !== getAuthToken()) throw new ChatClientError('Your account changed.', { kind: 'authorization' });
    if ([401, 403].includes(response.status)) throw new ChatClientError('Your account can no longer follow this turn.', { kind: 'authorization', status: response.status });
    if (response.status === 409) invalid('The saved stream cursor no longer matches the canonical turn. Check server state.');
    if (!response.ok || !response.body || !response.headers.get('Content-Type')?.includes('text/event-stream')) return { cursor, final: null };
    reader = response.body.getReader(); const decoder = new TextDecoder(); let buffer = ''; let total = 0;
    while (!current.signal.aborted) {
      const chunk = await reader.read(); if (token !== getAuthToken()) throw new ChatClientError('Your account changed.', { kind: 'authorization' }); if (chunk.done) break;
      total += chunk.value.byteLength; if (total > 2 * 1024 * 1024) invalid('The chat event stream exceeded its bound.'); buffer += decoder.decode(chunk.value, { stream: true }).replaceAll('\r\n', '\n');
      if (buffer.length > 512 * 1024) invalid('A chat event exceeded its bound.');
      let boundary = buffer.indexOf('\n\n');
      while (boundary >= 0) {
        const block = buffer.slice(0, boundary); buffer = buffer.slice(boundary + 2); const lines = block.split('\n'); const event = lines.find(line => line.startsWith('event:'))?.slice(6).trim(); const data = lines.filter(line => line.startsWith('data:')).map(line => line.slice(5).trimStart()).join('\n');
        if (data && event === 'chat.event') { const value = JSON.parse(data) as StreamEvent; cursor = checkEvent(value, cursor); const wireId = lines.find(line => line.startsWith('id:'))?.slice(3).trim(); if (wireId !== `${cursor.last_seen_sequence}:${cursor.last_event_digest}`) invalid('The chat stream event ID differs from its cursor.'); await update({ threadId, state: value.to_state, accepted: true, transport: 'stream', cursor }); }
        if (data && event === 'chat.final') return { cursor, final: checkTurn(JSON.parse(data), threadId, key) };
        boundary = buffer.indexOf('\n\n');
      }
    }
    return { cursor, final: null };
  } catch (err) { if (signal.aborted || err instanceof ChatClientError && ['protocol', 'authorization'].includes(err.kind)) throw err; return { cursor, final: null }; }
  finally { clearTimeout(timer); signal.removeEventListener('abort', stop); current.abort(); if (reader) await reader.cancel().catch(() => {}); }
}
/** Only final canonical answers are returned. Transition events are never presented as token output. */
export async function sendCanonicalChat(body: ChatBody, signal: AbortSignal, update: (value: ChatProgress) => Promise<void> = async () => {}): Promise<ChatResponse> {
  if (body.image_base64 || body.pdf_base64 || body.force_all_forms) throw new ChatClientError('Canonical chat currently accepts text and explicit knowledge context. Image/PDF and all-forms generation are not supported here.', { kind: 'validation', retryable: false });
  const key = body.client_message_id; if (!key || !ID.test(key)) invalid('A stable message identity is required.');
  let threadId = body.canonical_thread_id;
  if (!threadId) {
    const result = await read(api.post<{ thread: ConversationThread }>('/api/v1/conversations', { title: body.message.slice(0, 70), data_class: 'confidential' }, opts(signal)), getAuthToken(), 'The conversation could not be created. No chat generation was submitted.');
    threadId = thread(result.thread).thread_id; await update({ threadId, state: 'prepared', accepted: false });
  }
  const actualThread = threadId; let value: Turn | null = null;
  if (body.resume_existing) {
    try { value = await getTurn(actualThread, key, signal); }
    catch (err) { if (!(err instanceof ChatClientError) || err.status !== 404) throw err; if (body.resume_only) throw new ChatClientError('This saved turn is no longer on the active conversation branch. Start a new conversation rather than rebuilding its missing request.', { kind: 'conflict', retryable: false }); }
    if (value) { const final = finalResponse(value, actualThread); if (final) return final; if (value.server_resume_available) value = checkTurn(await read(api.post<Turn>(ROOT + '/turns/' + id(actualThread) + '/resume', { idempotency_key: key, response_mode: 'deferred' }, opts(signal)), getAuthToken(), 'The saved command could not be resumed.'), actualThread, key); }
  }
  if (!value) {
    const header = await getThread(actualThread, signal); if (header.state !== 'active') throw new ChatClientError('This canonical conversation is not writable. Start a new conversation.', { kind: 'conflict' });
    const request = { message: body.message, thread_id: actualThread, idempotency_key: key, expected_thread_version: header.version, context: body.context || undefined, response_mode: 'deferred', provider_id: body.provider_id, model_id: body.model_id, max_output_tokens: body.max_output_tokens, crawler_context: body.crawler_context };
    try { value = checkTurn(await read(api.post<Turn>(ROOT, request, opts(signal)), getAuthToken(), 'Chat admission was not confirmed. Check the server before retrying this exact turn.'), actualThread, key); }
    catch (err) { if (signal.aborted) throw err; try { value = await getTurn(actualThread, key, signal); } catch { throw err; } }
  }
  let cursor: ChatCursor | null = body.resume_cursor || null;
  if (cursor && value.operation_id && cursor.operation_id !== value.operation_id) invalid('The saved event cursor belongs to another chat operation.');
  await update(progress(value, actualThread, cursor));
  if (value.server_resume_available && value.accepted !== true) throw new ChatClientError('Your command is saved and waiting for engine admission. Use Resume to retry the same saved command.', { kind: 'unavailable', code: 'awaiting_admission' });
  let final = finalResponse(value, actualThread); if (final) return final;
  const deadline = Date.now() + 10 * 60 * 1000; let streamed = false; let readFailures = 0;
  while (!signal.aborted && Date.now() < deadline) {
    if (!streamed) { streamed = true; const stream = await streamTurn(actualThread, key, cursor, signal, update); cursor = stream.cursor; if (stream.final) { final = finalResponse(stream.final, actualThread); if (final) return final; } }
    try { value = await getTurn(actualThread, key, signal); readFailures = 0; }
    catch (err) {
      if (!signal.aborted && err instanceof ChatClientError && ['network', 'timeout', 'unavailable'].includes(err.kind) && readFailures < 3) {
        readFailures++; await update({ threadId: actualThread, state: 'reconnecting', accepted: true, ...(cursor ? { cursor } : {}) }); await wait(1000 * 2 ** readFailures, signal); continue;
      }
      throw err;
    }
    await update({ ...progress(value, actualThread, cursor), transport: 'poll' }); final = finalResponse(value, actualThread); if (final) return final;
    if (value.server_resume_available && value.accepted !== true) throw new ChatClientError('The saved command is waiting for admission. Use Resume when the engine is ready.', { kind: 'unavailable', code: 'awaiting_admission' });
    await wait(2000, signal);
  }
  throw new ChatClientError('Live following stopped. The saved turn remains on the server; use Resume or Check server to reconnect.', { kind: 'timeout' });
}
export async function cancelCanonicalChat(threadId: string, key: string): Promise<void> {
  const result = await read(api.post<Turn>(ROOT + '/turns/' + id(threadId) + '/cancel', { idempotency_key: key, reason: 'user-requested-stop' }, opts()), getAuthToken(), 'Stop was not confirmed. The server may still be running; check the saved turn.');
  if (typeof result.cancellation_requested !== 'boolean' && result.terminal !== true) invalid('The server did not confirm the cancellation request.');
}

export async function archiveCanonicalChat(threadId: string, archived: boolean): Promise<void> {
  const header = await getThread(threadId);
  if (header.state === (archived ? 'archived' : 'active')) return;
  const value = await read(api.patch<{ thread: ConversationThread }>('/api/v1/conversations/' + id(threadId) + '/state', { state: archived ? 'archived' : 'active', expected_thread_version: header.version }, opts()), getAuthToken(), 'The conversation state could not be changed. Refresh and try again.');
  if (thread(value.thread, threadId).state !== (archived ? 'archived' : 'active')) invalid('The canonical conversation state was not confirmed.');
}
export async function renameCanonicalChat(threadId: string, title: string): Promise<void> {
  const header = await getThread(threadId);
  if (header.title === title) return;
  const value = await read(api.patch<{ thread: ConversationThread }>('/api/v1/conversations/' + id(threadId) + '/metadata', { title, expected_thread_version: header.version }, opts()), getAuthToken(), 'The conversation title could not be saved. Refresh and try again.');
  if (thread(value.thread, threadId).title !== title) invalid('The canonical title was not confirmed.');
}
export async function deleteCanonicalChat(threadId: string): Promise<void> {
  const header = await getThread(threadId);
  const value = await read(api.delete<{ thread: ConversationThread; deletion_state: string; complete: boolean }>('/api/v1/conversations/' + id(threadId) + '?expected_thread_version=' + header.version, opts()), getAuthToken(), 'Conversation deletion was not confirmed. Refresh before trying again.');
  if (value.complete !== true || value.deletion_state !== 'deleted' || thread(value.thread, threadId).state !== 'deleted') invalid('The server did not confirm complete conversation deletion.');
}

export type CanonicalChatExport = { filename: string; mediaType: string; content: string; messageCount: number; snapshotVersion: number };
export async function exportCanonicalChat(threadId: string, format: 'json' | 'markdown'): Promise<CanonicalChatExport> {
  const token = getAuthToken(); const header = await getThread(threadId);
  const value = await read(api.get<{ schema_version: string; thread_id: string; snapshot_version: number; scope: string; format: string; filename: string; media_type: string; content: string; content_digest: string; message_count: number; attachments_embedded: boolean }>('/api/v1/conversations/' + id(threadId) + '/export?format=' + format + '&expected_thread_version=' + header.version, opts()), token, 'The authorized conversation export could not be read. Refresh and retry.');
  if (!value || !['skeleton.chat.export.v1', 'skeleton.conversation.export.v1'].includes(value.schema_version) || value.thread_id !== threadId || value.snapshot_version !== header.version || value.scope !== 'canonical_active_lineage' || value.format !== format || value.attachments_embedded !== false || !Number.isSafeInteger(value.message_count) || value.message_count < 0 || value.message_count > 10000 || typeof value.filename !== 'string' || value.filename.length > 256 || typeof value.content !== 'string' || new TextEncoder().encode(value.content).byteLength > 8 * 1024 * 1024 || !HASH.test(value.content_digest) || typeof value.media_type !== 'string' || value.media_type.split(';')[0].trim() !== (format === 'json' ? 'application/json' : 'text/markdown')) invalid('The canonical conversation export is invalid.');
  if (await digestStringAsync(CryptoDigestAlgorithm.SHA256, value.content) !== value.content_digest) invalid('The exported conversation bytes changed.');
  if (token !== getAuthToken()) throw new ChatClientError('Your account changed before the export completed.', { kind: 'authorization' });
  return { filename: value.filename, mediaType: value.media_type, content: value.content, messageCount: value.message_count, snapshotVersion: value.snapshot_version };
}
