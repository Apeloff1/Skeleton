// ============================================================================
// CODEDOCK QUANTUM NEXUS - Collaboration Modal UI
// Real-time multiplayer sessions with Y.js
// ============================================================================

import React, { useState, useEffect, useRef } from 'react';
import {
  View, Text, StyleSheet, Modal, TouchableOpacity, ScrollView,
  TextInput, ActivityIndicator, Share, Platform,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { 
  collaborationManager, 
  CollaboratorInfo, 
  ChatMessage 
} from './CollaborationManager';
import { toast } from '../../components/Toast';

// ============================================================================
// PROPS
// ============================================================================
interface CollaborationModalProps {
  visible: boolean;
  onClose: () => void;
  colors: any;
  code: string;
  language: string;
  onCodeChange: (code: string) => void;
}

// ============================================================================
// MAIN COMPONENT
// ============================================================================
export function CollaborationModal({
  visible,
  onClose,
  colors,
  code,
  language,
  onCodeChange,
}: CollaborationModalProps) {
  // State
  const [activeTab, setActiveTab] = useState<'session' | 'participants' | 'chat'>('session');
  const [isConnected, setIsConnected] = useState(false);
  const [isJoining, setIsJoining] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [joinSessionId, setJoinSessionId] = useState('');
  const [userName, setUserName] = useState('');
  const [participants, setParticipants] = useState<CollaboratorInfo[]>([]);
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [newMessage, setNewMessage] = useState('');
  const chatScrollRef = useRef<ScrollView>(null);

  // Initialize callbacks
  useEffect(() => {
    const unsubCode = collaborationManager.onCodeChange((newCode) => {
      onCodeChange(newCode);
    });

    const unsubParticipants = collaborationManager.onParticipantChange((p) => {
      setParticipants(p);
    });

    const unsubChat = collaborationManager.onChatMessage((messages) => {
      setChatMessages(messages);
      // Auto-scroll to bottom
      setTimeout(() => {
        chatScrollRef.current?.scrollToEnd({ animated: true });
      }, 100);
    });

    return () => {
      unsubCode();
      unsubParticipants();
      unsubChat();
    };
  }, [onCodeChange]);

  // Check connection status
  useEffect(() => {
    const interval = setInterval(() => {
      setIsConnected(collaborationManager.isConnected());
      setSessionId(collaborationManager.getSessionId());
    }, 1000);

    return () => clearInterval(interval);
  }, []);

  // Create new session
  const handleCreateSession = async () => {
    if (!userName.trim()) {
      toast.info('Please enter your name to create a session');
      return;
    }

    setIsJoining(true);
    try {
      collaborationManager.setUserInfo(userName);
      const newSessionId = await collaborationManager.createSession(
        `${userName}'s Session`,
        code,
        language
      );
      setSessionId(newSessionId);
      setIsConnected(true);
      
      // Send system message
      collaborationManager.sendMessage(`${userName} created the session`, 'system');
    } catch (e: any) {
      toast.error(`Failed to create session: ${e.message}`);
    } finally {
      setIsJoining(false);
    }
  };

  // Join existing session
  const handleJoinSession = async () => {
    if (!userName.trim()) {
      toast.info('Please enter your name to join a session');
      return;
    }

    if (!joinSessionId.trim()) {
      toast.info('Please enter a session ID to join');
      return;
    }

    setIsJoining(true);
    try {
      collaborationManager.setUserInfo(userName);
      await collaborationManager.joinSession(joinSessionId.trim());
      setSessionId(joinSessionId.trim());
      setIsConnected(true);
      
      // Sync code from session
      const sessionCode = collaborationManager.getCode();
      if (sessionCode) {
        onCodeChange(sessionCode);
      }
      
      // Send system message
      collaborationManager.sendMessage(`${userName} joined the session`, 'system');
    } catch (e: any) {
      toast.error(`Failed to join session: ${e.message}`);
    } finally {
      setIsJoining(false);
    }
  };

  // Leave session
  const handleLeaveSession = async () => {
    collaborationManager.sendMessage(`${userName} left the session`, 'system');
    await collaborationManager.leaveSession();
    setSessionId(null);
    setIsConnected(false);
    setParticipants([]);
    setChatMessages([]);
  };

  // Share session
  const handleShareSession = async () => {
    if (!sessionId) return;

    try {
      await Share.share({
        message: `Join my CodeDock session!\n\nSession ID: ${sessionId}\n\nOpen CodeDock and enter this ID to collaborate in real-time!`,
        title: 'Share CodeDock Session',
      });
    } catch {
      // Fallback for web
      if (Platform.OS === 'web' && navigator.clipboard) {
        await navigator.clipboard.writeText(sessionId);
        toast.success('Session ID copied to clipboard');
      }
    }
  };

  // Send chat message
  const handleSendMessage = () => {
    if (!newMessage.trim()) return;
    collaborationManager.sendMessage(newMessage.trim());
    setNewMessage('');
  };

  // Share code snippet
  const handleShareCode = () => {
    const snippet = code.slice(0, 200) + (code.length > 200 ? '...' : '');
    collaborationManager.sendMessage(snippet, 'code-share');
  };

  // ============================================================================
  // RENDER SESSION TAB
  // ============================================================================
  const renderSessionTab = () => (
    <ScrollView style={styles.tabContent}>
      {!isConnected ? (
        <>
          {/* Name Input */}
          <View style={[styles.inputSection, { backgroundColor: colors.surfaceAlt }]}>
            <Text style={[styles.inputLabel, { color: colors.text }]}>Your Name</Text>
            <TextInput
              style={[styles.input, { backgroundColor: colors.surface, color: colors.text, borderColor: colors.border }]}
              value={userName}
              onChangeText={setUserName}
              placeholder="Enter your name"
              placeholderTextColor={colors.textMuted}
            />
          </View>

          {/* Create Session */}
          <View style={[styles.section, { backgroundColor: colors.surface }]}>
            <View style={styles.sectionHeader}>
              <Ionicons name="add-circle" size={24} color="#10B981" />
              <Text style={[styles.sectionTitle, { color: colors.text }]}>Create New Session</Text>
            </View>
            <Text style={[styles.sectionDesc, { color: colors.textMuted }]}>
              Start a new collaborative session and invite up to 8 people to code together in real-time.
            </Text>
            <TouchableOpacity 
              style={[styles.primaryButton, { backgroundColor: '#10B981' }]}
              onPress={handleCreateSession}
              disabled={isJoining}
            >
              {isJoining ? (
                <ActivityIndicator color="#FFF" />
              ) : (
                <>
                  <Ionicons name="rocket" size={18} color="#FFF" />
                  <Text style={styles.primaryButtonText}>Create Session</Text>
                </>
              )}
            </TouchableOpacity>
          </View>

          {/* Join Session */}
          <View style={[styles.section, { backgroundColor: colors.surface }]}>
            <View style={styles.sectionHeader}>
              <Ionicons name="enter" size={24} color="#6366F1" />
              <Text style={[styles.sectionTitle, { color: colors.text }]}>Join Existing Session</Text>
            </View>
            <TextInput
              style={[styles.input, { backgroundColor: colors.surfaceAlt, color: colors.text, borderColor: colors.border }]}
              value={joinSessionId}
              onChangeText={setJoinSessionId}
              placeholder="Enter session ID"
              placeholderTextColor={colors.textMuted}
              autoCapitalize="none"
            />
            <TouchableOpacity 
              style={[styles.primaryButton, { backgroundColor: '#6366F1' }]}
              onPress={handleJoinSession}
              disabled={isJoining}
            >
              {isJoining ? (
                <ActivityIndicator color="#FFF" />
              ) : (
                <>
                  <Ionicons name="log-in" size={18} color="#FFF" />
                  <Text style={styles.primaryButtonText}>Join Session</Text>
                </>
              )}
            </TouchableOpacity>
          </View>
        </>
      ) : (
        <>
          {/* Connected Status */}
          <View style={[styles.connectedBanner, { backgroundColor: '#10B98120', borderColor: '#10B981' }]}>
            <View style={styles.connectedDot} />
            <View style={styles.connectedInfo}>
              <Text style={[styles.connectedTitle, { color: '#10B981' }]}>Session Active</Text>
              <Text style={[styles.connectedId, { color: colors.textMuted }]} numberOfLines={1}>
                {sessionId}
              </Text>
            </View>
            <TouchableOpacity onPress={handleShareSession}>
              <Ionicons name="share-outline" size={24} color="#10B981" />
            </TouchableOpacity>
          </View>

          {/* Session Info */}
          <View style={[styles.section, { backgroundColor: colors.surface }]}>
            <View style={styles.statRow}>
              <View style={styles.stat}>
                <Text style={[styles.statValue, { color: colors.text }]}>{participants.length}</Text>
                <Text style={[styles.statLabel, { color: colors.textMuted }]}>Participants</Text>
              </View>
              <View style={styles.stat}>
                <Text style={[styles.statValue, { color: colors.text }]}>{chatMessages.length}</Text>
                <Text style={[styles.statLabel, { color: colors.textMuted }]}>Messages</Text>
              </View>
              <View style={styles.stat}>
                <Text style={[styles.statValue, { color: colors.text }]}>{code.split('\n').length}</Text>
                <Text style={[styles.statLabel, { color: colors.textMuted }]}>Lines</Text>
              </View>
            </View>
          </View>

          {/* Quick Actions */}
          <View style={styles.quickActions}>
            <TouchableOpacity 
              style={[styles.quickAction, { backgroundColor: colors.surfaceAlt }]}
              onPress={handleShareCode}
            >
              <Ionicons name="code-slash" size={20} color="#8B5CF6" />
              <Text style={[styles.quickActionText, { color: colors.text }]}>Share Code</Text>
            </TouchableOpacity>
            <TouchableOpacity 
              style={[styles.quickAction, { backgroundColor: colors.surfaceAlt }]}
              onPress={handleShareSession}
            >
              <Ionicons name="link" size={20} color="#2563EB" />
              <Text style={[styles.quickActionText, { color: colors.text }]}>Copy Link</Text>
            </TouchableOpacity>
          </View>

          {/* Leave Button */}
          <TouchableOpacity 
            style={[styles.leaveButton, { backgroundColor: '#EF444420', borderColor: '#EF4444' }]}
            onPress={handleLeaveSession}
          >
            <Ionicons name="exit" size={18} color="#EF4444" />
            <Text style={[styles.leaveButtonText, { color: '#EF4444' }]}>Leave Session</Text>
          </TouchableOpacity>
        </>
      )}
    </ScrollView>
  );

  // ============================================================================
  // RENDER PARTICIPANTS TAB
  // ============================================================================
  const renderParticipantsTab = () => (
    <ScrollView style={styles.tabContent}>
      <View style={[styles.participantsHeader, { backgroundColor: colors.surfaceAlt }]}>
        <Text style={[styles.participantsCount, { color: colors.text }]}>
          {participants.length} / 8 Collaborators
        </Text>
      </View>

      {participants.length === 0 ? (
        <View style={[styles.emptyState, { backgroundColor: colors.surface }]}>
          <Ionicons name="people-outline" size={48} color={colors.textMuted} />
          <Text style={[styles.emptyTitle, { color: colors.text }]}>No Participants</Text>
          <Text style={[styles.emptyDesc, { color: colors.textMuted }]}>
            Create or join a session to see collaborators
          </Text>
        </View>
      ) : (
        participants.map((participant) => (
          <View 
            key={participant.id} 
            style={[styles.participantCard, { backgroundColor: colors.surface }]}
          >
            <View style={[styles.participantAvatar, { backgroundColor: participant.color }]}>
              <Text style={styles.participantInitial}>
                {participant.name.charAt(0).toUpperCase()}
              </Text>
            </View>
            <View style={styles.participantInfo}>
              <Text style={[styles.participantName, { color: colors.text }]}>
                {participant.name}
                {participant.id === collaborationManager.getUserId() && ' (You)'}
              </Text>
              <Text style={[styles.participantStatus, { color: colors.textMuted }]}>
                {participant.isActive ? 'Active' : 'Inactive'}
              </Text>
            </View>
            <View style={[styles.colorDot, { backgroundColor: participant.color }]} />
          </View>
        ))
      )}
    </ScrollView>
  );

  // ============================================================================
  // RENDER CHAT TAB
  // ============================================================================
  const renderChatTab = () => (
    <View style={styles.chatContainer}>
      <ScrollView 
        ref={chatScrollRef}
        style={styles.chatMessages}
        contentContainerStyle={styles.chatMessagesContent}
      >
        {chatMessages.length === 0 ? (
          <View style={styles.chatEmpty}>
            <Ionicons name="chatbubbles-outline" size={48} color={colors.textMuted} />
            <Text style={[styles.chatEmptyText, { color: colors.textMuted }]}>
              No messages yet. Start the conversation!
            </Text>
          </View>
        ) : (
          chatMessages.map((msg) => {
            const isOwn = msg.authorId === collaborationManager.getUserId();
            const isSystem = msg.type === 'system';
            const participant = participants.find(p => p.id === msg.authorId);
            
            if (isSystem) {
              return (
                <View key={msg.id} style={styles.systemMessage}>
                  <Text style={[styles.systemMessageText, { color: colors.textMuted }]}>
                    {msg.content}
                  </Text>
                </View>
              );
            }

            return (
              <View 
                key={msg.id} 
                style={[
                  styles.chatBubble,
                  isOwn ? styles.chatBubbleOwn : styles.chatBubbleOther,
                  { backgroundColor: isOwn ? '#6366F1' : colors.surfaceAlt }
                ]}
              >
                {!isOwn && (
                  <Text style={[styles.chatAuthor, { color: participant?.color || '#6366F1' }]}>
                    {msg.authorName}
                  </Text>
                )}
                {msg.type === 'code-share' ? (
                  <View style={[styles.codeShare, { backgroundColor: 'rgba(0,0,0,0.2)' }]}>
                    <Text style={[styles.codeShareText, { color: isOwn ? '#FFF' : colors.text }]}>
                      {msg.content}
                    </Text>
                  </View>
                ) : (
                  <Text style={[styles.chatText, { color: isOwn ? '#FFF' : colors.text }]}>
                    {msg.content}
                  </Text>
                )}
                <Text style={[styles.chatTime, { color: isOwn ? 'rgba(255,255,255,0.7)' : colors.textMuted }]}>
                  {new Date(msg.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                </Text>
              </View>
            );
          })
        )}
      </ScrollView>

      {isConnected && (
        <View style={[styles.chatInput, { backgroundColor: colors.surface, borderTopColor: colors.border }]}>
          <TextInput
            style={[styles.chatTextInput, { backgroundColor: colors.surfaceAlt, color: colors.text }]}
            value={newMessage}
            onChangeText={setNewMessage}
            placeholder="Type a message..."
            placeholderTextColor={colors.textMuted}
            onSubmitEditing={handleSendMessage}
          />
          <TouchableOpacity 
            style={[styles.sendButton, { backgroundColor: '#6366F1' }]}
            onPress={handleSendMessage}
          >
            <Ionicons name="send" size={18} color="#FFF" />
          </TouchableOpacity>
        </View>
      )}
    </View>
  );

  // ============================================================================
  // RENDER
  // ============================================================================
  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <View style={[styles.overlay, { backgroundColor: 'rgba(0,0,0,0.5)' }]}>
        <View style={[styles.container, { backgroundColor: colors.background }]}>
          {/* Header */}
          <View style={[styles.header, { backgroundColor: colors.surface, borderBottomColor: colors.border }]}>
            <View style={styles.headerTitle}>
              <Ionicons name="people" size={22} color="#6366F1" />
              <Text style={[styles.headerText, { color: colors.text }]}>Multiplayer Bridge</Text>
              {isConnected && (
                <View style={[styles.liveIndicator, { backgroundColor: '#10B981' }]}>
                  <Text style={styles.liveText}>LIVE</Text>
                </View>
              )}
            </View>
            <TouchableOpacity onPress={onClose}>
              <Ionicons name="close" size={24} color={colors.textSecondary} />
            </TouchableOpacity>
          </View>

          {/* Tabs */}
          <View style={[styles.tabs, { backgroundColor: colors.surfaceAlt }]}>
            {(['session', 'participants', 'chat'] as const).map(tab => (
              <TouchableOpacity
                key={tab}
                style={[
                  styles.tab,
                  { 
                    backgroundColor: activeTab === tab ? '#6366F120' : 'transparent',
                    borderBottomColor: activeTab === tab ? '#6366F1' : 'transparent',
                  }
                ]}
                onPress={() => setActiveTab(tab)}
              >
                <Ionicons 
                  name={tab === 'session' ? 'link' : tab === 'participants' ? 'people' : 'chatbubbles'}
                  size={16}
                  color={activeTab === tab ? '#6366F1' : colors.textMuted}
                />
                <Text style={[styles.tabText, { color: activeTab === tab ? '#6366F1' : colors.textMuted }]}>
                  {tab.charAt(0).toUpperCase() + tab.slice(1)}
                </Text>
                {tab === 'chat' && chatMessages.length > 0 && (
                  <View style={[styles.badge, { backgroundColor: '#EF4444' }]}>
                    <Text style={styles.badgeText}>{chatMessages.length}</Text>
                  </View>
                )}
              </TouchableOpacity>
            ))}
          </View>

          {/* Content */}
          {activeTab === 'session' && renderSessionTab()}
          {activeTab === 'participants' && renderParticipantsTab()}
          {activeTab === 'chat' && renderChatTab()}
        </View>
      </View>
    </Modal>
  );
}

// ============================================================================
// STYLES
// ============================================================================
const styles = StyleSheet.create({
  overlay: { flex: 1, justifyContent: 'flex-end' },
  container: { height: '92%', borderTopLeftRadius: 24, borderTopRightRadius: 24 },
  
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', padding: 16, borderBottomWidth: 1 },
  headerTitle: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  headerText: { fontSize: 18, fontWeight: '700' },
  liveIndicator: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: 4, marginLeft: 8 },
  liveText: { color: '#FFF', fontSize: 10, fontWeight: '700' },
  
  tabs: { flexDirection: 'row', padding: 8 },
  tab: { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', paddingVertical: 10, gap: 6, borderBottomWidth: 2 },
  tabText: { fontSize: 13, fontWeight: '600' },
  badge: { minWidth: 18, height: 18, borderRadius: 9, alignItems: 'center', justifyContent: 'center', marginLeft: 4 },
  badgeText: { color: '#FFF', fontSize: 10, fontWeight: '700' },
  
  tabContent: { flex: 1, padding: 16 },
  
  // Input Section
  inputSection: { padding: 16, borderRadius: 12, marginBottom: 16 },
  inputLabel: { fontSize: 14, fontWeight: '600', marginBottom: 8 },
  input: { padding: 14, borderRadius: 10, borderWidth: 1, fontSize: 14 },
  
  // Sections
  section: { padding: 16, borderRadius: 16, marginBottom: 16 },
  sectionHeader: { flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 8 },
  sectionTitle: { fontSize: 16, fontWeight: '700' },
  sectionDesc: { fontSize: 13, lineHeight: 20, marginBottom: 16 },
  
  // Buttons
  primaryButton: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', padding: 14, borderRadius: 12, gap: 8 },
  primaryButtonText: { color: '#FFF', fontSize: 15, fontWeight: '700' },
  
  // Connected Banner
  connectedBanner: { flexDirection: 'row', alignItems: 'center', padding: 16, borderRadius: 12, borderWidth: 1, marginBottom: 16, gap: 12 },
  connectedDot: { width: 12, height: 12, borderRadius: 6, backgroundColor: '#10B981' },
  connectedInfo: { flex: 1 },
  connectedTitle: { fontSize: 14, fontWeight: '700' },
  connectedId: { fontSize: 11, marginTop: 2 },
  
  // Stats
  statRow: { flexDirection: 'row', justifyContent: 'space-around' },
  stat: { alignItems: 'center' },
  statValue: { fontSize: 24, fontWeight: '800' },
  statLabel: { fontSize: 12, marginTop: 4 },
  
  // Quick Actions
  quickActions: { flexDirection: 'row', gap: 12, marginBottom: 16 },
  quickAction: { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', padding: 14, borderRadius: 12, gap: 8 },
  quickActionText: { fontSize: 13, fontWeight: '600' },
  
  // Leave Button
  leaveButton: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', padding: 14, borderRadius: 12, borderWidth: 1, gap: 8 },
  leaveButtonText: { fontSize: 14, fontWeight: '600' },
  
  // Participants
  participantsHeader: { padding: 14, borderRadius: 12, marginBottom: 16 },
  participantsCount: { fontSize: 14, fontWeight: '600', textAlign: 'center' },
  participantCard: { flexDirection: 'row', alignItems: 'center', padding: 14, borderRadius: 12, marginBottom: 10, gap: 12 },
  participantAvatar: { width: 44, height: 44, borderRadius: 22, alignItems: 'center', justifyContent: 'center' },
  participantInitial: { color: '#FFF', fontSize: 18, fontWeight: '700' },
  participantInfo: { flex: 1 },
  participantName: { fontSize: 15, fontWeight: '600' },
  participantStatus: { fontSize: 12, marginTop: 2 },
  colorDot: { width: 12, height: 12, borderRadius: 6 },
  
  // Empty State
  emptyState: { padding: 40, borderRadius: 16, alignItems: 'center' },
  emptyTitle: { fontSize: 18, fontWeight: '600', marginTop: 12 },
  emptyDesc: { fontSize: 13, marginTop: 4, textAlign: 'center' },
  
  // Chat
  chatContainer: { flex: 1 },
  chatMessages: { flex: 1 },
  chatMessagesContent: { padding: 16 },
  chatEmpty: { alignItems: 'center', paddingVertical: 60 },
  chatEmptyText: { fontSize: 14, marginTop: 12, textAlign: 'center' },
  
  systemMessage: { alignItems: 'center', marginVertical: 8 },
  systemMessageText: { fontSize: 12, fontStyle: 'italic' },
  
  chatBubble: { maxWidth: '80%', padding: 12, borderRadius: 16, marginBottom: 8 },
  chatBubbleOwn: { alignSelf: 'flex-end', borderBottomRightRadius: 4 },
  chatBubbleOther: { alignSelf: 'flex-start', borderBottomLeftRadius: 4 },
  chatAuthor: { fontSize: 12, fontWeight: '600', marginBottom: 4 },
  chatText: { fontSize: 14, lineHeight: 20 },
  chatTime: { fontSize: 10, marginTop: 4, textAlign: 'right' },
  
  codeShare: { padding: 8, borderRadius: 8, marginTop: 4 },
  codeShareText: { fontSize: 12, fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace' },
  
  chatInput: { flexDirection: 'row', alignItems: 'center', padding: 12, borderTopWidth: 1, gap: 10 },
  chatTextInput: { flex: 1, padding: 12, borderRadius: 20, fontSize: 14 },
  sendButton: { width: 44, height: 44, borderRadius: 22, alignItems: 'center', justifyContent: 'center' },
});

export default CollaborationModal;
