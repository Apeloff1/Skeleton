import { makeLazyModalRoute } from '../src/components/SafeModalRoute';
export default makeLazyModalRoute(() => import('../src/features/Collaboration/CollaborationModal'), 'CollaborationRoute', 'CollaborationModal');
