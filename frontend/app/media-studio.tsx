/**
 * /media-studio — Jeeves in-game Media Studio.
 * Generates REAL in-game images (main character, cast, promos, landscapes) and
 * actual-gameplay videos (30s / 120s / 2-min trailer / 1-min showcase / 5-min
 * let's-play w/ commentary) rendered from the game's own world.
 */
import React from 'react';
import {
  View, Text, StyleSheet, SafeAreaView, ScrollView, TouchableOpacity,
  ActivityIndicator, TextInput, Image, Linking,
} from 'react-native';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useVideoPlayer, VideoView } from 'expo-video';
import api from '../src/utils/apiClient';

const BG = '#0b1220', CARD = '#111a2e', PURPLE = '#7c3aed', GREEN = '#22c55e', AMBER = '#f59e0b', MUTE = '#64748b', FG = '#e2e8f0';
const BASE = (process.env.EXPO_PUBLIC_BACKEND_URL || '').replace(/\/$/, '');

const VIDEO_TYPES = [
  { id: 'clip30', label: '30s Gameplay', icon: 'game-controller-outline' },
  { id: 'clip120', label: '120s Gameplay', icon: 'game-controller' },
  { id: 'trailer', label: '2-min Trailer', icon: 'film-outline' },
  { id: 'showcase', label: '1-min Showcase', icon: 'sparkles-outline' },
  { id: 'letsplay', label: "5-min Let's Play", icon: 'mic-outline' },
];

function VideoPlayerCard({ url }: { url: string }) {
  const player = useVideoPlayer(url, (p) => { p.loop = true; });
  return <VideoView style={st.video} player={player} allowsFullscreen contentFit="contain" />;
}

export default function MediaStudio() {
  const router = useRouter();
  const params = useLocalSearchParams<{ game?: string }>();
  const [game, setGame] = React.useState(params.game || 'Ember Vanguard');
  const [imgBusy, setImgBusy] = React.useState(false);
  const [images, setImages] = React.useState<any[]>([]);
  const [job, setJob] = React.useState<any>(null);
  const [vType, setVType] = React.useState<string>('');
  const pollRef = React.useRef<any>(null);

  const genImages = async () => {
    setImgBusy(true); setImages([]);
    const r = await api.post<any>('/api/jeeves/media/images', { game_name: game }, { timeoutMs: 60000 });
    if (r.ok) setImages(r.data.images || []);
    setImgBusy(false);
  };

  const stopPoll = () => { if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; } };

  const genVideo = async (type: string) => {
    stopPoll();
    setVType(type); setJob({ status: 'rendering', percent: 0 });
    const r = await api.post<any>('/api/jeeves/media/video', { game_name: game, type }, { timeoutMs: 30000 });
    if (!r.ok) { setJob({ status: 'error' }); return; }
    const id = r.data.job_id;
    pollRef.current = setInterval(async () => {
      const s = await api.get<any>(`/api/jeeves/media/video/${id}`);
      if (s.ok) {
        setJob(s.data);
        if (s.data.status === 'done' || s.data.status === 'error') stopPoll();
      }
    }, 3000);
  };

  React.useEffect(() => () => stopPoll(), []);

  const videoUrl = job?.status === 'done' && job?.job_id ? `${BASE}/api/jeeves/media/download/${job.job_id}` : null;

  return (
    <SafeAreaView style={st.safe}>
      <View style={st.header}>
        <TouchableOpacity onPress={() => router.back()} testID="back-btn"><Ionicons name="chevron-back" size={26} color={FG} /></TouchableOpacity>
        <View style={{ flex: 1 }}>
          <Text style={st.title}>Media Studio</Text>
          <Text style={st.sub}>Actual in-game images &amp; gameplay video</Text>
        </View>
        <Ionicons name="videocam" size={22} color={PURPLE} />
      </View>

      <ScrollView contentContainerStyle={{ padding: 12, paddingBottom: 40 }}>
        <View style={st.card}>
          <Text style={st.lbl}>Game</Text>
          <TextInput style={st.input} value={game} onChangeText={setGame} testID="game-input"
            placeholder="Game name" placeholderTextColor={MUTE} />
          <TouchableOpacity style={[st.btn, { backgroundColor: PURPLE }]} onPress={genImages} disabled={imgBusy} testID="gen-images">
            {imgBusy ? <ActivityIndicator color="#fff" /> : <Text style={st.btnTxt}>Generate In-Game Image Set (23)</Text>}
          </TouchableOpacity>
        </View>

        {images.length > 0 && (
          <View style={st.grid}>
            {images.map((im) => (
              <View key={im.key} style={st.tile}>
                <Image source={{ uri: `data:${im.mime};base64,${im.base64}` }} style={st.tileImg} resizeMode="cover" />
                <Text style={st.tileLbl} numberOfLines={1}>{im.title}</Text>
              </View>
            ))}
          </View>
        )}

        <View style={[st.card, { marginTop: 14 }]}>
          <Text style={st.lbl}>Gameplay Video</Text>
          <View style={st.vRow}>
            {VIDEO_TYPES.map((v) => (
              <TouchableOpacity key={v.id} testID={`video-${v.id}`}
                onPress={() => genVideo(v.id)}
                style={[st.vBtn, vType === v.id && { borderColor: GREEN, backgroundColor: GREEN + '18' }]}>
                <Ionicons name={v.icon as any} size={16} color={vType === v.id ? GREEN : FG} />
                <Text style={[st.vTxt, vType === v.id && { color: GREEN }]}>{v.label}</Text>
              </TouchableOpacity>
            ))}
          </View>

          {job && job.status === 'rendering' && (
            <View style={{ marginTop: 14 }}>
              <Text style={st.sub}>Rendering actual gameplay… {job.percent || 0}%</Text>
              <View style={st.track}><View style={[st.fill, { width: `${job.percent || 0}%` }]} /></View>
            </View>
          )}
          {job && job.status === 'error' && <Text style={[st.sub, { color: '#ef4444', marginTop: 10 }]}>Render failed.</Text>}
          {videoUrl && (
            <View style={{ marginTop: 14 }}>
              <VideoPlayerCard url={videoUrl} />
              <View style={{ flexDirection: 'row', gap: 8, marginTop: 8 }}>
                {job.has_commentary && (
                  <View style={[st.chip, { backgroundColor: AMBER + '22' }]}>
                    <Ionicons name="mic" size={12} color={AMBER} /><Text style={[st.chipTxt, { color: AMBER }]}>commentary</Text>
                  </View>
                )}
                <View style={[st.chip, { backgroundColor: GREEN + '22' }]}>
                  <Text style={[st.chipTxt, { color: GREEN }]}>{Math.round((job.size_bytes || 0) / 1024)} KB · {job.frames} frames</Text>
                </View>
                <TouchableOpacity style={{ marginLeft: 'auto' }} onPress={() => Linking.openURL(videoUrl)}>
                  <Ionicons name="download-outline" size={20} color={FG} />
                </TouchableOpacity>
              </View>
            </View>
          )}
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const st = StyleSheet.create({
  safe: { flex: 1, backgroundColor: BG },
  header: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingHorizontal: 12, paddingVertical: 12, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: '#1f2937' },
  title: { color: FG, fontSize: 18, fontWeight: '800' },
  sub: { color: MUTE, fontSize: 12 },
  card: { backgroundColor: CARD, borderRadius: 14, padding: 14, borderColor: '#1f2937', borderWidth: 1 },
  lbl: { color: FG, fontSize: 14, fontWeight: '700', marginBottom: 8 },
  input: { backgroundColor: BG, borderColor: '#334155', borderWidth: 1, borderRadius: 10, paddingHorizontal: 12, paddingVertical: 10, color: FG, fontSize: 14, marginBottom: 12 },
  btn: { borderRadius: 10, paddingVertical: 12, alignItems: 'center' },
  btnTxt: { color: '#fff', fontWeight: '700', fontSize: 14 },
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 12 },
  tile: { width: '48%', backgroundColor: CARD, borderRadius: 10, overflow: 'hidden', borderColor: '#1f2937', borderWidth: 1 },
  tileImg: { width: '100%', height: 96, backgroundColor: BG },
  tileLbl: { color: FG, fontSize: 11, padding: 6 },
  vRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  vBtn: { flexDirection: 'row', alignItems: 'center', gap: 5, borderColor: '#334155', borderWidth: 1, borderRadius: 10, paddingHorizontal: 10, paddingVertical: 8 },
  vTxt: { color: FG, fontSize: 12, fontWeight: '600' },
  track: { height: 8, backgroundColor: BG, borderRadius: 4, marginTop: 6, overflow: 'hidden' },
  fill: { height: 8, backgroundColor: PURPLE },
  video: { width: '100%', height: 200, backgroundColor: '#000', borderRadius: 10 },
  chip: { flexDirection: 'row', alignItems: 'center', gap: 4, borderRadius: 6, paddingHorizontal: 8, paddingVertical: 3 },
  chipTxt: { fontSize: 11, fontWeight: '700' },
});
