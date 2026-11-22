/**
 * Minimal expo-router stand-in for rendering route components in isolation
 * (react-native-web screen harness). Navigation calls are recorded on
 * window.__nav so journeys can assert them; nothing navigates for real.
 */
import React from 'react';
import { Pressable } from 'react-native';

type Nav = { action: string; href?: unknown };
const log = (entry: Nav) => {
  const w = window as unknown as { __nav?: Nav[] };
  (w.__nav ??= []).push(entry);
};
const params = (): Record<string, string> => Object.fromEntries(new URLSearchParams(location.search));

export const router = {
  push: (href: unknown) => log({ action: 'push', href }),
  replace: (href: unknown) => log({ action: 'replace', href }),
  navigate: (href: unknown) => log({ action: 'navigate', href }),
  back: () => log({ action: 'back' }),
  canGoBack: () => true,
  setParams: (p: unknown) => log({ action: 'setParams', href: p }),
  dismiss: () => log({ action: 'dismiss' }),
  dismissAll: () => log({ action: 'dismissAll' }),
  canDismiss: () => false,
};
export const useRouter = () => router;
export const useLocalSearchParams = () => params();
export const useGlobalSearchParams = () => params();
export const usePathname = () => '/' + (params().screen ?? '');
export const useSegments = () => [params().screen ?? ''];
export const useNavigation = () => ({ setOptions: () => {}, addListener: () => () => {}, goBack: router.back, navigate: router.push, canGoBack: () => true, getParent: () => undefined, isFocused: () => true });
export const useFocusEffect = (effect: () => void | (() => void)) => { React.useEffect(() => effect(), [effect]); };
export const useRootNavigationState = () => ({ key: 'root' });
export const Redirect = ({ href }: { href: unknown }) => { React.useEffect(() => log({ action: 'redirect', href }), [href]); return null; };
export function Link({ href, children, asChild, ...rest }: { href: unknown; children?: React.ReactNode; asChild?: boolean; [k: string]: unknown }) {
  if (asChild && React.isValidElement(children)) return React.cloneElement(children as React.ReactElement<{ onPress?: () => void }>, { onPress: () => log({ action: 'link', href }) });
  return <Pressable accessibilityRole="link" onPress={() => log({ action: 'link', href })} {...rest}>{children}</Pressable>;
}
const Screen = (_: unknown) => null;
export const Stack = Object.assign(({ children }: { children?: React.ReactNode }) => <>{children}</>, { Screen });
export const Tabs = Stack;
export const Slot = () => null;
export default { router };
