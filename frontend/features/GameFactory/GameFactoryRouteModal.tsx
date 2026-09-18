import React from 'react';
import {
  ActivityIndicator,
  Modal,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import Constants from 'expo-constants';

import { apiFetch } from '../../utils/apiController';
import { GameFactoryModal } from './GameFactoryModal';
import {
  consumeGameBuilderArtifact,
  formatGameBuilderDescription,
  type GameBuilderArtifact,
} from './gameBuilderHandoff';

interface GameFactoryRouteModalProps {
  visible: boolean;
  onClose: () => void;
  colors: any;
}

type HandoffStage = 'review' | 'creating' | 'created' | 'factory';

interface CreatedProjectSummary {
  projectId: string;
  title: string;
}

const API_BASE = (() => {
  if (
    typeof window !== 'undefined'
    && (window as any).location?.origin
    && !(window as any).location.origin.startsWith('file:')
  ) {
    return (window as any).location.origin.replace(/\/+$/, '');
  }
  return (Constants.expoConfig?.extra?.EXPO_PUBLIC_BACKEND_URL as string)
    || process.env.EXPO_PUBLIC_BACKEND_URL
    || '';
})();

function parseCreatedProjectPayload(payload: unknown): CreatedProjectSummary | null {
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) return null;

  const record = payload as Record<string, unknown>;
  if (typeof record.project_id !== 'string') return null;
  const projectId = record.project_id.trim();
  if (!projectId || projectId.length > 256) return null;

  let title = 'Seeded game project';
  if (record.gdd && typeof record.gdd === 'object' && !Array.isArray(record.gdd)) {
    const rawTitle = (record.gdd as Record<string, unknown>).title;
    if (typeof rawTitle === 'string' && rawTitle.trim()) {
      title = rawTitle.trim().slice(0, 160);
    }
  }

  return { projectId, title };
}

export const GameFactoryRouteModal: React.FC<GameFactoryRouteModalProps> = ({
  visible,
  onClose,
  colors,
}) => {
  const [artifact] = React.useState<GameBuilderArtifact | null>(() => consumeGameBuilderArtifact());
  const [stage, setStage] = React.useState<HandoffStage>(artifact ? 'review' : 'factory');
  const [description, setDescription] = React.useState(() => (
    artifact ? formatGameBuilderDescription(artifact, 2000) : ''
  ));
  const [createdProjectId, setCreatedProjectId] = React.useState('');
  const [createdTitle, setCreatedTitle] = React.useState('');
  const [error, setError] = React.useState('');

  const createSeededProject = React.useCallback(async () => {
    const trimmed = description.trim();
    if (!trimmed || stage === 'creating') return;

    setStage('creating');
    setError('');
    try {
      const response = await apiFetch(`${API_BASE}/api/game-factory/create`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ description: trimmed }),
      });

      if (!response.ok) {
        setError(`Game Factory rejected the seed (${response.status}).`);
        setStage('review');
        return;
      }

      const payload: unknown = await response.json();
      const created = parseCreatedProjectPayload(payload);
      if (!created) {
        setError('Game Factory returned an invalid project response.');
        setStage('review');
        return;
      }

      setCreatedProjectId(created.projectId);
      setCreatedTitle(created.title);
      setStage('created');
    } catch {
      setError('Could not create project. Check your connection and try again.');
      setStage('review');
    }
  }, [description, stage]);

  if (stage === 'factory') {
    return <GameFactoryModal visible={visible} onClose={onClose} colors={colors} />;
  }

  const category = artifact?.category || 'game';
  const isCreating = stage === 'creating';
  const createDisabled = !description.trim() || isCreating;

  return (
    <Modal visible={visible} animationType="slide" onRequestClose={onClose}>
      <View style={[styles.root, { backgroundColor: colors.background || '#05070d' }]}>
        <View style={[styles.header, { borderBottomColor: colors.border }]}>
          <TouchableOpacity
            accessibilityRole="button"
            accessibilityLabel="Close Game Factory handoff"
            onPress={onClose}
            style={styles.iconButton}
          >
            <Ionicons name="close" size={24} color={colors.text} />
          </TouchableOpacity>
          <View style={styles.headerText}>
            <Text style={[styles.title, { color: colors.text }]}>AI Seed → Game Factory</Text>
            <Text style={[styles.subtitle, { color: colors.textMuted }]}>Review before creating a buildable project</Text>
          </View>
        </View>

        <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
          {stage === 'created' ? (
            <View
              accessibilityLiveRegion="polite"
              style={[styles.card, { backgroundColor: colors.surface, borderColor: '#22C55E55' }]}
            >
              <Ionicons name="checkmark-circle" size={42} color="#22C55E" />
              <Text style={[styles.cardTitle, { color: colors.text }]}>Project created</Text>
              <Text style={[styles.body, { color: colors.textMuted }]}>{createdTitle}</Text>
              <Text style={[styles.projectId, { color: colors.textMuted }]}>Project {createdProjectId}</Text>
              <TouchableOpacity
                accessibilityRole="button"
                accessibilityLabel="Continue in Game Factory"
                style={[styles.primaryButton, { backgroundColor: '#8B5CF6' }]}
                onPress={() => setStage('factory')}
              >
                <Ionicons name="hammer" size={18} color="#FFF" />
                <Text style={styles.primaryButtonText}>Continue in Game Factory</Text>
              </TouchableOpacity>
            </View>
          ) : (
            <>
              <View style={[styles.seedBadge, { backgroundColor: '#8B5CF620', borderColor: '#8B5CF650' }]}>
                <Ionicons name="sparkles" size={18} color="#A78BFA" />
                <Text style={styles.seedBadgeText}>AI {category.toUpperCase()} seed attached</Text>
              </View>

              <Text style={[styles.label, { color: colors.text }]}>Builder brief</Text>
              <Text style={[styles.help, { color: colors.textMuted }]}>
                The generated artifact is converted into the existing Game Factory description contract. Edit it before creation if needed.
              </Text>
              <TextInput
                accessibilityLabel="Game Factory builder brief"
                accessibilityHint="Edit the AI-generated seed before creating a Game Factory project"
                value={description}
                onChangeText={setDescription}
                editable={!isCreating}
                multiline
                maxLength={2000}
                textAlignVertical="top"
                style={[
                  styles.input,
                  { color: colors.text, backgroundColor: colors.surface, borderColor: error ? '#EF4444' : colors.border },
                ]}
              />
              <Text style={[styles.count, { color: colors.textMuted }]}>{description.length}/2000</Text>

              {!!error && (
                <View
                  accessibilityRole="alert"
                  accessibilityLiveRegion="assertive"
                  style={[styles.errorBox, { borderColor: '#EF444455' }]}
                >
                  <Text style={styles.errorText}>{error}</Text>
                </View>
              )}

              <TouchableOpacity
                accessibilityRole="button"
                accessibilityLabel="Create seeded Game Factory project"
                accessibilityState={{ disabled: createDisabled, busy: isCreating }}
                style={[
                  styles.primaryButton,
                  { backgroundColor: !createDisabled ? '#22C55E' : colors.border },
                ]}
                onPress={createSeededProject}
                disabled={createDisabled}
              >
                {isCreating ? (
                  <ActivityIndicator color="#FFF" />
                ) : (
                  <>
                    <Ionicons name="rocket" size={18} color="#FFF" />
                    <Text style={styles.primaryButtonText}>Create Seeded Project</Text>
                  </>
                )}
              </TouchableOpacity>

              <TouchableOpacity
                accessibilityRole="button"
                accessibilityLabel="Discard seed and open Game Factory"
                accessibilityState={{ disabled: isCreating }}
                style={styles.secondaryButton}
                onPress={() => setStage('factory')}
                disabled={isCreating}
              >
                <Text style={[styles.secondaryButtonText, { color: colors.textMuted }]}>Discard seed and open Game Factory</Text>
              </TouchableOpacity>
            </>
          )}
        </ScrollView>
      </View>
    </Modal>
  );
};

const styles = StyleSheet.create({
  root: { flex: 1 },
  header: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16, paddingVertical: 14, borderBottomWidth: 1 },
  iconButton: { width: 44, height: 44, alignItems: 'center', justifyContent: 'center' },
  headerText: { flex: 1, marginLeft: 8 },
  title: { fontSize: 18, fontWeight: '800' },
  subtitle: { fontSize: 12, marginTop: 2 },
  content: { padding: 20, gap: 12, flexGrow: 1 },
  card: { borderWidth: 1, borderRadius: 16, padding: 24, alignItems: 'center', gap: 10 },
  cardTitle: { fontSize: 20, fontWeight: '800' },
  body: { fontSize: 14, textAlign: 'center' },
  projectId: { fontSize: 11 },
  seedBadge: { alignSelf: 'flex-start', flexDirection: 'row', alignItems: 'center', gap: 8, borderWidth: 1, borderRadius: 999, paddingHorizontal: 12, paddingVertical: 8 },
  seedBadgeText: { color: '#C4B5FD', fontSize: 12, fontWeight: '800' },
  label: { fontSize: 18, fontWeight: '800', marginTop: 6 },
  help: { fontSize: 13, lineHeight: 19 },
  input: { minHeight: 260, borderWidth: 1, borderRadius: 14, padding: 14, fontSize: 14, lineHeight: 20 },
  count: { alignSelf: 'flex-end', fontSize: 11 },
  errorBox: { borderWidth: 1, borderRadius: 10, padding: 10, backgroundColor: '#EF444410' },
  errorText: { color: '#FCA5A5', fontSize: 12 },
  primaryButton: { minHeight: 48, borderRadius: 12, flexDirection: 'row', gap: 8, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 16, marginTop: 6 },
  primaryButtonText: { color: '#FFF', fontSize: 14, fontWeight: '800' },
  secondaryButton: { minHeight: 44, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 12 },
  secondaryButtonText: { fontSize: 13, fontWeight: '600' },
});
