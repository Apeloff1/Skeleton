// ============================================================================
// CODEDOCK QUANTUM NEXUS - Multiplayer Bridge Collaboration
// Lightweight stub implementation (yjs removed for EAS build compatibility)
// Provides identical API surface for feature-flag controlled re-enablement
// ============================================================================

// ============================================================================
// TYPES
// ============================================================================
export interface CollaboratorInfo {
  id: string;
  name: string;
  color: string;
  cursor?: CursorPosition;
  selection?: SelectionRange;
  isActive: boolean;
  joinedAt: Date;
}

export interface CursorPosition {
  line: number;
  column: number;
}

export interface SelectionRange {
  startLine: number;
  startColumn: number;
  endLine: number;
  endColumn: number;
}

export interface CollaborationSession {
  id: string;
  name: string;
  createdAt: Date;
  createdBy: string;
  participants: CollaboratorInfo[];
  maxParticipants: number;
  isPublic: boolean;
  code: string;
  language: string;
  chatMessages: ChatMessage[];
}

export interface ChatMessage {
  id: string;
  authorId: string;
  authorName: string;
  content: string;
  timestamp: Date;
  type: 'message' | 'system' | 'code-share';
}

export interface AwarenessState {
  user: CollaboratorInfo;
  cursor?: CursorPosition;
  selection?: SelectionRange;
}

// ============================================================================
// COLLABORATION COLORS
// ============================================================================
const COLLABORATOR_COLORS = [
  '#EF4444', '#F59E0B', '#10B981', '#3B82F6',
  '#8B5CF6', '#EC4899', '#2563EB', '#84CC16',
];

// ============================================================================
// COLLABORATION MANAGER CLASS (Lightweight Stub)
// ============================================================================
export class CollaborationManager {
  private sessionId: string | null = null;
  private userId: string;
  private userName: string;
  private userColor: string;
  private currentCode: string = '';
  private messages: ChatMessage[] = [];
  private participants: CollaboratorInfo[] = [];

  private onCodeChangeCallbacks: ((code: string) => void)[] = [];
  private onParticipantChangeCallbacks: ((participants: CollaboratorInfo[]) => void)[] = [];
  private onChatMessageCallbacks: ((messages: ChatMessage[]) => void)[] = [];
  private onCursorChangeCallbacks: ((cursors: Map<string, CursorPosition>) => void)[] = [];

  constructor() {
    this.userId = this.generateUserId();
    this.userName = 'Anonymous';
    this.userColor = COLLABORATOR_COLORS[Math.floor(Math.random() * COLLABORATOR_COLORS.length)];
  }

  // ============================================================================
  // INITIALIZATION
  // ============================================================================
  private generateUserId(): string {
    return `user-${Date.now().toString(36)}-${Math.random().toString(36).substr(2, 9)}`;
  }

  setUserInfo(name: string, color?: string): void {
    this.userName = name;
    if (color) this.userColor = color;
  }

  // ============================================================================
  // SESSION MANAGEMENT
  // ============================================================================
  async createSession(name: string, initialCode: string = '', language: string = 'python'): Promise<string> {
    const sessionId = `codedock-${Date.now().toString(36)}-${Math.random().toString(36).substr(2, 6)}`;
    await this.joinSession(sessionId, name, initialCode, language);
    return sessionId;
  }

  async joinSession(
    sessionId: string,
    sessionName?: string,
    initialCode?: string,
    language?: string
  ): Promise<void> {
    await this.leaveSession();
    this.sessionId = sessionId;

    if (initialCode) {
      this.currentCode = initialCode;
    }

    const selfParticipant: CollaboratorInfo = {
      id: this.userId,
      name: this.userName,
      color: this.userColor,
      isActive: true,
      joinedAt: new Date(),
    };
    this.participants = [selfParticipant];
    this.onParticipantChangeCallbacks.forEach(cb => cb(this.participants));

    console.log(`[CollaborationManager] Joined session: ${sessionId} (local-only mode)`);
  }

  async leaveSession(): Promise<void> {
    this.participants = [];
    this.messages = [];
    this.currentCode = '';
    this.sessionId = null;
  }

  // ============================================================================
  // AWARENESS
  // ============================================================================
  updateCursor(position: CursorPosition): void {
    // Local-only: no remote awareness in stub mode
  }

  updateSelection(selection: SelectionRange | null): void {
    // Local-only: no remote awareness in stub mode
  }

  // ============================================================================
  // CODE OPERATIONS
  // ============================================================================
  getCode(): string {
    return this.currentCode;
  }

  setCode(code: string): void {
    this.currentCode = code;
    this.onCodeChangeCallbacks.forEach(cb => cb(code));
  }

  insertText(index: number, text: string): void {
    this.currentCode = this.currentCode.slice(0, index) + text + this.currentCode.slice(index);
    this.onCodeChangeCallbacks.forEach(cb => cb(this.currentCode));
  }

  deleteText(index: number, length: number): void {
    this.currentCode = this.currentCode.slice(0, index) + this.currentCode.slice(index + length);
    this.onCodeChangeCallbacks.forEach(cb => cb(this.currentCode));
  }

  // ============================================================================
  // CHAT OPERATIONS
  // ============================================================================
  sendMessage(content: string, type: ChatMessage['type'] = 'message'): void {
    const message: ChatMessage = {
      id: `msg-${Date.now()}-${Math.random().toString(36).substr(2, 6)}`,
      authorId: this.userId,
      authorName: this.userName,
      content,
      timestamp: new Date(),
      type,
    };
    this.messages.push(message);
    this.onChatMessageCallbacks.forEach(cb => cb(this.messages));
  }

  getMessages(): ChatMessage[] {
    return this.messages;
  }

  // ============================================================================
  // PARTICIPANT OPERATIONS
  // ============================================================================
  getParticipants(): CollaboratorInfo[] {
    return this.participants;
  }

  getParticipantCount(): number {
    return this.participants.length;
  }

  // ============================================================================
  // CALLBACKS
  // ============================================================================
  onCodeChange(callback: (code: string) => void): () => void {
    this.onCodeChangeCallbacks.push(callback);
    return () => {
      this.onCodeChangeCallbacks = this.onCodeChangeCallbacks.filter(cb => cb !== callback);
    };
  }

  onParticipantChange(callback: (participants: CollaboratorInfo[]) => void): () => void {
    this.onParticipantChangeCallbacks.push(callback);
    return () => {
      this.onParticipantChangeCallbacks = this.onParticipantChangeCallbacks.filter(cb => cb !== callback);
    };
  }

  onChatMessage(callback: (messages: ChatMessage[]) => void): () => void {
    this.onChatMessageCallbacks.push(callback);
    return () => {
      this.onChatMessageCallbacks = this.onChatMessageCallbacks.filter(cb => cb !== callback);
    };
  }

  onCursorChange(callback: (cursors: Map<string, CursorPosition>) => void): () => void {
    this.onCursorChangeCallbacks.push(callback);
    return () => {
      this.onCursorChangeCallbacks = this.onCursorChangeCallbacks.filter(cb => cb !== callback);
    };
  }

  // ============================================================================
  // STATUS
  // ============================================================================
  isConnected(): boolean {
    return !!this.sessionId;
  }

  getSessionId(): string | null {
    return this.sessionId;
  }

  getUserId(): string {
    return this.userId;
  }

  getUserColor(): string {
    return this.userColor;
  }
}

// ============================================================================
// SINGLETON
// ============================================================================
export const collaborationManager = new CollaborationManager();

export default collaborationManager;
