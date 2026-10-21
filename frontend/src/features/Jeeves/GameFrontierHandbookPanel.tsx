/** Exact, authenticated reader for one generated original-game construction book. */
import React, { useState } from 'react';
import { ScrollView, Text, TouchableOpacity, View } from 'react-native';
import { readForgeHandbook, type ForgeRecipe } from '../../product/gameFrontierAuthoringClient';

export default function GameFrontierHandbookPanel({ recipe, disabled = false }: {
  recipe: ForgeRecipe;
  disabled?: boolean;
}) {
  const [markdown, setMarkdown] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  if (!recipe.worldline || !recipe.direction || !recipe.treatment || !recipe.domain)
    return null;
  const load = async () => {
    if (busy || disabled) return;
    setBusy(true);
    setError('');
    try {
      const content = await readForgeHandbook(
        recipe.domain, recipe.treatment, recipe.direction!, recipe.worldline!,
      );
      setMarkdown(content);
    } catch (cause: unknown) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally { setBusy(false); }
  };
  return <View style={{ gap: 8, marginVertical: 8 }}>
    <TouchableOpacity
      accessibilityRole="button"
      accessibilityLabel="Read selected worldline technical handbook"
      disabled={busy || disabled}
      onPress={() => { void load(); }}
      style={{ borderColor: '#537a9f', borderWidth: 1, borderRadius: 8, padding: 10 }}>
      <Text style={{ color: '#dcefff' }}>
        {busy ? 'Loading source-backed game handbook…' : 'Read this worldline production handbook'}
      </Text>
    </TouchableOpacity>
    {!!error && <Text selectable style={{ color: '#ffb2b2' }}>{error}</Text>}
    {!!markdown && <ScrollView style={{ maxHeight: 360 }}
      accessibilityLabel="Source-backed production handbook">
      <Text selectable style={{ color: '#dcefff', fontSize: 12 }}>{markdown}</Text>
    </ScrollView>}
  </View>;
}
