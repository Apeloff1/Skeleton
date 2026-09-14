import { useEffect, useMemo, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { AppHeader, Button, Screen, SectionHeader } from '../components/UI';
import theme from '../theme/tokens';
import { coinsForSeconds, loadWorkforce } from '../src/workspaces/workforceStore';
import { createValueEntry, loadWealth, saveWealth, totalValue, ValueEntry } from '../src/workspaces/wealthStore';

export default function WealthScreen() {
  const router = useRouter();
  const [hoursSeconds, setHoursSeconds] = useState(0);
  const [entries, setEntries] = useState<ValueEntry[]>([]);
  const [amount, setAmount] = useState('');
  const [note, setNote] = useState('');

  useEffect(() => {
    loadWorkforce().then(work => setHoursSeconds(work.totalSeconds)).catch(() => {});
    loadWealth().then(data => setEntries(data.entries)).catch(() => {});
  }, []);

  const trackedHours = hoursSeconds / 3600;
  const coins = coinsForSeconds(hoursSeconds);
  const value = useMemo(() => totalValue(entries), [entries]);
  const valuePerHour = trackedHours > 0 ? value / trackedHours : 0;

  const addEntry = async () => {
    const parsed = Number(amount.replace(',', '.'));
    if (!Number.isFinite(parsed) || parsed === 0) return;
    const next = [createValueEntry(parsed, note), ...entries].slice(0, 500);
    setEntries(next);
    setAmount('');
    setNote('');
    await saveWealth({ entries: next });
  };

  const removeEntry = async (id: string) => {
    const next = entries.filter(entry => entry.id !== id);
    setEntries(next);
    await saveWealth({ entries: next });
  };

  return (
    <Screen edges={['top', 'left', 'right']}>
      <AppHeader
        title="Wealth & Progress"
        subtitle="Work hours → value → long-range progression"
        onBack={() => router.back()}
      />
      <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
        <View style={styles.hero}>
          <View>
            <Text style={styles.eyebrow}>NET RECORDED VALUE</Text>
            <Text style={[styles.heroValue, { color: value >= 0 ? theme.colors.success : theme.colors.danger }]}>NOK {value.toLocaleString(undefined, { maximumFractionDigits: 0 })}</Text>
          </View>
          <View style={styles.heroIcon}>
            <Ionicons name={value >= 0 ? 'trending-up' : 'trending-down'} size={26} color={value >= 0 ? theme.colors.success : theme.colors.danger} />
          </View>
        </View>

        <View style={styles.metrics}>
          <Metric label="Tracked hours" value={trackedHours.toFixed(1)} icon="time" color={theme.colors.info} />
          <Metric label="Fantasy coins" value={coins.toLocaleString()} icon="diamond" color={theme.colors.warning} />
          <Metric label="Value / hour" value={`NOK ${Math.round(valuePerHour).toLocaleString()}`} icon="speedometer" color={theme.colors.primaryHover} />
        </View>

        <SectionHeader title="Record Value" subtitle="Positive for created value or profit · negative for cost/loss" />
        <View style={styles.formCard}>
          <View style={styles.amountRow}>
            <View style={styles.currencyBox}><Text style={styles.currencyText}>NOK</Text></View>
            <TextInput
              value={amount}
              onChangeText={setAmount}
              placeholder="0"
              placeholderTextColor={theme.colors.textDisabled}
              keyboardType="decimal-pad"
              style={styles.amountInput}
            />
          </View>
          <TextInput
            value={note}
            onChangeText={setNote}
            placeholder="What created or consumed this value?"
            placeholderTextColor={theme.colors.textDisabled}
            style={styles.noteInput}
          />
          <Button title="Add to ledger" icon="add-circle" onPress={() => addEntry().catch(() => {})} />
        </View>

        <SectionHeader title="Value Ledger" subtitle={`${entries.length} entries · newest first`} />
        <View style={styles.ledger}>
          {entries.length === 0 ? (
            <View style={styles.empty}>
              <Ionicons name="analytics-outline" size={28} color={theme.colors.textDim} />
              <Text style={styles.emptyTitle}>No value entries yet</Text>
              <Text style={styles.emptyText}>The old hours-versus-profit idea now shares time data with Work OS and keeps value in a separate durable ledger.</Text>
            </View>
          ) : entries.slice(0, 50).map(entry => (
            <View key={entry.id} style={styles.entryRow}>
              <View style={[styles.directionIcon, { backgroundColor: entry.amount >= 0 ? `${theme.colors.success}20` : `${theme.colors.danger}20` }]}>
                <Ionicons name={entry.amount >= 0 ? 'arrow-up' : 'arrow-down'} size={16} color={entry.amount >= 0 ? theme.colors.success : theme.colors.danger} />
              </View>
              <View style={styles.entryBody}>
                <Text style={styles.entryTitle}>{entry.note || (entry.amount >= 0 ? 'Value created' : 'Cost')}</Text>
                <Text style={styles.entryDate}>{new Date(entry.createdAt).toLocaleString()}</Text>
              </View>
              <Text style={[styles.entryAmount, { color: entry.amount >= 0 ? theme.colors.success : theme.colors.danger }]}>
                {entry.amount >= 0 ? '+' : ''}{Math.round(entry.amount).toLocaleString()}
              </Text>
              <Pressable accessibilityRole="button" accessibilityLabel="Delete entry" onPress={() => removeEntry(entry.id).catch(() => {})} hitSlop={8} style={styles.deleteBtn}>
                <Ionicons name="close" size={16} color={theme.colors.textDim} />
              </Pressable>
            </View>
          ))}
        </View>
      </ScrollView>
    </Screen>
  );
}

function Metric({ label, value, icon, color }: { label: string; value: string; icon: string; color: string }) {
  return (
    <View style={styles.metric}>
      <Ionicons name={icon as any} size={17} color={color} />
      <Text style={[styles.metricValue, { color }]} numberOfLines={1}>{value}</Text>
      <Text style={styles.metricLabel}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  content: { padding: theme.spacing.base, paddingBottom: 80, gap: theme.spacing.md },
  hero: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: theme.spacing.xl,
    borderRadius: theme.radii['2xl'],
    borderWidth: 1,
    borderColor: theme.colors.border,
    backgroundColor: theme.colors.surface,
  },
  eyebrow: { ...theme.typography.micro, color: theme.colors.textMuted },
  heroValue: { ...theme.typography.display, marginTop: 8 },
  heroIcon: { width: 52, height: 52, borderRadius: theme.radii.lg, alignItems: 'center', justifyContent: 'center', backgroundColor: theme.colors.surfaceAlt },
  metrics: { flexDirection: 'row', gap: theme.spacing.sm },
  metric: { flex: 1, minHeight: 92, borderRadius: theme.radii.lg, padding: theme.spacing.md, borderWidth: 1, borderColor: theme.colors.border, backgroundColor: theme.colors.surface },
  metricValue: { ...theme.typography.h4, marginTop: 8 },
  metricLabel: { ...theme.typography.caption, color: theme.colors.textMuted, marginTop: 2 },
  formCard: { padding: theme.spacing.base, gap: theme.spacing.md, borderRadius: theme.radii.xl, borderWidth: 1, borderColor: theme.colors.border, backgroundColor: theme.colors.surface },
  amountRow: { flexDirection: 'row', minHeight: 52, borderWidth: 1, borderColor: theme.colors.borderStrong, borderRadius: theme.radii.md, overflow: 'hidden', backgroundColor: theme.colors.bgSubtle },
  currencyBox: { minWidth: 64, alignItems: 'center', justifyContent: 'center', borderRightWidth: 1, borderRightColor: theme.colors.border },
  currencyText: { ...theme.typography.caption, color: theme.colors.textMuted },
  amountInput: { flex: 1, color: theme.colors.text, paddingHorizontal: theme.spacing.md, ...theme.typography.h4 },
  noteInput: { minHeight: 48, color: theme.colors.text, paddingHorizontal: theme.spacing.md, borderWidth: 1, borderColor: theme.colors.borderStrong, borderRadius: theme.radii.md, backgroundColor: theme.colors.bgSubtle, ...theme.typography.body },
  ledger: { borderRadius: theme.radii.xl, overflow: 'hidden', borderWidth: 1, borderColor: theme.colors.border, backgroundColor: theme.colors.surface },
  entryRow: { minHeight: 64, flexDirection: 'row', alignItems: 'center', paddingHorizontal: theme.spacing.md, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: theme.colors.border },
  directionIcon: { width: 34, height: 34, borderRadius: theme.radii.md, alignItems: 'center', justifyContent: 'center' },
  entryBody: { flex: 1, paddingHorizontal: 10 },
  entryTitle: { ...theme.typography.body, color: theme.colors.text },
  entryDate: { ...theme.typography.caption, color: theme.colors.textMuted, marginTop: 2 },
  entryAmount: { ...theme.typography.monoSm, fontSize: 13 },
  deleteBtn: { width: 30, height: 30, alignItems: 'center', justifyContent: 'center', marginLeft: 4 },
  empty: { padding: theme.spacing.xl, alignItems: 'center' },
  emptyTitle: { ...theme.typography.h4, color: theme.colors.text, marginTop: 10 },
  emptyText: { ...theme.typography.body, color: theme.colors.textMuted, textAlign: 'center', marginTop: 6 },
});
