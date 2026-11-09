import { Stack } from 'expo-router';

/** Nested forge-operator routes (hub + deep-linkable stubs). */
export default function ForgeOperatorLayout() {
  return <Stack screenOptions={{ headerShown: false, animation: 'slide_from_right' }} />;
}
