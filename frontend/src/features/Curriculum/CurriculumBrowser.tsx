/**
 * Curriculum Browser v11.0.0
 * Browse 10 comprehensive CS courses with 750+ hours of content
 */

import React, { useState, useEffect } from 'react';
import { API_BASE } from '../../utils/apiBase';
import {
  View, Text, StyleSheet, TouchableOpacity, ScrollView,
  Modal, ActivityIndicator, Platform,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import { apiFetch } from '../../utils/apiController';
const API_URL = API_BASE;

interface CurriculumBrowserProps {
  visible: boolean;
  onClose: () => void;
  colors: any;
  onCodeExample?: (code: string, language: string) => void;
}

interface Course {
  id: string;
  code: string;
  title: string;
  subtitle?: string;
  hours: number;
  weeks: number | { week: number; title: string; topics: string[]; code_examples?: any[]; exercises?: string[] }[];
  level?: string;
  prerequisites?: string[];
  description?: string;
  learning_objectives?: string[];
}

interface CurriculumInfo {
  total_classes: number;
  total_hours: number;
  features: string[];
  available_classes: Course[];
}

export const CurriculumBrowser: React.FC<CurriculumBrowserProps> = ({
  visible, onClose, colors, onCodeExample
}) => {
  const [isLoading, setIsLoading] = useState(true);
  const [curriculumInfo, setCurriculumInfo] = useState<CurriculumInfo | null>(null);
  const [, setSelectedCourse] = useState<Course | null>(null);
  const [courseDetails, setCourseDetails] = useState<any>(null);
  const [selectedWeek, setSelectedWeek] = useState<number | null>(null);
  const [weekContent, setWeekContent] = useState<any>(null);
  const [codeExamples, setCodeExamples] = useState<any[]>([]);
  const [viewMode, setViewMode] = useState<'list' | 'course' | 'week'>('list');

  const levelColors: Record<string, string> = {
    beginner: '#10B981',
    intermediate: '#F59E0B',
    advanced: '#EF4444',
    expert: '#8B5CF6',
  };

  const categoryIcons: Record<string, string> = {
    data_structures: '📊',
    oop: '🧱',
    databases: '🗄️',
    operating_systems: '💻',
    networks: '🌐',
    compilers: '⚙️',
    gamedev_fundamentals: '🎮',
    game_engine: '🎯',
    graphics_programming: '🎨',
    game_ai_physics: '🤖',
  };

  useEffect(() => {
    if (visible) {
      loadCurriculumInfo();
    }
  }, [visible]);

  const loadCurriculumInfo = async () => {
    setIsLoading(true);
    try {
      const response = await apiFetch(`${API_URL}/api/curriculum/info`);
      const data = await response.json();
      setCurriculumInfo(data);
    } catch (error) {
      console.error('Failed to load curriculum:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const loadCourseDetails = async (courseId: string) => {
    setIsLoading(true);
    try {
      const [detailsRes, examplesRes] = await Promise.all([
        apiFetch(`${API_URL}/api/curriculum/classes/${courseId}`),
        apiFetch(`${API_URL}/api/curriculum/classes/${courseId}/code-examples`),
      ]);
      const details = await detailsRes.json();
      const examples = await examplesRes.json();
      setCourseDetails(details);
      setCodeExamples(examples.examples || []);
      setViewMode('course');
    } catch (error) {
      console.error('Failed to load course:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const loadWeekContent = async (courseId: string, weekNum: number) => {
    setIsLoading(true);
    try {
      const response = await apiFetch(`${API_URL}/api/curriculum/classes/${courseId}/week/${weekNum}`);
      const data = await response.json();
      setWeekContent(data);
      setSelectedWeek(weekNum);
      setViewMode('week');
    } catch (error) {
      console.error('Failed to load week:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const goBack = () => {
    if (viewMode === 'week') {
      setViewMode('course');
      setSelectedWeek(null);
      setWeekContent(null);
    } else if (viewMode === 'course') {
      setViewMode('list');
      setSelectedCourse(null);
      setCourseDetails(null);
    }
  };

  const renderHeader = () => (
    <View style={[styles.header, { borderBottomColor: colors.border }]}>
      {viewMode !== 'list' ? (
        <TouchableOpacity onPress={goBack} style={styles.backBtn}>
          <Ionicons name="arrow-back" size={24} color={colors.text} />
        </TouchableOpacity>
      ) : (
        <TouchableOpacity onPress={onClose} style={styles.closeBtn}>
          <Ionicons name="close" size={24} color={colors.text} />
        </TouchableOpacity>
      )}
      <Text style={[styles.title, { color: colors.text }]} numberOfLines={1}>
        {viewMode === 'list' ? '📚 Curriculum' : viewMode === 'course' ? courseDetails?.title : `Week ${selectedWeek}`}
      </Text>
      <View style={styles.placeholder} />
    </View>
  );

  const renderCourseList = () => (
    <ScrollView style={styles.content} showsVerticalScrollIndicator={false}>
      {curriculumInfo && (
        <View style={[styles.statsCard, { backgroundColor: colors.primary + '15', borderColor: colors.primary }]}>
          <Text style={[styles.statsTitle, { color: colors.primary }]}>🎓 CodeDock Curriculum v11.0</Text>
          <View style={styles.statsRow}>
            <View style={styles.statItem}>
              <Text style={[styles.statValue, { color: colors.text }]}>{curriculumInfo.total_classes}</Text>
              <Text style={[styles.statLabel, { color: colors.textSecondary }]}>Courses</Text>
            </View>
            <View style={styles.statItem}>
              <Text style={[styles.statValue, { color: colors.text }]}>{curriculumInfo.total_hours}</Text>
              <Text style={[styles.statLabel, { color: colors.textSecondary }]}>Hours</Text>
            </View>
            <View style={styles.statItem}>
              <Text style={[styles.statValue, { color: colors.text }]}>4</Text>
              <Text style={[styles.statLabel, { color: colors.textSecondary }]}>Tracks</Text>
            </View>
          </View>
        </View>
      )}

      <Text style={[styles.sectionTitle, { color: colors.text }]}>Available Courses</Text>
      
      {curriculumInfo?.available_classes?.map((course) => (
        <TouchableOpacity
          key={course.id}
          style={[styles.courseCard, { backgroundColor: colors.cardBackground, borderColor: colors.border }]}
          onPress={() => {
            setSelectedCourse(course);
            loadCourseDetails(course.id);
          }}
        >
          <View style={styles.courseHeader}>
            <Text style={styles.courseIcon}>{categoryIcons[course.id] || '📖'}</Text>
            <View style={styles.courseInfo}>
              <Text style={[styles.courseCode, { color: colors.primary }]}>{course.code}</Text>
              <Text style={[styles.courseTitle, { color: colors.text }]} numberOfLines={2}>{course.title}</Text>
            </View>
            {course.level && (
              <View style={[styles.levelBadge, { backgroundColor: levelColors[course.level] || colors.primary }]}>
                <Text style={styles.levelText}>{course.level}</Text>
              </View>
            )}
          </View>
          <View style={styles.courseMeta}>
            <View style={styles.metaItem}>
              <Ionicons name="time-outline" size={14} color={colors.textSecondary} />
              <Text style={[styles.metaText, { color: colors.textSecondary }]}>{course.hours}h</Text>
            </View>
            <View style={styles.metaItem}>
              <Ionicons name="calendar-outline" size={14} color={colors.textSecondary} />
              <Text style={[styles.metaText, { color: colors.textSecondary }]}>
                {Array.isArray(course.weeks) ? course.weeks.length : course.weeks} weeks
              </Text>
            </View>
            <Ionicons name="chevron-forward" size={20} color={colors.textSecondary} />
          </View>
        </TouchableOpacity>
      ))}
    </ScrollView>
  );

  const renderCourseDetails = () => (
    <ScrollView style={styles.content} showsVerticalScrollIndicator={false}>
      {courseDetails && (
        <>
          <View style={[styles.courseDetailHeader, { backgroundColor: colors.cardBackground, borderColor: colors.border }]}>
            <Text style={styles.detailIcon}>{categoryIcons[courseDetails.id] || '📖'}</Text>
            <Text style={[styles.detailCode, { color: colors.primary }]}>{courseDetails.code}</Text>
            <Text style={[styles.detailTitle, { color: colors.text }]}>{courseDetails.title}</Text>
            {courseDetails.subtitle && (
              <Text style={[styles.detailSubtitle, { color: colors.textSecondary }]}>{courseDetails.subtitle}</Text>
            )}
            <View style={styles.detailMeta}>
              <View style={[styles.metaBadge, { backgroundColor: colors.primary + '20' }]}>
                <Text style={[styles.metaBadgeText, { color: colors.primary }]}>⏱️ {courseDetails.hours}h</Text>
              </View>
              <View style={[styles.metaBadge, { backgroundColor: colors.primary + '20' }]}>
                <Text style={[styles.metaBadgeText, { color: colors.primary }]}>📅 {Array.isArray(courseDetails.weeks) ? courseDetails.weeks.length : courseDetails.weeks} weeks</Text>
              </View>
              {courseDetails.level && (
                <View style={[styles.metaBadge, { backgroundColor: levelColors[courseDetails.level] + '30' }]}>
                  <Text style={[styles.metaBadgeText, { color: levelColors[courseDetails.level] }]}>🎯 {courseDetails.level}</Text>
                </View>
              )}
            </View>
          </View>

          {courseDetails.description && (
            <View style={[styles.section, { backgroundColor: colors.cardBackground, borderColor: colors.border }]}>
              <Text style={[styles.sectionHeader, { color: colors.text }]}>📝 Description</Text>
              <Text style={[styles.descText, { color: colors.textSecondary }]}>{courseDetails.description}</Text>
            </View>
          )}

          {courseDetails.learning_objectives?.length > 0 && (
            <View style={[styles.section, { backgroundColor: colors.cardBackground, borderColor: colors.border }]}>
              <Text style={[styles.sectionHeader, { color: colors.text }]}>🎯 Learning Objectives</Text>
              {courseDetails.learning_objectives.map((obj: string, i: number) => (
                <View key={i} style={styles.objectiveItem}>
                  <Text style={[styles.objectiveBullet, { color: colors.primary }]}>✓</Text>
                  <Text style={[styles.objectiveText, { color: colors.textSecondary }]}>{obj}</Text>
                </View>
              ))}
            </View>
          )}

          <Text style={[styles.sectionTitle, { color: colors.text }]}>📅 Weekly Schedule</Text>
          {(Array.isArray(courseDetails.weeks) ? courseDetails.weeks : []).map((week: any) => (
            <TouchableOpacity
              key={week.week}
              style={[styles.weekCard, { backgroundColor: colors.cardBackground, borderColor: colors.border }]}
              onPress={() => loadWeekContent(courseDetails.id, week.week)}
            >
              <View style={[styles.weekNum, { backgroundColor: colors.primary }]}>
                <Text style={styles.weekNumText}>{week.week}</Text>
              </View>
              <View style={styles.weekInfo}>
                <Text style={[styles.weekTitle, { color: colors.text }]}>{week.title}</Text>
                <Text style={[styles.weekTopics, { color: colors.textSecondary }]} numberOfLines={1}>
                  {week.topics?.join(' • ')}
                </Text>
              </View>
              <Ionicons name="chevron-forward" size={20} color={colors.textSecondary} />
            </TouchableOpacity>
          ))}

          {codeExamples.length > 0 && (
            <>
              <Text style={[styles.sectionTitle, { color: colors.text, marginTop: 20 }]}>💻 Code Examples ({codeExamples.length})</Text>
              {codeExamples.slice(0, 5).map((example, i) => (
                <TouchableOpacity
                  key={i}
                  style={[styles.exampleCard, { backgroundColor: colors.codeBackground, borderColor: colors.border }]}
                  onPress={() => onCodeExample?.(example.code, example.language || 'python')}
                >
                  <Text style={[styles.exampleTitle, { color: colors.text }]}>{example.title}</Text>
                  <Text style={[styles.exampleLang, { color: colors.primary }]}>{example.language || 'python'}</Text>
                </TouchableOpacity>
              ))}
            </>
          )}
        </>
      )}
    </ScrollView>
  );

  const renderWeekContent = () => (
    <ScrollView style={styles.content} showsVerticalScrollIndicator={false}>
      {weekContent && (
        <>
          <View style={[styles.weekHeader, { backgroundColor: colors.cardBackground, borderColor: colors.border }]}>
            <Text style={[styles.weekHeaderTitle, { color: colors.text }]}>{weekContent.week?.title || `Week ${selectedWeek}`}</Text>
            {weekContent.week?.topics && (
              <View style={styles.topicsList}>
                {weekContent.week.topics.map((topic: string, i: number) => (
                  <View key={i} style={[styles.topicChip, { backgroundColor: colors.primary + '20' }]}>
                    <Text style={[styles.topicText, { color: colors.primary }]}>{topic}</Text>
                  </View>
                ))}
              </View>
            )}
          </View>

          {weekContent.week?.code_examples?.map((example: any, i: number) => (
            <View key={i} style={[styles.codeExampleCard, { backgroundColor: colors.codeBackground, borderColor: colors.border }]}>
              <View style={styles.codeExampleHeader}>
                <Text style={[styles.codeExampleTitle, { color: colors.text }]}>{example.title}</Text>
                <TouchableOpacity
                  style={[styles.tryItBtn, { backgroundColor: colors.primary }]}
                  onPress={() => onCodeExample?.(example.code, example.language || 'python')}
                >
                  <Text style={styles.tryItText}>Try it</Text>
                </TouchableOpacity>
              </View>
              <ScrollView horizontal showsHorizontalScrollIndicator={false}>
                <Text style={[styles.codeSnippet, { color: colors.text }]}>
                  {example.code?.substring(0, 500)}...
                </Text>
              </ScrollView>
            </View>
          ))}

          {weekContent.week?.exercises?.map((exercise: string, i: number) => (
            <View key={i} style={[styles.exerciseCard, { backgroundColor: colors.cardBackground, borderColor: colors.border }]}>
              <Text style={[styles.exerciseLabel, { color: colors.primary }]}>Exercise {i + 1}</Text>
              <Text style={[styles.exerciseText, { color: colors.text }]}>{exercise}</Text>
            </View>
          ))}
        </>
      )}
    </ScrollView>
  );

  return (
    <Modal visible={visible} animationType="slide" transparent={false}>
      <View style={[styles.container, { backgroundColor: colors.background }]}>
        {renderHeader()}
        
        {isLoading ? (
          <View style={styles.loadingContainer}>
            <ActivityIndicator size="large" color={colors.primary} />
            <Text style={[styles.loadingText, { color: colors.textSecondary }]}>Loading curriculum...</Text>
          </View>
        ) : (
          <>
            {viewMode === 'list' && renderCourseList()}
            {viewMode === 'course' && renderCourseDetails()}
            {viewMode === 'week' && renderWeekContent()}
          </>
        )}
      </View>
    </Modal>
  );
};

const styles = StyleSheet.create({
  container: { flex: 1, paddingTop: Platform.OS === 'ios' ? 50 : 30 },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 16, paddingBottom: 12, borderBottomWidth: 1 },
  closeBtn: { padding: 8 },
  backBtn: { padding: 8 },
  title: { fontSize: 18, fontWeight: 'bold', flex: 1, textAlign: 'center' },
  placeholder: { width: 40 },
  content: { flex: 1, padding: 16 },
  loadingContainer: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  loadingText: { marginTop: 12, fontSize: 14 },
  statsCard: { padding: 16, borderRadius: 12, borderWidth: 1, marginBottom: 20 },
  statsTitle: { fontSize: 18, fontWeight: 'bold', marginBottom: 12, textAlign: 'center' },
  statsRow: { flexDirection: 'row', justifyContent: 'space-around' },
  statItem: { alignItems: 'center' },
  statValue: { fontSize: 28, fontWeight: 'bold' },
  statLabel: { fontSize: 12 },
  sectionTitle: { fontSize: 16, fontWeight: 'bold', marginBottom: 12 },
  courseCard: { padding: 16, borderRadius: 12, borderWidth: 1, marginBottom: 12 },
  courseHeader: { flexDirection: 'row', alignItems: 'flex-start', marginBottom: 8 },
  courseIcon: { fontSize: 32, marginRight: 12 },
  courseInfo: { flex: 1 },
  courseCode: { fontSize: 12, fontWeight: '600', marginBottom: 2 },
  courseTitle: { fontSize: 16, fontWeight: 'bold' },
  levelBadge: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: 10 },
  levelText: { color: '#FFF', fontSize: 10, fontWeight: '600', textTransform: 'capitalize' },
  courseMeta: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  metaItem: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  metaText: { fontSize: 12 },
  courseDetailHeader: { padding: 20, borderRadius: 12, borderWidth: 1, marginBottom: 16, alignItems: 'center' },
  detailIcon: { fontSize: 48, marginBottom: 8 },
  detailCode: { fontSize: 14, fontWeight: '600' },
  detailTitle: { fontSize: 22, fontWeight: 'bold', textAlign: 'center', marginTop: 4 },
  detailSubtitle: { fontSize: 14, textAlign: 'center', marginTop: 4 },
  detailMeta: { flexDirection: 'row', gap: 8, marginTop: 12, flexWrap: 'wrap', justifyContent: 'center' },
  metaBadge: { paddingHorizontal: 12, paddingVertical: 6, borderRadius: 16 },
  metaBadgeText: { fontSize: 12, fontWeight: '600' },
  section: { padding: 16, borderRadius: 12, borderWidth: 1, marginBottom: 16 },
  sectionHeader: { fontSize: 16, fontWeight: 'bold', marginBottom: 8 },
  descText: { fontSize: 14, lineHeight: 20 },
  objectiveItem: { flexDirection: 'row', marginBottom: 6 },
  objectiveBullet: { fontSize: 14, fontWeight: 'bold', marginRight: 8 },
  objectiveText: { flex: 1, fontSize: 13, lineHeight: 18 },
  weekCard: { flexDirection: 'row', alignItems: 'center', padding: 12, borderRadius: 10, borderWidth: 1, marginBottom: 8 },
  weekNum: { width: 36, height: 36, borderRadius: 18, justifyContent: 'center', alignItems: 'center' },
  weekNumText: { color: '#FFF', fontSize: 14, fontWeight: 'bold' },
  weekInfo: { flex: 1, marginLeft: 12 },
  weekTitle: { fontSize: 14, fontWeight: '600' },
  weekTopics: { fontSize: 11, marginTop: 2 },
  exampleCard: { padding: 12, borderRadius: 8, borderWidth: 1, marginBottom: 8, flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  exampleTitle: { fontSize: 14, fontWeight: '500', flex: 1 },
  exampleLang: { fontSize: 11, fontWeight: '600' },
  weekHeader: { padding: 16, borderRadius: 12, borderWidth: 1, marginBottom: 16 },
  weekHeaderTitle: { fontSize: 20, fontWeight: 'bold', marginBottom: 12 },
  topicsList: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  topicChip: { paddingHorizontal: 10, paddingVertical: 5, borderRadius: 12 },
  topicText: { fontSize: 12, fontWeight: '500' },
  codeExampleCard: { padding: 16, borderRadius: 12, borderWidth: 1, marginBottom: 12 },
  codeExampleHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 },
  codeExampleTitle: { fontSize: 14, fontWeight: '600', flex: 1 },
  tryItBtn: { paddingHorizontal: 12, paddingVertical: 6, borderRadius: 6 },
  tryItText: { color: '#FFF', fontSize: 12, fontWeight: '600' },
  codeSnippet: { fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace', fontSize: 11, lineHeight: 16 },
  exerciseCard: { padding: 12, borderRadius: 8, borderWidth: 1, marginBottom: 8 },
  exerciseLabel: { fontSize: 12, fontWeight: '600', marginBottom: 4 },
  exerciseText: { fontSize: 13, lineHeight: 18 },
});

export default CurriculumBrowser;
