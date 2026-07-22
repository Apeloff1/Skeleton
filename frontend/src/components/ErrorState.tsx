/**
 * ErrorState — friendly screen-level error / offline placeholder (Cat-4.7).
 *
 * Use after a failed data fetch. Shows the user a tappable Retry CTA and
 * an optional diagnostic blurb. A11y labels included.
 *
 * <ErrorState
 *   title="Couldn’t load achievements"
 *   detail="Your network might be offline."
 *   onRetry={refetch}
 * />
 */
import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';

interface Props {
  title?: string;
  detail?: string;
  onRetry?: () => void;
  ctaLabel?: string;
}

export function ErrorState({ title = "Something went wrong", detail, onRetry, ctaLabel = "Retry" }: Props) {
  return (
    <View style={styles.container} accessibilityRole="alert">
      <Text style={styles.icon}>⚠️</Text>
      <Text style={styles.title}>{title}</Text>
      {detail ? <Text style={styles.detail}>{detail}</Text> : null}
      {onRetry ? (
        <TouchableOpacity
          onPress={onRetry}
          style={styles.btn}
          accessibilityRole="button"
          accessibilityLabel={ctaLabel}
          activeOpacity={0.85}>
          <Text style={styles.btnText}>{ctaLabel}</Text>
        </TouchableOpacity>
      ) : null}
    </View>
  );
}

export default ErrorState;

const styles = StyleSheet.create({
  container: { flex: 1, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 32 },
  icon:      { fontSize: 40, marginBottom: 14 },
  title:     { color: '#fff', fontSize: 17, fontWeight: '800', textAlign: 'center', marginBottom: 8 },
  detail:    { color: '#9ca3af', fontSize: 13, textAlign: 'center', lineHeight: 19, marginBottom: 18 },
  btn:       { backgroundColor: '#7c3aed', paddingHorizontal: 26, paddingVertical: 13, borderRadius: 999, minHeight: 46, justifyContent: 'center' },
  btnText:   { color: '#fff', fontSize: 14, fontWeight: '800' },
});
