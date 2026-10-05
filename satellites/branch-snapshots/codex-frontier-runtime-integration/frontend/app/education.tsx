import { makeLazyModalRoute } from '../components/SafeModalRoute';
export default makeLazyModalRoute(() => import('../features/Education/EducationModal'), 'EducationRoute', 'EducationModal');
