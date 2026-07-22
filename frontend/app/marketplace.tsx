/**
 * /marketplace — Creator Marketplace (one-time game purchases via Stripe).
 *
 * Browse listed games, buy access through Stripe Checkout, see your purchases,
 * and list your own games for sale. Buyer/creator identity is a local visitor id.
 */
import React from 'react';
import {
  View, Text, ScrollView, TouchableOpacity, ActivityIndicator, TextInput,
  StyleSheet, SafeAreaView, Platform, Image, Modal, RefreshControl,
} from 'react-native';
import { useRouter, useLocalSearchParams } from 'expo-router';
import * as WebBrowser from 'expo-web-browser';
import api from '../src/utils/apiClient';
import { useHaptics } from '../src/hooks/useHaptics';
import { awardXp } from '../src/utils/liveops';
import { safeGetItem, safeSetItem } from '../utils/safeStorage';

const BACKEND = process.env.EXPO_PUBLIC_BACKEND_URL || '';

async function getVisitorId(): Promise<string> {
  let id = await safeGetItem('mkt_visitor_id');
  if (!id) {
    id = 'v_' + Math.random().toString(36).slice(2) + Date.now().toString(36);
    await safeSetItem('mkt_visitor_id', id);
  }
  return id;
}

type Listing = {
  playable_id: string; title: string; genre: string; price_usd: number;
  has_cover?: boolean; sales?: number; overall?: number; summary?: string;
  creator_id?: string; plays?: number;
};

function Cover({ id, hasCover, size = 56 }: { id: string; hasCover?: boolean; size?: number }) {
  const [err, setErr] = React.useState(false);
  if (!hasCover || err) {
    return <View style={[styles.coverFallback, { width: size, height: size }]}><Text style={{ fontSize: size * 0.4 }}>🎮</Text></View>;
  }
  return <Image source={{ uri: `${BACKEND}/api/playable/${id}/cover.png` }} style={{ width: size, height: size, borderRadius: 10, backgroundColor: '#141414' }} onError={() => setErr(true)} />;
}

export default function Marketplace() {
  const router = useRouter();
  const haptics = useHaptics();
  const params = useLocalSearchParams<{ session_id?: string; cancelled?: string; sell?: string }>();
  const [visitor, setVisitor] = React.useState('');
  const [tab, setTab] = React.useState<'browse' | 'owned'>('browse');
  const [sort, setSort] = React.useState<'newest' | 'price_low' | 'price_high' | 'bestselling'>('newest');
  const [listings, setListings] = React.useState<Listing[]>([]);
  const [owned, setOwned] = React.useState<Listing[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [buying, setBuying] = React.useState<string | null>(null);
  const [banner, setBanner] = React.useState<string | null>(null);
  const [sellModal, setSellModal] = React.useState(false);
  const [sellId, setSellId] = React.useState('');
  const [sellPrice, setSellPrice] = React.useState('4.99');
  const [sellMsg, setSellMsg] = React.useState('');

  const loadListings = React.useCallback(async () => {
    setLoading(true);
    const r = await api.get<{ listings: Listing[] }>(`/api/marketplace/listings?sort=${sort}`, { timeoutMs: 12000 });
    if (r.ok && r.data) setListings(r.data.listings || []);
    setLoading(false);
  }, [sort]);

  const loadOwned = React.useCallback(async (vid: string) => {
    const r = await api.get<{ purchases: Listing[] }>(`/api/marketplace/purchases?buyer_id=${encodeURIComponent(vid)}`, { timeoutMs: 12000 });
    if (r.ok && r.data) setOwned(r.data.purchases || []);
  }, []);

  React.useEffect(() => { getVisitorId().then((v) => { setVisitor(v); loadOwned(v); }); }, [loadOwned]);
  React.useEffect(() => { loadListings(); }, [loadListings]);

  // Return from Stripe Checkout: poll the session status.
  React.useEffect(() => {
    const sid = params.session_id;
    if (!sid || !visitor) return;
    let cancelled = false;
    (async () => {
      setBanner('⏳ Confirming your payment…');
      for (let i = 0; i < 8 && !cancelled; i++) {
        const r = await api.get<any>(`/api/marketplace/checkout/status/${sid}`, { timeoutMs: 12000 });
        const ps = r.data?.payment_status;
        if (ps === 'paid') { setBanner('✅ Purchase complete — game unlocked!'); haptics.notify('success'); awardXp('purchase'); loadOwned(visitor); setTab('owned'); return; }
        if (ps === 'expired' || r.data?.status === 'expired') { setBanner('⚠️ Checkout session expired.'); return; }
        await new Promise((res) => setTimeout(res, 2000));
      }
      if (!cancelled) setBanner('⌛ Still processing — check "My Games" shortly.');
    })();
    return () => { cancelled = true; };
  }, [params.session_id, visitor, haptics, loadOwned]);

  React.useEffect(() => { if (params.cancelled) setBanner('Checkout cancelled.'); }, [params.cancelled]);

  // Deep-link from /playable "🛒 Sell": open the List-a-game modal prefilled.
  React.useEffect(() => {
    const pid = (params.sell || '').toString().trim();
    if (pid) { setSellId(pid); setSellMsg(''); setSellModal(true); }
  }, [params.sell]);

  const buy = React.useCallback(async (l: Listing) => {
    if (!visitor || buying) return;
    haptics.selection();
    setBuying(l.playable_id);
    const origin = Platform.OS === 'web' && typeof window !== 'undefined' ? window.location.origin : BACKEND;
    const r = await api.post<{ url?: string; error?: string; owned?: boolean }>(
      '/api/marketplace/checkout', { playable_id: l.playable_id, buyer_id: visitor, origin_url: origin }, { timeoutMs: 20000 });
    setBuying(null);
    if (r.data?.owned) { setBanner('You already own this game.'); setTab('owned'); loadOwned(visitor); return; }
    const url = r.data?.url;
    if (!r.ok || !url) { setBanner(r.data?.error || 'Could not start checkout.'); return; }
    if (Platform.OS === 'web' && typeof window !== 'undefined') { window.location.href = url; }
    else { await WebBrowser.openBrowserAsync(url); /* user returns; they can pull to refresh */ loadOwned(visitor); }
  }, [visitor, buying, haptics, loadOwned]);

  const submitListing = React.useCallback(async () => {
    const price = parseFloat(sellPrice);
    if (!sellId.trim() || isNaN(price)) { setSellMsg('Enter a game id and a valid price.'); return; }
    setSellMsg('Listing…');
    const r = await api.post<{ ok?: boolean; error?: string; similarity_warning?: { title?: string; similarity?: number } | null }>(
      '/api/marketplace/list', { playable_id: sellId.trim(), price_usd: price, creator_id: visitor, summary: '' }, { timeoutMs: 12000 });
    if (r.data?.ok) {
      const w = r.data.similarity_warning;
      if (w && typeof w.similarity === 'number') {
        setSellMsg(`✅ Listed! ⚠️ Note: ${Math.round(w.similarity * 100)}% similar to “${w.title || 'another game'}” — make sure it's your original work.`);
        setSellId(''); loadListings(); haptics.notify('success');
      } else {
        setSellMsg('✅ Listed!'); setSellModal(false); setSellId(''); loadListings(); haptics.notify('success');
      }
    }
    else setSellMsg(r.data?.error || 'Failed to list.');
  }, [sellId, sellPrice, visitor, loadListings, haptics]);

  const data = tab === 'browse' ? listings : owned;

  return (
    <SafeAreaView style={styles.safe} testID="marketplace-screen">
      <View style={styles.header}>
        <TouchableOpacity testID="mkt-back" onPress={() => router.back()} style={styles.backBtn}><Text style={styles.backTxt}>‹ Back</Text></TouchableOpacity>
        <Text style={styles.title}>🛒 Marketplace</Text>
        <TouchableOpacity testID="mkt-studio" onPress={() => router.push('/creator' as any)} style={styles.studioBtn}><Text style={styles.studioBtnTxt}>📊 Studio</Text></TouchableOpacity>
        <TouchableOpacity testID="mkt-sell" onPress={() => { setSellMsg(''); setSellModal(true); }} style={styles.sellBtn}><Text style={styles.sellBtnTxt}>＋ Sell</Text></TouchableOpacity>
      </View>

      {banner ? <View testID="mkt-banner" style={styles.bannerBox}><Text style={styles.bannerTxt}>{banner}</Text></View> : null}

      <View style={styles.tabs}>
        <TouchableOpacity testID="mkt-tab-browse" style={[styles.tab, tab === 'browse' && styles.tabActive]} onPress={() => setTab('browse')}><Text style={[styles.tabTxt, tab === 'browse' && styles.tabTxtActive]}>Browse</Text></TouchableOpacity>
        <TouchableOpacity testID="mkt-tab-owned" style={[styles.tab, tab === 'owned' && styles.tabActive]} onPress={() => { setTab('owned'); loadOwned(visitor); }}><Text style={[styles.tabTxt, tab === 'owned' && styles.tabTxtActive]}>My Games ({owned.length})</Text></TouchableOpacity>
      </View>

      {tab === 'browse' ? (
        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.sortRow} contentContainerStyle={{ gap: 8, paddingHorizontal: 16 }}>
          {(['newest', 'bestselling', 'price_low', 'price_high'] as const).map((s) => (
            <TouchableOpacity key={s} testID={`mkt-sort-${s}`} style={[styles.chip, sort === s && styles.chipActive]} onPress={() => setSort(s)}>
              <Text style={[styles.chipTxt, sort === s && styles.chipTxtActive]}>{s === 'price_low' ? 'Price ↑' : s === 'price_high' ? 'Price ↓' : s === 'bestselling' ? 'Best-selling' : 'Newest'}</Text>
            </TouchableOpacity>
          ))}
        </ScrollView>
      ) : null}

      <ScrollView
        contentContainerStyle={{ padding: 16, paddingBottom: 60 }}
        refreshControl={<RefreshControl refreshing={loading} tintColor="#A78BFA"
          onRefresh={() => { loadListings(); if (visitor) loadOwned(visitor); }} />}
      >
        {loading ? <ActivityIndicator color="#A78BFA" style={{ marginTop: 40 }} /> : null}
        {!loading && data.length === 0 ? (
          <Text style={styles.empty}>{tab === 'browse' ? 'No games listed yet. Tap “＋ Sell” to list one (use a game id from /playable).' : 'No purchases yet.'}</Text>
        ) : null}
        {data.map((l) => (
          <View key={l.playable_id} testID={`mkt-row-${l.playable_id}`} style={styles.row}>
            <TouchableOpacity onPress={() => router.push(`/playable?id=${l.playable_id}`)}><Cover id={l.playable_id} hasCover={l.has_cover} /></TouchableOpacity>
            <View style={{ flex: 1, marginLeft: 12, minWidth: 0 }}>
              <Text style={styles.rowTitle} numberOfLines={1}>{l.title}</Text>
              <Text style={styles.rowSub}>{l.genre}{l.overall ? ` · 🧪${l.overall}` : ''}{typeof l.sales === 'number' ? ` · 🛒${l.sales}` : ''}</Text>
            </View>
            {tab === 'browse' ? (
              <TouchableOpacity testID={`mkt-buy-${l.playable_id}`} style={[styles.buyBtn, buying === l.playable_id && { opacity: 0.5 }]} disabled={!!buying} onPress={() => buy(l)}>
                <Text style={styles.buyTxt}>{buying === l.playable_id ? '…' : `$${(l.price_usd || 0).toFixed(2)}`}</Text>
              </TouchableOpacity>
            ) : (
              <TouchableOpacity testID={`mkt-play-${l.playable_id}`} style={styles.playBtn} onPress={() => router.push(`/playable?id=${l.playable_id}`)}><Text style={styles.buyTxt}>▶ Play</Text></TouchableOpacity>
            )}
          </View>
        ))}
      </ScrollView>

      <Modal visible={sellModal} transparent animationType="fade" onRequestClose={() => setSellModal(false)}>
        <View style={styles.modalWrap}>
          <View style={styles.modalCard} testID="mkt-sell-modal">
            <Text style={styles.modalTitle}>List a game for sale</Text>
            <Text style={styles.modalHint}>Paste a game id (from a /playable URL). Price $0.50–$500.</Text>
            <TextInput testID="mkt-sell-id" style={styles.input} value={sellId} onChangeText={setSellId} placeholder="playable_id" placeholderTextColor="#475569" autoCapitalize="none" />
            <TextInput testID="mkt-sell-price" style={styles.input} value={sellPrice} onChangeText={setSellPrice} placeholder="4.99" placeholderTextColor="#475569" keyboardType="decimal-pad" />
            {sellMsg ? <Text style={styles.modalMsg}>{sellMsg}</Text> : null}
            <View style={styles.modalRow}>
              <TouchableOpacity style={styles.modalCancel} onPress={() => setSellModal(false)}><Text style={styles.modalCancelTxt}>Cancel</Text></TouchableOpacity>
              <TouchableOpacity testID="mkt-sell-submit" style={styles.modalSubmit} onPress={submitListing}><Text style={styles.buyTxt}>List</Text></TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#0A0A0A' },
  header: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16, paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: '#262626' },
  backBtn: { paddingVertical: 6, paddingRight: 12 }, backTxt: { color: '#94a3b8', fontSize: 15 },
  title: { flex: 1, color: '#f1f5f9', fontSize: 20, fontWeight: '800' },
  sellBtn: { backgroundColor: '#8B5CF6', borderRadius: 8, paddingHorizontal: 12, paddingVertical: 8 }, sellBtnTxt: { color: '#fff', fontWeight: '700' },
  studioBtn: { backgroundColor: '#1F1F1F', borderRadius: 8, paddingHorizontal: 10, paddingVertical: 8, marginRight: 8, borderWidth: 1, borderColor: '#262626' }, studioBtnTxt: { color: '#A78BFA', fontWeight: '700', fontSize: 13 },
  bannerBox: { backgroundColor: '#1e1b4b', margin: 12, padding: 12, borderRadius: 10, borderWidth: 1, borderColor: '#4338ca' }, bannerTxt: { color: '#c7d2fe', fontSize: 14 },
  tabs: { flexDirection: 'row', paddingHorizontal: 16, gap: 10, marginTop: 10 },
  tab: { paddingVertical: 8, paddingHorizontal: 14, borderRadius: 20, backgroundColor: '#1F1F1F' }, tabActive: { backgroundColor: '#8B5CF6' },
  tabTxt: { color: '#94a3b8', fontWeight: '700' }, tabTxtActive: { color: '#fff' },
  sortRow: { marginTop: 12, maxHeight: 40 },
  chip: { paddingVertical: 6, paddingHorizontal: 12, borderRadius: 16, backgroundColor: '#1F1F1F', borderWidth: 1, borderColor: '#262626' }, chipActive: { backgroundColor: '#2E1B5B', borderColor: '#8B5CF6' },
  chipTxt: { color: '#94a3b8', fontSize: 12 }, chipTxtActive: { color: '#e0e7ff' },
  empty: { color: '#64748b', textAlign: 'center', marginTop: 50, lineHeight: 22, paddingHorizontal: 20 },
  row: { flexDirection: 'row', alignItems: 'center', backgroundColor: '#141414', borderRadius: 12, padding: 12, marginBottom: 10, borderWidth: 1, borderColor: '#262626' },
  coverFallback: { borderRadius: 10, backgroundColor: '#141414', alignItems: 'center', justifyContent: 'center' },
  rowTitle: { color: '#e2e8f0', fontSize: 15, fontWeight: '700' }, rowSub: { color: '#64748b', fontSize: 12, marginTop: 3 },
  buyBtn: { backgroundColor: '#16a34a', borderRadius: 10, paddingHorizontal: 16, paddingVertical: 10, minWidth: 70, alignItems: 'center' },
  playBtn: { backgroundColor: '#2563eb', borderRadius: 10, paddingHorizontal: 16, paddingVertical: 10 },
  buyTxt: { color: '#fff', fontWeight: '800' },
  modalWrap: { flex: 1, backgroundColor: 'rgba(0,0,0,0.7)', justifyContent: 'center', padding: 24 },
  modalCard: { backgroundColor: '#141414', borderRadius: 16, padding: 20, borderWidth: 1, borderColor: '#2E1B5B' },
  modalTitle: { color: '#f1f5f9', fontSize: 18, fontWeight: '800' }, modalHint: { color: '#94a3b8', fontSize: 13, marginTop: 6, marginBottom: 12 },
  input: { backgroundColor: '#0A0A0A', borderRadius: 10, borderWidth: 1, borderColor: '#404040', color: '#e2e8f0', paddingHorizontal: 12, paddingVertical: 10, marginBottom: 10 },
  modalMsg: { color: '#fbbf24', marginBottom: 8 },
  modalRow: { flexDirection: 'row', gap: 10, marginTop: 6 },
  modalCancel: { flex: 1, paddingVertical: 12, borderRadius: 10, backgroundColor: '#262626', alignItems: 'center' }, modalCancelTxt: { color: '#cbd5e1', fontWeight: '700' },
  modalSubmit: { flex: 1, paddingVertical: 12, borderRadius: 10, backgroundColor: '#8B5CF6', alignItems: 'center' },
});
