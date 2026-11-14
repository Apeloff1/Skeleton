import React, { useMemo, useRef, useState } from 'react';
import { Platform, Text, TouchableOpacity, View } from 'react-native';
import { type LearningFile } from '../../src/product/gameLearningClient';
import s, { gameLearningColors as C } from './GameLearningWorkspace.styles';

/** Derived, opaque-origin preview of the exact emitted local game files. */
export default function GameSuccessorPreview({ files, title }: { files: LearningFile[]; title: string }) {
  const [open, setOpen] = useState(false); const [revision, setRevision] = useState(0);
  const iframe = useRef<HTMLIFrameElement | null>(null); const [displayError, setDisplayError] = useState<string | null>(null);
  const html = useMemo(() => {
    const map = new Map(files.map(file => [file.path, file.content]));
    const entry = map.get('game/successor/index.html'); if (!entry || entry.length > 2 * 1024 * 1024) return null;
    let result = entry.replace(/<script\b([^>]*?)\bsrc=["']([^"']+)["']([^>]*)>\s*<\/script\s*>/gi, (_match, _before, source: string) => {
      const path = 'game/successor/' + source.replace(/^\.\//, '');
      if (source.includes('..') || /^[a-z]+:|^\//i.test(source) || !map.has(path)) return '';
      return '<script>' + map.get(path)!.replace(/<\/script/gi, '<\\/script') + '</script>';
    });
    result = result.replace(/<meta\b[^>]*http-equiv\s*=\s*["']?content-security-policy["']?[^>]*>/gi, '');
    const policy = `<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data: blob:; media-src data: blob:; connect-src 'none'; frame-src 'none'; object-src 'none'; form-action 'none'; base-uri 'none'">`;
    if (/<head\b[^>]*>/i.test(result)) result = result.replace(/<head\b[^>]*>/i, match => match + policy);
    else result = policy + result;
    return result.length <= 4 * 1024 * 1024 ? result : null;
  }, [files]);
  if (Platform.OS !== 'web' || !html) return <Text style={s.muted}>Adopt the saved game and use Play & observe for this device’s actual game preview.</Text>;
  return <View style={{ gap: 12 }}><View style={s.chips}><TouchableOpacity accessibilityRole="button" onPress={() => setOpen(value => !value)} style={s.button}><Text style={s.buttonText}>{open ? 'Close browser preview' : 'Play browser build preview'}</Text></TouchableOpacity>{open && <><TouchableOpacity accessibilityRole="button" onPress={() => setRevision(value => value + 1)} style={s.button}><Text style={s.buttonText}>Restart preview</Text></TouchableOpacity><TouchableOpacity accessibilityRole="button" onPress={() => { if (!iframe.current?.requestFullscreen) { setDisplayError('Full-screen display is unavailable in this browser.'); return; } void iframe.current.requestFullscreen().catch(() => setDisplayError('The browser did not allow full-screen display.')); }} style={s.button}><Text style={s.buttonText}>Play full screen</Text></TouchableOpacity></>}</View>
    {!!displayError && <Text style={s.unavailable}>{displayError}</Text>}
    {open && <><iframe ref={iframe} key={revision} title={title + ' — isolated game preview'} srcDoc={html} sandbox="allow-scripts" allow="fullscreen" allowFullScreen referrerPolicy="no-referrer" style={{ width: '100%', height: 960, border: 0, borderRadius: 12, backgroundColor: C.bg }} />
      <Text style={s.dim}>Browser preview starts fresh when closed. Use Play & observe to record demonstrations or train the saved game. Downloaded desktop games have their own local saves.</Text></>}
  </View>;
}
