import React, { useMemo, useRef, useState } from 'react';
import { Platform, Text, TouchableOpacity, View } from 'react-native';
import { type LearningFile } from '../../product/gameLearningClient';
import { successorPreviewDocument } from './successorPreviewDocument';
import s, { gameLearningColors as C } from './GameLearningWorkspace.styles';

/** Derived, opaque-origin preview of the exact emitted local game files. */
export default function GameSuccessorPreview({ files, title }: { files: LearningFile[]; title: string }) {
  const [open, setOpen] = useState(false); const [revision, setRevision] = useState(0);
  const iframe = useRef<HTMLIFrameElement | null>(null); const [displayError, setDisplayError] = useState<string | null>(null);
  const html = useMemo(() => successorPreviewDocument(files), [files]);
  if (Platform.OS !== 'web' || !html) return <Text style={s.muted}>Adopt the saved game and use Play & observe for this device’s actual game preview.</Text>;
  return <View style={{ gap: 12 }}><View style={s.chips}><TouchableOpacity accessibilityRole="button" onPress={() => setOpen(value => !value)} style={s.button}><Text style={s.buttonText}>{open ? 'Close browser preview' : 'Play browser build preview'}</Text></TouchableOpacity>{open && <><TouchableOpacity accessibilityRole="button" onPress={() => setRevision(value => value + 1)} style={s.button}><Text style={s.buttonText}>Restart preview</Text></TouchableOpacity><TouchableOpacity accessibilityRole="button" onPress={() => { if (!iframe.current?.requestFullscreen) { setDisplayError('Full-screen display is unavailable in this browser.'); return; } void iframe.current.requestFullscreen().catch(() => setDisplayError('The browser did not allow full-screen display.')); }} style={s.button}><Text style={s.buttonText}>Play full screen</Text></TouchableOpacity></>}</View>
    {!!displayError && <Text style={s.unavailable}>{displayError}</Text>}
    {open && <><iframe ref={iframe} key={revision} title={title + ' — isolated game preview'} srcDoc={html} sandbox="allow-scripts" allow="fullscreen" allowFullScreen referrerPolicy="no-referrer" style={{ width: '100%', height: 960, border: 0, borderRadius: 12, backgroundColor: C.bg }} />
      <Text style={s.dim}>Browser preview starts fresh when closed. Use Play & observe to record demonstrations or train the saved game. Downloaded desktop games have their own local saves.</Text></>}
  </View>;
}
