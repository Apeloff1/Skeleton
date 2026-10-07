import React, { useState, useEffect, useCallback } from 'react';
import { API_BASE } from '../../utils/apiBase';
import {
  View, Text, StyleSheet, TouchableOpacity, ScrollView, Modal,
  ActivityIndicator, SafeAreaView, Platform,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { ReadingVisualizer } from './ReadingVisualizer';
import { BookCover } from '../../components/BookCover';

import { apiFetch } from '../../utils/apiController';
const API_URL = API_BASE;

interface Props {
  visible: boolean;
  onClose: () => void;
}

export const ReadingLibraryModal: React.FC<Props> = ({ visible, onClose }) => {
  const [categories, setCategories] = useState<any[]>([]);
  const [books, setBooks] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const [selectedBook, setSelectedBook] = useState<any>(null);
  const [totalBooks, setTotalBooks] = useState(0);
  const [readerChapterIdx, setReaderChapterIdx] = useState<number | null>(null);

  const fetchCategories = useCallback(async () => {
    try {
      setLoading(true);
      const res = await apiFetch(`${API_URL}/api/academy/reading-library/categories`);
      const data = await res.json();
      setCategories(data.categories || []);
      setTotalBooks(data.total_books || 0);
    } catch (e) {
      console.error('Failed to fetch reading categories:', e);
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchBooks = useCallback(async (category?: string) => {
    try {
      setLoading(true);
      let url = `${API_URL}/api/academy/reading-library`;
      if (category) url += `?category=${category}`;
      const res = await apiFetch(url);
      const data = await res.json();
      setBooks(data.books || []);
      setSelectedCategory(category || null);
    } catch (e) {
      console.error('Failed to fetch books:', e);
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchBook = useCallback(async (bookId: string) => {
    try {
      setLoading(true);
      const res = await apiFetch(`${API_URL}/api/academy/reading-library/book/${bookId}`);
      const data = await res.json();
      setSelectedBook(data.book);
    } catch (e) {
      console.error('Failed to fetch book:', e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (visible) fetchCategories();
  }, [visible, fetchCategories]);

  const handleBack = () => {
    if (selectedBook) {
      setSelectedBook(null);
    } else if (selectedCategory) {
      setSelectedCategory(null);
      setBooks([]);
    } else {
      onClose();
    }
  };

  const DIFF_COLORS: Record<string, string> = {
    beginner: '#10B981', intermediate: '#3B82F6', advanced: '#F59E0B', expert: '#EF4444',
  };

  const renderCategories = () => (
    <ScrollView style={styles.content} showsVerticalScrollIndicator={false}>
      <View style={styles.heroCard}>
        <Ionicons name="book" size={40} color="#8B5CF6" />
        <Text style={styles.heroTitle}>Reading Library</Text>
        <Text style={styles.heroSub}>{totalBooks} essential books across {categories.length} domains</Text>
        <Text style={styles.heroDetail}>Every book a programmer should study — organized as interactive classes</Text>
      </View>
      {categories.map((cat) => (
        <TouchableOpacity
          key={cat.id}
          testID={`reading-cat-${cat.id}`}
          style={[styles.catCard, { borderLeftColor: cat.color || '#888' }]}
          onPress={() => fetchBooks(cat.id)}
        >
          <View style={[styles.catIcon, { backgroundColor: (cat.color || '#888') + '20' }]}>
            <Ionicons name={(cat.icon || 'book') as any} size={24} color={cat.color || '#888'} />
          </View>
          <View style={styles.catInfo}>
            <Text style={styles.catName}>{cat.name}</Text>
            <Text style={styles.catDesc} numberOfLines={1}>{cat.description}</Text>
            <Text style={styles.catStat}>{cat.book_count} books  |  {cat.total_hours} hours</Text>
          </View>
          <Ionicons name="chevron-forward" size={20} color="#6B7280" />
        </TouchableOpacity>
      ))}
    </ScrollView>
  );

  const renderBooks = () => (
    <ScrollView style={styles.content} showsVerticalScrollIndicator={false} contentContainerStyle={{ paddingBottom: 24 }}>
      {books.map((book) => (
        <TouchableOpacity
          key={book.id}
          testID={`reading-book-${book.id}`}
          style={styles.bookCard}
          onPress={() => fetchBook(book.id)}
          activeOpacity={0.85}
        >
          <BookCover
            title={book.title}
            author={book.author}
            seed={book.id}
            size="default"
          />
          <View style={styles.bookInfo}>
            <View style={styles.bookTop}>
              <Text style={styles.bookTitle} numberOfLines={2}>{book.title}</Text>
              <View style={[styles.diffBadge, { backgroundColor: (DIFF_COLORS[book.difficulty] || '#888') + '25' }]}>
                <Text style={[styles.diffText, { color: DIFF_COLORS[book.difficulty] || '#888' }]}>{book.difficulty}</Text>
              </View>
            </View>
            <Text style={styles.bookAuthor} numberOfLines={1}>by {book.author}</Text>
            <View style={styles.bookMeta}>
              <View style={styles.bookStat}>
                <Ionicons name="document-text" size={13} color="#94A3B8" />
                <Text style={styles.bookStatText}>{book.total_chapters} ch</Text>
              </View>
              <View style={styles.bookStat}>
                <Ionicons name="school" size={13} color="#94A3B8" />
                <Text style={styles.bookStatText}>{book.total_lessons} lessons</Text>
              </View>
              <View style={styles.bookStat}>
                <Ionicons name="time" size={13} color="#94A3B8" />
                <Text style={styles.bookStatText}>{book.estimated_hours}h</Text>
              </View>
            </View>
          </View>
        </TouchableOpacity>
      ))}
    </ScrollView>
  );

  const renderBookDetail = () => {
    if (!selectedBook) return null;
    return (
      <ScrollView style={styles.content} showsVerticalScrollIndicator={false}>
        <View style={styles.bookHeader}>
          <View style={{ flexDirection: 'row', gap: 16, alignItems: 'flex-start', marginBottom: 14 }}>
            <BookCover
              title={selectedBook.title}
              author={selectedBook.author}
              seed={selectedBook.id}
              size="large"
            />
            <View style={{ flex: 1, minWidth: 0 }}>
              <Text style={styles.bookDetailTitle} numberOfLines={3}>{selectedBook.title}</Text>
              <Text style={styles.bookDetailAuthor} numberOfLines={2}>by {selectedBook.author}</Text>
              <View style={[styles.diffBadge, { backgroundColor: (DIFF_COLORS[selectedBook.difficulty] || '#888') + '25', alignSelf: 'flex-start', marginTop: 8 }]}>
                <Text style={[styles.diffText, { color: DIFF_COLORS[selectedBook.difficulty] || '#888' }]}>{selectedBook.difficulty}</Text>
              </View>
            </View>
          </View>
          <Text style={styles.bookDetailDesc}>{selectedBook.description}</Text>
          <View style={styles.bookDetailStats}>
            <Text style={styles.bookDetailStat}>{selectedBook.total_chapters} chapters</Text>
            <Text style={styles.bookDetailStat}>{selectedBook.total_lessons} lessons</Text>
            <Text style={styles.bookDetailStat}>{selectedBook.estimated_hours} hours</Text>
          </View>
        </View>
        <Text style={styles.sectionTitle}>CHAPTERS — tap to read</Text>
        {(selectedBook.chapters || []).map((ch: any, idx: number) => (
          <TouchableOpacity
            key={ch.id}
            testID={`reading-chapter-${idx}`}
            style={styles.chapterCard}
            onPress={() => setReaderChapterIdx(idx)}
            activeOpacity={0.7}
          >
            <View style={styles.chapterNum}>
              <Text style={styles.chapterNumText}>{idx + 1}</Text>
            </View>
            <View style={styles.chapterInfo}>
              <Text style={styles.chapterName}>{ch.name}</Text>
              <Text style={styles.chapterLessons}>{ch.total_lessons} lessons • tap to open</Text>
            </View>
            <Ionicons name="chevron-forward" size={18} color="#64748B" />
          </TouchableOpacity>
        ))}
        <View style={{ height: 40 }} />
      </ScrollView>
    );
  };

  const getTitle = () => {
    if (selectedBook) return selectedBook.title;
    if (selectedCategory) {
      const cat = categories.find((c) => c.id === selectedCategory);
      return cat?.name || 'Books';
    }
    return 'Reading Library';
  };

  return (
    <Modal visible={visible} animationType="slide" onRequestClose={handleBack}>
      <SafeAreaView style={styles.container}>
        <View style={styles.header}>
          <TouchableOpacity testID="reading-back-btn" onPress={handleBack} style={styles.headerBtn}>
            <Ionicons name={selectedCategory || selectedBook ? 'arrow-back' : 'close'} size={24} color="#F8FAFC" />
          </TouchableOpacity>
          <Text style={styles.headerTitle} numberOfLines={1}>{getTitle()}</Text>
          <View style={{ width: 44 }} />
        </View>
        {loading ? (
          <View style={styles.loadingContainer}>
            <ActivityIndicator size="large" color="#8B5CF6" />
            <Text style={styles.loadingText}>Loading library...</Text>
          </View>
        ) : selectedBook ? renderBookDetail() : selectedCategory ? renderBooks() : renderCategories()}

        {/* Chapter reader — full Reading Visualizer with TTS + navigation */}
        {selectedBook && readerChapterIdx !== null && (
          <ReadingVisualizer
            visible={readerChapterIdx !== null}
            onClose={() => setReaderChapterIdx(null)}
            itemType="book"
            itemId={selectedBook.id}
            itemTitle={selectedBook.title}
            chapterIdx={readerChapterIdx}
            totalChapters={(selectedBook.chapters || []).length}
            onChangeChapter={(newIdx) => setReaderChapterIdx(newIdx)}
          />
        )}
      </SafeAreaView>
    </Modal>
  );
};

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0F172A' },
  header: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16, paddingTop: Platform.OS === 'ios' ? 52 : 18, paddingBottom: 12, backgroundColor: '#1E293B', borderBottomWidth: 1, borderBottomColor: '#334155' },
  headerBtn: { width: 44, height: 44, justifyContent: 'center', alignItems: 'center' },
  headerTitle: { flex: 1, fontSize: 18, fontWeight: '700', color: '#F8FAFC', textAlign: 'center' },
  content: { flex: 1, paddingHorizontal: 16 },
  loadingContainer: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  loadingText: { color: '#94A3B8', marginTop: 12 },
  heroCard: { alignItems: 'center', padding: 28, backgroundColor: '#1E293B', borderRadius: 16, marginTop: 16, borderWidth: 1, borderColor: '#8B5CF620' },
  heroTitle: { fontSize: 24, fontWeight: '800', color: '#F8FAFC', marginTop: 12 },
  heroSub: { fontSize: 14, color: '#94A3B8', marginTop: 4 },
  heroDetail: { fontSize: 12, color: '#64748B', marginTop: 8, textAlign: 'center' },
  catCard: { flexDirection: 'row', alignItems: 'center', padding: 16, backgroundColor: '#1E293B', borderRadius: 12, marginTop: 10, borderLeftWidth: 4 },
  catIcon: { width: 48, height: 48, borderRadius: 12, justifyContent: 'center', alignItems: 'center', marginRight: 14 },
  catInfo: { flex: 1 },
  catName: { fontSize: 15, fontWeight: '700', color: '#F8FAFC' },
  catDesc: { fontSize: 12, color: '#94A3B8', marginTop: 2 },
  catStat: { fontSize: 11, color: '#64748B', marginTop: 3 },
  bookCard: {
    flexDirection: 'row', gap: 14, padding: 14, backgroundColor: '#1E293B', borderRadius: 14, marginTop: 12,
    borderWidth: 1, borderColor: '#334155',
  },
  bookInfo: { flex: 1, minWidth: 0, justifyContent: 'space-between' },
  bookTop: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', gap: 8, marginBottom: 4 },
  bookTitle: { color: '#F8FAFC', fontSize: 15, fontWeight: '700', flex: 1, lineHeight: 19 },
  bookAuthor: { color: '#94A3B8', fontSize: 12, marginTop: 2 },
  bookMeta: { flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginTop: 8 },
  bookStat: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  bookStatText: { color: '#94A3B8', fontSize: 11, fontWeight: '600' },
  diffBadge: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6 },
  diffText: { fontSize: 10, fontWeight: '700', textTransform: 'uppercase' },
  bookHeader: { paddingTop: 20 },
  bookDetailTitle: { fontSize: 22, fontWeight: '800', color: '#F8FAFC' },
  bookDetailAuthor: { fontSize: 14, color: '#8B5CF6', marginTop: 4 },
  bookDetailDesc: { fontSize: 13, color: '#CBD5E1', marginTop: 12, lineHeight: 20 },
  bookDetailStats: { flexDirection: 'row', gap: 16, marginTop: 12 },
  bookDetailStat: { fontSize: 12, color: '#94A3B8', backgroundColor: '#334155', paddingHorizontal: 10, paddingVertical: 4, borderRadius: 6 },
  sectionTitle: { fontSize: 12, fontWeight: '700', color: '#64748B', letterSpacing: 1, marginTop: 24, marginBottom: 12 },
  chapterCard: { flexDirection: 'row', alignItems: 'center', padding: 14, backgroundColor: '#1E293B', borderRadius: 10, marginBottom: 8 },
  chapterNum: { width: 36, height: 36, borderRadius: 8, backgroundColor: '#334155', justifyContent: 'center', alignItems: 'center', marginRight: 12 },
  chapterNumText: { fontSize: 14, fontWeight: '700', color: '#F8FAFC' },
  chapterInfo: { flex: 1 },
  chapterName: { fontSize: 14, fontWeight: '600', color: '#F8FAFC' },
  chapterLessons: { fontSize: 11, color: '#94A3B8', marginTop: 2 },
});
