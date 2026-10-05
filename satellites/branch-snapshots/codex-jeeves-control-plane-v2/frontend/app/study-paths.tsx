import { makeLazyModalRoute } from '../components/SafeModalRoute';
export default makeLazyModalRoute(() => import('../features/StudyPaths/StudyPathsModal'), 'StudyPathsRoute', 'StudyPathsModal');
