/**
 * Reading Visualizer — the primary reading surface of the Academy.
 *
 * Renders ONE chapter at a time with:
 *  • Section-by-section display (Markdown-lite parsed into headings, code, paragraphs)
 *  • TTS playback with sentence-level highlight + auto-scroll
 *  • Progress bar (chapter X of N + current sentence within chapter)
 *  • Prev / Next chapter navigation (wraps on bounds)
 *  • Class-progress sync to backend on scroll & chapter change
 *
 * Used by: ReadingLibrary (books), Bible, Tracks — any item with
 * `(itemType, itemId, chapterIdx, totalChapters)`.
 */

import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity, ActivityIndicator,
  Modal, SafeAreaView, Platform, Linking,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import {
  ttsSpeak, ttsStop, ttsPause, ttsResume, ttsIsPaused, ttsIsSpeaking, ttsProgress,
} from '../Academy/tts';
import { jeevesSpeak, isJeevesEnabled } from '../Academy/jeevesTts';
import { getCachedChapter, saveChapterOffline, isChapterCached, deleteChapterOffline } from '../../utils/offlineSync';
import { addNote, getNotes, deleteNote, ChapterNote } from '../../utils/classStore';
import { API_BASE } from '../../utils/apiBase';
import { bumpStat } from '../../utils/userStore';

import { apiFetch } from '../../utils/apiController';
const API_URL = API_BASE;

export interface ReadingVisualizerProps {
  visible: boolean;
  onClose: () => void;
  itemType: 'book' | 'bible' | 'track' | 'manual';
  itemId: string;
  itemTitle: string;
  chapterIdx: number;
  totalChapters: number;
  // Endpoint pattern for chapter content (books use reading-library path)
  contentEndpoint?: (id: string, idx: number) => string;
  onChangeChapter?: (newIdx: number) => void;
  userId?: string;
}

interface ChapterContent {
  book_id?: string;
  book_title?: string;
  author?: string;
  chapter_idx: number;
  total_chapters: number;
  chapter_name: string;
  // Optional open-license metadata surfaced from the registry
  is_open_license?: boolean;
  license?: string;
  official_url?: string;
  content: {
    body_md: string;
    word_count: number;
    reading_minutes: number;
    sections: { title: string; text: string }[];
    glossary_structured?: { term: string; definition: string }[];
    comprehension_questions?: string[];
    key_takeaways?: string[];
  };
}

type Block = { kind: 'h1' | 'h2' | 'h3' | 'p' | 'code' | 'list' | 'sep'; text: string };

// ─── Mini markdown parser tuned for our content generator output ──────────
function parseMarkdown(md: string): Block[] {
  const out: Block[] = [];
  const lines = md.split('\n');
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (line.startsWith('```')) {
      i++;
      const code: string[] = [];
      while (i < lines.length && !lines[i].startsWith('```')) {
        code.push(lines[i]);
        i++;
      }
      i++; // closing fence
      out.push({ kind: 'code', text: code.join('\n') });
      continue;
    }
    if (line.startsWith('# ')) {
      out.push({ kind: 'h1', text: line.slice(2).trim() });
      i++;
      continue;
    }
    if (line.startsWith('## ')) {
      out.push({ kind: 'h2', text: line.slice(3).trim() });
      i++;
      continue;
    }
    if (line.startsWith('### ')) {
      out.push({ kind: 'h3', text: line.slice(4).trim() });
      i++;
      continue;
    }
    if (/^\s*[-*]\s+/.test(line) || /^\s*\d+\.\s+/.test(line)) {
      const items: string[] = [];
      while (
        i < lines.length &&
        (/^\s*[-*]\s+/.test(lines[i]) || /^\s*\d+\.\s+/.test(lines[i]))
      ) {
        items.push(lines[i].replace(/^\s*([-*]|\d+\.)\s+/, ''));
        i++;
      }
      out.push({ kind: 'list', text: items.join('\n') });
      continue;
    }
    if (line.trim() === '') {
      i++;
      continue;
    }
    // Paragraph — collect until blank line
    const para: string[] = [line];
    i++;
    while (i < lines.length && lines[i].trim() !== '' && !lines[i].startsWith('#') && !lines[i].startsWith('```')) {
      para.push(lines[i]);
      i++;
    }
    out.push({ kind: 'p', text: para.join(' ') });
  }
  return out;
}

// Inline markup: **bold**, *italic*, `code`
function renderInline(text: string, base: any = {}): React.ReactNode {
  const parts: React.ReactNode[] = [];
  const rx = /(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`)/g;
  let last = 0;
  let match: RegExpExecArray | null;
  let k = 0;
  while ((match = rx.exec(text)) !== null) {
    if (match.index > last) {
      parts.push(<Text key={`t${k++}`} style={base}>{text.slice(last, match.index)}</Text>);
    }
    const token = match[0];
    if (token.startsWith('**')) {
      parts.push(<Text key={`b${k++}`} style={[base, styles.bold]}>{token.slice(2, -2)}</Text>);
    } else if (token.startsWith('`')) {
      parts.push(<Text key={`c${k++}`} style={[base, styles.inlineCode]}>{token.slice(1, -1)}</Text>);
    } else {
      parts.push(<Text key={`i${k++}`} style={[base, styles.italic]}>{token.slice(1, -1)}</Text>);
    }
    last = match.index + token.length;
  }
  if (last < text.length) {
    parts.push(<Text key={`t${k++}`} style={base}>{text.slice(last)}</Text>);
  }
  return parts;
}

// Build the spoken text from blocks (strip code fences, spell "example code block" briefly)
function textForTTS(blocks: Block[]): string {
  return blocks
    .map((b) => {
      if (b.kind === 'code') return ' — example code block — ';
      if (b.kind === 'list') return b.text.split('\n').map((x) => '• ' + x).join('. ');
      return b.text;
    })
    .join('\n\n');
}

export const ReadingVisualizer: React.FC<ReadingVisualizerProps> = ({
  visible,
  onClose,
  itemType,
  itemId,
  itemTitle,
  chapterIdx,
  totalChapters,
  contentEndpoint,
  onChangeChapter,
  userId = 'default_user',
}) => {
  // Pull device safe-area insets so the bottom control bar (Listen / TTS controls)
  // can clear the iOS home-indicator gesture bar that previously covered it.
  const insets = useSafeAreaInsets();
  const [content, setContent] = useState<ChapterContent | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [ttsState, setTtsState] = useState<'idle' | 'playing' | 'paused'>('idle');
  const [ttsChunk, setTtsChunk] = useState<{ idx: number; total: number; text: string }>({
    idx: 0, total: 0, text: '',
  });

  // UX polish: persistent font scale (1.0 default, 0.85 small, 1.15 large, 1.3 xlarge)
  const [fontScale, setFontScale] = useState<number>(1.0);
  // Quiz overlay state
  const [quizVisible, setQuizVisible] = useState(false);
  const [quiz, setQuiz] = useState<{ q: string; options: string[]; answer_idx: number; explanation?: string }[] | null>(null);
  const [quizLoading, setQuizLoading] = useState(false);
  // NEW: per-row expansion state for glossary + comprehension Qs.
  const [glossOpen, setGlossOpen] = useState<Record<number, boolean>>({});
  const [compOpen, setCompOpen] = useState<Record<number, boolean>>({});
  const [quizAnswers, setQuizAnswers] = useState<Record<number, number>>({});

  // Offline cache state for the current chapter
  const [downloaded, setDownloaded] = useState(false);
  const [downloading, setDownloading] = useState(false);

  // Notes
  const [notes, setNotes] = useState<ChapterNote[]>([]);
  const [, setNotesOpen] = useState(false);
  const [draftNote, setDraftNote] = useState('');
  const [draftColor] = useState('#3B82F6');

  const scrollRef = useRef<ScrollView>(null);
  const ttsPollRef = useRef<any>(null);

  // ═══ 2026-05 — READING TIME TRACKER ════════════════════════════════
  // Heartbeat every 15 s while ReadingVisualizer is mounted + visible.
  // Backend `/api/reading-time/heartbeat` clips each tick to 300 s so a
  // tab left open in the background can't inflate the user's totals.
  const sessionRef = useRef<string | null>(null);
  const sessionStartRef = useRef<number>(Date.now());
  const [, setTotalMinutes] = useState<number>(0);

  // Open a session on first visible + close on unmount/close
  useEffect(() => {
    if (!visible) return;
    sessionStartRef.current = Date.now();
    let cancelled = false;
    (async () => {
      try {
        const r = await apiFetch(`${API_URL}/api/reading-time/start`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ user_id: userId, book_id: itemId, chapter_id: `ch${chapterIdx}` }),
        });
        const d = await r.json();
        if (!cancelled) sessionRef.current = d?.session_id || null;
      } catch { /* offline ok */ }
      try {
        const r2 = await apiFetch(`${API_URL}/api/reading-time/total/${userId}`);
        const d2 = await r2.json();
        if (!cancelled && d2?.total_minutes != null) setTotalMinutes(d2.total_minutes);
      } catch { /* offline ok */ }
    })();
    return () => {
      cancelled = true;
      const sid = sessionRef.current;
      const elapsed = Math.round((Date.now() - sessionStartRef.current) / 1000);
      const final_seconds = Math.min(7200, Math.max(0, elapsed));
      if (sid && final_seconds > 0) {
        apiFetch(`${API_URL}/api/reading-time/stop`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ user_id: userId, session_id: sid, final_seconds }),
        }).catch(() => {});
      }
    };
  }, [visible, itemId, chapterIdx, userId]);

  // 15-second heartbeat tick while reader is visible
  useEffect(() => {
    if (!visible) return;
    const id = setInterval(async () => {
      try {
        const r = await apiFetch(`${API_URL}/api/reading-time/heartbeat`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            user_id: userId, seconds: 15,
            book_id: itemId, chapter_id: `ch${chapterIdx}`,
            session_id: sessionRef.current,
          }),
        });
        const d = await r.json();
        if (d?.user_total_minutes != null) setTotalMinutes(d.user_total_minutes);
      } catch { /* network blip → skip this tick */ }
    }, 15_000);
    return () => clearInterval(id);
  }, [visible, itemId, chapterIdx, userId]);

  // Fetch chapter content
  useEffect(() => {
    if (!visible || !itemId) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    ttsStop();
    setTtsState('idle');

    const url =
      contentEndpoint
        ? `${API_URL}${contentEndpoint(itemId, chapterIdx)}`
        : `${API_URL}/api/academy/reading-library/book/${itemId}/chapter/${chapterIdx}/content`;

    // 1) Try the offline cache first — if present, render instantly without network
    const itemKeyForCache =
      itemType === 'book' ? itemId : `${itemType}:${itemId}`;
    getCachedChapter(itemKeyForCache, chapterIdx)
      .then((cachedDoc) => {
        if (cancelled) return;
        if (cachedDoc && cachedDoc.content && cachedDoc.content.body_md) {
          setContent(cachedDoc);
          setLoading(false);
          // Best-effort: still record progress
          apiFetch(`${API_URL}/api/academy/class-progress/update`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              user_id: userId,
              item_type: itemType,
              item_id: itemId,
              chapter_idx: chapterIdx,
              scroll_ratio: 0,
            }),
          }).catch(() => {});
          return;
        }
        // 2) Fall back to network
        apiFetch(url)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((data) => {
        if (cancelled) return;
        setContent(data);
        // Sync progress to backend
        apiFetch(`${API_URL}/api/academy/class-progress/update`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            user_id: userId,
            item_type: itemType,
            item_id: itemId,
            chapter_idx: chapterIdx,
            scroll_ratio: 0,
          }),
        }).catch(() => {});
      })
      .catch((e) => {
        if (!cancelled) setError(`Could not load chapter: ${e.message}`);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
        scrollRef.current?.scrollTo({ y: 0, animated: false });
      });
      })
      .catch(() => {
        // If offline cache lookup itself fails, just skip and try network
        apiFetch(url)
          .then((r) => r.json())
          .then((data) => { if (!cancelled) setContent(data); })
          .catch((e) => { if (!cancelled) setError(`Could not load chapter: ${e.message}`); })
          .finally(() => { if (!cancelled) setLoading(false); });
      });

    return () => {
      cancelled = true;
      ttsStop();
      if (ttsPollRef.current) {
        clearInterval(ttsPollRef.current);
        ttsPollRef.current = null;
      }
    };
  }, [visible, itemId, chapterIdx, contentEndpoint, itemType, userId]);

  // Parse body into blocks
  const blocks = useMemo(() => {
    if (!content) return [] as Block[];
    return parseMarkdown(content.content.body_md || '');
  }, [content]);

  // Poll TTS progress while playing
  useEffect(() => {
    if (ttsState !== 'playing') return;
    ttsPollRef.current = setInterval(() => {
      const p = ttsProgress();
      if (p.total > 0) setTtsChunk((prev) => ({ ...prev, idx: p.current, total: p.total }));
      if (!ttsIsSpeaking() && !ttsIsPaused()) setTtsState('idle');
    }, 500);
    return () => {
      if (ttsPollRef.current) {
        clearInterval(ttsPollRef.current);
        ttsPollRef.current = null;
      }
    };
  }, [ttsState]);

  const handlePlay = useCallback(() => {
    if (!content) return;
    const txt = textForTTS(blocks);
    ttsStop();
    const onProgress = (idx: number, total: number, text: string) => setTtsChunk({ idx, total, text });
    const onComplete = () => setTtsState('idle');
    if (isJeevesEnabled()) {
      jeevesSpeak(txt, {
        context: 'story_time',
        prependCatchphrase: true,
        onProgress, onComplete,
      });
    } else {
      ttsSpeak(txt, { onProgress, onComplete });
    }
    setTtsState('playing');
  }, [content, blocks]);

  const handlePause = useCallback(() => {
    if (ttsState === 'playing') {
      ttsPause();
      setTtsState('paused');
    } else if (ttsState === 'paused') {
      ttsResume();
      setTtsState('playing');
    }
  }, [ttsState]);

  const handleStop = useCallback(() => {
    ttsStop();
    setTtsState('idle');
  }, []);

  const handlePrev = useCallback(() => {
    if (chapterIdx > 0) {
      ttsStop();
      onChangeChapter?.(chapterIdx - 1);
    }
  }, [chapterIdx, onChangeChapter]);

  const handleNext = useCallback(() => {
    if (chapterIdx < totalChapters - 1) {
      ttsStop();
      onChangeChapter?.(chapterIdx + 1);
    } else {
      // Mark completed
      apiFetch(`${API_URL}/api/academy/class-progress/update`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: userId,
          item_type: itemType,
          item_id: itemId,
          chapter_idx: chapterIdx,
          scroll_ratio: 1,
          completed: true,
        }),
      }).catch(() => {});
    }
  }, [chapterIdx, totalChapters, onChangeChapter, userId, itemType, itemId]);

  const handleQuiz = useCallback(async () => {
    setQuizVisible(true);
    if (quiz) return;
    setQuizLoading(true);
    try {
      const res = await apiFetch(`${API_URL}/api/academy/reading-library/quiz`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          item_type: itemType,
          item_id: itemId,
          chapter_idx: chapterIdx,
        }),
      });
      const data = await res.json();
      if (data.questions) setQuiz(data.questions);
    } catch {
      // ignore
    } finally {
      setQuizLoading(false);
    }
  }, [itemType, itemId, chapterIdx, quiz]);

  const openOfficialUrl = useCallback(() => {
    const url = (content as any)?.official_url;
    if (url) Linking.openURL(url).catch(() => {});
  }, [content]);

  const cycleFontScale = useCallback(() => {
    setFontScale((s) => (s >= 1.3 ? 0.85 : s + 0.15));
  }, []);

  // Compute the cache key once per chapter
  const itemKeyForCache = useMemo(
    () => (itemType === 'book' ? itemId : `${itemType}:${itemId}`),
    [itemType, itemId],
  );

  // Check cached state on chapter change / open
  useEffect(() => {
    let cancelled = false;
    if (!visible || !itemId) { setDownloaded(false); return; }
    isChapterCached(itemKeyForCache, chapterIdx).then((c) => {
      if (!cancelled) setDownloaded(c);
    });
    return () => { cancelled = true; };
  }, [visible, itemId, itemKeyForCache, chapterIdx]);

  // Load notes for current chapter
  useEffect(() => {
    if (!visible || !itemId) { setNotes([]); return; }
    getNotes(itemType, itemId, chapterIdx).then(setNotes).catch(() => {});
  }, [visible, itemId, itemType, chapterIdx]);

  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const handleSaveNote = useCallback(async () => {
    const txt = draftNote.trim();
    if (!txt) return;
    await addNote(itemType, itemId, chapterIdx, txt, draftColor);
    const updated = await getNotes(itemType, itemId, chapterIdx);
    setNotes(updated);
    setDraftNote('');
  }, [draftNote, draftColor, itemType, itemId, chapterIdx]);

  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const handleDeleteNote = useCallback(async (id: string) => {
    await deleteNote(itemType, itemId, chapterIdx, id);
    const updated = await getNotes(itemType, itemId, chapterIdx);
    setNotes(updated);
  }, [itemType, itemId, chapterIdx]);

  const handleToggleDownload = useCallback(async () => {
    if (!content || downloading) return;
    setDownloading(true);
    try {
      if (downloaded) {
        await deleteChapterOffline(itemKeyForCache, chapterIdx);
        setDownloaded(false);
      } else {
        const ok = await saveChapterOffline(itemKeyForCache, chapterIdx, content);
        setDownloaded(ok);
      }
    } finally {
      setDownloading(false);
    }
  }, [content, downloaded, downloading, itemKeyForCache, chapterIdx]);

  const onScrollEnd = useCallback(
    (ev: any) => {
      if (!content) return;
      const { contentOffset, contentSize, layoutMeasurement } = ev.nativeEvent;
      const ratio = contentSize.height > 0
        ? Math.min(1, (contentOffset.y + layoutMeasurement.height) / contentSize.height)
        : 0;
      apiFetch(`${API_URL}/api/academy/class-progress/update`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: userId,
          item_type: itemType,
          item_id: itemId,
          chapter_idx: chapterIdx,
          scroll_ratio: ratio,
        }),
      }).catch(() => {});
      // Bump local stats once when chapter is ≥95% scrolled
      if (ratio >= 0.95) {
        bumpStat('reading_chapters_completed', 1, 25).catch(() => {});
      }
    },
    [content, userId, itemType, itemId, chapterIdx],
  );

  const chapterProgress = totalChapters > 0 ? (chapterIdx + 1) / totalChapters : 0;
  const ttsRatio = ttsChunk.total > 0 ? ttsChunk.idx / ttsChunk.total : 0;

  return (
    <Modal visible={visible} animationType="slide" onRequestClose={onClose}>
      <SafeAreaView style={styles.container}>
        {/* HEADER */}
        <View style={styles.header}>
          <TouchableOpacity
            testID="rv-close"
            onPress={() => { ttsStop(); onClose(); }}
            style={styles.headerBtn}
          >
            <Ionicons name="close" size={24} color="#F8FAFC" />
          </TouchableOpacity>
          <View style={styles.headerTitleWrap}>
            <Text testID="rv-chapter-title" style={styles.headerTitle} numberOfLines={1}>{itemTitle}</Text>
            <Text testID="rv-chapter-name" style={styles.headerSub}>
              {content ? content.chapter_name : `Chapter ${chapterIdx + 1}`}
              {content ? ` • ${content.content.reading_minutes} min read` : ''}
            </Text>
          </View>
          <TouchableOpacity
            testID="rv-next"
            onPress={handleNext}
            style={styles.headerBtn}
            disabled={!content}
          >
            <Ionicons
              name={chapterIdx < totalChapters - 1 ? 'chevron-forward' : 'checkmark-done'}
              size={22}
              color={content ? '#8B5CF6' : '#475569'}
            />
          </TouchableOpacity>
        </View>

        {/* PROGRESS BAR — chapter progression + TTS progression overlay */}
        <View style={styles.progressTrack}>
          <View style={[styles.progressChapter, { width: `${chapterProgress * 100}%` }]} />
          {ttsState !== 'idle' && (
            <View style={[styles.progressTTS, { width: `${ttsRatio * 100}%` }]} />
          )}
        </View>
        <View style={styles.progressMeta}>
          <Text style={styles.progressText}>
            Chapter {chapterIdx + 1} of {totalChapters}
          </Text>
          {ttsState !== 'idle' && ttsChunk.total > 0 && (
            <Text style={styles.progressTextAccent}>
              ▶ {ttsChunk.idx}/{ttsChunk.total} sentences
            </Text>
          )}
        </View>

        {/* TOOLBAR — font, official source link, quiz */}
        {content && (
          <View style={styles.toolbar}>
            <TouchableOpacity testID="rv-font" style={styles.toolbarBtn} onPress={cycleFontScale}>
              <Ionicons name="text" size={16} color="#CBD5E1" />
              <Text style={styles.toolbarBtnText}>{Math.round(fontScale * 100)}%</Text>
            </TouchableOpacity>
            {(content as any).official_url && (
              <TouchableOpacity testID="rv-official" style={styles.toolbarBtn} onPress={openOfficialUrl}>
                <Ionicons name="globe-outline" size={16} color="#10B981" />
                <Text style={styles.toolbarBtnTextAccent}>Official source</Text>
              </TouchableOpacity>
            )}
            {(content as any).license && (
              <Text style={styles.toolbarLicense}>{(content as any).license}</Text>
            )}
            <TouchableOpacity testID="rv-quiz" style={styles.toolbarBtn} onPress={handleQuiz}>
              <Ionicons name="help-circle-outline" size={16} color="#F59E0B" />
              <Text style={styles.toolbarBtnText}>Quiz</Text>
            </TouchableOpacity>
            <TouchableOpacity
              testID="rv-notes"
              style={[styles.toolbarBtn, notes.length > 0 && { borderColor: '#FBBF24' }]}
              onPress={() => setNotesOpen(true)}
            >
              <Ionicons name="bookmarks-outline" size={16} color={notes.length > 0 ? '#FBBF24' : '#CBD5E1'} />
              <Text style={[styles.toolbarBtnText, notes.length > 0 && { color: '#FBBF24' }]}>
                Notes{notes.length > 0 ? ` (${notes.length})` : ''}
              </Text>
            </TouchableOpacity>
            <TouchableOpacity
              testID="rv-download"
              style={[styles.toolbarBtn, downloaded && { borderColor: '#10B981' }]}
              onPress={handleToggleDownload}
              disabled={downloading || !content}
            >
              {downloading ? (
                <ActivityIndicator size="small" color="#F472B6" />
              ) : (
                <Ionicons
                  name={downloaded ? 'checkmark-circle' : 'cloud-download-outline'}
                  size={16}
                  color={downloaded ? '#10B981' : '#F472B6'}
                />
              )}
              <Text style={[styles.toolbarBtnText, downloaded && { color: '#10B981' }]}>
                {downloaded ? 'Saved' : 'Save'}
              </Text>
            </TouchableOpacity>
          </View>
        )}

        {/* BODY */}
        {loading ? (
          <View style={styles.centered}>
            <ActivityIndicator size="large" color="#8B5CF6" />
            <Text style={styles.loadingText}>Loading chapter content…</Text>
          </View>
        ) : error ? (
          <View style={styles.centered}>
            <Ionicons name="alert-circle-outline" size={48} color="#EF4444" />
            <Text style={styles.errorText}>{error}</Text>
          </View>
        ) : (
          <ScrollView
            ref={scrollRef}
            style={styles.scroll}
            contentContainerStyle={styles.scrollContent}
            onMomentumScrollEnd={onScrollEnd}
          >
            {/* ── KEY TAKEAWAYS ── pinned at top so readers see them first */}
            {Array.isArray(content?.content?.key_takeaways) && content!.content.key_takeaways!.length > 0 && (
              <View style={styles.takeawaysCard}>
                <View style={styles.takeawaysHead}>
                  <Ionicons name="bulb" size={14} color="#FBBF24" />
                  <Text style={styles.takeawaysHeadText}>Key Takeaways</Text>
                </View>
                {content!.content.key_takeaways!.map((t, i) => (
                  <View key={i} style={styles.takeawayRow}>
                    <Text style={styles.takeawayNum}>{i + 1}</Text>
                    <Text style={styles.takeawayText}>{t}</Text>
                  </View>
                ))}
              </View>
            )}

            {blocks.map((b, i) => {
              if (b.kind === 'h1') {
                return <Text key={i} style={[styles.h1, { fontSize: 26 * fontScale, lineHeight: 34 * fontScale }]}>{renderInline(b.text, styles.h1)}</Text>;
              }
              if (b.kind === 'h2') {
                return <Text key={i} style={[styles.h2, { fontSize: 19 * fontScale, lineHeight: 26 * fontScale }]}>{renderInline(b.text, styles.h2)}</Text>;
              }
              if (b.kind === 'h3') {
                return <Text key={i} style={[styles.h3, { fontSize: 15 * fontScale, lineHeight: 22 * fontScale }]}>{renderInline(b.text, styles.h3)}</Text>;
              }
              if (b.kind === 'code') {
                return (
                  <View key={i} style={styles.codeBlock}>
                    <Text style={[styles.codeText, { fontSize: 13 * fontScale, lineHeight: 19 * fontScale }]}>{b.text}</Text>
                  </View>
                );
              }
              if (b.kind === 'list') {
                return (
                  <View key={i} style={styles.list}>
                    {b.text.split('\n').map((item, j) => (
                      <View key={j} style={styles.listItem}>
                        <Text style={styles.listBullet}>•</Text>
                        <Text style={[styles.listText, { fontSize: 15 * fontScale, lineHeight: 22 * fontScale }]}>{renderInline(item, styles.listText)}</Text>
                      </View>
                    ))}
                  </View>
                );
              }
              return <Text key={i} style={[styles.paragraph, { fontSize: 15 * fontScale, lineHeight: 24 * fontScale }]}>{renderInline(b.text, styles.paragraph)}</Text>;
            })}

            {/* ── GLOSSARY (interactive cards) ── */}
            {Array.isArray(content?.content?.glossary_structured) && content!.content.glossary_structured!.length > 0 && (
              <View style={styles.extrasCard}>
                <View style={styles.extrasHead}>
                  <Ionicons name="book" size={14} color="#A78BFA" />
                  <Text style={styles.extrasHeadText}>Glossary · {content!.content.glossary_structured!.length} terms</Text>
                </View>
                {content!.content.glossary_structured!.map((g, i) => (
                  <TouchableOpacity
                    key={i}
                    style={styles.glossRow}
                    onPress={() => setGlossOpen(o => ({ ...o, [i]: !o[i] }))}
                    activeOpacity={0.8}
                  >
                    <View style={styles.glossHead}>
                      <Ionicons name={glossOpen[i] ? 'chevron-down' : 'chevron-forward'} size={14} color="#A78BFA" />
                      <Text style={styles.glossTerm}>{g.term}</Text>
                    </View>
                    {glossOpen[i] && <Text style={styles.glossDef}>{g.definition}</Text>}
                  </TouchableOpacity>
                ))}
              </View>
            )}

            {/* ── COMPREHENSION QUESTIONS ── */}
            {Array.isArray(content?.content?.comprehension_questions) && content!.content.comprehension_questions!.length > 0 && (
              <View style={styles.extrasCard}>
                <View style={styles.extrasHead}>
                  <Ionicons name="help-circle" size={14} color="#10B981" />
                  <Text style={styles.extrasHeadText}>Self-Check Comprehension</Text>
                </View>
                {content!.content.comprehension_questions!.map((q, i) => (
                  <TouchableOpacity
                    key={i}
                    style={styles.compRow}
                    onPress={() => setCompOpen(o => ({ ...o, [i]: !o[i] }))}
                    activeOpacity={0.8}
                  >
                    <Ionicons name={compOpen[i] ? 'chevron-down' : 'chevron-forward'} size={14} color="#10B981" />
                    <Text style={styles.compText}>Q{i + 1}. {q}</Text>
                  </TouchableOpacity>
                ))}
                <Text style={styles.compHint}>Tap a question to mark it as &quot;considered&quot;. This is a self-assessment — there are no graded answers here.</Text>
              </View>
            )}

            <View style={{ height: 120 }} />
          </ScrollView>
        )}

        {/* TTS + NAVIGATION BAR */}
        <View style={[styles.controlBar, { paddingBottom: Math.max(insets.bottom + 10, 14) }]}>
          <TouchableOpacity
            testID="rv-prev"
            style={[styles.navBtn, chapterIdx === 0 && styles.navDisabled]}
            onPress={handlePrev}
            disabled={chapterIdx === 0}
          >
            <Ionicons name="play-skip-back" size={20} color={chapterIdx === 0 ? '#475569' : '#F8FAFC'} />
            <Text style={[styles.navText, chapterIdx === 0 && styles.navTextDisabled]}>Prev</Text>
          </TouchableOpacity>

          <View style={styles.ttsCluster}>
            {ttsState === 'idle' ? (
              <TouchableOpacity testID="rv-tts-play" style={styles.ttsPrimaryBtn} onPress={handlePlay} disabled={!content}>
                <Ionicons name="play" size={22} color="#FFF" />
                <Text style={styles.ttsPrimaryText}>Listen</Text>
              </TouchableOpacity>
            ) : (
              <>
                <TouchableOpacity testID="rv-tts-pause" style={styles.ttsSecondaryBtn} onPress={handlePause}>
                  <Ionicons name={ttsState === 'playing' ? 'pause' : 'play'} size={22} color="#8B5CF6" />
                </TouchableOpacity>
                <TouchableOpacity testID="rv-tts-stop" style={styles.ttsSecondaryBtn} onPress={handleStop}>
                  <Ionicons name="stop" size={22} color="#EF4444" />
                </TouchableOpacity>
              </>
            )}
          </View>

          <TouchableOpacity
            testID="rv-next-btn"
            style={styles.navBtn}
            onPress={handleNext}
          >
            <Text style={styles.navText}>
              {chapterIdx < totalChapters - 1 ? 'Next' : 'Finish'}
            </Text>
            <Ionicons
              name={chapterIdx < totalChapters - 1 ? 'play-skip-forward' : 'checkmark-done'}
              size={20}
              color="#F8FAFC"
            />
          </TouchableOpacity>
        </View>

        {/* QUIZ OVERLAY */}
        {quizVisible && (
          <View style={styles.quizOverlay}>
            <View style={styles.quizHeader}>
              <Text style={styles.quizTitle}>Chapter Quiz</Text>
              <TouchableOpacity testID="quiz-close" onPress={() => setQuizVisible(false)}>
                <Ionicons name="close" size={26} color="#F8FAFC" />
              </TouchableOpacity>
            </View>
            {quizLoading && (
              <View style={{ alignItems: 'center', paddingVertical: 30 }}>
                <ActivityIndicator size="large" color="#F59E0B" />
                <Text style={{ color: '#94A3B8', marginTop: 10 }}>Generating quiz…</Text>
              </View>
            )}
            <ScrollView>
              {quiz?.map((q, qi) => (
                <View key={qi} style={{ marginBottom: 20 }}>
                  <Text style={styles.quizQ}>{qi + 1}. {q.q}</Text>
                  {q.options?.map((opt, oi) => {
                    const picked = quizAnswers[qi];
                    const isPicked = picked === oi;
                    const isCorrect = q.answer_idx === oi;
                    const showResult = picked !== undefined;
                    const optStyle = !showResult
                      ? styles.quizOpt
                      : isCorrect
                      ? [styles.quizOpt, styles.quizOptCorrect]
                      : isPicked
                      ? [styles.quizOpt, styles.quizOptWrong]
                      : styles.quizOpt;
                    return (
                      <TouchableOpacity
                        key={oi}
                        testID={`quiz-option-${qi}-${oi}`}
                        style={optStyle}
                        onPress={() => setQuizAnswers((a) => ({ ...a, [qi]: oi }))}
                        disabled={showResult}
                      >
                        <Text style={styles.quizOptText}>
                          {String.fromCharCode(65 + oi)}. {opt}
                        </Text>
                      </TouchableOpacity>
                    );
                  })}
                  {quizAnswers[qi] !== undefined && q.explanation && (
                    <Text style={styles.quizExplain}>↳ {q.explanation}</Text>
                  )}
                </View>
              ))}
            </ScrollView>
          </View>
        )}
      </SafeAreaView>
    </Modal>
  );
};

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0F172A' },
  header: {
    flexDirection: 'row', alignItems: 'center',
    paddingHorizontal: 12, paddingVertical: 10,
    backgroundColor: '#1E293B', borderBottomWidth: 1, borderBottomColor: '#334155',
  },
  headerBtn: { width: 44, height: 44, justifyContent: 'center', alignItems: 'center' },
  headerTitleWrap: { flex: 1, paddingHorizontal: 6 },
  headerTitle: { fontSize: 15, fontWeight: '700', color: '#F8FAFC' },
  headerSub: { fontSize: 11, color: '#94A3B8', marginTop: 2 },
  progressTrack: {
    height: 4, backgroundColor: '#1E293B', overflow: 'hidden',
  },
  progressChapter: { position: 'absolute', left: 0, top: 0, bottom: 0, backgroundColor: '#8B5CF6' },
  progressTTS: { position: 'absolute', left: 0, top: 0, bottom: 0, backgroundColor: '#10B98180' },
  progressMeta: {
    flexDirection: 'row', justifyContent: 'space-between',
    paddingHorizontal: 14, paddingVertical: 6, backgroundColor: '#0F172A',
  },
  progressText: { fontSize: 11, color: '#64748B' },
  progressTextAccent: { fontSize: 11, color: '#10B981', fontWeight: '600' },
  centered: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  loadingText: { color: '#94A3B8', marginTop: 14, fontSize: 13 },
  errorText: { color: '#F87171', marginTop: 12, fontSize: 13, textAlign: 'center', paddingHorizontal: 30 },
  scroll: { flex: 1 },
  scrollContent: { padding: 20, paddingBottom: 40 },
  h1: { fontSize: 26, fontWeight: '800', color: '#F8FAFC', marginTop: 4, marginBottom: 10, lineHeight: 34 },
  h2: { fontSize: 19, fontWeight: '700', color: '#8B5CF6', marginTop: 22, marginBottom: 8, lineHeight: 26 },
  h3: { fontSize: 15, fontWeight: '700', color: '#C4B5FD', marginTop: 16, marginBottom: 6, lineHeight: 22 },
  paragraph: { fontSize: 15, lineHeight: 24, color: '#E2E8F0', marginBottom: 12 },
  // NEW — key takeaways pinned at top of chapter.
  takeawaysCard: { backgroundColor: '#1E293B', borderRadius: 12, padding: 12, marginBottom: 16, borderWidth: 1, borderColor: '#FBBF2440' },
  takeawaysHead: { flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 8 },
  takeawaysHeadText: { color: '#FBBF24', fontSize: 11, fontWeight: '800', letterSpacing: 0.5, textTransform: 'uppercase' },
  takeawayRow: { flexDirection: 'row', gap: 8, marginBottom: 6, alignItems: 'flex-start' },
  takeawayNum: { backgroundColor: '#FBBF2422', color: '#FBBF24', fontSize: 11, fontWeight: '800', width: 22, height: 22, lineHeight: 22, textAlign: 'center', borderRadius: 11 },
  takeawayText: { color: '#E2E8F0', fontSize: 13, lineHeight: 19, flex: 1 },
  // NEW — glossary + comprehension shared.
  extrasCard: { backgroundColor: '#1E293B', borderRadius: 12, padding: 12, marginTop: 12, borderWidth: 1, borderColor: '#334155' },
  extrasHead: { flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 8 },
  extrasHeadText: { color: '#94A3B8', fontSize: 11, fontWeight: '800', letterSpacing: 0.5, textTransform: 'uppercase' },
  glossRow: { paddingVertical: 8, borderTopWidth: 1, borderTopColor: '#334155' },
  glossHead: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  glossTerm: { color: '#A78BFA', fontSize: 14, fontWeight: '800' },
  glossDef: { color: '#CBD5E1', fontSize: 13, lineHeight: 19, marginTop: 6, paddingLeft: 20 },
  compRow: { flexDirection: 'row', alignItems: 'flex-start', gap: 8, paddingVertical: 8, borderTopWidth: 1, borderTopColor: '#334155' },
  compText: { color: '#E2E8F0', fontSize: 13, lineHeight: 19, flex: 1 },
  compHint: { color: '#64748B', fontSize: 11, fontStyle: 'italic', marginTop: 8, lineHeight: 16 },
  bold: { fontWeight: '700', color: '#F8FAFC' },
  italic: { fontStyle: 'italic', color: '#CBD5E1' },
  inlineCode: {
    fontFamily: Platform.select({ ios: 'Menlo', android: 'monospace' }),
    backgroundColor: '#334155', color: '#FDE68A',
    paddingHorizontal: 5, paddingVertical: 2, borderRadius: 4,
    fontSize: 13,
  },
  codeBlock: {
    backgroundColor: '#0B1226', borderLeftWidth: 3, borderLeftColor: '#8B5CF6',
    padding: 12, marginVertical: 10, borderRadius: 6,
  },
  codeText: {
    fontFamily: Platform.select({ ios: 'Menlo', android: 'monospace' }),
    color: '#BFDBFE', fontSize: 13, lineHeight: 19,
  },
  list: { marginBottom: 12 },
  listItem: { flexDirection: 'row', marginBottom: 6, paddingRight: 10 },
  listBullet: { color: '#8B5CF6', fontSize: 16, marginRight: 10, marginTop: -1 },
  listText: { flex: 1, fontSize: 15, lineHeight: 22, color: '#E2E8F0' },
  controlBar: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: 14, paddingVertical: 10,
    backgroundColor: '#1E293B', borderTopWidth: 1, borderTopColor: '#334155',
  },
  navBtn: {
    flexDirection: 'row', alignItems: 'center', gap: 4,
    paddingHorizontal: 12, paddingVertical: 10,
    backgroundColor: '#334155', borderRadius: 8,
  },
  navDisabled: { opacity: 0.4 },
  navText: { color: '#F8FAFC', fontSize: 13, fontWeight: '600' },
  navTextDisabled: { color: '#475569' },
  ttsCluster: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  ttsPrimaryBtn: {
    flexDirection: 'row', alignItems: 'center', gap: 6,
    backgroundColor: '#8B5CF6', paddingHorizontal: 18, paddingVertical: 10, borderRadius: 10,
  },
  ttsPrimaryText: { color: '#FFF', fontSize: 13, fontWeight: '700' },
  ttsSecondaryBtn: {
    width: 44, height: 44, justifyContent: 'center', alignItems: 'center',
    backgroundColor: '#334155', borderRadius: 8,
  },
  toolbar: {
    flexDirection: 'row', alignItems: 'center', gap: 8,
    paddingHorizontal: 12, paddingVertical: 8,
    backgroundColor: '#0B1226', borderBottomWidth: 1, borderBottomColor: '#1E293B',
  },
  toolbarBtn: {
    flexDirection: 'row', alignItems: 'center', gap: 4,
    paddingHorizontal: 10, paddingVertical: 6,
    backgroundColor: '#1E293B', borderRadius: 6,
  },
  toolbarBtnText: { color: '#CBD5E1', fontSize: 12, fontWeight: '600' },
  toolbarBtnTextAccent: { color: '#10B981', fontSize: 12, fontWeight: '600' },
  toolbarLicense: { color: '#64748B', fontSize: 10, fontStyle: 'italic', flex: 1, textAlign: 'right' },
  quizOverlay: {
    position: 'absolute', top: 0, left: 0, right: 0, bottom: 0,
    backgroundColor: 'rgba(15,23,42,0.97)', padding: 18,
  },
  quizHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 },
  quizTitle: { color: '#F8FAFC', fontSize: 18, fontWeight: '700' },
  quizQ: { color: '#F8FAFC', fontSize: 15, fontWeight: '600', marginTop: 14 },
  quizOpt: {
    paddingVertical: 10, paddingHorizontal: 12, marginTop: 6,
    backgroundColor: '#1E293B', borderRadius: 8, borderWidth: 1, borderColor: '#334155',
  },
  quizOptCorrect: { borderColor: '#10B981', backgroundColor: '#10B98122' },
  quizOptWrong: { borderColor: '#EF4444', backgroundColor: '#EF444422' },
  quizOptText: { color: '#E2E8F0', fontSize: 13 },
  quizExplain: { color: '#94A3B8', fontSize: 12, marginTop: 6, fontStyle: 'italic' },
});

export default ReadingVisualizer;
