import React from 'react';
import { ActivityIndicator, Platform, Text, View } from 'react-native';
import { subscribeAuthChanges } from '../../auth/gameforgeAuth';
import {
  loadPlayableDocument, playableMessage, playableNativeNavigation,
  PLAYABLE_FRAME_ALLOW, PLAYABLE_FRAME_SANDBOX, PLAYABLE_NATIVE_ORIGIN,
} from '../../product/playablePreview';

let NativeWebView: any = null;
function nativeWebView() {
  if (NativeWebView) return NativeWebView;
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    NativeWebView = require('react-native-webview').WebView;
  } catch { /* An unavailable native adapter keeps a recoverable preview state. */ }
  return NativeWebView;
}

export default function GamePreview({ uri, testID, onGameError }: {
  uri: string; testID?: string; onGameError?: (message: string) => void;
}) {
  const [document, setDocument] = React.useState<{ html: string; generation: number } | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const frame = React.useRef<HTMLIFrameElement | null>(null);
  const native = React.useRef<any>(null);
  const generation = React.useRef(0);
  const report = React.useRef(onGameError);
  report.current = onGameError;

  React.useEffect(() => {
    const request = new AbortController();
    let active = true;
    const currentGeneration = ++generation.current;
    const clear = () => {
      active = false;
      generation.current++;
      request.abort();
      // Clear visible private bytes before React schedules its next render.
      if (frame.current) { frame.current.style.visibility = 'hidden'; frame.current.srcdoc = ''; frame.current.src = 'about:blank'; }
      try { native.current?.stopLoading?.(); native.current?.injectJavaScript?.("document.open();document.close();true;"); } catch {}
      setDocument(null);
    };
    setDocument(null); setError(null);
    const unsubscribe = subscribeAuthChanges(() => {
      clear();
      setError('Your account changed. Open the game again to load its preview.');
    });
    void loadPlayableDocument(uri, request.signal).then(html => {
      if (active && !request.signal.aborted) setDocument({ html, generation: currentGeneration });
    }).catch(() => {
      if (active && !request.signal.aborted) setError('The game preview could not be loaded. Sign in and open the game again.');
    });
    return () => { clear(); unsubscribe(); };
  }, [uri]);

  React.useEffect(() => {
    if (Platform.OS !== 'web' || typeof window === 'undefined' || !document) return;
    const handler = (event: MessageEvent) => {
      if (document.generation !== generation.current) return;
      const message = playableMessage(event, frame.current?.contentWindow);
      if (message !== null) report.current?.(message);
    };
    window.addEventListener('message', handler);
    return () => window.removeEventListener('message', handler);
  }, [document]);

  if (!document) return <View testID={testID ? `${testID}-loading` : undefined} style={{ flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: '#000' }}>{error ? <Text accessibilityRole="alert" style={{ color: '#94a3b8', fontSize: 12 }}>{error}</Text> : <ActivityIndicator color="#94a3b8" />}</View>;
  if (Platform.OS === 'web') return React.createElement('iframe', {
    key: document.generation, ref: frame, srcDoc: document.html, title: 'game-preview', 'data-testid': testID,
    sandbox: PLAYABLE_FRAME_SANDBOX, allow: PLAYABLE_FRAME_ALLOW, allowFullScreen: true,
    referrerPolicy: 'no-referrer', credentialless: 'true',
    style: { border: 0, background: '#000', width: '100%', height: '100%' },
  });
  const WebView = nativeWebView();
  if (!WebView) return <View style={{ flex: 1, backgroundColor: '#000' }}><Text style={{ color: '#94a3b8' }}>Preview unavailable on this device</Text></View>;
  // Static HTML needs wildcard admission in this adapter. The navigation
  // callback admits only its isolated bootstrap URL, never an application URL.
  return <WebView key={document.generation} ref={native} testID={testID} source={{ html: document.html, baseUrl: PLAYABLE_NATIVE_ORIGIN }}
    style={{ flex: 1, backgroundColor: '#000' }} originWhitelist={['*']}
    onShouldStartLoadWithRequest={(event: { url: string }) => playableNativeNavigation(event.url)}
    javaScriptEnabled domStorageEnabled={false} incognito cacheEnabled={false}
    sharedCookiesEnabled={false} thirdPartyCookiesEnabled={false}
    allowFileAccess={false} allowFileAccessFromFileURLs={false} allowUniversalAccessFromFileURLs={false}
    mixedContentMode="never" setSupportMultipleWindows={false} javaScriptCanOpenWindowsAutomatically={false}
    scalesPageToFit={false} allowsInlineMediaPlayback mediaPlaybackRequiresUserAction={false}
    onMessage={(event: { nativeEvent?: { data?: string } }) => {
      if (document.generation !== generation.current) return;
      try {
        const data = JSON.parse(event.nativeEvent?.data || '{}');
        // Native bridge messages already belong to this WebView instance.
        const message = playableMessage({ source: native.current, origin: 'null', data }, native.current);
        if (message !== null) report.current?.(message);
      } catch { /* Ignore malformed game messages. */ }
    }} />;
}
