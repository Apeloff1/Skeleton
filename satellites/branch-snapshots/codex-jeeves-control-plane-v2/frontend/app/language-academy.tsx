import { makeLazyModalRoute } from '../components/SafeModalRoute';
export default makeLazyModalRoute(() => import('../features/LanguageAcademy/LanguageAcademyModal'), 'LanguageAcademyRoute', 'LanguageAcademyModal');
