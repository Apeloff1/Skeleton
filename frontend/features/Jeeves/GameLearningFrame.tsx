import React, { useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, Image, Platform, Text, View } from 'react-native';
import Svg, { Line, Rect } from 'react-native-svg';
import { CryptoDigestAlgorithm, digest } from 'expo-crypto';
import s, { gameLearningColors as C } from './GameLearningWorkspace.styles';

type Frame = Record<string, unknown>;
type Run = { x: number; y: number; width: number; color: string };
function dimensions(frame: Frame): { width: number; height: number } | null {
  let width = frame.width; let height = frame.height;
  if ((!width || !height) && Array.isArray(frame.draw_commands)) {
    const background = frame.draw_commands.find(command => command?.kind === 'rect' && command.values?.[0] === 0 && command.values?.[1] === 0);
    width = background?.values?.[2]; height = background?.values?.[3];
  }
  return typeof width === 'number' && typeof height === 'number' && Number.isSafeInteger(width) && Number.isSafeInteger(height)
    && width > 0 && height > 0 && width <= 2048 && height <= 2048 ? { width, height } : null;
}
function rawPixels(frame: Frame, width: number, height: number) {
  const channels = frame.format === 'gray8' ? 1 : frame.format === 'rgb24' ? 3 : frame.format === 'rgba32' ? 4 : 0;
  if (!channels || width * height > 262144 || typeof frame.pixels_base64 !== 'string' || frame.pixels_base64.length > 1400000
    || frame.pixels_base64.length % 4 || !/^[A-Za-z0-9+/]*={0,2}$/.test(frame.pixels_base64) || typeof atob !== 'function') return null;
  const raw = atob(frame.pixels_base64);
  if (raw.length !== width * height * channels) throw new Error('The frame byte count does not match its dimensions.');
  return { channels, bytes: Uint8Array.from(raw, character => character.charCodeAt(0)) };
}
function pixelRuns(bytes: Uint8Array, channels: number, width: number, height: number) {
  const runs: Run[] = [];
  const color = (offset: number) => channels === 1 ? `rgb(${bytes[offset]},${bytes[offset]},${bytes[offset]})`
    : channels === 4 ? `rgba(${bytes[offset]},${bytes[offset + 1]},${bytes[offset + 2]},${bytes[offset + 3] / 255})`
      : `rgb(${bytes[offset]},${bytes[offset + 1]},${bytes[offset + 2]})`;
  for (let y = 0; y < height; y++) {
    let start = 0; let previous = color(y * width * channels);
    for (let x = 1; x <= width; x++) {
      const next = x === width ? '' : color((y * width + x) * channels);
      if (next !== previous) {
        runs.push({ x: start, y, width: x - start, color: previous });
        if (runs.length > 20000) throw new Error('This frame exceeds the mobile preview bound.');
        start = x; previous = next;
      }
    }
  }
  return runs;
}

/** Display returned pixels or bounded command geometry, never an invented frame. */
export default function GameLearningFrame({ frame }: { frame: Frame }) {
  const size = useMemo(() => dimensions(frame), [frame]);
  const [uri, setUri] = useState<string | null>(null);
  const [runs, setRuns] = useState<Run[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  useEffect(() => {
    let active = true; setUri(null); setRuns(null); setError(null); setLoading(false);
    if (!size || !frame.pixels_base64) return;
    setLoading(true);
    void (async () => {
      const pixels = rawPixels(frame, size.width, size.height);
      if (!pixels) throw new Error('This framebuffer format cannot be previewed on this device.');
      if (typeof frame.pixel_digest === 'string') {
        const buffer = await digest(CryptoDigestAlgorithm.SHA256, pixels.bytes as unknown as BufferSource);
        const sha = Array.from(new Uint8Array(buffer), byte => byte.toString(16).padStart(2, '0')).join('');
        if (sha !== frame.pixel_digest) throw new Error('The returned frame failed its content identity check.');
      }
      if (!active) return;
      if (Platform.OS === 'web' && typeof document !== 'undefined') {
        const canvas = document.createElement('canvas'); canvas.width = size.width; canvas.height = size.height;
        const context = canvas.getContext('2d');
        if (context) {
          const image = context.createImageData(size.width, size.height);
          for (let pixel = 0; pixel < size.width * size.height; pixel++) {
            const source = pixel * pixels.channels; const target = pixel * 4;
            image.data[target] = pixels.bytes[source];
            image.data[target + 1] = pixels.bytes[source + (pixels.channels > 1 ? 1 : 0)];
            image.data[target + 2] = pixels.bytes[source + (pixels.channels > 1 ? 2 : 0)];
            image.data[target + 3] = pixels.channels === 4 ? pixels.bytes[source + 3] : 255;
          }
          context.putImageData(image, 0, 0); setUri(canvas.toDataURL('image/png')); return;
        }
      }
      setRuns(pixelRuns(pixels.bytes, pixels.channels, size.width, size.height));
    })().catch(caught => { if (active) setError(caught instanceof Error ? caught.message : 'This frame could not be displayed.'); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [frame, size]);
  const commands = Array.isArray(frame.draw_commands) ? frame.draw_commands.slice(0, 512) : [];
  const geometry = size && commands.filter(command => (command.kind === 'rect' || command.kind === 'line') && Array.isArray(command.values)
    && command.values.length >= 5 && command.values.slice(0, 5).every((value: unknown) => typeof value === 'number' && Number.isFinite(value) && Math.abs(value) <= 100000));
  if (typeof frame.data_uri === 'string' && frame.data_uri.length <= 2 * 1024 * 1024 && /^data:image\/png;base64,[A-Za-z0-9+/]+={0,2}$/.test(frame.data_uri)) return <View style={{ width: '100%', gap: 8 }}>
    <Image source={{ uri: frame.data_uri }} style={s.frame} resizeMode="contain" accessibilityLabel="Actual generated game raster returned by the engine" /><Text style={s.dim}>Measured generated-game frame</Text>
  </View>;
  if (!size || !frame.pixels_base64 && !geometry?.length) return <Text style={s.muted}>This runtime reports render commands and scene state rather than a raster frame.</Text>;
  return <View style={{ width: '100%', gap: 8 }}>
    {loading ? <ActivityIndicator color={C.primaryHover} /> : error ? <Text style={s.muted}>{error}</Text> : uri ?
      <Image source={{ uri }} resizeMode="contain" style={s.frame} accessibilityLabel="Actual returned engine framebuffer" /> :
      <Svg width="100%" height={280} viewBox={`0 0 ${size.width} ${size.height}`} accessibilityLabel={runs ? 'Actual returned engine framebuffer' : 'Reference render command geometry'}>
        {runs ? runs.map((run, index) => <Rect key={index} x={run.x} y={run.y} width={run.width} height={1} fill={run.color} />) : geometry &&
          geometry.map((command, index) => command.kind === 'rect' ? <Rect key={index} x={command.values[0]} y={command.values[1]} width={Math.max(0, command.values[2])} height={Math.max(0, command.values[3])}
            fill={command.values[4] === 0 ? C.bg : C.text} /> : <Line key={index} x1={command.values[0]} y1={command.values[1]} x2={command.values[2]} y2={command.values[3]} stroke={C.text} strokeWidth={1} />)}
      </Svg>}
    <Text style={s.dim}>{frame.pixels_base64 ? frame.experimental ? 'Experimental ROM framebuffer' : 'Measured raster frame' : 'Reference command geometry · schematic colours'}</Text>
  </View>;
}
