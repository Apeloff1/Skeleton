/**
 * Jeeves AI Tutor Modal v2026.0
 * Complete 2026 UI overhaul — auto-scroll, proper sizing, modern design
 */

import { NATIVE_DRIVER } from '../../src/utils/platformStyles';
import React, { useState, useEffect, useRef, useCallback } from 'react';
import { API_BASE } from '../../utils/apiBase';
import {
  View, Text, StyleSheet, TouchableOpacity, ScrollView, TextInput,
  Modal, Dimensions, Platform, KeyboardAvoidingView,
  Animated, Keyboard,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useModalStore } from '../../store/modalStore';
import { useRouter } from 'expo-router';

import { apiFetch } from '../../utils/apiController';
const API_URL = API_BASE;
const { width: SW } = Dimensions.get('window');

interface JeevesModalProps {
  visible: boolean;
  onClose: () => void;
  colors: any;
  currentCode?: string;
  currentLanguage?: string;
}

type Personality = 'formal' | 'friendly' | 'encouraging' | 'concise';
type SkillLevel = 'beginner' | 'intermediate' | 'advanced' | 'expert';

interface Message {
  id: string;
  type: 'user' | 'jeeves';
  content: string;
  timestamp: Date;
}

const WELCOME: Record<Personality, string> = {
  formal: "Good day. I am Jeeves, your AI code butler. How may I assist?",
  friendly: "Hey! I'm Jeeves, your coding buddy. What are we building?",
  encouraging: "Welcome! I'm Jeeves — let's learn something amazing today!",
  concise: "Jeeves here. Ask me anything.",
};

export const JeevesModal: React.FC<JeevesModalProps> = ({
  visible, onClose, colors, currentCode = '', currentLanguage = 'python'
}) => {
  const insets = useSafeAreaInsets();
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputText, setInputText] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [personality, setPersonality] = useState<Personality>('friendly');
  const [skillLevel, setSkillLevel] = useState<SkillLevel>('intermediate');
  const [showSettings, setShowSettings] = useState(false);
  const scrollRef = useRef<ScrollView>(null);
  const sessionId = useRef(`jeeves-${Date.now()}`);
  const dotAnim = useRef(new Animated.Value(0)).current;

  // Auto-scroll to bottom on new messages
  const scrollToBottom = useCallback(() => {
    setTimeout(() => scrollRef.current?.scrollToEnd({ animated: true }), 80);
  }, []);

  useEffect(() => {
    if (visible && messages.length === 0) {
      setMessages([{ id: '1', type: 'jeeves', content: WELCOME[personality], timestamp: new Date() }]);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visible]);

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { scrollToBottom(); }, [messages, isLoading]);

  // Typing dots animation
  useEffect(() => {
    if (!isLoading) return;
    const anim = Animated.loop(
      Animated.sequence([
        Animated.timing(dotAnim, { toValue: 1, duration: 600, useNativeDriver: NATIVE_DRIVER }),
        Animated.timing(dotAnim, { toValue: 0, duration: 600, useNativeDriver: NATIVE_DRIVER }),
      ])
    );
    anim.start();
    return () => anim.stop();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isLoading]);

  const addMsg = (type: 'user' | 'jeeves', content: string) => {
    setMessages(prev => [...prev, { id: `${Date.now()}-${type[0]}`, type, content, timestamp: new Date() }]);
  };

  const sendMessage = async () => {
    const text = inputText.trim();
    if (!text || isLoading) return;
    addMsg('user', text);
    setInputText('');
    Keyboard.dismiss();
    setIsLoading(true);
    try {
      const res = await apiFetch(`${API_URL}/api/jeeves/ask`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: text,
          context: currentCode || undefined,
          skill_level: skillLevel,
          language: currentLanguage,
          personality,
          session_id: sessionId.current,
        }),
      });
      const data = await res.json();
      addMsg('jeeves', data.jeeves_response || 'Sorry, I had trouble responding. Try again.');
    } catch {
      addMsg('jeeves', 'Connection issue — please try again.');
    } finally {
      setIsLoading(false);
    }
  };

  const quickAsk = async (type: string) => {
    if (type === 'master_build') {
      onClose();
      setTimeout(() => useModalStore.getState().openModal('gameFactory' as any), 300);
      return;
    }
    if (type === 'concept') {
      addMsg('jeeves', 'What concept would you like me to teach? Type below!');
      return;
    }
    if ((type === 'explain' || type === 'debug') && !currentCode) {
      addMsg('jeeves', 'I need some code in the editor first. Write or paste code, then try again!');
      return;
    }
    setIsLoading(true);
    try {
      let endpoint = '';
      let body: any = {};
      if (type === 'explain') {
        endpoint = '/api/jeeves/explain';
        body = { code: currentCode, language: currentLanguage, depth: skillLevel === 'beginner' ? 'beginner' : 'detailed' };
      } else if (type === 'debug') {
        endpoint = '/api/jeeves/debug-help';
        body = { code: currentCode, language: currentLanguage, skill_level: skillLevel };
      } else if (type === 'practice') {
        endpoint = '/api/jeeves/practice';
        body = { topic: currentLanguage, difficulty: skillLevel === 'beginner' ? 'easy' : 'medium', language: currentLanguage, count: 3 };
      } else if (type === 'motivate') {
        endpoint = '/api/jeeves/motivate?mood=stuck';
        body = {};
      }
      const res = await apiFetch(`${API_URL}${endpoint}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
      const data = await res.json();
      const content = data.explanation || data.debug_assistance || data.lesson || data.practice_problems || data.message || JSON.stringify(data, null, 2);
      addMsg('jeeves', content);
    } catch {
      addMsg('jeeves', 'Something went wrong. Try again.');
    } finally {
      setIsLoading(false);
    }
  };

  const actions = [
    { key: 'master_build', icon: 'planet-outline', label: 'Galaxy Studio', color: '#8B5CF6' },
    { key: 'explain', icon: 'book-outline', label: 'Explain', color: '#3B82F6' },
    { key: 'debug', icon: 'bug-outline', label: 'Debug', color: '#EF4444' },
    { key: 'practice', icon: 'barbell-outline', label: 'Practice', color: '#10B981' },
    { key: 'motivate', icon: 'heart-outline', label: 'Motivate', color: '#EC4899' },
  ];

  // AI Tools — launchers for the dedicated tool modals, surfaced in the Jeeves AI Tutor.
  const aiTools = [
    { key: 'powerhouse', icon: 'planet', label: 'Powerhouse', color: '#A78BFA', route: '/jeeves-hub' },
    { key: 'zaibatsu', icon: 'git-network', label: 'Zaibatsu CNS', color: '#22c55e', route: '/zaibatsu' },
    { key: 'ai_assistant', icon: 'chatbubbles', label: 'AI Assistant', color: '#8B5CF6', modal: 'ai' },
    { key: 'copilot', icon: 'sparkles', label: 'Copilot', color: '#a78bfa', modal: 'ai' },
    { key: 'intelligence', icon: 'bulb', label: 'Code Intel', color: '#3B82F6', modal: 'codeIntelligence' },
    { key: 'ai_review', icon: 'eye', label: 'Code Review', color: '#10B981', modal: 'codeIntelligence' },
    { key: 'ai_security', icon: 'shield', label: 'Security', color: '#f59e0b', modal: 'codeIntelligence' },
    { key: 'ai_pipeline', icon: 'flash', label: 'Code Gen', color: '#fbbf24', modal: 'aiPipeline' },
    { key: 'debugger', icon: 'bug', label: 'Debugger', color: '#ef4444', modal: 'debugger' },
    { key: 'code_to_app', icon: 'apps', label: 'Code to App', color: '#3B82F6', modal: 'codeToApp' },
    { key: 'imagine', icon: 'image', label: 'Imagine', color: '#ec4899', modal: 'imagine' },
    { key: 'multi_agent', icon: 'people', label: 'Multi-Agent', color: '#10B981', modal: 'multiAgent' },
  ];

  const router = useRouter();
  const openTool = (t: { modal?: string; route?: string }) => {
    onClose();
    setTimeout(() => {
      if (t.route) router.push(t.route as any);
      else if (t.modal) useModalStore.getState().openModal(t.modal as any);
    }, 300);
  };

  const bg = colors.background || '#0a0a1a';
  const surface = colors.surface || '#141428';
  const surfaceAlt = colors.surfaceAlt || '#1e1e3a';
  const text = colors.text || '#e0e0ff';
  const muted = colors.textMuted || '#777';
  const primary = colors.primary || '#6366F1';
  const border = colors.border || '#222';

  return (
    <Modal visible={visible} animationType="slide" presentationStyle="pageSheet" onRequestClose={onClose}>
      <KeyboardAvoidingView
        style={[styles.root, { backgroundColor: bg, paddingTop: insets.top }]}
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        keyboardVerticalOffset={Platform.OS === 'ios' ? 0 : 20}
      >
        {/* ─── Header ─── */}
        <View style={[styles.header, { borderBottomColor: border }]} testID="jeeves-header">
          <TouchableOpacity onPress={onClose} style={styles.hBtn} testID="jeeves-close-btn">
            <Ionicons name="chevron-down" size={26} color={text} />
          </TouchableOpacity>
          <View style={styles.hCenter}>
            <View style={[styles.avatar, { backgroundColor: primary + '18' }]}>
              <Ionicons name="school" size={22} color={primary} />
            </View>
            <View>
              <Text style={[styles.hTitle, { color: text }]}>Jeeves</Text>
              <Text style={[styles.hSub, { color: isLoading ? '#10B981' : muted }]}>
                {isLoading ? 'Thinking...' : 'AI Tutor'}
              </Text>
            </View>
          </View>
          <TouchableOpacity onPress={() => setShowSettings(!showSettings)} style={styles.hBtn} testID="jeeves-settings-btn">
            <Ionicons name={showSettings ? 'close' : 'options-outline'} size={22} color={text} />
          </TouchableOpacity>
        </View>

        {/* ─── Settings Panel ─── */}
        {showSettings && (
          <View style={[styles.settings, { backgroundColor: surface, borderBottomColor: border }]} testID="jeeves-settings-panel">
            <Text style={[styles.sLabel, { color: muted }]}>Personality</Text>
            <View style={styles.row}>
              {([
                { key: 'formal' as const, icon: 'ribbon', label: 'Formal', c: '#6366F1' },
                { key: 'friendly' as const, icon: 'happy', label: 'Friendly', c: '#10B981' },
                { key: 'encouraging' as const, icon: 'heart', label: 'Coach', c: '#EC4899' },
                { key: 'concise' as const, icon: 'flash', label: 'Direct', c: '#F59E0B' },
              ]).map(p => (
                <TouchableOpacity
                  key={p.key}
                  style={[styles.chip, { backgroundColor: personality === p.key ? p.c + '22' : surfaceAlt, borderColor: personality === p.key ? p.c : 'transparent' }]}
                  onPress={() => setPersonality(p.key)}
                >
                  <Ionicons name={p.icon as any} size={18} color={personality === p.key ? p.c : muted} />
                  <Text style={[styles.chipText, { color: personality === p.key ? p.c : text }]}>{p.label}</Text>
                </TouchableOpacity>
              ))}
            </View>
            <Text style={[styles.sLabel, { color: muted, marginTop: 12 }]}>Skill Level</Text>
            <View style={styles.row}>
              {(['beginner', 'intermediate', 'advanced', 'expert'] as SkillLevel[]).map(s => (
                <TouchableOpacity
                  key={s}
                  style={[styles.lvlChip, { backgroundColor: skillLevel === s ? primary : surfaceAlt }]}
                  onPress={() => setSkillLevel(s)}
                >
                  <Text style={[styles.lvlText, { color: skillLevel === s ? '#fff' : text }]}>{s.charAt(0).toUpperCase() + s.slice(1)}</Text>
                </TouchableOpacity>
              ))}
            </View>
            <TouchableOpacity
              style={[styles.resetBtn, { backgroundColor: surfaceAlt }]}
              onPress={() => { setMessages([]); sessionId.current = `jeeves-${Date.now()}`; setShowSettings(false); }}
            >
              <Ionicons name="refresh" size={16} color={primary} />
              <Text style={[styles.resetText, { color: primary }]}>New Conversation</Text>
            </TouchableOpacity>
          </View>
        )}

        {/* ─── Quick Actions ─── */}
        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={[styles.actionsBar, { borderBottomColor: border }]} contentContainerStyle={styles.actionsContent}>
          {actions.map(a => (
            <TouchableOpacity
              key={a.key}
              style={[styles.action, { backgroundColor: a.color + '15' }]}
              onPress={() => quickAsk(a.key)}
              disabled={isLoading}
              testID={`jeeves-action-${a.key}`}
            >
              <Ionicons name={a.icon as any} size={16} color={a.color} />
              <Text style={[styles.actionText, { color: a.color }]}>{a.label}</Text>
            </TouchableOpacity>
          ))}
        </ScrollView>

        {/* ─── AI Tools (surfaced in the Jeeves AI Tutor) ─── */}
        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={[styles.actionsBar, { borderBottomColor: border }]} contentContainerStyle={styles.actionsContent}>
          {aiTools.map(t => (
            <TouchableOpacity
              key={t.key}
              style={[styles.action, { backgroundColor: t.color + '15' }]}
              onPress={() => openTool(t)}
              testID={`jeeves-tool-${t.key}`}
            >
              <Ionicons name={t.icon as any} size={16} color={t.color} />
              <Text style={[styles.actionText, { color: t.color }]}>{t.label}</Text>
            </TouchableOpacity>
          ))}
        </ScrollView>

        {/* ─── Messages ─── */}
        <ScrollView
          ref={scrollRef}
          style={styles.messages}
          contentContainerStyle={styles.msgContent}
          keyboardShouldPersistTaps="handled"
          keyboardDismissMode="interactive"
          onContentSizeChange={scrollToBottom}
          testID="jeeves-message-list"
        >
          {messages.map(msg => (
            <View
              key={msg.id}
              style={[
                styles.bubble,
                msg.type === 'user' ? styles.userBubble : styles.jBubble,
                {
                  backgroundColor: msg.type === 'user' ? primary : surfaceAlt,
                  maxWidth: SW * 0.82,
                },
              ]}
              testID={`jeeves-msg-${msg.id}`}
            >
              {msg.type === 'jeeves' && (
                <View style={[styles.bIcon, { backgroundColor: primary + '18' }]}>
                  <Ionicons name="school" size={14} color={primary} />
                </View>
              )}
              <Text
                style={[
                  styles.msgText,
                  { color: msg.type === 'user' ? '#fff' : text },
                ]}
                selectable
              >
                {msg.content}
              </Text>
            </View>
          ))}

          {isLoading && (
            <View style={[styles.bubble, styles.jBubble, { backgroundColor: surfaceAlt, maxWidth: 120 }]} testID="jeeves-typing-indicator">
              <Animated.View style={[styles.dot, { backgroundColor: primary, opacity: dotAnim }]} />
              <Animated.View style={[styles.dot, { backgroundColor: primary, opacity: dotAnim, marginHorizontal: 4 }]} />
              <Animated.View style={[styles.dot, { backgroundColor: primary, opacity: dotAnim }]} />
            </View>
          )}
        </ScrollView>

        {/* ─── Input ─── */}
        <View style={[styles.inputBar, { backgroundColor: surface, borderTopColor: border, paddingBottom: Math.max(insets.bottom, 8) }]} testID="jeeves-input-bar">
          <TextInput
            style={[styles.input, { backgroundColor: surfaceAlt, color: text }]}
            value={inputText}
            onChangeText={setInputText}
            placeholder="Ask Jeeves anything..."
            placeholderTextColor={muted}
            multiline
            maxLength={2000}
            blurOnSubmit={false}
            onSubmitEditing={sendMessage}
            testID="jeeves-text-input"
          />
          <TouchableOpacity
            style={[styles.sendBtn, { backgroundColor: inputText.trim() ? primary : surfaceAlt }]}
            onPress={sendMessage}
            disabled={!inputText.trim() || isLoading}
            testID="jeeves-send-btn"
          >
            <Ionicons name="arrow-up" size={22} color={inputText.trim() ? '#fff' : muted} />
          </TouchableOpacity>
        </View>
      </KeyboardAvoidingView>
    </Modal>
  );
};

const styles = StyleSheet.create({
  root: { flex: 1 },
  // Header
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 14, paddingVertical: 12, borderBottomWidth: 1 },
  hBtn: { width: 44, height: 44, justifyContent: 'center', alignItems: 'center', borderRadius: 22 },
  hCenter: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  avatar: { width: 38, height: 38, borderRadius: 19, justifyContent: 'center', alignItems: 'center' },
  hTitle: { fontSize: 17, fontWeight: '700', letterSpacing: 0.3 },
  hSub: { fontSize: 11, fontWeight: '500' },
  // Settings
  settings: { padding: 14, borderBottomWidth: 1 },
  sLabel: { fontSize: 12, fontWeight: '700', marginBottom: 8, textTransform: 'uppercase', letterSpacing: 1 },
  row: { flexDirection: 'row', gap: 8 },
  chip: { flex: 1, alignItems: 'center', paddingVertical: 10, borderRadius: 10, borderWidth: 1.5, gap: 4 },
  chipText: { fontSize: 11, fontWeight: '600' },
  lvlChip: { flex: 1, paddingVertical: 8, borderRadius: 8, alignItems: 'center' },
  lvlText: { fontSize: 11, fontWeight: '600' },
  resetBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, paddingVertical: 10, borderRadius: 8, marginTop: 12 },
  resetText: { fontSize: 13, fontWeight: '600' },
  // Actions
  actionsBar: { maxHeight: 56, borderBottomWidth: 1 },
  actionsContent: { paddingHorizontal: 12, paddingVertical: 10, gap: 8, flexDirection: 'row', alignItems: 'center' },
  action: {
    flexDirection: 'row', alignItems: 'center', gap: 6,
    paddingHorizontal: 14, paddingVertical: 8,
    borderRadius: 18, minHeight: 34, flexShrink: 0,
  },
  actionText: { fontSize: 12, fontWeight: '600', flexShrink: 0 },
  // Messages
  messages: { flex: 1 },
  msgContent: { paddingHorizontal: 14, paddingVertical: 12, gap: 10, paddingBottom: 20 },
  bubble: { padding: 12, borderRadius: 16 },
  userBubble: { alignSelf: 'flex-end', borderBottomRightRadius: 4 },
  jBubble: { alignSelf: 'flex-start', borderBottomLeftRadius: 4, flexDirection: 'row', alignItems: 'flex-start', gap: 8 },
  bIcon: { width: 24, height: 24, borderRadius: 12, justifyContent: 'center', alignItems: 'center', marginTop: 2 },
  msgText: { fontSize: 14, lineHeight: 21, flexShrink: 1 },
  dot: { width: 8, height: 8, borderRadius: 4 },
  // Input
  inputBar: { flexDirection: 'row', alignItems: 'flex-end', paddingHorizontal: 10, paddingTop: 8, gap: 8, borderTopWidth: 1 },
  input: { flex: 1, maxHeight: 100, paddingHorizontal: 14, paddingVertical: 10, borderRadius: 22, fontSize: 15, lineHeight: 20 },
  sendBtn: { width: 42, height: 42, borderRadius: 21, justifyContent: 'center', alignItems: 'center', marginBottom: 2 },
});
