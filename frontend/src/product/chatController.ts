import AsyncStorage from '@react-native-async-storage/async-storage';
import { getAuthToken, resolveStorageTenantIdentity } from '../auth/gameforgeAuth';
import {
  cancelConversationTurn, resumeConversationTurn, createConversation, editConversationMessage,
  getConversationRecovery, getConversationTurn, listConversationPage,
  reconstructConversation, renameConversation,
  requestConversationDeletion, updateConversationState, getConversationExport, type ConversationExport,
  type ConversationMessage, type ConversationRequestOptions,
  type ConversationThread, type ConversationTurn, type ConversationTurnMemoryPolicy, type ConversationRecovery,
} from './governedConversationClient';
import {
  followChatTurn, getChatModels, submitChatTurn, validateChatTurn,
  startRegenerationTurn, getRegenerationTurn, resumeRegenerationTurn, cancelRegenerationTurn, followRegenerationTurn,
  type ChatEngineProgress, type ChatModel,
} from './aiChatClient';
import { ChatClientError, asChatError } from './chatErrors';

export type PendingChatTurn = {
  kind: 'chat' | 'regeneration';
  messageId?: string;
  threadId: string;
  idempotencyKey: string;
  message: string;
  context?: string;
  attachmentRefs: string[];
  streamText: string;
  lastEventId: number;
  state: string;
  startedAt: string;
  operationId?: string | null;
  executionId?: string | null;
  progress?: ChatEngineProgress | null;
  accepted: boolean;
  serverResumeAvailable?: boolean;
};

export type ChatControllerState = {
  ready: boolean;
  threads: ConversationThread[];
  activeThread: ConversationThread | null;
  messages: ConversationMessage[];
  models: ChatModel[];
  selectedModelId: string | null;
  status: 'loading' | 'idle' | 'submitting' | 'streaming' | 'reconnecting' | 'cancelling' | 'error';
  pending: PendingChatTurn | null;
  error: ChatClientError | null;
  notice: string | null;
  hasMoreThreads: boolean;
};

export type ChatControllerOptions = {
  initialThreadId?: string;
  headers?: Record<string, string>;
};
export type SendChatOptions = {
  context?: string;
  attachmentRefs?: string[];
  memoryPolicy?: ConversationTurnMemoryPolicy;
  maxOutputTokens?: number;
  temperature?: number;
};

type PendingReference = { threadId: string; idempotencyKey: string; lastEventId: number; kind?: 'chat' | 'regeneration'; messageId?: string };
type SavedSelection = {
  schema_version: 1;
  activeThreadId: string | null;
  selectedModelId: string | null;
  pendingTurns: PendingReference[];
};
type Submission = {
  thread: ConversationThread;
  pending: PendingChatTurn;
  model: ChatModel | null;
  options: SendChatOptions;
};

function newKey(prefix: string): string {
  const cryptoObject = (globalThis as { crypto?: { randomUUID?: () => string } }).crypto;
  return prefix + ':' + (cryptoObject?.randomUUID?.() ?? Date.now().toString(36) + '-' + Math.random().toString(36).slice(2));
}

function sortedThreads(threads: ConversationThread[]): ConversationThread[] {
  return [...threads].sort((a, b) => b.updated_at.localeCompare(a.updated_at) || a.thread_id.localeCompare(b.thread_id));
}

/** Device state is a rebuildable view, never a transcript or execution authority. */
export class ChatController {
  private snapshot: ChatControllerState = {
    ready: false, threads: [], activeThread: null, messages: [], models: [],
    selectedModelId: null, status: 'loading', pending: null, error: null,
    notice: null, hasMoreThreads: false,
  };
  private listeners = new Set<() => void>();
  private initializing: Promise<void> | null = null;
  private disposed = false;
  private activeRead: AbortController | null = null;
  private listRead: AbortController | null = null;
  private lifetime = new AbortController();
  private observing: AbortController | null = null;
  private selectionEpoch = 0;
  private listEpoch = 0;
  private listCursor: string | null = null;
  private listQuery = '';
  private includeArchived = false;
  private storageKey: string | null = null;
  private authToken: string | null = null;
  private pendingReferences = new Map<string, PendingReference>();
  private submission: Submission | null = null;
  private mutationRetry: (() => Promise<void>) | null = null;
  private nextSave: { key: string; value: string } | null = null;
  private saving = false;
  private saveTimer: ReturnType<typeof setTimeout> | null = null;
  private sending = false;
  private cancellationRequests = new Set<string>();
  private regenerationAdmitting = false;
  private regenerationSubmission: { thread: ConversationThread; messageId: string; key: string; model: ChatModel | null } | null = null;

  constructor(private options: ChatControllerOptions = {}) {}

  getSnapshot = (): ChatControllerState => this.snapshot;
  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  private emit(patch: Partial<ChatControllerState>): void {
    if (this.disposed) return;
    if (this.authToken !== null && getAuthToken() !== this.authToken) {
      this.observing?.abort(); this.activeRead?.abort(); this.listRead?.abort(); this.lifetime.abort();
      this.snapshot = { ...this.snapshot, ready: false, threads: [], activeThread: null, messages: [],
        pending: null, models: [], status: 'error', error: new ChatClientError('Sign in again to continue.', { kind: 'authorization' }) };
      this.listeners.forEach(listener => listener());
      return;
    }
    this.snapshot = { ...this.snapshot, ...patch };
    this.listeners.forEach(listener => listener());
  }

  private request(signal?: AbortSignal): ConversationRequestOptions {
    return { headers: this.options.headers, signal: signal ?? this.lifetime.signal };
  }

  private async identity(): Promise<void> {
    const identity = await resolveStorageTenantIdentity();
    const key = 'canonical-chat-ui:v1:' + encodeURIComponent(identity.tenantId) + ':' + encodeURIComponent(identity.principalId);
    if (this.storageKey && this.storageKey !== key) {
      this.observing?.abort(); this.activeRead?.abort();
      throw new ChatClientError('Account changed. Reopen chat to continue.', { kind: 'authorization' });
    }
    const token = getAuthToken();
    for (const [header, value] of Object.entries(this.options.headers ?? {})) {
      if ((header.toLowerCase() === 'authorization' && value !== (token ? 'Bearer ' + token : ''))
        || header.toLowerCase() === 'cookie') {
        throw new ChatClientError('Chat authentication must use the current verified account.', { kind: 'authorization', code: 'identity_header_mismatch' });
      }
    }
    this.storageKey = key;
    this.authToken = token;
  }

  private assertSession(): void {
    if (this.disposed || this.authToken === null || getAuthToken() !== this.authToken) {
      throw new ChatClientError('Account changed before this request completed.', { kind: 'authorization', code: 'account_changed' });
    }
  }

  private saveSelection(): void {
    if (!this.storageKey || this.disposed) return;
    const key = this.storageKey;
    const value: SavedSelection = {
      schema_version: 1,
      activeThreadId: this.snapshot.activeThread?.thread_id ?? null,
      selectedModelId: this.snapshot.selectedModelId,
      pendingTurns: [...this.pendingReferences.values()].slice(-32),
    };
    // Coalesce high-frequency delta cursors into one in-flight write and one latest value.
    this.nextSave = { key, value: JSON.stringify(value) };
    if (!this.saveTimer) this.saveTimer = setTimeout(() => {
      this.saveTimer = null;
      void this.flushSelection();
    }, 250);
  }

  private async flushSelection(): Promise<void> {
    if (this.saving) return;
    this.saving = true;
    try {
      while (this.nextSave) {
        const next = this.nextSave;
        this.nextSave = null;
        try { await AsyncStorage.setItem(next.key, next.value); }
        catch { this.emit({ notice: 'Reply progress is live, but this device could not save its reconnect position.' }); }
      }
    } finally { this.saving = false; }
  }

  private async readSelection(): Promise<SavedSelection | null> {
    if (!this.storageKey) return null;
    try {
      const raw = await AsyncStorage.getItem(this.storageKey);
      if (!raw || raw.length > 65536) return null;
      const value = JSON.parse(raw) as SavedSelection;
      if (value.schema_version !== 1 || !Array.isArray(value.pendingTurns) || value.pendingTurns.length > 32) return null;
      for (const pending of value.pendingTurns) {
        if (typeof pending.threadId !== 'string' || pending.threadId.length > 64
          || typeof pending.idempotencyKey !== 'string' || pending.idempotencyKey.length > 1024
          || !Number.isSafeInteger(pending.lastEventId) || pending.lastEventId < 0
          || (pending.kind !== undefined && pending.kind !== 'chat' && pending.kind !== 'regeneration')
          || (pending.kind === 'regeneration' && (typeof pending.messageId !== 'string' || !pending.messageId || pending.messageId.length > 64))) return null;
      }
      return value;
    } catch { return null; }
  }

  initialize = (): Promise<void> => {
    if (!this.disposed && !this.initializing && this.authToken !== null && getAuthToken() !== this.authToken) {
      this.selectionEpoch += 1; this.listEpoch += 1;
      this.observing?.abort(); this.activeRead?.abort(); this.listRead?.abort(); this.lifetime.abort();
      this.lifetime = new AbortController();
      this.storageKey = null; this.authToken = null; this.pendingReferences.clear();
      this.submission = null; this.regenerationSubmission = null; this.mutationRetry = null;
      this.cancellationRequests.clear();
      this.emit({ ready: false, activeThread: null, messages: [], threads: [], pending: null,
        models: [], selectedModelId: null, status: 'loading', error: null, notice: null });
    }
    if (this.initializing) return this.initializing;
    if (this.snapshot.ready && !(this.snapshot.status === 'error' && !this.snapshot.activeThread && !this.snapshot.threads.length)) return Promise.resolve();
    this.initializing = this.load().finally(() => { this.initializing = null; });
    return this.initializing;
  };

  private async load(): Promise<void> {
    this.emit({ status: 'loading', error: null });
    try {
      await this.identity();
      const saved = await this.readSelection();
      for (const pending of saved?.pendingTurns ?? []) this.pendingReferences.set(pending.threadId, pending);
      const [catalogResult, pageResult] = await Promise.allSettled([
        getChatModels(this.request()), listConversationPage({ ...this.request(), limit: 50 }),
      ]);
      if (pageResult.status === 'rejected') throw pageResult.reason;
      const models = catalogResult.status === 'fulfilled' ? catalogResult.value.models : [];
      const selected = models.find(model => model.id === saved?.selectedModelId && model.selectable && model.available)
        ?? models.find(model => model.active && model.selectable && model.available);
      this.listCursor = pageResult.value.nextCursor;
      this.emit({ ready: true, threads: sortedThreads(pageResult.value.threads), models,
        selectedModelId: selected?.id ?? null, status: 'idle', hasMoreThreads: !!this.listCursor,
        notice: catalogResult.status === 'rejected' ? 'Model availability could not be loaded. Refresh before selecting a model.' : null });
      const threadId = this.options.initialThreadId ?? saved?.activeThreadId ?? pageResult.value.threads[0]?.thread_id;
      if (threadId) await this.openConversation(threadId);
      else this.saveSelection();
    } catch (error) { this.emit({ ready: true, status: 'error', error: asChatError(error) }); }
  }

  refreshThreads = async (input: { query?: string; includeArchived?: boolean; loadMore?: boolean } = {}): Promise<void> => {
    const epoch = ++this.listEpoch;
    this.listRead?.abort();
    const readController = new AbortController(); this.listRead = readController;
    try {
      await this.identity();
      const query = input.query ?? this.listQuery;
      const includeArchived = input.includeArchived ?? this.includeArchived;
      const loadMore = input.loadMore && query === this.listQuery && includeArchived === this.includeArchived;
      const page = await listConversationPage({ ...this.request(readController.signal), query, includeArchived,
        cursor: loadMore ? this.listCursor ?? undefined : undefined, limit: 50 });
      if (epoch !== this.listEpoch || this.disposed) return;
      this.listQuery = query; this.includeArchived = includeArchived; this.listCursor = page.nextCursor;
      const threads = loadMore ? [...this.snapshot.threads, ...page.threads] : page.threads;
      const unique = [...new Map(threads.map(thread => [thread.thread_id, thread])).values()];
      this.emit({ threads: sortedThreads(unique), hasMoreThreads: !!page.nextCursor });
    } catch (error) {
      const failure = asChatError(error);
      if (epoch === this.listEpoch && failure.kind !== 'cancelled') this.emit({ error: failure });
    }
  };

  private upsertThread(thread: ConversationThread): void {
    this.emit({ threads: sortedThreads([thread, ...this.snapshot.threads.filter(item => item.thread_id !== thread.thread_id)]),
      ...(this.snapshot.activeThread?.thread_id === thread.thread_id ? { activeThread: thread } : {}) });
  }

  openConversation = async (threadId: string): Promise<void> => {
    const epoch = ++this.selectionEpoch;
    this.activeRead?.abort(); this.observing?.abort();
    const controller = new AbortController(); this.activeRead = controller;
    this.submission = null; this.regenerationSubmission = null; this.mutationRetry = null;
    this.emit({ status: 'loading', error: null, pending: null, messages: [], activeThread: null });
    try {
      await this.identity();
      const snapshot = await reconstructConversation(threadId, this.request(controller.signal));
      if (epoch !== this.selectionEpoch) return;
      this.emit({ activeThread: snapshot.thread, messages: snapshot.messages, status: 'idle' });
      this.upsertThread(snapshot.thread); this.saveSelection();
      const savedReference = this.pendingReferences.get(threadId);
      let key = savedReference?.kind === 'regeneration' ? undefined : savedReference?.idempotencyKey;
      let recovery: ConversationRecovery | null = null;
      try {
        recovery = await getConversationRecovery(threadId, this.request(controller.signal));
        if (epoch !== this.selectionEpoch) return;
        key = recovery.pending_turn?.idempotency_key ?? key;
      } catch (error) {
        const failure = asChatError(error);
        if (failure.kind === 'authorization' || failure.kind === 'cancelled') throw failure;
        // Older servers still support exact pending keys saved on this device.
      }
      const regenerationReferences = recovery?.pending_turn ? []
        : savedReference?.kind === 'regeneration'
          ? [{ messageId: savedReference.messageId, key: savedReference.idempotencyKey }]
          : [...(recovery?.regeneration_requests ?? [])].reverse().slice(0, 32)
            .map(reference => ({ messageId: reference.message_id, key: reference.idempotency_key }));
      for (const reference of regenerationReferences) {
        if (!reference.messageId) continue;
        const turn = await getRegenerationTurn(threadId, reference.messageId, reference.key, this.request(controller.signal));
        if (epoch !== this.selectionEpoch) return;
        if (turn.terminal) {
          if (turn.success || savedReference?.kind === 'regeneration') { await this.settle(turn, epoch); return; }
          continue;
        }
        const pending = this.pendingFromTurn(threadId, reference.key, turn, { kind: 'regeneration', messageId: reference.messageId });
        this.emit({ pending, status: turn.accepted === false ? 'error' : 'streaming',
          error: turn.accepted === false ? new ChatClientError('Regeneration is saved. Resume to submit it.', { kind: 'unavailable', code: 'awaiting_admission' }) : null });
        this.rememberPending(pending);
        if (pending.accepted) void this.observe(pending, epoch).catch(() => {});
        return;
      }
      if (key) {
        const turn = validateChatTurn(await getConversationTurn(threadId, key, this.request(controller.signal)), threadId, key);
        if (epoch !== this.selectionEpoch) return;
        if (turn.terminal) { await this.settle(turn, epoch); return; }
        const pending = this.pendingFromTurn(threadId, key, turn);
        if (!pending.accepted && !turn.server_resume_available && turn.user_message?.supersedes_message_id) {
          this.submission = { thread: snapshot.thread, pending,
            model: this.snapshot.models.find(model => model.id === this.snapshot.selectedModelId) ?? null,
            options: { attachmentRefs: turn.user_message.attachment_refs.filter(ref => ref.startsWith('chat-attachment://')) } };
        }
        this.emit({ pending, status: pending.accepted ? 'streaming' : 'error',
          error: pending.accepted ? null : new ChatClientError('This turn is saved. Resume to submit it.', { kind: 'unavailable', code: 'awaiting_admission' }) });
        this.rememberPending(pending);
        if (pending.accepted) void this.observe(pending, epoch).catch(() => {});
      }
    } catch (error) {
      const failure = asChatError(error);
      if (epoch === this.selectionEpoch && failure.kind !== 'cancelled') { this.emit({ status: 'error', error: failure }); throw failure; }
    }
  };

  private pendingFromTurn(threadId: string, key: string, turn: ConversationTurn, identity: { kind: 'chat' | 'regeneration'; messageId?: string } = { kind: 'chat' }): PendingChatTurn {
    return { ...identity, threadId, idempotencyKey: key, message: turn.user_message?.content ?? '',
      attachmentRefs: turn.user_message?.attachment_refs ?? [], streamText: '',
      // No transcript bytes are persisted. Rebuild provisional output from durable events on remount.
      lastEventId: 0,
      state: turn.state ?? 'running', startedAt: turn.user_message?.created_at ?? new Date().toISOString(),
      operationId: turn.operation_id, executionId: turn.engine_execution_id, accepted: turn.accepted !== false, serverResumeAvailable: turn.server_resume_available };
  }

  private rememberPending(pending: PendingChatTurn): void {
    this.pendingReferences.set(pending.threadId, { threadId: pending.threadId,
      idempotencyKey: pending.idempotencyKey, lastEventId: pending.lastEventId, kind: pending.kind, messageId: pending.messageId });
    while (this.pendingReferences.size > 32) this.pendingReferences.delete(this.pendingReferences.keys().next().value!);
    this.saveSelection();
  }

  newConversation = async (input: { title?: string } = {}): Promise<void> => {
    if (this.snapshot.status === 'submitting' && !this.sending) throw new ChatClientError('Another conversation update is running.', { kind: 'conflict' });
    try {
      await this.identity();
      const thread = await createConversation({ ...this.request(), title: input.title });
      this.upsertThread(thread);
      await this.openConversation(thread.thread_id);
    } catch (error) { const failure = asChatError(error); this.emit({ status: 'error', error: failure }); throw failure; }
  };

  send = async (message: string, options: SendChatOptions = {}): Promise<void> => {
    if (this.sending || this.snapshot.pending || ['submitting', 'cancelling', 'loading'].includes(this.snapshot.status)) {
      throw new ChatClientError('Wait for this reply or stop it before sending another message.', { kind: 'conflict' });
    }
    if (!message.trim() || message.length > 100000) throw new ChatClientError('Enter a message of up to 100,000 characters.', { kind: 'validation' });
    if ((options.context?.length ?? 0) > 100000 || (options.attachmentRefs?.length ?? 0) > 4
      || new Set(options.attachmentRefs ?? []).size !== (options.attachmentRefs?.length ?? 0)
      || options.attachmentRefs?.some(ref => !/^chat-attachment:\/\/[0-9a-f-]{36}$/.test(ref))
      || (options.maxOutputTokens !== undefined && (!Number.isSafeInteger(options.maxOutputTokens) || options.maxOutputTokens < 1))
      || (options.temperature !== undefined && (!Number.isFinite(options.temperature) || options.temperature < 0 || options.temperature > 2))) {
      throw new ChatClientError('Context, attachment references or generation settings are invalid.', { kind: 'validation' });
    }
    this.sending = true;
    try {
      await this.identity();
      if (!this.snapshot.activeThread) await this.newConversation({ title: message.trim().slice(0, 80) || 'New conversation' });
      let thread = this.snapshot.activeThread;
      if (!thread) throw new ChatClientError('Create a conversation before sending.', { kind: 'unavailable' });
      if (thread.state !== 'active') throw new ChatClientError('Restore this archived conversation before sending.', { kind: 'validation' });
      if (thread.message_sequence === 0 && thread.title === 'New conversation') {
        thread = await renameConversation(thread, message.trim().replace(/\s+/g, ' ').slice(0, 80), this.request());
        this.upsertThread(thread);
      }
      const model = this.snapshot.models.find(item => item.id === this.snapshot.selectedModelId) ?? null;
      const pending: PendingChatTurn = { kind: 'chat', threadId: thread.thread_id, idempotencyKey: newKey('chat'), message,
        context: options.context, attachmentRefs: [...(options.attachmentRefs ?? [])], streamText: '',
        lastEventId: 0, state: 'submitting', startedAt: new Date().toISOString(), accepted: false };
      this.submission = { thread, pending, model, options: { ...options, attachmentRefs: [...pending.attachmentRefs] } };
      this.mutationRetry = null;
      this.emit({ pending, status: 'submitting', error: null, notice: null });
      this.rememberPending(pending);
      await this.submit(this.submission, this.selectionEpoch);
    } catch (error) { const failure = asChatError(error); this.emit({ status: 'error', error: failure }); throw failure; }
    finally { this.sending = false; }
  };

  private async submit(submission: Submission, epoch: number): Promise<void> {
    this.observing?.abort();
    const controller = new AbortController(); this.observing = controller;
    try {
      const turn = await submitChatTurn(submission.thread, { ...this.request(controller.signal),
        ...submission.options, message: submission.pending.message, idempotencyKey: submission.pending.idempotencyKey,
        model: submission.model });
      if (epoch !== this.selectionEpoch || controller.signal.aborted) return;
      if (turn.thread) this.upsertThread(turn.thread);
      if (turn.user_message) this.mergeMessages([turn.user_message]);
      if (turn.terminal) { await this.settle(turn, epoch); return; }
      const pending = { ...submission.pending, accepted: turn.accepted !== false, state: turn.state ?? 'running',
        operationId: turn.operation_id, executionId: turn.engine_execution_id };
      submission.pending = pending;
      if (!pending.accepted) {
        this.emit({ pending, status: 'error', error: new ChatClientError('This turn is saved. Resume to submit it.', { kind: 'unavailable', code: 'awaiting_admission' }) });
        this.rememberPending(pending);
        return;
      }
      this.emit({ pending, status: this.cancellationRequests.has(pending.idempotencyKey) ? 'cancelling' : 'streaming' }); this.rememberPending(pending);
      if (this.cancellationRequests.has(pending.idempotencyKey)) { await this.cancel(); return; }
      void this.observe(pending, epoch).catch(() => {});
    } catch (error) {
      const failure = asChatError(error);
      if (epoch === this.selectionEpoch && failure.kind !== 'cancelled') { this.emit({ status: 'error', error: failure }); throw failure; }
    }
  }

  private mergeMessages(messages: ConversationMessage[]): void {
    const threadId = this.snapshot.activeThread?.thread_id;
    if (messages.some(message => message.thread_id !== threadId)) throw new ChatClientError('A foreign conversation message was returned.');
    const merged = [...new Map([...this.snapshot.messages, ...messages].map(message => [message.message_id, message])).values()]
      .sort((left, right) => left.sequence - right.sequence);
    this.emit({ messages: merged });
  }

  private async observe(pending: PendingChatTurn, epoch: number): Promise<void> {
    this.observing?.abort();
    const controller = new AbortController(); this.observing = controller;
    const current = () => epoch === this.selectionEpoch && !controller.signal.aborted
      && this.snapshot.pending?.idempotencyKey === pending.idempotencyKey;
    const updatePending = (patch: Partial<PendingChatTurn>) => {
      if (!current() || !this.snapshot.pending) return;
      const next = { ...this.snapshot.pending, ...patch };
      this.emit({ pending: next });
      if (patch.lastEventId !== undefined) this.rememberPending(next);
    };
    try {
      const followOptions = {
        ...this.request(controller.signal), lastEventId: pending.lastEventId,
        executionId: pending.executionId, operationId: pending.operationId, provisionalText: pending.streamText,
        onConnection: (state: import('./aiChatClient').ChatStreamConnection) => { if (current()) this.emit({ status: this.snapshot.status === 'cancelling' ? 'cancelling'
          : state === 'reconnecting' || state === 'resyncing' ? 'reconnecting' : 'streaming' }); },
        onCursor: (lastEventId: number) => updatePending({ lastEventId }),
        onText: (streamText: string) => updatePending({ streamText }),
        onProgress: (progress: ChatEngineProgress) => updatePending({ progress,
          state: typeof progress.payload.state === 'string' ? progress.payload.state : progress.type }),
        onTurn: (value: ConversationTurn) => { if (current() && value.state) updatePending({ state: value.state }); },
      };
      const turn = pending.kind === 'regeneration'
        ? await followRegenerationTurn(pending.threadId, pending.messageId!, pending.idempotencyKey, followOptions)
        : await followChatTurn(pending.threadId, pending.idempotencyKey, followOptions);
      if (current()) await this.settle(turn, epoch);
    } catch (error) {
      const failure = asChatError(error);
      if (current() && failure.kind !== 'cancelled') { this.emit({ status: 'error', error: failure }); throw failure; }
    }
  }

  private async settle(turn: ConversationTurn, epoch: number): Promise<void> {
    if (epoch !== this.selectionEpoch) return;
    const threadId = turn.thread?.thread_id ?? this.snapshot.activeThread?.thread_id;
    if (!threadId) return;
    this.pendingReferences.delete(threadId);
    if (this.snapshot.pending) this.cancellationRequests.delete(this.snapshot.pending.idempotencyKey);
    this.submission = null; this.regenerationSubmission = null;
    if (turn.thread) this.upsertThread(turn.thread);
    this.mergeMessages([turn.user_message, turn.assistant_message, turn.terminal_message].filter(Boolean) as ConversationMessage[]);
    this.emit({ pending: null, status: turn.success ? 'idle' : 'error',
      error: turn.success ? null : new ChatClientError(turn.state === 'cancelled' || turn.state === 'withdrawn' ? 'Reply stopped.' : 'The reply could not be completed.', {
        kind: turn.state === 'cancelled' || turn.state === 'withdrawn' ? 'cancelled' : 'execution', code: turn.failure_code ?? turn.state ?? 'execution_failed', retryable: false,
      }) });
    this.saveSelection();
    try {
      const snapshot = await reconstructConversation(threadId, this.request());
      if (epoch === this.selectionEpoch) this.emit({ activeThread: snapshot.thread, messages: snapshot.messages });
    } catch { if (epoch === this.selectionEpoch) this.emit({ notice: 'Reply settled. Refresh to load the latest complete transcript.' }); }
  }

  cancel = async (): Promise<void> => {
    const pending = this.snapshot.pending;
    if (!pending) return;
    const epoch = this.selectionEpoch;
    this.cancellationRequests.add(pending.idempotencyKey);
    this.emit({ status: 'cancelling', error: null });
    if (!pending.accepted && (this.sending || this.regenerationAdmitting)) return;
    try {
      await this.identity();
      // Admission may have succeeded even if its HTTP response was interrupted.
      const turn = pending.kind === 'regeneration'
        ? await cancelRegenerationTurn(pending.threadId, pending.messageId!, pending.idempotencyKey, this.request())
        : await cancelConversationTurn(pending.threadId, pending.idempotencyKey, this.request());
      if (epoch !== this.selectionEpoch) return;
      if (turn.terminal) {
        const final = pending.kind === 'regeneration'
          ? await getRegenerationTurn(pending.threadId, pending.messageId!, pending.idempotencyKey, this.request())
          : validateChatTurn(await getConversationTurn(pending.threadId, pending.idempotencyKey, this.request()), pending.threadId, pending.idempotencyKey);
        await this.settle(final, epoch);
      } else {
        const observed = { ...pending, accepted: turn.accepted !== false, state: turn.state ?? pending.state,
          operationId: turn.operation_id ?? pending.operationId, executionId: turn.engine_execution_id ?? pending.executionId };
        this.emit({ pending: observed }); this.rememberPending(observed);
        if (observed.accepted) await this.observe(observed, epoch);
        else {
          const failure = new ChatClientError('The saved request has not reached engine admission. Stop could not be confirmed yet.', { kind: 'unavailable', code: 'cancellation_unconfirmed' });
          this.emit({ status: 'error', error: failure }); throw failure;
        }
      }
    } catch (error) {
      const failure = asChatError(error);
      if (epoch === this.selectionEpoch) { this.emit({ status: 'error', error: failure }); throw failure; }
    }
  };

  retry = async (): Promise<void> => {
    if (this.mutationRetry) { await this.mutationRetry(); return; }
    const pending = this.snapshot.pending;
    if (!pending) { await this.refreshConversation(); return; }
    const epoch = this.selectionEpoch;
    this.emit({ error: null, status: pending.accepted ? 'reconnecting' : 'submitting' });
    try {
      await this.identity();
      let turn = pending.kind === 'regeneration'
        ? await getRegenerationTurn(pending.threadId, pending.messageId!, pending.idempotencyKey, this.request())
        : validateChatTurn(await getConversationTurn(pending.threadId, pending.idempotencyKey, this.request()), pending.threadId, pending.idempotencyKey);
      if (turn.accepted === false && !turn.terminal) {
        if (pending.kind === 'regeneration') {
          turn = await resumeRegenerationTurn(pending.threadId, pending.messageId!, pending.idempotencyKey, this.request());
        } else if (turn.server_resume_available) {
          turn = validateChatTurn(await resumeConversationTurn(pending.threadId, pending.idempotencyKey, this.request()), pending.threadId, pending.idempotencyKey);
        } else if (this.submission) {
          await this.submit(this.submission, epoch);
          return;
        } else {
          throw new ChatClientError('This saved turn needs its original request settings before it can resume.', {
            kind: 'conflict', code: 'original_request_required', retryable: false,
          });
        }
      }
      if (epoch !== this.selectionEpoch) return;
      if (turn.terminal) { await this.settle(turn, epoch); return; }
      const recovered = { ...pending, accepted: turn.accepted !== false, operationId: turn.operation_id, executionId: turn.engine_execution_id };
      if (!recovered.accepted) {
        const failure = new ChatClientError('The saved request is awaiting admission. Resume again when the engine is available.', { kind: 'unavailable', code: 'awaiting_admission' });
        this.emit({ pending: recovered, status: 'error', error: failure }); throw failure;
      }
      this.emit({ pending: recovered });
      if (this.cancellationRequests.has(recovered.idempotencyKey)) await this.cancel();
      else void this.observe(recovered, epoch).catch(() => {});
    } catch (error) {
      const failure = asChatError(error);
      if (epoch !== this.selectionEpoch) return;
      if (failure.status === 404 && pending.kind === 'regeneration' && this.regenerationSubmission && !pending.accepted) await this.admitRegeneration(this.regenerationSubmission, pending, epoch);
      else if (failure.status === 404 && this.submission && !pending.accepted) await this.submit(this.submission, epoch);
      else { this.emit({ status: 'error', error: failure }); throw failure; }
    }
  };

  refreshConversation = async (): Promise<void> => {
    const threadId = this.snapshot.activeThread?.thread_id;
    if (threadId) await this.openConversation(threadId);
    else await this.initialize();
  };

  selectModel = (modelId: string | null): void => {
    if (modelId !== null && !this.snapshot.models.some(model => model.id === modelId && model.available && model.selectable)) {
      this.emit({ error: new ChatClientError('This model is unavailable.', { kind: 'unavailable', retryable: false }) }); return;
    }
    this.emit({ selectedModelId: modelId, error: null }); this.saveSelection();
  };

  refreshModels = async (): Promise<void> => {
    try {
      await this.identity();
      const catalog = await getChatModels(this.request());
      const selected = catalog.models.find(model => model.id === this.snapshot.selectedModelId && model.selectable && model.available);
      this.emit({ models: catalog.models, selectedModelId: selected?.id ?? null, error: null }); this.saveSelection();
    } catch (error) { this.emit({ error: asChatError(error) }); }
  };

  edit = async (messageId: string, content: string): Promise<void> => {
    const thread = this.snapshot.activeThread;
    if (!thread || this.snapshot.pending) return;
    const key = newKey('edit'); const epoch = this.selectionEpoch;
    const execute = async () => {
      this.emit({ status: 'submitting', error: null });
      try {
        await this.identity();
        const edited = await editConversationMessage(thread, messageId, { ...this.request(), content, idempotencyKey: key });
        if (epoch !== this.selectionEpoch) return;
        const snapshot = await reconstructConversation(thread.thread_id, this.request());
        if (epoch !== this.selectionEpoch) return;
        this.mutationRetry = null;
        this.emit({ activeThread: snapshot.thread, messages: snapshot.messages });
        this.upsertThread(snapshot.thread);
        const attachmentRefs = edited.message.attachment_refs.filter(ref => ref.startsWith('chat-attachment://'));
        const pending: PendingChatTurn = {
          kind: 'chat', threadId: thread.thread_id, idempotencyKey: key, message: content,
          attachmentRefs, streamText: '', lastEventId: 0, state: 'submitting',
          startedAt: edited.message.created_at, accepted: false,
        };
        this.submission = { thread: snapshot.thread, pending,
          model: this.snapshot.models.find(item => item.id === this.snapshot.selectedModelId) ?? null,
          options: { attachmentRefs } };
        this.emit({ pending, status: 'submitting' }); this.rememberPending(pending);
        await this.submit(this.submission, epoch);
      } catch (error) { if (epoch === this.selectionEpoch) { const failure = asChatError(error); this.emit({ status: 'error', error: failure }); throw failure; } }
    };
    this.mutationRetry = execute; await execute();
  };

  regenerate = async (messageId: string): Promise<void> => {
    const thread = this.snapshot.activeThread;
    if (!thread || this.snapshot.pending || this.snapshot.status === 'submitting') {
      throw new ChatClientError('Finish the current reply before regenerating.', { kind: 'conflict' });
    }
    const message = this.snapshot.messages.find(item => item.message_id === messageId);
    if (!message || message.author_type !== 'assistant') {
      throw new ChatClientError('Choose an assistant reply to regenerate.', { kind: 'validation' });
    }
    const key = newKey('regenerate'); const epoch = this.selectionEpoch;
    const pending: PendingChatTurn = {
      kind: 'regeneration', messageId, threadId: thread.thread_id, idempotencyKey: key,
      message: '', attachmentRefs: [], streamText: '', lastEventId: 0,
      state: 'submitting', startedAt: new Date().toISOString(), accepted: false,
    };
    this.regenerationSubmission = { thread, messageId, key,
      model: this.snapshot.models.find(item => item.id === this.snapshot.selectedModelId) ?? null };
    this.mutationRetry = null; this.submission = null;
    this.emit({ pending, status: 'submitting', error: null }); this.rememberPending(pending);
    await this.admitRegeneration(this.regenerationSubmission, pending, epoch);
  };

  private async admitRegeneration(
    request: { thread: ConversationThread; messageId: string; key: string; model: ChatModel | null },
    pending: PendingChatTurn, epoch: number,
  ): Promise<void> {
    this.regenerationAdmitting = true;
    try {
      await this.identity();
      const turn = await startRegenerationTurn(request.thread, request.messageId, {
        ...this.request(), idempotencyKey: request.key, model: request.model,
      });
      if (epoch !== this.selectionEpoch) return;
      if (turn.terminal) { await this.settle(turn, epoch); return; }
      const accepted = { ...pending, accepted: turn.accepted !== false, state: turn.state ?? 'running',
        operationId: turn.operation_id, executionId: turn.engine_execution_id };
      if (!accepted.accepted) {
        this.emit({ pending: accepted, status: 'error', error: new ChatClientError('Regeneration is saved. Resume to submit it.', { kind: 'unavailable', code: 'awaiting_admission' }) });
        this.rememberPending(accepted);
        return;
      }
      this.emit({ pending: accepted, status: 'streaming' }); this.rememberPending(accepted);
      if (this.cancellationRequests.has(accepted.idempotencyKey)) { await this.cancel(); return; }
      void this.observe(accepted, epoch).catch(() => {});
    } catch (error) {
      const failure = asChatError(error);
      if (epoch === this.selectionEpoch) { this.emit({ status: 'error', error: failure }); throw failure; }
    } finally { this.regenerationAdmitting = false; }
  }

  rename = async (title: string): Promise<void> => {
    const thread = this.snapshot.activeThread;
    if (!thread || this.snapshot.pending) return;
    try { await this.identity(); this.upsertThread(await renameConversation(thread, title, this.request())); this.emit({ error: null }); }
    catch (error) { const failure = asChatError(error); this.emit({ error: failure }); throw failure; }
  };

  archive = async (archived = true): Promise<void> => {
    const thread = this.snapshot.activeThread;
    if (!thread || this.snapshot.pending) return;
    try { await this.identity(); this.upsertThread(await updateConversationState(thread, archived ? 'archived' : 'active', this.request())); this.emit({ error: null }); }
    catch (error) { const failure = asChatError(error); this.emit({ error: failure }); throw failure; }
  };

  remove = async (): Promise<void> => {
    const thread = this.snapshot.activeThread;
    if (!thread || this.snapshot.pending) return;
    try {
      await this.identity(); await requestConversationDeletion(thread, this.request());
      this.pendingReferences.delete(thread.thread_id);
      this.emit({ threads: this.snapshot.threads.filter(item => item.thread_id !== thread.thread_id), activeThread: null, messages: [], error: null });
      this.saveSelection();
    } catch (error) { const failure = asChatError(error); this.emit({ error: failure }); throw failure; }
  };

  exportConversation = async (format: 'json' | 'markdown'): Promise<ConversationExport> => {
    const thread = this.snapshot.activeThread;
    if (!thread) throw new ChatClientError('Open a conversation before exporting.', { kind: 'validation' });
    try {
      await this.identity();
      // Export admission, source rights and rendering are all server-owned.
      const result = await getConversationExport(thread, format, this.request());
      this.assertSession();
      return result;
    } catch (error) {
      const failure = asChatError(error); this.emit({ error: failure }); throw failure;
    }
  };

  dismissError = (): void => this.emit({ error: null, status: this.snapshot.pending ? 'error' : 'idle' });
  dismissNotice = (): void => this.emit({ notice: null });

  dispose = (): void => {
    this.disposed = true; this.selectionEpoch += 1; this.listEpoch += 1;
    this.observing?.abort(); this.activeRead?.abort(); this.listRead?.abort(); this.lifetime.abort(); this.listeners.clear();
    if (this.saveTimer) clearTimeout(this.saveTimer);
    this.saveTimer = null;
    void this.flushSelection();
  };
}
