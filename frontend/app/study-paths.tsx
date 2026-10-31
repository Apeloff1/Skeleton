import { makeLazyModalRoute } from '../src/components/SafeModalRoute';
export default makeLazyModalRoute(() => import('../src/features/StudyPaths/StudyPathsModal'), 'StudyPathsRoute', 'StudyPathsModal');
