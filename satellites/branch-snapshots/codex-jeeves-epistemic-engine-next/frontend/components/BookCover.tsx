/**
 * BookCover.tsx — "Bookflix" Netflix-style procedural cover art.
 *
 * Generates a deterministic, attractive cover for each book using
 * the title + author as a hash seed (no network needed). Each book
 * gets a unique colourway, monogram, and accent shape.
 */
import React, { useMemo } from 'react';
import { View, Text, StyleSheet, ViewStyle, Platform } from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { Ionicons } from '@expo/vector-icons';

// Curated set of duo-tone palettes that feel premium / streaming-service-y.
const PALETTES: [string, string, string][] = [
  ['#1e3a8a', '#7c3aed', '#A78BFA'], // royal indigo → violet
  ['#7c2d12', '#dc2626', '#FCA5A5'], // ember red
  ['#064e3b', '#10b981', '#6EE7B7'], // emerald forest
  ['#92400e', '#f59e0b', '#FCD34D'], // amber gold
  ['#1E3A8A', '#2563EB', '#93C5FD'], // cyan ocean
  ['#831843', '#ec4899', '#F9A8D4'], // raspberry
  ['#374151', '#3B82F6', '#93C5FD'], // graphite-azure
  ['#1f2937', '#84cc16', '#BEF264'], // moss
  ['#312e81', '#3B82F6', '#BFDBFE'], // midnight-sky
  ['#581c87', '#a855f7', '#D8B4FE'], // plum
  ['#7f1d1d', '#f97316', '#FED7AA'], // crimson-tang
  ['#134e4a', '#3B82F6', '#93C5FD'], // teal
  ['#365314', '#65a30d', '#BEF264'], // lime
  ['#701a75', '#d946ef', '#F0ABFC'], // magenta
  ['#0c4a6e', '#3b82f6', '#93C5FD'], // sapphire
];

// Pattern accents — emojis or icons sprinkled diagonally for visual interest.
const PATTERNS: string[] = ['▲', '◆', '●', '■', '★', '✦', '◇', '◯'];
const ICON_BY_GENRE: Record<string, any> = {
  computing: 'hardware-chip',
  history: 'time',
  science: 'flask',
  math: 'calculator',
  philosophy: 'bulb',
  programming: 'code-slash',
  algorithms: 'git-branch',
  ai: 'sparkles',
  fiction: 'book',
  default: 'book',
};

function hashString(s: string): number {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0;
  return Math.abs(h);
}

function pickPalette(seed: number): [string, string, string] {
  return PALETTES[seed % PALETTES.length];
}

function genreToIcon(title: string, author: string): any {
  const blob = (title + ' ' + author).toLowerCase();
  if (/(algorithm|complexity|sort)/.test(blob)) return ICON_BY_GENRE.algorithms;
  if (/(history|chronicle|origin)/.test(blob)) return ICON_BY_GENRE.history;
  if (/(ai|neural|machine|deep)/.test(blob)) return ICON_BY_GENRE.ai;
  if (/(math|number|calculus|geometr)/.test(blob)) return ICON_BY_GENRE.math;
  if (/(physic|chemistr|biolog|scien)/.test(blob)) return ICON_BY_GENRE.science;
  if (/(philosoph|moral|ethic)/.test(blob)) return ICON_BY_GENRE.philosophy;
  if (/(program|code|software|comput|engine)/.test(blob)) return ICON_BY_GENRE.computing;
  return ICON_BY_GENRE.default;
}

function monogram(title: string): string {
  const cleaned = title.replace(/[^a-zA-Z0-9 ]/g, '').trim();
  const parts = cleaned.split(/\s+/).filter(Boolean);
  if (parts.length === 0) return '?';
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

interface BookCoverProps {
  title: string;
  author?: string;
  /** Compact: square 64×64 thumb. Default: 96×140 portrait. Large: 132×190 hero. */
  size?: 'compact' | 'default' | 'large';
  /** Override seed string; defaults to title+author. */
  seed?: string;
  style?: ViewStyle;
}

export const BookCover: React.FC<BookCoverProps> = ({
  title, author = '', size = 'default', seed, style,
}) => {
  const dims = useMemo(() => {
    if (size === 'compact') return { w: 56, h: 56, br: 8,  mono: 18, ico: 14 };
    if (size === 'large')   return { w: 132, h: 190, br: 12, mono: 44, ico: 28 };
    return                         { w: 96, h: 140, br: 10, mono: 30, ico: 20 };
  }, [size]);

  const palette = useMemo(() => {
    const h = hashString(seed || (title + author));
    return pickPalette(h);
  }, [title, author, seed]);

  const accentChar = useMemo(() => {
    const h = hashString((seed || title) + 'p');
    return PATTERNS[h % PATTERNS.length];
  }, [title, seed]);

  const icon = useMemo(() => genreToIcon(title, author), [title, author]);
  const mono = useMemo(() => monogram(title), [title]);

  return (
    <View style={[
      { width: dims.w, height: dims.h, borderRadius: dims.br, overflow: 'hidden' },
      style,
    ]}>
      <LinearGradient
        colors={[palette[0], palette[1]]}
        start={{ x: 0, y: 0 }}
        end={{ x: 1, y: 1 }}
        style={StyleSheet.absoluteFillObject}
      />
      {/* Faint repeating accent pattern */}
      <View style={[StyleSheet.absoluteFillObject, { pointerEvents: 'none' }]}>
        <Text style={{ position: 'absolute', top: 4,  right: 6,  color: '#ffffff15', fontSize: dims.mono * 0.8, fontWeight: '900' }}>{accentChar}</Text>
        <Text style={{ position: 'absolute', bottom: 6, left: 6, color: '#ffffff10', fontSize: dims.mono * 1.4, fontWeight: '900' }}>{accentChar}</Text>
      </View>
      {/* Spine accent strip (left edge) */}
      <View style={{
        position: 'absolute', top: 0, bottom: 0, left: 0, width: 3,
        backgroundColor: palette[2], opacity: 0.85,
      }} />
      {/* Centered content */}
      <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', padding: 6 }}>
        <Ionicons name={icon} size={dims.ico} color={palette[2]} style={{ marginBottom: 2, opacity: 0.95 }} />
        <Text
          style={{
            color: '#FFFFFF',
            fontSize: dims.mono,
            fontWeight: '900',
            letterSpacing: 1,
            ...(Platform.OS === 'web' ? {
              // @ts-ignore — web-only style key
              textShadow: '0px 1px 3px #00000099',
            } : {
              textShadowColor: '#00000099',
              textShadowOffset: { width: 0, height: 1 },
              textShadowRadius: 3,
            }),
          }}
          numberOfLines={1}
        >
          {mono}
        </Text>
        {size !== 'compact' && (
          <Text
            style={{
              color: '#ffffffdd',
              fontSize: size === 'large' ? 10 : 8,
              fontWeight: '700',
              marginTop: 4,
              textAlign: 'center',
              letterSpacing: 0.4,
            }}
            numberOfLines={2}
          >
            {title.length > 36 ? title.slice(0, 34) + '…' : title}
          </Text>
        )}
      </View>
      {/* Bottom shimmer band — adds the streaming-service polish */}
      <LinearGradient
        colors={['transparent', '#00000055']}
        style={[{ position: 'absolute', left: 0, right: 0, bottom: 0, height: '30%' }, { pointerEvents: 'none' }]}
      />
    </View>
  );
};

export default BookCover;
