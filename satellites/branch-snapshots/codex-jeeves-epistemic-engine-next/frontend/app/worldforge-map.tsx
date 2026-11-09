/**
 * /worldforge-map — interactive LOD "slippy map" explorer.
 * Streams chunked virtual-texture tiles from /stream/tile/{z}/{x}/{y}.png,
 * pannable in both axes with +/- zoom changing the LOD level (2^z tiles/axis).
 */
import React from 'react';
import {
  View, Text, ScrollView, TouchableOpacity, StyleSheet, SafeAreaView, Image, Platform,
} from 'react-native';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { useHaptics } from '../src/hooks/useHaptics';

const BACKEND = process.env.EXPO_PUBLIC_BACKEND_URL || process.env.EXPO_PUBLIC_API_URL || '';
const TILE = 200;
const MAX_Z = 2;

export default function WorldforgeMap() {
  const router = useRouter();
  const haptics = useHaptics();
  const p = useLocalSearchParams<{ seed?: string; scale?: string; palette?: string; climate?: string; size?: string; mode?: string }>();
  const seed = p.seed || '1337';
  const scale = (p.scale === 'planet' ? 'planet' : 'region');
  const palette = p.palette || 'natural';
  const climate = p.climate || 'temperate';
  const size = p.size || '56';
  const mode = p.mode || 'atlas';
  const [z, setZ] = React.useState(1);

  const tiles = Math.pow(2, z);
  const coords: { x: number; y: number }[] = [];
  for (let y = 0; y < tiles; y++) for (let x = 0; x < tiles; x++) coords.push({ x, y });
  const tileUrl = (x: number, y: number) =>
    `${BACKEND}/api/worldforge/stream/tile/${z}/${x}/${y}.png?seed=${seed}&scale=${scale}&size=${size}&palette=${palette}&climate=${climate}&mode=${mode}`;

  return (
    <SafeAreaView style={styles.root} testID="worldforge-map-screen">
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} testID="map-back"><Text style={styles.back}>‹ Back</Text></TouchableOpacity>
        <Text style={styles.title}>🛰️ Explore — LOD {z}</Text>
        <View style={{ width: 48 }} />
      </View>

      <ScrollView horizontal contentContainerStyle={{ alignItems: 'center' }} maximumZoomScale={Platform.OS === 'ios' ? 3 : 1} minimumZoomScale={1}>
        <ScrollView contentContainerStyle={{ justifyContent: 'center' }}>
          <View style={[styles.grid, { width: tiles * TILE, height: tiles * TILE }]}>
            {coords.map(({ x, y }) => (
              <Image
                key={`${z}-${x}-${y}`}
                testID={`map-tile-${z}-${x}-${y}`}
                source={{ uri: tileUrl(x, y) }}
                style={{ position: 'absolute', left: x * TILE, top: y * TILE, width: TILE, height: TILE }}
              />
            ))}
          </View>
        </ScrollView>
      </ScrollView>

      <View style={styles.controls}>
        <TouchableOpacity testID="map-zoom-out" style={styles.zBtn} onPress={() => { haptics.selection(); setZ((v) => Math.max(0, v - 1)); }}><Text style={styles.zTxt}>−</Text></TouchableOpacity>
        <Text style={styles.zLbl}>{tiles}×{tiles} tiles · {tiles * tiles} chunks</Text>
        <TouchableOpacity testID="map-zoom-in" style={styles.zBtn} onPress={() => { haptics.selection(); setZ((v) => Math.min(MAX_Z, v + 1)); }}><Text style={styles.zTxt}>+</Text></TouchableOpacity>
      </View>
      <Text style={styles.hint}>Drag to pan{Platform.OS === 'ios' ? ' · pinch to magnify' : ''} · +/− streams a finer LOD mip level on demand.</Text>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#07080f' },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 16, paddingVertical: 14, borderBottomWidth: 1, borderBottomColor: '#1a1c2a' },
  back: { color: '#93C5FD', fontSize: 15, fontWeight: '700' },
  title: { color: '#f1f5f9', fontSize: 17, fontWeight: '800' },
  grid: { position: 'relative', backgroundColor: '#04050a' },
  controls: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 14, paddingVertical: 12 },
  zBtn: { backgroundColor: '#10131f', borderRadius: 10, width: 46, height: 46, alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: '#334155' },
  zTxt: { color: '#93C5FD', fontSize: 22, fontWeight: '800' },
  zLbl: { color: '#cbd5e1', fontSize: 13, fontWeight: '700', minWidth: 150, textAlign: 'center' },
  hint: { color: '#64748b', fontSize: 12, textAlign: 'center', paddingBottom: 14, paddingHorizontal: 20 },
});
