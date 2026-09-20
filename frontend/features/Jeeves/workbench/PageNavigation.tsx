import React, { useEffect, useState } from 'react';
import { Text, View } from 'react-native';
import { paginate } from './pagination';
import type { Page } from './pagination';
import { Action, styles } from './ui';

export function usePage<T>(items: readonly T[], filterKey: string) {
  const [requested, setRequested] = useState(0);
  useEffect(() => { setRequested(0); }, [filterKey]);
  const page = paginate(items, requested);
  return { page, setPage: setRequested };
}

export function Pagination<T>({ page, setPage, label }: {
  page: Page<T>;
  setPage: (index: number) => void;
  label: string;
}) {
  if (page.total <= page.size) return null;
  return <View style={[styles.card, styles.wrap]}>
    <Text accessibilityLiveRegion="polite" style={styles.small}>{label}: {page.first}–{page.last} of {page.total}</Text>
    <Action label={`Previous ${label}`} disabled={!page.hasPrevious} onPress={() => setPage(page.index - 1)} compact />
    <Text style={styles.small}>Page {page.index + 1} / {page.pages}</Text>
    <Action label={`Next ${label}`} disabled={!page.hasNext} onPress={() => setPage(page.index + 1)} compact />
  </View>;
}
