import React, { useRef, useState } from 'react';
import { Text, TextInput, View } from 'react-native';
import { useRouter } from 'expo-router';
import AsyncStorage from '@react-native-async-storage/async-storage';
import {
  prepareSceneChatHandoff, SCENE_CHAT_HANDOFF_KEY, SCENE_ERAS,
  SCENE_RECIPES, suggestedSceneRecipe,
} from './sceneHandoff';
import type { SceneEra, SceneRecipeKey } from './sceneHandoff';
import { newId } from './workspace';
import { Action, Editor, styles } from './workbench/ui';

/** Scene Composer owns all generation: this creates only an explicit reviewed form draft. */
export default function ChatSceneActions({
  text, conversationId, messageId, notify,
}: {
  text: string;
  conversationId: string;
  messageId: string;
  notify: (notice: string) => void;
}) {
  const router = useRouter();
  const suggested = suggestedSceneRecipe(text);
  const relevant = !!suggested || /\b(scene|environment|world|level|diorama|forge)\b/i.test(text);
  const [open, setOpen] = useState(false);
  const [buildId, setBuildId] = useState('');
  const [era, setEra] = useState<SceneEra>('modern');
  const [recipeKey, setRecipeKey] = useState<SceneRecipeKey | null>(suggested);
  const [error, setError] = useState('');
  const [working, setWorking] = useState(false);
  const saving = useRef(false);

  if (!relevant) return null;

  const handoff = async () => {
    if (saving.current || !recipeKey) return;
    saving.current = true;
    setWorking(true);
    setError('');
    try {
      const draft = prepareSceneChatHandoff({
        id: newId(),
        createdAt: Date.now(),
        buildId: buildId.trim(),
        era,
        recipeKey,
        conversationId,
        assistantMessageId: messageId,
      });
      await AsyncStorage.setItem(SCENE_CHAT_HANDOFF_KEY, JSON.stringify(draft));
      setOpen(false);
      router.push({
        pathname: '/compose-scene',
        params: { build: draft.buildId, chat_scene: draft.id },
      });
      notify('Scene draft transferred. Review the entire composition before forging.');
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Scene draft could not be saved.');
    } finally {
      saving.current = false;
      setWorking(false);
    }
  };

  const chosen = SCENE_RECIPES.find(recipe => recipe.key === recipeKey);
  return (
    <View style={{ marginTop: 8 }}>
      <Action icon="color-wand-outline" label="Draft a scene in editor"
        compact disabled={working} onPress={() => setOpen(true)} />
      <Editor visible={open} title="Prepare Scene Composer draft"
        close={() => { if (!working) setOpen(false); }}
        footer={
          <View style={{ gap: 8 }}>
            <Action icon="arrow-forward-circle-outline" label="Review in Scene Composer"
              disabled={!recipeKey || !buildId.trim() || working}
              onPress={() => { void handoff(); }} />
            <Action icon="close" label="Cancel without changes"
              disabled={working} onPress={() => setOpen(false)} />
          </View>
        }>
        <Text style={styles.muted}>
          Choose a real game build and a supported recipe. Jeeves suggestions are not
          executable commands. The Scene Composer must be reviewed and its separate
          Compose & mount button pressed before any asset is created.
        </Text>
        <Text style={styles.label}>Destination game build ID</Text>
        <TextInput style={styles.input} value={buildId}
          onChangeText={setBuildId} autoCapitalize="none"
          autoCorrect={false} maxLength={128}
          placeholder="Existing game build ID"
          accessibilityLabel="Scene game build ID" />
        <Text style={styles.label}>Scene recipe</Text>
        <View style={styles.wrap}>
          {SCENE_RECIPES.map(recipe => (
            <Action key={recipe.key} compact label={recipe.name}
              icon="albums-outline"
              selected={recipeKey === recipe.key} disabled={working}
              onPress={() => setRecipeKey(recipe.key)} />
          ))}
        </View>
        <Text style={styles.label}>Target era</Text>
        <View style={styles.wrap}>
          {SCENE_ERAS.map(value => (
            <Action key={value} compact label={value}
              selected={era === value} disabled={working}
              onPress={() => setEra(value)} />
          ))}
        </View>
        {chosen && (
          <View style={styles.stack}>
            <Text style={styles.label}>Preset preview · {chosen.name}</Text>
            {chosen.items.map(item => (
              <Text key={item.category} style={styles.text}>
                {item.count} × {item.category.replace(/_/g, ' ')}
              </Text>
            ))}
            <Text style={styles.muted}>
              Asset counts and styles can be adjusted in the actual composer.
            </Text>
          </View>
        )}
        {!!error && <Text style={styles.error} accessibilityRole="alert">{error}</Text>}
      </Editor>
    </View>
  );
}
