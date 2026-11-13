import { makeLazyModalRoute } from '../src/components/SafeModalRoute';
export default makeLazyModalRoute(() => import('../src/features/Education/EducationModal'), 'EducationRoute', 'EducationModal');
