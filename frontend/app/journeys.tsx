/**
 * Guided product journeys. This is navigation state only; it does not assert
 * backend completion, duplicate authoritative project state or trigger work.
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator, SafeAreaView, ScrollView, StyleSheet,
  Text, TextInput, TouchableOpacity, View, useWindowDimensions,
} from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import api from '../src/utils/apiClient';
import { safeGetItem, safeSetItem } from '../utils/safeStorage';
import {
  PRODUCT_JOURNEYS, initialJourneySession, journeyById, journeyStepHref,
  nextUnopened, normalizeJourneySession, recordJourneyOpen, validBuildId,
} from '../src/product/journeyCatalog';
import type { JourneySession, JourneyStep } from '../src/product/journeyCatalog';

const SESSION_KEY = '@product:journeys:v1';
type RecentBuild = { id: string; title: string; status: string };

function parseRecentBuilds(response: unknown): RecentBuild[] {
  if (!response || typeof response !== 'object') return [];
  const item = response as Record<string, unknown>;
  const rows = [item.items, item.playables, item.games].find(Array.isArray);
  if (!Array.isArray(rows)) return [];
  const seen = new Set<string>();
  const result: RecentBuild[] = [];
  for (const row of rows) {
    if (!row || typeof row !== 'object') continue;
    const build = row as Record<string, unknown>;
    const id = validBuildId(build.playable_id ?? build.id);
    if (!id || seen.has(id)) continue;
    seen.add(id);
    result.push({
      id,
      title: typeof build.title === 'string' && build.title.trim()
        ? build.title.trim().slice(0, 100) : 'Untitled build',
      status: typeof build.status === 'string'
        ? build.status.slice(0, 36) : 'Status unavailable',
    });
    if (result.length >= 8) break;
  }
  return result;
}

export default function JourneysRoute() {
  const router = useRouter();
  const params = useLocalSearchParams<{ game?: string | string[]; workflow?: string | string[] }>();
  const requestedGame = Array.isArray(params.game) ? params.game[0] : params.game;
  const requestedWorkflow = Array.isArray(params.workflow) ? params.workflow[0] : params.workflow;
  const [session, setSession] = useState<JourneySession | null>(null);
  const current = useRef<JourneySession>(initialJourneySession());
  const writes = useRef<Promise<void>>(Promise.resolve());
  const [buildId, setBuildId] = useState(() => validBuildId(requestedGame));
  const [builds, setBuilds] = useState<RecentBuild[]>([]);
  const [loadingBuilds, setLoadingBuilds] = useState(false);
  const [buildError, setBuildError] = useState(false);
  const [filter, setFilter] = useState('');
  const [confirmReset, setConfirmReset] = useState(false);
  const { width } = useWindowDimensions();
  const wide = width >= 780;

  const save = useCallback((next: JourneySession) => {
    current.current = next;
    setSession(next);
    // Serialize writes so rapid taps cannot reorder the saved last-opened step.
    writes.current = writes.current.catch(() => {}).then(async () => {
      await safeSetItem(SESSION_KEY, JSON.stringify(next));
    });
  }, []);

  useEffect(() => {
    let active = true;
    void (async () => {
      const raw = await safeGetItem(SESSION_KEY);
      if (!active) return;
      let restored: unknown;
      try { restored = raw ? JSON.parse(raw) : null; } catch { restored = null; }
      const next = normalizeJourneySession(restored);
      if (requestedWorkflow && journeyById(requestedWorkflow)) next.selected = requestedWorkflow;
      current.current = next;
      setSession(next);
    })();
    return () => { active = false; };
  }, [requestedWorkflow]);

  useEffect(() => {
    const id = validBuildId(requestedGame);
    if (id) setBuildId(id);
  }, [requestedGame]);

  const refreshBuilds = useCallback(async (signal?: AbortSignal) => {
    setLoadingBuilds(true);
    setBuildError(false);
    try {
      const result = await api.get<unknown>('/api/playable/list?limit=8', { signal, timeoutMs: 8_000, retries: 0 });
      if (signal?.aborted) return;
      if (result.ok) setBuilds(parseRecentBuilds(result.data));
      else setBuildError(true);
    } catch {
      if (!signal?.aborted) setBuildError(true);
    } finally {
      if (!signal?.aborted) setLoadingBuilds(false);
    }
  }, []);

  useEffect(() => {
    const controller = typeof AbortController !== 'undefined' ? new AbortController() : null;
    void refreshBuilds(controller?.signal);
    return () => controller?.abort();
  }, [refreshBuilds]);

  const choose = useCallback((id: string) => {
    if (!journeyById(id)) return;
    save({ ...current.current, selected: id });
    setConfirmReset(false);
  }, [save]);

  const openStep = useCallback((journeyId: string, step: JourneyStep) => {
    const href = journeyStepHref(step, buildId);
    if (!href) return;
    save(recordJourneyOpen(current.current, journeyId, step.id));
    router.push(href as never);
  }, [buildId, router, save]);

  const reset = useCallback(() => {
    const next = { ...initialJourneySession(), selected: current.current.selected };
    save(next);
    setConfirmReset(false);
  }, [save]);

  const selectedJourney = journeyById(session?.selected ?? '') ?? PRODUCT_JOURNEYS[0];
  const opened = session?.opened[selectedJourney.id] ?? [];
  const availableNext = nextUnopened(selectedJourney, opened, !!buildId);
  const filtered = PRODUCT_JOURNEYS.filter((journey) => {
    const q = filter.trim().toLowerCase();
    return !q || [journey.title, journey.purpose, ...journey.steps.map(s => s.title)].join(' ').toLowerCase().includes(q);
  });

  return (
    <SafeAreaView style={styles.safe}>
      <ScrollView contentContainerStyle={[styles.page, wide && styles.wide]} keyboardShouldPersistTaps="handled">
        <TouchableOpacity accessibilityRole="button" accessibilityLabel="Back to product home"
          style={styles.back} onPress={() => router.push('/product' as never)}>
          <Text style={styles.link}>‹ Product home</Text>
        </TouchableOpacity>
        <View style={styles.hero}>
          <Text style={styles.eyebrow}>SKELETON · WORKFLOWS</Text>
          <Text style={styles.title}>Pick a goal. Keep your place.</Text>
          <Text style={styles.body}>Connected journeys across the tools you already have. Opened steps are navigation history, not proof that a build, task or review is complete.</Text>
        </View>

        <View style={styles.panel}>
          <Text style={styles.section}>Choose a journey</Text>
          <TextInput
            testID="journey-search"
            accessibilityLabel="Filter journeys"
            placeholder="Search goals, workflows and steps…"
            placeholderTextColor="#76849B"
            value={filter}
            onChangeText={setFilter}
            style={styles.input}
            autoCorrect={false}
          />
          <View style={styles.grid}>
            {filtered.map((journey) => {
              const active = selectedJourney.id === journey.id;
              const visits = session?.opened[journey.id]?.length ?? 0;
              return (
                <TouchableOpacity key={journey.id} testID={`journey-select-${journey.id}`}
                  accessibilityRole="button" accessibilityState={{ selected: active }}
                  onPress={() => choose(journey.id)}
                  style={[styles.choice, wide && styles.choiceWide, active && styles.choiceActive]}>
                  <Text style={styles.choiceTitle}>{journey.title}</Text>
                  <Text style={styles.choiceDescription}>{journey.purpose}</Text>
                  <Text style={styles.meta}>{visits}/{journey.steps.length} screens opened</Text>
                </TouchableOpacity>
              );
            })}
          </View>
          {filtered.length === 0 ? (
            <TouchableOpacity onPress={() => setFilter('')} style={styles.clear} accessibilityRole="button">
              <Text style={styles.link}>No journeys match. Clear search</Text>
            </TouchableOpacity>
          ) : null}
        </View>

        <View style={styles.panel}>
          <Text style={styles.section}>Working build</Text>
          <Text style={styles.body}>Select a recent build to carry its ID into Studio and the game knowledge base. The selection stays in memory; it is not added to local navigation history.</Text>
          {loadingBuilds ? <ActivityIndicator color="#A78BFA" style={styles.loading} /> : null}
          {buildError ? (
            <Text accessibilityLiveRegion="polite" style={styles.warning}>Builds are temporarily unavailable. You can still use the journeys and choose a build in Studio.</Text>
          ) : null}
          <View style={styles.buildGrid}>
            {builds.map((build) => (
              <TouchableOpacity key={build.id} testID={`journey-build-${build.id}`}
                accessibilityRole="button" accessibilityState={{ selected: buildId === build.id }}
                style={[styles.buildChoice, buildId === build.id && styles.choiceActive]}
                onPress={() => setBuildId(build.id)}>
                <Text numberOfLines={1} style={styles.choiceTitle}>{build.title}</Text>
                <Text style={styles.meta}>{build.status}</Text>
              </TouchableOpacity>
            ))}
          </View>
          {!loadingBuilds && !buildError && builds.length === 0 ? (
            <Text style={styles.muted}>No recent playable builds returned. Start one in Galaxy Studio.</Text>
          ) : null}
          <View style={styles.controls}>
            <TouchableOpacity accessibilityRole="button" onPress={() => void refreshBuilds()} disabled={loadingBuilds} style={styles.secondary}>
              <Text style={styles.secondaryText}>Refresh builds</Text>
            </TouchableOpacity>
            <TouchableOpacity accessibilityRole="button" onPress={() => setBuildId('')} disabled={!buildId} style={styles.secondary}>
              <Text style={styles.secondaryText}>Clear selection</Text>
            </TouchableOpacity>
          </View>
          {buildId ? <Text style={styles.success}>Build selected for contextual links.</Text> : null}
        </View>

        <View style={styles.panel}>
          <Text style={styles.section}>{selectedJourney.title}</Text>
          <Text style={styles.body}>{selectedJourney.purpose}</Text>
          {session === null ? <ActivityIndicator color="#A78BFA" /> : (
            <>
              <Text style={styles.meta}>{opened.length} of {selectedJourney.steps.length} screens opened · No completion claimed</Text>
              {availableNext ? (
                <TouchableOpacity testID="journey-next" accessibilityRole="button"
                  accessibilityLabel={`Open next available step: ${availableNext.title}`}
                  style={styles.primary} onPress={() => openStep(selectedJourney.id, availableNext)}>
                  <Text style={styles.primaryText}>Continue · {availableNext.title} →</Text>
                </TouchableOpacity>
              ) : (
                <Text style={styles.muted}>Every currently accessible step has been opened. Review a step again or select a build to unlock a contextual step.</Text>
              )}
              {selectedJourney.steps.map((step, index) => {
                const href = journeyStepHref(step, buildId);
                const seen = opened.includes(step.id);
                return (
                  <View key={step.id} testID={`journey-step-${step.id}`} style={styles.step}>
                    <View style={styles.stepNumber}><Text style={styles.stepNumText}>{index + 1}</Text></View>
                    <View style={styles.stepCopy}>
                      <Text style={styles.stepTitle}>{step.title}</Text>
                      <Text style={styles.body}>{step.description}</Text>
                      <Text style={styles.meta}>{seen ? 'Previously opened' : 'Not opened'}{!href ? ' · Select a build first' : ''}</Text>
                    </View>
                    <TouchableOpacity accessibilityRole="button" accessibilityLabel={`Open ${step.title}`}
                      accessibilityState={{ disabled: !href }} disabled={!href}
                      testID={`journey-open-${step.id}`}
                      style={[styles.smallButton, !href && styles.disabled]}
                      onPress={() => openStep(selectedJourney.id, step)}>
                      <Text style={styles.smallButtonText}>Open</Text>
                    </TouchableOpacity>
                  </View>
                );
              })}
            </>
          )}
        </View>

        <View style={styles.panel}>
          <Text style={styles.section}>Resume and privacy</Text>
          <Text style={styles.body}>On-device preferences remember your chosen journey and screens opened. No prompts, project contents or build IDs are saved here. Actual build status always comes from the service.</Text>
          {session?.last ? (
            <TouchableOpacity testID="journey-resume" accessibilityRole="button"
              style={styles.secondary} onPress={() => {
                const last = session.last;
                const journey = journeyById(last.journey);
                const step = journey?.steps.find(s => s.id === last.step);
                if (step) openStep(journey!.id, step);
              }}>
              <Text style={styles.secondaryText}>Reopen last screen →</Text>
            </TouchableOpacity>
          ) : null}
          {confirmReset ? (
            <View style={styles.controls}>
              <Text style={styles.warning}>Clear all journey navigation history on this device?</Text>
              <TouchableOpacity testID="journey-reset-confirm" accessibilityRole="button" style={styles.danger} onPress={reset}>
                <Text style={styles.primaryText}>Clear history</Text>
              </TouchableOpacity>
              <TouchableOpacity accessibilityRole="button" style={styles.secondary} onPress={() => setConfirmReset(false)}>
                <Text style={styles.secondaryText}>Cancel</Text>
              </TouchableOpacity>
            </View>
          ) : (
            <TouchableOpacity testID="journey-reset" accessibilityRole="button" style={styles.secondary}
              onPress={() => setConfirmReset(true)}>
              <Text style={styles.secondaryText}>Reset navigation history</Text>
            </TouchableOpacity>
          )}
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#080A0F' },
  page: { padding: 18, paddingBottom: 55, gap: 15 },
  wide: { maxWidth: 1100, width: '100%', alignSelf: 'center' },
  back: { paddingVertical: 5, minHeight: 44, justifyContent: 'center' },
  link: { color: '#AFB5FF', fontWeight: '800', fontSize: 13 },
  hero: { backgroundColor: '#13182A', borderColor: '#333C5B', borderWidth: 1, borderRadius: 22, padding: 22 },
  eyebrow: { color: '#A5B4FC', fontSize: 11, letterSpacing: 1.7, fontWeight: '900' },
  title: { color: '#F8FAFC', fontSize: 27, fontWeight: '900', marginTop: 9 },
  body: { color: '#AAB5C9', fontSize: 12, lineHeight: 18, marginTop: 5 },
  panel: { backgroundColor: '#101622', borderColor: '#283248', borderWidth: 1, borderRadius: 18, padding: 16, gap: 10 },
  section: { color: '#F6F8FF', fontSize: 18, fontWeight: '850' },
  input: { backgroundColor: '#0B1020', borderColor: '#344058', borderWidth: 1, borderRadius: 12, color: '#FAFCFF', padding: 12, minHeight: 48 },
  grid: { flexDirection: 'row', gap: 10, flexWrap: 'wrap' },
  choice: { width: '100%', borderColor: '#30394F', borderWidth: 1, borderRadius: 12, backgroundColor: '#161D2C', padding: 14 },
  choiceWide: { width: '49%', flexGrow: 1 },
  choiceActive: { borderColor: '#A78BFA', backgroundColor: '#232344' },
  choiceTitle: { color: '#FAFCFF', fontWeight: '800', fontSize: 14 },
  choiceDescription: { color: '#AAB5C9', fontSize: 12, lineHeight: 18, marginTop: 6 },
  meta: { color: '#94A2BB', fontSize: 11, marginTop: 6 },
  clear: { padding: 10 },
  buildGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  buildChoice: { width: '48%', flexGrow: 1, borderRadius: 12, backgroundColor: '#151B2A', borderWidth: 1, borderColor: '#30394F', padding: 12 },
  loading: { alignSelf: 'flex-start' },
  muted: { color: '#929EB6', fontSize: 12, lineHeight: 19 },
  warning: { color: '#F9BC91', fontSize: 12, lineHeight: 19, flexShrink: 1 },
  success: { color: '#80DEA3', fontSize: 12 },
  controls: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: 9 },
  primary: { backgroundColor: '#6755D6', borderRadius: 12, padding: 14, minHeight: 48, justifyContent: 'center' },
  primaryText: { color: '#FFFFFF', fontWeight: '900', fontSize: 13 },
  secondary: { borderColor: '#414A64', borderWidth: 1, borderRadius: 12, padding: 12, minHeight: 44, justifyContent: 'center' },
  secondaryText: { color: '#D7DDF3', fontWeight: '800', fontSize: 12 },
  danger: { backgroundColor: '#7F3045', borderRadius: 10, padding: 12, minHeight: 44, justifyContent: 'center' },
  step: { flexDirection: 'row', gap: 10, alignItems: 'center', borderTopColor: '#2B3447', borderTopWidth: 1, paddingTop: 12 },
  stepNumber: { height: 29, width: 29, borderRadius: 15, alignItems: 'center', justifyContent: 'center', backgroundColor: '#252C41' },
  stepNumText: { color: '#C9D3EB', fontWeight: '900', fontSize: 12 },
  stepCopy: { flex: 1 },
  stepTitle: { color: '#F0F5FF', fontSize: 14, fontWeight: '800' },
  smallButton: { backgroundColor: '#35477B', paddingHorizontal: 13, paddingVertical: 12, minHeight: 44, borderRadius: 10, justifyContent: 'center' },
  smallButtonText: { color: '#FFFFFF', fontWeight: '800', fontSize: 12 },
  disabled: { opacity: 0.38 },
});
