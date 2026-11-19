/**
 * /settings/jeeves-voice — 🎙️ Jeeves Voice Lab.
 * Give Jeeves "innlevelse": pick an expressive tone, audition it with real HD
 * audio (storyteller cadence + tone control), and toggle the cinematic voice
 * that replaces the robotic on-device speech app-wide.
 */
import React from 'react';
import {
  View, Text, StyleSheet, ScrollView, SafeAreaView, TouchableOpacity,
  ActivityIndicator, Switch, TextInput,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useSettings } from '../../state/settingsStore';
import { fetchTones, previewTone, speakCinematic, stopCinematic, playTrailer, type Tone } from '../../src/utils/cinematicVoice';
import { toast } from '../../components/Toast';

const TONE_EMOJI: Record<string, string> = {
  butler: '🤵', storyteller: '📖', warm: '☀️', dramatic: '🎭', witty: '😏',
  solemn: '🕯️', excited: '🎉', gentle: '🪷', calm: '🌊', suspense: '🔦',
  triumphant: '🏆', narrator: '🌌',
};

export default function JeevesVoiceLab() {
  const router = useRouter();
  const academy = useSettings(s => s.academy);
  const setAcademy = useSettings(s => s.setAcademy);

  const [tones, setTones] = React.useState<Tone[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [busy, setBusy] = React.useState<string | null>(null);
  const [trailerTitle, setTrailerTitle] = React.useState('Neon Drifters');
  const [trailerBusy, setTrailerBusy] = React.useState(false);

  const activeTone = academy.jeevesTone || 'butler';
  const cinematic = academy.cinematicVoice !== false;

  React.useEffect(() => {
    (async () => {
      setLoading(true);
      setTones(await fetchTones());
      setLoading(false);
    })();
    return () => { stopCinematic(); };
  }, []);

  const onAudition = async (toneId: string) => {
    setBusy(toneId);
    const res = await previewTone(toneId);
    setBusy(null);
    if (!res.ok) toast.warn('Could not play sample — check connection');
  };

  const onHearJeeves = async () => {
    setBusy('jeeves');
    const res = await speakCinematic(
      "Good day. I'm Jeeves — your butler and narrator. Listen closely, for every world we build together deserves to be told beautifully.",
      { tone: activeTone },
    );
    setBusy(null);
    if (!res.ok) toast.warn('Could not play — check connection');
  };

  const onTrailer = async () => {
    setTrailerBusy(true);
    const res = await playTrailer({ title: trailerTitle.trim() || 'Your World' });
    setTrailerBusy(false);
    if (!res.ok) toast.warn('Could not build trailer — check connection');
  };

  return (
    <SafeAreaView style={s.root}>
      <View style={s.header}>
        <TouchableOpacity testID="voice-back" onPress={() => { stopCinematic(); router.back(); }} style={s.headerBtn}>
          <Ionicons name="arrow-back" size={24} color="#F8FAFC" />
        </TouchableOpacity>
        <Text style={s.headerTitle}>🎙️ Jeeves Voice Lab</Text>
        <TouchableOpacity testID="voice-stop" onPress={stopCinematic} style={s.headerBtn}>
          <Ionicons name="stop-circle" size={24} color="#EF4444" />
        </TouchableOpacity>
      </View>

      <ScrollView contentContainerStyle={{ padding: 16, paddingBottom: 48 }}>
        <Text style={s.intro}>
          Replace the robotic device voice with a cinematic, immersive narrator. Pick a tone, audition it, and Jeeves will speak with real storyteller cadence everywhere in the app.
        </Text>

        {/* Cinematic toggle */}
        <View style={s.toggleCard}>
          <View style={{ flex: 1 }}>
            <Text style={s.toggleTitle}>Cinematic HD voice</Text>
            <Text style={s.toggleSub}>Storyteller cadence + tone control (tts-1-hd). Falls back to device voice offline.</Text>
          </View>
          <Switch
            testID="cinematic-toggle"
            value={cinematic}
            onValueChange={(v) => setAcademy({ cinematicVoice: v })}
            trackColor={{ true: '#8B5CF6', false: '#3f3f46' }}
            thumbColor="#fff"
          />
        </View>

        {/* Hear Jeeves */}
        <TouchableOpacity testID="hear-jeeves" onPress={onHearJeeves} style={s.heroBtn} activeOpacity={0.9}>
          {busy === 'jeeves'
            ? <ActivityIndicator color="#fff" />
            : <><Ionicons name="play" size={18} color="#fff" /><Text style={s.heroTxt}>Hear Jeeves in “{activeTone}”</Text></>}
        </TouchableOpacity>

        {/* 🎬 Voiced trailer demo */}
        <View style={s.trailerCard}>
          <Text style={s.trailerTitle}>🎬 Voiced Game Trailer</Text>
          <Text style={s.trailerSub}>A 3-beat multi-voice hype reel: narrator → dramatic → triumphant.</Text>
          <TextInput
            testID="trailer-title"
            value={trailerTitle}
            onChangeText={setTrailerTitle}
            placeholder="Game title…"
            placeholderTextColor="#64748b"
            style={s.trailerInput}
            autoCorrect={false}
          />
          <TouchableOpacity testID="build-trailer" onPress={onTrailer} style={s.trailerBtn} activeOpacity={0.9}>
            {trailerBusy
              ? <ActivityIndicator color="#fff" />
              : <><Ionicons name="film" size={16} color="#fff" /><Text style={s.trailerBtnTxt}>Build voiced trailer</Text></>}
          </TouchableOpacity>
        </View>

        <Text style={s.section}>Tone · tap to select, ▶ to audition</Text>

        {loading ? (
          <ActivityIndicator color="#8B5CF6" style={{ marginTop: 24 }} />
        ) : (
          <View style={s.grid}>
            {tones.map((t) => {
              const on = t.id === activeTone;
              return (
                <View key={t.id} style={[s.card, on && s.cardOn]}>
                  <TouchableOpacity
                    testID={`tone-${t.id}`}
                    style={{ flex: 1 }}
                    activeOpacity={0.85}
                    onPress={() => setAcademy({ jeevesTone: t.id })}
                  >
                    <Text style={s.cardEmoji}>{TONE_EMOJI[t.id] || '🎙️'}</Text>
                    <Text style={s.cardName} numberOfLines={1}>{t.label}</Text>
                    <Text style={s.cardMeta}>{t.voice} · {t.speed}×</Text>
                    {on && <View style={s.activePill}><Text style={s.activeTxt}>ACTIVE</Text></View>}
                  </TouchableOpacity>
                  <TouchableOpacity
                    testID={`audition-${t.id}`}
                    onPress={() => onAudition(t.id)}
                    style={s.auditionBtn}
                  >
                    {busy === t.id
                      ? <ActivityIndicator size="small" color="#A78BFA" />
                      : <Ionicons name="volume-high" size={16} color="#A78BFA" />}
                  </TouchableOpacity>
                </View>
              );
            })}
          </View>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#0b0820' },
  header: { flexDirection: 'row', alignItems: 'center', padding: 12, backgroundColor: '#15103a', borderBottomWidth: 1, borderBottomColor: '#2a2150' },
  headerBtn: { width: 44, height: 44, justifyContent: 'center', alignItems: 'center' },
  headerTitle: { flex: 1, textAlign: 'center', fontSize: 17, fontWeight: '800', color: '#F8FAFC' },
  intro: { color: '#94a3b8', fontSize: 13, lineHeight: 19, marginBottom: 14 },
  toggleCard: { flexDirection: 'row', alignItems: 'center', gap: 12, backgroundColor: '#15103a', borderRadius: 14, borderWidth: 1, borderColor: '#8B5CF655', padding: 14, marginBottom: 14 },
  toggleTitle: { color: '#F8FAFC', fontSize: 15, fontWeight: '800' },
  toggleSub: { color: '#94a3b8', fontSize: 11, marginTop: 3, lineHeight: 15 },
  heroBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, backgroundColor: '#c026d3', borderRadius: 14, paddingVertical: 14, marginBottom: 18 },
  heroTxt: { color: '#fff', fontSize: 15, fontWeight: '800' },
  trailerCard: { backgroundColor: '#15103a', borderRadius: 14, borderWidth: 1, borderColor: '#3B82F655', padding: 14, marginBottom: 18 },
  trailerTitle: { color: '#F8FAFC', fontSize: 15, fontWeight: '800' },
  trailerSub: { color: '#94a3b8', fontSize: 11, marginTop: 3, lineHeight: 15, marginBottom: 10 },
  trailerInput: { backgroundColor: '#0b0820', borderRadius: 10, borderWidth: 1, borderColor: '#ffffff14', color: '#e2e8f0', fontSize: 13, paddingHorizontal: 12, paddingVertical: 10, marginBottom: 10 },
  trailerBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, backgroundColor: '#1D4ED8', borderRadius: 12, paddingVertical: 12 },
  trailerBtnTxt: { color: '#fff', fontSize: 14, fontWeight: '800' },
  section: { color: '#e879f9', fontSize: 12, fontWeight: '800', letterSpacing: 0.6, textTransform: 'uppercase', marginBottom: 10 },
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: 10, justifyContent: 'space-between' },
  card: { width: '48%', backgroundColor: '#15103a', borderRadius: 14, borderWidth: 2, borderColor: '#ffffff14', padding: 12, flexDirection: 'row', alignItems: 'center' },
  cardOn: { borderColor: '#c026d3' },
  cardEmoji: { fontSize: 26, marginBottom: 4 },
  cardName: { color: '#F8FAFC', fontSize: 13, fontWeight: '800' },
  cardMeta: { color: '#94a3b8', fontSize: 11, marginTop: 2 },
  activePill: { alignSelf: 'flex-start', backgroundColor: '#c026d3', borderRadius: 6, paddingHorizontal: 6, paddingVertical: 2, marginTop: 6 },
  activeTxt: { color: '#fff', fontSize: 8, fontWeight: '900' },
  auditionBtn: { width: 36, height: 36, borderRadius: 18, backgroundColor: '#8B5CF622', borderWidth: 1, borderColor: '#8B5CF655', alignItems: 'center', justifyContent: 'center' },
});
