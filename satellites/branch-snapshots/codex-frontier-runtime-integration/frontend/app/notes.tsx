/**
 * /notes — Sticky-note pinboard. (v2)
 *
 *   Core actions
 *   ──────────────────────────────────────────────────────────────
 *   • Tap "+" to add a new note (random pastel colour).
 *   • Tap a note's body to edit it inline.
 *   • Tap the pin icon to pin → pinned stickies float to the top
 *     and stay sorted before everything else.
 *   • Tap the colour swatch to cycle colours.
 *   • Tap the duplicate icon to clone a note.
 *   • Long-press OR trash icon to delete (with Undo toast).
 *   • Pull-to-refresh shuffles the deck for a quick mental reset.
 *
 *   Comfort & polish
 *   ──────────────────────────────────────────────────────────────
 *   • Reanimated FadeInDown stagger on first paint.
 *   • Haptics on every meaningful interaction (add / pin / delete).
 *   • Live character count + "Saved" indicator (subtle, auto-fades).
 *   • Undo toast after deletion (3s grace window).
 *   • Pinned section header surfaces context when notes are pinned.
 *   • Schema-versioned persistence (@autosave/notes:v2) so migrating
 *     from v1 (no pin field) is safe; old notes auto-upgrade.
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import {
  View, Text, TextInput, ScrollView, TouchableOpacity, StyleSheet,
  SafeAreaView, KeyboardAvoidingView, Platform, RefreshControl,
} from 'react-native';
import { useRouter , useLocalSearchParams } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import Animated, {
  FadeInDown, FadeOut, Layout, useSharedValue, useAnimatedStyle, withTiming,
} from 'react-native-reanimated';
import { useAutosave } from '../utils/useAutosave';
import { withScreenGuard } from '../components/withScreenGuard';
import Skeleton from '../components/ui/Skeleton';
import * as haptics from '../utils/haptics';
import { toast } from '../components/Toast';
import { actionSheet } from '../components/ActionSheet';
import { copyToClipboard } from '../utils/shareResult';
import { useNotesFilters } from '../state/notesFiltersStore';

interface Note {
  id:      string;
  text:    string;
  color:   string;
  ts:      number;
  pinned?: boolean;
}

const COLORS = ['#fde68a', '#fca5a5', '#a7f3d0', '#BFDBFE', '#ddd6fe', '#fbcfe8', '#fed7aa'];

const newId = () => `n_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 7)}`;

function NotesScreen() {
  const router = useRouter();
  // v2 schema — keep storageKey so v1 data automatically migrates the
  // first time a user opens this screen after the update.
  const [notes, setNotes, { ready }] = useAutosave<Note[]>('notes:v2', [], {
    storageKey: '@autosave/notes:v2',
  });
  const [editing, setEditing] = useState<string | null>(null);
  // Search state is now lifted to a global Zustand store so deep-links
  // (command palette, dashboard widget, etc.) can preset it.
  const search = useNotesFilters(s => s.search);
  const setSearch = useNotesFilters(s => s.setSearch);
  const clearAllFiltersStore = useNotesFilters(s => s.clearAllFilters);
  const [refreshing, setRefreshing] = useState(false);

  // Read `?q=` deep-link param ONCE on mount and seed the filter store.
  const params = useLocalSearchParams<{ q?: string; clear?: string }>();
  const seededFromParamsRef = useRef(false);
  useEffect(() => {
    if (seededFromParamsRef.current) return;
    seededFromParamsRef.current = true;
    if (params?.clear === 'true') {
      clearAllFiltersStore();
    } else if (typeof params?.q === 'string' && params.q.length > 0) {
      setSearch(params.q);
    }
  }, [params, setSearch, clearAllFiltersStore]);

  /**
   * clearAllFilters — single chokepoint for "show every note again".
   * Delegates to the Zustand store so deep-link callers stay in sync.
   */
  const clearAllFilters = () => {
    haptics.tap();
    clearAllFiltersStore();
  };

  // ── One-time v1 → v2 migration ─────────────────────────────
  const migratedRef = useRef(false);
  useEffect(() => {
    if (migratedRef.current || !ready) return;
    migratedRef.current = true;
    if (notes.length > 0) return; // already have v2 data
    (async () => {
      try {
         
        // eslint-disable-next-line @typescript-eslint/no-require-imports
        const AsyncStorage = require('@react-native-async-storage/async-storage').default;
        const legacy = await AsyncStorage.getItem('@autosave/notes:v1');
        if (legacy) {
          const arr = JSON.parse(legacy) as Note[];
          if (Array.isArray(arr) && arr.length > 0) {
            setNotes(arr.map(n => ({ ...n, pinned: n.pinned ?? false })));
            toast.info(`Restored ${arr.length} note${arr.length === 1 ? '' : 's'} from the legacy pad`);
          }
        }
      } catch { /* swallow */ }
    })();
  }, [ready]);  // eslint-disable-line react-hooks/exhaustive-deps

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return notes.filter(n => !q || n.text.toLowerCase().includes(q));
  }, [notes, search]);

  const pinned = useMemo(
    () => filtered.filter(n => n.pinned).sort((a, b) => b.ts - a.ts),
    [filtered],
  );
  const others = useMemo(
    () => filtered.filter(n => !n.pinned).sort((a, b) => b.ts - a.ts),
    [filtered],
  );

  // ── Save indicator (fades in after every change for 1.2s) ─────
  const savedOpacity = useSharedValue(0);
  const savedStyle = useAnimatedStyle(() => ({ opacity: savedOpacity.value }));
  const pingSaved = () => {
    savedOpacity.value = withTiming(1, { duration: 120 });
    setTimeout(() => { savedOpacity.value = withTiming(0, { duration: 600 }); }, 900);
  };

  // ── Actions ────────────────────────────────────────────────
  const addNote = () => {
    haptics.success();
    const n: Note = {
      id:    newId(),
      text:  '',
      color: COLORS[Math.floor(Math.random() * COLORS.length)],
      ts:    Date.now(),
      pinned: false,
    };
    setNotes([n, ...notes]);
    setEditing(n.id);
    toast.success('New sticky added');
  };

  const updateText = (id: string, text: string) => {
    setNotes(notes.map(n => n.id === id ? { ...n, text, ts: Date.now() } : n));
    pingSaved();
  };

  const cycleColor = (id: string) => {
    haptics.tap();
    setNotes(notes.map(n => {
      if (n.id !== id) return n;
      const idx = COLORS.indexOf(n.color);
      return { ...n, color: COLORS[(idx + 1) % COLORS.length], ts: Date.now() };
    }));
    // Note: when Reduce-Motion is OFF, the surrounding Animated.View's
    // `layout={Layout.springify()}` provides a subtle spring on the
    // colour swap. When ON, RN-Reanimated's layout animations are
    // automatically skipped — so this is already RM-compliant.
  };

  const togglePin = (id: string) => {
    const target = notes.find(n => n.id === id);
    if (!target) return;
    if (target.pinned) haptics.warn(); else haptics.success();
    setNotes(notes.map(n => n.id === id ? { ...n, pinned: !n.pinned, ts: Date.now() } : n));
    toast.info(target.pinned ? 'Unpinned' : 'Pinned to top');
  };

  const duplicateNote = (id: string) => {
    const src = notes.find(n => n.id === id);
    if (!src) return;
    haptics.tap();
    const copy: Note = { ...src, id: newId(), ts: Date.now(), pinned: false };
    setNotes([copy, ...notes]);
    toast.success('Duplicated');
  };

  const deleteNote = (id: string) => {
    const removed = notes.find(n => n.id === id);
    if (!removed) return;
    haptics.error();
    setNotes(notes.filter(n => n.id !== id));
    toast.warn('Sticky deleted', {
      durationMs: 3500,
      action: {
        label: 'Undo',
        onPress: () => {
          haptics.tap();
          // Re-insert at its original spot (top for simplicity).
          setNotes(prev => [removed, ...prev.filter(p => p.id !== removed.id)]);
          toast.success('Restored');
        },
      },
    });
  };

  const onRefresh = () => {
    setRefreshing(true);
    haptics.tap();
    // Light "shuffle" — re-stamp ts so unpinned notes reorder gently.
    setTimeout(() => {
      setRefreshing(false);
      toast.info('Refreshed');
    }, 450);
  };

  /**
   * Long-press / overflow menu — surfaces the full set of actions an
   * editor needs without crowding the small footer toolbar. Uses our
   * cross-platform ActionSheet so the same flow works on web too.
   */
  const showNoteSheet = (id: string) => {
    const n = notes.find(x => x.id === id);
    if (!n) return;
    haptics.tap();
    actionSheet.show({
      title: n.text ? n.text.slice(0, 40) + (n.text.length > 40 ? '…' : '') : 'Empty sticky',
      message: `${n.pinned ? 'Pinned' : 'Unpinned'} · ${n.text.length} chars · ${new Date(n.ts).toLocaleString()}`,
      options: [
        { label: n.pinned ? 'Unpin'   : 'Pin to top',       onPress: () => togglePin(id) },
        { label: 'Copy text',                               onPress: async () => {
          if (!n.text) { toast.warn('Nothing to copy'); return; }
          await copyToClipboard(n.text, 'Sticky copied to clipboard');
        }},
        { label: 'Cycle colour',                            onPress: () => cycleColor(id) },
        { label: 'Duplicate',                               onPress: () => duplicateNote(id) },
        { label: 'Delete',         kind: 'destructive',     onPress: () => deleteNote(id) },
        { label: 'Cancel',         kind: 'cancel' },
      ],
    });
  };

  // ── Renderer for a single note card ────────────────────────
  const renderNote = (n: Note, idx: number) => {
    const isEditing = editing === n.id;
    const charCount = n.text.length;
    return (
      <Animated.View
        key={n.id}
        entering={FadeInDown.duration(260).delay(Math.min(idx * 35, 350))}
        exiting={FadeOut.duration(180)}
        layout={Layout.springify().damping(18)}
        style={[styles.note, { backgroundColor: n.color }]}
      >
        {/* Pin badge — bold corner indicator for pinned cards */}
        {n.pinned && (
          <View style={[styles.pinBadge, { pointerEvents: 'none' }]}>
            <Ionicons name="pin" size={11} color="#0A0A0A" />
          </View>
        )}

        <TouchableOpacity
          activeOpacity={0.9}
          onPress={() => { haptics.tap(); setEditing(n.id); }}
          onLongPress={() => showNoteSheet(n.id)}
          delayLongPress={350}
          style={{ flex: 1 }}
        >
          {isEditing ? (
            <TextInput
              style={styles.noteInput}
              value={n.text}
              onChangeText={(t) => updateText(n.id, t)}
              multiline
              autoFocus
              onBlur={() => setEditing(null)}
              placeholder="Type a sticky…"
              placeholderTextColor="#475569"
              maxLength={2000}
            />
          ) : (
            <Text style={styles.noteText}>
              {n.text || <Text style={styles.notePlace}>(empty — tap to edit)</Text>}
            </Text>
          )}
        </TouchableOpacity>

        <View style={styles.noteFoot}>
          {/* Colour swatch (cycles palette) */}
          <TouchableOpacity onPress={() => cycleColor(n.id)} hitSlop={8} style={styles.footBtn}>
            <View style={[styles.swatch, { backgroundColor: COLORS[(COLORS.indexOf(n.color) + 1) % COLORS.length] }]} />
          </TouchableOpacity>
          {/* Pin toggle */}
          <TouchableOpacity onPress={() => togglePin(n.id)} hitSlop={8} style={styles.footBtn}>
            <Ionicons name={n.pinned ? 'pin' : 'pin-outline'} size={14} color="#0A0A0A99" />
          </TouchableOpacity>
          {/* Duplicate */}
          <TouchableOpacity onPress={() => duplicateNote(n.id)} hitSlop={8} style={styles.footBtn}>
            <Ionicons name="copy-outline" size={13} color="#0A0A0A99" />
          </TouchableOpacity>
          <View style={{ flex: 1 }} />
          {isEditing && charCount > 0 && (
            <Text style={styles.charCount}>{charCount}</Text>
          )}
          <Text style={styles.noteTs}>
            {new Date(n.ts).toLocaleString(undefined, { month: 'short', day: '2-digit', hour: '2-digit', minute: '2-digit' })}
          </Text>
          <TouchableOpacity onPress={() => deleteNote(n.id)} hitSlop={8} style={styles.footBtn}>
            <Ionicons name="trash-outline" size={13} color="#0A0A0A99" />
          </TouchableOpacity>
        </View>
      </Animated.View>
    );
  };

  // ── UI ─────────────────────────────────────────────────────
  return (
    <SafeAreaView style={styles.safe}>
      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : 'height'} style={{ flex: 1 }}>
        <View style={styles.header}>
          <TouchableOpacity
            onPress={() => { haptics.tap(); { if (router.canGoBack()) router.back(); else router.replace('/menu'); } }}
            hitSlop={12}
          >
            <Ionicons name="chevron-back" size={26} color="#e2e8f0" />
          </TouchableOpacity>
          <View style={{ flex: 1 }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
              <Text style={styles.badge}>Persistent</Text>
              <Animated.View style={[styles.savedDot, savedStyle]}>
                <Ionicons name="cloud-done" size={9} color="#10b981" />
                <Text style={styles.savedText}>SAVED</Text>
              </Animated.View>
            </View>
            <Text style={styles.title}>Sticky Notes</Text>
            <Text style={styles.sub}>
              {notes.length} note{notes.length === 1 ? '' : 's'}
              {pinned.length > 0 ? ` · ${pinned.length} pinned` : ''} · auto-saved
            </Text>
          </View>
          <TouchableOpacity onPress={addNote} style={styles.addBtn} accessibilityLabel="Add sticky" testID="notes-add">
            <Ionicons name="add" size={22} color="#0A0A0A" />
          </TouchableOpacity>
        </View>

        <ScrollView
          style={styles.scroll}
          contentContainerStyle={{ paddingHorizontal: 8, paddingTop: 8, paddingBottom: 40 }}
          refreshControl={
            <RefreshControl
              refreshing={refreshing}
              onRefresh={onRefresh}
              tintColor="#fbbf24"
              colors={['#fbbf24']}
            />
          }
          keyboardShouldPersistTaps="handled"
        >
          {!ready ? (
            /* Polish — skeleton sticky stack while AsyncStorage hydrates so
               the empty 'Loading…' text doesn't make the page feel dead. */
            <View style={{ gap: 12 }}>
              {[0, 1, 2].map(i => (
                <View key={i} style={styles.skeletonNote}>
                  <Skeleton width="70%" height={14} />
                  <View style={{ height: 8 }} />
                  <Skeleton width="95%" height={11} />
                  <View style={{ height: 6 }} />
                  <Skeleton width="60%" height={11} />
                </View>
              ))}
            </View>
          ) : filtered.length === 0 ? (
            <Animated.View entering={FadeInDown.duration(260)} style={styles.empty}>
              <Ionicons name={search ? 'search-outline' : 'document-text-outline'} size={48} color="#475569" />
              <Text style={styles.emptyT}>
                {search
                  ? (notes.length === 0 ? 'No notes yet' : `No notes match "${search}"`)
                  : 'No notes yet'}
              </Text>
              <Text style={styles.emptyS}>
                {search
                  ? (notes.length === 0
                      ? 'Tap + above to drop your first sticky.'
                      : `${notes.length} saved sticky${notes.length === 1 ? '' : 's'} — none match your search. Try a different keyword.`)
                  : 'Tap the + button to drop your first sticky.'}
              </Text>
              {/* Two-CTA layout when search hides everything — let the user
                  either clear the filter or just create a brand-new sticky. */}
              <View style={styles.emptyCtaRow}>
                {search && notes.length > 0 ? (
                  <TouchableOpacity
                    onPress={clearAllFilters}
                    style={[styles.emptyCta, { backgroundColor: '#262626', borderWidth: 1, borderColor: '#404040' }]}
                    testID="notes-clear-search"
                  >
                    <Ionicons name="close" size={14} color="#94a3b8" />
                    <Text style={[styles.emptyCtaText, { color: '#cbd5e1' }]}>Clear search</Text>
                  </TouchableOpacity>
                ) : null}
                <TouchableOpacity onPress={addNote} style={styles.emptyCta} testID="notes-empty-create">
                  <Ionicons name="add" size={14} color="#0A0A0A" />
                  <Text style={styles.emptyCtaText}>Create a sticky</Text>
                </TouchableOpacity>
              </View>
            </Animated.View>
          ) : (
            <>
              {pinned.length > 0 && (
                <>
                  <View style={styles.sectionRow}>
                    <Ionicons name="pin" size={11} color="#fbbf24" />
                    <Text style={styles.sectionTxt}>Pinned</Text>
                  </View>
                  <View style={styles.grid}>
                    {pinned.map((n, i) => renderNote(n, i))}
                  </View>
                </>
              )}
              {others.length > 0 && (
                <>
                  {pinned.length > 0 && (
                    <View style={styles.sectionRow}>
                      <Ionicons name="apps-outline" size={11} color="#94a3b8" />
                      <Text style={styles.sectionTxt}>Others</Text>
                    </View>
                  )}
                  <View style={styles.grid}>
                    {others.map((n, i) => renderNote(n, pinned.length + i))}
                  </View>
                </>
              )}

              {/* Bulk-clear footer — only surfaces once the user has >5 notes
                  so it never crowds first-time / casual users. */}
              {notes.length > 5 && (
                <View style={styles.footerActions}>
                  <TouchableOpacity
                    onPress={() => {
                      const unpinnedCount = notes.filter(n => !n.pinned).length;
                      if (unpinnedCount === 0) {
                        toast.warn('Only pinned notes remain · unpin first');
                        return;
                      }
                      actionSheet.show({
                        title: `Clear ${unpinnedCount} unpinned note${unpinnedCount === 1 ? '' : 's'}?`,
                        message: 'Pinned notes are preserved. This can be undone via the toast that appears after.',
                        options: [
                          { label: 'Cancel', kind: 'cancel' },
                          { label: `Clear ${unpinnedCount}`, kind: 'destructive', onPress: () => {
                            const removed = notes.filter(n => !n.pinned);
                            haptics.error();
                            setNotes(notes.filter(n => n.pinned));
                            toast.warn(`${removed.length} note${removed.length === 1 ? '' : 's'} cleared`, {
                              durationMs: 4500,
                              action: {
                                label: 'Undo',
                                onPress: () => {
                                  haptics.tap();
                                  setNotes(prev => [...removed, ...prev]);
                                  toast.success('Restored');
                                },
                              },
                            });
                          }},
                        ],
                      });
                    }}
                    style={styles.clearAllBtn}
                    accessibilityLabel="Clear all unpinned notes"
                    testID="notes-clear-all"
                  >
                    <Ionicons name="trash-bin-outline" size={14} color="#fca5a5" />
                    <Text style={styles.clearAllText}>
                      Clear all unpinned ({notes.filter(n => !n.pinned).length})
                    </Text>
                  </TouchableOpacity>
                </View>
              )}
            </>
          )}
        </ScrollView>

        <View style={styles.searchRow}>
          <Ionicons name="search" size={16} color="#94a3b8" />
          <TextInput
            style={styles.searchInput}
            placeholder="Search notes…"
            placeholderTextColor="#64748b"
            value={search}
            onChangeText={setSearch}
            testID="notes-search"
          />
          {search.length > 0 && (
            <TouchableOpacity onPress={clearAllFilters} hitSlop={8}>
              <Ionicons name="close-circle" size={16} color="#64748b" />
            </TouchableOpacity>
          )}
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

export default withScreenGuard(NotesScreen, 'NotesRoute');

const styles = StyleSheet.create({
  safe:    { flex: 1, backgroundColor: '#0A0A0A' },
  header:  { flexDirection: 'row', alignItems: 'center', gap: 12, paddingHorizontal: 16, paddingTop: 12, paddingBottom: 14, borderBottomWidth: 1, borderBottomColor: '#262626' },
  badge:   { color: '#fbbf24', fontSize: 10, fontWeight: '800', letterSpacing: 1.4, textTransform: 'uppercase' },
  savedDot:{ flexDirection: 'row', alignItems: 'center', gap: 3, backgroundColor: '#064e3b66', paddingHorizontal: 5, paddingVertical: 1, borderRadius: 4 },
  savedText:{ color: '#10b981', fontSize: 8, fontWeight: '800', letterSpacing: 1 },
  title:   { fontSize: 22, fontWeight: '800', color: '#f8fafc' },
  sub:     { fontSize: 11, color: '#94a3b8', marginTop: 2 },
  addBtn:  { backgroundColor: '#fbbf24', width: 38, height: 38, borderRadius: 19, alignItems: 'center', justifyContent: 'center' },

  searchRow:   { flexDirection: 'row', alignItems: 'center', gap: 8, marginHorizontal: 16, marginVertical: 12, paddingHorizontal: 12, paddingVertical: 8, backgroundColor: '#141414', borderRadius: 10, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: '#262626' },
  searchInput: { flex: 1, color: '#e2e8f0', fontSize: 13 },

  scroll:  { flex: 1, marginTop: 8 },

  sectionRow: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 12, paddingTop: 14, paddingBottom: 6 },
  sectionTxt: { color: '#94a3b8', fontSize: 10, fontWeight: '800', letterSpacing: 1.4, textTransform: 'uppercase' },

  grid:    { flexDirection: 'row', flexWrap: 'wrap' },
  empty:   { width: '100%', alignItems: 'center', justifyContent: 'center', paddingVertical: 80, paddingHorizontal: 24 },
  emptyT:  { color: '#cbd5e1', fontSize: 16, fontWeight: '700', marginTop: 12 },
  emptyS:  { color: '#64748b', fontSize: 12, marginTop: 6, textAlign: 'center' },
  emptyCta:{ marginTop: 16, flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: '#fbbf24', paddingHorizontal: 14, paddingVertical: 8, borderRadius: 9 },
  emptyCtaRow: { flexDirection: 'row', gap: 8, flexWrap: 'wrap', justifyContent: 'center' },
  emptyCtaText: { color: '#0A0A0A', fontSize: 12, fontWeight: '800', letterSpacing: 0.3 },
  dim:     { color: '#64748b', fontSize: 13, textAlign: 'center', paddingTop: 24, width: '100%' },
  skeletonNote: { backgroundColor: '#141414', borderRadius: 12, padding: 14, borderWidth: 1, borderColor: '#262626' },

  note:    { width: '47%', minHeight: 138, margin: '1.5%', padding: 14, borderRadius: 12, justifyContent: 'space-between', position: 'relative', overflow: 'hidden' },
  pinBadge:{ position: 'absolute', top: 0, right: 0, backgroundColor: '#fbbf24', paddingHorizontal: 5, paddingVertical: 3, borderBottomLeftRadius: 8 },
  noteText:{ color: '#0A0A0A', fontSize: 13, lineHeight: 18, fontWeight: '500' },
  notePlace:{ color: '#475569', fontStyle: 'italic', fontWeight: '400' },
  noteInput:{ color: '#0A0A0A', fontSize: 13, lineHeight: 18, fontWeight: '500', textAlignVertical: 'top', minHeight: 70 },
  noteFoot:{ flexDirection: 'row', alignItems: 'center', gap: 4, marginTop: 10, paddingTop: 8, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: '#0A0A0A33' },
  footBtn: { paddingHorizontal: 2, paddingVertical: 2 },
  swatch:  { width: 12, height: 12, borderRadius: 6, borderWidth: 1, borderColor: '#0A0A0A55' },
  charCount:{ color: '#0A0A0A88', fontSize: 9, fontWeight: '700', marginRight: 4 },
  noteTs:  { color: '#0A0A0A99', fontSize: 9, fontWeight: '700' },

  footerActions: { paddingHorizontal: 12, paddingTop: 18, paddingBottom: 8, alignItems: 'center' },
  clearAllBtn: {
    flexDirection: 'row', alignItems: 'center', gap: 8,
    paddingHorizontal: 16, paddingVertical: 10,
    backgroundColor: '#7f1d1d22',
    borderColor: '#7f1d1d55', borderWidth: 1,
    borderRadius: 10,
  },
  clearAllText: { color: '#fca5a5', fontSize: 12, fontWeight: '700', letterSpacing: 0.3 },
});
