/**
 * Tab shell for the signed-in app at /app (inside the auth-gated (account)
 * group). Lives under its own /app prefix so the launcher at `/` and the
 * existing flat routes (/forge, /settings, …) are untouched.
 */
import { Tabs } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { color, minTouch, usePresence, useT } from '../../../src/foundation';

export { RouteErrorFallback as ErrorBoundary } from '../../../src/foundation';

type IconName = keyof typeof Ionicons.glyphMap;
const icon = (name: IconName) => function TabIcon({ color: tint, size }: { color: string; size: number }) {
  return <Ionicons name={name} size={size} color={tint} />;
};

export default function AppTabsLayout() {
  const { t } = useT();
  // Presence for the signed-in shell (POST /api/v1/presence join/heartbeat/leave).
  usePresence('app');
  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: color.focus,
        tabBarInactiveTintColor: color.textMuted,
        tabBarStyle: { backgroundColor: color.surface, borderTopColor: color.border, minHeight: minTouch + 12 },
        tabBarItemStyle: { minHeight: minTouch },
        sceneStyle: { backgroundColor: color.bg },
      }}
    >
      <Tabs.Screen name="index" options={{ title: t('tab.home'), tabBarAccessibilityLabel: t('tab.home'), tabBarIcon: icon('home-outline') }} />
      <Tabs.Screen name="forge" options={{ title: t('tab.forge'), tabBarAccessibilityLabel: t('tab.forge'), tabBarIcon: icon('hammer-outline') }} />
      <Tabs.Screen name="projects" options={{ title: t('tab.projects'), tabBarAccessibilityLabel: t('tab.projects'), tabBarIcon: icon('folder-open-outline') }} />
      <Tabs.Screen name="settings" options={{ title: t('tab.settings'), tabBarAccessibilityLabel: t('tab.settings'), tabBarIcon: icon('settings-outline') }} />
    </Tabs>
  );
}
