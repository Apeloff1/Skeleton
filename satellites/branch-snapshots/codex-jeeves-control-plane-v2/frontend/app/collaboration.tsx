import { makeLazyModalRoute } from '../components/SafeModalRoute';
export default makeLazyModalRoute(() => import('../features/Collaboration/CollaborationModal'), 'CollaborationRoute', 'CollaborationModal');
