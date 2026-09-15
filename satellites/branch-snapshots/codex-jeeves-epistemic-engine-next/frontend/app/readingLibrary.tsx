/**
 * /readingLibrary  —  deep-link route into the Reading Library modal.
 *
 * Previously the library could only be opened by tapping its tile in /menu,
 * which sets the global modalStore and navigates to '/'. On the web preview
 * the navigation race occasionally swallowed the open-modal action, leaving
 * the user on a blank splash. This dedicated route mounts the modal directly
 * so /readingLibrary always lands cleanly in the library — for users,
 * dev-tools and the testing agent alike.
 */
import { useState } from 'react';
import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { lazyDefault, LazyMount } from '../src/utils/lazyMount';
const ReadingLibraryModal = lazyDefault(() => import('../features/ReadingLibrary/ReadingLibraryModal').then((m) => ({ default: m.ReadingLibraryModal })));

export default function ReadingLibraryRoute() {
  const router = useRouter();
  const params = useLocalSearchParams<{ track?: string; from_class?: string }>();
  // The modal is in `visible` state on mount. When the user closes it, we
  // navigate back so they return to wherever they came from.
  const [open, setOpen] = useState(true);
  const fromClass = typeof params?.from_class === 'string' ? params.from_class : '';

  const handleClose = () => {
    setOpen(false);
    // Small defer so the close animation can run cleanly before nav.
    setTimeout(() => {
      if (fromClass) {
        router.replace({ pathname: '/curriculum' } as any);
      } else if (router.canGoBack && router.canGoBack()) {
        router.back();
      } else {
        router.replace('/menu' as any);
      }
    }, 50);
  };

  const goBackToClass = () => {
    if (!fromClass) return;
    setOpen(false);
    setTimeout(() => {
      router.replace({ pathname: '/class-week', params: { class_id: fromClass, week: 1 } } as any);
    }, 50);
  };

  return (
    <View style={{ flex: 1 }}>
      {!!fromClass && (
        <View style={[s.banner, { pointerEvents: 'box-none' }]}>
          <TouchableOpacity onPress={goBackToClass} style={s.bannerBtn} activeOpacity={0.85}>
            <Ionicons name="arrow-back-circle" size={18} color="#a78bfa" />
            <Text style={s.bannerText} numberOfLines={1}>← Back to class · {fromClass.replace(/_/g, ' ')}</Text>
          </TouchableOpacity>
        </View>
      )}
      {open && (
        <LazyMount>
          <ReadingLibraryModal visible={open} onClose={handleClose} />
        </LazyMount>
      )}
    </View>
  );
}

const s = StyleSheet.create({
  banner: {
    position: 'absolute', top: 6, left: 8, right: 8, zIndex: 10000,
    alignItems: 'flex-start', pointerEvents: 'box-none',
  },
  bannerBtn: {
    flexDirection: 'row', alignItems: 'center', gap: 6,
    backgroundColor: '#1f293bdd', borderColor: '#a78bfa', borderWidth: 1,
    paddingHorizontal: 10, paddingVertical: 6, borderRadius: 14,
  },
  bannerText: { color: '#a78bfa', fontSize: 11, fontWeight: '700', maxWidth: 240 },
});
