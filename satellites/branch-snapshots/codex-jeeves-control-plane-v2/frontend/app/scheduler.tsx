/**
 * Calendar • Clock • Scheduler
 * A self-contained productivity surface persisted in AsyncStorage.
 *
 * Three sections:
 *   1. Live Clock — local time, time zone, sunrise/sunset placeholder
 *   2. Calendar   — monthly grid with dot indicators for days that have events
 *   3. Scheduler  — list of events (title, date, time, notes) with add/edit/delete
 *
 * Events are stored under @codedock:scheduler:events as a JSON array.
 * No network. No backend. Works offline.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity,
  TextInput, Modal, Platform, KeyboardAvoidingView, Alert,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import AsyncStorage from '@react-native-async-storage/async-storage';
import {
  scheduleEventReminder,
  cancelEventReminder,
} from '../utils/notifications';
import { LinearGradient } from 'expo-linear-gradient';
import theme from '../theme/tokens';
import { Screen, AppHeader } from '../components/ui';
import { openModalFromRoute } from '../utils/openModalFromRoute';
import { toast } from '../components/Toast';

interface Event {
  id: string;
  title: string;
  date: string;  // YYYY-MM-DD
  time?: string; // HH:mm
  notes?: string;
  color?: string;
  /** Notification id for the scheduled reminder (null/undefined = no reminder). */
  reminderId?: string | null;
  /** Minutes before event to fire reminder. 0 = at event time. -1 = no reminder. */
  reminderLeadMin?: number;
}

// Common lead-time presets shown in the editor.
const REMINDER_PRESETS: { label: string; value: number }[] = [
  { label: 'Off', value: -1 },
  { label: 'At time', value: 0 },
  { label: '10 min', value: 10 },
  { label: '1 hour', value: 60 },
  { label: '1 day', value: 24 * 60 },
];

const STORAGE_KEY = '@codedock:scheduler:events';

const DAY_NAMES = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const MONTH_NAMES = ['January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December'];

const COLORS = [theme.colors.primary, '#10B981', '#F59E0B', '#EF4444', '#8B5CF6', '#8B5CF6', '#3B82F6', '#F97316'];

function pad2(n: number) { return n.toString().padStart(2, '0'); }
function ymd(d: Date) { return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`; }

export default function SchedulerScreen() {
  const router = useRouter();
  const [now, setNow] = useState(new Date());
  const [events, setEvents] = useState<Event[]>([]);
  const [viewMonth, setViewMonth] = useState(new Date());
  const [selectedDate, setSelectedDate] = useState<string>(ymd(new Date()));
  const [editorOpen, setEditorOpen] = useState(false);
  const [editing, setEditing] = useState<Event | null>(null);

  // Live clock — update every second
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);

  // Load events from AsyncStorage once
  useEffect(() => {
    AsyncStorage.getItem(STORAGE_KEY).then((raw) => {
      if (raw) {
        try { setEvents(JSON.parse(raw)); } catch {}
      }
    });
  }, []);

  const persist = useCallback(async (next: Event[]) => {
    setEvents(next);
    try { await AsyncStorage.setItem(STORAGE_KEY, JSON.stringify(next)); } catch {}
  }, []);

  const monthGrid = useMemo(() => {
    const y = viewMonth.getFullYear();
    const m = viewMonth.getMonth();
    const first = new Date(y, m, 1);
    const offset = first.getDay();
    const daysInMonth = new Date(y, m + 1, 0).getDate();
    const cells: { y: number; m: number; d: number; key: string; inMonth: boolean }[] = [];
    // Previous month tail
    const prevDays = new Date(y, m, 0).getDate();
    for (let i = offset - 1; i >= 0; i--) {
      const d = prevDays - i;
      cells.push({ y: m === 0 ? y - 1 : y, m: m === 0 ? 11 : m - 1, d, key: `prev-${d}`, inMonth: false });
    }
    for (let d = 1; d <= daysInMonth; d++) cells.push({ y, m, d, key: `cur-${d}`, inMonth: true });
    // Next month head — pad to multiple of 7
    while (cells.length % 7 !== 0) {
      const d = cells.length - (offset + daysInMonth) + 1;
      cells.push({ y: m === 11 ? y + 1 : y, m: m === 11 ? 0 : m + 1, d, key: `next-${d}`, inMonth: false });
    }
    return cells;
  }, [viewMonth]);

  const eventsByDate = useMemo(() => {
    const map: Record<string, Event[]> = {};
    for (const e of events) (map[e.date] = map[e.date] || []).push(e);
    return map;
  }, [events]);

  const eventsForSelected = eventsByDate[selectedDate] || [];

  const openCreate = useCallback(() => {
    setEditing({ id: '', title: '', date: selectedDate, time: '', notes: '', color: COLORS[0], reminderLeadMin: 0 });
    setEditorOpen(true);
  }, [selectedDate]);

  const openEdit = useCallback((e: Event) => {
    setEditing({ ...e, reminderLeadMin: e.reminderLeadMin ?? (e.reminderId ? 0 : -1) });
    setEditorOpen(true);
  }, []);

  const saveEvent = useCallback(async () => {
    if (!editing) return;
    if (!editing.title.trim()) {
      toast.warn('Please give your event a title.');
      return;
    }
    // ── 1. Cancel any prior reminder owned by this event row.
    const prev = editing.id ? events.find(e => e.id === editing.id) : null;
    if (prev?.reminderId) await cancelEventReminder(prev.reminderId);

    // ── 2. Schedule a fresh reminder if the user picked one and the
    //       computed fire-time is still in the future.
    let reminderId: string | null = null;
    const lead = editing.reminderLeadMin ?? -1;
    if (lead >= 0) {
      reminderId = await scheduleEventReminder({
        title: editing.title.trim(),
        body: editing.notes?.trim() || `${editing.date}${editing.time ? ' • ' + editing.time : ''}`,
        date: editing.date,
        time: editing.time,
        leadMinutes: lead,
        data: { eventId: editing.id || `pending` },
      });
    }

    // ── 3. Persist.
    const merged: Event = { ...editing, reminderId };
    let next: Event[];
    if (editing.id) {
      next = events.map(e => (e.id === editing.id ? merged : e));
    } else {
      next = [...events, { ...merged, id: `e_${Date.now()}_${Math.floor(Math.random() * 1000)}` }];
    }
    await persist(next);
    setEditorOpen(false);
    setEditing(null);
  }, [editing, events, persist]);

  const deleteEvent = useCallback(async (id: string) => {
    Alert.alert('Delete event?', '', [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Delete', style: 'destructive',
        onPress: async () => {
          const target = events.find(e => e.id === id);
          if (target?.reminderId) await cancelEventReminder(target.reminderId);
          await persist(events.filter(e => e.id !== id));
        },
      },
    ]);
  }, [events, persist]);

  const todayKey = ymd(now);
  const upcoming = useMemo(() => {
    return [...events]
      .filter(e => e.date >= todayKey)
      .sort((a, b) => (a.date + (a.time || '')).localeCompare(b.date + (b.time || '')))
      .slice(0, 5);
  }, [events, todayKey]);

  return (
    <Screen edges={['top']}>
      <LinearGradient
        colors={['#10B98122', '#3B82F622', 'transparent'] as any}
        start={{ x: 0.2, y: 0 }}
        end={{ x: 0.9, y: 0.6 }}
        style={[{ position: 'absolute', top: 0, left: 0, right: 0, height: 240 }, { pointerEvents: 'none' }]}
      />
      <AppHeader
        title="Calendar & Scheduler"
        onBack={() => router.back()}
        right={
          <TouchableOpacity onPress={openCreate} hitSlop={theme.hitSlop.md} style={{ width: 44, height: 44, justifyContent: 'center', alignItems: 'center', borderRadius: theme.radii.md, backgroundColor: theme.colors.primarySoft, borderWidth: 1, borderColor: theme.colors.primary + '44' }}>
            <Ionicons name="add" size={20} color={theme.colors.primary} />
          </TouchableOpacity>
        }
      />

      <ScrollView contentContainerStyle={{ padding: 16, paddingBottom: 80 }}>
        {/* ─── LIVE CLOCK ─── */}
        <View style={s.clockCard}>
          <Text style={s.clockTime}>
            {pad2(now.getHours())}<Text style={s.clockSep}>:</Text>{pad2(now.getMinutes())}<Text style={s.clockSec}>:{pad2(now.getSeconds())}</Text>
          </Text>
          <Text style={s.clockDate}>{DAY_NAMES[now.getDay()]}, {MONTH_NAMES[now.getMonth()]} {now.getDate()}, {now.getFullYear()}</Text>
          <View style={s.clockMeta}>
            <View style={s.clockChip}><Ionicons name="time" size={11} color="#3B82F6" /><Text style={s.clockChipText}>{Intl.DateTimeFormat().resolvedOptions().timeZone || 'Local TZ'}</Text></View>
            <View style={s.clockChip}><Ionicons name="calendar" size={11} color="#10B981" /><Text style={s.clockChipText}>Week {Math.ceil(((now.getTime() - new Date(now.getFullYear(), 0, 1).getTime()) / 86400000 + new Date(now.getFullYear(), 0, 1).getDay() + 1) / 7)}</Text></View>
            <View style={s.clockChip}><Ionicons name="star" size={11} color="#F59E0B" /><Text style={s.clockChipText}>Day {Math.ceil((now.getTime() - new Date(now.getFullYear(), 0, 1).getTime()) / 86400000)} of yr</Text></View>
          </View>
        </View>

        {/* ─── UPCOMING ─── */}
        {upcoming.length > 0 && (
          <View style={s.section}>
            <View style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 8 }}>
              <Text style={[s.sectionTitle, { flex: 1, marginBottom: 0 }]}>Upcoming</Text>
              <TouchableOpacity
                onPress={() => openModalFromRoute(router, 'myProgress')}
                style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}
              >
                <Ionicons name="analytics" size={12} color="#A78BFA" />
                <Text style={{ color: '#A78BFA', fontSize: 11, fontWeight: '700' }}>Progress</Text>
              </TouchableOpacity>
            </View>
            {upcoming.map(e => (
              <TouchableOpacity key={e.id} style={s.eventRow} onPress={() => openEdit(e)} activeOpacity={0.7}>
                <View style={[s.eventDot, { backgroundColor: e.color || theme.colors.primary }]} />
                <View style={{ flex: 1 }}>
                  <Text style={s.eventTitle}>{e.title}</Text>
                  <Text style={s.eventSub}>{e.date}{e.time ? ` • ${e.time}` : ''}</Text>
                </View>
                <Ionicons name="chevron-forward" size={16} color="#64748B" />
              </TouchableOpacity>
            ))}
          </View>
        )}

        {/* ─── CALENDAR GRID ─── */}
        <View style={s.section}>
          <View style={s.monthNav}>
            <TouchableOpacity
              onPress={() => {
                // eslint-disable-next-line @typescript-eslint/no-require-imports
    try { require('../utils/haptics').default.tap(); } catch {}
                setViewMonth(new Date(viewMonth.getFullYear(), viewMonth.getMonth() - 1, 1));
              }}
              hitSlop={theme.hitSlop.md}
              style={s.monthNavBtn}
              accessibilityLabel="Previous month"
            >
              <Ionicons name="chevron-back" size={22} color="#3B82F6" />
            </TouchableOpacity>
            <TouchableOpacity
              onPress={() => {
                // eslint-disable-next-line @typescript-eslint/no-require-imports
    try { require('../utils/haptics').default.tap(); } catch {}
                const now = new Date();
                setViewMonth(new Date(now.getFullYear(), now.getMonth(), 1));
                setSelectedDate(`${now.getFullYear()}-${pad2(now.getMonth()+1)}-${pad2(now.getDate())}`);
              }}
              hitSlop={theme.hitSlop.sm}
              style={s.monthTitleWrap}
              accessibilityLabel="Jump to today"
            >
              <Text style={s.monthTitle}>{MONTH_NAMES[viewMonth.getMonth()]} {viewMonth.getFullYear()}</Text>
              <Text style={s.monthHint}>tap for today</Text>
            </TouchableOpacity>
            <TouchableOpacity
              onPress={() => {
                // eslint-disable-next-line @typescript-eslint/no-require-imports
    try { require('../utils/haptics').default.tap(); } catch {}
                setViewMonth(new Date(viewMonth.getFullYear(), viewMonth.getMonth() + 1, 1));
              }}
              hitSlop={theme.hitSlop.md}
              style={s.monthNavBtn}
              accessibilityLabel="Next month"
            >
              <Ionicons name="chevron-forward" size={22} color="#3B82F6" />
            </TouchableOpacity>
          </View>
          <View style={s.weekRow}>
            {DAY_NAMES.map(d => <Text key={d} style={s.weekDay}>{d}</Text>)}
          </View>
          <View style={s.grid}>
            {monthGrid.map(cell => {
              const k = `${cell.y}-${pad2(cell.m + 1)}-${pad2(cell.d)}`;
              const isToday = k === todayKey;
              const isSelected = k === selectedDate;
              const hasEvents = (eventsByDate[k] || []).length > 0;
              return (
                <TouchableOpacity
                  key={cell.key}
                  style={[s.cell, isSelected && s.cellSelected, isToday && s.cellToday]}
                  onPress={() => { setSelectedDate(k); }}
                  activeOpacity={0.7}
                >
                  <Text style={[
                    s.cellText,
                    !cell.inMonth && s.cellTextDim,
                    isSelected && s.cellTextSelected,
                    isToday && s.cellTextToday,
                  ]}>{cell.d}</Text>
                  {hasEvents && <View style={[s.cellDot, { backgroundColor: isSelected ? '#fff' : theme.colors.info }]} />}
                </TouchableOpacity>
              );
            })}
          </View>
        </View>

        {/* ─── EVENTS FOR SELECTED DATE ─── */}
        <View style={s.section}>
          <View style={s.sectionHead}>
            <Text style={s.sectionTitle}>{selectedDate}</Text>
            <TouchableOpacity onPress={openCreate} style={s.addBtn}>
              <Ionicons name="add" size={14} color="#fff" />
              <Text style={s.addBtnText}>Add Event</Text>
            </TouchableOpacity>
          </View>
          {eventsForSelected.length === 0 ? (
            <Text style={s.emptyText}>No events scheduled for this day.</Text>
          ) : (
            eventsForSelected.map(e => (
              <View key={e.id} style={s.eventRow}>
                <View style={[s.eventDot, { backgroundColor: e.color || theme.colors.primary }]} />
                <TouchableOpacity style={{ flex: 1 }} onPress={() => openEdit(e)} activeOpacity={0.7}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                    <Text style={s.eventTitle}>{e.title}</Text>
                    {e.reminderId ? <Ionicons name="notifications" size={11} color="#10B981" /> : null}
                  </View>
                  {e.time ? <Text style={s.eventSub}>{e.time}</Text> : null}
                  {e.notes ? <Text style={s.eventNotes} numberOfLines={2}>{e.notes}</Text> : null}
                </TouchableOpacity>
                <TouchableOpacity onPress={() => deleteEvent(e.id)} hitSlop={{ top: 8, left: 8, right: 8, bottom: 8 }}>
                  <Ionicons name="trash-outline" size={16} color="#EF4444" />
                </TouchableOpacity>
              </View>
            ))
          )}
        </View>
      </ScrollView>

      {/* ─── EVENT EDITOR ─── */}
      <Modal visible={editorOpen} animationType="slide" transparent onRequestClose={() => setEditorOpen(false)}>
        <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : 'height'} style={s.modalOverlay}>
          <View style={s.modalCard}>
            <View style={s.modalHeader}>
              <Text style={s.modalTitle}>{editing?.id ? 'Edit Event' : 'New Event'}</Text>
              <TouchableOpacity onPress={() => setEditorOpen(false)}>
                <Ionicons name="close" size={22} color="#94A3B8" />
              </TouchableOpacity>
            </View>
            <ScrollView contentContainerStyle={{ padding: 16 }} keyboardShouldPersistTaps="handled">
              <Text style={s.fieldLabel}>Title</Text>
              <TextInput
                style={s.input}
                placeholder="Meeting, study session, deadline…"
                placeholderTextColor="#475569"
                value={editing?.title || ''}
                onChangeText={t => editing && setEditing({ ...editing, title: t })}
              />
              <Text style={s.fieldLabel}>Date (YYYY-MM-DD)</Text>
              <TextInput
                style={s.input}
                placeholder="2026-05-13"
                placeholderTextColor="#475569"
                value={editing?.date || ''}
                onChangeText={t => editing && setEditing({ ...editing, date: t })}
              />
              <Text style={s.fieldLabel}>Time (HH:mm — optional)</Text>
              <TextInput
                style={s.input}
                placeholder="14:30"
                placeholderTextColor="#475569"
                value={editing?.time || ''}
                onChangeText={t => editing && setEditing({ ...editing, time: t })}
              />
              <Text style={s.fieldLabel}>Notes (optional)</Text>
              <TextInput
                style={[s.input, { minHeight: 80, textAlignVertical: 'top' }]}
                placeholder="Anything to remember…"
                placeholderTextColor="#475569"
                value={editing?.notes || ''}
                onChangeText={t => editing && setEditing({ ...editing, notes: t })}
                multiline
              />
              <Text style={s.fieldLabel}>Color</Text>
              <View style={s.colorRow}>
                {COLORS.map(c => (
                  <TouchableOpacity
                    key={c}
                    style={[s.colorDot, { backgroundColor: c, borderColor: editing?.color === c ? '#fff' : 'transparent' }]}
                    onPress={() => editing && setEditing({ ...editing, color: c })}
                  />
                ))}
              </View>
              <Text style={s.fieldLabel}>Reminder {Platform.OS === 'web' ? '(mobile only)' : ''}</Text>
              <View style={s.reminderRow}>
                {REMINDER_PRESETS.map(p => {
                  const active = (editing?.reminderLeadMin ?? -1) === p.value;
                  return (
                    <TouchableOpacity
                      key={p.value}
                      style={[s.reminderChip, active && s.reminderChipActive]}
                      onPress={() => editing && setEditing({ ...editing, reminderLeadMin: p.value })}
                      disabled={Platform.OS === 'web'}
                      activeOpacity={0.7}
                    >
                      {p.value === -1 && <Ionicons name="notifications-off-outline" size={12} color={active ? '#fff' : theme.colors.textMuted} />}
                      {p.value === 0 && <Ionicons name="alarm-outline" size={12} color={active ? '#fff' : theme.colors.textMuted} />}
                      {p.value > 0 && <Ionicons name="time-outline" size={12} color={active ? '#fff' : theme.colors.textMuted} />}
                      <Text style={[s.reminderChipText, active && s.reminderChipTextActive]}>{p.label}</Text>
                    </TouchableOpacity>
                  );
                })}
              </View>
              {editing?.reminderId ? (
                <Text style={s.reminderHint}>✓ Reminder scheduled</Text>
              ) : null}
              <TouchableOpacity style={s.saveBtn} onPress={saveEvent} activeOpacity={0.8}>
                <Ionicons name="checkmark" size={18} color="#fff" />
                <Text style={s.saveBtnText}>{editing?.id ? 'Update Event' : 'Create Event'}</Text>
              </TouchableOpacity>
            </ScrollView>
          </View>
        </KeyboardAvoidingView>
      </Modal>
    </Screen>
  );
}

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: theme.colors.bg },
  header: { flexDirection: 'row', alignItems: 'center', padding: 14, backgroundColor: theme.colors.bgElevated, borderBottomWidth: 1, borderBottomColor: theme.colors.border },
  hdrBtn: { width: 44, height: 44, justifyContent: 'center', alignItems: 'center' },
  hdrTitle: { flex: 1, textAlign: 'center', fontSize: 17, fontWeight: '700', color: theme.colors.text },
  clockCard: { backgroundColor: theme.colors.bgElevated, borderRadius: 14, padding: 20, marginBottom: 16, borderWidth: 1, borderColor: theme.colors.border, alignItems: 'center' },
  clockTime: { fontSize: 48, color: theme.colors.text, fontWeight: '200', letterSpacing: 2, fontVariant: ['tabular-nums'] },
  clockSep: { color: theme.colors.info },
  clockSec: { fontSize: 22, color: theme.colors.textMuted },
  clockDate: { color: theme.colors.text, fontSize: 14, marginTop: 8, fontWeight: '600' },
  clockMeta: { flexDirection: 'row', marginTop: 12, gap: 6, flexWrap: 'wrap', justifyContent: 'center' },
  clockChip: { flexDirection: 'row', alignItems: 'center', backgroundColor: theme.colors.bg, borderRadius: 999, paddingHorizontal: 10, paddingVertical: 4, gap: 4, borderWidth: 1, borderColor: theme.colors.border },
  clockChipText: { color: theme.colors.textMuted, fontSize: 11, fontWeight: '600' },
  section: { backgroundColor: theme.colors.bgElevated, borderRadius: 12, padding: 14, marginBottom: 12, borderWidth: 1, borderColor: theme.colors.border },
  sectionHead: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 },
  sectionTitle: { color: theme.colors.text, fontSize: 14, fontWeight: '700' },
  addBtn: { flexDirection: 'row', alignItems: 'center', backgroundColor: theme.colors.primary, borderRadius: 6, paddingHorizontal: 10, paddingVertical: 6, gap: 4 },
  addBtnText: { color: '#fff', fontSize: 11, fontWeight: '700' },
  monthNav: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 },
  monthNavBtn: {
    width: 40, height: 40,
    borderRadius: 20,
    backgroundColor: '#3B82F615',
    borderWidth: 1, borderColor: '#3B82F633',
    justifyContent: 'center', alignItems: 'center',
  },
  monthTitleWrap: { alignItems: 'center', flex: 1 },
  monthTitle: { color: theme.colors.text, fontSize: 16, fontWeight: '700' },
  monthHint:  { color: theme.colors.textDim, fontSize: 9, marginTop: 2, fontWeight: '700', letterSpacing: 0.5, textTransform: 'uppercase' },
  weekRow: { flexDirection: 'row', marginBottom: 4 },
  weekDay: { flex: 1, textAlign: 'center', color: theme.colors.textDim, fontSize: 11, fontWeight: '700', textTransform: 'uppercase' },
  grid: { flexDirection: 'row', flexWrap: 'wrap' },
  cell: { width: '14.2857%', aspectRatio: 1, justifyContent: 'center', alignItems: 'center', borderRadius: 6 },
  cellSelected: { backgroundColor: theme.colors.primary },
  cellToday: { borderWidth: 1, borderColor: theme.colors.info },
  cellText: { color: theme.colors.text, fontSize: 13, fontWeight: '600' },
  cellTextDim: { color: '#475569' },
  cellTextSelected: { color: '#fff', fontWeight: '800' },
  cellTextToday: { color: theme.colors.info, fontWeight: '800' },
  cellDot: { width: 4, height: 4, borderRadius: 2, marginTop: 2 },
  eventRow: { flexDirection: 'row', alignItems: 'center', backgroundColor: theme.colors.bg, borderRadius: 8, padding: 10, marginBottom: 6, borderWidth: 1, borderColor: theme.colors.border, gap: 10 },
  eventDot: { width: 8, height: 8, borderRadius: 4 },
  eventTitle: { color: theme.colors.text, fontSize: 13, fontWeight: '700' },
  eventSub: { color: theme.colors.textMuted, fontSize: 11, marginTop: 2 },
  eventNotes: { color: theme.colors.textDim, fontSize: 11, marginTop: 4, fontStyle: 'italic' },
  emptyText: { color: theme.colors.textDim, fontSize: 12, fontStyle: 'italic', textAlign: 'center', paddingVertical: 16 },
  modalOverlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.7)', justifyContent: 'flex-end' },
  modalCard: { backgroundColor: theme.colors.bg, borderTopLeftRadius: 18, borderTopRightRadius: 18, maxHeight: '90%', borderWidth: 1, borderColor: theme.colors.border },
  modalHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', padding: 14, borderBottomWidth: 1, borderBottomColor: theme.colors.bgElevated },
  modalTitle: { color: theme.colors.text, fontSize: 16, fontWeight: '700' },
  fieldLabel: { color: theme.colors.textMuted, fontSize: 11, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 6, marginTop: 12 },
  input: { backgroundColor: theme.colors.bgElevated, borderRadius: 8, padding: 12, color: theme.colors.text, fontSize: 14, borderWidth: 1, borderColor: theme.colors.border },
  colorRow: { flexDirection: 'row', gap: 8, marginTop: 4 },
  colorDot: { width: 30, height: 30, borderRadius: 15, borderWidth: 2 },
  reminderRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginTop: 4 },
  reminderChip: { flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: theme.colors.bgElevated, borderRadius: 999, paddingHorizontal: 10, paddingVertical: 6, borderWidth: 1, borderColor: theme.colors.border },
  reminderChipActive: { backgroundColor: theme.colors.primary, borderColor: theme.colors.info },
  reminderChipText: { color: theme.colors.textMuted, fontSize: 11, fontWeight: '700' },
  reminderChipTextActive: { color: '#fff' },
  reminderHint: { color: '#10B981', fontSize: 11, marginTop: 6, fontWeight: '700' },
  saveBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', backgroundColor: theme.colors.primary, borderRadius: 10, paddingVertical: 14, marginTop: 20, gap: 8 },
  saveBtnText: { color: '#fff', fontWeight: '800', fontSize: 14 },
});
