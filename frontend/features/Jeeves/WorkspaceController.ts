import {
  WORKSPACE_KEY, LEGACY_KEY, MAX_TEXT, MAX_REPLY, MAX_CONTEXT, MAX_MESSAGES, MAX_CONVERSATIONS,
  addConversation, buildChatBody, createWorkspace, decodeWorkspace, deleteConversation,
  encodeWorkspace, migrateLegacy, newId, projectCanonicalHistory, updateConversation,
} from './workspace';
import type {
  Artifact, Attachment, CanonicalChatTurn, ChatBody, ChatHistoryProjection,
  Conversation, Message, Workspace,
} from './workspace';
import type { ChatHandoff } from './workbench/types';

export interface WorkspaceStorage {
  getItem(key: string): Promise<string | null>;
  setItem(key: string, value: string): Promise<void>;
}

export type ChatResponse = {
  ok?: boolean;
  session_id?: string;
  reply?: string;
  tier?: string;
  model?: string;
  forms?: string[];
  artifacts?: Artifact[];
  persisted?: boolean;
  canonical_thread_id?: string | null;
  canonical_message_id?: string | null;
  operation_id?: string | null;
  ai_result_id?: string | null;
};

export type ChatProgress = { threadId: string; state: string; accepted?: boolean; transport?: 'stream' | 'poll'; serverResumeAvailable?: boolean; cursor?: NonNullable<ChatBody['resume_cursor']> };
export type Transport = (body: ChatBody, signal: AbortSignal, update?: (value: ChatProgress) => Promise<void>) => Promise<ChatResponse>;
export type ChatHistoryTurn = CanonicalChatTurn;
export type ChatHistoryResponse = ChatHistoryProjection;
export type HistoryTransport = (
  sessionId: string,
) => Promise<ChatHistoryResponse>;

export type WorkspaceSnapshot = {
  workspace: Workspace;
  ready: boolean;
  loadError: string | null;
  saveState: 'loading' | 'saving' | 'saved' | 'error';
  notice: string | null;
  busyId: string | null;
  progress: ChatProgress | null;
};

type Running = {
  controller: AbortController;
  conversationId: string;
  messageId: string;
};

/** Single writer, observable store; transport and storage are injectable for race tests. */
export class WorkspaceController {
  private snapshot: WorkspaceSnapshot = {
    workspace: createWorkspace(), ready: false, loadError: null,
    saveState: 'loading', notice: null, busyId: null, progress: null,
  };
  private listeners = new Set<() => void>();
  private running: Running | null = null;
  private nextSave: string | null = null;
  private saving = false;
  private loading: Promise<void> | null = null;
  private attachments = new Map<string, Attachment>();
  /** Fence duplicate manual retries while authoritative history is being checked. */
  private retrying = new Set<string>();
  private threadChanges = new Set<string>();

  constructor(
    private storage: WorkspaceStorage,
    private transport: Transport,
    private historyTransport?: HistoryTransport,
    private hooks: { cancel?: (threadId: string, messageId: string) => Promise<void>; library?: () => Promise<Conversation[]>; archive?: (threadId: string, archived: boolean) => Promise<void>; remove?: (threadId: string) => Promise<void>; rename?: (threadId: string, title: string) => Promise<void> } = {},
  ) {}

  getSnapshot = (): WorkspaceSnapshot => this.snapshot;

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => { this.listeners.delete(listener); };
  };

  private emit(patch: Partial<WorkspaceSnapshot>): void {
    this.snapshot = { ...this.snapshot, ...patch };
    this.listeners.forEach(listener => listener());
  }

  initialize(): Promise<void> {
    if (this.snapshot.ready) return Promise.resolve();
    if (this.loading) return this.loading;
    this.loading = this.load().finally(() => { this.loading = null; });
    return this.loading;
  }

  private async hydrateConversation(
    conversation: Conversation,
  ): Promise<Conversation> {
    if (!this.historyTransport || !conversation.sessionId) return conversation;
    const result = await this.historyTransport(conversation.sessionId);
    if (
      result.ok === false
      || result.available === false
      || result.session_id !== conversation.sessionId
      || !Array.isArray(result.turns)
    ) {
      throw new Error('canonical conversation history unavailable');
    }
    return projectCanonicalHistory(
      conversation,
      result,
    );
  }

  private async rehydrateServerTranscripts(
    workspace: Workspace,
  ): Promise<{ workspace: Workspace; failed: number }> {
    if (!this.historyTransport) return { workspace, failed: 0 };

    let failed = 0;
    const conversations: Conversation[] = [];
    for (let offset = 0; offset < workspace.conversations.length; offset += 3) {
      const group = await Promise.all(workspace.conversations.slice(offset, offset + 3).map(async conversation => {
        if (!conversation.sessionId) return conversation;
        try {
          return await this.hydrateConversation(conversation);
        } catch {
          failed += 1;
          return conversation;
        }
      }));
      conversations.push(...group);
    }
    return {
      workspace: { ...workspace, conversations },
      failed,
    };
  }

  private async load(): Promise<void> {
    this.emit({ loadError: null, saveState: 'loading' });
    try {
      const saved = await this.storage.getItem(WORKSPACE_KEY);
      const legacy = saved === null ? await this.storage.getItem(LEGACY_KEY) : null;
      let local = saved !== null ? decodeWorkspace(saved)
        : legacy !== null ? migrateLegacy(legacy) : this.snapshot.workspace;
      let libraryFailed = false;
      if (this.hooks.library) {
        try {
          const remote = await this.hooks.library();
          const bound = new Set(local.conversations.map(item => item.canonicalThreadId).filter(Boolean));
          const extra = remote.filter(item => !bound.has(item.canonicalThreadId));
          const meaningful = local.conversations.filter(item => item.messages.length || item.draft || item.context || item.canonicalThreadId);
          const conversations = [...meaningful, ...extra].slice(0, MAX_CONVERSATIONS);
          if (conversations.length) local = { ...local, conversations, activeId: conversations.some(item => item.id === local.activeId) ? local.activeId : conversations[0].id };
        } catch { libraryFailed = true; }
      }
      const hydrated = await this.rehydrateServerTranscripts(local);
      let opened = hydrated.workspace;
      if (opened.conversations.find(item => item.id === opened.activeId)?.archived) {
        const active = opened.conversations.find(item => !item.archived);
        if (active) opened = { ...opened, activeId: active.id };
        else if (opened.conversations.length < MAX_CONVERSATIONS) opened = addConversation(opened);
      }
      this.emit({
        workspace: opened,
        ready: true,
        saveState: 'saved',
        notice: hydrated.failed || libraryFailed
          ? 'Some chats could not be refreshed from the server. Showing the last device cache for those chats.'
          : null,
      });
      // Local persistence is a rebuildable cache plus drafts/workspace metadata.
      this.queueSave();
    } catch {
      this.emit({
        ready: false, saveState: 'error',
        loadError: 'Saved chats could not be opened. Your stored data has been left intact. Retry after checking device storage.',
      });
    }
  }

  private change(workspace: Workspace): void {
    if (!this.snapshot.ready) return;
    this.emit({ workspace });
    this.queueSave();
  }

  private queueSave(): void {
    if (!this.snapshot.ready) return;
    this.nextSave = encodeWorkspace(this.snapshot.workspace);
    this.emit({ saveState: 'saving' });
    void this.flush();
  }

  private async flush(): Promise<void> {
    if (this.saving) return;
    this.saving = true;
    try {
      while (this.nextSave !== null) {
        const value = this.nextSave;
        this.nextSave = null;
        try {
          await this.storage.setItem(WORKSPACE_KEY, value);
          if (this.nextSave === null) this.emit({ saveState: 'saved' });
        } catch {
          this.nextSave = null;
          this.emit({ saveState: 'error', notice: 'Changes are still in memory but could not be saved. Free device storage, then retry saving.' });
          break;
        }
      }
    } finally {
      this.saving = false;
    }
  }

  retrySave = (): void => { this.queueSave(); };
  dismissNotice = (): void => { this.emit({ notice: null }); };
  notify = (notice: string): void => { this.emit({ notice }); };

  async refreshLibrary(): Promise<void> {
    if (!this.snapshot.ready || !this.hooks.library) return;
    try {
      const remote = await this.hooks.library();
      const byThread = new Map(remote.map(item => [item.canonicalThreadId, item]));
      const current = this.snapshot.workspace;
      const known = new Set(current.conversations.map(item => item.canonicalThreadId));
      const local = current.conversations.map(item => {
        const header = byThread.get(item.canonicalThreadId);
        return header ? { ...item, title: header.title, archived: header.archived, updatedAt: Math.max(item.updatedAt, header.updatedAt) } : item;
      });
      const extras = remote.filter(item => !known.has(item.canonicalThreadId));
      const conversations = [...local, ...extras].sort((a, b) => Number(b.id === current.activeId) - Number(a.id === current.activeId) || Number(b.pinned) - Number(a.pinned) || b.updatedAt - a.updatedAt).slice(0, MAX_CONVERSATIONS);
      this.change({ ...current, conversations });
      this.notify('Account conversation headers refreshed. Open a conversation to load its current server history.');
    } catch (error) { this.notify(error instanceof Error ? error.message : 'Account conversations could not be refreshed. The device cache is unchanged.'); }
  }

  async refreshCanonical(
    conversationId = this.snapshot.workspace.activeId,
  ): Promise<boolean> {
    if (!this.snapshot.ready || !this.historyTransport) return false;
    if (this.running?.conversationId === conversationId) return false;
    const current = this.snapshot.workspace.conversations.find(
      item => item.id === conversationId,
    );
    // The first turn uses the device conversation ID before the server returns a session ID.
    // Its reply may have committed even if the HTTP response was lost.
    if (!current || (!current.sessionId && !current.messages.length)) return false;
    if (!current.canonicalThreadId && !current.sessionId) return true;
    const sessionId = current.sessionId || current.id;
    try {
      const result = await this.historyTransport(sessionId);
      if (
        result.ok === false
        || result.available === false
        || result.session_id !== sessionId
        || !Array.isArray(result.turns)
      ) {
        return false;
      }
      const latest = this.snapshot.workspace.conversations.find(
        item => item.id === conversationId,
      );
      if (
        !latest
        || latest !== current
        || (latest.sessionId || latest.id) !== sessionId
        || this.running?.conversationId === conversationId
      ) {
        return false;
      }
      const projection = projectCanonicalHistory(latest, result);
      this.change(updateConversation(
        this.snapshot.workspace,
        conversationId,
        () => projection,
      ));
      return true;
    } catch {
      return false;
    }
  }

  get active(): Conversation {
    return this.snapshot.workspace.conversations.find(c => c.id === this.snapshot.workspace.activeId)!;
  }

  edit(patch: Partial<Pick<Conversation, 'title' | 'draft' | 'context' | 'allForms' | 'pinned'>>): void {
    const safe = { ...patch };
    if (safe.title !== undefined) safe.title = safe.title.trim().slice(0, 100) || 'Untitled conversation';
    if (safe.draft !== undefined) safe.draft = safe.draft.slice(0, MAX_TEXT);
    if (safe.context !== undefined) safe.context = safe.context.slice(0, MAX_CONTEXT);
    this.change(updateConversation(this.snapshot.workspace, this.active.id, c => ({ ...c, ...safe })));
  }

  create(): void {
    if (!this.snapshot.ready) return;
    try {
      const workspace = addConversation(this.snapshot.workspace);
      this.detach();
      this.change({
        ...workspace,
        // cancel() may have marked the previous conversation's turn cancelled.
        conversations: [workspace.conversations[0], ...this.snapshot.workspace.conversations],
      });
    } catch (error) {
      this.notify(error instanceof Error ? error.message : 'Could not create a conversation.');
    }
  }

  /** Import into a separate conversation, with a persisted receipt for safe retries. */
  acceptHandoff(handoff: ChatHandoff): boolean {
    if (!this.snapshot.ready) return false;
    const existing = this.snapshot.workspace.conversations.find(item => item.handoffId === handoff.id);
    if (existing) {
      this.select(existing.id);
      return true;
    }
    try {
      const workspace = addConversation(this.snapshot.workspace);
      this.detach();
      const conversation = {
        ...workspace.conversations[0],
        handoffId: handoff.id,
        title: handoff.projectTitle.slice(0, 100) || 'Project discussion',
        draft: handoff.draft.slice(0, MAX_TEXT),
        context: handoff.context.slice(0, MAX_CONTEXT),
      };
      this.change({ ...workspace, conversations: [conversation, ...this.snapshot.workspace.conversations] });
      this.notify('Project draft opened. Review its context in Details, then send when ready.');
      return true;
    } catch (error) {
      this.notify(error instanceof Error ? error.message : 'Could not open the project draft.');
      return false;
    }
  }

  whenSaved(): Promise<boolean> {
    if (this.snapshot.saveState !== 'saving') return Promise.resolve(this.snapshot.saveState === 'saved');
    return new Promise(resolve => {
      const unsubscribe = this.subscribe(() => {
        if (this.snapshot.saveState === 'saving') return;
        unsubscribe();
        resolve(this.snapshot.saveState === 'saved');
      });
    });
  }

  select(id: string): void {
    if (!this.snapshot.workspace.conversations.some(c => c.id === id)) return;
    if (id !== this.active.id) this.detach();
    const selected = this.snapshot.workspace.conversations.find(item => item.id === id);
    if (selected?.archived) { this.notify('Restore the canonical conversation before opening it.'); return; }
    this.change({ ...this.snapshot.workspace, activeId: id });
    void this.refreshCanonical(id);
  }

  async saveDetails(title: string, context: string): Promise<boolean> {
    const current = this.active;
    if (this.threadChanges.has(current.id) || this.running?.conversationId === current.id) return false;
    this.threadChanges.add(current.id);
    try {
      const normalized = title.trim().slice(0, 100) || 'Untitled conversation';
      if (current.canonicalThreadId && this.hooks.rename) await this.hooks.rename(current.canonicalThreadId, normalized);
      this.change(updateConversation(this.snapshot.workspace, current.id, item => ({ ...item, title: normalized, context: context.slice(0, MAX_CONTEXT) })));
      return true;
    } catch (error) { this.notify(error instanceof Error ? error.message : 'The title could not be saved.'); return false; }
    finally { this.threadChanges.delete(current.id); }
  }

  async remove(id: string): Promise<void> {
    if (this.threadChanges.has(id) || this.running?.conversationId === id) { this.notify('Stop or detach the active turn before deleting this conversation.'); return; }
    const removed = this.snapshot.workspace.conversations.find(c => c.id === id); if (!removed) return;
    this.threadChanges.add(id);
    try {
      if (removed.canonicalThreadId && this.hooks.remove) await this.hooks.remove(removed.canonicalThreadId);
      removed.messages.forEach(m => this.attachments.delete(m.id));
      this.change(deleteConversation(this.snapshot.workspace, id));
    } catch (error) { this.notify(error instanceof Error ? error.message : 'Conversation deletion was not confirmed.'); }
    finally { this.threadChanges.delete(id); }
  }

  async archive(id: string, archived: boolean): Promise<void> {
    if (this.threadChanges.has(id) || this.running?.conversationId === id) { this.notify('Detach the active turn before archiving this conversation.'); return; }
    const current = this.snapshot.workspace.conversations.find(item => item.id === id); if (!current) return;
    this.threadChanges.add(id);
    try {
      if (current.canonicalThreadId && this.hooks.archive) await this.hooks.archive(current.canonicalThreadId, archived);
      let workspace = updateConversation(this.snapshot.workspace, id, c => ({ ...c, archived }));
      if (archived && workspace.activeId === id) {
        const next = workspace.conversations.find(c => !c.archived);
        if (next) workspace = { ...workspace, activeId: next.id };
        else {
          try { workspace = addConversation(workspace); }
          catch { this.notify('The server archived this conversation. Remove a cached chat to make room for a new one.'); }
        }
      }
      this.change(workspace);
    } catch (error) { this.notify(error instanceof Error ? error.message : 'The archive state could not be saved.'); }
    finally { this.threadChanges.delete(id); }
  }

  /** Navigation detaches the view; it never claims the server worker was cancelled. */
  detach = (): void => {
    const running = this.running;
    if (!running) return;
    this.running = null;
    running.controller.abort();
    this.setMessage(running.conversationId, running.messageId, { status: 'failed', error: 'Live following was detached. The server may still be running. Resume or check the saved turn.' });
    this.emit({ busyId: null, progress: null });
  };

  cancel = async (): Promise<void> => {
    const running = this.running;
    if (!running || this.snapshot.progress?.state === 'cancelling') return;
    const conversation = this.snapshot.workspace.conversations.find(item => item.id === running.conversationId);
    const threadId = conversation?.canonicalThreadId;
    if (!threadId || !this.hooks.cancel) { this.notify('The turn has not reached a cancellable canonical state. Check server status before trying again.'); return; }
    this.emit({ progress: { threadId, state: 'cancelling', accepted: true } });
    try { await this.hooks.cancel(threadId, running.messageId); if (this.running === running) this.notify('The server received Stop. Following continues until its actual terminal state is confirmed.'); }
    catch (error) { if (this.running === running) { this.emit({ progress: { threadId, state: 'cancellation_unconfirmed' } }); this.notify(error instanceof Error ? error.message : 'Stop was not confirmed. Check the saved turn.'); } }
  };

  async cancelSavedTurn(messageId: string): Promise<void> {
    const current = this.active; const message = current.messages.find(item => item.id === messageId && item.role === 'user');
    if (!message || message.terminal || !current.canonicalThreadId || !this.hooks.cancel) return;
    if (this.running?.messageId === messageId) { await this.cancel(); return; }
    try {
      await this.hooks.cancel(current.canonicalThreadId, messageId);
      await this.refreshCanonical(current.id);
      this.notify('The server received the cancellation request. Check server state to confirm its final outcome.');
    } catch (error) { this.notify(error instanceof Error ? error.message : 'Cancellation was not confirmed.'); }
  }

  private setMessage(conversationId: string, messageId: string, patch: Partial<Message>): void {
    this.change(updateConversation(this.snapshot.workspace, conversationId, c => ({
      ...c, messages: c.messages.map(m => m.id === messageId ? { ...m, ...patch } : m),
    })));
  }

  async send(attachment?: Attachment, preferences: Pick<ChatBody, 'provider_id' | 'model_id' | 'max_output_tokens' | 'crawler_context'> = {}): Promise<void> {
    if (!this.snapshot.ready || this.running) return;
    const conversation = this.active;
    if (conversation.archived) { this.notify('Restore this canonical conversation before sending another turn.'); return; }
    const tail = conversation.messages[conversation.messages.length - 1];
    if (tail?.role === 'user' && tail.status !== 'complete' && !tail.terminal) {
      if (attachment && tail.attachmentName
          && ['failed', 'cancelled'].includes(tail.status) && !tail.terminal
          && conversation.draft.trim() === tail.text) {
        await this.retry(tail.id, attachment);
        // Reconciliation may recover the answer without running the model.
        // Preserve any draft edited while that check or generation was in flight.
        this.change(updateConversation(this.snapshot.workspace, conversation.id, c => (
          c.draft.trim() === tail.text
          && c.messages.some(m => m.id === tail.id && m.status === 'complete')
            ? { ...c, draft: '' } : c
        )));
        return;
      }
      this.notify('Resolve the interrupted turn with Retry or Check server before sending another message. Your draft is preserved.');
      return;
    }
    const content = conversation.draft.trim() || (attachment ? `Analyze this ${attachment.modality}` : '');
    if (!content) return;
    const message: Message = {
      id: newId(), role: 'user', text: content, createdAt: Date.now(), status: 'pending', attachmentName: attachment?.name,
    };
    // Older failed turns can only be copied into a new draft, so their bytes are no longer needed.
    this.attachments.clear();
    if (attachment) this.attachments.set(message.id, attachment);
    const body = buildChatBody(
      conversation,
      content,
      attachment,
      Date.now(),
      message.id,
    );
    Object.assign(body, preferences);
    const { message: _message, client_message_id: _client, image_base64: _image, pdf_base64: _pdf, ...retryRequest } = body;
    message.retryRequest = retryRequest;
    this.change(updateConversation(this.snapshot.workspace, conversation.id, c => ({
      ...c, title: c.messages.length === 0 && c.title === 'New conversation' ? content.slice(0, 70) : c.title,
      draft: '', updatedAt: Date.now(), messages: [...c.messages, message].slice(-(MAX_MESSAGES - 1)),
    })));
    await this.execute(conversation.id, message.id, body);
  }

  async retry(messageId: string, replacementAttachment?: Attachment): Promise<void> {
    if (!this.snapshot.ready || this.running || this.retrying.has(messageId)) return;
    const conversation = this.active;
    const index = conversation.messages.findIndex(m => m.id === messageId && m.role === 'user');
    const message = conversation.messages[index];
    if (!message || message.terminal || !['failed', 'cancelled'].includes(message.status)) return;
    // Retrying an older turn would make the transcript order ambiguous.
    if (index !== conversation.messages.length - 1) {
      this.edit({ draft: message.text });
      this.notify('The earlier message is in your draft. Send it as a new turn.');
      return;
    }
    this.retrying.add(messageId);
    try {
      // An HTTP abort or timeout is not proof the backend failed to commit.
      // Read the canonical transcript BEFORE re-submitting the identical client ID.
      if (this.historyTransport) {
        const checked = await this.refreshCanonical(conversation.id);
        if (!checked) {
          this.notify('Canonical history is unavailable. Retry was not sent; check the connection and try again.');
          return;
        }
      }
      const current = this.snapshot.workspace.conversations.find(c => c.id === conversation.id);
      if (!current || this.active.id !== conversation.id || this.running) return;
      const last = current.messages[current.messages.length - 1];
      // A successful reconciliation is terminal. Do not generate a duplicate.
      if (!last || last.terminal || last.id !== messageId || last.status === 'complete'
          || !['failed', 'cancelled'].includes(last.status)) return;
      const attachment = replacementAttachment || this.attachments.get(messageId);
      if (last.attachmentName && !attachment) {
        this.edit({ draft: last.text });
        this.notify('Attachments are not saved on this device. Reattach the same file and send your restored draft to retry the original turn.');
        return;
      }
      const body = buildChatBody(
        { ...current, messages: current.messages.slice(0, -1) },
        last.text,
        attachment,
        Date.now(),
        last.id,
      );
      if (last.retryRequest) Object.assign(body, last.retryRequest);
      body.resume_existing = true;
      if (attachment) this.attachments.set(messageId, attachment);
      this.setMessage(conversation.id, messageId, { status: 'pending', error: undefined });
      await this.execute(conversation.id, messageId, body);
    } finally {
      this.retrying.delete(messageId);
    }
  }

  private async execute(conversationId: string, messageId: string, body: ChatBody): Promise<void> {
    const running: Running = { controller: new AbortController(), conversationId, messageId };
    this.running = running;
    this.emit({ busyId: conversationId, notice: null, progress: { threadId: body.canonical_thread_id || '', state: 'connecting' } });
    let deliveryUncertain = false;
    try {
      const response = await this.transport(body, running.controller.signal, async value => {
        if (this.running !== running || running.controller.signal.aborted) throw new Error('Request detached.');
        this.emit({ progress: value });
        const existing = this.snapshot.workspace.conversations.find(item => item.id === conversationId);
        const previousCursor = existing?.messages.find(item => item.id === messageId)?.retryRequest?.resume_cursor;
        if (existing?.canonicalThreadId !== value.threadId || value.cursor && (previousCursor?.last_seen_sequence !== value.cursor.last_seen_sequence || previousCursor.last_event_digest !== value.cursor.last_event_digest)) {
          this.change(updateConversation(this.snapshot.workspace, conversationId, conversation => ({ ...conversation, canonicalThreadId: value.threadId, sessionId: value.threadId,
            messages: conversation.messages.map(message => message.id === messageId ? { ...message, retryRequest: { ...message.retryRequest!, session_id: value.threadId, canonical_thread_id: value.threadId, ...(value.cursor ? { resume_cursor: value.cursor } : {}) } } : message) })));
        }
        // The actual thread binding must survive a reload before any model admission.
        if (value.state === 'prepared' && !await this.whenSaved()) throw new Error('The canonical thread reference could not be cached. Generation was not submitted.');
      });
      if (this.running !== running) return;
      if (response.ok === false || typeof response.reply !== 'string' || !response.reply.trim()) {
        throw new Error('Jeeves returned an empty response. Try again.');
      }
      const reply: Message = {
        id: response.canonical_message_id || newId(),
        role: 'jeeves',
        text: response.reply.slice(0, MAX_REPLY),
        status: 'complete',
        createdAt: Date.now(),
        tier: response.tier,
        model: response.model,
        forms: response.forms,
        artifacts: response.artifacts || [],
        artifactCount: response.artifacts?.length || 0,
      };
      this.change(updateConversation(this.snapshot.workspace, conversationId, c => ({
        ...c,
        canonicalThreadId: response.canonical_thread_id || c.canonicalThreadId,
        sessionId: response.session_id || c.sessionId,
        sessionUpdatedAt: Date.now(),
        updatedAt: Date.now(),
        messages: [
          ...c.messages.map(m => m.id === messageId ? {
            ...m,
            status: 'complete' as const,
            error: undefined,
            retryRequest: undefined,
          } : m),
          reply,
        ].slice(-MAX_MESSAGES),
      })));
      this.attachments.delete(messageId);
      if (response.persisted === false) this.notify('The server could not save this exchange. Your device-local transcript is still available.');
    } catch (error) {
      if (this.running !== running) return;
      deliveryUncertain = true;
      this.setMessage(conversationId, messageId, {
        status: 'failed', terminal: error instanceof Error && 'code' in error && error.code === 'chat_turn_terminal', error: error instanceof Error ? error.message.slice(0, 400) : 'Jeeves could not respond. Try again.',
      });
    } finally {
      if (this.running === running) {
        this.running = null;
        this.emit({ busyId: null, progress: null });
        if (deliveryUncertain && this.historyTransport) {
          // Reconciliation itself is part of the logical retry fence.
          // Another tap must not start generation while the first check is in flight.
          this.retrying.add(messageId);
          try {
            const checked = await this.refreshCanonical(conversationId);
            const latest = this.snapshot.workspace.conversations.find(c => c.id === conversationId);
            if (checked && latest?.messages.some(m => m.id === messageId && m.status === 'complete')) {
              this.notify('The reply was saved on the server and has been recovered.');
            }
          } finally {
            this.retrying.delete(messageId);
          }
        }
      }
    }
  }
}
