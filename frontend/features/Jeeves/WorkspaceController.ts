import {
  WORKSPACE_KEY, LEGACY_KEY, MAX_TEXT, MAX_CONTEXT, MAX_MESSAGES,
  addConversation, buildChatBody, createWorkspace, decodeWorkspace, deleteConversation,
  encodeWorkspace, migrateLegacy, newId, updateConversation,
} from './workspace';
import type { Artifact, Attachment, ChatBody, Conversation, Message, Workspace } from './workspace';
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
};

export type Transport = (body: ChatBody, signal: AbortSignal) => Promise<ChatResponse>;


export type AuthorityThread = {
  thread_id: string;
  title: string;
  created_at: string;
  updated_at: string;
  version: number;
  state: 'active' | 'archived' | 'deleting' | 'deleted';
  data_class: 'public' | 'internal' | 'confidential' | 'restricted';
};

export type AuthorityMessage = {
  message_id: string;
  sequence: number;
  author_type: 'user' | 'assistant' | 'tool' | 'system-derived';
  created_at: string;
  content?: string | null;
  operation_id?: string | null;
  ai_result_id?: string | null;
  artifact_refs?: string[];
};

export type AuthorityChatResult = {
  success: boolean;
  approval_required?: boolean;
  response?: string;
  engine_execution_id?: string;
  thread: AuthorityThread;
  user_message: AuthorityMessage;
  assistant_message?: AuthorityMessage;
  pending_approvals?: Array<{
    call_id: string;
    tool_id: string;
    arguments_digest: string;
  }>;
};

export interface ConversationAuthority {
  listThreads(): Promise<AuthorityThread[]>;
  createThread(title: string): Promise<AuthorityThread>;
  listMessages(threadId: string): Promise<AuthorityMessage[]>;
  chat(input: {
    threadId: string;
    expectedThreadVersion: number;
    message: string;
    idempotencyKey: string;
    context?: string;
    signal: AbortSignal;
  }): Promise<AuthorityChatResult>;
  setState(input: {
    threadId: string;
    expectedThreadVersion: number;
    state: 'active' | 'archived' | 'deleting';
  }): Promise<AuthorityThread>;
  requestDeletion(input: {
    threadId: string;
    expectedThreadVersion: number;
  }): Promise<AuthorityThread>;
}

export type WorkspaceSnapshot = {
  workspace: Workspace;
  ready: boolean;
  loadError: string | null;
  saveState: 'loading' | 'saving' | 'saved' | 'error';
  notice: string | null;
  busyId: string | null;
  serverSynced: boolean;
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
    saveState: 'loading', notice: null, busyId: null, serverSynced: false,
  };
  private listeners = new Set<() => void>();
  private running: Running | null = null;
  private nextSave: string | null = null;
  private saving = false;
  private loading: Promise<void> | null = null;
  private attachments = new Map<string, Attachment>();

  constructor(
    private storage: WorkspaceStorage,
    private transport: Transport,
    private authority?: ConversationAuthority,
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

  private async load(): Promise<void> {
    this.emit({ loadError: null, saveState: 'loading' });
    try {
      const saved = await this.storage.getItem(WORKSPACE_KEY);
      const legacy = saved === null ? await this.storage.getItem(LEGACY_KEY) : null;
      const workspace = saved !== null ? decodeWorkspace(saved)
        : legacy !== null ? migrateLegacy(legacy) : this.snapshot.workspace;
      this.emit({ workspace, ready: true, saveState: 'saved' });
      // Migration is additive: retain the legacy key as a recovery copy.
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
      this.cancel();
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
      this.cancel();
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
    if (id !== this.active.id) this.cancel();
    this.change({ ...updateConversation(this.snapshot.workspace, id, c => ({ ...c, archived: false })), activeId: id });
  }

  remove(id: string): void {
    if (this.running?.conversationId === id) this.cancel();
    const removed = this.snapshot.workspace.conversations.find(c => c.id === id);
    removed?.messages.forEach(m => this.attachments.delete(m.id));
    this.change(deleteConversation(this.snapshot.workspace, id));
  }

  archive(id: string, archived: boolean): void {
    if (this.running?.conversationId === id) this.cancel();
    let workspace = updateConversation(this.snapshot.workspace, id, c => ({ ...c, archived }));
    if (archived && workspace.activeId === id) {
      const next = workspace.conversations.find(c => !c.archived);
      if (next) workspace = { ...workspace, activeId: next.id };
      else {
        try { workspace = addConversation(workspace); }
        catch { this.notify('Keep one conversation open, or delete a chat to make room.'); return; }
      }
    }
    this.change(workspace);
  }

  cancel = (): void => {
    const running = this.running;
    if (!running) return;
    this.running = null;
    running.controller.abort();
    this.setMessage(running.conversationId, running.messageId, {
      status: 'cancelled', error: 'Response stopped. You can retry this message.',
    });
    this.emit({ busyId: null });
  };

  private setMessage(conversationId: string, messageId: string, patch: Partial<Message>): void {
    this.change(updateConversation(this.snapshot.workspace, conversationId, c => ({
      ...c, messages: c.messages.map(m => m.id === messageId ? { ...m, ...patch } : m),
    })));
  }

  async send(attachment?: Attachment): Promise<void> {
    if (!this.snapshot.ready || this.running) return;
    const conversation = this.active;
    const content = conversation.draft.trim() || (attachment ? `Analyze this ${attachment.modality}` : '');
    if (!content) return;
    if (conversation.messages.length > MAX_MESSAGES - 2) {
      this.notify('This conversation has reached 100 messages. Start a new chat; the existing transcript is preserved.');
      return;
    }
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
    this.change(updateConversation(this.snapshot.workspace, conversation.id, c => ({
      ...c, title: c.messages.length === 0 && c.title === 'New conversation' ? content.slice(0, 70) : c.title,
      draft: '', updatedAt: Date.now(), messages: [...c.messages, message],
    })));
    await this.execute(conversation.id, message.id, body);
  }

  async retry(messageId: string): Promise<void> {
    if (!this.snapshot.ready || this.running) return;
    const conversation = this.active;
    const index = conversation.messages.findIndex(m => m.id === messageId && m.role === 'user');
    const message = conversation.messages[index];
    if (!message || !['failed', 'cancelled'].includes(message.status)) return;
    // Retrying an older turn would make the transcript order ambiguous.
    if (index !== conversation.messages.length - 1) {
      this.edit({ draft: message.text });
      this.notify('The earlier message is in your draft. Send it as a new turn.');
      return;
    }
    const attachment = this.attachments.get(messageId);
    if (message.attachmentName && !attachment) {
      this.edit({ draft: message.text });
      this.notify('Attachments are not saved on this device. Reattach the file and send your restored draft.');
      return;
    }
    const body = buildChatBody(
      { ...conversation, messages: conversation.messages.slice(0, index) },
      message.text,
      attachment,
      Date.now(),
      message.id,
    );
    this.setMessage(conversation.id, messageId, { status: 'pending', error: undefined });
    await this.execute(conversation.id, messageId, body);
  }

  private async execute(conversationId: string, messageId: string, body: ChatBody): Promise<void> {
    const running: Running = { controller: new AbortController(), conversationId, messageId };
    this.running = running;
    this.emit({ busyId: conversationId, notice: null });
    try {
      const response = await this.transport(body, running.controller.signal);
      if (this.running !== running) return;
      if (response.ok === false || typeof response.reply !== 'string' || !response.reply.trim()) {
        throw new Error('Jeeves returned an empty response. Try again.');
      }
      const reply: Message = {
        id: newId(), role: 'jeeves', text: response.reply.slice(0, MAX_TEXT), status: 'complete',
        createdAt: Date.now(), tier: response.tier, model: response.model,
        forms: response.forms, artifacts: response.artifacts || [], artifactCount: response.artifacts?.length || 0,
      };
      this.change(updateConversation(this.snapshot.workspace, conversationId, c => ({
        ...c, sessionId: response.session_id || c.sessionId, sessionUpdatedAt: Date.now(), updatedAt: Date.now(),
        messages: [...c.messages.map(m => m.id === messageId ? { ...m, status: 'complete' as const, error: undefined } : m), reply],
      })));
      this.attachments.delete(messageId);
      if (response.persisted === false) this.notify('The server could not save this exchange. Your device-local transcript is still available.');
    } catch (error) {
      if (this.running !== running) return;
      this.setMessage(conversationId, messageId, {
        status: 'failed', error: error instanceof Error ? error.message.slice(0, 400) : 'Jeeves could not respond. Try again.',
      });
    } finally {
      if (this.running === running) {
        this.running = null;
        this.emit({ busyId: null });
      }
    }
  }
}
