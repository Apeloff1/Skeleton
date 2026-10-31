import React, { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Platform, Text, TouchableOpacity, View } from 'react-native';
import * as DocumentPicker from 'expo-document-picker';
import { getAuthToken } from '../../auth/gameforgeAuth';
import { getLearningProject, learningRequestKey, type LearningProject } from '../../product/gameLearningClient';
import { completeGameContent, contentReceivedBytes, reserveGameContent, transferGameContent, withdrawGameContentUpload, type ContentFile, type ContentUpload, CONTENT_BUNDLE_LIMIT, CONTENT_FILE_LIMIT } from '../../product/gameContentClient';
import s, { gameLearningColors as C } from './GameLearningWorkspace.styles';
function bytes(value: number) { return value >= 1024 ** 3 ? `${(value / 1024 ** 3).toFixed(2)} GB` : `${(value / 1024 ** 2).toFixed(1)} MB`; }
function Button({ label, onPress, disabled, primary }: { label: string; onPress: () => void; disabled?: boolean; primary?: boolean }) { return <TouchableOpacity accessibilityRole="button" accessibilityState={{ disabled }} disabled={disabled} onPress={onPress} style={[s.button, primary && s.primaryButton, disabled && s.disabled]}><Text style={s.buttonText}>{label}</Text></TouchableOpacity>; }

export default function GameContentUpload({ project, rightsRefs, consent, disabled, onComplete, onBusy }: {
  project: LearningProject; rightsRefs: string[]; consent: boolean; disabled?: boolean;
  onComplete: (project: LearningProject) => void; onBusy?: (busy: boolean) => void;
}) {
  const [files, setFiles] = useState<ContentFile[]>([]); const [entrypoint, setEntrypoint] = useState('');
  const [upload, setUpload] = useState<ContentUpload | null>(null); const [busy, setBusy] = useState(false); const [error, setError] = useState<string | null>(null);
  const abort = useRef<AbortController | null>(null); const mounted = useRef(true); const busyCallback = useRef(onBusy); busyCallback.current = onBusy;
  const owner = useRef({ token: getAuthToken(), projectId: project.project_id }); const current = useRef(project); current.current = project;
  const activeTransfer = useRef(false);
  const reservation = useRef({ key: learningRequestKey('content'), fingerprint: '' });
  const safe = () => mounted.current && owner.current.token === getAuthToken() && owner.current.projectId === current.current.project_id;
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; abort.current?.abort(); if (activeTransfer.current) { activeTransfer.current = false; busyCallback.current?.(false); } }; }, []);
  const pick = async () => {
    const token = getAuthToken(); const id = project.project_id; setError(null);
    try {
      const result = await DocumentPicker.getDocumentAsync({ type: '*/*', multiple: true, copyToCacheDirectory: true });
      if (result.canceled || !safe() || token !== getAuthToken() || id !== current.current.project_id) return;
      if (result.assets.length > 64) throw new Error('Choose no more than 64 files for a content bundle.');
      const chosen: ContentFile[] = [];
      for (const asset of result.assets) {
        const file = asset.file; let blob: Blob | undefined;
        if (Platform.OS === 'web') {
          if (!file && !asset.uri.startsWith('blob:')) throw new Error('Choose files from your local device.');
          blob = file || await (await fetch(asset.uri)).blob();
        }
        const size = blob?.size ?? asset.size;
        if (!size || !Number.isSafeInteger(size) || size > CONTENT_FILE_LIMIT) throw new Error('Each content file must contain between 1 byte and 2 GB.');
        const path = asset.name.trim();
        if (!path || path.length > 256 || path.startsWith('/') || path.includes('\\') || path.split('/').some(part => !part || part === '.' || part === '..') || chosen.some(value => value.path === path)) throw new Error('Choose files with distinct safe names.');
        chosen.push({ path, bytes: size, uri: asset.uri, blob });
      }
      if (chosen.reduce((sum, file) => sum + file.bytes, 0) > CONTENT_BUNDLE_LIMIT) throw new Error('The whole content bundle must fit within 4 GB.');
      if (!safe() || token !== getAuthToken()) return;
      setFiles(chosen); setEntrypoint(chosen.find(file => /\.(m3u|cue)$/i.test(file.path))?.path || chosen[0]?.path || ''); setUpload(null); reservation.current = { key: learningRequestKey('content'), fingerprint: '' };
    } catch (caught) { if (safe()) setError(caught instanceof Error ? caught.message : 'The content files could not be selected.'); }
  };
  const transfer = async () => {
    if (busy || !consent || !rightsRefs.length || !files.length || !safe()) return;
    const controller = new AbortController(); abort.current = controller; activeTransfer.current = true; setBusy(true); busyCallback.current?.(true); setError(null);
    try {
      if (upload && reservation.current.fingerprint && JSON.stringify(rightsRefs) !== JSON.stringify(JSON.parse(reservation.current.fingerprint).rightsRefs)) throw new Error('Keep the original permission references while resuming, or withdraw this upload before changing them.');
      const fingerprint = JSON.stringify({ projectId: current.current.project_id, version: current.current.version, entrypoint, rightsRefs, files: files.map(file => ({ path: file.path, bytes: file.bytes })) });
      if (!upload && reservation.current.fingerprint !== fingerprint) reservation.current = { key: learningRequestKey('content'), fingerprint };
      const reserved = upload || await reserveGameContent(current.current, files, entrypoint, rightsRefs, controller.signal, reservation.current.key);
      if (!safe() || controller.signal.aborted) return; setUpload(reserved);
      const completed = await transferGameContent(reserved, files, value => { if (safe() && !controller.signal.aborted) setUpload(value); }, controller.signal);
      if (!safe() || controller.signal.aborted) return;
      setUpload(completed); await completeGameContent(completed.upload_id, controller.signal);
      const canonical = await getLearningProject(current.current.project_id, { signal: controller.signal });
      if (safe() && !controller.signal.aborted) { onComplete(canonical); setFiles([]); setEntrypoint(''); setUpload(null); }
    } catch (caught) { if (safe() && !controller.signal.aborted) setError(caught instanceof Error ? caught.message : 'The content upload could not be completed.'); }
    finally { if (safe()) { activeTransfer.current = false; setBusy(false); busyCallback.current?.(false); } }
  };
  const uploaded = upload ? contentReceivedBytes(upload) : 0; const total = files.reduce((sum, file) => sum + file.bytes, 0);
  return <View style={s.section}><Text accessibilityRole="header" style={s.sectionTitle}>Large ROM / disc content</Text>
    <Text style={s.description}>Upload an authorized ROM, disc image, or a multi-file disc set in bounded chunks. Select its cue sheet or playlist as the entry point. Runtime support is checked separately.</Text>
    <Text style={s.muted}>Up to 2 GB per file and 4 GB per bundle. Uses the permission references and consent entered above.</Text>
    <Button label={files.length ? 'Choose different files' : 'Choose ROM / disc files'} disabled={busy || disabled || !!upload} onPress={() => { void pick(); }} />
    {!!files.length && <><Text style={s.label}>Content entry point</Text><View style={s.chips}>{files.map(file => <TouchableOpacity key={file.path} accessibilityRole="radio" accessibilityState={{ checked: entrypoint === file.path }} disabled={!!upload || busy} onPress={() => setEntrypoint(file.path)} style={[s.chip, entrypoint === file.path && s.selected]}><Text style={s.chipText}>{file.path} · {bytes(file.bytes)}</Text></TouchableOpacity>)}</View>
      {upload && <><View style={s.progressTrack}><View style={[s.progressFill, { width: `${uploaded / total * 100}%` }]} /></View><Text accessibilityLiveRegion="polite" style={s.muted}>{bytes(uploaded)} of {bytes(total)} verified by the server{busy ? ' · uploading' : ' · paused'}</Text></>}
      <View style={s.chips}><Button label={busy ? 'Uploading…' : upload ? 'Resume upload' : 'Upload content'} primary disabled={busy || !consent || !rightsRefs.length || disabled} onPress={() => { void transfer(); }} />
        {busy && <Button label="Pause upload" onPress={() => abort.current?.abort()} />}
        {upload && !busy && <Button label="Withdraw upload" onPress={() => { void withdrawGameContentUpload(upload.upload_id).then(() => { if (safe()) setUpload(null); }).catch(caught => { if (safe()) setError(caught.message); }); }} />}</View>
    </>}
    {busy && <ActivityIndicator color={C.primaryHover} />}{!!error && <Text accessibilityRole="alert" style={s.error}>{error}</Text>}
    {!consent && <Text style={s.dim}>Acknowledge source rights above before starting the upload.</Text>}
  </View>;
}
