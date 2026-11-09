import { makeLazyModalRoute } from '../src/components/SafeModalRoute';
export default makeLazyModalRoute(() => import('../src/features/LanguageAcademy/LanguageAcademyModal'), 'LanguageAcademyRoute', 'LanguageAcademyModal');
