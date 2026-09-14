import { Pressable, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { usePathname, useRouter } from 'expo-router';
import theme from '../theme/tokens';

const HIDDEN_PATHS = new Set(['/', '/welcome', '/safe-mode']);

/**
 * Persistent bridge from the legacy route graph into the canonical workspace
 * model. Kept deliberately small so it does not become another navigation
 * system: one tap always opens the unified workspace navigator.
 */
export default function WorkspaceDock() {
  const router = useRouter();
  const pathname = usePathname();

  if (HIDDEN_PATHS.has(pathname || '/')) return null;
  if (pathname === '/workspaces') return null;

  return (
    <View pointerEvents="box-none" style={styles.host}>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel="Open unified workspaces"
        onPress={() => router.push('/workspaces' as any)}
        style={({ pressed }) => [styles.button, pressed && styles.pressed]}
      >
        <View style={styles.iconWrap}>
          <Ionicons name="grid" size={16} color={theme.colors.primaryHover} />
        </View>
        <Text style={styles.label}>Workspaces</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  host: {
    position: 'absolute',
    right: 14,
    bottom: 18,
    zIndex: 900,
  },
  button: {
    minHeight: 44,
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: theme.radii.full,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 7,
    backgroundColor: theme.colors.bgElevated,
    borderWidth: 1,
    borderColor: theme.colors.borderStrong,
    ...theme.elevation.lg,
  },
  pressed: { opacity: 0.72, transform: [{ scale: 0.98 }] },
  iconWrap: {
    width: 30,
    height: 30,
    borderRadius: 15,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: theme.colors.primarySoft,
  },
  label: { ...theme.typography.buttonSm, color: theme.colors.text, paddingRight: 3 },
});
