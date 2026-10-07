/**
 * GalaxyStudioFactoryModal.SubScreens
 * -------------------------------------------------------------------
 * Extracted from GalaxyStudioFactoryModal.tsx on 2026-05-15.
 *
 * Three "Done"-state sub-screens that previously lived inline inside the
 * modal's renderDone() helper. Each is a pure presentational component:
 *   • <CodeFileView />    — single-file source viewer
 *   • <CodeBrowseView />  — file list / browse
 *   • <VaultView />       — ZIP / APK downloads listing
 *
 * No behavior change — these render the exact same JSX, styles, and
 * Ionicons as before. Props mirror the parent state they need.
 */
import React from 'react';
import {
  View, Text, TouchableOpacity, ScrollView, FlatList, Linking,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { T, s } from './GalaxyStudioFactoryModal.styles';

// ───────────────────────────────────────────────────────────────────────
// CodeFileView — single-file source viewer
// ───────────────────────────────────────────────────────────────────────
interface CodeFileViewProps {
  selectedFile: { path: string; lines: number } | null;
  fileContent: string;
  onBack: () => void;
}
export const CodeFileView: React.FC<CodeFileViewProps> = ({ selectedFile, fileContent, onBack }) => {
  if (!selectedFile) return null;
  return (
    <View style={{ flex: 1 }}>
      <TouchableOpacity style={s.codeBack} onPress={onBack}>
        <Ionicons name="arrow-back-outline" size={18} color={T.accentLight} />
        <Text style={s.codeBackText}>Back</Text>
      </TouchableOpacity>
      <View style={s.codeHeader}>
        <Ionicons name="code-slash-outline" size={16} color={T.accent} />
        <Text style={s.codePath} numberOfLines={1}>{selectedFile.path}</Text>
        <Text style={s.codeLineCount}>{selectedFile.lines}L</Text>
      </View>
      <ScrollView style={s.codeScroll}>
        <Text style={s.codeText}>{fileContent}</Text>
      </ScrollView>
    </View>
  );
};

// ───────────────────────────────────────────────────────────────────────
// CodeBrowseView — file list browser
// ───────────────────────────────────────────────────────────────────────
interface CodeBrowseViewProps {
  files: any;
  onBack: () => void;
  onSelectFile: (path: string) => void;
}
export const CodeBrowseView: React.FC<CodeBrowseViewProps> = ({ files, onBack, onSelectFile }) => (
  <View style={{ flex: 1 }}>
    <TouchableOpacity style={s.codeBack} onPress={onBack}>
      <Ionicons name="arrow-back-outline" size={18} color={T.accentLight} />
      <Text style={s.codeBackText}>Back</Text>
    </TouchableOpacity>
    {files && (
      <View style={s.codeStatsRow}>
        <View style={s.codeStat}>
          <Text style={s.codeStatVal}>{files.total_files}</Text>
          <Text style={s.codeStatLabel}>Files</Text>
        </View>
        <View style={s.codeStat}>
          <Text style={s.codeStatVal}>{files.total_lines?.toLocaleString()}</Text>
          <Text style={s.codeStatLabel}>Lines</Text>
        </View>
        <View style={s.codeStat}>
          <Text style={s.codeStatVal}>{Math.round((files.total_bytes || 0) / 1024)}KB</Text>
          <Text style={s.codeStatLabel}>Size</Text>
        </View>
      </View>
    )}
    <FlatList
      data={files?.files || []}
      keyExtractor={(item: any) => item.path}
      contentContainerStyle={{ paddingHorizontal: 14, paddingBottom: 40 }}
      renderItem={({ item: f }: any) => (
        <TouchableOpacity style={s.fileRow} onPress={() => onSelectFile(f.path)} activeOpacity={0.7}>
          <Ionicons
            name={f.type === 'tsx' ? 'logo-react' : 'code-slash-outline'}
            size={16}
            color={f.type === 'tsx' ? '#61dafb' : f.type === 'ts' ? '#3B82F6' : T.textDim}
          />
          <Text style={s.fileName} numberOfLines={1}>{f.path}</Text>
          <Text style={s.fileSize}>{f.lines}L</Text>
        </TouchableOpacity>
      )}
    />
  </View>
);

// ───────────────────────────────────────────────────────────────────────
// VaultView — downloads listing (ZIPs + APKs)
// ───────────────────────────────────────────────────────────────────────
interface VaultViewProps {
  vaultData: { zips?: any[]; apks?: any[] } | null;
  backendUrl: string;
  onBack: () => void;
}
export const VaultView: React.FC<VaultViewProps> = ({ vaultData, backendUrl, onBack }) => (
  <View style={{ flex: 1 }}>
    <TouchableOpacity style={s.codeBack} onPress={onBack}>
      <Ionicons name="arrow-back-outline" size={18} color={T.accentLight} />
      <Text style={s.codeBackText}>Back</Text>
    </TouchableOpacity>
    <ScrollView style={{ flex: 1, paddingHorizontal: 14 }} showsVerticalScrollIndicator={false}>
      <View style={s.vaultHeader}>
        <Ionicons name="folder-open" size={24} color="#34D399" />
        <Text style={s.vaultTitle}>Vault</Text>
      </View>

      {vaultData && (vaultData.zips?.length || 0) > 0 ? (
        <View style={s.vaultSection}>
          <Text style={s.vaultSectionTitle}>Downloads ({vaultData.zips!.length})</Text>
          {vaultData.zips!.map((z: any) => (
            <TouchableOpacity
              key={z.vault_id}
              style={s.vaultItem}
              onPress={() => Linking.openURL(`${backendUrl}${z.download_url}`).catch(() => {})}
              activeOpacity={0.7}
            >
              <Ionicons name="archive" size={20} color={T.accent} />
              <View style={{ flex: 1 }}>
                <Text style={s.vaultItemTitle} numberOfLines={1}>{z.title}</Text>
                <Text style={s.vaultItemSub}>{z.file_count} files • {z.size}</Text>
              </View>
              <Ionicons name="download-outline" size={20} color={T.accent} />
            </TouchableOpacity>
          ))}
        </View>
      ) : (
        <Text style={s.vaultEmpty}>No downloads yet.</Text>
      )}

      {vaultData && (vaultData.apks?.length || 0) > 0 && (
        <View style={s.vaultSection}>
          <Text style={s.vaultSectionTitle}>APKs ({vaultData.apks!.length})</Text>
          {vaultData.apks!.map((a: any) => (
            <TouchableOpacity
              key={a.vault_id}
              style={s.vaultItem}
              onPress={() => Linking.openURL(`${backendUrl}${a.download_url}`).catch(() => {})}
              activeOpacity={0.7}
            >
              <Ionicons name="logo-android" size={20} color="#10B981" />
              <View style={{ flex: 1 }}>
                <Text style={s.vaultItemTitle} numberOfLines={1}>{a.title}</Text>
                <Text style={s.vaultItemSub}>APK Ready</Text>
              </View>
              <Ionicons name="download-outline" size={20} color="#10B981" />
            </TouchableOpacity>
          ))}
        </View>
      )}
      <View style={{ height: 40 }} />
    </ScrollView>
  </View>
);
