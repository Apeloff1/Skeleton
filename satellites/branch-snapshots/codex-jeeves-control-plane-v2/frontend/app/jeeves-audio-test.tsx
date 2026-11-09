/**
 * /jeeves-audio-test — P2 Jeeves TTS audio diagnostics route.
 *
 * Lets the user (or testing agent) verify that Jeeves' persona-flavoured TTS
 * actually plays on-device. Cycles through every supported Jeeves context,
 * shows the catchphrase loaded from backend, the mannerism (speed/pitch/voice)
 * applied, and offers a "Play" button per context.
 *
 * Also surfaces a vanilla on-device test (no persona overlay) for A/B
 * comparison so we can rule out persona-layer issues vs underlying TTS.
 */
import { useEffect, useState } from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity,
  ActivityIndicator, Platform, Switch,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { LinearGradient } from 'expo-linear-gradient';
import {
  jeevesSpeak, jeevesCatchphrase, jeevesStop, type JeevesContext,
} from '../features/Academy/jeevesTts';
import {
  ttsSpeak, ttsAvailableVoices, pickPreferredVoice, ttsIsSpeaking,
} from '../features/Academy/tts';
import { useSettings } from '../state/settingsStore';

const BACKEND = process.env.EXPO_PUBLIC_BACKEND_URL || '';

const CONTEXTS: { ctx: JeevesContext; label: string; sample: string; icon: any; tone: string }[] = [
  { ctx: 'greeting',              label: 'Greeting',              sample: 'A pleasure to see you again. Shall we continue where we left off?', icon: 'hand-left',         tone: '#A78BFA' },
  { ctx: 'lesson',                label: 'Lesson',                sample: 'Allow me to explain how a hash table resolves collisions through chaining.',           icon: 'school',            tone: '#3B82F6' },
  { ctx: 'lesson_intro',          label: 'Lesson intro',          sample: 'Today we shall study the elegant tail-recursive factorial.',                            icon: 'book',              tone: '#60A5FA' },
  { ctx: 'encouragement',         label: 'Encouragement',         sample: 'You are doing splendidly. Trust your work.',                                            icon: 'rocket',            tone: '#10B981' },
  { ctx: 'gentle_correction',     label: 'Gentle correction',     sample: 'A small detail — the index begins at zero, not one.',                                   icon: 'create',            tone: '#F59E0B' },
  { ctx: 'alert',                 label: 'Alert',                 sample: 'I beg your pardon — your build has failed three consecutive times.',                    icon: 'alert-circle',      tone: '#EF4444' },
  { ctx: 'debug',                 label: 'Debug',                 sample: 'Curious. The stack trace points to line forty-seven.',                                  icon: 'bug',               tone: '#F87171' },
  { ctx: 'joke',                  label: 'Joke',                  sample: 'Why do programmers prefer dark mode? Because light attracts bugs.',                     icon: 'happy',             tone: '#F5C451' },
  { ctx: 'sign_off',              label: 'Sign-off',              sample: 'Until next we meet. Do enjoy your evening.',                                            icon: 'exit',              tone: '#94A3B8' },
  { ctx: 'quiz_nudge',            label: 'Quiz nudge',            sample: 'Care to test yourself? Three swift questions await.',                                   icon: 'help-circle',       tone: '#8B5CF6' },
  { ctx: 'celebration',           label: 'Celebration',           sample: 'Magnificent! That is a streak worth recording.',                                        icon: 'trophy',            tone: '#F59E0B' },
  { ctx: 'code_walkthrough',      label: 'Code walkthrough',      sample: 'We begin at the for loop, iterate through the array, and accumulate.',                  icon: 'code-slash',        tone: '#3B82F6' },
  { ctx: 'story_time',            label: 'Story time',            sample: 'Once upon a time, in 1843, Lady Ada Lovelace penned the first algorithm.',              icon: 'library',           tone: '#8B5CF6' },
  { ctx: 'thinking',              label: 'Thinking',              sample: 'Hm. Let me consider this for a moment.',                                                icon: 'bulb',              tone: '#FDE047' },
  { ctx: 'frustration_relief',    label: 'Frustration relief',    sample: 'Breathe. Step away. Return refreshed.',                                                 icon: 'heart',             tone: '#F472B6' },
  { ctx: 'transition',            label: 'Transition',            sample: 'Now then, onward to the next chapter.',                                                 icon: 'arrow-forward',     tone: '#3B82F6' },
  { ctx: 'definition',            label: 'Definition',            sample: 'A monad is a monoid in the category of endofunctors.',                                  icon: 'reader',            tone: '#A3E635' },
  { ctx: 'warning_clarification', label: 'Warning clarification', sample: 'Pray, mind that this operation is irreversible.',                                       icon: 'warning',           tone: '#FB923C' },
  { ctx: 'quote',                 label: 'Famous quote',          sample: 'Premature optimization is the root of all evil. — D. E. Knuth',                         icon: 'chatbox',           tone: '#C084FC' },
];

type Mannerism = { speed: number; pitch_hint: string; emoji: string; voice: string };

export default function JeevesAudioTestScreen() {
  const router = useRouter();
  const academy = useSettings(s => s.academy);
  const [mannerisms, setMannerisms] = useState<Record<string, Mannerism>>({});
  const [catchphrases, setCatchphrases] = useState<Record<string, string>>({});
  const [voices, setVoices] = useState<any[]>([]);
  const [busyCtx, setBusyCtx] = useState<string | null>(null);
  const [voiceProbeResult, setVoiceProbeResult] = useState<string>('');
  const [withCatchphrase, setWithCatchphrase] = useState(true);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      setLoading(true);
      // 1. Load mannerism map
      try {
        const r = await fetch(`${BACKEND}/api/jeeves/persona/vocal_mannerisms`);
        const j = await r.json();
        if (j && typeof j === 'object') setMannerisms(j);
      } catch {}
      // 2. Prefetch one catchphrase per ctx
      const out: Record<string, string> = {};
      for (const c of CONTEXTS) {
        try {
          const cp = await jeevesCatchphrase(c.ctx);
          out[c.ctx] = cp;
        } catch { out[c.ctx] = ''; }
      }
      setCatchphrases(out);
      // 3. Voices list (mobile only really)
      try {
        const v = await ttsAvailableVoices();
        setVoices(v || []);
      } catch {}
      setLoading(false);
    })();
    return () => { jeevesStop(); };
  }, []);

  const play = async (ctx: JeevesContext, sample: string) => {
    setBusyCtx(ctx);
    try {
      await jeevesSpeak(sample, {
        context: ctx,
        prependCatchphrase: withCatchphrase,
        onComplete: () => setBusyCtx(null),
      });
    } catch {
      setBusyCtx(null);
    }
    setTimeout(() => { if (!ttsIsSpeaking()) setBusyCtx(null); }, sample.length * 80 + 4000);
  };

  const stopAll = () => { jeevesStop(); setBusyCtx(null); };

  const probeBaselineVoice = () => {
    ttsSpeak('This is a vanilla on-device test without any persona overlay.', {
      onComplete: () => setVoiceProbeResult('✓ Vanilla TTS finished'),
    });
    setVoiceProbeResult('Speaking…');
  };

  const refreshVoice = async () => {
    try {
      const id = await pickPreferredVoice('en-US', 'male');
      useSettings.setState({ academy: { ...academy, voiceIdentifier: id } });
      setVoiceProbeResult(`✓ Picked voice: ${id || '(default)'}`);
    } catch (e: any) {
      setVoiceProbeResult(`✗ ${e.message || 'failed'}`);
    }
  };

  return (
    <View style={s.root}>
      <LinearGradient
        colors={['#A78BFA22', '#3B82F622', 'transparent']}
        start={{ x: 0.1, y: 0 }} end={{ x: 0.9, y: 0.5 }}
        style={[s.aurora, { pointerEvents: 'none' }]}
      />
      <View style={s.header}>
        <TouchableOpacity onPress={() => router.back()} style={s.backBtn}>
          <Ionicons name="chevron-back" size={22} color="#A78BFA" />
        </TouchableOpacity>
        <View style={{ flex: 1 }}>
          <Text style={s.title}>🎩 Jeeves Audio Test</Text>
          <Text style={s.subtitle}>P2 verification · {CONTEXTS.length} contexts · live persona TTS</Text>
        </View>
        <TouchableOpacity onPress={stopAll} style={s.stopBtn}>
          <Ionicons name="stop-circle" size={20} color="#EF4444" />
        </TouchableOpacity>
      </View>

      <ScrollView contentContainerStyle={s.scroll}>
        {/* Settings strip */}
        <View style={s.settingsCard}>
          <View style={s.settingRow}>
            <Ionicons name="megaphone" size={16} color="#A78BFA" />
            <Text style={s.settingLabel}>Include catchphrase</Text>
            <Switch
              value={withCatchphrase}
              onValueChange={setWithCatchphrase}
              trackColor={{ false: '#404040', true: '#A78BFA66' }}
              thumbColor={withCatchphrase ? '#A78BFA' : '#94A3B8'}
            />
          </View>
          <View style={s.settingRow}>
            <Ionicons name="settings" size={16} color="#3B82F6" />
            <Text style={s.settingLabel}>TTS rate</Text>
            <Text style={s.settingVal}>{academy.ttsRate?.toFixed(2) ?? '1.00'}×</Text>
          </View>
          <View style={s.settingRow}>
            <Ionicons name="mic" size={16} color="#10B981" />
            <Text style={s.settingLabel}>Voices available</Text>
            <Text style={s.settingVal}>{voices.length}</Text>
          </View>
          <View style={s.settingRow}>
            <Ionicons name="globe" size={16} color="#F5C451" />
            <Text style={s.settingLabel}>Platform</Text>
            <Text style={s.settingVal}>{Platform.OS}</Text>
          </View>
          <View style={s.btnRow}>
            <TouchableOpacity onPress={probeBaselineVoice} style={[s.probeBtn, { backgroundColor: '#3B82F6' }]}>
              <Ionicons name="volume-medium" size={14} color="#fff" />
              <Text style={s.probeText}>Vanilla TTS probe</Text>
            </TouchableOpacity>
            <TouchableOpacity onPress={refreshVoice} style={[s.probeBtn, { backgroundColor: '#10B981' }]}>
              <Ionicons name="refresh" size={14} color="#fff" />
              <Text style={s.probeText}>Auto-pick male voice</Text>
            </TouchableOpacity>
          </View>
          {voiceProbeResult ? <Text style={s.probeResult}>{voiceProbeResult}</Text> : null}
        </View>

        {loading ? (
          <View style={s.loading}><ActivityIndicator color="#A78BFA" /><Text style={s.loadingText}>Loading persona DB…</Text></View>
        ) : (
          CONTEXTS.map(c => {
            const m = mannerisms[c.ctx];
            const cp = catchphrases[c.ctx] || '';
            const busy = busyCtx === c.ctx;
            return (
              <View key={c.ctx} style={[s.ctxCard, { borderColor: c.tone + '66' }]}>
                <View style={s.ctxHead}>
                  <View style={[s.ctxIcon, { backgroundColor: c.tone + '22', borderColor: c.tone }]}>
                    <Ionicons name={c.icon} size={18} color={c.tone} />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={s.ctxLabel}>{c.label}</Text>
                    <Text style={s.ctxMeta} numberOfLines={1}>
                      {m
                        ? `speed ${m.speed?.toFixed(2)}× · pitch ${m.pitch_hint || '—'} · voice ${m.voice || 'default'}`
                        : 'no mannerism loaded'}
                    </Text>
                  </View>
                  <TouchableOpacity
                    onPress={() => (busy ? stopAll() : play(c.ctx, c.sample))}
                    style={[s.playBtn, { backgroundColor: busy ? '#EF4444' : c.tone }]}
                  >
                    <Ionicons name={busy ? 'stop' : 'play'} size={16} color="#fff" />
                  </TouchableOpacity>
                </View>
                {cp ? (
                  <View style={s.cpBlock}>
                    <Text style={s.cpLabel}>CATCHPHRASE</Text>
                    <Text style={s.cpText} numberOfLines={3}>“{cp}”</Text>
                  </View>
                ) : null}
                <View style={s.sampleBlock}>
                  <Text style={s.sampleLabel}>SAMPLE</Text>
                  <Text style={s.sampleText} numberOfLines={3}>{c.sample}</Text>
                </View>
              </View>
            );
          })
        )}
        <View style={{ height: 60 }} />
      </ScrollView>
    </View>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#0A0A0A' },
  aurora: { position: 'absolute', top: 0, left: 0, right: 0, height: 220 },
  header: { flexDirection: 'row', alignItems: 'center', padding: 14, gap: 10, borderBottomWidth: 1, borderBottomColor: '#1F1F1F' },
  backBtn: { width: 36, height: 36, borderRadius: 18, alignItems: 'center', justifyContent: 'center', backgroundColor: '#A78BFA22' },
  stopBtn: { width: 36, height: 36, borderRadius: 18, alignItems: 'center', justifyContent: 'center', backgroundColor: '#EF444422' },
  title: { color: '#F8FAFC', fontSize: 16, fontWeight: '800' },
  subtitle: { color: '#94A3B8', fontSize: 11, marginTop: 2 },
  scroll: { padding: 14, paddingBottom: 40 },
  settingsCard: { borderRadius: 12, padding: 14, marginBottom: 16, backgroundColor: '#141414', borderWidth: 1, borderColor: '#1F1F1F' },
  settingRow: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 6 },
  settingLabel: { color: '#CBD5E1', fontSize: 12, fontWeight: '600', flex: 1 },
  settingVal: { color: '#94A3B8', fontSize: 11, fontWeight: '700' },
  btnRow: { flexDirection: 'row', gap: 8, marginTop: 10 },
  probeBtn: { flex: 1, flexDirection: 'row', gap: 6, alignItems: 'center', justifyContent: 'center', paddingVertical: 9, borderRadius: 8 },
  probeText: { color: '#fff', fontSize: 11, fontWeight: '800' },
  probeResult: { color: '#10B981', fontSize: 11, fontWeight: '700', marginTop: 10, textAlign: 'center' },
  loading: { padding: 40, alignItems: 'center' },
  loadingText: { color: '#94A3B8', fontSize: 12, marginTop: 8 },
  ctxCard: { borderWidth: 1, borderRadius: 10, padding: 12, marginBottom: 10, backgroundColor: '#141414' },
  ctxHead: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  ctxIcon: { width: 36, height: 36, borderRadius: 10, borderWidth: 1, alignItems: 'center', justifyContent: 'center' },
  ctxLabel: { color: '#F8FAFC', fontSize: 13, fontWeight: '800' },
  ctxMeta: { color: '#64748B', fontSize: 10, marginTop: 2 },
  playBtn: { width: 36, height: 36, borderRadius: 18, alignItems: 'center', justifyContent: 'center' },
  cpBlock: { marginTop: 10, padding: 8, borderRadius: 6, backgroundColor: '#1E1B3520', borderLeftWidth: 2, borderLeftColor: '#A78BFA' },
  cpLabel: { color: '#A78BFA', fontSize: 9, fontWeight: '800', letterSpacing: 1 },
  cpText: { color: '#E2E8F0', fontSize: 11, fontStyle: 'italic', marginTop: 4 },
  sampleBlock: { marginTop: 8, padding: 8, borderRadius: 6, backgroundColor: '#3B82F620', borderLeftWidth: 2, borderLeftColor: '#3B82F6' },
  sampleLabel: { color: '#3B82F6', fontSize: 9, fontWeight: '800', letterSpacing: 1 },
  sampleText: { color: '#CBD5E1', fontSize: 11, marginTop: 4 },
});
