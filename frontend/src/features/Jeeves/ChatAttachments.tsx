import React, { useEffect, useState } from 'react';
import { ActivityIndicator, Text, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { getAuthToken } from '../../auth/gameforgeAuth';
import { readChatAttachment, type UploadedChatAttachment } from './chatFiles';
import s, { colors as C } from './ChatWorkspace.styles';

type FileDetail = { reference: string; file: UploadedChatAttachment | null; error: string | null };

/** Metadata is requested only when a person opens this message's attachments. */
export default function ChatAttachments({ references, threadId }: { references: string[]; threadId: string }) {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [details, setDetails] = useState<FileDetail[]>([]);
  const [generation, setGeneration] = useState(0);
  const identity = JSON.stringify(references);
  const accountToken = getAuthToken();
  useEffect(() => {
    if (!open) return;
    const abort = new AbortController();
    setLoading(true);
    void Promise.all(references.slice(0, 4).map(async reference => {
      try { return { reference, file: await readChatAttachment(reference, threadId, { signal: abort.signal }), error: null }; }
      catch { return { reference, file: null, error: 'File details could not be loaded. Try refreshing.' }; }
    })).then(files => {
      if (!abort.signal.aborted) {
        setDetails(accountToken === getAuthToken() ? files : []); setLoading(false);
      }
    });
    return () => abort.abort();
  }, [open, threadId, identity, generation, accountToken]);
  useEffect(() => { setDetails([]); setOpen(false); }, [accountToken]);
  return <View style={{ gap: 8 }}>
    <TouchableOpacity onPress={() => setOpen(value => !value)} accessibilityRole="button"
      accessibilityLabel={`${open ? 'Hide' : 'View'} ${references.length} attached file${references.length === 1 ? '' : 's'}`}
      accessibilityState={{ expanded: open }} style={s.miniButton}>
      <Ionicons name="attach-outline" size={17} color={C.textMuted} />
      <Text style={s.miniText}>{references.length} attached file{references.length === 1 ? '' : 's'}</Text>
      <Ionicons name={open ? 'chevron-up-outline' : 'chevron-down-outline'} size={13} color={C.textMuted} />
    </TouchableOpacity>
    {open && (loading ? <ActivityIndicator size="small" color={C.primaryHover} /> :
      details.map(detail => <View key={detail.reference} style={s.attachmentDetail}>
        {detail.file ? <>
          <View style={s.row}><Ionicons name="document-outline" size={17} color={C.primaryHover} />
            <Text selectable style={[s.fileName, { flex: 1 }]}>{detail.file.filename}</Text>
            <Text style={s.fileSize}>{Math.max(1, Math.ceil(detail.file.sizeBytes / 1024))} KB</Text></View>
          {!!detail.file.preview && <Text selectable numberOfLines={5} style={s.muted}>{detail.file.preview}</Text>}
        </> : <Text style={s.muted}>{detail.error}</Text>}
      </View>))}
    {open && !loading && details.some(detail => detail.error) && <TouchableOpacity accessibilityRole="button" accessibilityLabel="Refresh attachment details"
      style={s.miniButton} onPress={() => setGeneration(value => value + 1)}><Ionicons name="refresh-outline" size={14} color={C.textMuted} /><Text style={s.miniText}>Refresh files</Text></TouchableOpacity>}
  </View>;
}
