// ============================================================================
// CODEDOCK - BIBLE MODAL COMPONENT
// Complete Day 1 to Godtier Coding Manual
// With Ambient Bossa Nova Learning Music
// ============================================================================

import React, { memo, useState, useCallback, useEffect } from 'react';
import {
  View, Text, StyleSheet, Modal, TouchableOpacity,
  ScrollView, Platform, Vibration, Switch
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useAudioPlayer, setAudioModeAsync } from 'expo-audio';
import { useModalStore } from '../../store/modalStore';
import { ReadingVisualizer } from '../ReadingLibrary/ReadingVisualizer';
import { ThemeColors } from '../../constants/themes';
import { BibleChapter, BibleProgress } from '../../types';
import { CODING_BIBLE, getTierColor, getBibleStats } from './bibleContent';
import { API_BASE } from '../../utils/apiBase';

// Ambient Bossa Nova / Classical music URLs (royalty-free)
import { apiFetch } from '../../utils/apiController';
import { toast } from '../../components/Toast';
const AMBIENT_TRACKS = [
  'https://cdn.pixabay.com/download/audio/2022/10/25/audio_946b0939c8.mp3', // Soft Jazz
  'https://cdn.pixabay.com/download/audio/2022/05/27/audio_1808fbf07a.mp3', // Chill
  'https://cdn.pixabay.com/download/audio/2024/11/04/audio_4956b4edd1.mp3', // Classical
];

interface BibleModalProps {
  visible: boolean;
  onClose: () => void;
  colors: ThemeColors;
  progress: BibleProgress;
  onMarkComplete: (chapterId: string) => void;
  onToggleBookmark: (chapterId: string) => void;
  onLoadCode: (code: string, language: string) => void;
}

// eslint-disable-next-line react/display-name
export const BibleModal: React.FC<BibleModalProps> = memo(({
  visible,
  onClose,
  colors,
  progress,
  onMarkComplete,
  onToggleBookmark,
  onLoadCode,
}) => {
  const [selectedChapter, setSelectedChapter] = useState<BibleChapter | null>(null);
  const [currentSectionIndex, setCurrentSectionIndex] = useState(0);
  const [musicEnabled, setMusicEnabled] = useState(true);
  const [isPlaying, setIsPlaying] = useState(false);
  const topicData = useModalStore(s => s.getModalData('bible'));
  const categoryFilter = topicData?.topic || '';
  const [dbBibles, setDbBibles] = useState<any[]>([]);
  const [, setLoading] = useState(false);
  const [, setPage] = useState(1);
  const [, setHasMore] = useState(true);
  // New: launch the Reading Visualizer for any API-backed bible
  const [readerTarget, setReaderTarget] = useState<{ id: string; title: string; totalChapters: number } | null>(null);

  const fetchBibles = useCallback(async (p = 1, append = false) => {
    try {
      setLoading(true);
      let url = `${API_BASE}/api/academy/bibles?page=${p}&limit=50`;
      if (categoryFilter) url += `&category=${categoryFilter}`;
      const res = await apiFetch(url);
      const data = await res.json();
      setDbBibles(prev => append ? [...prev, ...data.bibles] : data.bibles);
      setHasMore(p < data.pages);
      setPage(p);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (visible) {
      fetchBibles(1, false);
    }
  }, [visible, fetchBibles]);

  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const loadFullBible = async (bibleMeta: any) => {
    try {
      setLoading(true);
      const res = await apiFetch(`${API_BASE}/api/academy/bible/${bibleMeta.id}`);
      const data = await res.json();
      const bible = data.bible;
      
      // Map DB schema to expected BibleChapter structure
      let flattenedSections: any[] = [];
      if (bible.sections) {
        bible.sections.forEach((sec: any) => {
          if (sec.articles) {
            sec.articles.forEach((art: any) => {
              flattenedSections.push({
                title: art.title || sec.name,
                content: art.content || 'No content provided.',
                code: '',
                language: 'python'
              });
            });
          }
        });
      }

      openChapter({
        id: bible.id,
        day: bible.total_hours || 1,
        tier: 'godtier',
        title: bible.name,
        subtitle: bible.description || 'Hyperscale Knowledge',
        icon: bible.icon || 'book',
        color: bible.color || '#F59E0B',
        unlocked: true,
        estimatedTime: `${bible.total_hours || 5}h`,
        sections: flattenedSections.length > 0 ? flattenedSections : [{title: 'Overview', content: bible.description}]
      });
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };


  // Pick a random track URI for the player
  const [trackUri] = useState(() => AMBIENT_TRACKS[Math.floor(Math.random() * AMBIENT_TRACKS.length)]);
  const player = useAudioPlayer({ uri: trackUri });

  const stats = getBibleStats(progress.completedChapters);

  // Configure audio mode & start/stop music based on visibility & preference
  useEffect(() => {
    if (visible && musicEnabled) {
      (async () => {
        try {
          await setAudioModeAsync({
            playsInSilentMode: true,
            shouldPlayInBackground: false,
          });
          player.loop = true;
          player.volume = 0.3;
          player.play();
          setIsPlaying(true);
        } catch (error) {
          console.log('Music playback error:', error);
        }
      })();
    } else {
      try {
        player.pause();
        setIsPlaying(false);
      } catch (error) {
        console.log('Stop music error:', error);
      }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visible, musicEnabled]);

  const toggleMusic = () => {
    setMusicEnabled(!musicEnabled);
  };

  const openChapter = useCallback((chapter: BibleChapter) => {
    setSelectedChapter(chapter);
    setCurrentSectionIndex(0);
  }, []);

  const closeChapter = useCallback(() => {
    setSelectedChapter(null);
    setCurrentSectionIndex(0);
  }, []);

  const nextSection = useCallback(() => {
    if (selectedChapter && currentSectionIndex < selectedChapter.sections.length - 1) {
      setCurrentSectionIndex(prev => prev + 1);
    }
  }, [selectedChapter, currentSectionIndex]);

  const prevSection = useCallback(() => {
    if (currentSectionIndex > 0) {
      setCurrentSectionIndex(prev => prev - 1);
    }
  }, [currentSectionIndex]);

  const handleComplete = useCallback(() => {
    if (selectedChapter) {
      onMarkComplete(selectedChapter.id);
      if (Platform.OS !== 'web') Vibration.vibrate([50, 50]);
      toast.info(`You finished "${selectedChapter.title}"!`);
    }
  }, [selectedChapter, onMarkComplete]);

  const handleLoadCode = useCallback((code: string, language: string) => {
    onLoadCode(code, language);
    onClose();
    setSelectedChapter(null);
  }, [onLoadCode, onClose]);

  const handleClose = useCallback(() => {
    setMusicEnabled(false);
    setSelectedChapter(null);
    setCurrentSectionIndex(0);
    onClose();
  }, [onClose]);

  return (
    <>
    <Modal visible={visible} transparent animationType="slide" onRequestClose={handleClose}>
      <View style={styles.overlay}>
        <View style={[styles.content, { backgroundColor: colors.surface }]}>
          {!selectedChapter ? (
            // Chapter List View
            <>
              <View style={[styles.header, { borderBottomColor: colors.border }]}>
                <View style={styles.titleRow}>
                  <Ionicons name="book" size={22} color="#FFD700" />
                  <Text style={[styles.title, { color: colors.text }]}>Coding Bible</Text>
                </View>
                <TouchableOpacity onPress={handleClose}>
                  <Ionicons name="close" size={24} color={colors.secondary} />
                </TouchableOpacity>
              </View>

              {/* Progress Banner */}
              <View style={[styles.progressBanner, { backgroundColor: colors.surfaceAlt }]}>
                <View style={styles.progressInfo}>
                  <Text style={[styles.progressTitle, { color: colors.text }]}>Your Journey</Text>
                  <Text style={[styles.progressSubtitle, { color: colors.textMuted }]}>
                    {stats.completedCount}/{stats.totalChapters} chapters • ~52 weeks
                  </Text>
                </View>
                <View style={[styles.progressCircle, { borderColor: '#FFD700' }]}>
                  <Text style={[styles.progressPercent, { color: '#FFD700' }]}>{stats.percentage}%</Text>
                </View>
              </View>

              {/* Music Control */}
              <View style={[styles.musicControl, { backgroundColor: colors.surfaceAlt }]}>
                <View style={styles.musicInfo}>
                  <Ionicons 
                    name={isPlaying ? 'musical-notes' : 'musical-notes-outline'} 
                    size={18} 
                    color={isPlaying ? colors.primary : colors.textMuted} 
                  />
                  <View>
                    <Text style={[styles.musicTitle, { color: colors.text }]}>Ambient Learning Music</Text>
                    <Text style={[styles.musicSubtitle, { color: colors.textMuted }]}>
                      {isPlaying ? 'Soft bossa nova playing...' : 'Music paused'}
                    </Text>
                  </View>
                </View>
                <Switch
                  value={musicEnabled}
                  onValueChange={toggleMusic}
                  trackColor={{ false: colors.surfaceAlt, true: colors.primary + '50' }}
                  thumbColor={musicEnabled ? colors.primary : colors.textMuted}
                />
              </View>

              {/* Chapter List */}
              <ScrollView style={styles.chapterList}>
                {/* API-backed Bibles — open in the new Reading Visualizer */}
                {dbBibles.length > 0 && (
                  <View style={{ marginHorizontal: 14, marginTop: 8, marginBottom: 4 }}>
                    <Text style={{ color: colors.textMuted, fontSize: 11, fontWeight: '700', letterSpacing: 0.6, textTransform: 'uppercase', marginBottom: 6 }}>
                      Read in Visualizer
                    </Text>
                    {dbBibles.slice(0, 8).map((b: any) => {
                      const tot = (b.sections || []).reduce((n: number, s: any) => n + (s.articles?.length || 0), 0) || b.total_articles || 8;
                      return (
                        <TouchableOpacity
                          key={`db_${b.id}`}
                          testID={`bible-visualizer-${b.id}`}
                          style={[styles.chapterCard, { backgroundColor: colors.surfaceAlt, borderLeftColor: '#10B981' }]}
                          onPress={() => setReaderTarget({ id: b.id, title: b.name, totalChapters: Math.max(1, tot) })}
                        >
                          <View style={[styles.chapterIcon, { backgroundColor: '#10B98122' }]}>
                            <Ionicons name="library" size={24} color="#10B981" />
                          </View>
                          <View style={styles.chapterInfo}>
                            <View style={styles.chapterHeader}>
                              <Text style={[styles.chapterDay, { color: '#10B981' }]}>
                                {b.category?.toUpperCase() || 'BIBLE'}
                              </Text>
                              <Text style={[styles.chapterSections, { color: colors.textMuted }]}>
                                {tot} ch • TTS ready
                              </Text>
                            </View>
                            <Text style={[styles.chapterTitle, { color: colors.text }]} numberOfLines={1}>{b.name}</Text>
                            <Text style={[styles.chapterSections, { color: colors.textMuted }]} numberOfLines={2}>{b.description}</Text>
                          </View>
                          <Ionicons name="chevron-forward" size={20} color={colors.textMuted} />
                        </TouchableOpacity>
                      );
                    })}
                    <Text style={{ color: colors.textMuted, fontSize: 11, fontWeight: '700', letterSpacing: 0.6, textTransform: 'uppercase', marginTop: 12, marginBottom: 6 }}>
                      Bundled 100-Day Curriculum
                    </Text>
                  </View>
                )}
                {CODING_BIBLE.map((chapter) => (
                  <TouchableOpacity
                    key={chapter.id}
                    style={[styles.chapterCard, { backgroundColor: colors.surfaceAlt, borderLeftColor: getTierColor(chapter.tier) }]}
                    onPress={() => openChapter(chapter)}
                  >
                    <View style={[styles.chapterIcon, { backgroundColor: getTierColor(chapter.tier) + '20' }]}>
                      <Ionicons name={chapter.icon as any} size={24} color={getTierColor(chapter.tier)} />
                    </View>
                    <View style={styles.chapterInfo}>
                      <View style={styles.chapterHeader}>
                        <Text style={[styles.chapterDay, { color: getTierColor(chapter.tier) }]}>
                          {chapter.day === 100 ? 'MASTERY' : `Day ${chapter.day}`}
                        </Text>
                        <Text style={[styles.chapterTier, { color: colors.textMuted }]}>
                          {chapter.tier.toUpperCase()}
                        </Text>
                        {chapter.estimatedTime && (
                          <Text style={[styles.chapterTime, { color: colors.textMuted }]}>
                            ~{chapter.estimatedTime}
                          </Text>
                        )}
                      </View>
                      <Text style={[styles.chapterTitle, { color: colors.text }]}>{chapter.title}</Text>
                      <Text style={[styles.chapterSubtitle, { color: colors.textMuted }]}>{chapter.subtitle}</Text>
                      <Text style={[styles.chapterSections, { color: colors.textMuted }]}>
                        {chapter.sections.length} sections • {chapter.exercises?.length || 0} exercises
                      </Text>
                    </View>
                    <View style={styles.chapterStatus}>
                      {progress.completedChapters[chapter.id] && (
                        <Ionicons name="checkmark-circle" size={22} color={colors.success} />
                      )}
                      {progress.bookmarks.includes(chapter.id) && (
                        <Ionicons name="bookmark" size={18} color="#FFD700" />
                      )}
                    </View>
                  </TouchableOpacity>
                ))}
              </ScrollView>
            </>
          ) : (
            // Chapter Reading View
            <>
              <View style={[styles.header, { borderBottomColor: colors.border }]}>
                <TouchableOpacity style={styles.backButton} onPress={closeChapter}>
                  <Ionicons name="arrow-back" size={20} color={colors.primary} />
                  <Text style={[styles.backText, { color: colors.primary }]}>Back</Text>
                </TouchableOpacity>
                <View style={styles.chapterActions}>
                  <TouchableOpacity onPress={() => onToggleBookmark(selectedChapter.id)}>
                    <Ionicons
                      name={progress.bookmarks.includes(selectedChapter.id) ? 'bookmark' : 'bookmark-outline'}
                      size={22}
                      color={progress.bookmarks.includes(selectedChapter.id) ? '#FFD700' : colors.secondary}
                    />
                  </TouchableOpacity>
                  <TouchableOpacity onPress={handleClose}>
                    <Ionicons name="close" size={24} color={colors.secondary} />
                  </TouchableOpacity>
                </View>
              </View>

              {/* Chapter Header */}
              <View style={[styles.readingHeader, { backgroundColor: getTierColor(selectedChapter.tier) + '15' }]}>
                <Text style={[styles.readingDay, { color: getTierColor(selectedChapter.tier) }]}>
                  {selectedChapter.day === 100 ? '🏆 MASTERY LEVEL' : `📖 Day ${selectedChapter.day}`}
                </Text>
                <Text style={[styles.readingTitle, { color: colors.text }]}>{selectedChapter.title}</Text>
                <Text style={[styles.readingSubtitle, { color: colors.textSecondary }]}>{selectedChapter.subtitle}</Text>
                <View style={styles.readingProgress}>
                  <Text style={[styles.readingProgressText, { color: colors.textMuted }]}>
                    Section {currentSectionIndex + 1} of {selectedChapter.sections.length}
                  </Text>
                  <View style={[styles.progressBar, { backgroundColor: colors.surfaceAlt }]}>
                    <View
                      style={[
                        styles.progressFill,
                        {
                          backgroundColor: getTierColor(selectedChapter.tier),
                          width: `${((currentSectionIndex + 1) / selectedChapter.sections.length) * 100}%`,
                        },
                      ]}
                    />
                  </View>
                </View>
              </View>

              {/* Section Content */}
              <ScrollView style={styles.readingContent}>
                {selectedChapter.sections[currentSectionIndex] && (
                  <View style={styles.sectionContainer}>
                    <Text style={[styles.sectionTitle, { color: colors.text }]}>
                      {selectedChapter.sections[currentSectionIndex].title}
                    </Text>

                    <Text style={[styles.sectionContent, { color: colors.textSecondary }]}>
                      {selectedChapter.sections[currentSectionIndex].content}
                    </Text>

                    {selectedChapter.sections[currentSectionIndex].warning && (
                      <View style={[styles.warningBox, { backgroundColor: colors.error + '15', borderColor: colors.error }]}>
                        <Ionicons name="warning" size={18} color={colors.error} />
                        <Text style={[styles.warningText, { color: colors.error }]}>
                          {selectedChapter.sections[currentSectionIndex].warning}
                        </Text>
                      </View>
                    )}

                    {selectedChapter.sections[currentSectionIndex].code && (
                      <View style={styles.codeContainer}>
                        <View style={[styles.codeHeader, { backgroundColor: colors.surfaceAlt }]}>
                          <Text style={[styles.codeLang, { color: colors.textMuted }]}>
                            {selectedChapter.sections[currentSectionIndex].language || 'python'}
                          </Text>
                          <TouchableOpacity
                            style={[styles.tryButton, { backgroundColor: colors.primary }]}
                            onPress={() => handleLoadCode(
                              selectedChapter.sections[currentSectionIndex].code!,
                              selectedChapter.sections[currentSectionIndex].language || 'python'
                            )}
                          >
                            <Ionicons name="play" size={12} color="#FFF" />
                            <Text style={styles.tryButtonText}>Try it</Text>
                          </TouchableOpacity>
                        </View>
                        <ScrollView horizontal showsHorizontalScrollIndicator={false}>
                          <Text style={[styles.codeText, { color: colors.text, backgroundColor: colors.codeBackground }]}>
                            {selectedChapter.sections[currentSectionIndex].code}
                          </Text>
                        </ScrollView>
                      </View>
                    )}

                    {selectedChapter.sections[currentSectionIndex].tips && (
                      <View style={[styles.tipsContainer, { backgroundColor: colors.primary + '10' }]}>
                        <Text style={[styles.tipsTitle, { color: colors.primary }]}>💡 Tips</Text>
                        {selectedChapter.sections[currentSectionIndex].tips!.map((tip, i) => (
                          <Text key={i} style={[styles.tipText, { color: colors.textSecondary }]}>• {tip}</Text>
                        ))}
                      </View>
                    )}
                  </View>
                )}
              </ScrollView>

              {/* Navigation Footer */}
              <View style={[styles.navFooter, { backgroundColor: colors.surfaceAlt, borderTopColor: colors.border }]}>
                <TouchableOpacity
                  style={[styles.navButton, currentSectionIndex === 0 && styles.navButtonDisabled]}
                  onPress={prevSection}
                  disabled={currentSectionIndex === 0}
                >
                  <Ionicons name="chevron-back" size={20} color={currentSectionIndex === 0 ? colors.textMuted : colors.primary} />
                  <Text style={[styles.navButtonText, { color: currentSectionIndex === 0 ? colors.textMuted : colors.primary }]}>
                    Previous
                  </Text>
                </TouchableOpacity>

                {currentSectionIndex === selectedChapter.sections.length - 1 ? (
                  <TouchableOpacity
                    style={[styles.completeButton, { backgroundColor: colors.success }]}
                    onPress={handleComplete}
                  >
                    <Ionicons name="checkmark-circle" size={18} color="#FFF" />
                    <Text style={styles.completeButtonText}>Complete</Text>
                  </TouchableOpacity>
                ) : (
                  <TouchableOpacity
                    style={[styles.navButton, styles.navButtonNext, { backgroundColor: colors.primary }]}
                    onPress={nextSection}
                  >
                    <Text style={[styles.navButtonText, { color: '#FFF' }]}>Next</Text>
                    <Ionicons name="chevron-forward" size={20} color="#FFF" />
                  </TouchableOpacity>
                )}
              </View>
            </>
          )}
        </View>
      </View>
    </Modal>
    {readerTarget && (
      <ReadingVisualizer
        visible={!!readerTarget}
        onClose={() => setReaderTarget(null)}
        itemType="bible"
        itemId={readerTarget.id}
        itemTitle={readerTarget.title}
        chapterIdx={0}
        totalChapters={readerTarget.totalChapters}
        contentEndpoint={(id, idx) => `/api/academy/bible/${id}/chapter/${idx}/content`}
      />
    )}
    </>
  );
});

const styles = StyleSheet.create({
  overlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.5)',
    justifyContent: 'flex-end',
  },
  content: {
    maxHeight: '95%',
    borderTopLeftRadius: 20,
    borderTopRightRadius: 20,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingVertical: 14,
    borderBottomWidth: 1,
  },
  titleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  title: {
    fontSize: 20,
    fontWeight: '700',
  },
  progressBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: 16,
    marginHorizontal: 16,
    marginTop: 12,
    borderRadius: 12,
  },
  progressInfo: {
    flex: 1,
  },
  progressTitle: {
    fontSize: 16,
    fontWeight: '700',
  },
  progressSubtitle: {
    fontSize: 13,
    marginTop: 2,
  },
  progressCircle: {
    width: 50,
    height: 50,
    borderRadius: 25,
    borderWidth: 3,
    alignItems: 'center',
    justifyContent: 'center',
  },
  progressPercent: {
    fontSize: 14,
    fontWeight: '700',
  },
  musicControl: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingVertical: 12,
    marginHorizontal: 16,
    marginTop: 8,
    borderRadius: 12,
  },
  musicInfo: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  musicTitle: {
    fontSize: 14,
    fontWeight: '600',
  },
  musicSubtitle: {
    fontSize: 11,
    marginTop: 1,
  },
  chapterList: {
    flex: 1,
    padding: 16,
  },
  chapterCard: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 14,
    borderRadius: 12,
    marginBottom: 12,
    borderLeftWidth: 4,
  },
  chapterIcon: {
    width: 48,
    height: 48,
    borderRadius: 12,
    alignItems: 'center',
    justifyContent: 'center',
  },
  chapterInfo: {
    flex: 1,
    marginLeft: 14,
  },
  chapterHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  chapterDay: {
    fontSize: 11,
    fontWeight: '700',
  },
  chapterTier: {
    fontSize: 10,
    fontWeight: '600',
  },
  chapterTime: {
    fontSize: 10,
  },
  chapterTitle: {
    fontSize: 16,
    fontWeight: '700',
    marginTop: 2,
  },
  chapterSubtitle: {
    fontSize: 13,
    marginTop: 2,
  },
  chapterSections: {
    fontSize: 11,
    marginTop: 4,
  },
  chapterStatus: {
    flexDirection: 'row',
    gap: 8,
  },
  backButton: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  backText: {
    fontSize: 15,
    fontWeight: '600',
  },
  chapterActions: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 16,
  },
  readingHeader: {
    padding: 16,
  },
  readingDay: {
    fontSize: 13,
    fontWeight: '700',
  },
  readingTitle: {
    fontSize: 24,
    fontWeight: '800',
    marginTop: 4,
  },
  readingSubtitle: {
    fontSize: 15,
    marginTop: 4,
  },
  readingProgress: {
    marginTop: 12,
  },
  readingProgressText: {
    fontSize: 12,
    marginBottom: 6,
  },
  progressBar: {
    height: 4,
    borderRadius: 2,
    overflow: 'hidden',
  },
  progressFill: {
    height: '100%',
    borderRadius: 2,
  },
  readingContent: {
    flex: 1,
    padding: 16,
  },
  sectionContainer: {
    paddingBottom: 20,
  },
  sectionTitle: {
    fontSize: 20,
    fontWeight: '700',
    marginBottom: 12,
  },
  sectionContent: {
    fontSize: 15,
    lineHeight: 24,
  },
  warningBox: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    padding: 12,
    borderRadius: 8,
    marginTop: 16,
    borderWidth: 1,
    gap: 10,
  },
  warningText: {
    flex: 1,
    fontSize: 13,
    fontWeight: '500',
  },
  codeContainer: {
    marginTop: 16,
    borderRadius: 12,
    overflow: 'hidden',
  },
  codeHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  codeLang: {
    fontSize: 12,
    fontWeight: '600',
    textTransform: 'uppercase',
  },
  tryButton: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 10,
    paddingVertical: 5,
    borderRadius: 6,
    gap: 4,
  },
  tryButtonText: {
    color: '#FFF',
    fontSize: 11,
    fontWeight: '600',
  },
  codeText: {
    fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace',
    fontSize: 13,
    padding: 12,
    lineHeight: 20,
  },
  tipsContainer: {
    padding: 14,
    borderRadius: 10,
    marginTop: 16,
  },
  tipsTitle: {
    fontSize: 14,
    fontWeight: '700',
    marginBottom: 8,
  },
  tipText: {
    fontSize: 13,
    lineHeight: 22,
  },
  navFooter: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: 16,
    borderTopWidth: 1,
  },
  navButton: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingVertical: 10,
    borderRadius: 8,
    gap: 6,
  },
  navButtonDisabled: {
    opacity: 0.5,
  },
  navButtonNext: {
    paddingHorizontal: 24,
  },
  navButtonText: {
    fontSize: 14,
    fontWeight: '600',
  },
  completeButton: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 20,
    paddingVertical: 12,
    borderRadius: 8,
    gap: 8,
  },
  completeButtonText: {
    color: '#FFF',
    fontSize: 14,
    fontWeight: '700',
  },
});

export default BibleModal;
