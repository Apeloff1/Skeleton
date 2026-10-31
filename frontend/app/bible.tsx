import { makeLazyModalRoute } from '../src/components/SafeModalRoute';
export default makeLazyModalRoute(() => import('../src/features/Bible/BibleModal'), 'BibleRoute', 'BibleModal', { progress: { completedChapters: {}, bookmarks: [] }, onMarkComplete: () => {}, onToggleBookmark: () => {}, onLoadCode: () => {} } as any);
