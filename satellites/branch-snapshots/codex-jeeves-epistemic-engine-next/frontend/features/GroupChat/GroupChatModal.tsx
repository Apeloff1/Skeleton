/**
 * Creator's Group Chat v16.5
 * Interconnected chat system with all pipeline agents + Jeeves
 * 3 System Blurbs enforced as immutable laws
 * Code auto-stored in Vault | Jeeves idle parsing | Level system
 */

import React, { useState, useEffect, useRef } from 'react';
import {
  View, Text, StyleSheet, TouchableOpacity, ScrollView,
  Modal, TextInput, ActivityIndicator, KeyboardAvoidingView,
  Platform,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import Constants from 'expo-constants';

import { apiFetch } from '../../utils/apiController';
const API_BASE = (() => {
  if (typeof window !== 'undefined' && (window as any).location?.origin && !(window as any).location.origin.startsWith('file:')) {
    return (window as any).location.origin.replace(/\/+$/, '');
  }
  return (Constants.expoConfig?.extra?.EXPO_PUBLIC_BACKEND_URL as string)
    || process.env.EXPO_PUBLIC_BACKEND_URL || '';
})();

interface GroupChatModalProps {
  visible: boolean;
  onClose: () => void;
  colors: any;
}

interface ChatRoom {
  id: string;
  name: string;
  description: string;
  agents: string[];
  icon: string;
  color: string;
}

interface Agent {
  id: string;
  name: string;
  role: string;
  specialty: string;
  icon: string;
  avatar_color: string;
}

interface Message {
  user_id: string;
  agent_id?: string;
  content: string;
  code_blocks?: string[];
  message_type: string;
  timestamp: string;
}

interface SystemBlurb {
  id: string;
  law: string;
  text: string;
  icon: string;
  color: string;
}

export const GroupChatModal: React.FC<GroupChatModalProps> = ({ visible, onClose, colors }) => {
  const [rooms, setRooms] = useState<ChatRoom[]>([]);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [blurbs, setBlurbs] = useState<SystemBlurb[]>([]);
  const [selectedRoom, setSelectedRoom] = useState<ChatRoom | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputText, setInputText] = useState('');
  const [loading, setLoading] = useState(true);
  const [jeevesLevel, setJeevesLevel] = useState({ level: 1, xp: 0, xp_to_next: 100 });
  const [showBlurbs, setShowBlurbs] = useState(false);
  const scrollRef = useRef<ScrollView>(null);

  useEffect(() => {
    if (visible) loadData();
  }, [visible]);

  const loadData = async () => {
    setLoading(true);
    try {
      const [roomsRes, agentsRes, levelRes] = await Promise.all([
        apiFetch(`${API_BASE}/api/agents/chat/rooms`),
        apiFetch(`${API_BASE}/api/agents/list`),
        apiFetch(`${API_BASE}/api/agents/jeeves/level`),
      ]);
      if (roomsRes.ok) {
        const rd = await roomsRes.json();
        setRooms(rd.rooms || []);
      }
      if (agentsRes.ok) {
        const ad = await agentsRes.json();
        setAgents(ad.agents || []);
        setBlurbs(ad.system_blurbs || []);
      }
      if (levelRes.ok) {
        setJeevesLevel(await levelRes.json());
      }
    } catch {
      setRooms([
        { id: 'creators_main', name: "Creator's Main Chat", description: 'All agents', agents: [], icon: 'chatbubbles', color: '#8B5CF6' },
        { id: 'tutors_chat', name: "Tutor's Chat", description: 'Jeeves delivers here', agents: ['jeeves'], icon: 'school', color: '#3B82F6' },
      ]);
    }
    setLoading(false);
  };

  const loadMessages = async (roomId: string) => {
    try {
      const res = await apiFetch(`${API_BASE}/api/agents/chat/${roomId}/messages?limit=50`);
      if (res.ok) {
        const data = await res.json();
        setMessages(data.messages || []);
      }
    } catch {
      setMessages([]);
    }
  };

  const selectRoom = (room: ChatRoom) => {
    setSelectedRoom(room);
    loadMessages(room.id);
  };

  const sendMessage = async () => {
    if (!inputText.trim() || !selectedRoom) return;
    const text = inputText.trim();
    setInputText('');

    // Detect code blocks
    const codeBlockRegex = /```[\s\S]*?```/g;
    const codeBlocks = text.match(codeBlockRegex)?.map(b => b.replace(/```\w*/g, '').replace(/```/g, '').trim()) || [];

    // Optimistic update
    const newMsg: Message = {
      user_id: 'default_user',
      content: text,
      code_blocks: codeBlocks,
      message_type: codeBlocks.length > 0 ? 'code' : 'text',
      timestamp: new Date().toISOString(),
    };
    setMessages(prev => [...prev, newMsg]);

    // Show typing indicator
    const typingMsg: Message = {
      user_id: 'system',
      agent_id: 'jeeves',
      content: '💭 Agents thinking...',
      message_type: 'typing',
      timestamp: new Date().toISOString(),
    };
    setMessages(prev => [...prev, typingMsg]);

    try {
      const res = await apiFetch(`${API_BASE}/api/agents/chat/send`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: 'default_user',
          content: text,
          code_blocks: codeBlocks,
          chat_id: selectedRoom.id,
          message_type: newMsg.message_type,
        }),
      });

      if (res.ok) {
        const data = await res.json();
        
        // Remove typing indicator and add real agent responses
        setMessages(prev => {
          const filtered = prev.filter(m => m.message_type !== 'typing');
          const agentMsgs: Message[] = (data.agent_responses || []).map((r: any) => ({
            user_id: r.agent_id,
            agent_id: r.agent_id,
            content: r.content,
            code_blocks: r.code_blocks || [],
            message_type: r.code_blocks?.length > 0 ? 'code' : 'text',
            timestamp: r.timestamp,
          }));
          return [...filtered, ...agentMsgs];
        });
      } else {
        // Remove typing indicator on error
        setMessages(prev => prev.filter(m => m.message_type !== 'typing'));
      }

      // Reload Jeeves level
      const lvlRes = await apiFetch(`${API_BASE}/api/agents/jeeves/level`);
      if (lvlRes.ok) setJeevesLevel(await lvlRes.json());
    } catch {
      setMessages(prev => prev.filter(m => m.message_type !== 'typing'));
    }

    setTimeout(() => scrollRef.current?.scrollToEnd({ animated: true }), 300);
  };

  const getAgentInfo = (agentId: string): Agent | undefined => {
    return agents.find(a => a.id === agentId);
  };

  const renderRoomList = () => (
    <ScrollView style={styles.content} showsVerticalScrollIndicator={false}>
      {/* Jeeves Level */}
      <View style={[styles.levelCard, { backgroundColor: '#8B5CF620', borderColor: '#8B5CF640' }]}>
        <View style={[styles.levelCircle, { backgroundColor: '#8B5CF6' }]}>
          <Text style={styles.levelNum}>{jeevesLevel.level}</Text>
        </View>
        <View style={styles.levelInfo}>
          <Text style={[styles.levelTitle, { color: colors.text }]}>Jeeves Level {jeevesLevel.level}</Text>
          <View style={styles.xpBar}>
            <View style={[styles.xpFill, { width: `${Math.min(100, (jeevesLevel.xp / jeevesLevel.xp_to_next) * 100)}%` }]} />
          </View>
          <Text style={[styles.xpText, { color: colors.textMuted }]}>
            {jeevesLevel.xp}/{jeevesLevel.xp_to_next} XP • Cap: 1,000,000
          </Text>
        </View>
      </View>

      {/* System Blurbs */}
      <TouchableOpacity onPress={() => setShowBlurbs(!showBlurbs)} style={[styles.blurbToggle, { backgroundColor: colors.surface, borderColor: colors.border }]}>
        <Ionicons name="shield-checkmark" size={18} color="#EF4444" />
        <Text style={[styles.blurbToggleText, { color: colors.text }]}>3 System Laws</Text>
        <Ionicons name={showBlurbs ? 'chevron-up' : 'chevron-down'} size={16} color={colors.textMuted} />
      </TouchableOpacity>

      {showBlurbs && blurbs.map(b => (
        <View key={b.id} style={[styles.blurbCard, { backgroundColor: b.color + '10', borderColor: b.color + '30' }]}>
          <View style={styles.blurbHeader}>
            <Ionicons name={b.icon as any} size={16} color={b.color} />
            <Text style={[styles.blurbLaw, { color: b.color }]}>{b.law}</Text>
          </View>
          <Text style={[styles.blurbText, { color: colors.text }]}>{b.text}</Text>
        </View>
      ))}

      {/* Chat Rooms */}
      <Text style={[styles.sectionTitle, { color: colors.text }]}>Chat Rooms</Text>
      {rooms.map(room => (
        <TouchableOpacity
          key={room.id}
          style={[styles.roomCard, { backgroundColor: room.color + '10', borderColor: room.color + '30' }]}
          onPress={() => selectRoom(room)}
        >
          <View style={[styles.roomIcon, { backgroundColor: room.color + '20' }]}>
            <Ionicons name={room.icon as any} size={22} color={room.color} />
          </View>
          <View style={styles.roomInfo}>
            <Text style={[styles.roomName, { color: colors.text }]}>{room.name}</Text>
            <Text style={[styles.roomDesc, { color: colors.textMuted }]}>{room.description}</Text>
            <Text style={[styles.roomAgents, { color: room.color }]}>{room.agents.length} agents</Text>
          </View>
          <Ionicons name="chevron-forward" size={18} color={colors.textMuted} />
        </TouchableOpacity>
      ))}

      {/* Pipeline Agents */}
      <Text style={[styles.sectionTitle, { color: colors.text }]}>Pipeline Agents</Text>
      {agents.map(agent => (
        <View key={agent.id} style={[styles.agentCard, { backgroundColor: colors.surface, borderColor: colors.border }]}>
          <View style={[styles.agentAvatar, { backgroundColor: agent.avatar_color + '20' }]}>
            <Ionicons name={agent.icon as any} size={20} color={agent.avatar_color} />
          </View>
          <View style={styles.agentInfo}>
            <Text style={[styles.agentName, { color: colors.text }]}>{agent.name}</Text>
            <Text style={[styles.agentRole, { color: colors.textMuted }]}>{agent.role}</Text>
            <Text style={[styles.agentSpecialty, { color: agent.avatar_color }]} numberOfLines={1}>{agent.specialty}</Text>
          </View>
        </View>
      ))}

      <View style={{ height: 40 }} />
    </ScrollView>
  );

  const renderChat = () => (
    <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : 'height'}>
      {/* Chat Header */}
      <View style={[styles.chatHeader, { backgroundColor: selectedRoom?.color + '10', borderBottomColor: colors.border }]}>
        <TouchableOpacity onPress={() => setSelectedRoom(null)} style={styles.backBtn}>
          <Ionicons name="arrow-back" size={22} color={colors.text} />
        </TouchableOpacity>
        <View style={[styles.chatIcon, { backgroundColor: selectedRoom?.color + '20' }]}>
          <Ionicons name={(selectedRoom?.icon || 'chatbubbles') as any} size={18} color={selectedRoom?.color} />
        </View>
        <View style={styles.chatHeaderInfo}>
          <Text style={[styles.chatHeaderTitle, { color: colors.text }]}>{selectedRoom?.name}</Text>
          <Text style={[styles.chatHeaderSub, { color: colors.textMuted }]}>{selectedRoom?.agents.length} agents</Text>
        </View>
      </View>

      {/* Messages */}
      <ScrollView ref={scrollRef} style={styles.messagesArea} showsVerticalScrollIndicator={false}>
        {/* System blurbs always shown */}
        <View style={[styles.systemMsg, { backgroundColor: '#EF444410' }]}>
          <Ionicons name="shield-checkmark" size={14} color="#EF4444" />
          <Text style={[styles.systemMsgText, { color: '#EF4444' }]}>3 System Laws Active • AAA Standards Enforced</Text>
        </View>

        {messages.length === 0 ? (
          <View style={styles.emptyChat}>
            <Ionicons name="chatbubble-ellipses" size={48} color={colors.textMuted} />
            <Text style={[styles.emptyChatText, { color: colors.textMuted }]}>Start the conversation!</Text>
            <Text style={[styles.emptyChatSub, { color: colors.textMuted }]}>All agents are listening. Code blocks are auto-stored in Vault.</Text>
          </View>
        ) : (
          messages.map((msg, idx) => {
            const agent = msg.agent_id ? getAgentInfo(msg.agent_id) : null;
            const isUser = !msg.agent_id;
            return (
              <View key={idx} style={[styles.msgBubble, isUser ? styles.msgUser : styles.msgAgent, { backgroundColor: isUser ? colors.primary + '15' : agent ? agent.avatar_color + '10' : colors.surface }]}>
                {agent && (
                  <View style={styles.msgAgentHeader}>
                    <Ionicons name={agent.icon as any} size={14} color={agent.avatar_color} />
                    <Text style={[styles.msgAgentName, { color: agent.avatar_color }]}>{agent.name}</Text>
                  </View>
                )}
                <Text style={[styles.msgText, { color: colors.text }]}>{msg.content}</Text>
                {msg.code_blocks && msg.code_blocks.length > 0 && (
                  <View style={[styles.codeBlock, { backgroundColor: '#1E1E2E' }]}>
                    {msg.code_blocks.map((code, ci) => (
                      <Text key={ci} style={styles.codeText}>{code}</Text>
                    ))}
                    <View style={styles.vaultBadge}>
                      <Ionicons name="lock-closed" size={10} color="#22C55E" />
                      <Text style={styles.vaultBadgeText}>Stored in Vault</Text>
                    </View>
                  </View>
                )}
                <Text style={[styles.msgTime, { color: colors.textMuted }]}>
                  {new Date(msg.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                </Text>
              </View>
            );
          })
        )}
        <View style={{ height: 16 }} />
      </ScrollView>

      {/* Input */}
      <View style={[styles.inputBar, { backgroundColor: colors.surface, borderTopColor: colors.border }]}>
        <TextInput
          value={inputText}
          onChangeText={setInputText}
          placeholder="Message all agents..."
          placeholderTextColor={colors.textMuted}
          style={[styles.input, { color: colors.text, backgroundColor: colors.background }]}
          multiline
          maxLength={4000}
        />
        <TouchableOpacity
          onPress={sendMessage}
          style={[styles.sendBtn, { backgroundColor: inputText.trim() ? colors.primary : colors.border }]}
          disabled={!inputText.trim()}
        >
          <Ionicons name="send" size={18} color="#FFF" />
        </TouchableOpacity>
      </View>
    </KeyboardAvoidingView>
  );

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <View style={[styles.overlay, { backgroundColor: colors.background }]}>
        {/* Header */}
        <View style={[styles.header, { borderBottomColor: colors.border }]}>
          <TouchableOpacity onPress={selectedRoom ? () => setSelectedRoom(null) : onClose} style={styles.backBtn}>
            <Ionicons name="arrow-back" size={24} color={colors.text} />
          </TouchableOpacity>
          <View style={styles.headerCenter}>
            <Text style={[styles.headerTitle, { color: colors.text }]}>
              {selectedRoom ? selectedRoom.name : "Creator's Studio"}
            </Text>
            <Text style={[styles.headerSub, { color: colors.textMuted }]}>
              {selectedRoom ? 'Group Chat' : `${agents.length} Agents • ${rooms.length} Rooms`}
            </Text>
          </View>
          <View style={[styles.levelBadge, { backgroundColor: '#8B5CF620' }]}>
            <Text style={styles.levelBadgeText}>Lv.{jeevesLevel.level}</Text>
          </View>
        </View>

        {loading ? (
          <View style={styles.loadingView}>
            <ActivityIndicator size="large" color={colors.primary} />
          </View>
        ) : selectedRoom ? renderChat() : renderRoomList()}
      </View>
    </Modal>
  );
};

const styles = StyleSheet.create({
  overlay: { flex: 1 },
  header: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16, paddingVertical: 14, borderBottomWidth: 1 },
  backBtn: { padding: 4 },
  headerCenter: { flex: 1, marginLeft: 12 },
  headerTitle: { fontSize: 18, fontWeight: '700' },
  headerSub: { fontSize: 12, marginTop: 2 },
  levelBadge: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: 10 },
  levelBadgeText: { color: '#8B5CF6', fontSize: 12, fontWeight: '800' },
  loadingView: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  content: { flex: 1, paddingHorizontal: 16 },
  levelCard: { flexDirection: 'row', alignItems: 'center', padding: 14, borderRadius: 14, marginTop: 16, borderWidth: 1, gap: 12 },
  levelCircle: { width: 48, height: 48, borderRadius: 24, justifyContent: 'center', alignItems: 'center' },
  levelNum: { color: '#FFF', fontSize: 18, fontWeight: '800' },
  levelInfo: { flex: 1 },
  levelTitle: { fontSize: 16, fontWeight: '700' },
  xpBar: { height: 6, borderRadius: 3, backgroundColor: 'rgba(0,0,0,0.1)', marginTop: 6, overflow: 'hidden' },
  xpFill: { height: '100%', borderRadius: 3, backgroundColor: '#8B5CF6' },
  xpText: { fontSize: 11, marginTop: 4 },
  blurbToggle: { flexDirection: 'row', alignItems: 'center', gap: 8, padding: 12, borderRadius: 10, marginTop: 12, borderWidth: 1 },
  blurbToggleText: { flex: 1, fontSize: 14, fontWeight: '600' },
  blurbCard: { padding: 12, borderRadius: 10, marginTop: 8, borderWidth: 1 },
  blurbHeader: { flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 6 },
  blurbLaw: { fontSize: 12, fontWeight: '800' },
  blurbText: { fontSize: 13, lineHeight: 18 },
  sectionTitle: { fontSize: 16, fontWeight: '700', marginTop: 20, marginBottom: 10 },
  roomCard: { flexDirection: 'row', alignItems: 'center', padding: 14, borderRadius: 14, marginBottom: 10, borderWidth: 1, gap: 12 },
  roomIcon: { width: 44, height: 44, borderRadius: 14, justifyContent: 'center', alignItems: 'center' },
  roomInfo: { flex: 1 },
  roomName: { fontSize: 15, fontWeight: '700' },
  roomDesc: { fontSize: 12, marginTop: 2 },
  roomAgents: { fontSize: 11, fontWeight: '600', marginTop: 4 },
  agentCard: { flexDirection: 'row', alignItems: 'center', padding: 12, borderRadius: 12, marginBottom: 8, borderWidth: 1, gap: 10 },
  agentAvatar: { width: 40, height: 40, borderRadius: 12, justifyContent: 'center', alignItems: 'center' },
  agentInfo: { flex: 1 },
  agentName: { fontSize: 14, fontWeight: '700' },
  agentRole: { fontSize: 11, marginTop: 1 },
  agentSpecialty: { fontSize: 11, marginTop: 2, fontWeight: '500' },
  chatHeader: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16, paddingVertical: 10, borderBottomWidth: 1, gap: 10 },
  chatIcon: { width: 36, height: 36, borderRadius: 10, justifyContent: 'center', alignItems: 'center' },
  chatHeaderInfo: { flex: 1 },
  chatHeaderTitle: { fontSize: 16, fontWeight: '700' },
  chatHeaderSub: { fontSize: 11 },
  messagesArea: { flex: 1, paddingHorizontal: 16, paddingTop: 8 },
  systemMsg: { flexDirection: 'row', alignItems: 'center', gap: 6, padding: 8, borderRadius: 8, marginBottom: 10 },
  systemMsgText: { fontSize: 11, fontWeight: '600' },
  emptyChat: { alignItems: 'center', paddingTop: 60, gap: 8 },
  emptyChatText: { fontSize: 16, fontWeight: '600' },
  emptyChatSub: { fontSize: 13, textAlign: 'center', paddingHorizontal: 40 },
  msgBubble: { padding: 12, borderRadius: 14, marginBottom: 8, maxWidth: '85%' },
  msgUser: { alignSelf: 'flex-end' },
  msgAgent: { alignSelf: 'flex-start' },
  msgAgentHeader: { flexDirection: 'row', alignItems: 'center', gap: 4, marginBottom: 4 },
  msgAgentName: { fontSize: 11, fontWeight: '700' },
  msgText: { fontSize: 14, lineHeight: 20 },
  codeBlock: { padding: 10, borderRadius: 8, marginTop: 8 },
  codeText: { fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace', color: '#E2E8F0', fontSize: 12 },
  vaultBadge: { flexDirection: 'row', alignItems: 'center', gap: 4, marginTop: 6 },
  vaultBadgeText: { color: '#22C55E', fontSize: 10, fontWeight: '600' },
  msgTime: { fontSize: 10, marginTop: 4, textAlign: 'right' },
  inputBar: { flexDirection: 'row', alignItems: 'flex-end', padding: 10, borderTopWidth: 1, gap: 8 },
  input: { flex: 1, borderRadius: 12, paddingHorizontal: 14, paddingVertical: 10, fontSize: 14, maxHeight: 100 },
  sendBtn: { width: 40, height: 40, borderRadius: 20, justifyContent: 'center', alignItems: 'center' },
});
