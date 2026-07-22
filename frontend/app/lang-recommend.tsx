import { makeLazyModalRoute } from '../components/SafeModalRoute';
export default makeLazyModalRoute(() => import('../features/LanguageRecommend/LanguageRecommendModal'), 'LanguageRecommendRoute', 'LanguageRecommendModal');
