import { makeLazyModalRoute } from '../src/components/SafeModalRoute';
export default makeLazyModalRoute(() => import('../src/features/MegaAcademy/MegaAcademyModal'), 'MegaAcademyRoute', 'MegaAcademyModal');
