import { makeLazyModalRoute } from '../components/SafeModalRoute';
export default makeLazyModalRoute(() => import('../features/MegaAcademy/MegaAcademyModal'), 'MegaAcademyRoute', 'MegaAcademyModal');
