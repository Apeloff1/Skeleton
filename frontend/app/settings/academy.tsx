import { useEffect, useState, useMemo } from 'react';
import { View, Text, StyleSheet, ScrollView, SafeAreaView, TouchableOpacity } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useSettings, ACADEMY_DNA_GROUPS } from '../../state/settingsStore';
import { Section, SwitchRow, SliderRow, ChoiceRow, ActionButton } from '../../features/Settings/components';
import DnaCockpit from '../../features/Settings/DnaCockpit';
import { ttsSpeak, ttsStop, ttsAvailableVoices, pickPreferredVoice } from '../../features/Academy/tts';
import { jeevesSpeak, jeevesCatchphrase, getRandomQuote } from '../../features/Academy/jeevesTts';
import { actionSheet } from '../../components/ActionSheet';
import { toast } from '../../components/Toast';

export default function AcademySettings() {
  const router = useRouter();
  const a = useSettings(s => s.academy);
  const set = useSettings(s => s.setAcademy);
  const reset = useSettings(s => s.resetAcademy);
  const setAcademyDna = useSettings(s => s.setAcademyDna);
  const resetAcademyDna = useSettings(s => s.resetAcademyDna);
  const resetAcademyDnaGroup = useSettings(s => s.resetAcademyDnaGroup);

  const [allVoices, setAllVoices] = useState<any[]>([]);
  const [voiceLangOptions, setVoiceLangOptions] = useState<{ value: string; label: string }[]>([
    { value: 'en-US', label: 'English (US)' }, { value: 'en-GB', label: 'English (UK)' },
    { value: 'en-AU', label: 'English (AU)' }, { value: 'fr-FR', label: 'French' },
    { value: 'es-ES', label: 'Spanish' }, { value: 'de-DE', label: 'German' },
  ]);

  useEffect(() => {
    (async () => {
      const voices = await ttsAvailableVoices();
      if (voices && voices.length > 0) {
        setAllVoices(voices);
        const langs = [...new Set(voices.map((v: any) => v.language).filter(Boolean))].slice(0, 14);
        const opts = langs.map((lang: string) => ({ value: lang, label: lang }));
        if (opts.length > 0) setVoiceLangOptions(opts);
      }
    })();
    return () => { ttsStop(); };
  }, []);

  // Filter voices by gender heuristic for the dropdown
  const voiceIdOptions = useMemo(() => {
    if (!allVoices.length) return [{ value: '', label: 'System default' }];
    const gender = a.voiceGender;
    const MALE = ['male', 'man', 'daniel', 'fred', 'alex', 'tom', 'george', 'arthur', 'oliver', 'james', 'john', 'michael', 'david', 'ryan', 'aaron', 'reed', 'eddy', 'rocko', 'grandpa', 'iom', 'itn', 'imn', 'deep'];
    const FEMALE = ['female', 'woman', 'samantha', 'susan', 'victoria', 'allison', 'ava', 'karen', 'serena', 'kate', 'fiona', 'tessa', 'nora', 'grandma'];
    const lang = a.voiceLang?.split('-')[0] || 'en';
    const filtered = allVoices
      .filter((v: any) => (v.language || '').toLowerCase().startsWith(lang))
      .filter((v: any) => {
        if (gender === 'any') return true;
        const hay = `${v.name || ''} ${v.identifier || ''}`.toLowerCase();
        const wanted = gender === 'male' ? MALE : FEMALE;
        const other = gender === 'male' ? FEMALE : MALE;
        const hasWanted = wanted.some(t => hay.includes(t));
        const hasOther = other.some(t => hay.includes(t));
        // Include unknown-gender voices too, but demote opposite-gender ones
        return !hasOther || hasWanted;
      })
      .slice(0, 20);
    const opts = [{ value: '', label: 'Auto (best match)' }];
    for (const v of filtered) {
      const label = `${v.name || 'Voice'} (${v.language || '?'})`.slice(0, 38);
      opts.push({ value: v.identifier, label });
    }
    return opts;
  }, [allVoices, a.voiceGender, a.voiceLang]);

  const sampleText = 'Welcome to the Academy. This is your audiobook reader. Adjust the rate and pitch until the narration feels engaging and natural.';

  const autoPickVoice = async () => {
    const id = await pickPreferredVoice(a.voiceLang || 'en-US', a.voiceGender || 'male');
    if (id) {
      set({ voiceIdentifier: id });
      toast.info(`Picked best ${a.voiceGender} voice for ${a.voiceLang}.`);
    } else {
      toast.info('No TTS voices are installed on this device.');
    }
  };

  return (
    <SafeAreaView style={s.container}>
      <View style={s.header}>
        <TouchableOpacity onPress={() => { ttsStop(); router.back(); }} style={s.headerBtn}>
          <Ionicons name="arrow-back" size={24} color="#F8FAFC" />
        </TouchableOpacity>
        <Text style={s.headerTitle}>Academy Settings</Text>
        <TouchableOpacity onPress={() => actionSheet.show({
          title: 'Reset Academy?',
          message: 'Reset Academy settings to defaults?',
          options: [
            { label: 'Cancel', kind: 'cancel' },
            { label: 'Reset', kind: 'destructive', onPress: () => { reset(); toast.warn('Academy reset'); } },
          ],
        })} style={s.headerBtn}>
          <Ionicons name="refresh" size={22} color="#EF4444" />
        </TouchableOpacity>
      </View>

      <ScrollView contentContainerStyle={{ paddingBottom: 40 }}>

        <Section title="Audiobook mode (Text-to-Speech)" hint="Turn reading material into narration. Pair with Audiobook Mode below for hands-free playback.">
          <SwitchRow icon="volume-high" color="#8B5CF6" label="Enable TTS everywhere" hint="Adds play/pause controls on every lesson and chapter."
            value={a.ttsEnabled} onValueChange={v => set({ ttsEnabled: v })} />
          <SwitchRow icon="headset" color="#10B981" label="Audiobook Mode" hint="Opens chapters in narration mode — auto-starts reading when you open a chapter, smoother pacing, deeper voice."
            value={a.audiobookMode} onValueChange={v => set({ audiobookMode: v, ttsEnabled: v ? true : a.ttsEnabled })} />
          <SwitchRow icon="play-forward" color="#8B5CF6" label="Auto-advance chapters" hint="When chapter narration finishes, open and read the next one."
            value={a.autoAdvance} onValueChange={v => set({ autoAdvance: v })} />
          <SwitchRow icon="code" color="#8B5CF6" label="Read code blocks" hint="Speak ``` fenced code aloud. Off by default — code sounds awkward."
            value={a.readCodeBlocks} onValueChange={v => set({ readCodeBlocks: v })} />
        </Section>

        <Section title="Voice character" hint="Audiobook mode defaults to a warm male voice. Switch below.">
          <View style={s.genderRow}>
            {(['male', 'female', 'any'] as const).map(g => (
              <TouchableOpacity
                key={g}
                onPress={() => set({ voiceGender: g, voiceIdentifier: '' })}
                style={[s.genderPill, a.voiceGender === g && s.genderPillActive]}
              >
                <Ionicons
                  name={g === 'male' ? 'man' : g === 'female' ? 'woman' : 'people'}
                  size={16}
                  color={a.voiceGender === g ? '#141414' : '#CBD5E1'}
                />
                <Text style={[s.genderTxt, a.voiceGender === g && { color: '#141414' }]}>{g.toUpperCase()}</Text>
              </TouchableOpacity>
            ))}
          </View>
          <ChoiceRow label="Voice language" hint="Available on this device" color="#8B5CF6"
            value={a.voiceLang} onChange={v => set({ voiceLang: v, voiceIdentifier: '' })} options={voiceLangOptions.slice(0, 10)} />
          <ChoiceRow label="Specific voice" hint={`Filtered by gender: ${a.voiceGender}. "Auto" picks best available match.`} color="#8B5CF6"
            value={a.voiceIdentifier} onChange={v => set({ voiceIdentifier: v })} options={voiceIdOptions} />
          <View style={{ padding: 14, paddingTop: 0 }}>
            <ActionButton icon="sparkles" label={`Auto-pick best ${a.voiceGender} voice`} color="#10B981" onPress={autoPickVoice} />
          </View>
        </Section>

        <Section title="Pacing & tone">
          <SwitchRow icon="hat-cowboy" color="#a78bfa" label="Jeeves persona TTS" hint="Prepends catchphrases & adjusts pace to context (story/lesson/joke)"
            value={a.jeevesPersonaEnabled !== false} onValueChange={v => set({ jeevesPersonaEnabled: v })} />
          <SliderRow color="#8B5CF6" label="Speaking rate" hint="0.5× slower → 2× faster (0.95 = natural audiobook)"
            value={a.ttsRate} onChange={v => set({ ttsRate: v })} min={0.5} max={2.0} step={0.05} valueLabel={`${a.ttsRate.toFixed(2)}×`} />
          <SliderRow color="#8B5CF6" label="Pitch" hint="0.5 = deep → 2.0 = high (0.9 = warm male)"
            value={a.ttsPitch} onChange={v => set({ ttsPitch: v })} min={0.5} max={2.0} step={0.05} valueLabel={`${a.ttsPitch.toFixed(2)}`} />
        </Section>

        <View style={{ padding: 14 }}>
          <ActionButton icon="play" label="▶ Preview sample" color="#8B5CF6" onPress={() => {
            if (a.jeevesPersonaEnabled !== false) {
              jeevesSpeak(sampleText, { context: 'lesson' });
            } else {
              ttsSpeak(sampleText);
            }
          }} />
          <View style={{ height: 8 }} />
          <ActionButton icon="bulb" label="🎩 Hear Jeeves greet you" kind="ghost" onPress={async () => {
            const phrase = await jeevesCatchphrase('greeting');
            if (phrase) jeevesSpeak('Pleased to make your acquaintance.', { context: 'greeting' });
          }} />
          <View style={{ height: 8 }} />
          <ActionButton icon="bookmark" label="📜 Quote of the moment" kind="ghost" onPress={async () => {
            const q = await getRandomQuote();
            if (q) jeevesSpeak(`${q.quote} — ${q.author}.`, { context: 'quote' as any, prependCatchphrase: false });
          }} />
          <View style={{ height: 8 }} />
          <ActionButton icon="stop" label="Stop" kind="ghost" onPress={() => ttsStop()} />
        </View>

        <Section title="Reading ergonomics" hint="For when you're reading with your eyes instead of your ears.">
          <SliderRow color="#8B5CF6" label="Font size" hint="Larger = easier on the eyes"
            value={a.fontSize} onChange={v => set({ fontSize: Math.round(v) })} min={12} max={28} step={1} valueLabel={`${a.fontSize}pt`} />
          <SliderRow color="#8B5CF6" label="Line height" hint="Breathing room between lines"
            value={a.lineHeight} onChange={v => set({ lineHeight: v })} min={1.0} max={2.2} step={0.05} valueLabel={`${a.lineHeight.toFixed(2)}`} />
          <SwitchRow icon="contrast" color="#8B5CF6" label="High contrast" hint="Brighter foreground for low-vision reading"
            value={a.highContrast} onValueChange={v => set({ highContrast: v })} />
        </Section>

        {/* 100-slider Academy Mastery cockpit — collapsible to keep render cheap. */}
        <DnaCockpit
          title="Academy Mastery"
          groups={ACADEMY_DNA_GROUPS}
          dna={a.masteryDna}
          onChange={setAcademyDna}
          onResetGroup={resetAcademyDnaGroup}
          onResetAll={resetAcademyDna}
          accent="#8B5CF6"
          previewEndpoint="/api/dna/preview/academy"
        />
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#141414' },
  header: { flexDirection: 'row', alignItems: 'center', padding: 12, backgroundColor: '#262626', borderBottomWidth: 1, borderBottomColor: '#404040' },
  headerBtn: { width: 44, height: 44, justifyContent: 'center', alignItems: 'center' },
  headerTitle: { flex: 1, textAlign: 'center', fontSize: 18, fontWeight: '700', color: '#F8FAFC' },
  genderRow: { flexDirection: 'row', gap: 8, paddingHorizontal: 14, paddingVertical: 8 },
  genderPill: {
    flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6,
    paddingVertical: 10, borderRadius: 12, backgroundColor: '#404040', borderWidth: 1, borderColor: '#475569',
  },
  genderPillActive: { backgroundColor: '#10B981', borderColor: '#10B981' },
  genderTxt: { color: '#CBD5E1', fontSize: 12, fontWeight: '800' },
});
