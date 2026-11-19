import { makeLazyModalRoute } from '../components/SafeModalRoute';
export default makeLazyModalRoute(() => import('../features/MathAcademy/MathAcademyFullModal'), 'MathAcademyFullRoute', 'MathAcademyModal');
