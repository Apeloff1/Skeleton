/** Read-only owner acquisition restriction view, with revision and account fencing. */
import React, { useEffect, useRef, useState } from 'react';
import { Text, TouchableOpacity, View } from 'react-native';
import { getAuthToken } from '../../auth/gameforgeAuth';
import { getAcquisitionHoldCatalog, type AcquisitionHoldCatalog } from '../../product/crawlerClient';
import s from './CrawlerWorkspace.styles';

export default function CrawlerAcquisitionHoldPanel({ revision }: { revision: string }) {
  const [result, setResult] = useState<AcquisitionHoldCatalog | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const pending = useRef<AbortController | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const observed = useRef<{ revision: string; token: ReturnType<typeof getAuthToken> } | null>(null);
  const clear = () => {
    pending.current?.abort();
    pending.current = null;
    if (timer.current !== null) clearTimeout(timer.current);
    timer.current = null;
    observed.current = null;
  };
  useEffect(() => {
    setResult(null); setError(''); setBusy(false);
    return clear;
  }, [revision]);

  const refresh = async () => {
    clear();
    const controller = new AbortController(), token = getAuthToken();
    pending.current = controller;
    setBusy(true); setResult(null); setError('');
    try {
      const receipt = await getAcquisitionHoldCatalog(controller.signal);
      if (controller.signal.aborted || pending.current !== controller || token !== getAuthToken()) return;
      observed.current = { revision, token };
      setResult(receipt);
      timer.current = setTimeout(() => {
        if (pending.current === controller) {
          observed.current = null;
          setResult(null);
        }
      }, 30000);
    } catch (err) {
      if (!controller.signal.aborted && pending.current === controller && token === getAuthToken())
        setError(err instanceof Error ? err.message : 'Restriction audit unavailable.');
    } finally {
      if (!controller.signal.aborted && pending.current === controller) setBusy(false);
    }
  };

  const visible = result && observed.current?.revision === revision
    && observed.current?.token === getAuthToken() ? result : null;
  return <View style={s.card}>
    <Text style={s.heading}>Owner acquisition restrictions</Text>
    <Text style={s.small}>Inspect committed grant-wide host holds. This observation is not live authorization, a global host lock, or proof that unrestricted sources permit access.</Text>
    <TouchableOpacity accessibilityRole="button" disabled={busy} accessibilityState={{disabled: busy}} style={[s.button, busy && s.disabled]} onPress={() => void refresh()}>
      <Text style={s.buttonText}>{busy ? 'Inspecting committed revisions…' : 'Refresh restriction audit'}</Text>
    </TouchableOpacity>
    {!!error && <Text accessibilityLiveRegion="polite" style={s.error}>{error}</Text>}
    {visible && <>
      <Text style={s.small}>{visible.qualified_sessions} qualified sessions · {visible.excluded_sessions} unqualified</Text>
      {(visible.capacity_reached || visible.excluded_sessions > 0) && <Text style={s.error}>Incomplete restriction evidence. Overlapping dispatch may be held pending qualification.</Text>}
      {!visible.holds.length && <Text style={s.small}>No grant-wide holds were observed in the qualified revisions.</Text>}
      {visible.holds.map(h => <View key={h.host} style={s.check}>
        <Text style={s.label}>{h.host}</Text>
        <Text style={s.small}>{h.observed_grants} observed grant holds · {h.denial_statuses} denial statuses · {h.rejected_success_statuses} rejected successful-status responses</Text>
        <Text style={s.small}>Latest observed grant expiry: {new Date(h.latest_grant_expiry * 1000).toLocaleString()}</Text>
      </View>)}
      <Text style={s.small}>Observed {new Date(visible.as_of * 1000).toLocaleString()}. Refresh after a revision or after 30 seconds.</Text>
    </>}
  </View>;
}
