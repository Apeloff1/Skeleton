/**
 * platformStyles
 * -------------------------------------------------------------------
 * Tiny cross-platform helpers to keep RN-web free of deprecation noise
 * while preserving optimal native behaviour.
 *
 * NATIVE_DRIVER — use for every Animated `useNativeDriver` flag. It is
 * `true` on iOS/Android (so animations run off-thread, as intended) and
 * `false` on web, where react-native-web has no native animated module
 * and would otherwise log:
 *   "Animated: `useNativeDriver` is not supported because the native
 *    animated module is missing."
 */
import { Platform } from 'react-native';

export const NATIVE_DRIVER = Platform.OS !== 'web';
