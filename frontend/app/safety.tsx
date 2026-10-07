/**
 * /safety — VII.5 Governance & Safety console (DELUXE).
 * Platform trust surface: safety KPIs, the open moderation queue (with one-tap
 * warn / hide / dismiss), and the immutable audit trail.
 * Backed by /api/governance/{overview,reports,moderate/{rid},audit}.
 */
import { useState, useEffect, useCallback } from 'react';
import {
  View, Text, ScrollView, ActivityIndicator, TouchableOpacity,
  StyleSheet, SafeAreaView, RefreshControl,
} from 'react-native';
import { useRouter } from 'expo-router';
import api from '../src/utils/apiClient';
import { C, S, R } from '../src/theme/deluxe';

type Overview = {
  games: number; hidden: number; warned: number; in_review: number;
  open_reports: number; open_appeals: number; audit_entries: number;
};
type Report = {
  report_id: string; playable_id: string; reason: string; detail: string;
  reporter_id: string; status: string; created_at: string;
  title: string; genre: string; moderation_status: string;
};
type Appeal = {
  appeal_id: string; playable_id: string; reason: string; creator_id: string;
  moderation_status: string; current_status: string; status: string; created_at: string;
  title: string; genre: string; age_hours?: number; sla_days?: number; sla_breached?: boolean;
};
type Audit = { audit_id: string; action: string; target_id: string; actor: string; at: string; detail: any };

const REASON_COLOR: Record<string, string> = {
  inappropriate: C.error, offensive: C.error, copyright: C.gold,
  broken: C.warning, spam: C.info, other: C.textMute,
};
const ACTION_ICON: Record<string, string> = { scan: '🛡️', report: '🚩', moderate: '⚖️' };

export default function Safety() {
  const router = useRouter();
  const [ov, setOv] = useState<Overview | null>(null);
  const [reports, setReports] = useState<Report[]>([]);
  const [appeals, setAppeals] = useState<Appeal[]>([]);
  const [audit, setAudit] = useState<Audit[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [busy, setBusy] = useState<string>('');

  const load = useCallback(async () => {
    const [o, r, ap, a] = await Promise.all([
      api.get<Overview>('/api/governance/overview', { timeoutMs: 12000 }),
      api.get<{ reports: Report[] }>('/api/governance/reports?status=open', { timeoutMs: 12000 }),
      api.get<{ appeals: Appeal[] }>('/api/governance/appeals?status=open', { timeoutMs: 12000 }),
      api.get<{ entries: Audit[] }>('/api/governance/audit?limit=20', { timeoutMs: 12000 }),
    ]);
    if (o.ok && o.data) setOv(o.data);
    if (r.ok && r.data) setReports(r.data.reports || []);
    if (ap.ok && ap.data) setAppeals(ap.data.appeals || []);
    if (a.ok && a.data) setAudit(a.data.entries || []);
    setLoading(false); setRefreshing(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  const moderate = useCallback(async (rid: string, action: string) => {
    setBusy(rid);
    const r = await api.post(`/api/governance/moderate/${rid}`, { action, actor: 'moderator' }, { timeoutMs: 12000 });
    setBusy('');
    if (r.ok) load();
  }, [load]);

  const resolveAppeal = useCallback(async (aid: string, action: string) => {
    setBusy(aid);
    const r = await api.post(`/api/governance/appeal/${aid}/resolve`, { action, actor: 'moderator' }, { timeoutMs: 12000 });
    setBusy('');
    if (r.ok) load();
  }, [load]);

  return (
    <SafeAreaView style={styles.safe} testID="safety-screen">
      <View style={styles.header}>
        <TouchableOpacity testID="safety-back" onPress={() => router.back()} style={styles.backBtn}><Text style={styles.backTxt}>‹ Back</Text></TouchableOpacity>
        <Text style={styles.title}>🛡️ Trust & Safety</Text>
      </View>
      {loading ? <ActivityIndicator color={C.brand} style={{ marginTop: S.xxl }} /> : (
        <ScrollView
          contentContainerStyle={{ padding: S.lg, paddingBottom: S.xxxl }}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} tintColor={C.brand} />}
        >
          {ov ? (
            <View style={styles.kpiGrid}>
              <Kpi label="Games" value={ov.games} accent={C.brand2} testID="safety-kpi-games" />
              <Kpi label="Open Reports" value={ov.open_reports} accent={ov.open_reports ? C.error : C.success} testID="safety-kpi-open" />
              <Kpi label="Appeals" value={ov.open_appeals} accent={ov.open_appeals ? C.gold : C.success} testID="safety-kpi-appeals" />
              <Kpi label="In Review" value={ov.in_review} accent={C.warning} testID="safety-kpi-review" />
              <Kpi label="Warned" value={ov.warned} accent={C.gold} testID="safety-kpi-warned" />
              <Kpi label="Hidden" value={ov.hidden} accent={C.error} testID="safety-kpi-hidden" />
              <Kpi label="Audit Log" value={ov.audit_entries} accent={C.info} testID="safety-kpi-audit" />
            </View>
          ) : null}

          <Text style={styles.section}>MODERATION QUEUE</Text>
          {reports.length === 0 ? (
            <View style={styles.cleanCard} testID="safety-queue-empty">
              <Text style={styles.cleanEmoji}>✅</Text>
              <Text style={styles.cleanTxt}>Queue is clear — no open reports.</Text>
            </View>
          ) : reports.map((r) => (
            <View key={r.report_id} testID={`safety-report-${r.report_id}`} style={styles.card}>
              <View style={styles.cardTop}>
                <View style={[styles.reasonTag, { borderColor: REASON_COLOR[r.reason] || C.textMute }]}>
                  <Text style={[styles.reasonTxt, { color: REASON_COLOR[r.reason] || C.textMute }]}>{r.reason}</Text>
                </View>
                <Text style={styles.cardTitle} numberOfLines={1}>{r.title}</Text>
              </View>
              {r.detail ? <Text style={styles.detail} numberOfLines={2}>“{r.detail}”</Text> : null}
              <Text style={styles.meta}>by {r.reporter_id} · {r.genre} · mod: {r.moderation_status}</Text>
              <View style={styles.actions}>
                <Act label="Dismiss" color={C.textMute} disabled={busy === r.report_id} onPress={() => moderate(r.report_id, 'dismiss')} testID={`safety-dismiss-${r.report_id}`} />
                <Act label="Warn" color={C.gold} disabled={busy === r.report_id} onPress={() => moderate(r.report_id, 'warn')} testID={`safety-warn-${r.report_id}`} />
                <Act label="Hide" color={C.error} disabled={busy === r.report_id} onPress={() => moderate(r.report_id, 'hide')} testID={`safety-hide-${r.report_id}`} />
              </View>
            </View>
          ))}

          <Text style={styles.section}>CREATOR APPEALS</Text>
          {appeals.length === 0 ? (
            <View style={styles.cleanCard} testID="safety-appeals-empty">
              <Text style={styles.cleanEmoji}>⚖️</Text>
              <Text style={styles.cleanTxt}>No pending appeals.</Text>
            </View>
          ) : appeals.map((ap) => (
            <View key={ap.appeal_id} testID={`safety-appeal-${ap.appeal_id}`} style={styles.card}>
              <View style={styles.cardTop}>
                <View style={[styles.reasonTag, { borderColor: C.gold }]}>
                  <Text style={[styles.reasonTxt, { color: C.gold }]}>{ap.current_status}</Text>
                </View>
                <Text style={styles.cardTitle} numberOfLines={1}>{ap.title}</Text>
              </View>
              <Text style={styles.detail} numberOfLines={3}>“{ap.reason}”</Text>
              <Text style={styles.meta}>
                by {ap.creator_id} · {ap.genre} · {ap.age_hours != null ? (ap.age_hours < 48 ? `${Math.round(ap.age_hours)}h old` : `${Math.round(ap.age_hours / 24)}d old`) : ''}
                {ap.sla_breached ? '  ⏰ SLA BREACHED' : ''}
              </Text>
              <View style={styles.actions}>
                <Act label="Uphold" color={C.error} disabled={busy === ap.appeal_id} onPress={() => resolveAppeal(ap.appeal_id, 'uphold')} testID={`safety-uphold-${ap.appeal_id}`} />
                <Act label="Restore" color={C.success} disabled={busy === ap.appeal_id} onPress={() => resolveAppeal(ap.appeal_id, 'restore')} testID={`safety-restore-${ap.appeal_id}`} />
              </View>
            </View>
          ))}

          <Text style={styles.section}>AUDIT TRAIL</Text>
          {audit.length === 0 ? <Text style={styles.empty}>No audit entries yet.</Text> : audit.map((a) => (
            <View key={a.audit_id} testID={`safety-audit-${a.audit_id}`} style={styles.auditRow}>
              <Text style={styles.auditIcon}>{ACTION_ICON[a.action] || '•'}</Text>
              <View style={{ flex: 1, minWidth: 0 }}>
                <Text style={styles.auditTxt} numberOfLines={1}>
                  <Text style={styles.auditAction}>{a.action}</Text> · {a.target_id.slice(0, 8)} · {a.actor}
                </Text>
                <Text style={styles.auditTs}>{new Date(a.at).toLocaleString()}</Text>
              </View>
            </View>
          ))}
        </ScrollView>
      )}
    </SafeAreaView>
  );
}

function Kpi({ label, value, accent, testID }: { label: string; value: number; accent: string; testID: string }) {
  return (
    <View style={styles.kpi} testID={testID}>
      <Text style={[styles.kpiValue, { color: accent }]}>{value}</Text>
      <Text style={styles.kpiLabel}>{label}</Text>
    </View>
  );
}

function Act({ label, color, onPress, disabled, testID }: { label: string; color: string; onPress: () => void; disabled?: boolean; testID: string }) {
  return (
    <TouchableOpacity testID={testID} disabled={disabled} onPress={onPress} activeOpacity={0.8} style={[styles.actBtn, { borderColor: color, opacity: disabled ? 0.5 : 1 }]}>
      <Text style={[styles.actTxt, { color }]}>{label}</Text>
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: C.bg },
  header: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: S.lg, paddingVertical: S.md, borderBottomWidth: 1, borderBottomColor: C.border },
  backBtn: { paddingVertical: 6, paddingRight: S.md, minHeight: 44, justifyContent: 'center' }, backTxt: { color: C.textMute, fontSize: 15, fontWeight: '600' },
  title: { flex: 1, color: C.text, fontSize: 20, fontWeight: '800', letterSpacing: 0.3 },
  kpiGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: S.md },
  kpi: { width: '30%', flexGrow: 1, backgroundColor: C.surface, borderRadius: R.lg, borderWidth: 1, borderColor: C.border, paddingVertical: S.lg, paddingHorizontal: S.md, alignItems: 'center' },
  kpiValue: { fontSize: 22, fontWeight: '800', letterSpacing: 0.5 },
  kpiLabel: { color: C.textMute, fontSize: 10, fontWeight: '700', letterSpacing: 0.8, marginTop: 4, textTransform: 'uppercase' },
  section: { color: C.textDim, fontSize: 13, fontWeight: '800', letterSpacing: 1.5, marginTop: S.xl, marginBottom: S.md },
  empty: { color: C.textMute, textAlign: 'center', marginVertical: S.lg },
  cleanCard: { backgroundColor: C.surface, borderRadius: R.lg, borderWidth: 1, borderColor: C.border, padding: S.xl, alignItems: 'center' },
  cleanEmoji: { fontSize: 32, marginBottom: S.sm }, cleanTxt: { color: C.textMute, fontSize: 14 },
  card: { backgroundColor: C.surface, borderRadius: R.lg, borderWidth: 1, borderColor: C.border, padding: S.md, marginBottom: S.md },
  cardTop: { flexDirection: 'row', alignItems: 'center', gap: S.sm },
  reasonTag: { borderWidth: 1, borderRadius: R.sm, paddingHorizontal: 8, paddingVertical: 3 },
  reasonTxt: { fontSize: 10, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 0.6 },
  cardTitle: { flex: 1, color: C.text, fontSize: 15, fontWeight: '700' },
  detail: { color: C.textDim, fontSize: 13, fontStyle: 'italic', marginTop: S.sm },
  meta: { color: C.textMute, fontSize: 11, marginTop: 6 },
  actions: { flexDirection: 'row', gap: S.sm, marginTop: S.md },
  actBtn: { flex: 1, borderWidth: 1, borderRadius: R.md, paddingVertical: 10, alignItems: 'center', minHeight: 44, justifyContent: 'center' },
  actTxt: { fontSize: 13, fontWeight: '800', letterSpacing: 0.4 },
  auditRow: { flexDirection: 'row', alignItems: 'center', backgroundColor: C.surface2, borderRadius: R.md, padding: S.md, marginBottom: S.sm, gap: S.md },
  auditIcon: { fontSize: 16 },
  auditTxt: { color: C.textDim, fontSize: 13 }, auditAction: { color: C.text, fontWeight: '800' },
  auditTs: { color: C.textMute, fontSize: 11, marginTop: 2 },
});
