import React, { useCallback, useEffect, useRef, useState } from 'react';
import { ActivityIndicator, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { getAuthToken } from '../../auth/gameforgeAuth';
import { getDragonSanctuary, type DragonSanctuary } from '../../product/crawlerClient';
import s, { colors } from './CrawlerWorkspace.styles';

const FORMS = ['Hatchling', 'Scout', 'Scholar', 'Pathfinder', 'Archivist'];
const HABITATS: Record<string, string> = { web:'Web forest', document:'Archive vault',
  structured:'Data crystals', media:'Media caverns', text:'Scribe library', artifact:'Artifact forge' };

export default function DragonSanctuaryPanel({ revision }: { revision: string }) {
  const [value, setValue] = useState<DragonSanctuary | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [expired, setExpired] = useState(false);
  const pending = useRef<AbortController | null>(null);
  const expiryTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const observedRevision = useRef(revision);
  const token = useRef(getAuthToken());
  const generation = useRef(0);

  const invalidate = useCallback(() => {
    generation.current++;
    pending.current?.abort();
    pending.current = null;
    if (expiryTimer.current !== null) clearTimeout(expiryTimer.current);
    expiryTimer.current = null;
  }, []);
  useEffect(() => {
    if (observedRevision.current !== revision) {
      observedRevision.current = revision;
      invalidate();
      setValue(null); setBusy(false); setExpired(true); setError('');
    }
    return () => invalidate();
  }, [revision, invalidate]);

  async function observe() {
    invalidate();
    const current = new AbortController(), attempt = generation.current;
    const owner = getAuthToken(), started = Date.now();
    token.current = owner;
    pending.current = current;
    setBusy(true); setValue(null); setError(''); setExpired(false);
    try {
      const result = await getDragonSanctuary(current.signal);
      if (current.signal.aborted || generation.current !== attempt || getAuthToken() !== owner) return;
      // This is a deliberately short-lived observation, not a live source grant.
      // Only an explicit refresh can obtain another server projection.
      const lifetime = result.earliest_source_expiry === null ? 300000 :
        Math.min(300000, Math.max(0, 1000 * (result.earliest_source_expiry - result.as_of_unix) - (Date.now() - started)));
      if (lifetime <= 0) { setExpired(true); return; }
      setValue(result);
      expiryTimer.current = setTimeout(() => {
        if (generation.current === attempt) { setValue(null); setExpired(true); }
      }, lifetime);
    } catch (err) {
      if (!current.signal.aborted && generation.current === attempt && getAuthToken() === owner)
        setError(err instanceof Error ? err.message : 'Sanctuary observation unavailable.');
    } finally {
      if (generation.current === attempt) { pending.current = null; setBusy(false); }
    }
  }

  const visible = value && observedRevision.current === revision && token.current === getAuthToken() ? value : null;
  return <View style={s.card}>
    <Text style={s.eyebrow}>DRAGON SANCTUARY · SHARED COLLECTION</Text>
    <Text style={s.heading}>Discoveries across expeditions</Text>
    <Text style={s.small}>Recompute one collection from current, authorized sources across up to eight expeditions. Exact copies and low-signal pages cannot earn additional collection credit. No permanent XP wallet or new network permission is created.</Text>
    <TouchableOpacity accessibilityRole="button" accessibilityState={{ disabled:busy }} disabled={busy}
      style={[s.button,busy&&s.disabled]} onPress={()=>void observe()}>
      {busy&&<ActivityIndicator color={colors.accent} size="small"/>}
      <Text style={s.buttonText}>{busy?'Observing current evidence…':visible?'Refresh sanctuary':'Observe my sanctuary'}</Text>
    </TouchableOpacity>
    {error&&<Text accessibilityLiveRegion="polite" style={s.error}>{error}</Text>}
    {expired&&!visible&&<Text accessibilityLiveRegion="polite" style={s.small}>This observation is no longer current. Refresh when you want a new collection view.</Text>}
    {visible&&<>
      <View style={local.band}><Text style={s.heading}>{FORMS[visible.stage]} · collection index {visible.collection_index}/1000</Text>
        <View accessible accessibilityLabel={'Collection index '+visible.collection_index+' of 1000'} style={local.track}><View style={[local.fill,{width:(visible.collection_index/10+'%') as `${number}%`}]}/></View>
        <Text style={s.small}>Collection reflects available evidence, not a pet's health, and may change when source permissions or freshness change.</Text>
      </View>
      <View style={local.grid}>
        {[
          ['Contributing expeditions',visible.contributing_expeditions],
          ['Credited discoveries',visible.credited_sources],
          ['Distinct origins',visible.distinct_origins],
          ['Exact copies excluded',visible.exact_duplicates],
          ['Low-signal captures',visible.low_signal_sources],
          ['Unqualified expeditions',visible.unqualified_expeditions],
        ].map(([label,count])=><View key={String(label)} style={local.cell}><Text style={s.small}>{label}</Text><Text style={local.count}>{count}</Text></View>)}
      </View>
      <View style={local.grid}>{Object.entries(HABITATS).map(([key,label])=><View style={local.cell} key={key}><Text style={s.label}>{label}</Text><Text style={s.small}>{visible.habitats[key]??0} credited discoveries</Text></View>)}</View>
      <Text style={s.small}>{visible.candidate_limit_reached?'Collection is a bounded subset; additional expeditions or sources exist.':'Collection covers the selected current-consent candidates.'} Observed {new Date(visible.as_of_unix*1000).toLocaleString()}.</Text>
      <Text selectable style={s.small}>Revision: {visible.revision_digest}</Text>
      <Text style={s.small}>Historical capture observations remain unreviewed. No source text or evidence-use authorization appears in this view.</Text>
    </>}
  </View>;
}

const local = StyleSheet.create({
  band:{borderWidth:1,borderColor:'#64558c',borderRadius:12,padding:12,backgroundColor:'#211a36',gap:10},
  track:{height:10,borderRadius:8,backgroundColor:colors.edge,overflow:'hidden'},
  fill:{height:10,borderRadius:8,backgroundColor:colors.accent},
  grid:{flexDirection:'row',flexWrap:'wrap',gap:8},
  cell:{flexGrow:1,flexBasis:140,padding:10,borderRadius:10,borderWidth:1,borderColor:colors.edge,gap:4},
  count:{color:colors.text,fontSize:23,fontWeight:'700'},
});
