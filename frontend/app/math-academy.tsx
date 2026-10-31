import { makeLazyModalRoute } from '../src/components/SafeModalRoute';
export default makeLazyModalRoute(() => import('../src/features/MathAcademy/MathAcademyModal'), 'MathAcademyRoute', 'MathAcademyModal');
