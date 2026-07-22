import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { API_BASE } from '../../utils/apiBase';
import {
  View, Text, StyleSheet, TouchableOpacity, ScrollView, Modal,
  ActivityIndicator, SafeAreaView, Animated, Platform,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useSettings } from '../../state/settingsStore';
import {
  ttsSpeak, ttsStop, ttsPause, ttsResume,
  ttsIsSpeaking, ttsIsPaused, pickPreferredVoice,
} from '../Academy/tts';
import { jeevesSpeak, isJeevesEnabled } from '../Academy/jeevesTts';

import { apiFetch } from '../../utils/apiController';
const API_URL = API_BASE;

interface Props {
  visible: boolean;
  onClose: () => void;
  bookId: string;
  bookTitle: string;
  chapterIdx: number;
  totalChapters: number;
  onChangeChapter?: (newIdx: number) => void;
}

/**
 * Full-screen chapter reader with audiobook-mode TTS controls.
 * - Streams lesson content from /api/academy/reading-library/book/{id}/chapter/{idx}
 * - Renders lessons as flowing prose with font-size / line-height from Academy settings
 * - Floating control bar: play / pause / stop / next-chapter / prev-chapter
 * - Highlights the currently-spoken chunk for reading-along
 */
export const ChapterReader: React.FC<Props> = ({
  visible, onClose, bookId, bookTitle, chapterIdx, totalChapters, onChangeChapter,
}) => {
  const academy = useSettings(s => s.academy);
  const setAcademy = useSettings(s => s.setAcademy);

  const [chapter, setChapter] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [tick, setTick] = useState(0);          // forces re-render for tts state
  const [progress, setProgress] = useState({ cur: 0, total: 0, text: '' });
  const pulse = useRef(new Animated.Value(0.6)).current;
  const scrollRef = useRef<ScrollView | null>(null);

  // ═══ 2026-05 — READING TIME TRACKER ════════════════════════════════
  // Heartbeat every 15 s while the reader is mounted + visible. The
  // backend (/api/reading-time/heartbeat) clips each tick to 5 min so
  // background tabs can't inflate. Total user reading time is shown in
  // the header pill and persisted server-side.
  const sessionRef = useRef<string | null>(null);
  const sessionStartRef = useRef<number>(Date.now());
  const [, setTotalMinutes] = useState<number>(0);

  // start/stop session lifecycle
  useEffect(() => {
    if (!visible) return;
    sessionStartRef.current = Date.now();
    (async () => {
      try {
        const r = await apiFetch(`${API_URL}/api/reading-time/start`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ user_id: 'default_user', book_id: bookId, chapter_id: `ch${chapterIdx}` }),
        });
        const d = await r.json();
        sessionRef.current = d?.session_id || null;
      } catch {}
      // Preload total on open
      try {
        const r2 = await apiFetch(`${API_URL}/api/reading-time/total/default_user`);
        const d2 = await r2.json();
        if (d2?.total_minutes != null) setTotalMinutes(d2.total_minutes);
      } catch {}
    })();
    return () => {
      // On unmount → flush remaining seconds and close session
      const sid = sessionRef.current;
      const elapsed = Math.round((Date.now() - sessionStartRef.current) / 1000);
      const final_seconds = Math.min(7200, Math.max(0, elapsed));
      if (sid && final_seconds > 0) {
        apiFetch(`${API_URL}/api/reading-time/stop`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ user_id: 'default_user', session_id: sid, final_seconds }),
        }).catch(() => {});
      }
    };
  }, [visible, bookId, chapterIdx]);

  // 15s heartbeats while reader is visible — pumps server total clock.
  useEffect(() => {
    if (!visible) return;
    const id = setInterval(async () => {
      try {
        const r = await apiFetch(`${API_URL}/api/reading-time/heartbeat`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            user_id: 'default_user', seconds: 15,
            book_id: bookId, chapter_id: `ch${chapterIdx}`,
            session_id: sessionRef.current,
          }),
        });
        const d = await r.json();
        if (d?.user_total_minutes != null) setTotalMinutes(d.user_total_minutes);
      } catch {}
    }, 15_000);
    return () => clearInterval(id);
  }, [visible, bookId, chapterIdx]);

  // Pulse animation while speaking (JS-driver, safe on web)
  useEffect(() => {
    if (!ttsIsSpeaking()) { pulse.setValue(0.6); return; }
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(pulse, { toValue: 1.0, duration: 700, useNativeDriver: false }),
        Animated.timing(pulse, { toValue: 0.6, duration: 700, useNativeDriver: false }),
      ])
    );
    loop.start();
    return () => loop.stop();
  }, [tick, pulse]);

  // Fetch chapter
  useEffect(() => {
    if (!visible || !bookId) return;
    let alive = true;
    (async () => {
      try {
        setLoading(true); setErr(null);
        const res = await apiFetch(
          `${API_URL}/api/academy/reading-library/book/${bookId}/chapter/${chapterIdx}`
        );
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        if (!alive) return;
        setChapter(data.chapter);
      } catch (e: any) {
        if (alive) setErr(e?.message || 'Failed to load chapter');
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => { alive = false; ttsStop(); };
  }, [visible, bookId, chapterIdx]);

  // Auto-pick male voice on first run if not set yet
  useEffect(() => {
    if (!visible) return;
    if (academy.voiceIdentifier) return;
    (async () => {
      const v = await pickPreferredVoice(academy.voiceLang || 'en-US', academy.voiceGender || 'male');
      if (v) setAcademy({ voiceIdentifier: v });
    })();
  }, [visible, academy.voiceIdentifier, academy.voiceLang, academy.voiceGender, setAcademy]);

  // Flatten chapter lessons into a single narrative string
  const narrative = useMemo(() => {
    if (!chapter) return '';
    const parts: string[] = [];
    parts.push(`${chapter.name || 'Chapter'}.`);
    if (chapter.summary) parts.push(chapter.summary);
    (chapter.lessons || []).forEach((l: any, idx: number) => {
      if (l.title) parts.push(`Lesson ${idx + 1}: ${l.title}.`);
      if (l.content) parts.push(l.content);
    });
    return parts.join('\n\n');
  }, [chapter]);

  // Audiobook mode: auto-start narration when chapter loads
  useEffect(() => {
    if (!visible || !chapter || !narrative) return;
    if (academy.audiobookMode && academy.ttsEnabled) {
      startReading();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visible, chapter, narrative, academy.audiobookMode, academy.ttsEnabled]);

  const startReading = useCallback(() => {
    if (!narrative) return;
    const onProgress = (cur: number, total: number, text: string) => {
      setProgress({ cur, total, text });
      setTick(t => t + 1);
    };
    const onComplete = () => {
      setTick(t => t + 1);
      // Auto-advance to next chapter when audiobook mode is on
      if (academy.audiobookMode && academy.autoAdvance && onChangeChapter && chapterIdx + 1 < totalChapters) {
        setTimeout(() => onChangeChapter(chapterIdx + 1), 800);
      }
    };
    if (isJeevesEnabled()) {
      // Story_time mannerism + narrative catchphrase prepend
      jeevesSpeak(narrative, {
        context: 'story_time',
        prependCatchphrase: chapterIdx === 0, // only flair at the start of the book
        readCode: academy.readCodeBlocks,
        onProgress, onComplete,
      });
    } else {
      ttsSpeak(narrative, { onProgress, onComplete });
    }
    setTick(t => t + 1);
  }, [narrative, academy.audiobookMode, academy.autoAdvance, academy.readCodeBlocks, chapterIdx, totalChapters, onChangeChapter]);

  const handlePause = useCallback(() => { ttsPause(); setTick(t => t + 1); }, []);
  const handleResume = useCallback(() => { ttsResume(); setTick(t => t + 1); }, []);
  const handleStop = useCallback(() => { ttsStop(); setProgress({ cur: 0, total: 0, text: '' }); setTick(t => t + 1); }, []);

  const close = useCallback(() => { ttsStop(); onClose(); }, [onClose]);
  const speaking = ttsIsSpeaking();
  const pausedNow = ttsIsPaused();

  const fontSize = academy.fontSize ?? 15;
  const lineHeight = Math.round(fontSize * (academy.lineHeight ?? 1.55));
  const textColor = academy.highContrast ? '#FFFFFF' : '#E2E8F0';
  const bgColor = academy.highContrast ? '#000000' : '#0F172A';

  return (
    <Modal visible={visible} animationType="slide" onRequestClose={close}>
      <SafeAreaView style={[s.container, { backgroundColor: bgColor }]}>
        {/* Header */}
        <View style={s.header}>
          <TouchableOpacity onPress={close} style={s.headerBtn} testID="chapter-close">
            <Ionicons name="close" size={24} color="#F8FAFC" />
          </TouchableOpacity>
          <View style={{ flex: 1, alignItems: 'center' }}>
            <Text style={s.headerTitle} numberOfLines={1}>{bookTitle}</Text>
            <Text style={s.headerSub}>Chapter {chapterIdx + 1} / {totalChapters}</Text>
          </View>
          <View style={s.headerPill}>
            <Ionicons
              name={speaking ? 'volume-high' : pausedNow ? 'pause' : 'volume-mute'}
              size={14}
              color={speaking ? '#10B981' : pausedNow ? '#F59E0B' : '#64748B'}
            />
            <Text style={[s.headerPillText, speaking && { color: '#10B981' }, pausedNow && { color: '#F59E0B' }]}>
              {speaking ? 'Narrating' : pausedNow ? 'Paused' : 'Silent'}
            </Text>
          </View>
        </View>

        {/* Body */}
        {loading ? (
          <View style={s.center}>
            <ActivityIndicator size="large" color="#8B5CF6" />
            <Text style={s.loadTxt}>Opening chapter…</Text>
          </View>
        ) : err ? (
          <View style={s.center}>
            <Ionicons name="alert-circle" size={36} color="#EF4444" />
            <Text style={s.errTxt}>{err}</Text>
          </View>
        ) : (
          <ScrollView
            ref={scrollRef}
            style={{ flex: 1 }}
            contentContainerStyle={s.scrollBody}
            showsVerticalScrollIndicator={false}
          >
            <Text style={[s.chapterTitle, { color: textColor }]}>{chapter?.name || 'Chapter'}</Text>
            {chapter?.summary && (
              <Text style={[s.chapterSum, { color: academy.highContrast ? '#CBD5E1' : '#94A3B8', fontSize: fontSize - 1, lineHeight: lineHeight - 4 }]}>
                {chapter.summary}
              </Text>
            )}
            {(chapter?.lessons || []).map((lesson: any, idx: number) => (
              <View key={lesson.id || idx} style={s.lessonBlock}>
                <View style={s.lessonHeader}>
                  <View style={s.lessonNum}>
                    <Text style={s.lessonNumText}>{idx + 1}</Text>
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={[s.lessonTitle, { color: textColor }]}>{lesson.title}</Text>
                    <Text style={s.lessonMeta}>{lesson.type} • {lesson.estimated_minutes ?? 10} min</Text>
                  </View>
                </View>
                <Text style={[s.lessonBody, { color: textColor, fontSize, lineHeight }]}>
                  {lesson.content || '(No content yet.)'}
                </Text>
              </View>
            ))}

            <View style={{ height: 140 }} />
          </ScrollView>
        )}

        {/* Now-reading chip */}
        {speaking && progress.total > 0 && (
          <View style={s.nowReading}>
            <Animated.View style={[s.nowDot, { opacity: pulse }]} />
            <Text style={s.nowText} numberOfLines={2}>{progress.text}</Text>
            <Text style={s.nowProgress}>{progress.cur}/{progress.total}</Text>
          </View>
        )}

        {/* Floating control bar */}
        <View style={s.controlBar}>
          <TouchableOpacity
            onPress={() => onChangeChapter?.(Math.max(0, chapterIdx - 1))}
            disabled={chapterIdx === 0}
            style={[s.ctrlSmall, chapterIdx === 0 && { opacity: 0.35 }]}
          >
            <Ionicons name="play-skip-back" size={20} color="#F8FAFC" />
          </TouchableOpacity>

          {!speaking && !pausedNow ? (
            <TouchableOpacity onPress={startReading} style={s.ctrlPlay} testID="tts-play">
              <Ionicons name="play" size={28} color="#0F172A" />
              <Text style={s.ctrlPlayText}>Read</Text>
            </TouchableOpacity>
          ) : speaking ? (
            <TouchableOpacity onPress={handlePause} style={s.ctrlPlay} testID="tts-pause">
              <Ionicons name="pause" size={28} color="#0F172A" />
              <Text style={s.ctrlPlayText}>Pause</Text>
            </TouchableOpacity>
          ) : (
            <TouchableOpacity onPress={handleResume} style={s.ctrlPlay} testID="tts-resume">
              <Ionicons name="play" size={28} color="#0F172A" />
              <Text style={s.ctrlPlayText}>Resume</Text>
            </TouchableOpacity>
          )}

          {(speaking || pausedNow) && (
            <TouchableOpacity onPress={handleStop} style={s.ctrlSmall} testID="tts-stop">
              <Ionicons name="stop" size={20} color="#F8FAFC" />
            </TouchableOpacity>
          )}

          <TouchableOpacity
            onPress={() => onChangeChapter?.(Math.min(totalChapters - 1, chapterIdx + 1))}
            disabled={chapterIdx >= totalChapters - 1}
            style={[s.ctrlSmall, chapterIdx >= totalChapters - 1 && { opacity: 0.35 }]}
          >
            <Ionicons name="play-skip-forward" size={20} color="#F8FAFC" />
          </TouchableOpacity>
        </View>
      </SafeAreaView>
    </Modal>
  );
};

const s = StyleSheet.create({
  container: { flex: 1 },
  header: {
    flexDirection: 'row', alignItems: 'center',
    paddingHorizontal: 12, paddingVertical: 10,
    backgroundColor: '#1E293B', borderBottomWidth: 1, borderBottomColor: '#334155',
  },
  headerBtn: { width: 44, height: 44, justifyContent: 'center', alignItems: 'center' },
  headerTitle: { color: '#F8FAFC', fontSize: 15, fontWeight: '700' },
  headerSub: { color: '#94A3B8', fontSize: 11, marginTop: 2 },
  headerPill: {
    flexDirection: 'row', alignItems: 'center', gap: 4,
    backgroundColor: '#334155', paddingHorizontal: 10, paddingVertical: 6, borderRadius: 12,
  },
  headerPillText: { color: '#94A3B8', fontSize: 11, fontWeight: '600' },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center', padding: 20 },
  loadTxt: { color: '#94A3B8', marginTop: 12 },
  errTxt: { color: '#EF4444', marginTop: 12, textAlign: 'center' },
  scrollBody: { padding: 20, paddingBottom: 100 },
  chapterTitle: { fontSize: 26, fontWeight: '800', marginBottom: 8 },
  chapterSum: { marginBottom: 24 },
  lessonBlock: { marginTop: 24 },
  lessonHeader: { flexDirection: 'row', alignItems: 'center', marginBottom: 10 },
  lessonNum: {
    width: 32, height: 32, borderRadius: 16, backgroundColor: '#8B5CF6',
    justifyContent: 'center', alignItems: 'center', marginRight: 10,
  },
  lessonNumText: { color: '#FFF', fontSize: 13, fontWeight: '800' },
  lessonTitle: { fontSize: 17, fontWeight: '700' },
  lessonMeta: { fontSize: 11, color: '#64748B', textTransform: 'uppercase', marginTop: 2 },
  lessonBody: { marginTop: 4 },
  nowReading: {
    position: 'absolute', left: 12, right: 12, bottom: 92,
    flexDirection: 'row', alignItems: 'center', gap: 10,
    backgroundColor: 'rgba(15, 23, 42, 0.94)', borderColor: '#8B5CF6', borderWidth: 1,
    padding: 10, borderRadius: 12,
  },
  nowDot: { width: 10, height: 10, borderRadius: 5, backgroundColor: '#10B981' },
  nowText: { flex: 1, color: '#CBD5E1', fontSize: 12, fontStyle: 'italic' },
  nowProgress: { color: '#8B5CF6', fontSize: 11, fontWeight: '800' },
  controlBar: {
    position: 'absolute', left: 12, right: 12, bottom: 16,
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    backgroundColor: 'rgba(30, 41, 59, 0.96)', paddingHorizontal: 16, paddingVertical: 12,
    borderRadius: 18, borderWidth: 1, borderColor: '#334155',
    ...(Platform.OS === 'web' ? { boxShadow: '0 4px 16px rgba(0,0,0,0.4)' as any } : {}),
  },
  ctrlSmall: {
    width: 44, height: 44, borderRadius: 22, backgroundColor: '#334155',
    justifyContent: 'center', alignItems: 'center',
  },
  ctrlPlay: {
    flexDirection: 'row', alignItems: 'center', gap: 6,
    backgroundColor: '#10B981', paddingHorizontal: 22, paddingVertical: 12, borderRadius: 22,
  },
  ctrlPlayText: { color: '#0F172A', fontSize: 14, fontWeight: '800' },
});

export default ChapterReader;
