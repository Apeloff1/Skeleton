import { makeLazyModalRoute } from '../components/SafeModalRoute';
export default makeLazyModalRoute(() => import('../features/CSAcademy/CSAcademyModal'), 'CSAcademyRoute', 'CSAcademyModal');
