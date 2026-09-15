import { makeLazyModalRoute } from '../components/SafeModalRoute';
export default makeLazyModalRoute(() => import('../features/Bible/BibleModal'), 'BibleRoute', 'BibleModal', { progress: { completedChapters: {}, bookmarks: [] }, onMarkComplete: () => {}, onToggleBookmark: () => {}, onLoadCode: () => {} } as any);
