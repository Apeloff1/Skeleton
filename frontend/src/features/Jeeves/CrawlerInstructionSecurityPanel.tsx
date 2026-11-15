/** Owner-scoped, metadata-only security and recovery view. No raw attack text. */
import React from 'react';
import { Text, View } from 'react-native';
import type { CrawlSession } from '../../product/crawlerClient';
import s from './CrawlerWorkspace.styles';

export default function CrawlerInstructionSecurityPanel({ session }: { session: CrawlSession }) {
  const security = session.instruction_security;
  const origins = session.adaptive_origin_health;
  const duplicates = session.duplicate_evidence;
  const recovery = session.checkpoint_recovery;
  return <View style={s.card}>
    <Text style={s.heading}>Adaptive resilience and source quarantine</Text>
    {recovery && <View style={s.check}>
      <Text style={s.label}>Checkpoint redundancy</Text>
      <Text style={s.small}>{recovery.replica_present ? 'Exact-current recovery copy recorded; not independently verified.' : 'No available exact-current recovery copy: ' + recovery.reason.replaceAll('_', ' ')} No ancestor rollback is permitted.</Text>
      {recovery.last_repair_at !== null && <Text style={s.small}>Last committed repair: {recovery.last_repair_at} · sequence {recovery.last_repair_sequence}</Text>}
    </View>}
    {duplicates && <View style={s.check}>
      <Text style={s.label}>Duplicate acquisition custody</Text>
      <Text style={s.small}>{duplicates.count} duplicate observations across {duplicates.observed_origins} origins; {duplicates.represented_sources} retained primary sources. Mirrored text is not counted as independent corroboration.</Text>
    </View>}
    {!security ? <Text style={s.small}>Instruction inspection evidence is not available from this backend.</Text> :
      <>
        <Text accessibilityLiveRegion="polite" style={security.count ? s.error : s.message}>
          {security.count} recorded instruction incident{security.count === 1 ? '' : 's'}
        </Text>
        <Text style={s.small}>Source-provided agent instructions are never executable authority. Detected material is excluded from ordinary capture or discovery; robots rules still govern permitted access. Receipts retain categories and, where permitted, fingerprints, never attack payloads.</Text>
        {Object.entries(security.categories).map(([code, count]) =>
          <Text key={code} style={s.small}>{code.replaceAll('_', ' ')} · {count}</Text>)}
        {security.records.slice().reverse().slice(0, 12).map(record =>
          <View key={record.sequence} style={s.check}>
            <Text style={s.label}>Incident {record.sequence} · {record.stage.replaceAll('_', ' ')}</Text>
            <Text style={s.small}>{record.categories.map(value => value.replaceAll('_', ' ')).join(' · ')}</Text>
            <Text selectable style={s.small}>URL fingerprint: {record.url_digest}</Text>
            {record.input_digest !== null && <Text selectable style={s.small}>Input fingerprint: {record.input_digest}</Text>}
            {record.inspection_limited && <Text style={s.error}>Inspection limit reached; content held.</Text>}
          </View>)}
        {security.count > 12 && <Text style={s.small}>Latest 12 shown; all {security.count} incident receipts remain in the owned session checkpoint.</Text>}
      </>}
    {!origins ? <Text style={s.small}>Adaptive origin-health observations have not been returned.</Text> :
      Object.entries(origins).map(([host, health]) =>
        <View key={host} style={s.check}>
          <Text style={s.label}>{host}</Text>
          <Text style={s.small}>{health.successes} useful outcomes · {health.failures} failures · {health.rejections} rejections</Text>
          <Text style={s.small}>{health.evidence_count ? 'Smoothed success estimate: ' + Math.round(health.posterior_success * 100) + '%' : 'No observed dispatch outcomes yet'}. {health.failure_streak ? 'Consecutive recent failures: ' + health.failure_streak + '.' : ''}</Text>
        </View>)}
    <Text style={s.small}>Health estimates rank already-admitted work only; they do not override consent, site denials, budgets, or robots policy.</Text>
  </View>;
}
