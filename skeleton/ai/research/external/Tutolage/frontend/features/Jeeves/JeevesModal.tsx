/**
 * Jeeves AI Tutor Modal v11.0.0
 * Your Personal AI Code Butler & Mentor
 */

import React, { useState, useEffect, useRef } from 'react';
import {
  View, Text, StyleSheet, TouchableOpacity, ScrollView, TextInput,
  Modal, ActivityIndicator, Dimensions, Platform, KeyboardAvoidingView,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';

const API_URL = process.env.EXPO_PUBLIC_BACKEND_URL || 'http://localhost:8001';
const { width: SCREEN_WIDTH } = Dimensions.get('window');

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

export const JeevesModal: React.FC<JeevesModalProps> = ({
  visible, onClose, colors, currentCode = '', currentLanguage = 'python'
}) => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputText, setInputText] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [personality, setPersonality] = useState<Personality>('friendly');
  const [skillLevel, setSkillLevel] = useState<SkillLevel>('intermediate');
  const [showSettings, setShowSettings] = useState(false);
  const [tipOfDay, setTipOfDay] = useState<string | null>(null);
  const scrollRef = useRef<ScrollView>(null);
  const sessionId = useRef(`jeeves-${Date.now()}`);

  useEffect(() => {
    if (visible && messages.length === 0) {
      loadTipOfDay();
      // Welcome message
      setMessages([{
        id: '1',
        type: 'jeeves',
        content: getWelcomeMessage(),
        timestamp: new Date()
      }]);
    }
  }, [visible]);

  const getWelcomeMessage = () => {
    const greetings: Record<Personality, string> = {
      formal: "Good day. I am Jeeves, your AI code butler. How may I be of assistance today?",
      friendly: "Hey there! 👋 I'm Jeeves, your coding buddy. What are we building today?",
      encouraging: "Welcome! 🌟 I'm Jeeves, and I'm SO excited to help you code! You're going to do amazing things!",
      concise: "Jeeves here. How can I help?"
    };
    return greetings[personality];
  };

  const loadTipOfDay = async () => {
    try {
      const response = await fetch(`${API_URL}/api/jeeves/tip-of-the-day?language=${currentLanguage}&level=${skillLevel}`);
      const data = await response.json();
      setTipOfDay(data.tip);
    } catch (error) {
      console.error('Failed to load tip:', error);
    }
  };

  const sendMessage = async () => {
    if (!inputText.trim() || isLoading) return;
    
    const userMessage: Message = {
      id: Date.now().toString(),
      type: 'user',
      content: inputText.trim(),
      timestamp: new Date()
    };
    
    setMessages(prev => [...prev, userMessage]);
    setInputText('');
    setIsLoading(true);
    
    try {
      const response = await fetch(`${API_URL}/api/jeeves/ask`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: userMessage.content,
          context: currentCode || undefined,
          skill_level: skillLevel,
          language: currentLanguage,
          personality,
          session_id: sessionId.current
        })
      });
      const data = await response.json();
      
      const jeevesMessage: Message = {
        id: Date.now().toString() + '-j',
        type: 'jeeves',
        content: data.jeeves_response || 'I apologize, but I encountered an issue. Please try again.',
        timestamp: new Date()
      };
      
      setMessages(prev => [...prev, jeevesMessage]);
    } catch (error) {
      console.error('Jeeves error:', error);
      setMessages(prev => [...prev, {
        id: Date.now().toString() + '-e',
        type: 'jeeves',
        content: 'I seem to be having a moment. Please try again.',
        timestamp: new Date()
      }]);
    } finally {
      setIsLoading(false);
      setTimeout(() => scrollRef.current?.scrollToEnd({ animated: true }), 100);
    }
  };

  const askForHelp = async (type: 'explain' | 'debug' | 'concept' | 'practice' | 'motivate') => {
    setIsLoading(true);
    
    try {
      let endpoint = '';
      let body: any = {};
      
      switch (type) {
        case 'explain':
          if (!currentCode) {
            setMessages(prev => [...prev, {
              id: Date.now().toString(),
              type: 'jeeves',
              content: 'I\'d be happy to explain code, but I don\'t see any code in the editor. Please write or paste some code first!',
              timestamp: new Date()
            }]);
            setIsLoading(false);
            return;
          }
          endpoint = '/api/jeeves/explain';
          body = { code: currentCode, language: currentLanguage, depth: skillLevel === 'beginner' ? 'beginner' : 'detailed' };
          break;
        case 'debug':
          if (!currentCode) {
            setMessages(prev => [...prev, {
              id: Date.now().toString(),
              type: 'jeeves',
              content: 'I need to see some code to help debug it. Please add code to the editor!',
              timestamp: new Date()
            }]);
            setIsLoading(false);
            return;
          }
          endpoint = '/api/jeeves/debug-help';
          body = { code: currentCode, language: currentLanguage, skill_level: skillLevel };
          break;
        case 'concept':
          endpoint = '/api/jeeves/teach-concept';
          body = { concept: 'a coding concept', skill_level: skillLevel, language: currentLanguage, include_examples: true };
          // For concept, we'll use the input field
          setMessages(prev => [...prev, {
            id: Date.now().toString(),
            type: 'jeeves',
            content: 'What concept would you like me to teach you? Just type it below!',
            timestamp: new Date()
          }]);
          setIsLoading(false);
          return;
        case 'practice':
          endpoint = '/api/jeeves/practice';
          body = { topic: currentLanguage, difficulty: skillLevel === 'beginner' ? 'easy' : skillLevel === 'expert' ? 'hard' : 'medium', language: currentLanguage, count: 3 };
          break;
        case 'motivate':
          endpoint = '/api/jeeves/motivate?mood=stuck';
          break;
      }
      
      const response = await fetch(`${API_URL}${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      });
      const data = await response.json();
      
      const content = data.explanation || data.debug_assistance || data.lesson || data.practice_problems || data.message || JSON.stringify(data, null, 2);
      
      setMessages(prev => [...prev, {
        id: Date.now().toString(),
        type: 'jeeves',
        content,
        timestamp: new Date()
      }]);
    } catch (error) {
      console.error('Help error:', error);
    } finally {
      setIsLoading(false);
      setTimeout(() => scrollRef.current?.scrollToEnd({ animated: true }), 100);
    }
  };

  const personalities: { key: Personality; icon: string; label: string; color: string }[] = [
    { key: 'formal', icon: 'ribbon', label: 'Formal', color: '#6366F1' },
    { key: 'friendly', icon: 'happy', label: 'Friendly', color: '#10B981' },
    { key: 'encouraging', icon: 'heart', label: 'Coach', color: '#EC4899' },
    { key: 'concise', icon: 'flash', label: 'Direct', color: '#F59E0B' },
  ];

  const skillLevels: { key: SkillLevel; label: string }[] = [
    { key: 'beginner', label: 'Beginner' },
    { key: 'intermediate', label: 'Intermediate' },
    { key: 'advanced', label: 'Advanced' },
    { key: 'expert', label: 'Expert' },
  ];

  const quickActions = [
    { key: 'explain', icon: 'book-outline', label: 'Explain Code', color: '#3B82F6' },
    { key: 'debug', icon: 'bug-outline', label: 'Debug Help', color: '#EF4444' },
    { key: 'practice', icon: 'barbell-outline', label: 'Practice', color: '#10B981' },
    { key: 'motivate', icon: 'heart-outline', label: 'Motivate Me', color: '#EC4899' },
  ];

  const renderSettings = () => (
    <View style={[styles.settingsPanel, { backgroundColor: colors.surface }]}>
      <View style={styles.settingsHeader}>
        <Text style={[styles.settingsTitle, { color: colors.text }]}>Jeeves Settings</Text>
        <TouchableOpacity onPress={() => setShowSettings(false)}>
          <Ionicons name="close" size={24} color={colors.text} />
        </TouchableOpacity>
      </View>

      <Text style={[styles.settingsLabel, { color: colors.textMuted }]}>Personality</Text>
      <View style={styles.personalityGrid}>
        {personalities.map((p) => (
          <TouchableOpacity
            key={p.key}
            style={[styles.personalityCard, { backgroundColor: personality === p.key ? p.color + '20' : colors.surfaceAlt, borderColor: personality === p.key ? p.color : 'transparent' }]}
            onPress={() => setPersonality(p.key)}
          >
            <Ionicons name={p.icon as any} size={24} color={personality === p.key ? p.color : colors.textMuted} />
            <Text style={[styles.personalityLabel, { color: personality === p.key ? p.color : colors.text }]}>{p.label}</Text>
          </TouchableOpacity>
        ))}
      </View>

      <Text style={[styles.settingsLabel, { color: colors.textMuted }]}>Your Skill Level</Text>
      <View style={styles.skillSelector}>
        {skillLevels.map((s) => (
          <TouchableOpacity
            key={s.key}
            style={[styles.skillBtn, { backgroundColor: skillLevel === s.key ? colors.primary : colors.surfaceAlt }]}
            onPress={() => setSkillLevel(s.key)}
          >
            <Text style={[styles.skillText, { color: skillLevel === s.key ? '#FFF' : colors.text }]}>{s.label}</Text>
          </TouchableOpacity>
        ))}
      </View>

      <TouchableOpacity
        style={[styles.resetBtn, { backgroundColor: colors.surfaceAlt }]}
        onPress={() => {
          setMessages([]);
          sessionId.current = `jeeves-${Date.now()}`;
          setShowSettings(false);
        }}
      >
        <Ionicons name="refresh" size={20} color={colors.primary} />
        <Text style={[styles.resetText, { color: colors.primary }]}>Reset Conversation</Text>
      </TouchableOpacity>
    </View>
  );

  return (
    <Modal visible={visible} animationType="slide" presentationStyle="pageSheet" onRequestClose={onClose}>
      <KeyboardAvoidingView
        style={[styles.container, { backgroundColor: colors.background }]}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      >
        {/* Header */}
        <View style={[styles.header, { borderBottomColor: colors.border }]}>
          <TouchableOpacity onPress={onClose} style={styles.closeBtn}>
            <Ionicons name="close" size={24} color={colors.text} />
          </TouchableOpacity>
          <View style={styles.headerTitle}>
            <View style={[styles.jeevesAvatar, { backgroundColor: '#6366F120' }]}>
              <Text style={styles.jeevesEmoji}>🎩</Text>
            </View>
            <View>
              <Text style={[styles.title, { color: colors.text }]}>Jeeves</Text>
              <Text style={[styles.subtitle, { color: colors.textMuted }]}>AI Code Butler</Text>
            </View>
          </View>
          <TouchableOpacity onPress={() => setShowSettings(!showSettings)} style={styles.settingsBtn}>
            <Ionicons name="settings-outline" size={22} color={colors.text} />
          </TouchableOpacity>
        </View>

        {showSettings && renderSettings()}

        {/* Quick Actions */}
        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.quickActionsScroll} contentContainerStyle={styles.quickActionsContent}>
          {quickActions.map((action) => (
            <TouchableOpacity
              key={action.key}
              style={[styles.quickAction, { backgroundColor: action.color + '20' }]}
              onPress={() => askForHelp(action.key as any)}
              disabled={isLoading}
            >
              <Ionicons name={action.icon as any} size={18} color={action.color} />
              <Text style={[styles.quickActionText, { color: action.color }]}>{action.label}</Text>
            </TouchableOpacity>
          ))}
        </ScrollView>

        {/* Messages */}
        <ScrollView
          ref={scrollRef}
          style={styles.messagesContainer}
          contentContainerStyle={styles.messagesContent}
        >
          {tipOfDay && messages.length <= 1 && (
            <View style={[styles.tipCard, { backgroundColor: colors.surfaceAlt }]}>
              <View style={styles.tipHeader}>
                <Ionicons name="bulb" size={20} color="#F59E0B" />
                <Text style={[styles.tipTitle, { color: colors.text }]}>Tip of the Day</Text>
              </View>
              <Text style={[styles.tipText, { color: colors.text }]}>{tipOfDay}</Text>
            </View>
          )}

          {messages.map((message) => (
            <View
              key={message.id}
              style={[
                styles.messageBubble,
                message.type === 'user' ? styles.userBubble : styles.jeevesBubble,
                { backgroundColor: message.type === 'user' ? colors.primary : colors.surfaceAlt }
              ]}
            >
              {message.type === 'jeeves' && (
                <View style={styles.jeevesIcon}>
                  <Text style={styles.jeevesSmallEmoji}>🎩</Text>
                </View>
              )}
              <Text style={[
                styles.messageText,
                { color: message.type === 'user' ? '#FFF' : colors.text }
              ]}>
                {message.content}
              </Text>
            </View>
          ))}

          {isLoading && (
            <View style={[styles.loadingBubble, { backgroundColor: colors.surfaceAlt }]}>
              <ActivityIndicator size="small" color={colors.primary} />
              <Text style={[styles.loadingText, { color: colors.textMuted }]}>Jeeves is thinking...</Text>
            </View>
          )}
        </ScrollView>

        {/* Input */}
        <View style={[styles.inputContainer, { backgroundColor: colors.surface, borderTopColor: colors.border }]}>
          <TextInput
            style={[styles.textInput, { backgroundColor: colors.surfaceAlt, color: colors.text }]}
            value={inputText}
            onChangeText={setInputText}
            placeholder="Ask Jeeves anything..."
            placeholderTextColor={colors.textMuted}
            multiline
            maxLength={2000}
            onSubmitEditing={sendMessage}
          />
          <TouchableOpacity
            style={[styles.sendBtn, { backgroundColor: inputText.trim() ? colors.primary : colors.surfaceAlt }]}
            onPress={sendMessage}
            disabled={!inputText.trim() || isLoading}
          >
            <Ionicons name="send" size={20} color={inputText.trim() ? '#FFF' : colors.textMuted} />
          </TouchableOpacity>
        </View>
      </KeyboardAvoidingView>
    </Modal>
  );
};

const styles = StyleSheet.create({
  container: { flex: 1 },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 16, paddingVertical: 12, borderBottomWidth: 1 },
  closeBtn: { width: 40, height: 40, justifyContent: 'center', alignItems: 'center' },
  headerTitle: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  jeevesAvatar: { width: 40, height: 40, borderRadius: 20, justifyContent: 'center', alignItems: 'center' },
  jeevesEmoji: { fontSize: 24 },
  title: { fontSize: 18, fontWeight: '700' },
  subtitle: { fontSize: 12 },
  settingsBtn: { width: 40, height: 40, justifyContent: 'center', alignItems: 'center' },
  settingsPanel: { padding: 16, borderBottomWidth: 1, borderBottomColor: '#333' },
  settingsHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 },
  settingsTitle: { fontSize: 16, fontWeight: '700' },
  settingsLabel: { fontSize: 13, fontWeight: '600', marginBottom: 10, marginTop: 8 },
  personalityGrid: { flexDirection: 'row', gap: 10 },
  personalityCard: { flex: 1, alignItems: 'center', padding: 12, borderRadius: 12, borderWidth: 2 },
  personalityLabel: { fontSize: 12, fontWeight: '600', marginTop: 4 },
  skillSelector: { flexDirection: 'row', gap: 8 },
  skillBtn: { flex: 1, paddingVertical: 10, borderRadius: 8, alignItems: 'center' },
  skillText: { fontSize: 12, fontWeight: '600' },
  resetBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, paddingVertical: 12, borderRadius: 10, marginTop: 16 },
  resetText: { fontSize: 14, fontWeight: '600' },
  quickActionsScroll: { maxHeight: 50, borderBottomWidth: 1, borderBottomColor: '#222' },
  quickActionsContent: { paddingHorizontal: 16, paddingVertical: 8, gap: 8, flexDirection: 'row' },
  quickAction: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 14, paddingVertical: 8, borderRadius: 20 },
  quickActionText: { fontSize: 13, fontWeight: '600' },
  messagesContainer: { flex: 1 },
  messagesContent: { padding: 16, gap: 12 },
  tipCard: { padding: 16, borderRadius: 12, marginBottom: 8 },
  tipHeader: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 8 },
  tipTitle: { fontSize: 14, fontWeight: '700' },
  tipText: { fontSize: 13, lineHeight: 20 },
  messageBubble: { maxWidth: '85%', padding: 14, borderRadius: 16 },
  userBubble: { alignSelf: 'flex-end', borderBottomRightRadius: 4 },
  jeevesBubble: { alignSelf: 'flex-start', borderBottomLeftRadius: 4, flexDirection: 'row', gap: 10 },
  jeevesIcon: { width: 28, height: 28, borderRadius: 14, backgroundColor: '#6366F120', justifyContent: 'center', alignItems: 'center' },
  jeevesSmallEmoji: { fontSize: 16 },
  messageText: { fontSize: 14, lineHeight: 22, flex: 1 },
  loadingBubble: { flexDirection: 'row', alignItems: 'center', gap: 10, alignSelf: 'flex-start', padding: 14, borderRadius: 16 },
  loadingText: { fontSize: 14 },
  inputContainer: { flexDirection: 'row', alignItems: 'flex-end', padding: 12, gap: 10, borderTopWidth: 1 },
  textInput: { flex: 1, maxHeight: 100, padding: 12, borderRadius: 20, fontSize: 15 },
  sendBtn: { width: 44, height: 44, borderRadius: 22, justifyContent: 'center', alignItems: 'center' },
});
