import React, { useEffect, useRef, useState, useSyncExternalStore } from 'react';
import { Image, Platform, View, type ImageProps, type NativeSyntheticEvent, type ImageErrorEventData } from 'react-native';
import * as Clipboard from 'expo-clipboard';
import { getAuthEpoch, subscribeAuthChanges } from '../auth/gameforgeAuth';
import { loadPrivateImage } from '../product/privateImage';

export type PrivateImageProps = Omit<ImageProps, 'source'> & { uri: string; fallback?: React.ReactNode };

/** Each render owns only bytes for this exact URL/account. Image elements never
 * receive bearer URLs or depend on browser support for native image headers. */
export default function PrivateImage({ uri, fallback, onError, ...props }: PrivateImageProps) {
  const epoch = useSyncExternalStore(subscribeAuthChanges, getAuthEpoch, getAuthEpoch);
  const [loaded, setLoaded] = useState<{ uri: string; epoch: number; data: string } | null>(null);
  const errorHandler = useRef(onError); errorHandler.current = onError;
  const lifecycle = useRef({ start: props.onLoadStart, end: props.onLoadEnd });
  lifecycle.current = { start: props.onLoadStart, end: props.onLoadEnd };
  useEffect(() => {
    const controller = new AbortController(); let active = true;
    setLoaded(null);
    lifecycle.current.start?.();
    void loadPrivateImage(uri, controller.signal).then(data => {
      if (active && !controller.signal.aborted && epoch === getAuthEpoch()) setLoaded({ uri, epoch, data });
    }, error => {
      if (!active || controller.signal.aborted || epoch !== getAuthEpoch()) return;
      errorHandler.current?.({ nativeEvent: { error: error instanceof Error ? error.message : 'Private image unavailable.' } } as NativeSyntheticEvent<ImageErrorEventData>);
      lifecycle.current.end?.();
    });
    return () => { active = false; controller.abort(); };
  }, [uri, epoch]);
  if (!loaded || loaded.uri !== uri || loaded.epoch !== epoch) {
    return fallback ? <>{fallback}</> : <View style={props.style} testID={props.testID} accessibilityLabel={props.accessibilityLabel} />;
  }
  return <Image {...props} source={{ uri: loaded.data }} onLoadStart={undefined} onError={event => {
    if (loaded.epoch !== getAuthEpoch() || loaded.uri !== uri) return;
    setLoaded(null); errorHandler.current?.(event);
  }} />;
}

/** Explicit user export: authenticated bounded bytes, never a private API link.
 * Native uses the existing image clipboard rather than a persistent temp cache. */
export async function savePrivateImage(uri: string, fileName = 'image.png'): Promise<'saved' | 'copied'> {
  const epoch = getAuthEpoch();
  const current = () => { if (epoch !== getAuthEpoch()) throw new Error('Private image export cancelled because the account changed.'); };
  const data = await loadPrivateImage(uri);
  current();
  if (Platform.OS === 'web' && typeof document !== 'undefined') {
    const link = document.createElement('a'); link.href = data;
    link.download = fileName.replace(/[^A-Za-z0-9_.-]/g, '_').slice(0, 128) || 'image.png';
    document.body.appendChild(link);
    try { current(); link.click(); return 'saved'; } finally { link.remove(); }
  }
  current();
  await Clipboard.setImageAsync(data.slice(data.indexOf(',') + 1));
  current(); return 'copied';
}
