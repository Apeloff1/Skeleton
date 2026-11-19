import { makeLazyModalRoute } from '../components/SafeModalRoute';
export default makeLazyModalRoute(() => import('../features/MathAcademy/MathAcademyModal'), 'MathAcademyRoute', 'MathAcademyModal');
