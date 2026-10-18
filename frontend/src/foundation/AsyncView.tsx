import React from 'react';
import { ActivityIndicator, View } from 'react-native';
import { EmptyState, ErrorState } from '../components/primitives';
import { AppText } from './AppText';
import { Stack } from './Stack';
import { color } from './tokens';
import { t } from './strings';
import type { UseQueryResult } from './useQuery';

export interface AsyncViewProps<T> {
  query: UseQueryResult<T>;
  children: (data: T) => React.ReactNode;
  emptyTitle?: string;
  emptyMessage?: string;
  loadingLabel?: string;
}

/** Uniform loading / error / empty / ready rendering for any `useQuery` result. */
export function AsyncView<T>({ query, children, emptyTitle, emptyMessage, loadingLabel }: AsyncViewProps<T>) {
  switch (query.view) {
    case 'loading':
      return (
        <View accessibilityRole="progressbar" accessibilityLabel={loadingLabel ?? t('state.loading')} accessibilityState={{ busy: true }}>
          <Stack align="center" padding="xl" gap="sm">
            <ActivityIndicator color={color.primary} />
            <AppText color="textMuted">{loadingLabel ?? t('state.loading')}</AppText>
          </Stack>
        </View>
      );
    case 'error':
      return <ErrorState title={t('state.error')} error={query.error} onRetry={() => { void query.refetch(); }} />;
    case 'empty':
      return <EmptyState title={emptyTitle ?? t('state.empty')} message={emptyMessage ?? t('state.emptyHint')} />;
    default:
      return <>{children(query.data as T)}</>;
  }
}

export default AsyncView;
