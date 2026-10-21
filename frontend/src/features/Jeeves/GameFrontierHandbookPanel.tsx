/** Exact scope, objective completeness and measured-length game manual comparison. */
import React, { useState } from 'react';
import { ScrollView, Text, TouchableOpacity, View } from 'react-native';
import {
  readForgeHandbook, readForgePhaseHandbook, readForgeCampaignHandbook,
  rankForgeCampaignHandbooks, type ForgeRecipe, type ForgeCampaignRanking,
} from '../../product/gameFrontierAuthoringClient';

export default function GameFrontierHandbookPanel({ recipe, disabled = false }: {
  recipe: ForgeRecipe; disabled?: boolean;
}) {
  const [markdown, setMarkdown] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [metrics, setMetrics] = useState('');
  const [ranking, setRanking] = useState<ForgeCampaignRanking | null>(null);
  if (!recipe.worldline || !recipe.direction || !recipe.treatment || !recipe.domain)
    return null;
  const load = async () => {
    if (busy || disabled) return;
    setBusy(true); setError('');
    try {
      if (recipe.campaign && recipe.phase) {
        const doc = await readForgeCampaignHandbook(
          recipe.domain, recipe.treatment, recipe.direction,
          recipe.worldline, recipe.phase, recipe.campaign);
        setMarkdown(doc.markdown);
        setMetrics('Document completeness ' + doc.score + '/100 · ' +
          doc.words.toLocaleString() + ' measured words');
      } else {
        const body = recipe.phase
          ? await readForgePhaseHandbook(recipe.domain, recipe.treatment,
              recipe.direction, recipe.worldline, recipe.phase)
          : await readForgeHandbook(recipe.domain, recipe.treatment,
              recipe.direction, recipe.worldline);
        setMarkdown(body); setMetrics('');
      }
    } catch (cause: unknown) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally { setBusy(false); }
  };
  const compare = async (sort: 'quality' | 'length') => {
    if (!recipe.phase || busy || disabled) return;
    setBusy(true); setError('');
    try {
      setRanking(await rankForgeCampaignHandbooks(
        recipe.domain, recipe.treatment, recipe.direction,
        recipe.worldline, recipe.phase, sort));
    } catch (cause: unknown) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally { setBusy(false); }
  };
  const control = (title: string, click: () => void) => (
    <TouchableOpacity
      key={title} accessibilityRole="button" accessibilityLabel={title}
      disabled={busy || disabled} onPress={click}
      style={{ borderColor: '#537a9f', borderWidth: 1, borderRadius: 8,
        padding: 10, marginRight: 6, marginBottom: 6 }}>
      <Text style={{ color: '#dcefff' }}>{title}</Text>
    </TouchableOpacity>
  );
  return <View style={{ gap: 8, marginVertical: 8 }}>
    <View style={{ flexDirection: 'row', flexWrap: 'wrap' }}>
      {control(busy ? 'Reading source documentation…' : 'Read selected game handbook',
        () => { void load(); })}
      {!!recipe.phase && <>
        {control('Rank quality', () => { void compare('quality'); })}
        {control('Rank length', () => { void compare('length'); })}
      </>}
    </View>
    {!!error && <Text selectable style={{ color: '#ffb2b2' }}>{error}</Text>}
    {!!metrics && <Text style={{ color: '#b1cada', fontSize: 12 }}>{metrics}</Text>}
    {!!ranking && <View style={{ gap: 4 }}>
      <Text style={{ color:'#dcefff', fontWeight: '700' }}>
        {ranking.sort === 'quality' ? 'Quality-first' : 'Longest-first'}
        {' · ranked within ten campaign variants'}
      </Text>
      <Text style={{ color: '#b1cada', fontSize: 11 }}>
        Heuristic documentation completeness, not native game quality.
        Word counts measured from rendered Markdown.
      </Text>
      {ranking.items.map(item =>
        <Text key={item.campaign} style={{ color: '#dcefff', fontSize: 12 }}>
          {item.rank}. {item.campaign.replace(/_/g,' ')} ·
          {' '}{item.quality_score}/100 · {item.words.toLocaleString()} words
        </Text>)}
    </View>}
    {!!markdown && <ScrollView style={{ maxHeight: 360 }}
        accessibilityLabel="Full source-backed game production manual">
      <Text selectable style={{ color: '#dcefff', fontSize: 12 }}>{markdown}</Text>
    </ScrollView>}
  </View>;
}
