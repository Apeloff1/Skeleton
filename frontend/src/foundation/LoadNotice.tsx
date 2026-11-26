/**
 * Inline loading and load-failure notices for screens that fetch ad hoc
 * (screens on useQuery should use AsyncView instead).
 *
 * - LoadingNotice: named progressbar with aria-busy, so screen readers hear
 *   what is loading instead of an unnamed spinner.
 * - LoadErrorNotice: role=alert with an honest message and, when retrying can
 *   help, a 44pt "Try again" button. Replaces silently-empty screens.
 * Token-only, no gradients/haptics: renders identically on native and web/SSR.
 */
import React from 'react';
import { ActivityIndicator, Pressable, View } from 'react-native';
import { AppText } from './AppText';
import { color } from './tokens';
import { MIN_TOUCH_TARGET } from './a11y';
import { t } from './strings';
import type { LoadFailure } from './loadFailure';

export interface LoadingNoticeProps {
  /** What is loading, e.g. "worlds". Announced as "Loading worlds…". */
  what?: string;
  testID?: string;
}

export function LoadingNotice({ what, testID }: LoadingNoticeProps) {
  const label = what ? `${t('state.loading').replace(/…$/, '').replace(/ …$/, '')} ${what}…` : t('state.loading');
  return (
    <View
      testID={testID}
      role="progressbar"
      aria-label={label}
      aria-busy
      style={{ alignItems: 'center', paddingVertical: 24, gap: 8 }}
    >
      <ActivityIndicator color={color.primary} aria-hidden />
      <AppText color="textMuted">{label}</AppText>
    </View>
  );
}

export interface LoadErrorNoticeProps {
  failure: LoadFailure;
  /** What failed to load, e.g. "worlds". */
  what?: string;
  onRetry?: () => void;
  testID?: string;
}

export function LoadErrorNotice({ failure, what, onRetry, testID }: LoadErrorNoticeProps) {
  const title = what ? t('load.failedTitle', { what }) : t('state.error');
  const canRetry = failure.retryable && typeof onRetry === 'function';
  return (
    <View
      testID={testID}
      role="alert"
      style={{
        borderWidth: 1,
        borderColor: color.danger,
        backgroundColor: color.surface,
        borderRadius: 12,
        padding: 16,
        gap: 8,
        marginVertical: 12,
      }}
    >
      <AppText variant="h3" color="danger">{title}</AppText>
      <AppText>{failure.message}</AppText>
      {failure.detail && failure.detail !== failure.message ? (
        <AppText color="textMuted" variant="caption">{failure.detail}</AppText>
      ) : null}
      {canRetry ? (
        <Pressable
          role="button"
          aria-label={what ? `${t('state.retry')}: ${what}` : t('state.retry')}
          onPress={onRetry}
          testID={testID ? `${testID}-retry` : undefined}
          style={({ pressed }) => ({
            alignSelf: 'flex-start',
            minHeight: MIN_TOUCH_TARGET,
            minWidth: MIN_TOUCH_TARGET,
            paddingHorizontal: 16,
            justifyContent: 'center',
            borderRadius: 10,
            backgroundColor: pressed ? color.primaryPressed : color.primary,
          })}
        >
          <AppText color="onPrimary" variant="label">{t('state.retry')}</AppText>
        </Pressable>
      ) : null}
    </View>
  );
}

export default LoadErrorNotice;
