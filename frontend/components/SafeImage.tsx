/**
 * SafeImage — image component that never breaks layout on failure.
 *
 *   • Falls back to a placeholder when uri is null/empty.
 *   • Catches `onError` and swaps to a neutral grey placeholder.
 *   • Renders an ActivityIndicator while loading.
 *   • Optional `fallbackText` shown as initials when image fails (e.g.
 *     for avatars without a uri).
 *
 * Usage:
 *   <SafeImage uri={user.avatar} size={48} fallbackText={user.name} />
 *   <SafeImage uri={url} style={{ width: '100%', aspectRatio: 16/9 }} />
 */
import React, { useState } from 'react';
import { View, Image, ActivityIndicator, Text, StyleSheet, ImageStyle, StyleProp } from 'react-native';

export interface SafeImageProps {
  uri:           string | null | undefined;
  size?:         number;
  style?:        StyleProp<ImageStyle>;
  fallbackText?: string;
  /** Custom render when image fails. */
  fallback?:     React.ReactNode;
  /** Show ActivityIndicator while loading. Default true. */
  showLoader?:   boolean;
  /** Background colour for the placeholder. */
  bg?:           string;
}

export default function SafeImage({
  uri,
  size,
  style,
  fallbackText,
  fallback,
  showLoader = true,
  bg = '#1e293b',
}: SafeImageProps) {
  const [loading, setLoading] = useState(true);
  const [errored, setErrored] = useState(false);

  const dim = size != null ? { width: size, height: size, borderRadius: size / 8 } : null;
  const containerStyle = [styles.box, dim, { backgroundColor: bg }, style as any];

  if (!uri || errored) {
    return (
      <View style={containerStyle}>
        {fallback ?? (fallbackText ? <Text style={styles.initials}>{initials(fallbackText)}</Text> : null)}
      </View>
    );
  }

  return (
    <View style={containerStyle}>
      <Image
        source={{ uri }}
        style={StyleSheet.absoluteFill as any}
        onLoadEnd={() => setLoading(false)}
        onError={() => { setLoading(false); setErrored(true); }}
        resizeMode="cover"
      />
      {loading && showLoader && (
        <View style={[StyleSheet.absoluteFill as any, { pointerEvents: 'none' }]}>
          <ActivityIndicator style={styles.spinner} size="small" color="#94a3b8" />
        </View>
      )}
    </View>
  );
}

function initials(text: string): string {
  const parts = text.trim().split(/\s+/).filter(Boolean).slice(0, 2);
  return parts.map(p => p[0]?.toUpperCase() || '').join('') || '?';
}

const styles = StyleSheet.create({
  box:      { overflow: 'hidden', alignItems: 'center', justifyContent: 'center' },
  spinner:  { flex: 1, alignSelf: 'center' },
  initials: { color: '#e2e8f0', fontSize: 18, fontWeight: '800' },
});
